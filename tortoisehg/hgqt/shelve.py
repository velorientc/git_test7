# shelve.py - TortoiseHg shelve and patch tool
#
# Copyright 2011 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

import os
import time

from tortoisehg.util import hglib
from tortoisehg.util.patchctx import patchctx
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, cmdui, chunks

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class ShelveDialog(QMainWindow):

    finished = pyqtSignal(int)

    wdir = _('Working Directory')

    def __init__(self, repo):
        QMainWindow.__init__(self)

        self.repo = repo

        self.splitter = QSplitter(self)
        self.splitter.setOrientation(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setObjectName('splitter')
        self.setCentralWidget(self.splitter)

        aframe = QFrame(self.splitter)
        avbox = QVBoxLayout()
        avbox.setSpacing(2)
        avbox.setMargin(2)
        avbox.setContentsMargins(2, 2, 2, 2)
        aframe.setLayout(avbox)
        ahbox = QHBoxLayout()
        ahbox.setSpacing(2)
        ahbox.setMargin(2)
        ahbox.setContentsMargins(2, 2, 2, 2)
        avbox.addLayout(ahbox)
        self.comboa = QComboBox(self)
        self.comboa.currentIndexChanged.connect(self.comboAChanged)
        self.delShelfButtonA = QPushButton(_('Delete'))
        self.delShelfButtonA.setToolTip(_('Delete the current shelf file'))
        ahbox.addWidget(self.comboa, 1)
        ahbox.addWidget(self.delShelfButtonA)

        self.browsea = chunks.ChunksWidget(repo, self)
        self.browsea.splitter.splitterMoved.connect(self.linkSplitters)
        self.browsea.linkActivated.connect(self.linkActivated)
        self.browsea.showMessage.connect(self.showMessage)
        avbox.addWidget(self.browsea)

        bframe = QFrame(self.splitter)
        bvbox = QVBoxLayout()
        bvbox.setSpacing(2)
        bvbox.setMargin(2)
        bvbox.setContentsMargins(2, 2, 2, 2)
        bframe.setLayout(bvbox)
        bhbox = QHBoxLayout()
        bhbox.setSpacing(2)
        bhbox.setMargin(2)
        bhbox.setContentsMargins(2, 2, 2, 2)
        bvbox.addLayout(bhbox)
        self.combob = QComboBox(self)
        self.combob.currentIndexChanged.connect(self.comboBChanged)
        self.delShelfButtonB = QPushButton(_('Delete'))
        self.delShelfButtonB.setToolTip(_('Delete the current shelf file'))
        self.delShelfButtonB.clicked.connect(self.deleteShelfB)
        bhbox.addWidget(self.combob, 1)
        bhbox.addWidget(self.delShelfButtonB)

        self.browseb = chunks.ChunksWidget(repo, self)
        self.browseb.splitter.splitterMoved.connect(self.linkSplitters)
        self.browseb.linkActivated.connect(self.linkActivated)
        self.browseb.showMessage.connect(self.showMessage)
        bvbox.addWidget(self.browseb)

        self.rbar = QToolBar(_('Refresh Toolbar'), objectName='rbar')
        self.addToolBar(self.rbar)
        self.refreshAction = a = QAction(_('Refresh'), self)
        a.setIcon(qtlib.geticon('reload'))
        a.setShortcut(QKeySequence.Refresh)
        a.triggered.connect(self.refresh)
        self.rbar.addAction(self.refreshAction)
        self.actionNew = a = QAction(_('New Shelf'), self)
        a.setIcon(qtlib.geticon('document-new'))
        a.triggered.connect(self.newShelf)
        self.rbar.addAction(self.actionNew)

        self.lefttbar = QToolBar(_('Left Toolbar'), objectName='lefttbar')
        self.addToolBar(self.lefttbar)
        self.deletea = a = QAction(_('Deleted selected chunks'), self)
        a.setIcon(qtlib.geticon('delfilesleft'))
        self.lefttbar.addAction(self.deletea)
        self.allright = a = QAction(_('Move all files right'), self)
        a.setIcon(qtlib.geticon('media-seek-forward'))
        self.lefttbar.addAction(self.allright)
        self.fileright = a = QAction(_('Move selected file right'), self)
        a.setIcon(qtlib.geticon('file2right'))
        self.lefttbar.addAction(self.fileright)
        self.chunksright = a = QAction(_('Move selected chunks right'), self)
        a.setIcon(qtlib.geticon('chunk2right'))
        self.lefttbar.addAction(self.chunksright)

        self.righttbar = QToolBar(_('Right Toolbar'), objectName='righttbar')
        self.addToolBar(self.righttbar)
        self.chunksleft = a = QAction(_('Move selected chunks left'), self)
        a.setIcon(qtlib.geticon('chunk2left'))
        self.righttbar.addAction(self.chunksleft)
        self.fileleft = a = QAction(_('Move selected file left'), self)
        a.setIcon(qtlib.geticon('file2left'))
        self.righttbar.addAction(self.fileleft)
        self.allleft = a = QAction(_('Move all files left'), self)
        a.setIcon(qtlib.geticon('media-seek-backward'))
        self.righttbar.addAction(self.allleft)
        self.deleteb = a = QAction(_('Deleted selected chunks'), self)
        a.setIcon(qtlib.geticon('delfilesright'))
        self.righttbar.addAction(self.deleteb)

        self.browsea.chunksSelected.connect(self.chunksright.setEnabled)
        self.browsea.chunksSelected.connect(self.deletea.setEnabled)
        self.browsea.fileSelected.connect(self.fileright.setEnabled)
        self.browseb.chunksSelected.connect(self.chunksleft.setEnabled)
        self.browseb.chunksSelected.connect(self.deleteb.setEnabled)
        self.browseb.fileSelected.connect(self.fileleft.setEnabled)

        self.statusbar = cmdui.ThgStatusBar(self)
        self.setStatusBar(self.statusbar)

        self.refreshCombos()
        repo.repositoryChanged.connect(self.refreshCombos)

        self.setWindowTitle(_('TortoiseHg Shelve - %s') % repo.displayname)
        self.restoreSettings()

    @pyqtSlot()
    def newShelf(self):
        dlg = QInputDialog(self, Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setWindowTitle(_('TortoiseHg New Shelf Name'))
        dlg.setLabelText(_('Specify name of new shelf'))
        dlg.setTextValue(time.strftime('%Y-%m-%d_%H-%M-%S'))
        if not dlg.exec_():
            return
        shelve = hglib.fromunicode(dlg.textValue())
        try:
            fn = os.path.join('shelves', shelve)
            if os.path.exists(self.repo.join(fn)):
                qtlib.ErrorMsgBox(_('File already exists'),
                                  _('A shelf file of that name already exists'))
                return
            self.repo.opener(fn, 'wb').write('')
            self.showMessage(_('New shelf created'))
        except EnvironmentError, e:
            self.showMessage(hglib.tounicode(str(e)))
        self.refreshCombos()

    @pyqtSlot()
    def deleteShelfA(self):
        shelf = hglib.fromunicode(self.combob.currentText())
        try:
            os.unlink(shelf)
            self.showMessage(_('Shelf deleted'))
        except EnvironmentError, e:
            self.showMessage(hglib.tounicode(str(e)))
        self.refreshCombos()

    @pyqtSlot()
    def deleteShelfB(self):
        shelf = hglib.fromunicode(self.combob.currentText())
        try:
            os.unlink(shelf)
            self.showMessage(_('Shelf deleted'))
        except EnvironmentError, e:
            self.showMessage(hglib.tounicode(str(e)))
        self.refreshCombos()

    @pyqtSlot()
    def refreshCombos(self):
        # TODO: preserve selection through refresh
        self.comboa.clear()
        self.combob.clear()
        shelves = [hglib.tounicode(s) for s in self.repo.thgshelves()]
        patches = self.repo.thgmqunappliedpatches[:]
        patches = [hglib.tounicode(self.repo.mq.join(p)) for p in patches]
        patches = shelves + patches
        self.comboa.addItems([self.wdir] + patches)
        self.combob.addItems(patches)
        if not patches:
            self.delShelfButtonB.setEnabled(False)
            self.browseb.setContext(patchctx('', self.repo, None))

    @pyqtSlot(int)
    def comboAChanged(self, index):
        if index == 0:
            rev = None
            self.delShelfButtonA.setEnabled(False)
        else:
            rev = hglib.fromunicode(self.comboa.currentText())
            self.delShelfButtonA.setEnabled(rev.startswith(self.repo.shelfdir))
        self.browsea.setContext(self.repo.changectx(rev))

    @pyqtSlot(int)
    def comboBChanged(self, index):
        rev = hglib.fromunicode(self.combob.currentText())
        self.delShelfButtonB.setEnabled(rev.startswith(self.repo.shelfdir))
        self.browseb.setContext(self.repo.changectx(rev))

    def refresh(self):
        self.browsea.refresh()
        self.browseb.refresh()
        self.refreshCombos()

    def linkSplitters(self, pos, index):
        if self.browsea.splitter.sizes()[0] != pos:
            self.browsea.splitter.moveSplitter(pos, index)
        if self.browseb.splitter.sizes()[0] != pos:
            self.browseb.splitter.moveSplitter(pos, index)

    def linkActivated(self, linktext):
        pass

    def showMessage(self, message):
        self.statusbar.showMessage(message)

    def storeSettings(self):
        s = QSettings()
        wb = "shelve/"
        s.setValue(wb + 'geometry', self.saveGeometry())
        s.setValue(wb + 'windowState', self.saveState())
        s.setValue(wb + 'filesplitter', self.browsea.splitter.saveState())

    def restoreSettings(self):
        s = QSettings()
        wb = "shelve/"
        self.restoreGeometry(s.value(wb + 'geometry').toByteArray())
        self.restoreState(s.value(wb + 'windowState').toByteArray())
        self.browsea.splitter.restoreState(
                          s.value(wb + 'filesplitter').toByteArray())
        self.browseb.splitter.restoreState(
                          s.value(wb + 'filesplitter').toByteArray())

    def safeToExit(self):
        return True

    def closeEvent(self, event):
        if not self.safeToExit():
            event.ignore()
        else:
            self.storeSettings()
            # mimic QDialog exit
            self.finished.emit(0)

def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    from tortoisehg.hgqt import thgrepo
    repo = thgrepo.repository(ui, path=paths.find_root())
    return ShelveDialog(repo)

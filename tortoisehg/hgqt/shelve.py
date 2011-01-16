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
        self.shelves = []
        self.patches = []

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
        self.delShelfButtonA.clicked.connect(self.deleteShelfA)
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
        a.triggered.connect(self.refreshCombos)
        self.rbar.addAction(self.refreshAction)
        self.actionNew = a = QAction(_('New Shelf'), self)
        a.setIcon(qtlib.geticon('document-new'))
        a.triggered.connect(self.newShelf)
        self.rbar.addAction(self.actionNew)

        self.lefttbar = QToolBar(_('Left Toolbar'), objectName='lefttbar')
        self.addToolBar(self.lefttbar)
        self.deletea = a = QAction(_('Deleted selected chunks'), self)
        self.deletea.triggered.connect(self.browsea.deleteSelectedChunks)
        a.setIcon(qtlib.geticon('delfilesleft'))
        self.lefttbar.addAction(self.deletea)
        self.allright = a = QAction(_('Move all files right'), self)
        self.allright.triggered.connect(self.moveFilesRight)
        a.setIcon(qtlib.geticon('all2right'))
        self.lefttbar.addAction(self.allright)
        self.fileright = a = QAction(_('Move selected file right'), self)
        self.fileright.triggered.connect(self.moveFileRight)
        a.setIcon(qtlib.geticon('file2right'))
        self.lefttbar.addAction(self.fileright)
        self.editfilea = a = QAction(_('Edit file'), self)
        a.setIcon(qtlib.geticon('edit-find'))
        self.lefttbar.addAction(self.editfilea)
        self.chunksright = a = QAction(_('Move selected chunks right'), self)
        self.chunksright.triggered.connect(self.moveChunksRight)
        a.setIcon(qtlib.geticon('chunk2right'))
        self.lefttbar.addAction(self.chunksright)

        self.righttbar = QToolBar(_('Right Toolbar'), objectName='righttbar')
        self.addToolBar(self.righttbar)
        self.chunksleft = a = QAction(_('Move selected chunks left'), self)
        self.chunksleft.triggered.connect(self.moveChunksLeft)
        a.setIcon(qtlib.geticon('chunk2left'))
        self.righttbar.addAction(self.chunksleft)
        self.editfileb = a = QAction(_('Edit file'), self)
        a.setIcon(qtlib.geticon('edit-find'))
        self.righttbar.addAction(self.editfileb)
        self.fileleft = a = QAction(_('Move selected file left'), self)
        self.fileleft.triggered.connect(self.moveFileLeft)
        a.setIcon(qtlib.geticon('file2left'))
        self.righttbar.addAction(self.fileleft)
        self.allleft = a = QAction(_('Move all files left'), self)
        self.allleft.triggered.connect(self.moveFilesLeft)
        a.setIcon(qtlib.geticon('all2left'))
        self.righttbar.addAction(self.allleft)
        self.deleteb = a = QAction(_('Deleted selected chunks'), self)
        self.deleteb.triggered.connect(self.browseb.deleteSelectedChunks)
        a.setIcon(qtlib.geticon('delfilesright'))
        self.righttbar.addAction(self.deleteb)

        self.editfilea.triggered.connect(self.browsea.editCurrentFile)
        self.editfileb.triggered.connect(self.browseb.editCurrentFile)

        self.browsea.chunksSelected.connect(self.chunksright.setEnabled)
        self.browsea.chunksSelected.connect(self.deletea.setEnabled)
        self.browsea.fileSelected.connect(self.fileright.setEnabled)
        self.browsea.fileSelected.connect(self.editfilea.setEnabled)
        self.browsea.fileModified.connect(self.refreshCombos)
        self.browsea.fileModelEmpty.connect(self.allright.setDisabled)
        self.browseb.chunksSelected.connect(self.chunksleft.setEnabled)
        self.browseb.chunksSelected.connect(self.deleteb.setEnabled)
        self.browseb.fileSelected.connect(self.fileleft.setEnabled)
        self.browseb.fileSelected.connect(self.editfileb.setEnabled)
        self.browseb.fileModified.connect(self.refreshCombos)
        self.browseb.fileModelEmpty.connect(self.allleft.setDisabled)

        self.statusbar = cmdui.ThgStatusBar(self)
        self.setStatusBar(self.statusbar)

        self.refreshCombos()
        repo.repositoryChanged.connect(self.refreshCombos)

        self.setWindowTitle(_('TortoiseHg Shelve - %s') % repo.displayname)
        self.restoreSettings()

    @pyqtSlot()
    def moveFileRight(self):
        file, _ = self.browsea.getSelectedFileAndChunks()
        chunks = self.browsea.getChunksForFile(file)
        if self.browseb.mergeChunks(file, chunks):
            self.browsea.removeFile(file)

    @pyqtSlot()
    def moveFileLeft(self):
        file, _ = self.browseb.getSelectedFileAndChunks()
        chunks = self.browseb.getChunksForFile(file)
        if self.browsea.mergeChunks(file, chunks):
            self.browseb.removeFile(file)

    @pyqtSlot()
    def moveFilesRight(self):
        for file in self.browsea.getFileList():
            chunks = self.browsea.getChunksForFile(file)
            if self.browseb.mergeChunks(file, chunks):
                self.browsea.removeFile(file)

    @pyqtSlot()
    def moveFilesLeft(self):
        for file in self.browseb.getFileList():
            chunks = self.browseb.getChunksForFile(file)
            if self.browsea.mergeChunks(file, chunks):
                self.browseb.removeFile(file)

    @pyqtSlot()
    def moveChunksRight(self):
        file, chunks = self.browsea.getSelectedFileAndChunks()
        if self.browseb.mergeChunks(file, chunks):
            self.browsea.deleteSelectedChunks()

    @pyqtSlot()
    def moveChunksLeft(self):
        file, chunks = self.browseb.getSelectedFileAndChunks()
        if self.browsea.mergeChunks(file, chunks):
            self.browseb.deleteSelectedChunks()

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
            shelfpath = self.repo.join(fn)
            if os.path.exists(shelfpath):
                qtlib.ErrorMsgBox(_('File already exists'),
                                  _('A shelf file of that name already exists'))
                return
            self.repo.opener(fn, 'wb').write('')
            self.showMessage(_('New shelf created'))
            self.refreshCombos()
            if shelfpath in self.shelves:
                self.combob.setCurrentIndex(self.shelves.index(shelfpath))
        except EnvironmentError, e:
            self.showMessage(hglib.tounicode(str(e)))

    @pyqtSlot()
    def deleteShelfA(self):
        shelf = self.currentPatchA()
        ushelf = hglib.tounicode(os.path.basename(shelf))
        if not qtlib.QuestionMsgBox(_('Are you sure?'),
                                    _('Delete shelf file %s?') % ushelf):
            return
        try:
            os.unlink(shelf)
            self.showMessage(_('Shelf deleted'))
        except EnvironmentError, e:
            self.showMessage(hglib.tounicode(str(e)))
        self.refreshCombos()

    @pyqtSlot()
    def deleteShelfB(self):
        shelf = self.currentPatchB()
        ushelf = hglib.tounicode(os.path.basename(shelf))
        if not qtlib.QuestionMsgBox(_('Are you sure?'),
                                    _('Delete shelf file %s?') % ushelf):
            return
        try:
            os.unlink(shelf)
            self.showMessage(_('Shelf deleted'))
        except EnvironmentError, e:
            self.showMessage(hglib.tounicode(str(e)))
        self.refreshCombos()

    def currentPatchA(self):
        idx = self.comboa.currentIndex()
        if idx == -1:
            return None
        if idx == 0:
            return self.wdir
        idx -= 1
        if idx < len(self.shelves):
            return self.shelves[idx]
        idx -= len(self.shelves)
        if idx < len(self.patches):
            return self.patches[idx]
        return None

    def currentPatchB(self):
        idx = self.combob.currentIndex()
        if idx == -1:
            return None
        if idx < len(self.shelves):
            return self.shelves[idx]
        idx -= len(self.shelves)
        if idx < len(self.patches):
            return self.patches[idx]
        return None

    @pyqtSlot()
    def refreshCombos(self):
        shelvea, shelveb = self.currentPatchA(), self.currentPatchB()

        shelves = self.repo.thgshelves()
        disp = [_('Shelf: %s') % hglib.tounicode(s) for s in shelves]

        patches = self.repo.thgmqunappliedpatches
        disp += [_('Patch: %s') % hglib.tounicode(p) for p in patches]

        # store fully qualified paths
        self.shelves = [os.path.join(self.repo.shelfdir, s) for s in shelves]
        self.patches = [self.repo.mq.join(p) for p in patches]

        self.comboRefreshInProgress = True
        self.comboa.clear()
        self.combob.clear()
        self.comboa.addItems([self.wdir] + disp)
        self.combob.addItems(disp)

        # attempt to restore selection
        if shelvea == self.wdir:
            idxa = 0
        elif shelvea in self.shelves:
            idxa = self.shelves.index(shelvea) + 1
        elif shelvea in self.patches:
            idxa = len(self.shelves) + self.patches.index(shelvea) + 1
        else:
            idxa = 0
        self.comboa.setCurrentIndex(idxa)

        if shelveb in self.shelves:
            idxb = self.shelves.index(shelveb)
        elif shelveb in self.patches:
            idxb = len(self.shelves) + self.patches.index(shelveb)
        else:
            idxb = 0
        self.combob.setCurrentIndex(idxb)
        self.comboRefreshInProgress = False

        self.comboAChanged(idxa)
        self.comboBChanged(idxb)
        if not patches and not shelves:
            self.delShelfButtonB.setEnabled(False)
            self.browseb.setContext(patchctx('', self.repo, None))

    @pyqtSlot(int)
    def comboAChanged(self, index):
        if self.comboRefreshInProgress:
            return
        if index == 0:
            rev = None
            self.delShelfButtonA.setEnabled(False)
        else:
            rev = self.currentPatchA()
            self.delShelfButtonA.setEnabled(index <= len(self.shelves))
        self.browsea.setContext(self.repo.changectx(rev))

    @pyqtSlot(int)
    def comboBChanged(self, index):
        if self.comboRefreshInProgress:
            return
        rev = self.currentPatchB()
        self.delShelfButtonB.setEnabled(index < len(self.shelves))
        self.browseb.setContext(self.repo.changectx(rev))

    @pyqtSlot(int, int)
    def linkSplitters(self, pos, index):
        if self.browsea.splitter.sizes()[0] != pos:
            self.browsea.splitter.moveSplitter(pos, index)
        if self.browseb.splitter.sizes()[0] != pos:
            self.browseb.splitter.moveSplitter(pos, index)

    @pyqtSlot(QString)
    def linkActivated(self, linktext):
        pass

    @pyqtSlot(QString)
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

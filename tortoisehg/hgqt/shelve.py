# shelve.py - TortoiseHg shelve and patch tool
#
# Copyright 2011 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.
#
from tortoisehg.util import hglib
from tortoisehg.util.patchctx import patchctx
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, cmdui, chunks

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class ShelveDialog(QMainWindow):
    finished = pyqtSignal(int)

    def __init__(self, repo, ctxa, ctxb):
        QMainWindow.__init__(self)

        self.repo = repo

        self.splitter = QSplitter(self)
        self.splitter.setOrientation(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setObjectName('splitter')
        self.setCentralWidget(self.splitter)

        self.browsea = chunks.ChunksWidget(repo, self.splitter)
        self.browsea.splitter.splitterMoved.connect(self.linkSplitters)
        self.browsea.linkActivated.connect(self.linkActivated)
        self.browsea.showMessage.connect(self.showMessage)
        self.browseb = chunks.ChunksWidget(repo, self.splitter)
        self.browseb.splitter.splitterMoved.connect(self.linkSplitters)
        self.browseb.linkActivated.connect(self.linkActivated)
        self.browseb.showMessage.connect(self.showMessage)

        self.rbar = QToolBar(_('Refresh Toolbar'), objectName='rbar')
        self.addToolBar(self.rbar)
        self.refresh = a = QAction(_('Refresh'), self)
        a.setIcon(qtlib.geticon('reload'))
        a.setShortcut(QKeySequence.Refresh)
        a.triggered.connect(self.browsea.refresh)
        a.triggered.connect(self.browseb.refresh)
        self.rbar.addAction(self.refresh)

        self.lefttbar = QToolBar(_('Left Toolbar'), objectName='lefttbar')
        self.addToolBar(self.lefttbar)
        self.allright = a = QAction(_('Move all files right'), self)
        a.setIcon(qtlib.geticon('media-seek-forward'))
        self.lefttbar.addAction(self.allright)
        self.fileright = a = QAction(_('Move selected file right'), self)
        a.setIcon(qtlib.geticon('media-playback-start'))
        self.lefttbar.addAction(self.fileright)
        self.chunksright = a = QAction(_('Move selected chunks right'), self)
        a.setIcon(qtlib.geticon('merge'))
        self.lefttbar.addAction(self.chunksright)
        self.deletea = a = QAction(_('Deleted selected chunks'), self)
        a.setIcon(qtlib.geticon('edit-cut'))
        self.lefttbar.addAction(self.deletea)

        self.righttbar = QToolBar(_('Right Toolbar'), objectName='righttbar')
        self.addToolBar(self.righttbar)
        self.deleteb = a = QAction(_('Deleted selected chunks'), self)
        a.setIcon(qtlib.geticon('edit-cut'))
        self.righttbar.addAction(self.deleteb)
        self.chunksleft = a = QAction(_('Move selected chunks left'), self)
        a.setIcon(qtlib.geticon('merge'))
        self.righttbar.addAction(self.chunksleft)
        self.fileleft = a = QAction(_('Move selected file left'), self)
        a.setIcon(qtlib.geticon('back'))
        self.righttbar.addAction(self.fileleft)
        self.allleft = a = QAction(_('Move all files left'), self)
        a.setIcon(qtlib.geticon('media-seek-backward'))
        self.righttbar.addAction(self.allleft)

        self.browsea.chunksSelected.connect(self.chunksright.setEnabled)
        self.browsea.chunksSelected.connect(self.deletea.setEnabled)
        self.browsea.fileSelected.connect(self.fileright.setEnabled)
        self.browseb.chunksSelected.connect(self.chunksleft.setEnabled)
        self.browseb.chunksSelected.connect(self.deleteb.setEnabled)
        self.browseb.fileSelected.connect(self.fileleft.setEnabled)

        self.statusbar = cmdui.ThgStatusBar(self)
        self.setStatusBar(self.statusbar)

        self.browsea.setContext(ctxa or repo.changectx(None))
        self.browseb.setContext(ctxb or repo.changectx(None))

        self.restoreSettings()

    def linkSplitters(self, pos, index):
        if self.browsea.splitter.sizes()[0] != pos:
            self.browsea.splitter.moveSplitter(pos, index)
        if self.browseb.splitter.sizes()[0] != pos:
            self.browseb.splitter.moveSplitter(pos, index)

    def linkActivated(self, linktext):
        pass

    def showMessage(self, message):
        self.stbar.showMessage(message)

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
    return ShelveDialog(repo, None, None)

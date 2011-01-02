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
        self.setCentralWidget(self.splitter)

        self.browsea = chunks.ChunksWidget(repo, ctxa, self.splitter)
        self.browsea.splitter.splitterMoved.connect(self.linkSplitters)
        self.browsea.linkActivated.connect(self.linkActivated)
        self.browsea.showMessage.connect(self.showMessage)
        self.browseb = chunks.ChunksWidget(repo, ctxb, self.splitter)
        self.browseb.splitter.splitterMoved.connect(self.linkSplitters)
        self.browseb.linkActivated.connect(self.linkActivated)
        self.browseb.showMessage.connect(self.showMessage)

        self.xfertbar = QToolBar(_('Xfer Toolbar'), objectName='xfertbar')
        self.addToolBar(self.xfertbar)
        self.allright = a = QAction(_('Move all files right'), self)
        a.setIcon(qtlib.geticon('media-seek-forward'))
        self.xfertbar.addAction(self.allright)
        self.fileright = a = QAction(_('Move selected file right'), self)
        a.setIcon(qtlib.geticon('media-playback-start'))
        self.xfertbar.addAction(self.fileright)
        self.chunksright = a = QAction(_('Move selected chunks right'), self)
        a.setIcon(qtlib.geticon('merge'))
        self.xfertbar.addAction(self.chunksright)
        self.deletea = a = QAction(_('Deleted selected chunks'), self)
        a.setIcon(qtlib.geticon('edit-cut'))
        self.xfertbar.addAction(self.deletea)
        self.xfertbar.addSeparator()
        self.deleteb = a = QAction(_('Deleted selected chunks'), self)
        a.setIcon(qtlib.geticon('edit-cut'))
        self.xfertbar.addAction(self.deleteb)
        self.chunksleft = a = QAction(_('Move selected chunks left'), self)
        a.setIcon(qtlib.geticon('merge'))
        self.xfertbar.addAction(self.chunksleft)
        self.fileleft = a = QAction(_('Move selected file left'), self)
        a.setIcon(qtlib.geticon('back'))
        self.xfertbar.addAction(self.fileleft)
        self.allleft = a = QAction(_('Move all files left'), self)
        a.setIcon(qtlib.geticon('media-seek-backward'))
        self.xfertbar.addAction(self.allleft)

        self.statusbar = cmdui.ThgStatusBar(self)
        self.setStatusBar(self.statusbar)

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

    def restoreSettings(self):
        s = QSettings()
        wb = "shelve/"
        self.restoreGeometry(s.value(wb + 'geometry').toByteArray())
        self.restoreState(s.value(wb + 'windowState').toByteArray())

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

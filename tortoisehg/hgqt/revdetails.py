# revdetails.py - TortoiseHg revision details widget
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
# Copyright (C) 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

from tortoisehg.hgqt.qtlib import getfont, geticon, descriptionhtmlizer
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.filelistmodel import HgFileListModel
from tortoisehg.hgqt.filelistview import HgFileListView
from tortoisehg.hgqt.fileview import HgFileView
from tortoisehg.hgqt.revpanel import RevPanelWidget
from tortoisehg.hgqt import thgrepo, qscilib

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class RevDetailsWidget(QWidget):

    showMessage = pyqtSignal(QString)
    linkActivated = pyqtSignal(unicode)
    grepRequested = pyqtSignal(unicode, dict)
    revisionSelected = pyqtSignal(int)
    updateToRevision = pyqtSignal(int)

    def __init__(self, repo, parent):
        QWidget.__init__(self, parent)

        self.repo = repo
        self.splitternames = []

        self._deschtmlize = descriptionhtmlizer(repo.ui)
        repo.configChanged.connect(self._updatedeschtmlizer)

        # these are used to know where to go after a reload
        self._last_rev = None
        self._reload_file = None

        self.setupUi()
        self.createActions()
        self.setupModels()

    def setRepo(self, repo):
        self.repo = repo
        self.fileview.setRepo(repo)
        self.filelist.setRepo(repo)

    def setupUi(self):
        SP = QSizePolicy
        sp = SP(SP.Preferred, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setSizePolicy(sp)

        # + basevbox -------------------------------------------------------+
        # |+ filelistsplit ........                                         |
        # | + filelistframe (vbox)    | + panelframe (vbox)                 |
        # |  + filelisttbar           |  + revpanel                         |
        # +---------------------------+-------------------------------------+
        # |  + filelist               |  + messagesplitter                  |
        # |                           |  :+ message                         |
        # |                           |  :----------------------------------+
        # |                           |   + fileview                        |
        # +---------------------------+-------------------------------------+

        basevbox = QVBoxLayout(self)
        basevbox.setSpacing(0)
        basevbox.setMargin(0)
        basevbox.setContentsMargins(2, 2, 2, 2)

        self.filelistsplit = QSplitter(self)
        basevbox.addWidget(self.filelistsplit)

        self.splitternames.append('filelistsplit')

        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.filelistsplit.sizePolicy().hasHeightForWidth())
        self.filelistsplit.setSizePolicy(sp)
        self.filelistsplit.setOrientation(Qt.Horizontal)
        self.filelistsplit.setChildrenCollapsible(False)

        self.filelisttbar = QToolBar(_('File List Toolbar'))
        self.filelisttbar.setIconSize(QSize(16,16))
        self.filelist = HgFileListView(self.repo, self)
        self.filelist.linkActivated.connect(self.linkActivated)

        self.filelistframe = QFrame(self.filelistsplit)
        sp = SP(SP.Preferred, SP.Preferred)
        sp.setHorizontalStretch(3)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(
            self.filelistframe.sizePolicy().hasHeightForWidth())
        self.filelistframe.setSizePolicy(sp)
        self.filelistframe.setFrameShape(QFrame.NoFrame)
        vbox = QVBoxLayout()
        vbox.setSpacing(0)
        vbox.setMargin(0)
        vbox.addWidget(self.filelisttbar)
        vbox.addWidget(self.filelist)
        self.filelistframe.setLayout(vbox)

        self.fileviewframe = QFrame(self.filelistsplit)
        sp = SP(SP.Preferred, SP.Preferred)
        sp.setHorizontalStretch(7)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(
            self.fileviewframe.sizePolicy().hasHeightForWidth())
        self.fileviewframe.setSizePolicy(sp)
        self.fileviewframe.setFrameShape(QFrame.NoFrame)

        vbox = QVBoxLayout(self.fileviewframe)
        vbox.setSpacing(0)
        vbox.setSizeConstraint(QLayout.SetDefaultConstraint)
        vbox.setMargin(0)
        panelframevbox = vbox

        self.messagesplitter = QSplitter(self.fileviewframe)
        self.splitternames.append('messagesplitter')
        sp = SP(SP.Preferred, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.messagesplitter.sizePolicy().hasHeightForWidth())
        self.messagesplitter.setSizePolicy(sp)
        self.messagesplitter.setMinimumSize(QSize(50, 50))
        self.messagesplitter.setFrameShape(QFrame.NoFrame)
        self.messagesplitter.setLineWidth(0)
        self.messagesplitter.setMidLineWidth(0)
        self.messagesplitter.setOrientation(Qt.Vertical)
        self.messagesplitter.setOpaqueResize(True)
        self.message = QTextBrowser(self.messagesplitter,
                                    lineWrapMode=QTextEdit.NoWrap,
                                    openLinks=False)
        self.message.minimumSizeHint = lambda: QSize(0, 25)
        self.message.anchorClicked.connect(
            lambda url: self.linkActivated.emit(url.toString()))

        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(2)
        sp.setHeightForWidth(self.message.sizePolicy().hasHeightForWidth())
        self.message.setSizePolicy(sp)
        self.message.setMinimumSize(QSize(0, 0))
        f = getfont('fontcomment')
        self.message.setFont(f.font())
        f.changed.connect(self.forwardFont)

        self.fileview = HgFileView(self.repo, self.messagesplitter)
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(5)
        sp.setHeightForWidth(self.fileview.sizePolicy().hasHeightForWidth())
        self.fileview.setSizePolicy(sp)
        self.fileview.setMinimumSize(QSize(0, 0))
        self.fileview.linkActivated.connect(self.linkActivated)
        self.fileview.setFont(getfont('fontdiff').font())
        self.fileview.showMessage.connect(self.showMessage)
        self.fileview.grepRequested.connect(self.grepRequested)
        self.fileview.revisionSelected.connect(self.revisionSelected)
        self.filelist.fileSelected.connect(self.fileview.displayFile)
        self.filelist.clearDisplay.connect(self.fileview.clearDisplay)

        self.revpanel = RevPanelWidget(self.repo)
        self.revpanel.linkActivated.connect(self.linkActivated)

        panelframevbox.addWidget(self.revpanel)
        panelframevbox.addWidget(self.messagesplitter)

    def forwardFont(self, font):
        self.message.setFont(font)

    def setupModels(self):
        self.filelistmodel = HgFileListModel(self)
        self.filelist.setModel(self.filelistmodel)

    def createActions(self):
        def fileActivated():
            idx = self.filelist.currentIndex()
            self.filelist.fileActivated(idx, alternate=True)
        self.actionActivateFileAlt = QAction('Activate alt. file', self)
        self.actionActivateFileAlt.setShortcuts([Qt.ALT+Qt.Key_Return,
                                                 Qt.ALT+Qt.Key_Enter])
        self.actionActivateFileAlt.triggered.connect(fileActivated)

        self.actionUpdate = a = self.filelisttbar.addAction(
            geticon('hg-update'), _('Update to this revision'))
        a.triggered.connect(lambda: self.updateToRevision.emit(self._last_rev))
        self.filelisttbar.addSeparator()
        self.filelisttbar.addAction(self.filelist.actionShowAllMerge)

        self.actionNextLine = QAction('Next line', self)
        self.actionNextLine.setShortcut(Qt.SHIFT + Qt.Key_Down)
        self.actionNextLine.triggered.connect(self.fileview.nextLine)
        self.addAction(self.actionNextLine)
        self.actionPrevLine = QAction('Prev line', self)
        self.actionPrevLine.setShortcut(Qt.SHIFT + Qt.Key_Up)
        self.actionPrevLine.triggered.connect(self.fileview.prevLine)
        self.addAction(self.actionPrevLine)
        self.actionNextCol = QAction('Next column', self)
        self.actionNextCol.setShortcut(Qt.SHIFT + Qt.Key_Right)
        self.actionNextCol.triggered.connect(self.fileview.nextCol)
        self.addAction(self.actionNextCol)
        self.actionPrevCol = QAction('Prev column', self)
        self.actionPrevCol.setShortcut(Qt.SHIFT + Qt.Key_Left)
        self.actionPrevCol.triggered.connect(self.fileview.prevCol)
        self.addAction(self.actionPrevCol)

    def onRevisionSelected(self, rev):
        'called by repowidget when repoview changes revisions'
        self._last_rev = rev
        ctx = self.repo.changectx(rev)
        self.revpanel.set_revision(rev)
        self.revpanel.update(repo = self.repo)
        self.message.setHtml('<pre>%s</pre>'
                             % self._deschtmlize(ctx.description()))
        self.fileview.setContext(ctx)
        self.filelist.setContext(ctx)

    @pyqtSlot()
    def _updatedeschtmlizer(self):
        self._deschtmlize = descriptionhtmlizer(self.repo.ui)
        self.onRevisionSelected(self._last_rev)  # regenerate desc html

    def reload(self):
        'Task tab is reloaded, or repowidget is refreshed'
        if type(self._last_rev) is int and len(self.repo) <= self._last_rev:
            self._last_rev = 'tip'
        f = self.filelist.currentFile()
        self.onRevisionSelected(self._last_rev)
        self.filelist.selectFile(f)

    def saveSettings(self, s):
        wb = "RevDetailsWidget/"
        for n in self.splitternames:
            s.setValue(wb + n, getattr(self, n).saveState())
        s.setValue(wb + 'revpanel.expanded', self.revpanel.is_expanded())
        self.fileview.saveSettings(s, 'revpanel/fileview')

    def loadSettings(self, s):
        wb = "RevDetailsWidget/"
        for n in self.splitternames:
            getattr(self, n).restoreState(s.value(wb + n).toByteArray())
        expanded = s.value(wb + 'revpanel.expanded', False).toBool()
        self.revpanel.set_expanded(expanded)
        self.fileview.loadSettings(s, 'revpanel/fileview')

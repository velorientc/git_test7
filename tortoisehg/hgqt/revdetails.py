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

    def __init__(self, repo):
        QWidget.__init__(self)

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

        self.fileview.setFont(getfont('fontdiff').font())
        self.fileview.showMessage.connect(self.showMessage)
        self.fileview.grepRequested.connect(self.grepRequested)
        self.fileview.revisionSelected.connect(self.revisionSelected)

    def setRepo(self, repo):
        self.repo = repo
        self.fileview.setRepo(repo)

    def setupUi(self):
        SP = QSizePolicy
        sp = SP(SP.Preferred, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setSizePolicy(sp)

        # + revisiondetails_layout -----------------------------------------+
        # |+ filelist_splitter ........                                     |
        # | + tbarFileListFrame (vbox)| + cset_and_file_details_frame (vbox)|
        # |  + filelistToolbar        |  + revpanel                         |
        # +---------------------------+-------------------------------------+
        # |  + filelist               |  + message_splitter                 |
        # |                           |  :+ message                         |
        # |                           |  :----------------------------------+
        # |                           |   + fileview                        |
        # +---------------------------+-------------------------------------+

        revisiondetails_layout = QVBoxLayout(self)
        revisiondetails_layout.setSpacing(0)
        revisiondetails_layout.setMargin(0)
        revisiondetails_layout.setContentsMargins(2, 2, 2, 2)

        self.filelist_splitter = QSplitter(self)
        self.splitternames.append('filelist_splitter')

        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.filelist_splitter.sizePolicy().hasHeightForWidth())
        self.filelist_splitter.setSizePolicy(sp)
        self.filelist_splitter.setOrientation(Qt.Horizontal)
        self.filelist_splitter.setChildrenCollapsible(False)

        self.filelistToolbar = QToolBar(_('File List Toolbar'))
        self.filelistToolbar.setIconSize(QSize(16,16))
        self.filelist = HgFileListView()

        self.tbarFileListFrame = QFrame(self.filelist_splitter)
        sp = SP(SP.Preferred, SP.Preferred)
        sp.setHorizontalStretch(3)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(
            self.tbarFileListFrame.sizePolicy().hasHeightForWidth())
        self.tbarFileListFrame.setSizePolicy(sp)
        self.tbarFileListFrame.setFrameShape(QFrame.NoFrame)
        vbox = QVBoxLayout()
        vbox.setSpacing(0)
        vbox.setMargin(0)
        vbox.addWidget(self.filelistToolbar)
        vbox.addWidget(self.filelist)
        self.tbarFileListFrame.setLayout(vbox)

        self.cset_and_file_details_frame = QFrame(self.filelist_splitter)
        sp = SP(SP.Preferred, SP.Preferred)
        sp.setHorizontalStretch(7)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(
            self.cset_and_file_details_frame.sizePolicy().hasHeightForWidth())
        self.cset_and_file_details_frame.setSizePolicy(sp)
        self.cset_and_file_details_frame.setFrameShape(QFrame.NoFrame)

        vbox = QVBoxLayout(self.cset_and_file_details_frame)
        vbox.setSpacing(0)
        vbox.setSizeConstraint(QLayout.SetDefaultConstraint)
        vbox.setMargin(0)
        cset_and_file_details_layout = vbox

        self.message_splitter = QSplitter(self.cset_and_file_details_frame)
        self.splitternames.append('message_splitter')
        sp = SP(SP.Preferred, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.message_splitter.sizePolicy().hasHeightForWidth())
        self.message_splitter.setSizePolicy(sp)
        self.message_splitter.setMinimumSize(QSize(50, 50))
        self.message_splitter.setFrameShape(QFrame.NoFrame)
        self.message_splitter.setLineWidth(0)
        self.message_splitter.setMidLineWidth(0)
        self.message_splitter.setOrientation(Qt.Vertical)
        self.message_splitter.setOpaqueResize(True)
        self.message = QTextBrowser(self.message_splitter,
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

        self.fileview = HgFileView(self.repo, self.message_splitter)
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(5)
        sp.setHeightForWidth(self.fileview.sizePolicy().hasHeightForWidth())
        self.fileview.setSizePolicy(sp)
        self.fileview.setMinimumSize(QSize(0, 0))

        self.revpanel = RevPanelWidget(self.repo)
        self.revpanel.linkActivated.connect(self.linkActivated)

        cset_and_file_details_layout.addWidget(self.revpanel)
        cset_and_file_details_layout.addWidget(self.message_splitter)

        revisiondetails_layout.addWidget(self.filelist_splitter)

        self.filelist.fileRevSelected.connect(self.onFileRevSelected)
        self.filelist.clearDisplay.connect(self.fileview.clearDisplay)

    def forwardFont(self, font):
        self.message.setFont(font)

    def createActions(self):
        def fileActivated():
            idx = self.filelist.currentIndex()
            self.filelist.fileActivated(idx, alternate=True)
        self.actionActivateFileAlt = QAction('Activate alt. file', self)
        self.actionActivateFileAlt.setShortcuts([Qt.ALT+Qt.Key_Return,
                                                 Qt.ALT+Qt.Key_Enter])
        self.actionActivateFileAlt.triggered.connect(fileActivated)

        self.actionUpdate = a = self.filelistToolbar.addAction(
            geticon('hg-update'), _('Update to this revision'))
        a.triggered.connect(lambda: self.updateToRevision.emit(self._last_rev))
        self.filelistToolbar.addSeparator()
        self.filelistToolbar.addAction(self.filelist.actionShowAllMerge)
        self.filelistToolbar.addAction(self.filelist.actionSecondParent)

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

    def create_models(self):
        self.filelistmodel = HgFileListModel(self.repo, self)

    def setupModels(self):
        self.create_models()
        self.filelist.setModel(self.filelistmodel)

    @pyqtSlot(object, object, object)
    def onFileRevSelected(self, file, rev, status):
        self.fileview.displayFile(file, rev, status)

    def onRevisionSelected(self, rev):
        'called by repowidget when repoview changes revisions'
        self._last_rev = rev
        ctx = self.repo.changectx(rev)
        self.revpanel.set_revision(rev)
        self.revpanel.update(repo = self.repo)
        self.message.setHtml('<pre>%s</pre>'
                             % self._deschtmlize(ctx.description()))
        self.fileview.setContext(ctx)
        self.filelistmodel.setContext(ctx)

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

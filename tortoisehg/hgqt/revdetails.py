# -*- coding: iso-8859-1 -*-
#!/usr/bin/env python
# repowidget.py - TortoiseHg repository widget
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
# Copyright (C) 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

from tortoisehg.hgqt.qtlib import getfont, geticon
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.filelistmodel import HgFileListModel
from tortoisehg.hgqt.filelistview import HgFileListView
from tortoisehg.hgqt.fileview import HgFileView
from tortoisehg.hgqt.revpanel import RevPanelWidget
from tortoisehg.hgqt.revmessage import RevMessage
from tortoisehg.hgqt import thgrepo, qscilib

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class RevDetailsWidget(QWidget):

    showMessage = pyqtSignal(str)
    revisionLinkClicked = pyqtSignal(str)

    def __init__(self, repo):
        QWidget.__init__(self)

        self.repo = repo
        self.splitternames = []

        # these are used to know where to go after a reload
        self._last_rev = None
        self._reload_file = None

        self.setupUi()
        self.createActions()
        self.setupModels()

        self.fileview.setFont(getfont('fontlog').font())
        self.fileview.showMessage.connect(self.showMessage)
        self.restoreSettings()

    def setRepo(self, repo):
        self.repo = repo

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
        # |  + diffToolbar            |  + revpanel                         |
        # +---------------------------+-------------------------------------+
        # |  + filelist               |  + message_splitter                 |
        # |                           |  :+ message                         |
        # |                           |  :----------------------------------+
        # |                           |   + fileview                        |
        # +---------------------------+-------------------------------------+
        # |+ searchbar                                                      |
        # +-----------------------------------------------------------------+

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

        self.diffToolbar = QToolBar(_('Diff Toolbar'))
        self.diffToolbar.setIconSize(QSize(16,16))
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
        vbox.addWidget(self.diffToolbar)
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
        self.message = RevMessage(self.message_splitter)
        self.message.revisionLinkClicked.connect(self.revisionLinkClicked_)

        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(2)
        sp.setHeightForWidth(self.message.sizePolicy().hasHeightForWidth())
        self.message.setSizePolicy(sp)
        self.message.setMinimumSize(QSize(0, 0))
        self.message.setFont(getfont('fontcomment').font())

        self.fileview = HgFileView(self.message_splitter)
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(5)
        sp.setHeightForWidth(self.fileview.sizePolicy().hasHeightForWidth())
        self.fileview.setSizePolicy(sp)
        self.fileview.setMinimumSize(QSize(0, 0))

        self.revpanel = RevPanelWidget(self.repo)
        self.revpanel.revisionLinkClicked.connect(self.revisionLinkClicked)

        cset_and_file_details_layout.addWidget(self.revpanel)
        cset_and_file_details_layout.addWidget(self.message_splitter)

        revisiondetails_layout.addWidget(self.filelist_splitter)

        self.searchbar = qscilib.SearchToolBar(hidable=True)
        self.searchbar.hide()
        self.searchbar.searchRequested.connect(self.fileview.find)
        self.searchbar.conditionChanged.connect(self.fileview.highlightText)
        revisiondetails_layout.addWidget(self.searchbar)
        self.fileview.filled.connect(self._updateHighlightText)

    def revisionLinkClicked_(self, rev):
        self.revisionLinkClicked.emit(rev)

    def createActions(self):
        self.actionDiffMode = QAction('Diff mode', self)
        self.actionDiffMode.setCheckable(True)
        self.actionDiffMode.toggled.connect(self.setMode)

        self.actionAnnMode = QAction('Annotate', self)
        self.actionAnnMode.setCheckable(True)
        self.actionAnnMode.toggled.connect(self.setAnnotate)

        # Next/Prev diff (in full file mode)
        self.actionNextDiff = QAction(geticon('down'), 'Next diff', self)
        self.actionNextDiff.setShortcut('Alt+Down')
        self.actionNextDiff.triggered.connect(self.nextDiff)
        def filled():
            self.actionNextDiff.setEnabled(
                self.fileview.fileMode() and self.fileview.nDiffs())
        self.fileview.filled.connect(filled)

        self.actionPrevDiff = QAction(geticon('up'), 'Previous diff', self)
        self.actionPrevDiff.setShortcut('Alt+Up')
        self.actionPrevDiff.triggered.connect(self.prevDiff)
        self.actionDiffMode.setChecked(True)

        # navigate in file viewer
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

        # Activate file (file diff navigator)
        self.actionActivateFile = QAction('Activate file', self)
        self.actionActivateFileAlt = QAction('Activate alt. file', self)
        self.actionActivateFileAlt.setShortcuts([Qt.ALT+Qt.Key_Return,
                                                 Qt.ALT+Qt.Key_Enter])
        self.actionActivateFileAlt.triggered.connect(
                lambda self=self:
                self.filelist.fileActivated(self.filelist.currentIndex(),
                                                      alternate=True))
        # toolbar
        tb = self.diffToolbar
        tb.addAction(self.actionDiffMode)
        tb.addAction(self.actionNextDiff)
        tb.addAction(self.actionPrevDiff)
        tb.addSeparator()
        tb.addAction(self.actionAnnMode)

    def setMode(self, mode):
        self.fileview.setMode(mode)
        if mode:
            self.actionAnnMode.setEnabled(False)
            self.actionAnnMode.setChecked(False)
            self.actionNextDiff.setEnabled(False)
            self.actionPrevDiff.setEnabled(False)
        else:
            self.actionAnnMode.setEnabled(True)
            # next/prev actions are enabled via signals

    def getMode(self):
        return self.fileview.getMode()

    def setAnnotate(self, ann):
        self.fileview.setAnnotate(ann)

    def getAnnotate(self):
        return self.fileview.getAnnotate()

    @pyqtSlot()
    def showSearchBar(self):
        self.searchbar.show()
        self.searchbar.setFocus()

    @pyqtSlot()
    def _updateHighlightText(self):
        if not self.searchbar.isVisible():
            return
        self.fileview.highlightText(self.searchbar.pattern(),
                                    self.searchbar.caseInsensitive())

    def nextDiff(self):
        notlast = self.fileview.nextDiff()
        filemode = self.fileview.fileMode()
        nDiffs = self.fileview.nDiffs()
        self.actionNextDiff.setEnabled(filemode and notlast and nDiffs)
        self.actionPrevDiff.setEnabled(filemode and nDiffs)

    def prevDiff(self):
        notfirst = self.fileview.prevDiff()
        filemode = self.fileview.fileMode()
        nDiffs = self.fileview.nDiffs()
        self.actionPrevDiff.setEnabled(filemode and notfirst and nDiffs)
        self.actionNextDiff.setEnabled(filemode and nDiffs)

    def create_models(self):
        self.filelistmodel = HgFileListModel(self.repo, parent=self)

    def setupModels(self):
        self.create_models()
        self.filelist.setModel(self.filelistmodel)
        self.filelist.fileRevSelected.connect(self._displayFile)
        self.filelist.clearDisplay.connect(self.fileview.clearDisplay)

    @pyqtSlot(object, object, object)
    def _displayFile(self, file, rev, status):
        self.fileview.displayFile(file, rev, status)
        self._updateHighlightText()

    def revision_selected(self, rev):
        self._last_rev = rev
        ctx = thgrepo.getcontext(self.repo, rev)
        self.revpanel.set_revision(rev)
        self.revpanel.update(repo = self.repo)
        self.message.displayRevision(ctx)
        if type(ctx.rev()) == str:
            self.actionDiffMode.setChecked(True)
            self.actionDiffMode.setEnabled(False)
        else:
            self.actionDiffMode.setEnabled(True)
        self.fileview.setContext(ctx)
        self.filelistmodel.setContext(ctx)

        mode = self.getMode()
        self.actionAnnMode.setEnabled(mode != 'diff')
        self.actionNextDiff.setEnabled(mode != 'diff')
        self.actionPrevDiff.setEnabled(mode != 'diff')

    def record(self):
        'Repo widget is reloading, record current file'
        self._reload_file = self.filelist.currentFile()

    def finishReload(self):
        'Finish reload by re-selecting previous file'
        if self._reload_file:
            self.filelist.selectFile(self._reload_file)
        elif not self.filelist.selectedIndexes():
            self.filelist.selectRow(0)

    def reload(self):
        'Task tab is reloaded, or repowidget is refreshed'
        if len(self.repo) <= self._last_rev:
            self._last_rev = '.'
        f = self.filelist.currentFile()
        self.revision_selected(self._last_rev)
        self.filelist.selectFile(f)

    def storeSettings(self):
        s = QSettings()
        wb = "RevDetailsWidget/"
        for n in self.splitternames:
            s.setValue(wb + n, getattr(self, n).saveState())
        s.setValue(wb + 'revpanel.expanded', self.revpanel.is_expanded())

    def restoreSettings(self):
        s = QSettings()
        wb = "RevDetailsWidget/"
        for n in self.splitternames:
            getattr(self, n).restoreState(s.value(wb + n).toByteArray())
        expanded = s.value(wb + 'revpanel.expanded', False).toBool()
        self.revpanel.set_expanded(expanded)
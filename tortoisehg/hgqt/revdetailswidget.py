# -*- coding: iso-8859-1 -*-
#!/usr/bin/env python
# repowidget.py - TortoiseHg repository widget
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
# Copyright (C) 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

from mercurial import hg

from tortoisehg.hgqt import qtlib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.filelistmodel import HgFileListModel
from tortoisehg.hgqt.filelistview import HgFileListView
from tortoisehg.hgqt.fileview import HgFileView
from tortoisehg.hgqt.revpanelwidget import RevPanelWidget
from tortoisehg.hgqt.revmessage import RevMessage

from PyQt4.QtCore import *
from PyQt4.QtGui import *

connect = QObject.connect


class RevDetailsWidget(QWidget):

    showMessageSignal = pyqtSignal(str)
    revisionLinkClicked = pyqtSignal(str)

    def __init__(self, repo, repoview):
        self.repo = repo
        self.repoview = repoview

        # these are used to know where to go after a reload
        self._reload_file = None

        self.splitternames = []

        QWidget.__init__(self)
        
        self.load_config()

        self.setupUi()
        self.disab_shortcuts = []

        self.currentMessage = ''

        self.createActions()

        self.fileview.setFont(self._font)
        connect(self.fileview, SIGNAL('showMessage'), self.showMessage)
        connect(self.fileview, SIGNAL('fileDisplayed'), self.file_displayed)

        self.restoreSettings()

    def setupUi(self):
        SP = QSizePolicy

        self.hbox = QHBoxLayout(self)
        self.hbox.setSpacing(0)
        self.hbox.setMargin(0)

        self.setupRevisionDetailsWidget()

        self.hbox.addWidget(self.revisionDetailsWidget)

    def setupRevisionDetailsWidget(self):
        SP = QSizePolicy

        self.revisionDetailsWidget = QFrame()
        sp = SP(SP.Preferred, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.revisionDetailsWidget.sizePolicy().hasHeightForWidth())
        self.revisionDetailsWidget.setSizePolicy(sp)
        self.revisionDetailsWidget.setFrameShape(QFrame.NoFrame)
        self.revisionDetailsWidget.setFrameShadow(QFrame.Plain)

        revisiondetails_layout = QVBoxLayout(self.revisionDetailsWidget)
        revisiondetails_layout.setSpacing(0)
        revisiondetails_layout.setMargin(0)

        self.filelist_splitter = QSplitter(self.revisionDetailsWidget)
        self.splitternames.append('filelist_splitter')

        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.filelist_splitter.sizePolicy().hasHeightForWidth())
        self.filelist_splitter.setSizePolicy(sp)
        self.filelist_splitter.setOrientation(Qt.Horizontal)
        self.filelist_splitter.setChildrenCollapsible(False)

        self.tableView_filelist = HgFileListView(self.filelist_splitter)

        self.cset_and_file_details_frame = QFrame(self.filelist_splitter)
        sp = SP(SP.Preferred, SP.Preferred)
        sp.setHorizontalStretch(1)
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
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.message.sizePolicy().hasHeightForWidth())
        self.message.setSizePolicy(sp)
        self.message.setMinimumSize(QSize(0, 0))
        font = QFont()
        font.setFamily("Courier")
        font.setPointSize(9)
        self.message.setFont(font)

        self.fileview = HgFileView(self.message_splitter)
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(1)
        sp.setHeightForWidth(self.fileview.sizePolicy().hasHeightForWidth())
        self.fileview.setSizePolicy(sp)
        self.fileview.setMinimumSize(QSize(0, 0))

        self.revpanel = RevPanelWidget(self.repo, self.repoview)

        cset_and_file_details_layout.addWidget(self.revpanel)
        cset_and_file_details_layout.addWidget(self.message_splitter)

        revisiondetails_layout.addWidget(self.filelist_splitter)

    def load_config(self):
        self._font = qtlib.getfont(self.repo.ui, 'fontlog').font()
        self.rowheight = 8
        self.users, self.aliases = [], []

    def revisionLinkClicked_(self, rev):
        self.revisionLinkClicked.emit(rev)

    def showMessage(self, msg):
        self.currentMessage = msg
        if self.isVisible():
            self.showMessageSignal.emit(msg)

    def showEvent(self, event):
        QWidget.showEvent(self, event)
        self.showMessageSignal.emit(self.currentMessage)

    def createActions(self):
        # navigate in file viewer
        self.actionNextLine = QAction('Next line', self)
        self.actionNextLine.setShortcut(Qt.SHIFT + Qt.Key_Down)
        connect(self.actionNextLine, SIGNAL('triggered()'),
                self.fileview.nextLine)
        self.addAction(self.actionNextLine)
        self.actionPrevLine = QAction('Prev line', self)
        self.actionPrevLine.setShortcut(Qt.SHIFT + Qt.Key_Up)
        connect(self.actionPrevLine, SIGNAL('triggered()'),
                self.fileview.prevLine)
        self.addAction(self.actionPrevLine)
        self.actionNextCol = QAction('Next column', self)
        self.actionNextCol.setShortcut(Qt.SHIFT + Qt.Key_Right)
        connect(self.actionNextCol, SIGNAL('triggered()'),
                self.fileview.nextCol)
        self.addAction(self.actionNextCol)
        self.actionPrevCol = QAction('Prev column', self)
        self.actionPrevCol.setShortcut(Qt.SHIFT + Qt.Key_Left)
        connect(self.actionPrevCol, SIGNAL('triggered()'),
                self.fileview.prevCol)
        self.addAction(self.actionPrevCol)

        # Activate file (file diff navigator)
        self.actionActivateFile = QAction('Activate file', self)

        self.actionActivateFileAlt = QAction('Activate alt. file', self)
        self.actionActivateFileAlt.setShortcuts([Qt.ALT+Qt.Key_Return, Qt.ALT+Qt.Key_Enter])
        connect(self.actionActivateFileAlt, SIGNAL('triggered()'),
                lambda self=self:
                self.tableView_filelist.fileActivated(self.tableView_filelist.currentIndex(),
                                                      alternate=True))

    def setMode(self, mode):
        self.fileview.setMode(mode)

    def getMode(self):
        return self.fileview.getMode()

    def setAnnotate(self, ann):
        self.fileview.setAnnotate(ann)

    def getAnnotate(self):
        return self.fileview.getAnnotate()

    def nextDiff(self):
        notlast = self.fileview.nextDiff()
        self.actionNextDiff.setEnabled(self.fileview.fileMode() and notlast and self.fileview.nDiffs())
        self.actionPrevDiff.setEnabled(self.fileview.fileMode() and self.fileview.nDiffs())

    def prevDiff(self):
        notfirst = self.fileview.prevDiff()
        self.actionPrevDiff.setEnabled(self.fileview.fileMode() and notfirst and self.fileview.nDiffs())
        self.actionNextDiff.setEnabled(self.fileview.fileMode() and self.fileview.nDiffs())

    def create_models(self):
        self.filelistmodel = HgFileListModel(self.repo)

    def setupModels(self, repomodel):
        self.repomodel = repomodel
        self.create_models()
        self.tableView_filelist.setModel(self.filelistmodel)
        self.fileview.setModel(repomodel)
        filetable = self.tableView_filelist
        connect(filetable, SIGNAL('fileSelected'), self.fileview.displayFile)

    def on_filled(self):
        self.tableView_filelist.selectFile(self._reload_file)

    def file_displayed(self, filename):
        #self.actionPrevDiff.setEnabled(False)
        pass

    def revision_selected(self, rev):
        ctx = self.repo[rev]
        if len(self.filelistmodel):
            self.tableView_filelist.selectRow(0)
        if ctx.rev() is not None:
            self.fileview.setContext(ctx)
            self.revpanel.update(ctx.rev())
            self.message.displayRevision(ctx)
            self.filelistmodel.setSelectedRev(ctx)

    def reload(self, rev=None):
        self._reload_file = self.tableView_filelist.currentFile()
        self.repo = hg.repository(self.repo.ui, self.repo.root)
        self.setupModels(self.repomodel)

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
        expanded = s.value(wb + 'revpanel.expanded', True).toBool()
        self.revpanel.set_expanded(expanded)

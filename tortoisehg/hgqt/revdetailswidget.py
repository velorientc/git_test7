# -*- coding: iso-8859-1 -*-
#!/usr/bin/env python
# repowidget.py - TortoiseHg repository widget
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
# Copyright (C) 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

from PyQt4 import QtCore, QtGui

from mercurial import hg

from tortoisehg.hgqt.i18n import _

from tortoisehg.hgqt.config import HgConfig
from tortoisehg.hgqt.filelistmodel import HgFileListModel

from filelistview import HgFileListView
from fileview import HgFileView
from revpanelwidget import RevPanelWidget
from revdisplay import RevMessage

Qt = QtCore.Qt
connect = QtCore.QObject.connect
SIGNAL = QtCore.SIGNAL


class RevDetailsWidget(QtGui.QWidget):

    showMessageSignal = QtCore.pyqtSignal(str)

    def __init__(self, repo, repoview):
        self.repo = repo
        self.repoview = repoview

        # these are used to know where to go after a reload
        self._reload_file = None

        self.splitternames = []

        QtGui.QWidget.__init__(self)
        
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
        SP = QtGui.QSizePolicy

        self.hbox = QtGui.QHBoxLayout(self)
        self.hbox.setSpacing(0)
        self.hbox.setMargin(0)

        self.setupRevisionDetailsWidget()

        self.hbox.addWidget(self.revisionDetailsWidget)

    def setupRevisionDetailsWidget(self):
        SP = QtGui.QSizePolicy

        self.revisionDetailsWidget = QtGui.QFrame()
        sp = SP(SP.Preferred, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.revisionDetailsWidget.sizePolicy().hasHeightForWidth())
        self.revisionDetailsWidget.setSizePolicy(sp)
        self.revisionDetailsWidget.setFrameShape(QtGui.QFrame.NoFrame)
        self.revisionDetailsWidget.setFrameShadow(QtGui.QFrame.Plain)

        revisiondetails_layout = QtGui.QVBoxLayout(self.revisionDetailsWidget)
        revisiondetails_layout.setSpacing(0)
        revisiondetails_layout.setMargin(0)

        self.filelist_splitter = QtGui.QSplitter(self.revisionDetailsWidget)
        self.splitternames.append('filelist_splitter')

        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.filelist_splitter.sizePolicy().hasHeightForWidth())
        self.filelist_splitter.setSizePolicy(sp)
        self.filelist_splitter.setOrientation(QtCore.Qt.Horizontal)
        self.filelist_splitter.setChildrenCollapsible(False)

        self.tableView_filelist = HgFileListView(self.filelist_splitter)

        self.cset_and_file_details_frame = QtGui.QFrame(self.filelist_splitter)
        sp = SP(SP.Preferred, SP.Preferred)
        sp.setHorizontalStretch(1)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(
            self.cset_and_file_details_frame.sizePolicy().hasHeightForWidth())
        self.cset_and_file_details_frame.setSizePolicy(sp)
        self.cset_and_file_details_frame.setFrameShape(QtGui.QFrame.NoFrame)

        vbox = QtGui.QVBoxLayout(self.cset_and_file_details_frame)
        vbox.setSpacing(0)
        vbox.setSizeConstraint(QtGui.QLayout.SetDefaultConstraint)
        vbox.setMargin(0)
        cset_and_file_details_layout = vbox

        self.message_splitter = QtGui.QSplitter(self.cset_and_file_details_frame)
        self.splitternames.append('message_splitter')
        sp = SP(SP.Preferred, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.message_splitter.sizePolicy().hasHeightForWidth())
        self.message_splitter.setSizePolicy(sp)
        self.message_splitter.setMinimumSize(QtCore.QSize(50, 50))
        self.message_splitter.setFrameShape(QtGui.QFrame.NoFrame)
        self.message_splitter.setLineWidth(0)
        self.message_splitter.setMidLineWidth(0)
        self.message_splitter.setOrientation(Qt.Vertical)
        self.message_splitter.setOpaqueResize(True)
        self.message = RevMessage(self.message_splitter)

        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.message.sizePolicy().hasHeightForWidth())
        self.message.setSizePolicy(sp)
        self.message.setMinimumSize(QtCore.QSize(0, 0))
        font = QtGui.QFont()
        font.setFamily("Courier")
        font.setPointSize(9)
        self.message.setFont(font)

        self.fileview = HgFileView(self.message_splitter)
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(1)
        sp.setHeightForWidth(self.fileview.sizePolicy().hasHeightForWidth())
        self.fileview.setSizePolicy(sp)
        self.fileview.setMinimumSize(QtCore.QSize(0, 0))

        self.revpanel = RevPanelWidget(self.repo, self.repoview)

        cset_and_file_details_layout.addWidget(self.revpanel)
        cset_and_file_details_layout.addWidget(self.message_splitter)

        revisiondetails_layout.addWidget(self.filelist_splitter)

    def load_config(self):
        cfg = HgConfig(self.repo.ui)
        fontstr = cfg.getFont()
        font = QtGui.QFont()
        try:
            if not font.fromString(fontstr):
                raise Exception
        except:
            print "bad font name '%s'" % fontstr
            font.setFamily("Monospace")
            font.setFixedPitch(True)
            font.setPointSize(10)
        self._font = font

        self.rowheight = cfg.getRowHeight()
        self.users, self.aliases = cfg.getUsers()
        self.hidefinddelay = cfg.getHideFindDelay()
        return cfg

    def showMessage(self, msg):
        self.currentMessage = msg
        if self.isVisible():
            self.showMessageSignal.emit(msg)

    def showEvent(self, event):
        QtGui.QWidget.showEvent(self, event)
        self.showMessageSignal.emit(self.currentMessage)

    def createActions(self):
        # navigate in file viewer
        self.actionNextLine = QtGui.QAction('Next line', self)
        self.actionNextLine.setShortcut(Qt.SHIFT + Qt.Key_Down)
        connect(self.actionNextLine, SIGNAL('triggered()'),
                self.fileview.nextLine)
        self.addAction(self.actionNextLine)
        self.actionPrevLine = QtGui.QAction('Prev line', self)
        self.actionPrevLine.setShortcut(Qt.SHIFT + Qt.Key_Up)
        connect(self.actionPrevLine, SIGNAL('triggered()'),
                self.fileview.prevLine)
        self.addAction(self.actionPrevLine)
        self.actionNextCol = QtGui.QAction('Next column', self)
        self.actionNextCol.setShortcut(Qt.SHIFT + Qt.Key_Right)
        connect(self.actionNextCol, SIGNAL('triggered()'),
                self.fileview.nextCol)
        self.addAction(self.actionNextCol)
        self.actionPrevCol = QtGui.QAction('Prev column', self)
        self.actionPrevCol.setShortcut(Qt.SHIFT + Qt.Key_Left)
        connect(self.actionPrevCol, SIGNAL('triggered()'),
                self.fileview.prevCol)
        self.addAction(self.actionPrevCol)

        # Activate file (file diff navigator)
        self.actionActivateFile = QtGui.QAction('Activate file', self)

        self.actionActivateFileAlt = QtGui.QAction('Activate alt. file', self)
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
            self.message.displayRevision(ctx, None)
            self.filelistmodel.setSelectedRev(ctx)

    def reload(self, rev=None):
        self._reload_file = self.tableView_filelist.currentFile()
        self.repo = hg.repository(self.repo.ui, self.repo.root)
        self.setupModels(self.repomodel)

    def storeSettings(self):
        s = QtCore.QSettings()
        wb = "RevDetailsWidget/"
        for n in self.splitternames:
            s.setValue(wb + n, getattr(self, n).saveState())
        s.setValue(wb + 'revpanel.expanded', self.revpanel.is_expanded())

    def restoreSettings(self):
        s = QtCore.QSettings()
        wb = "RevDetailsWidget/"
        for n in self.splitternames:
            getattr(self, n).restoreState(s.value(wb + n).toByteArray())
        expanded = s.value(wb + 'revpanel.expanded', True).toBool()
        self.revpanel.set_expanded(expanded)

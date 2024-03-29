# revdetails.py - TortoiseHg revision details widget
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
# Copyright (C) 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

import os # for os.name

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.filelistmodel import HgFileListModel
from tortoisehg.hgqt.filelistview import HgFileListView
from tortoisehg.hgqt.fileview import HgFileView
from tortoisehg.hgqt.revpanel import RevPanelWidget
from tortoisehg.hgqt import filectxactions, qtlib, cmdui
from tortoisehg.util import hglib

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class RevDetailsWidget(QWidget, qtlib.TaskWidget):

    showMessage = pyqtSignal(QString)
    linkActivated = pyqtSignal(unicode)
    grepRequested = pyqtSignal(unicode, dict)
    revisionSelected = pyqtSignal(int)
    updateToRevision = pyqtSignal(int)
    runCustomCommandRequested = pyqtSignal(str, list)

    def __init__(self, repoagent, parent, rev=None):
        QWidget.__init__(self, parent)

        self._repoagent = repoagent
        repo = repoagent.rawRepo()
        # TODO: replace by repoagent if setRepo(bundlerepo) can be removed
        self.repo = repo
        self.ctx = repo[rev]
        self.splitternames = []

        self.setupUi()
        self.createActions()
        self.setupModels()

        self._deschtmlize = qtlib.descriptionhtmlizer(repo.ui)
        repoagent.configChanged.connect(self._updatedeschtmlizer)

    def setRepo(self, repo):
        self.repo = repo
        self.fileview.setRepo(repo)
        self.filelist.setRepo(repo)
        self._fileactions.setRepo(repo)

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
        self.filelist = HgFileListView(self.repo, self, True)
        self.filelist.setContextMenuPolicy(Qt.CustomContextMenu)
        self.filelist.customContextMenuRequested.connect(self.menuRequest)
        self.filelist.doubleClicked.connect(self.onDoubleClick)

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
        if os.name == 'nt':
            self.messagesplitter.setStyle(QStyleFactory.create('Plastique'))

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
        self.message.anchorClicked.connect(self._forwardAnchorClicked)

        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(2)
        sp.setHeightForWidth(self.message.sizePolicy().hasHeightForWidth())
        self.message.setSizePolicy(sp)
        self.message.setMinimumSize(QSize(0, 0))
        f = qtlib.getfont('fontcomment')
        self.message.setFont(f.font())
        f.changed.connect(self.forwardFont)

        self.fileview = HgFileView(self._repoagent, self.messagesplitter)
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(5)
        sp.setHeightForWidth(self.fileview.sizePolicy().hasHeightForWidth())
        self.fileview.setSizePolicy(sp)
        self.fileview.setMinimumSize(QSize(0, 0))
        self.fileview.linkActivated.connect(self.linkActivated)
        self.fileview.setFont(qtlib.getfont('fontdiff').font())
        self.fileview.showMessage.connect(self.showMessage)
        self.fileview.grepRequested.connect(self.grepRequested)
        self.fileview.revisionSelected.connect(self.revisionSelected)
        self.filelist.fileSelected.connect(self.fileview.displayFile)
        self.filelist.fileSelected.connect(self.updateItemFileActions)
        self.filelist.clearDisplay.connect(self.fileview.clearDisplay)

        self.revpanel = RevPanelWidget(self.repo)
        self.revpanel.linkActivated.connect(self.linkActivated)

        panelframevbox.addWidget(self.revpanel)
        panelframevbox.addSpacing(5)
        panelframevbox.addWidget(self.messagesplitter)

    def forwardFont(self, font):
        self.message.setFont(font)

    def setupModels(self):
        self.filelistmodel = model = HgFileListModel(self)
        self.filelistmodel.showMessage.connect(self.showMessage)
        self.filelist.setModel(model)
        self.actionShowAllMerge.toggled.connect(model.toggleFullFileList)

        # Because filelist.fileSelected, i.e. currentRowChanged, is emitted
        # *before* selection changed, we cannot rely only on fileSelected.
        # On fileSelected, getSelectedFiles() happens to return the previous
        # selection, even though currentFile() works as expected.
        self.filelist.selectionModel().selectionChanged.connect(
            self.updateItemFileActions)

    def createActions(self):
        self.actionUpdate = a = self.filelisttbar.addAction(
            qtlib.geticon('hg-update'), _('Update to this revision'))
        a.triggered.connect(self._emitUpdateToRevision)
        self.filelisttbar.addSeparator()
        self.actionShowAllMerge = QAction(_('Show All'), self)
        self.actionShowAllMerge.setToolTip(
            _('Toggle display of all files and the direction they were merged'))
        self.actionShowAllMerge.setCheckable(True)
        self.actionShowAllMerge.setChecked(False)
        self.actionShowAllMerge.setEnabled(False)
        self.filelisttbar.addAction(self.actionShowAllMerge)

        le = QLineEdit()
        if hasattr(le, 'setPlaceholderText'): # Qt >= 4.7
            le.setPlaceholderText(_('### filter text ###'))
        self.filefilter = le
        self.filelisttbar.addWidget(self.filefilter)
        self.filefilter.textEdited.connect(self.setFilter)

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

        self._fileactions = filectxactions.FilectxActions(self.repo, self,
                                                          rev=self.ctx.rev())
        self._fileactions.linkActivated.connect(self.linkActivated)
        self._fileactions.runCustomCommandRequested.connect(
            self.runCustomCommandRequested)
        self.addActions(self._fileactions.actions())

    def onRevisionSelected(self, rev):
        'called by repowidget when repoview changes revisions'
        self.ctx = ctx = self.repo.changectx(rev)
        self.revpanel.set_revision(rev)
        self.revpanel.update(repo = self.repo)
        msg = ctx.description()
        inlinetags = self.repo.ui.configbool('tortoisehg', 'issue.inlinetags')
        if ctx.tags() and inlinetags:
            msg = ' '.join(['[%s]' % tag for tag in ctx.tags()]) + ' ' + msg
        # don't use <pre>...</pre>, which also changes font family
        self.message.setHtml('<div style="white-space: pre;">%s</div>'
                             % self._deschtmlize(msg))
        self._fileactions.setRev(rev)
        self.actionShowAllMerge.setEnabled(len(ctx.parents()) == 2)
        self.fileview.setContext(ctx)
        self.filelist.setContext(ctx)
        self.setFilter(self.filefilter.text())

    @pyqtSlot()
    def _updatedeschtmlizer(self):
        self._deschtmlize = qtlib.descriptionhtmlizer(self.repo.ui)
        self.onRevisionSelected(self.ctx.rev())  # regenerate desc html

    def reload(self):
        'Task tab is reloaded, or repowidget is refreshed'
        rev = self.ctx.rev()
        if (type(self.ctx.rev()) is int and len(self.repo) <= self.ctx.rev()
            or (rev is not None  # wctxrev in repo raises TypeError
                and rev not in self.repo
                and rev not in self.repo.thgmqunappliedpatches)):
            rev = 'tip'
        self.onRevisionSelected(rev)

    @pyqtSlot(QUrl)
    def _forwardAnchorClicked(self, url):
        self.linkActivated.emit(url.toString())

    @pyqtSlot()
    def _emitUpdateToRevision(self):
        self.updateToRevision.emit(self.ctx.rev())

    #@pyqtSlot(QModelIndex)
    def onDoubleClick(self, index):
        model = self.filelist.model()
        itemstatus = model.dataFromIndex(index)['status']
        itemissubrepo = (itemstatus == 'S')
        if itemissubrepo:
            self._fileactions.opensubrepo()
        elif itemstatus == 'C':
            self._fileactions.editfile()
        else:
            self._fileactions.vdiff()

    @pyqtSlot(QPoint)
    def menuRequest(self, point):
        index = self.filelist.currentIndex()
        if not index.isValid():
            return
        model = self.filelist.model()
        data = model.dataFromIndex(index)
        if not data:
            return
        contextmenu = self._fileactions.menu()
        if contextmenu:
            contextmenu.exec_(self.filelist.viewport().mapToGlobal(point))

    @pyqtSlot()
    def updateItemFileActions(self):
        index = self.filelist.currentIndex()
        model = self.filelist.model()
        data = model.dataFromIndex(index)
        if not data:
            return
        itemissubrepo = (data['status'] == 'S')
        self._fileactions.setPaths_(self.filelist.getSelectedFiles(),
                                    self.filelist.currentFile(),
                                    itemissubrepo)

    @pyqtSlot(QString)
    def setFilter(self, match):
        model = self.filelist.model()
        if model is not None:
            model.setFilter(match)
            self.filelist.enablefilterpalette(bool(match))

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


class RevDetailsDialog(QDialog):
    'Standalone revision details tool, a wrapper for RevDetailsWidget'

    def __init__(self, repoagent, rev='.', parent=None):
        QDialog.__init__(self, parent)
        self.setWindowFlags(Qt.Window)
        self.setWindowIcon(qtlib.geticon('hg-log'))

        layout = QVBoxLayout()
        layout.setMargin(0)
        self.setLayout(layout)

        toplayout = QVBoxLayout()
        toplayout.setContentsMargins(5, 5, 5, 0)
        layout.addLayout(toplayout)

        revdetails = RevDetailsWidget(repoagent, parent, rev=rev)
        toplayout.addWidget(revdetails, 1)

        self.statusbar = cmdui.ThgStatusBar(self)
        revdetails.showMessage.connect(self.statusbar.showMessage)
        revdetails.linkActivated.connect(self.linkActivated)

        layout.addWidget(self.statusbar)

        s = QSettings()
        self.restoreGeometry(s.value('revdetails/geom').toByteArray())
        revdetails.loadSettings(s)
        repoagent.repositoryChanged.connect(self.refresh)

        self.revdetails = revdetails
        self.setRev(rev)
        qtlib.newshortcutsforstdkey(QKeySequence.Refresh, self, self.refresh)

    def setRev(self, rev):
        self.revdetails.onRevisionSelected(rev)
        self.refresh()

    def linkActivated(self, link):
        link = hglib.fromunicode(link)
        link = link.split(':', 1)
        if len(link) == 1:
            linktype = 'cset:'
            linktarget = link[0]
        else:
            linktype = link[0]
            linktarget = link[1]

        if linktype == 'cset':
            self.setRev(linktarget)
        elif linktype == 'repo':
            try:
                linkpath, rev = linktarget.split('?', 1)
            except ValueError:
                linkpath = linktarget
                rev = None
            # TODO: implement by using signal-slot if possible
            from tortoisehg.hgqt import run
            run.qtrun.showRepoInWorkbench(hglib.tounicode(linkpath), rev)

    @pyqtSlot()
    def refresh(self):
        rev = revnum = self.revdetails.ctx.rev()
        if rev is None:
            revstr = _('Working Directory')
        else:
            hash = self.revdetails.ctx.hex()[:12]
            revstr = '@%s: %s' % (str(revnum), hash)
        self.setWindowTitle(_('%s - Revision Details (%s)')
                            % (self.revdetails.repo.displayname, revstr))
        self.revdetails.reload()

    def done(self, ret):
        s = QSettings()
        s.setValue('revdetails/geom', self.saveGeometry())
        super(RevDetailsDialog, self).done(ret)

# -*- coding: iso-8859-1 -*-
#!/usr/bin/env python
# workbench.py - main TortoiseHg Window
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.
"""
Main Qt4 application for TortoiseHg
"""

import os
import subprocess

from mercurial.error import RepoError

from tortoisehg.util import paths, hglib

#from tortoisehg.hgqt.decorators import timeit

from tortoisehg.hgqt import repomodel, thgrepo, cmdui
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.qtlib import geticon, getfont, InfoMsgBox
from tortoisehg.hgqt.repowidget import RepoWidget
from tortoisehg.hgqt.reporegistry import RepoRegistryView
from tortoisehg.hgqt.logcolumns import ColumnSelectDialog
from tortoisehg.hgqt.docklog import LogDockWidget
from tortoisehg.hgqt.settings import SettingsDialog

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class Workbench(QMainWindow):
    """hg repository viewer/browser application"""
    finished = pyqtSignal(int)

    def __init__(self, ui, repo=None):
        self.ui = ui

        self._reload_rev = None
        self._reload_file = None

        self._loading = True
        self._scanForRepoChanges = True
        self._searchWidgets = []

        QMainWindow.__init__(self)

        self.load_config(ui)
        self.setupUi()

        self.setWindowTitle('TortoiseHg Workbench')

        self.reporegistry = rr = RepoRegistryView(ui, self)
        rr.setObjectName('RepoRegistryView')
        self.addDockWidget(Qt.LeftDockWidgetArea, rr)

        self.log = LogDockWidget(self)
        self.log.setObjectName('Log')
        self.log.progressReceived.connect(self.statusbar.progress)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log)

        rr.openRepoSignal.connect(self.openRepo)

        self.createActions()
        self.createToolbars()

        self.repoTabChanged()

        def gotVisible(state):
            self.actionShowRepoRegistry.setChecked(self.reporegistry.isVisible())
        def logVisible(state):
            self.actionShowLog.setChecked(self.log.isVisible())

        self.reporegistry.visibilityChanged.connect(gotVisible)
        self.log.visibilityChanged.connect(logVisible)

        self.restoreSettings()
        self.setAcceptDrops(True)

        if repo:
            self.addRepoTab(repo)
        else:
            self.reporegistry.setVisible(True)

    def load_config(self, ui):
        # TODO: connect to font changed signal
        self._font = getfont('fontlog').font()
        self.rowheight = 8
        self.users, self.aliases = [], []

    def accept(self):
        self.close()

    def reject(self):
        self.close()

    def setupUi(self):
        desktopgeom = qApp.desktop().availableGeometry()
        self.resize(desktopgeom.size() * 0.8)

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icons/log.svg"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        self.centralwidget = QWidget(self)

        self.verticalLayout = vl = QVBoxLayout(self.centralwidget)
        vl.setSpacing(0)
        vl.setMargin(0)

        self.repoTabsWidget = tw = QTabWidget()
        tw.setDocumentMode(True)
        tw.setTabsClosable(True)
        tw.setMovable(True)
        sp = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sp.setHorizontalStretch(1)
        sp.setVerticalStretch(1)
        sp.setHeightForWidth(tw.sizePolicy().hasHeightForWidth())
        tw.setSizePolicy(sp)
        tw.tabCloseRequested.connect(self.repoTabCloseRequested)
        tw.currentChanged.connect(self.repoTabChanged)
        vl.addWidget(tw)

        self.setCentralWidget(self.centralwidget)
        self.statusbar = cmdui.ThgStatusBar(self)
        self.setStatusBar(self.statusbar)

        self.filterToolbar = tb = QToolBar(_("Filter Toolbar"), self)
        tb.setEnabled(True)
        tb.setObjectName("filterToolbar")
        self.addToolBar(Qt.ToolBarArea(Qt.TopToolBarArea), tb)

        self.actionHelp = a = QAction(_("Help"), self)
        a.setShortcut(QKeySequence.HelpContents)
        a.setIcon(geticon('help'))

        self.actionNew_repository = a = QAction(_("&New Repository..."), self)
        a.setShortcut(QKeySequence.New)
        
        self.actionClone_repository = a = QAction(_("Clone Repository..."), self)
        b = QKeySequence.keyBindings(QKeySequence.New)
        a.setShortcut(QKeySequence.fromString(u'Shift+' + b[0].toString()))

        self.actionOpen_repository = a = QAction(_("&Open Repository..."), self)
        a.setShortcut(QKeySequence.Open)

        self.actionClose_repository = a = QAction(_("&Close Repository"), self)
        a.setShortcut(QKeySequence.Close)

        self.actionSettings = a = QAction(_('&Settings...'), self)
        a.setShortcut(QKeySequence.Preferences)
        a.setIcon(geticon('settings_user'))

        self.actionRefresh = a = QAction(_("&Refresh"), self)
        a.setIcon(geticon('reload'))
        a.setShortcut(QKeySequence.Refresh)
        a.setToolTip(_('Refresh all for current repository'))

        self.actionRefreshTaskTab = a = QAction(_("Refresh &Task Tab"), self)
        a.setIcon(geticon('reloadtt'))
        b = QKeySequence.keyBindings(QKeySequence.Refresh)
        a.setShortcut(QKeySequence.fromString(u'Shift+' + b[0].toString()))
        a.setToolTip(_('Refresh only the current task tab'))

        self.actionFind = a = QAction(_('Find'), self)
        a.setIcon(geticon('find'))

        self.actionQuit = a = QAction(_("E&xit"), self)
        a.setIcon(geticon('quit'))
        a.setShortcut(QKeySequence.Quit)
        a.setIconText(_("Exit"))
        a.setToolTip(_("Exit"))

        self.actionAbout = QAction(_("About"), self)
        self.actionDisplayAllBranches = QAction("displayAllBranches", self)

        self.actionBack = a = QAction(_("Back"), self)
        a.setEnabled(False)
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icons/back.svg"), QIcon.Normal, QIcon.Off)
        a.setIcon(icon)

        self.actionForward = a = QAction(_("Forward"), self)
        a.setEnabled(False)
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icons/forward.svg"), QIcon.Normal, QIcon.Off)
        a.setIcon(icon)

        self.actionLoadAll = a = QAction(_("Load all"), self)
        a.setEnabled(True)
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icons/loadall.png"), QIcon.Normal, QIcon.Off)
        a.setIcon(icon)

        self.actionShowPaths = a = QAction(_("Show Paths"), self)
        a.setCheckable(True)

        self.actionSelectColumns = QAction(_("Choose Log Columns..."), self)

        self.actionGroupTaskView = ag = QActionGroup(self)
        ag.setEnabled(False)
        self.actionSelectTaskLog = a = QAction(_("Revision &Details"), ag)
        a.setIcon(geticon('log'))
        self.actionSelectTaskCommit = a = QAction(_("&Commit..."), ag)
        a.setIcon(geticon('commit'))
        self.actionSelectTaskManifest = a = QAction(_("&Manifest..."), ag)
        a.setIcon(geticon('annotate'))
        self.actionSelectTaskGrep = a = QAction(_("&Search..."), ag)
        a.setIcon(geticon('repobrowse'))
        self.actionSelectTaskSync = a = QAction(_("S&ynchronize..."), ag)
        a.setIcon(geticon('sync'))
        for a in ag.actions():
            a.setCheckable(True)

        self.actionShowRepoRegistry = a = QAction(_("Show Repository Registry"), self)
        a.setCheckable(True)
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icons/repotree.svg"), QIcon.Normal, QIcon.Off)
        a.setIcon(icon)

        self.actionShowLog = a = QAction(_("Show Output &Log"), self)
        a.setCheckable(True)
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icons/showlog.png"), QIcon.Normal, QIcon.Off)
        a.setIcon(icon)
        a.setShortcut(QKeySequence("Ctrl+L"))

        self.actionServe = QAction(_("Web Server"), self)
        self.actionImport = QAction(_("Import"), self)
        self.actionVerify = QAction(_("Verify"), self)
        self.actionRecover = QAction(_("Recover"), self)
        self.actionRollback = QAction(_("Rollback/Undo"), self)
        self.actionPurge = QAction(_("Purge"), self)
        self.actionExplore = a = QAction(_("Explore"), self)
        a.setShortcut(QKeySequence("Shift+Ctrl+S"))
        self.actionTerminal = a = QAction(_("Terminal"), self)
        a.setShortcut(QKeySequence("Shift+Ctrl+T"))

        # TODO: Use long names when these have icons
        self.actionIncoming = a = QAction(_('In'), self)
        a.setToolTip(_('Check for incoming changes from default pull target'))
        a.setIcon(QIcon(":/icons/incoming.svg"))
        self.actionPull = a = QAction(_('Pull'), self)
        a.setToolTip(_('Pull incoming changes from default pull target'))
        a.setIcon(QIcon(":/icons/pull.svg"))
        self.actionOutgoing = a = QAction(_('Out'), self)
        a.setToolTip(_('Detect outgoing changes to default push target'))
        a.setIcon(QIcon(":/icons/outgoing.svg"))
        self.actionPush = a = QAction(_('Push'), self)
        a.setToolTip(_('Push outgoing changes to default push target'))
        a.setIcon(QIcon(":/icons/push.svg"))

        self.menubar = QMenuBar(self)
        self.setMenuBar(self.menubar)

        self.menuFile = m = QMenu(_("&File"), self.menubar)
        m.addAction(self.actionNew_repository)
        m.addAction(self.actionClone_repository)
        m.addAction(self.actionOpen_repository)
        m.addAction(self.actionClose_repository)
        m.addSeparator()
        m.addAction(self.actionSettings)
        m.addSeparator()
        m.addAction(self.actionQuit)

        self.menuView = m = QMenu(_("&View"), self.menubar)
        m.addAction(self.actionShowRepoRegistry)
        m.addAction(self.actionShowPaths)
        m.addAction(self.actionShowLog)
        m.addSeparator()
        m.addAction(self.actionSelectColumns)
        m.addSeparator()
        m.addActions(self.actionGroupTaskView.actions())
        m.addSeparator()
        m.addAction(self.actionRefresh)
        m.addAction(self.actionRefreshTaskTab)

        self.menuRepository = m = QMenu(_("&Repository"), self.menubar)
        m.addAction(self.actionServe)
        m.addSeparator()
        m.addAction(self.actionImport)
        m.addSeparator()
        m.addAction(self.actionVerify)
        m.addAction(self.actionRecover)
        m.addSeparator()
        m.addAction(self.actionRollback)
        m.addAction(self.actionPurge)
        m.addSeparator()
        m.addAction(self.actionExplore)
        m.addAction(self.actionTerminal)

        self.menuHelp = m = QMenu(_("&Help"), self.menubar)
        m.addAction(self.actionHelp)
        m.addAction(self.actionAbout)

        self.menubar.addAction(self.menuFile.menuAction())
        self.menubar.addAction(self.menuView.menuAction())
        self.menubar.addAction(self.menuRepository.menuAction())
        self.menubar.addAction(self.menuHelp.menuAction())
        
        self.updateMenu()

    def createToolbars(self):
        self.edittbar = tb = QToolBar(_("Edit Toolbar"), self)
        tb.setEnabled(True)
        tb.setObjectName("edittbar")
        tb.addAction(self.actionRefresh)
        tb.addAction(self.actionRefreshTaskTab)
        tb.addSeparator()
        tb.addAction(self.actionBack)
        tb.addAction(self.actionForward)
        tb.addAction(self.actionLoadAll)
        tb.addSeparator()
        tb.addAction(self.actionFind)
        self.addToolBar(Qt.ToolBarArea(Qt.TopToolBarArea), tb)

        self.docktbar = tb = QToolBar(_("Dock Toolbar"), self)
        tb.setEnabled(True)
        tb.setObjectName("docktbar")
        tb.addAction(self.actionShowRepoRegistry)
        tb.addAction(self.actionShowLog)
        self.addToolBar(Qt.ToolBarArea(Qt.TopToolBarArea), tb)

        self.synctbar = tb = QToolBar(_('Sync Toolbar'), self)
        tb.setEnabled(True)
        tb.setObjectName('synctbar')
        tb.addAction(self.actionIncoming)
        tb.addAction(self.actionPull)
        tb.addAction(self.actionOutgoing)
        tb.addAction(self.actionPush)
        self.addToolBar(Qt.ToolBarArea(Qt.TopToolBarArea), tb)

        # tree filters toolbar
        self.branchLabel = QToolButton()
        self.branchLabel.setText("Branch")
        self.branchLabel.setStatusTip("Display graph the named branch only")
        self.branchLabel.setPopupMode(QToolButton.InstantPopup)
        self.branch_menu = QMenu()
        cbranch_action = self.branch_menu.addAction("Display closed branches")
        cbranch_action.setCheckable(True)
        self.cbranch_action = cbranch_action
        allpar_action = self.branch_menu.addAction("Include all ancestors")
        allpar_action.setCheckable(True)
        self.allpar_action = allpar_action
        self.branchLabel.setMenu(self.branch_menu)
        self.branchCombo = QComboBox()
        self.branchCombo.activated.connect(self.setBranch)
        cbranch_action.toggled.connect(self.setupBranchCombo)
        allpar_action.toggled.connect(self.setBranch)

        self.filterToolbar.layout().setSpacing(3)

        self.branchLabelAction = self.filterToolbar.addWidget(self.branchLabel)
        self.branchComboAction = self.filterToolbar.addWidget(self.branchCombo)
        self.filterToolbar.addSeparator()

    def createActions(self):
        # main window actions (from .ui file)
        self.actionFind.triggered.connect(self.find)
        self.actionRefresh.triggered.connect(self.reload)
        self.actionRefreshTaskTab.triggered.connect(self.reloadTaskTab)
        self.actionAbout.triggered.connect(self.on_about)
        self.actionQuit.triggered.connect(self.close)
        self.actionBack.triggered.connect(self.back)
        self.actionForward.triggered.connect(self.forward)
        self.actionImport.triggered.connect(self.thgimport)
        self.actionLoadAll.triggered.connect(self.loadall)
        self.actionSelectColumns.triggered.connect(self.setHistoryColumns)
        self.actionSelectTaskLog.triggered.connect(self.showRepoTaskLog)
        self.actionSelectTaskCommit.triggered.connect(self.showRepoTaskCommit)
        self.actionSelectTaskManifest.triggered.connect(self.showRepoTaskManifest)
        self.actionSelectTaskGrep.triggered.connect(self.showRepoTaskGrep)
        self.actionSelectTaskSync.triggered.connect(self.showRepoTaskSync)
        self.actionShowPaths.toggled.connect(self.actionShowPathsToggled)
        self.actionShowRepoRegistry.toggled.connect(self.showRepoRegistry)
        self.actionShowLog.toggled.connect(self.showLog)

        self.actionNew_repository.triggered.connect(self.newRepository)
        self.actionClone_repository.triggered.connect(self.cloneRepository)
        self.actionOpen_repository.triggered.connect(self.openRepository)
        self.actionClose_repository.triggered.connect(self.closeRepository)
        self.actionSettings.triggered.connect(self.editSettings)

        self.actionServe.triggered.connect(self.serve)
        self.actionVerify.triggered.connect(self.verify)
        self.actionRecover.triggered.connect(self.recover)
        self.actionRollback.triggered.connect(self.rollback)
        self.actionPurge.triggered.connect(self.purge)
        self.actionExplore.triggered.connect(self.explore)
        self.actionTerminal.triggered.connect(self.terminal)

        self.actionIncoming.triggered.connect(self.incoming)
        self.actionPull.triggered.connect(self.pull)
        self.actionOutgoing.triggered.connect(self.outgoing)
        self.actionPush.triggered.connect(self.push)

        self.actionHelp.triggered.connect(self.on_help)

    def showRepoRegistry(self, show):
        self.reporegistry.setVisible(show)

    def showLog(self, show):
        self.log.setVisible(show)

    def showRepoTaskLog(self, show):
        rw = self.repoTabsWidget.currentWidget()
        if not rw: return
        rw.taskTabsWidget.setCurrentIndex(rw.logTabIndex)

    def showRepoTaskCommit(self, show):
        rw = self.repoTabsWidget.currentWidget()
        if not rw: return
        rw.taskTabsWidget.setCurrentIndex(rw.commitTabIndex)

    def showRepoTaskManifest(self, show):
        rw = self.repoTabsWidget.currentWidget()
        if not rw: return
        rw.taskTabsWidget.setCurrentIndex(rw.manifestTabIndex)

    def showRepoTaskSync(self, show):
        rw = self.repoTabsWidget.currentWidget()
        if not rw: return
        rw.taskTabsWidget.setCurrentIndex(rw.syncTabIndex)

    def showRepoTaskGrep(self, show):
        rw = self.repoTabsWidget.currentWidget()
        if not rw: return
        rw.taskTabsWidget.setCurrentIndex(rw.grepTabIndex)
        
    def openRepo(self, repopath):
        if isinstance(repopath, (unicode, QString)):  # as Qt slot
            repopath = hglib.fromunicode(repopath)
        try:
            repo = thgrepo.repository(self.ui, path=repopath)
            self.addRepoTab(repo)
        except RepoError:
            QMessageBox.warning(self, _('Failed to open repository'),
                _('%s is not a valid repository') % repopath)

    def find_root(self, url):
        p = hglib.fromunicode(url.toLocalFile())
        return paths.find_root(p)

    def dragEnterEvent(self, event):
        d = event.mimeData()
        for u in d.urls():
            root = self.find_root(u)
            if root:
                event.setDropAction(Qt.LinkAction)
                event.accept()
                break

    def dropEvent(self, event):
        accept = False
        d = event.mimeData()
        for u in d.urls():
            root = self.find_root(u)
            if root:
                self.openRepo(root)
                accept = True
        if accept:
            event.setDropAction(Qt.LinkAction)
            event.accept()

    def linkActivated(self, link):
        link = hglib.fromunicode(link)
        if link.startswith('subrepo:'):
            self.openRepo(link[8:])
            
    def updateMenu(self):
        someRepoOpen = self.repoTabsWidget.count() > 0
        self.actionGroupTaskView.setEnabled(someRepoOpen)
        self.updateTaskViewMenu()
        
        self.actionFind.setEnabled(someRepoOpen)
        self.actionRefresh.setEnabled(someRepoOpen)
        self.actionRefreshTaskTab.setEnabled(someRepoOpen)
        self.actionLoadAll.setEnabled(someRepoOpen)

        self.actionClose_repository.setEnabled(someRepoOpen)
        self.actionImport.setEnabled(someRepoOpen)
        self.actionServe.setEnabled(someRepoOpen)
        self.actionVerify.setEnabled(someRepoOpen)
        self.actionRecover.setEnabled(someRepoOpen)
        self.actionRollback.setEnabled(someRepoOpen)
        self.actionPurge.setEnabled(someRepoOpen)
        self.actionExplore.setEnabled(someRepoOpen)
        self.actionTerminal.setEnabled(someRepoOpen)

        self.actionIncoming.setEnabled(someRepoOpen)
        self.actionPull.setEnabled(someRepoOpen)
        self.actionOutgoing.setEnabled(someRepoOpen)
        self.actionPush.setEnabled(someRepoOpen)

    def updateTaskViewMenu(self, taskIndex=0):
        # Fetch selected task tab from current repowidget and check corresponding action in menu
        if self.repoTabsWidget.count() == 0:
            for a in self.actionGroupTaskView.actions():
                a.setChecked(False)
        else:
            repoWidget = self.repoTabsWidget.currentWidget()
            taskIndex = repoWidget.taskTabsWidget.currentIndex()
            self.actionGroupTaskView.actions()[taskIndex].setChecked(True)

    def repoTabCloseSelf(self, widget):
        self.repoTabsWidget.setCurrentWidget(widget)
        index = self.repoTabsWidget.currentIndex()
        if widget.closeRepoWidget():
            self.repoTabsWidget.removeTab(index)
            self.updateMenu()

    def repoTabCloseRequested(self, index):
        tw = self.repoTabsWidget
        w = tw.widget(index)
        if w and w.closeRepoWidget():
            tw.removeTab(index)
            self.updateMenu()

    def repoTabChanged(self, index=0):
        self.setupBranchCombo()
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.switchedTo()
            self.updateTaskViewMenu()
        self.log.setRepository(w and w.repo or None)

    def addRepoTab(self, repo):
        '''opens the given repo in a new tab'''
        rw = RepoWidget(repo, self)
        rw.showMessageSignal.connect(self.showMessage)
        rw.closeSelfSignal.connect(self.repoTabCloseSelf)
        rw.progress.connect(lambda tp, p, i, u, tl:
            self.statusbar.progress(tp, p, i, u, tl, repo.root))
        rw.output.connect(self.log.output)
        rw.makeLogVisible.connect(self.log.setShown)
        rw.taskTabsWidget.currentChanged.connect(self.updateTaskViewMenu)

        tw = self.repoTabsWidget
        index = self.repoTabsWidget.addTab(rw, repo.shortname)
        tw.setCurrentIndex(index)
        self.reporegistry.addRepo(repo.root)
        
        self.updateMenu()


    def showMessage(self, msg):
        self.statusbar.showMessage(msg)

    def setupBranchCombo(self, *args):
        w = self.repoTabsWidget.currentWidget()
        if not w:
            self.branchLabelAction.setEnabled(False)
            self.branchComboAction.setEnabled(False)
            self.branchCombo.clear()
            return

        repo = w.repo
        allbranches = sorted(repo.branchtags().items())

        openbr = []
        for branch, brnode in allbranches:
            openbr.extend(repo.branchheads(branch, closed=False))
        clbranches = [br for br, node in allbranches if node not in openbr]
        branches = [br for br, node in allbranches if node in openbr]
        if self.cbranch_action.isChecked():
            branches = branches + clbranches

        if len(branches) == 1:
            self.branchLabelAction.setEnabled(False)
            self.branchComboAction.setEnabled(False)
            self.branchCombo.clear()
        else:
            branches = [''] + branches
            self.branchesmodel = QStringListModel(branches)
            self.branchCombo.setModel(self.branchesmodel)
            self.branchLabelAction.setEnabled(True)
            self.branchComboAction.setEnabled(True)

            branch = w.filterbranch()
            index = -1
            for i, b in enumerate(branches):
                if b == branch:
                    index = i
                    break
            self.branchCombo.setCurrentIndex(index)


    def actionShowPathsToggled(self, show):
        self.reporegistry.showPaths(show)

    def setHistoryColumns(self, *args):
        """Display the column selection dialog"""
        w = self.repoTabsWidget.currentWidget()
        dlg = ColumnSelectDialog(repomodel.ALLCOLUMNS, w and w.repoview.model().columns)
        if dlg.exec_() == QDialog.Accepted:
            if w:
                w.repoview.model().updateColumns()
                w.repoview.resizeColumns()

    def serve(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            from tortoisehg.hgqt import run
            run.serve(self.ui, root=w.repo.root)

    def thgimport(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.thgimport()

    def verify(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.verify()

    def recover(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.recover()

    def rollback(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.rollback()

    def purge(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.purge()

    def back(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.back()

    def forward(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.forward()

    def find(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.find()

    def loadall(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.repoview.model().loadall()

    def newRepository(self):
        """ Run init dialog """
        from tortoisehg.hgqt.hginit import InitDialog
        initdlg = InitDialog(parent=self)
        if initdlg.exec_():
            path = initdlg.getPath()
            self.openRepo(path)

    def cloneRepository(self):
        """ Run clone dialog """
        from tortoisehg.hgqt.clone import CloneDialog
        clonedlg = CloneDialog(args=[], parent=self)
        if clonedlg.exec_():
            path = clonedlg.getDest()
            self.openRepo(path)

    def openRepository(self):
        caption = _('Select repository directory to open')
        FD = QFileDialog
        path = FD.getExistingDirectory(parent=self, caption=caption,
            options=FD.ShowDirsOnly | FD.ReadOnly)
        if path:
            try:
                repo = thgrepo.repository(self.ui, path=hglib.fromunicode(path))
                self.addRepoTab(repo)
            except RepoError:
                QMessageBox.warning(self, _('Failed to open repository'),
                    _('%s is not a valid repository') % path)

    def reload(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.reload()
            self.setupBranchCombo()

    def reloadTaskTab(self, root):
        rw = self.repoTabsWidget.currentWidget()
        if rw:
            rw.reloadTaskTab()

    def goto(self, root, rev):
        for rw in self._findrepowidget(root):
            rw.goto(rev)

    def reloadRepository(self, root):
        for rw in self._findrepowidget(root):
            rw.reload()
        self.setupBranchCombo()

    def _findrepowidget(self, root):
        """Iterates RepoWidget for the specified root"""
        tw = self.repoTabsWidget
        for idx in range(tw.count()):
            rw = tw.widget(idx)
            if rw.repo.root == root:
                yield rw

    #@timeit
    def setBranch(self, *args, **kw):
        'Handle new branch choice or allparents toggle'
        branch = self.branchCombo.currentText()
        branch = str(branch)
        allparents = self.allpar_action.isChecked()
        tw = self.repoTabsWidget
        w = tw.currentWidget()
        if w:
            w.setBranch(branch, allparents)
            if branch:
                tabtext = '%s [%s]' % (w.reponame(), branch)
            else:
                tabtext = w.reponame()
            tw.setTabText(tw.currentIndex(), tabtext)

    def on_about(self, *args):
        """ Display about dialog """
        from tortoisehg.hgqt.about import AboutDialog
        ad = AboutDialog()
        ad.exec_()

    def on_help(self, *args):
        pass

    def storeSettings(self):
        s = QSettings()
        wb = "Workbench/"
        s.setValue(wb + 'geometry', self.saveGeometry())
        s.setValue(wb + 'windowState', self.saveState())
        s.setValue(wb + 'showPaths', self.actionShowPaths.isChecked())

    def restoreSettings(self):
        s = QSettings()
        wb = "Workbench/"
        self.restoreGeometry(s.value(wb + 'geometry').toByteArray())
        self.restoreState(s.value(wb + 'windowState').toByteArray())
        # Allow repo registry to assemble itself before toggling path state
        sp = s.value(wb + 'showPaths').toBool()
        QTimer.singleShot(0, lambda: self.actionShowPaths.setChecked(sp))

    def closeEvent(self, event):
        if not self.closeRepoTabs():
            event.ignore()
        else:
           self.storeSettings()
           self.reporegistry.close()
           # mimic QDialog exit
           self.finished.emit(0)

    def closeRepoTabs(self):
        '''returns False if close should be aborted'''
        tw = self.repoTabsWidget
        for idx in range(tw.count()):
            rw = tw.widget(idx)
            if not rw.closeRepoWidget():
                return False
        return True

    def closeRepository(self):
        """close the current repo tab"""
        self.repoTabCloseRequested(self.repoTabsWidget.currentIndex())

    def explore(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            self.launchExplorer(w.repo.root)

    def terminal(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            self.launchTerminal(w.repo)

    def incoming(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.incoming()

    def pull(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.pull()

    def outgoing(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.outgoing()

    def push(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.push()

    def launchExplorer(self, root):
        """open Windows Explorer at the repo root"""
        QDesktopServices.openUrl(QUrl.fromLocalFile(root))

    def launchTerminal(self, repo):
        shell = repo.shell()
        if shell:
            cwd = os.getcwd()
            try:
                os.chdir(repo.root)
                QProcess.startDetached(shell)
            finally:
                os.chdir(cwd)
        else:
            InfoMsgBox(_('No shell configured'),
                       _('A terminal shell must be configured'))

    def editSettings(self):
        tw = self.repoTabsWidget
        w = tw.currentWidget()
        twrepo = (w and w.repo.root or '')
        sd = SettingsDialog(configrepo=False, focus='tortoisehg.authorcolor',
                            parent=self, root=twrepo)
        sd.exec_()


def run(ui, *pats, **opts):
    repo = None
    root = opts.get('root') or paths.find_root()
    if root:
        repo = thgrepo.repository(ui, path=root)
    return Workbench(ui, repo)

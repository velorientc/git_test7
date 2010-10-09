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
from tortoisehg.hgqt.qtlib import geticon, getfont, configstyles
from tortoisehg.hgqt.qtlib import InfoMsgBox, WarningMsgBox
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

        self.createToolbars()

        self.repoTabChanged()

        def gotVisible(state):
            self.actionShowRepoRegistry.setChecked(self.reporegistry.isVisible())
        def logVisible(state):
            self.actionShowLog.setChecked(self.log.isVisible())

        self.reporegistry.visibilityChanged.connect(gotVisible)
        self.log.visibilityChanged.connect(logVisible)

        self.savedrepos = []
        self.restoreSettings()
        self.setAcceptDrops(True)

        for savedroot in self.savedrepos:
            if repo and repo.root == savedroot:
                # keep the passed-in repo at the saved position
                self.addRepoTab(repo)
                ti = self.repoTabsWidget.currentIndex()
            else:
                self._openRepo(path=savedroot)
        if repo:
            if repo.root in self.savedrepos:
                # explicitly give focus to the passed-in repo
                self.repoTabsWidget.setCurrentIndex(ti)
                self.repoTabChanged()
            else:
                # open the passed-in repo last if it's not in the saved repos,
                # so it gets focus automatically
                self.addRepoTab(repo)
        if not repo and not self.savedrepos:
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

        self.setWindowIcon(geticon('log'))

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

        self.setCentralWidget(tw)
        self.statusbar = cmdui.ThgStatusBar(self)
        self.setStatusBar(self.statusbar)

        self.menubar = QMenuBar(self)
        self.setMenuBar(self.menubar)

        self.menuFile = m = QMenu(_("&File"), self.menubar)
        self.menubar.addAction(self.menuFile.menuAction())

        self.actionNew_repository = a = QAction(_("&New Repository..."), self)
        self.actionNew_repository.triggered.connect(self.newRepository)
        a.setShortcut(QKeySequence.New)
        m.addAction(self.actionNew_repository)

        self.actionClone_repository = a = QAction(_("Clone Repository..."), self)
        self.actionClone_repository.triggered.connect(self.cloneRepository)
        b = QKeySequence.keyBindings(QKeySequence.New)
        a.setShortcut(QKeySequence.fromString(u'Shift+' + b[0].toString()))
        m.addAction(self.actionClone_repository)

        self.actionOpen_repository = a = QAction(_("&Open Repository..."), self)
        self.actionOpen_repository.triggered.connect(self.openRepository)
        a.setShortcut(QKeySequence.Open)
        m.addAction(self.actionOpen_repository)

        self.actionClose_repository = a = QAction(_("&Close Repository"), self)
        self.actionClose_repository.triggered.connect(self.closeRepository)
        a.setShortcut(QKeySequence.Close)
        m.addAction(self.actionClose_repository)

        m.addSeparator()

        self.actionSettings = a = QAction(_('&Settings...'), self)
        self.actionSettings.triggered.connect(self.editSettings)
        a.setShortcut(QKeySequence.Preferences)
        a.setIcon(geticon('settings_user'))
        m.addAction(self.actionSettings)

        m.addSeparator()

        self.actionQuit = a = QAction(_("E&xit"), self)
        self.actionQuit.triggered.connect(self.close)
        a.setIcon(geticon('quit'))
        a.setShortcut(QKeySequence.Quit)
        a.setIconText(_("Exit"))
        a.setToolTip(_("Exit"))
        m.addAction(self.actionQuit)

        self.menuView = m = QMenu(_("&View"), self.menubar)
        self.menubar.addAction(self.menuView.menuAction())

        self.actionShowRepoRegistry = a = QAction(_("Show Repository Registry"), self)
        self.actionShowRepoRegistry.toggled.connect(self.showRepoRegistry)
        a.setCheckable(True)
        a.setIcon(geticon('repotree'))
        m.addAction(self.actionShowRepoRegistry)

        self.actionShowPaths = a = QAction(_("Show Paths"), self)
        self.actionShowPaths.toggled.connect(self.actionShowPathsToggled)
        a.setCheckable(True)
        m.addAction(self.actionShowPaths)

        self.actionShowLog = a = QAction(_("Show Output &Log"), self)
        self.actionShowLog.toggled.connect(self.showLog)
        a.setCheckable(True)
        a.setIcon(geticon('showlog'))
        a.setShortcut(QKeySequence("Ctrl+L"))
        m.addAction(self.actionShowLog)

        m.addSeparator()

        self.actionSelectColumns = QAction(_("Choose Log Columns..."), self)
        self.actionSelectColumns.triggered.connect(self.setHistoryColumns)
        m.addAction(self.actionSelectColumns)

        self.actionSaveRepos = a = QAction(_("Save Open Repositories On Exit"), self)
        a.setCheckable(True)
        m.addAction(self.actionSaveRepos)

        m.addSeparator()

        self.actionGroupTaskView = ag = QActionGroup(self, enabled=False)
        self.actionGroupTaskView.triggered.connect(self._switchRepoTaskTab)
        def addtaskview(icon, label):
            index = len(self.actionGroupTaskView.actions())
            a = self.actionGroupTaskView.addAction(geticon(icon), label)
            a.setData(index)
            a.setCheckable(True)
        addtaskview('log', _("Revision &Details"))
        addtaskview('commit', _("&Commit..."))
        addtaskview('annotate', _("&Manifest..."))
        addtaskview('repobrowse', _("&Search..."))
        addtaskview('sync', _("S&ynchronize..."))
        m.addActions(self.actionGroupTaskView.actions())

        m.addSeparator()

        self.actionRefresh = a = QAction(_("&Refresh"), self)
        self.actionRefresh.triggered.connect(self._repofwd('reload'))
        a.setIcon(geticon('reload'))
        a.setShortcut(QKeySequence.Refresh)
        a.setToolTip(_('Refresh all for current repository'))
        m.addAction(self.actionRefresh)

        self.actionRefreshTaskTab = a = QAction(_("Refresh &Task Tab"), self)
        self.actionRefreshTaskTab.triggered.connect(self._repofwd('reloadTaskTab'))
        a.setIcon(geticon('reloadtt'))
        b = QKeySequence.keyBindings(QKeySequence.Refresh)
        a.setShortcut(QKeySequence.fromString(u'Shift+' + b[0].toString()))
        a.setToolTip(_('Refresh only the current task tab'))
        m.addAction(self.actionRefreshTaskTab)

        self.menuRepository = m = QMenu(_("&Repository"), self.menubar)
        self.menubar.addAction(self.menuRepository.menuAction())

        self.actionServe = QAction(_("Web Server"), self)
        self.actionServe.triggered.connect(self.serve)
        m.addAction(self.actionServe)

        m.addSeparator()

        self.actionImport = QAction(_("Import"), self)
        self.actionImport.triggered.connect(self._repofwd('thgimport'))
        m.addAction(self.actionImport)

        m.addSeparator()

        self.actionVerify = QAction(_("Verify"), self)
        self.actionVerify.triggered.connect(self._repofwd('verify'))
        m.addAction(self.actionVerify)

        self.actionRecover = QAction(_("Recover"), self)
        self.actionRecover.triggered.connect(self._repofwd('recover'))
        m.addAction(self.actionRecover)

        m.addSeparator()

        self.actionRollback = QAction(_("Rollback/Undo"), self)
        self.actionRollback.triggered.connect(self._repofwd('rollback'))
        m.addAction(self.actionRollback)

        self.actionPurge = QAction(_("Purge"), self)
        self.actionPurge.triggered.connect(self._repofwd('purge'))
        m.addAction(self.actionPurge)

        m.addSeparator()

        self.actionExplore = a = QAction(_("Explore"), self)
        self.actionExplore.triggered.connect(self.explore)
        a.setShortcut(QKeySequence("Shift+Ctrl+S"))
        m.addAction(self.actionExplore)

        self.actionTerminal = a = QAction(_("Terminal"), self)
        self.actionTerminal.triggered.connect(self.terminal)
        a.setShortcut(QKeySequence("Shift+Ctrl+T"))
        m.addAction(self.actionTerminal)

        self.menuHelp = m = QMenu(_("&Help"), self.menubar)
        self.menubar.addAction(self.menuHelp.menuAction())

        self.actionAbout = QAction(_("About"), self)
        self.actionAbout.triggered.connect(self.on_about)
        m.addAction(self.actionAbout)

        self.actionFind = a = QAction(_('Find'), self)
        self.actionFind.triggered.connect(self._repofwd('find'))
        a.setToolTip(_('Search file and revision contents for keyword'))
        a.setIcon(geticon('find'))

        self.actionBack = a = QAction(_("Back"), self)
        self.actionBack.triggered.connect(self._repofwd('back'))
        a.setEnabled(False)
        a.setIcon(geticon('back'))

        self.actionForward = a = QAction(_("Forward"), self)
        self.actionForward.triggered.connect(self._repofwd('forward'))
        a.setEnabled(False)
        a.setIcon(geticon('forward'))

        self.actionLoadAll = a = QAction(_("Load all"), self)
        self.actionLoadAll.triggered.connect(self.loadall)
        a.setEnabled(True)
        a.setToolTip(_('Load all revisions into graph'))
        a.setIcon(geticon('loadall'))

        # TODO: Use long names when these have icons
        self.actionIncoming = a = QAction(_('In'), self)
        self.actionIncoming.triggered.connect(self._repofwd('incoming'))
        a.setToolTip(_('Check for incoming changes from default pull target'))
        a.setIcon(geticon('incoming'))
        self.actionPull = a = QAction(_('Pull'), self)
        self.actionPull.triggered.connect(self._repofwd('pull'))
        a.setToolTip(_('Pull incoming changes from default pull target'))
        a.setIcon(geticon('pull'))
        self.actionOutgoing = a = QAction(_('Out'), self)
        self.actionOutgoing.triggered.connect(self._repofwd('outgoing'))
        a.setToolTip(_('Detect outgoing changes to default push target'))
        a.setIcon(geticon('outgoing'))
        self.actionPush = a = QAction(_('Push'), self)
        self.actionPush.triggered.connect(self._repofwd('push'))
        a.setToolTip(_('Push outgoing changes to default push target'))
        a.setIcon(geticon('push'))

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

    def showRepoRegistry(self, show):
        self.reporegistry.setVisible(show)

    def showLog(self, show):
        self.log.setVisible(show)

    @pyqtSlot(QAction)
    def _switchRepoTaskTab(self, action):
        rw = self.repoTabsWidget.currentWidget()
        if not rw: return
        index = action.data().toPyObject()
        rw.taskTabsWidget.setCurrentIndex(index)

    def openRepo(self, repopath):
        """ Open repo by openRepoSignal from reporegistry """
        if isinstance(repopath, (unicode, QString)):  # as Qt slot
            repopath = hglib.fromunicode(repopath)
        self._openRepo(path=repopath)

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
        index = self.repoTabsWidget.addTab(rw, rw.title())
        tw.setCurrentIndex(index)
        rw.titleChanged.connect(
            lambda title: self.repoTabsWidget.setTabText(index, title))
        self.reporegistry.addRepo(repo.root)

        self.updateMenu()


    def showMessage(self, msg):
        self.statusbar.showMessage(msg)

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

    def _repofwd(self, name):
        """Return function to forward action to the current repo tab"""
        def forwarder():
            w = self.repoTabsWidget.currentWidget()
            if w:
                getattr(w, name)()
        return forwarder

    def serve(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            from tortoisehg.hgqt import run
            run.serve(self.ui, root=w.repo.root)

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
        """ Open repo from File menu """
        caption = _('Select repository directory to open')
        FD = QFileDialog
        path = FD.getExistingDirectory(parent=self, caption=caption,
            options=FD.ShowDirsOnly | FD.ReadOnly)
        self._openRepo(path=hglib.fromunicode(path))

    def _openRepo(self, path):
        if path:
            try:
                repo = thgrepo.repository(path=path)
                self.addRepoTab(repo)
            except RepoError:
                WarningMsgBox(_('Failed to open repository'),
                        _('%s is not a valid repository') % path)

    def goto(self, root, rev):
        for rw in self._findrepowidget(root):
            rw.goto(rev)

    def reloadRepository(self, root):
        for rw in self._findrepowidget(root):
            rw.reload()

    def _findrepowidget(self, root):
        """Iterates RepoWidget for the specified root"""
        tw = self.repoTabsWidget
        for idx in range(tw.count()):
            rw = tw.widget(idx)
            if rw.repo.root == root:
                yield rw

    def on_about(self, *args):
        """ Display about dialog """
        from tortoisehg.hgqt.about import AboutDialog
        ad = AboutDialog(self)
        ad.finished.connect(ad.deleteLater)
        ad.exec_()

    def storeSettings(self):
        s = QSettings()
        wb = "Workbench/"
        s.setValue(wb + 'geometry', self.saveGeometry())
        s.setValue(wb + 'windowState', self.saveState())
        s.setValue(wb + 'showPaths', self.actionShowPaths.isChecked())
        s.setValue(wb + 'saveRepos', self.actionSaveRepos.isChecked())
        repostosave = []
        if self.actionSaveRepos.isChecked():
            tw = self.repoTabsWidget
            for idx in range(tw.count()):
                rw = tw.widget(idx)
                repostosave.append(rw.repo.root)
        s.setValue(wb + 'openrepos', (',').join(repostosave))

    def restoreSettings(self):
        s = QSettings()
        wb = "Workbench/"
        self.restoreGeometry(s.value(wb + 'geometry').toByteArray())
        self.restoreState(s.value(wb + 'windowState').toByteArray())
        save = s.value(wb + 'saveRepos').toBool()
        self.actionSaveRepos.setChecked(save)
        sr = str(s.value(wb + 'openrepos').toString())
        if sr:
            self.savedrepos = sr.split(',')
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

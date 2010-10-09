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

        self.menuFile = self.menubar.addMenu(_("&File"))
        self.menuView = self.menubar.addMenu(_("&View"))
        self.menuRepository = self.menubar.addMenu(_("&Repository"))
        self.menuHelp = self.menubar.addMenu(_("&Help"))

        self.edittbar = QToolBar(_("Edit Toolbar"), objectName='edittbar')
        self.addToolBar(self.edittbar)
        self.docktbar = QToolBar(_("Dock Toolbar"), objectName='docktbar')
        self.addToolBar(self.docktbar)
        self.synctbar = QToolBar(_('Sync Toolbar'), objectName='synctbar')
        self.addToolBar(self.synctbar)

        def keysequence(o):
            """Create QKeySequence from string or QKeySequence"""
            if isinstance(o, (QKeySequence, QKeySequence.StandardKey)):
                return o
            try:
                return getattr(QKeySequence, str(o))  # standard key
            except AttributeError:
                return QKeySequence(o)

        def modifiedkeysequence(o, modifier):
            """Create QKeySequence of modifier key prepended"""
            origseq = QKeySequence(keysequence(o))
            return QKeySequence('%s+%s' % (modifier, origseq.toString()))

        def newaction(text, slot=None, icon=None, shortcut=None,
                      checkable=False, tooltip=None, data=None, enabled=True,
                      menu=None, toolbar=None, parent=self):
            """Create new action and register it

            :slot: function called if action triggered or toggled.
            :checkable: checkable action. slot will be called on toggled.
            :data: optional data stored on QAction.
            :shortcut: QKeySequence, key sequence or name of standard key.
            :menu: name of menu to add this action.
            :toolbar: name of toolbar to add this action.
            """
            action = QAction(text, parent, checkable=checkable,
                             enabled=enabled)
            if slot:
                if checkable:
                    action.toggled.connect(slot)
                else:
                    action.triggered.connect(slot)
            if icon:
                action.setIcon(geticon(icon))
            if shortcut:
                action.setShortcut(keysequence(shortcut))
            if tooltip:
                action.setToolTip(tooltip)
            if data is not None:
                action.setData(data)
            if menu:
                getattr(self, 'menu%s' % menu.title()).addAction(action)
            if toolbar:
                getattr(self, '%stbar' % toolbar).addAction(action)
            return action

        def newseparator(menu=None, toolbar=None):
            """Insert a separator action; returns nothing"""
            if menu:
                getattr(self, 'menu%s' % menu.title()).addSeparator()
            if toolbar:
                getattr(self, '%stbar' % toolbar).addSeparator()

        newaction(_("&New Repository..."), self.newRepository,
                  shortcut='New', menu='file')
        newaction(_("Clone Repository..."), self.cloneRepository,
                  shortcut=modifiedkeysequence('New', modifier='Shift'),
                  menu='file')
        newaction(_("&Open Repository..."), self.openRepository,
                  shortcut='Open', menu='file')
        self.actionClose_repository = \
        newaction(_("&Close Repository"), self.closeRepository,
                  shortcut='Close', menu='file')
        newseparator(menu='file')
        newaction(_('&Settings...'), self.editSettings, icon='settings_user',
                  shortcut='Preferences', menu='file')
        newseparator(menu='file')
        newaction(_("E&xit"), self.close, icon='quit',
                  shortcut='Quit', menu='file')

        self.actionShowRepoRegistry = \
        newaction(_("Show Repository Registry"), self.showRepoRegistry,
                  icon='repotree', checkable=True, menu='view',
                  toolbar='dock')
        self.actionShowPaths = \
        newaction(_("Show Paths"), self.actionShowPathsToggled,
                  checkable=True, menu='view')
        self.actionShowLog = \
        newaction(_("Show Output &Log"), self.showLog, icon='showlog',
                  shortcut='Ctrl+L', checkable=True, menu='view',
                  toolbar='dock')
        newseparator(menu='view')
        newaction(_("Choose Log Columns..."), self.setHistoryColumns,
                  menu='view')
        self.actionSaveRepos = \
        newaction(_("Save Open Repositories On Exit"), checkable=True,
                  menu='view')
        newseparator(menu='view')

        self.actionGroupTaskView = QActionGroup(self, enabled=False)
        self.actionGroupTaskView.triggered.connect(self._switchRepoTaskTab)
        def addtaskview(icon, label):
            index = len(self.actionGroupTaskView.actions())
            a = newaction(label, icon=icon, checkable=True, data=index,
                          menu='view')
            self.actionGroupTaskView.addAction(a)
        addtaskview('log', _("Revision &Details"))
        addtaskview('commit', _("&Commit..."))
        addtaskview('annotate', _("&Manifest..."))
        addtaskview('repobrowse', _("&Search..."))
        addtaskview('sync', _("S&ynchronize..."))
        newseparator(menu='view')

        self.actionRefresh = \
        newaction(_("&Refresh"), self._repofwd('reload'), icon='reload',
                  shortcut='Refresh', menu='view', toolbar='edit',
                  tooltip=_('Refresh all for current repository'))
        self.actionRefreshTaskTab = \
        newaction(_("Refresh &Task Tab"), self._repofwd('reloadTaskTab'),
                  icon='reloadtt',
                  shortcut=modifiedkeysequence('Refresh', modifier='Shift'),
                  tooltip=_('Refresh only the current task tab'),
                  menu='view', toolbar='edit')

        self.actionServe = \
        newaction(_("Web Server"), self.serve, menu='repository')
        newseparator(menu='repository')
        self.actionImport = \
        newaction(_("Import"), self._repofwd('thgimport'), menu='repository')
        newseparator(menu='repository')
        self.actionVerify = \
        newaction(_("Verify"), self._repofwd('verify'), menu='repository')
        self.actionRecover = \
        newaction(_("Recover"), self._repofwd('recover'), menu='repository')
        newseparator(menu='repository')
        self.actionRollback = \
        newaction(_("Rollback/Undo"), self._repofwd('rollback'),
                  menu='repository')
        self.actionPurge = \
        newaction(_("Purge"), self._repofwd('purge'), menu='repository')
        newseparator(menu='repository')
        self.actionExplore = \
        newaction(_("Explore"), self.explore, shortcut='Shift+Ctrl+S',
                  menu='repository')
        self.actionTerminal = \
        newaction(_("Terminal"), self.terminal, shortcut='Shift+Ctrl+T',
                  menu='repository')

        newaction(_("About"), self.on_about, menu='help')

        newseparator(toolbar='edit')
        self.actionBack = \
        newaction(_("Back"), self._repofwd('back'), icon='back',
                  enabled=False, toolbar='edit')
        self.actionForward = \
        newaction(_("Forward"), self._repofwd('forward'), icon='forward',
                  enabled=False, toolbar='edit')
        self.actionLoadAll = \
        newaction(_("Load all"), self.loadall, icon='loadall', toolbar='edit',
                  tooltip=_('Load all revisions into graph'))
        newseparator(toolbar='edit')
        self.actionFind = \
        newaction(_('Find'), self._repofwd('find'), icon='find',
                  toolbar='edit',
                  tooltip=_('Search file and revision contents for keyword'))

        # TODO: Use long names when these have icons
        self.actionIncoming = \
        newaction(_('In'), self._repofwd('incoming'), icon='incoming',
                  tooltip=_('Check for incoming changes from default pull target'),
                  toolbar='sync')
        self.actionPull = \
        newaction(_('Pull'), self._repofwd('pull'), icon='pull',
                  tooltip=_('Pull incoming changes from default pull target'),
                  toolbar='sync')
        self.actionOutgoing = \
        newaction(_('Out'), self._repofwd('outgoing'), icon='outgoing',
                   tooltip=_('Detect outgoing changes to default push target'),
                   toolbar='sync')
        self.actionPush = \
        newaction(_('Push'), self._repofwd('push'), icon='push',
                  tooltip=_('Push outgoing changes to default push target'),
                  toolbar='sync')

        self.updateMenu()

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

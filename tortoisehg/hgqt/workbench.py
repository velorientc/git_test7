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
import sys

from mercurial.error import RepoError

from tortoisehg.util import paths, hglib

from tortoisehg.hgqt import repomodel, thgrepo, cmdui, qtlib
from tortoisehg.hgqt.i18n import _
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

    def __init__(self):
        QMainWindow.__init__(self)

        self.setupUi()
        self.setWindowTitle(_('TortoiseHg Workbench'))

        self.reporegistry = rr = RepoRegistryView(self)
        rr.setObjectName('RepoRegistryView')
        rr.hide()
        self.addDockWidget(Qt.LeftDockWidgetArea, rr)

        self.log = LogDockWidget(self)
        self.log.setObjectName('Log')
        self.log.progressReceived.connect(self.statusbar.progress)
        self.log.hide()
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log)

        self._setupActions()

        rr.openRepoSignal.connect(self.openRepo)

        self.repoTabChanged()
        self.restoreSettings()
        self.setAcceptDrops(True)
        if os.name == 'nt':
            # Allow CTRL+Q to close Workbench on Windows
            QShortcut(QKeySequence('CTRL+Q'), self, self.close)
        if sys.platform == 'darwin':
            self.dockMenu = QMenu(self)
            self.dockMenu.addAction(_('New Repository...'),
                                    self.newRepository)
            self.dockMenu.addAction(_('Clone Repository...'),
                                    self.cloneRepository)
            self.dockMenu.addAction(_('Open Repository...'),
                                    self.openRepository)
            qt_mac_set_dock_menu(self.dockMenu)

    def setupUi(self):
        desktopgeom = qApp.desktop().availableGeometry()
        self.resize(desktopgeom.size() * 0.8)

        self.setWindowIcon(qtlib.geticon('hg-log'))

        self.repoTabsWidget = tw = QTabWidget()
        tw.setDocumentMode(True)
        tw.setTabsClosable(True)
        tw.setMovable(True)
        tw.tabBar().hide()
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

    def _setupActions(self):
        """Setup actions, menus and toolbars"""
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
        self.tasktbar = QToolBar(_('Task Toolbar'), objectName='taskbar')
        self.addToolBar(self.tasktbar)

        # availability map of actions; applied by updateMenu()
        self._actionavails = {'repoopen': []}

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
                      checkable=False, tooltip=None, data=None, enabled=None,
                      menu=None, toolbar=None, parent=self):
            """Create new action and register it

            :slot: function called if action triggered or toggled.
            :checkable: checkable action. slot will be called on toggled.
            :data: optional data stored on QAction.
            :enabled: bool or group name to enable/disable action.
            :shortcut: QKeySequence, key sequence or name of standard key.
            :menu: name of menu to add this action.
            :toolbar: name of toolbar to add this action.
            """
            action = QAction(text, parent, checkable=checkable)
            if slot:
                if checkable:
                    action.toggled.connect(slot)
                else:
                    action.triggered.connect(slot)
            if icon:
                if toolbar:
                    action.setIcon(qtlib.geticon(icon))
                else:
                    action.setIcon(qtlib.getmenuicon(icon))
            if shortcut:
                action.setShortcut(keysequence(shortcut))
            if tooltip:
                action.setToolTip(tooltip)
            if data is not None:
                action.setData(data)
            if isinstance(enabled, bool):
                action.setEnabled(enabled)
            elif enabled:
                self._actionavails[enabled].append(action)
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

        newaction(_("&Open Repository..."), self.openRepository,
                  shortcut='Open', menu='file')
        newaction(_("&Close Repository"), self.closeRepository,
                  shortcut='Close', enabled='repoopen', menu='file')
        newseparator(menu='file')
        newaction(_("&New Repository..."), self.newRepository,
                  shortcut='New', menu='file', icon='hg-init')
        newaction(_("Clone Repository..."), self.cloneRepository,
                  shortcut=modifiedkeysequence('New', modifier='Shift'),
                  menu='file', icon='hg-clone')
        newseparator(menu='file')
        newaction(_('&Settings...'), self.editSettings, icon='settings_user',
                  shortcut='Preferences', menu='file')
        newseparator(menu='file')
        newaction(_("E&xit"), self.close, shortcut='Quit', menu='file')

        a = self.reporegistry.toggleViewAction()
        a.setText(_('Show Repository Registry'))
        a.setShortcut('Ctrl+Shift+O')
        a.setIcon(qtlib.geticon('thg-reporegistry'))
        self.docktbar.addAction(a)
        self.menuView.addAction(a)

        self.actionShowPaths = \
        newaction(_("Show Paths"), self.reporegistry.showPaths,
                  checkable=True, menu='view')

        a = self.log.toggleViewAction()
        a.setText(_('Show Output &Log'))
        a.setShortcut('Ctrl+L')
        a.setIcon(qtlib.geticon('thg-console'))
        self.docktbar.addAction(a)
        self.menuView.addAction(a)

        newseparator(menu='view')
        newaction(_("Choose Log Columns..."), self.setHistoryColumns,
                  menu='view')
        self.actionSaveRepos = \
        newaction(_("Save Open Repositories On Exit"), checkable=True,
                  menu='view')
        newseparator(menu='view')

        self.actionGroupTaskView = QActionGroup(self)
        self.actionGroupTaskView.triggered.connect(self.onSwitchRepoTaskTab)
        def addtaskview(icon, label, data=None):
            if data is None:
                data = len(self.actionGroupTaskView.actions())
            a = newaction(label, icon=None, checkable=True, data=data,
                          enabled='repoopen', menu='view')
            a.setIcon(qtlib.geticon(icon))
            self.actionGroupTaskView.addAction(a)
            self.tasktbar.addAction(a)
            return a
        # NOTE: Sequence must match that in repowidget.py
        addtaskview('hg-log', _("Revision &Details"))
        addtaskview('hg-commit', _('&Commit'))
        addtaskview('thg-sync', _('S&ynchronize'))
        addtaskview('hg-annotate', _('&Manifest'))
        addtaskview('hg-grep', _('&Search'))
        self.actionSelectTaskMQ = \
                addtaskview('thg-mq', _('Patch &Queue'), 'mq')
        self.actionSelectTaskPbranch = \
                addtaskview('branch', _('&Patch Branch'), 'pbranch')
        newseparator(menu='view')

        newaction(_("&Refresh"), self._repofwd('reload'), icon='view-refresh',
                  shortcut='Refresh', enabled='repoopen',
                  menu='view', toolbar='edit',
                  tooltip=_('Refresh current repository'))
        newaction(_("Refresh &Task Tab"), self._repofwd('reloadTaskTab'),
                  enabled='repoopen',
                  shortcut=modifiedkeysequence('Refresh', modifier='Shift'),
                  tooltip=_('Refresh only the current task tab'),
                  menu='view')
        newaction(_("Load all revisions"), self.loadall,
                  enabled='repoopen', menu='view', shortcut='Shift+Ctrl+A',
                  tooltip=_('Load all revisions into graph'))

        newaction(_("Web Server..."), self.serve, enabled='repoopen',
                  menu='repository')
        newseparator(menu='repository')
        newaction(_("Shelve..."), self._repofwd('shelve'), icon='shelve',
                  enabled='repoopen', menu='repository')
        newaction(_("Import..."), self._repofwd('thgimport'), icon='hg-import',
                  enabled='repoopen', menu='repository')
        newseparator(menu='repository')
        newaction(_("Verify"), self._repofwd('verify'), enabled='repoopen',
                  menu='repository')
        newaction(_("Recover"), self._repofwd('recover'),
                  enabled='repoopen', menu='repository')
        newseparator(menu='repository')
        newaction(_("Resolve..."), self._repofwd('resolve'), icon='hg-merge',
                  enabled='repoopen', menu='repository')
        newseparator(menu='repository')
        newaction(_("Rollback/Undo..."), self._repofwd('rollback'),
                  enabled='repoopen', menu='repository')
        newseparator(menu='repository')
        newaction(_("Purge..."), self._repofwd('purge'), enabled='repoopen',
                  icon='hg-purge', menu='repository')
        newseparator(menu='repository')
        newaction(_("Bisect..."), self._repofwd('bisect'),
                  enabled='repoopen', menu='repository')
        newseparator(menu='repository')
        newaction(_("Explore"), self.explore, shortcut='Shift+Ctrl+S',
                  icon='system-file-manager', enabled='repoopen',
                  menu='repository')
        newaction(_("Terminal"), self.terminal, shortcut='Shift+Ctrl+T',
                  icon='utilities-terminal', enabled='repoopen',
                  menu='repository')

        newaction(_("Help"), self.onHelp, menu='help', icon='help-browser')
        newaction(_("About"), self.onAbout, menu='help', icon='thg-logo')

        newseparator(toolbar='edit')
        self.actionBack = \
        newaction(_("Back"), self._repofwd('back'), icon='go-previous',
                  enabled=False, toolbar='edit')
        self.actionForward = \
        newaction(_("Forward"), self._repofwd('forward'), icon='go-next',
                  enabled=False, toolbar='edit')
        newseparator(toolbar='edit', menu='View')

        self.filtertbaction = \
        newaction(_('Filter Toolbar'), self._repotogglefwd('toggleFilterBar'),
                  icon='view-filter', shortcut='Ctrl+S', enabled='repoopen',
                  toolbar='edit', menu='View', checkable=True,
                  tooltip=_('Filter graph with revision sets or branches'))

        menu = QMenu(_('Workbench Toolbars'), self)
        menu.addAction(self.edittbar.toggleViewAction())
        menu.addAction(self.docktbar.toggleViewAction())
        menu.addAction(self.synctbar.toggleViewAction())
        menu.addAction(self.tasktbar.toggleViewAction())
        self.menuView.addMenu(menu)

        newaction(_('Incoming'), self._repofwd('incoming'), icon='hg-incoming',
                  tooltip=_('Check for incoming changes from default pull target'),
                  enabled='repoopen', toolbar='sync')
        newaction(_('Pull'), self._repofwd('pull'), icon='hg-pull',
                  tooltip=_('Pull incoming changes from default pull target'),
                  enabled='repoopen', toolbar='sync')
        newaction(_('Outgoing'), self._repofwd('outgoing'), icon='hg-outgoing',
                   tooltip=_('Detect outgoing changes to default push target'),
                   enabled='repoopen', toolbar='sync')
        newaction(_('Push'), self._repofwd('push'), icon='hg-push',
                  tooltip=_('Push outgoing changes to default push target'),
                  enabled='repoopen', toolbar='sync')

        self.updateMenu()

    @pyqtSlot(QAction)
    def onSwitchRepoTaskTab(self, action):
        rw = self.repoTabsWidget.currentWidget()
        if not rw: return
        index, wasint = action.data().toInt()
        if wasint:
            rw.taskTabsWidget.setCurrentIndex(index)
        else:
            rw.switchToNamedTaskTab(str(action.data().toString()))

    def openRepo(self, repopath, reuse=False):
        """ Open repo by openRepoSignal from reporegistry """
        if isinstance(repopath, (unicode, QString)):  # as Qt slot
            repopath = hglib.fromunicode(repopath)
        self._openRepo(path=repopath, reuse=reuse)

    @pyqtSlot(unicode)
    def showRepo(self, path):
        """Activate the repo tab or open it if not available [unicode]"""
        for i in xrange(self.repoTabsWidget.count()):
            w = self.repoTabsWidget.widget(i)
            if hglib.tounicode(w.repo.root) == path:
                return self.repoTabsWidget.setCurrentIndex(i)
        self.openRepo(path)

    @pyqtSlot(unicode, QString)
    def setRevsetFilter(self, path, filter):
        for i in xrange(self.repoTabsWidget.count()):
            w = self.repoTabsWidget.widget(i)
            if hglib.tounicode(w.repo.root) == path:
                w.filterbar.revsetle.setText(filter)
                w.filterbar.returnPressed()
                return

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

    def updateMenu(self):
        """Enable actions when repoTabs are opened or closed or changed"""

        # Update actions affected by repo open/close
        someRepoOpen = self.repoTabsWidget.count() > 0
        for action in self._actionavails['repoopen']:
            action.setEnabled(someRepoOpen)

        # Update actions affected by repo open/close/change
        self.updateTaskViewMenu()
        self.updateToolBarActions()
        tw = self.repoTabsWidget
        w = tw.currentWidget()

        if tw.count() < 2:
            tw.tabBar().hide()
        else:
            tw.tabBar().show()
        if tw.count() == 0:
            self.setWindowTitle(_('TortoiseHg Workbench'))
        elif w.repo.shortname != w.repo.displayname:
            self.setWindowTitle(_('%s - TortoiseHg Workbench - %s') %
                                (w.repo.shortname, w.repo.displayname))
        else:
            self.setWindowTitle(_('%s - TortoiseHg Workbench') %
                                w.repo.shortname)

    def updateToolBarActions(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            self.filtertbaction.setChecked(w.filterBarVisible())

    def updateTaskViewMenu(self, taskIndex=0):
        'Update task tab menu for current repository'
        if self.repoTabsWidget.count() == 0:
            for a in self.actionGroupTaskView.actions():
                a.setChecked(False)
            self.actionSelectTaskMQ.setVisible(False)
            self.actionSelectTaskPbranch.setVisible(False)
        else:
            repoWidget = self.repoTabsWidget.currentWidget()
            exts = repoWidget.repo.extensions()
            self.actionSelectTaskMQ.setVisible('mq' in exts)
            self.actionSelectTaskPbranch.setVisible('pbranch' in exts)
            taskIndex = repoWidget.taskTabsWidget.currentIndex()
            if taskIndex <= 4: # count of standard task tabs
                self.actionGroupTaskView.actions()[taskIndex].setChecked(True)
            elif taskIndex == repoWidget.namedTabs.get('mq', None):
                self.actionSelectTaskMQ.setChecked(True)
            elif taskIndex == repoWidget.namedTabs.get('pbranch', None):
                self.actionSelectTaskPbranch.setChecked(True)

    @pyqtSlot()
    def updateHistoryActions(self):
        'Update back / forward actions'
        rw = self.repoTabsWidget.currentWidget()
        if not rw:
            return
        self.actionBack.setEnabled(rw.canGoBack())
        self.actionForward.setEnabled(rw.canGoForward())

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
            self.updateHistoryActions()
            self.updateMenu()
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
        rw.revisionSelected.connect(self.updateHistoryActions)
        rw.repoLinkClicked.connect(self.showRepo)
        rw.taskTabsWidget.currentChanged.connect(self.updateTaskViewMenu)
        rw.toolbarVisibilityChanged.connect(self.updateToolBarActions)

        tw = self.repoTabsWidget
        index = self.repoTabsWidget.addTab(rw, rw.title())
        tw.setCurrentIndex(index)
        rw.titleChanged.connect(
            lambda title: tw.setTabText(tw.indexOf(rw), title))
        self.reporegistry.addRepo(repo)

        self.updateMenu()


    def showMessage(self, msg):
        self.statusbar.showMessage(msg)

    def setHistoryColumns(self, *args):
        """Display the column selection dialog"""
        w = self.repoTabsWidget.currentWidget()
        dlg = ColumnSelectDialog(repomodel.ALLCOLUMNS,
                                 w and w.repoview.model()._columns)
        if dlg.exec_() == QDialog.Accepted:
            if w:
                w.repoview.model().updateColumns()
                w.repoview.resizeColumns()

    def _repotogglefwd(self, name):
        """Return function to forward action to the current repo tab"""
        def forwarder(checked):
            w = self.repoTabsWidget.currentWidget()
            if w:
                getattr(w, name)(checked)
        return forwarder

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
            run.serve(w.repo.ui, root=w.repo.root)

    def loadall(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.repoview.model().loadall()

    def newRepository(self):
        """ Run init dialog """
        from tortoisehg.hgqt.hginit import InitDialog
        repoWidget = self.repoTabsWidget.currentWidget()
        if repoWidget:
            path = os.path.dirname(repoWidget.repo.root)
        else:
            path = os.getcwd()
        dlg = InitDialog([path], parent=self)
        dlg.finished.connect(dlg.deleteLater)
        if dlg.exec_():
            path = dlg.getPath()
            self.openRepo(path)

    def cloneRepository(self):
        """ Run clone dialog """
        from tortoisehg.hgqt.clone import CloneDialog
        repoWidget = self.repoTabsWidget.currentWidget()
        if repoWidget:
            root = repoWidget.repo.root
            args = [root, os.path.dirname(root)]
        else:
            args = []
        dlg = CloneDialog(args, parent=self)
        dlg.finished.connect(dlg.deleteLater)
        if dlg.exec_():
            path = dlg.getDest()
            self.openRepo(path)

    def openRepository(self):
        """ Open repo from File menu """
        caption = _('Select repository directory to open')
        repoWidget = self.repoTabsWidget.currentWidget()
        if repoWidget:
            cwd = os.path.dirname(repoWidget.repo.root)
        else:
            cwd = os.getcwd()
        cwd = hglib.tounicode(cwd)
        FD = QFileDialog
        path = FD.getExistingDirectory(self, caption, cwd,
                                       FD.ShowDirsOnly | FD.ReadOnly)
        self._openRepo(path=hglib.fromunicode(path))

    def _openRepo(self, path, reuse=False):
        if path:
            if reuse:
                for rw in self._findrepowidget(path):
                    return
            try:
                repo = thgrepo.repository(path=path)
                self.addRepoTab(repo)
            except RepoError:
                qtlib.WarningMsgBox(_('Failed to open repository'),
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

    def onAbout(self, *args):
        """ Display about dialog """
        from tortoisehg.hgqt.about import AboutDialog
        ad = AboutDialog(self)
        ad.finished.connect(ad.deleteLater)
        ad.exec_()

    def onHelp(self, *args):
        """ Display online help """
        qtlib.openhelpcontents('workbench.html')

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
                repostosave.append(hglib.tounicode(rw.repo.root))
        s.setValue(wb + 'openrepos', (',').join(repostosave))

    def restoreSettings(self):
        s = QSettings()
        wb = "Workbench/"
        self.restoreGeometry(s.value(wb + 'geometry').toByteArray())
        self.restoreState(s.value(wb + 'windowState').toByteArray())
        save = s.value(wb + 'saveRepos').toBool()
        self.actionSaveRepos.setChecked(save)
        for path in hglib.fromunicode(s.value(wb + 'openrepos').toString()).split(','):
            self._openRepo(path)
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
                tw.setCurrentWidget(rw)
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
            qtlib.InfoMsgBox(_('No shell configured'),
                       _('A terminal shell must be configured'))

    def editSettings(self):
        tw = self.repoTabsWidget
        w = tw.currentWidget()
        twrepo = (w and w.repo.root or '')
        sd = SettingsDialog(configrepo=False, focus='tortoisehg.authorcolor',
                            parent=self, root=twrepo)
        sd.exec_()


def run(ui, *pats, **opts):
    root = opts.get('root') or paths.find_root()
    if root and pats:
        repo = thgrepo.repository(ui, root)
        pats = hglib.canonpaths(pats)
        if len(pats) == 1 and os.path.isfile(repo.wjoin(pats[0])):
            from tortoisehg.hgqt.filedialogs import FileLogDialog
            fname = pats[0]
            ufname = hglib.tounicode(fname)
            dlg = FileLogDialog(repo, fname, None)
            dlg.setWindowTitle(_('Hg file log viewer [%s] - %s') % (
                repo.displayname, ufname))
            return dlg
    w = Workbench()
    if root:
        root = hglib.tounicode(root)
        w.showRepo(root)
        if pats:
            q = []
            for pat in pats:
                f = repo.wjoin(pat)
                if os.path.isdir(f):
                    q.append('file("%s/**")' % pat)
                elif os.path.isfile(f):
                    q.append('file("%s")' % pat)
            w.setRevsetFilter(root, ' or '.join(q))
    if w.repoTabsWidget.count() <= 0:
        w.reporegistry.setVisible(True)
    return w

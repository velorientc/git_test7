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

from mercurial.error import RepoError

from tortoisehg.util import paths, hglib

from tortoisehg.hgqt import repomodel, thgrepo, cmdui
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.qtlib import geticon, getfont
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

    def __init__(self):
        QMainWindow.__init__(self)

        self._reload_rev = None
        self._reload_file = None

        self._loading = True
        self._scanForRepoChanges = True
        self._searchWidgets = []

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
        self.mqtbar = QToolBar(_("MQ Toolbar"), objectName='mqtbar')
        self.addToolBar(self.mqtbar)

        # availability map of actions; applied by updateMenu()
        self._actionavails = {'repoopen': [], 'mq': []}

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
                action.setIcon(geticon(icon))
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

        newaction(_("&New Repository..."), self.newRepository,
                  shortcut='New', menu='file')
        newaction(_("Clone Repository..."), self.cloneRepository,
                  shortcut=modifiedkeysequence('New', modifier='Shift'),
                  menu='file')
        newaction(_("&Open Repository..."), self.openRepository,
                  shortcut='Open', menu='file')
        newaction(_("&Close Repository"), self.closeRepository,
                  shortcut='Close', enabled='repoopen', menu='file')
        newseparator(menu='file')
        newaction(_('&Settings...'), self.editSettings, icon='settings_user',
                  shortcut='Preferences', menu='file')
        newseparator(menu='file')
        newaction(_("E&xit"), self.close, icon='quit',
                  shortcut='Quit', menu='file')

        a = self.reporegistry.toggleViewAction()
        a.setText(_('Show Repository Registry'))
        a.setShortcut('Ctrl+Shift+O')
        a.setIcon(geticon('repotree'))
        self.docktbar.addAction(a)
        self.menuView.addAction(a)

        self.actionShowPaths = \
        newaction(_("Show Paths"), self.reporegistry.showPaths,
                  checkable=True, menu='view')

        a = self.log.toggleViewAction()
        a.setText(_('Show Output &Log'))
        a.setShortcut('Ctrl+L')
        a.setIcon(geticon('showlog'))
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
        self.actionGroupTaskView.triggered.connect(self._switchRepoTaskTab)
        def addtaskview(icon, label):
            index = len(self.actionGroupTaskView.actions())
            a = newaction(label, icon=icon, checkable=True, data=index,
                          enabled='repoopen', menu='view')
            self.actionGroupTaskView.addAction(a)
            self.tasktbar.addAction(a)
            return a
        # NOTE: Sequence must match that in repowidget.py
        addtaskview('log', _("Revision &Details"))
        addtaskview('commit', _("&Commit..."))
        addtaskview('annotate', _("&Manifest..."))
        addtaskview('repobrowse', _("&Search..."))
        addtaskview('view-refresh', _("S&ynchronize..."))
        self.actionSelectTaskPbranch = \
        addtaskview('branch', _("&Patch Branch..."))
        newseparator(menu='view')

        newaction(_("&Refresh"), self._repofwd('reload'), icon='reload',
                  shortcut='Refresh', enabled='repoopen',
                  menu='view', toolbar='edit',
                  tooltip=_('Refresh all for current repository'))
        newaction(_("Refresh &Task Tab"), self._repofwd('reloadTaskTab'),
                  icon='reloadtt', enabled='repoopen',
                  shortcut=modifiedkeysequence('Refresh', modifier='Shift'),
                  tooltip=_('Refresh only the current task tab'),
                  menu='view', toolbar='edit')

        newaction(_("Web Server"), self.serve, enabled='repoopen',
                  menu='repository')
        newaction(_("Bisect"), self._repofwd('bisect'),
                  enabled='repoopen', menu='repository')
        newseparator(menu='repository')
        newaction(_("Import"), self._repofwd('thgimport'),
                  enabled='repoopen', menu='repository')
        newseparator(menu='repository')
        newaction(_("Verify"), self._repofwd('verify'), enabled='repoopen',
                  menu='repository')
        newaction(_("Recover"), self._repofwd('recover'), enabled='repoopen',
                  menu='repository')
        newseparator(menu='repository')
        newaction(_("Resolve"), self._repofwd('resolve'),
                  enabled='repoopen', menu='repository')
        newaction(_("Rollback/Undo"), self._repofwd('rollback'),
                  enabled='repoopen', menu='repository')
        newaction(_("Purge"), self._repofwd('purge'), enabled='repoopen',
                  menu='repository')
        newseparator(menu='repository')
        newaction(_("Explore"), self.explore, shortcut='Shift+Ctrl+S',
                  enabled='repoopen', menu='repository')
        newaction(_("Terminal"), self.terminal, shortcut='Shift+Ctrl+T',
                  enabled='repoopen', menu='repository')

        newaction(_("About"), self.on_about, menu='help', icon='help-browser')

        newseparator(toolbar='edit')
        self.actionBack = \
        newaction(_("Back"), self._repofwd('back'), icon='back',
                  enabled=False, toolbar='edit')
        self.actionForward = \
        newaction(_("Forward"), self._repofwd('forward'), icon='forward',
                  enabled=False, toolbar='edit')
        newaction(_("Load all"), self.loadall, icon='loadall',
                  enabled='repoopen', toolbar='edit',
                  tooltip=_('Load all revisions into graph'))
        newseparator(toolbar='edit', menu='View')
        newaction(_('Filter Toolbar'), self._repofwd('toggleFilterBar'),
                  icon='find', shortcut='Ctrl+S', enabled='repoopen',
                  toolbar='edit', menu='View',
                  tooltip=_('Filter graph with revision sets or branches'))
        newaction(_('Goto Toolbar'), self._repofwd('toggleGotoBar'),
                  icon='go-jump', shortcut='Ctrl+T', enabled='repoopen',
                  toolbar='edit', menu='View',
                  tooltip=_('Jump to a specific revision'))
        newaction(_('Find in File'), self._repofwd('toggleSearchBar'),
                  icon='edit-find', shortcut='Find', enabled='repoopen',
                  toolbar='edit', menu='View', checkable=False,
                  tooltip=_('Search file and revision contents for keyword'))

        newaction(_('Incoming'), self._repofwd('incoming'), icon='incoming',
                  tooltip=_('Check for incoming changes from default pull target'),
                  enabled='repoopen', toolbar='sync')
        newaction(_('Pull'), self._repofwd('pull'), icon='pull',
                  tooltip=_('Pull incoming changes from default pull target'),
                  enabled='repoopen', toolbar='sync')
        newaction(_('Outgoing'), self._repofwd('outgoing'), icon='outgoing',
                   tooltip=_('Detect outgoing changes to default push target'),
                   enabled='repoopen', toolbar='sync')
        newaction(_('Push'), self._repofwd('push'), icon='push',
                  tooltip=_('Push outgoing changes to default push target'),
                  enabled='repoopen', toolbar='sync')

        newaction(_('QPush'), self._repofwd('qpush'), icon='qpush',
                   tooltip=_('Apply one patch'),
                   enabled='mq', toolbar='mq')
        newaction(_('QPop'), self._repofwd('qpop'), icon='qpop',
                  tooltip=_('Unapply one patch'),
                  enabled='mq', toolbar='mq')

        self.updateMenu()

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

        tw = self.repoTabsWidget
        w = tw.currentWidget()
        mqEnabled = w and 'mq' in w.repo.extensions() or False
        for action in self._actionavails['mq']:
            action.setEnabled(mqEnabled)

        if tw.count() > 1:
            tw.tabBar().show()
            self.setWindowTitle(_('TortoiseHg Workbench'))
        elif tw.count() == 1:
            tw.tabBar().hide()
            self.setWindowTitle(_('TortoiseHg Workbench - %s') %
                                w.repo.displayname)
        else:
            tw.tabBar().hide()
            self.setWindowTitle(_('TortoiseHg Workbench'))


    def updateTaskViewMenu(self, taskIndex=0):
        # Fetch selected task tab from current repowidget and check corresponding action in menu
        if self.repoTabsWidget.count() == 0:
            for a in self.actionGroupTaskView.actions():
                a.setChecked(False)
            self.actionSelectTaskPbranch.setVisible(False)
        else:
            repoWidget = self.repoTabsWidget.currentWidget()
            self.actionSelectTaskPbranch.setVisible('pbranch' in repoWidget.repo.extensions())
            taskIndex = repoWidget.taskTabsWidget.currentIndex()
            self.actionGroupTaskView.actions()[taskIndex].setChecked(True)

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

        tw = self.repoTabsWidget
        index = self.repoTabsWidget.addTab(rw, rw.title())
        tw.setCurrentIndex(index)
        rw.titleChanged.connect(
            lambda title: tw.setTabText(tw.indexOf(rw), title))
        self.reporegistry.addRepo(repo.root)

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
        for path in str(s.value(wb + 'openrepos').toString()).split(','):
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
    root = opts.get('root') or paths.find_root()
    if root and pats:
        repo = thgrepo.repository(ui, root)
        pats = hglib.canonpaths(pats)
        if len(pats) == 1 and os.path.isfile(repo.wjoin(pats[0])):
            from tortoisehg.hgqt.filedialogs import FileLogDialog
            return FileLogDialog(repo, pats[0], None)
    w = Workbench()
    if root:
        root = hglib.tounicode(root)
        w.showRepo(root)
        if pats:
            q = []
            for pat in pats:
                f = repo.wjoin(pat)
                if os.path.isdir(f):
                    q.append('file("%s/*")' % pat)
                elif os.path.isfile(f):
                    q.append('file("%s")' % pat)
            w.setRevsetFilter(root, ' or '.join(q))
    if w.repoTabsWidget.count() <= 0:
        w.reporegistry.setVisible(True)
    return w

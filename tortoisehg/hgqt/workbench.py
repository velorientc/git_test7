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

from tortoisehg.hgqt import cmdui, qtlib, mq, serve
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.repowidget import RepoWidget
from tortoisehg.hgqt.reporegistry import RepoRegistryView
from tortoisehg.hgqt.logcolumns import ColumnSelectDialog
from tortoisehg.hgqt.docklog import LogDockWidget
from tortoisehg.hgqt.settings import SettingsDialog

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class ThgTabBar(QTabBar):
    def mouseReleaseEvent(self, event):

        if event.button() == Qt.MidButton:
            self.tabCloseRequested.emit(self.tabAt(event.pos()))

        super(ThgTabBar, self).mouseReleaseEvent(event)

class Workbench(QMainWindow):
    """hg repository viewer/browser application"""
    finished = pyqtSignal(int)

    def __init__(self, ui, repomanager):
        QMainWindow.__init__(self)
        self.progressDialog = QProgressDialog(
            'TortoiseHg - Initializing Workbench', QString(), 0, 100)
        self.progressDialog.setAutoClose(False)

        self.ui = ui
        self._repomanager = repomanager
        self._repomanager.configChanged.connect(self._setupUrlComboIfCurrent)
        self._repomanager.configChanged.connect(self._updateRepoShortName)
        self._repomanager.repositoryChanged.connect(self._updateRepoBaseNode)
        self._repomanager.repositoryDestroyed.connect(self.closeRepo)
        self._repomanager.repositoryOpened.connect(self._updateRepoRegItem)

        self.setupUi()
        self.setWindowTitle(_('TortoiseHg Workbench'))
        self.reporegistry = rr = RepoRegistryView(self)
        rr.setObjectName('RepoRegistryView')
        rr.showMessage.connect(self.showMessage)
        rr.openRepo.connect(self.openRepo)
        rr.removeRepo.connect(self.closeRepo)
        rr.progressReceived.connect(self.progress)
        self._repomanager.repositoryChanged.connect(rr.scanRepo)
        rr.hide()
        self.addDockWidget(Qt.LeftDockWidgetArea, rr)

        self.mqpatches = p = mq.MQPatchesWidget(self)
        p.setObjectName('MQPatchesWidget')
        p.showMessage.connect(self.showMessage)
        p.hide()
        self.addDockWidget(Qt.LeftDockWidgetArea, p)

        self.log = LogDockWidget(repomanager, self)
        self.log.setObjectName('Log')
        self.log.progressReceived.connect(self.statusbar.progress)
        self.log.hide()
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log)

        self._setupActions()

        self.restoreSettings()
        self.repoTabChanged()
        self.setAcceptDrops(True)
        if os.name == 'nt':
            # Allow CTRL+Q to close Workbench on Windows
            QShortcut(QKeySequence('CTRL+Q'), self, self.close)
        if sys.platform == 'darwin':
            self.dockMenu = QMenu(self)
            self.dockMenu.addAction(_('New &Workbench'),
                                    self.newWorkbench)
            self.dockMenu.addAction(_('&New Repository...'),
                                    self.newRepository)
            self.dockMenu.addAction(_('Clon&e Repository...'),
                                    self.cloneRepository)
            self.dockMenu.addAction(_('&Open Repository...'),
                                    self.openRepository)
            qt_mac_set_dock_menu(self.dockMenu)
            # On Mac OS X, we do not want icons on menus
            qt_mac_set_menubar_icons(False)

        # Create the actions that will be displayed on the context menu
        self.createActions()
        self.lastClosedRepoRootList = []
        self.progressDialog.close()
        self.progressDialog = None
        self._dialogs = qtlib.DialogKeeper(
            lambda self, dlgmeth: dlgmeth(self), parent=self)

    def setupUi(self):
        desktopgeom = qApp.desktop().availableGeometry()
        self.resize(desktopgeom.size() * 0.8)

        self.setWindowIcon(qtlib.geticon('hg-log'))

        self.repoTabsWidget = tw = QTabWidget()
        # FIXME setTabBar() is protected method
        tw.setTabBar(ThgTabBar())
        tw.setDocumentMode(True)
        tw.setTabsClosable(True)
        tw.setMovable(True)
        tw.tabBar().hide()
        tw.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        tw.tabBar().customContextMenuRequested.connect(
            self.tabBarContextMenuRequest)
        tw.lastClickedTab = -1 # No tab clicked yet

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
        self.menuViewregistryopts = QMenu(_('Workbench Toolbars'), self)
        self.menuRepository = self.menubar.addMenu(_("&Repository"))
        self.menuHelp = self.menubar.addMenu(_("&Help"))

        self.edittbar = QToolBar(_("&Edit Toolbar"), objectName='edittbar')
        self.addToolBar(self.edittbar)
        self.docktbar = QToolBar(_("&Dock Toolbar"), objectName='docktbar')
        self.addToolBar(self.docktbar)
        self.tasktbar = QToolBar(_('&Task Toolbar'), objectName='taskbar')
        self.addToolBar(self.tasktbar)
        self.customtbar = QToolBar(_('&Custom Toolbar'), objectName='custombar')
        self.addToolBar(self.customtbar)
        self.synctbar = QToolBar(_('S&ync Toolbar'), objectName='synctbar')
        self.addToolBar(self.synctbar)

        # availability map of actions; applied by updateMenu()
        self._actionavails = {'repoopen': []}
        self._actionvisibles = {'repoopen': []}

        modifiedkeysequence = qtlib.modifiedkeysequence
        newaction = self._addNewAction
        newseparator = self._addNewSeparator

        newaction(_("New &Workbench"), self.newWorkbench,
                  shortcut='Shift+Ctrl+W', menu='file', icon='hg-log')
        newseparator(menu='file')
        newaction(_("&New Repository..."), self.newRepository,
                  shortcut='New', menu='file', icon='hg-init')
        newaction(_("Clon&e Repository..."), self.cloneRepository,
                  shortcut=modifiedkeysequence('New', modifier='Shift'),
                  menu='file', icon='hg-clone')
        newseparator(menu='file')
        newaction(_("&Open Repository..."), self.openRepository,
                  shortcut='Open', menu='file')
        newaction(_("&Close Repository"), self.closeCurrentRepoTab,
                  shortcut='Close', enabled='repoopen', menu='file')
        newseparator(menu='file')
        newaction(_('&Settings'), self.editSettings, icon='settings_user',
                  shortcut='Preferences', menu='file')
        newseparator(menu='file')
        newaction(_("E&xit"), self.close, shortcut='Quit', menu='file')

        a = self.reporegistry.toggleViewAction()
        a.setText(_('Sh&ow Repository Registry'))
        a.setShortcut('Ctrl+Shift+O')
        a.setIcon(qtlib.geticon('thg-reporegistry'))
        self.docktbar.addAction(a)
        self.menuView.addAction(a)

        a = self.mqpatches.toggleViewAction()
        a.setText(_('Show &Patch Queue'))
        a.setIcon(qtlib.geticon('thg-mq'))
        self.docktbar.addAction(a)
        self.menuView.addAction(a)

        a = self.log.toggleViewAction()
        a.setText(_('Show Output &Log'))
        a.setShortcut('Ctrl+L')
        a.setIcon(qtlib.geticon('thg-console'))
        self.docktbar.addAction(a)
        self.menuView.addAction(a)

        newseparator(menu='view')
        self.menuViewregistryopts = self.menuView.addMenu(
            _('R&epository Registry Options'))
        self.menuViewregistryopts.addActions(self.reporegistry.settingActions())

        newseparator(menu='view')
        newaction(_("C&hoose Log Columns..."), self.setHistoryColumns,
                  menu='view')
        self.actionSaveRepos = \
        newaction(_("Save Open Repositories on E&xit"), checkable=True,
                  menu='view')
        newseparator(menu='view')

        self.actionGroupTaskView = QActionGroup(self)
        self.actionGroupTaskView.triggered.connect(self.onSwitchRepoTaskTab)
        def addtaskview(icon, label, name, shortcut=None):
            a = newaction(label, icon=None, checkable=True, data=name,
                          enabled='repoopen', menu='view')
            a.setIcon(qtlib.geticon(icon))
            if shortcut:
                a.setShortcut(shortcut)
            self.actionGroupTaskView.addAction(a)
            self.tasktbar.addAction(a)
            return a

        # note that 'grep' and 'search' are equivalent
        taskdefs = {
            'commit': ('hg-commit', _('&Commit')),
            'mq': ('thg-qrefresh', _('M&Q Patch')),
            'pbranch': ('branch', _('&Patch Branch')),
            'log': ('hg-log', _("Revision &Details")),
            'manifest': ('hg-annotate', _('&Manifest')),
            'grep': ('hg-grep', _('&Search')),
            'sync': ('thg-sync', _('S&ynchronize')),
        }
        tasklist = self.ui.configlist(
            'tortoisehg', 'workbench.task-toolbar', [])
        if tasklist == []:
            tasklist = ['log', 'commit', 'mq', 'manifest',
                'grep', 'pbranch', '|', 'sync']

        self.actionSelectTaskMQ = None
        self.actionSelectTaskPbranch = None

        for i, taskname in enumerate(tasklist):
            taskname = taskname.strip()
            taskinfo = taskdefs.get(taskname, None)
            if taskinfo is None:
                newseparator(toolbar='task')
                continue
            tbar = addtaskview(taskinfo[0], taskinfo[1], taskname,
                               "Alt+%d" % (i + 1))
            if taskname == 'mq':
                self.actionSelectTaskMQ = tbar
            elif taskname == 'pbranch':
                self.actionSelectTaskPbranch = tbar

        newseparator(menu='view')

        newaction(_("&Refresh"), self.refresh, icon='view-refresh',
                  shortcut='Refresh', enabled='repoopen',
                  menu='view', toolbar='edit',
                  tooltip=_('Refresh current repository'))
        newaction(_("Refresh &Task Tab"), self._repofwd('reloadTaskTab'),
                  enabled='repoopen',
                  shortcut=modifiedkeysequence('Refresh', modifier='Shift'),
                  tooltip=_('Refresh only the current task tab'),
                  menu='view')
        newaction(_("Load &All Revisions"), self.loadall,
                  enabled='repoopen', menu='view', shortcut='Shift+Ctrl+A',
                  tooltip=_('Load all revisions into graph'))
        newaction(_("&Goto Revision..."), self.gotorev,
                  enabled='repoopen', menu='view', shortcut='Ctrl+/',
                  tooltip=_('Go to a specific revision'))

        menuSync = self.menuRepository.addMenu(_('S&ynchronize'))
        newseparator(menu='repository')
        newaction(_("Start &Web Server"), self.serve, menu='repository')
        newseparator(menu='repository')
        newaction(_("&Shelve..."), self._repofwd('shelve'), icon='shelve',
                  enabled='repoopen', menu='repository')
        newaction(_("&Import..."), self._repofwd('thgimport'), icon='hg-import',
                  enabled='repoopen', menu='repository')
        newseparator(menu='repository')
        newaction(_("&Verify"), self._repofwd('verify'), enabled='repoopen',
                  menu='repository')
        newaction(_("Re&cover"), self._repofwd('recover'),
                  enabled='repoopen', menu='repository')
        newseparator(menu='repository')
        newaction(_("&Resolve..."), self._repofwd('resolve'), icon='hg-merge',
                  enabled='repoopen', menu='repository')
        newseparator(menu='repository')
        newaction(_("Rollback/&Undo..."), self._repofwd('rollback'),
                  shortcut='Ctrl+u',
                  enabled='repoopen', menu='repository')
        newseparator(menu='repository')
        newaction(_("&Purge..."), self._repofwd('purge'), enabled='repoopen',
                  icon='hg-purge', menu='repository')
        newseparator(menu='repository')
        newaction(_("&Bisect..."), self._repofwd('bisect'),
                  enabled='repoopen', menu='repository')
        newseparator(menu='repository')
        newaction(_("E&xplore"), self.explore, shortcut='Shift+Ctrl+X',
                  icon='system-file-manager', enabled='repoopen',
                  menu='repository')
        newaction(_("&Terminal"), self.terminal, shortcut='Shift+Ctrl+T',
                  icon='utilities-terminal', enabled='repoopen',
                  menu='repository')

        newaction(_("&Help"), self.onHelp, menu='help', icon='help-browser')
        newaction(_("E&xplorer Help"), self.onHelpExplorer, menu='help')
        visiblereadme = 'repoopen'
        if  self.ui.config('tortoisehg', 'readme', None):
            visiblereadme = True
        newaction(_("&Readme"), self.onReadme, menu='help', icon='help-readme',
                  visible=visiblereadme, shortcut='Ctrl+F1')
        newseparator(menu='help')
        newaction(_("About &Qt"), QApplication.aboutQt, menu='help')
        newaction(_("&About TortoiseHg"), self.onAbout, menu='help',
                  icon='thg-logo')

        newseparator(toolbar='edit')
        self.actionCurrentRev = \
        newaction(_("Go to current revision"), self._repofwd('gotoParent'),
                  icon='go-home', tooltip=_('Go to current revision'),
                  enabled=True, toolbar='edit', shortcut='Ctrl+.')
        self.actionGoTo = \
        newaction(_("Go to a specific revision"), self.gotorev,
                  icon='go-to-rev', tooltip=_('Go to a specific revision'),
                  enabled=True, toolbar='edit')
        self.actionBack = \
        newaction(_("Back"), self._repofwd('back'), icon='go-previous',
                  enabled=False, toolbar='edit')
        self.actionForward = \
        newaction(_("Forward"), self._repofwd('forward'), icon='go-next',
                  enabled=False, toolbar='edit')
        newseparator(toolbar='edit', menu='View')

        self.filtertbaction = \
        newaction(_('&Filter Toolbar'), self._repotogglefwd('toggleFilterBar'),
                  icon='view-filter', shortcut='Ctrl+S', enabled='repoopen',
                  toolbar='edit', menu='View', checkable=True,
                  tooltip=_('Filter graph with revision sets or branches'))

        menu = QMenu(_('&Workbench Toolbars'), self)
        menu.addAction(self.edittbar.toggleViewAction())
        menu.addAction(self.docktbar.toggleViewAction())
        menu.addAction(self.tasktbar.toggleViewAction())
        menu.addAction(self.synctbar.toggleViewAction())
        menu.addAction(self.customtbar.toggleViewAction())
        self.menuView.addMenu(menu)

        newaction(_('&Incoming'), data='incoming', icon='hg-incoming',
                  enabled='repoopen', toolbar='sync', shortcut='Ctrl+Shift+,')
        newaction(_('&Pull'), data='pull', icon='hg-pull',
                  enabled='repoopen', toolbar='sync')
        newaction(_('&Outgoing'), data='outgoing', icon='hg-outgoing',
                  enabled='repoopen', toolbar='sync', shortcut='Ctrl+Shift+.')
        newaction(_('P&ush'), data='push', icon='hg-push',
                  enabled='repoopen', toolbar='sync')
        menuSync.addActions(self.synctbar.actions())
        self.urlCombo = QComboBox(self)
        self.urlCombo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.urlCombo.currentIndexChanged.connect(self._updateSyncUrlToolTip)
        self.urlComboAction = self.synctbar.addWidget(self.urlCombo)
        # hide it because workbench could be started without open repo
        self.urlComboAction.setVisible(False)
        self.synctbar.actionTriggered.connect(self._runSyncAction)

        self.updateMenu()

    def _setupUrlCombo(self, repo):
        """repository has been switched, fill urlCombo with URLs"""
        pathdict = dict((hglib.tounicode(alias), hglib.tounicode(path))
                         for alias, path in repo.ui.configitems('paths'))
        aliases = pathdict.keys()

        combo_setting = repo.ui.config('tortoisehg', 'workbench.target-combo',
                                       'auto')
        self.urlComboAction.setVisible(len(aliases) > 1
                                       or combo_setting == 'always')

        # 1. Sort the list if aliases
        aliases.sort()
        # 2. Place the default alias at the top of the list
        if 'default' in aliases:
            aliases.remove('default')
            aliases.insert(0, 'default')
        # 3. Make a list of paths that have a 'push path'
        # note that the default path will be first (if it has a push path),
        # followed by the other paths that have a push path, alphabetically
        haspushaliases = [alias for alias in aliases
                         if alias + '-push' in aliases]
        # 4. Place the "-push" paths next to their "pull paths"
        regularaliases = []
        for a in aliases[:]:
            if a.endswith('-push'):
                if a[:-len('-push')] in haspushaliases:
                    continue
            regularaliases.append(a)
            if a in haspushaliases:
                regularaliases.append(a + '-push')
        # 5. Create the list of 'combined aliases'
        combinedaliases = [(a, a + '-push') for a in haspushaliases]
        # 6. Put the combined aliases first, followed by the regular aliases
        aliases = combinedaliases + regularaliases
        # 7. Ensure the first path is a default path (either a
        # combined "default | default-push" path or a regular default path)
        if not 'default-push' in aliases and 'default' in aliases:
            aliases.remove('default')
            aliases.insert(0, 'default')

        self.urlCombo.blockSignals(True)
        self.urlCombo.clear()
        for n, a in enumerate(aliases):
            # text, (pull-alias, push-alias)
            if isinstance(a, tuple):
                itemtext = u'\u2193 %s | %s \u2191' % a
                itemdata = tuple(pathdict[alias] for alias in a)
                tooltip = _('pull: %s\npush: %s') % itemdata
            else:
                itemtext = a
                itemdata = (pathdict[a], pathdict[a])
                tooltip = pathdict[a]
            self.urlCombo.addItem(itemtext, itemdata)
            self.urlCombo.setItemData(n, tooltip, Qt.ToolTipRole)
        self.urlCombo.blockSignals(False)
        self._updateSyncUrlToolTip(self.urlCombo.currentIndex())

    @pyqtSlot(unicode)
    def _setupUrlComboIfCurrent(self, root):
        w = self.repoTabsWidget.currentWidget()
        if w.repoRootPath() == root:
            self._setupUrlCombo(w.repo)

    def _syncUrlFor(self, op):
        """Current URL for the given sync operation"""
        urlindex = self.urlCombo.currentIndex()
        if urlindex < 0:
            return
        opindex = {'incoming': 0, 'pull': 0, 'outgoing': 1, 'push': 1}[op]
        return self.urlCombo.itemData(urlindex).toPyObject()[opindex]

    @pyqtSlot(int)
    def _updateSyncUrlToolTip(self, index):
        self._updateUrlComboToolTip(index)
        self._updateSyncActionToolTip(index)

    def _updateUrlComboToolTip(self, index):
        if not self.urlCombo.count():
            tooltip = _('There are no configured sync paths.\n'
                        'Open the Synchronize tab to configure them.')
        else:
            tooltip = self.urlCombo.itemData(index, Qt.ToolTipRole).toString()
        self.urlCombo.setToolTip(tooltip)

    def _updateSyncActionToolTip(self, index):
        if index < 0:
            tooltips = {
                'incoming': _('Check for incoming changes'),
                'pull':     _('Pull incoming changes'),
                'outgoing': _('Detect outgoing changes'),
                'push':     _('Push outgoing changes'),
                }
        else:
            pullurl, pushurl = self.urlCombo.itemData(index).toPyObject()
            tooltips = {
                'incoming': _('Check for incoming changes from\n%s') % pullurl,
                'pull':     _('Pull incoming changes from\n%s') % pullurl,
                'outgoing': _('Detect outgoing changes to\n%s') % pushurl,
                'push':     _('Push outgoing changes to\n%s') % pushurl,
                }

        for a in self.synctbar.actions():
            op = str(a.data().toString())
            if op in tooltips:
                a.setToolTip(tooltips[op])

    def _setupCustomTools(self, ui):
        tools, toollist = hglib.tortoisehgtools(ui,
            selectedlocation='workbench.custom-toolbar')
        # Clear the existing "custom" toolbar
        self.customtbar.clear()
        # and repopulate it again with the tool configuration
        # for the current repository
        if not tools:
            return
        for name in toollist:
            if name == '|':
                self._addNewSeparator(toolbar='custom')
                continue
            info = tools.get(name, None)
            if info is None:
                continue
            command = info.get('command', None)
            if not command:
                continue
            showoutput = info.get('showoutput', False)
            workingdir = info.get('workingdir', '')
            label = info.get('label', name)
            tooltip = info.get('tooltip', _("Execute custom tool '%s'") % label)
            icon = info.get('icon', 'tools-spanner-hammer')

            self._addNewAction(label,
                self._repofwd('runCustomCommand',
                              [command, showoutput, workingdir]),
                icon=icon, tooltip=tooltip,
                enabled=True, toolbar='custom')

    def _addNewAction(self, text, slot=None, icon=None, shortcut=None,
                  checkable=False, tooltip=None, data=None, enabled=None,
                  visible=None, menu=None, toolbar=None):
        """Create new action and register it

        :slot: function called if action triggered or toggled.
        :checkable: checkable action. slot will be called on toggled.
        :data: optional data stored on QAction.
        :enabled: bool or group name to enable/disable action.
        :visible: bool or group name to show/hide action.
        :shortcut: QKeySequence, key sequence or name of standard key.
        :menu: name of menu to add this action.
        :toolbar: name of toolbar to add this action.
        """
        action = QAction(text, self, checkable=checkable)
        if slot:
            if checkable:
                action.toggled.connect(slot)
            else:
                action.triggered.connect(slot)
        if icon:
            action.setIcon(qtlib.geticon(icon))
        if shortcut:
            keyseq = qtlib.keysequence(shortcut)
            if isinstance(keyseq, QKeySequence.StandardKey):
                action.setShortcuts(keyseq)
            else:
                action.setShortcut(keyseq)
        if tooltip:
            action.setToolTip(tooltip)
        if data is not None:
            action.setData(data)
        if isinstance(enabled, bool):
            action.setEnabled(enabled)
        elif enabled:
            self._actionavails[enabled].append(action)
        if isinstance(visible, bool):
            action.setVisible(visible)
        elif visible:
            self._actionvisibles[visible].append(action)
        if menu:
            getattr(self, 'menu%s' % menu.title()).addAction(action)
        if toolbar:
            getattr(self, '%stbar' % toolbar).addAction(action)
        return action

    def _addNewSeparator(self, menu=None, toolbar=None):
        """Insert a separator action; returns nothing"""
        if menu:
            getattr(self, 'menu%s' % menu.title()).addSeparator()
        if toolbar:
            getattr(self, '%stbar' % toolbar).addSeparator()

    def _action_defs(self):
        a = [("closetab", _("Close tab"), '',
                _("Close tab"), self.closeLastClickedTab),
             ("closeothertabs", _("Close other tabs"), '',
                _("Close other tabs"), self.closeNotLastClickedTabs),
             ("reopenlastclosed", _("Undo close tab"), '',
                _("Reopen last closed tab"), self.reopenLastClosedTabs),
             ("reopenlastclosedgroup", _("Undo close other tabs"), '',
                _("Reopen last closed tab group"), self.reopenLastClosedTabs),
             ]
        return a

    def createActions(self):
        self._actions = {}
        for name, desc, icon, tip, cb in self._action_defs():
            self._actions[name] = QAction(desc, self)
        QTimer.singleShot(0, self.configureActions)

    def configureActions(self):
        for name, desc, icon, tip, cb in self._action_defs():
            act = self._actions[name]
            if icon:
                act.setIcon(qtlib.geticon(icon))
            if tip:
                act.setStatusTip(tip)
            if cb:
                act.triggered.connect(cb)
            self.addAction(act)

    @pyqtSlot(QPoint)
    def tabBarContextMenuRequest(self, point):
        # Activate the clicked tab
        clickedwidget = qApp.widgetAt(self.repoTabsWidget.mapToGlobal(point))
        if not clickedwidget or \
            not isinstance(clickedwidget, ThgTabBar):
            return
        self.repoTabsWidget.lastClickedTab = -1

        clickedtabindex = clickedwidget.tabAt(point)
        if clickedtabindex > -1:
            self.repoTabsWidget.lastClickedTab = clickedtabindex
        else:
            self.repoTabsWidget.lastClickedTab = self.repoTabsWidget.currentIndex()

        actionlist = ['closetab', 'closeothertabs']

        existingClosedRepoList = []

        for reporoot in self.lastClosedRepoRootList:
            if os.path.isdir(reporoot):
                existingClosedRepoList.append(reporoot)
        self.lastClosedRepoRootList = existingClosedRepoList

        if len(self.lastClosedRepoRootList) > 1:
            actionlist += ['', 'reopenlastclosedgroup']
        elif len(self.lastClosedRepoRootList) > 0:
            actionlist += ['', 'reopenlastclosed']

        contextmenu = QMenu(self)
        for act in actionlist:
            if act:
                contextmenu.addAction(self._actions[act])
            else:
                contextmenu.addSeparator()

        if actionlist:
            contextmenu.exec_(self.repoTabsWidget.mapToGlobal(point))

    @pyqtSlot()
    def closeLastClickedTab(self):
        if self.repoTabsWidget.lastClickedTab > -1:
            self.repoTabCloseRequested(self.repoTabsWidget.lastClickedTab)

    def _closeOtherTabs(self, tabIndex):
        if tabIndex > -1:
            tb = self.repoTabsWidget.tabBar()
            tb.setCurrentIndex(tabIndex)
            closedRepoRootList = []
            for idx in range(tb.count()-1, -1, -1):
                if idx != tabIndex:
                    self.repoTabCloseRequested(idx)
                    # repoTabCloseRequested updates self.lastClosedRepoRootList
                    closedRepoRootList += self.lastClosedRepoRootList
            self.lastClosedRepoRootList = closedRepoRootList


    @pyqtSlot()
    def closeNotLastClickedTabs(self):
        self._closeOtherTabs(self.repoTabsWidget.lastClickedTab)

    def onSwitchRepoTaskTab(self, action):
        rw = self.repoTabsWidget.currentWidget()
        if rw:
            rw.switchToNamedTaskTab(str(action.data().toString()))

    @pyqtSlot(QString, bool)
    def openRepo(self, root, reuse, bundle=None):
        """Open tab of the specified repo [unicode]"""
        root = unicode(root)
        if root and not root.startswith('ssh://'):
            if reuse:
                for rw in self._findRepoWidget(root):
                    self.repoTabsWidget.setCurrentWidget(rw)
                    return
            try:
                repoagent = self._repomanager.openRepoAgent(root)
                self.addRepoTab(repoagent, bundle)
            except RepoError, e:
                qtlib.WarningMsgBox(_('Failed to open repository'),
                                    hglib.tounicode(str(e)), parent=self)

    @pyqtSlot(QString)
    def closeRepo(self, root):
        """Close tabs of the specified repo [unicode]"""
        for rw in list(self._findRepoWidget(unicode(root))):
            self.repoTabCloseRequested(self.repoTabsWidget.indexOf(rw))

    @pyqtSlot(QString)
    def openLinkedRepo(self, path):
        uri = unicode(path).split('?', 1)
        path = uri[0]
        rev = None
        if len(uri) > 1:
            rev = hglib.fromunicode(uri[1])
        self.showRepo(path)
        rw = self.repoTabsWidget.currentWidget()
        if rw and rw.repoRootPath() == os.path.normpath(path):
            if rev:
                rw.goto(rev)
            else:
                # assumes that the request comes from commit widget; in this
                # case, the user is going to commit changes to this repo.
                rw.taskTabsWidget.setCurrentIndex(rw.commitTabIndex)

    @pyqtSlot(QString)
    def showRepo(self, root):
        """Activate the repo tab or open it if not available [unicode]"""
        self.openRepo(root, True)

    @pyqtSlot(unicode, QString)
    def setRevsetFilter(self, path, filter):
        for i in xrange(self.repoTabsWidget.count()):
            w = self.repoTabsWidget.widget(i)
            if w.repoRootPath() == path:
                w.setFilter(filter)
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
                self.showRepo(hglib.tounicode(root))
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
        for action in self._actionvisibles['repoopen']:
            action.setVisible(someRepoOpen)

        # Update actions affected by repo open/close/change
        self.updateTaskViewMenu()
        self.updateToolBarActions()
        tw = self.repoTabsWidget
        if ((tw.count() == 0) or
            ((tw.count() == 1) and
             not self.ui.configbool('tortoisehg', 'forcerepotab', False))):
            tw.tabBar().hide()
        else:
            tw.tabBar().show()
        self._updateWindowTitle()

    def _updateWindowTitle(self):
        tw = self.repoTabsWidget
        w = tw.currentWidget()
        if tw.count() == 0:
            self.setWindowTitle(_('TortoiseHg Workbench'))
        elif w.repo.shortname != w.repo.displayname:
            self.setWindowTitle(_('%s - TortoiseHg Workbench - %s') %
                                (w.title(), w.repo.displayname))
        else:
            self.setWindowTitle(_('%s - TortoiseHg Workbench') % w.title())

    def updateToolBarActions(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            self.filtertbaction.setChecked(w.filterBarVisible())

    def updateTaskViewMenu(self):
        'Update task tab menu for current repository'
        if self.repoTabsWidget.count() == 0:
            for a in self.actionGroupTaskView.actions():
                a.setChecked(False)
            if self.actionSelectTaskMQ is not None:
                self.actionSelectTaskMQ.setVisible(False)
            if self.actionSelectTaskPbranch is not None:
                self.actionSelectTaskPbranch.setVisible(False)
        else:
            repoWidget = self.repoTabsWidget.currentWidget()
            exts = repoWidget.repo.extensions()
            if self.actionSelectTaskMQ is not None:
                self.actionSelectTaskMQ.setVisible('mq' in exts)
            if self.actionSelectTaskPbranch is not None:
                self.actionSelectTaskPbranch.setVisible('pbranch' in exts)
            taskIndex = repoWidget.taskTabsWidget.currentIndex()
            for name, idx in repoWidget.namedTabs.iteritems():
                if idx == taskIndex:
                    break
            for action in self.actionGroupTaskView.actions():
                if str(action.data().toString()) == name:
                    action.setChecked(True)

    @pyqtSlot()
    def updateHistoryActions(self):
        'Update back / forward actions'
        rw = self.repoTabsWidget.currentWidget()
        if not rw:
            return
        self.actionBack.setEnabled(rw.canGoBack())
        self.actionForward.setEnabled(rw.canGoForward())

    # might be better to move them to RepoRegistry
    @pyqtSlot(unicode)
    def _updateRepoRegItem(self, root):
        self._updateRepoShortName(root)
        self._updateRepoBaseNode(root)

    @pyqtSlot(unicode)
    def _updateRepoShortName(self, root):
        repo = self._repomanager.repoAgent(root).rawRepo()
        self.reporegistry.setShortName(root, repo.shortname)

    @pyqtSlot(unicode)
    def _updateRepoBaseNode(self, root):
        repo = self._repomanager.repoAgent(root).rawRepo()
        self.reporegistry.setBaseNode(root, repo[0].node())

    @pyqtSlot(int)
    def repoTabCloseRequested(self, index):
        tw = self.repoTabsWidget
        if 0 <= index < tw.count():
            w = tw.widget(index)
            reporoot = w.repoRootPath()
            if w.closeRepoWidget():
                tw.removeTab(index)
                w.deleteLater()
                self._repomanager.releaseRepoAgent(reporoot)
                self.updateMenu()
                self.lastClosedRepoRootList = [reporoot]

    @pyqtSlot()
    def reopenLastClosedTabs(self):
        for n, reporoot in enumerate(self.lastClosedRepoRootList):
            self.progress(_('Reopening tabs'), n,
                _('Reopening repository %s') % reporoot, '',
                len(self.lastClosedRepoRootList))
            if os.path.isdir(reporoot):
                self.showRepo(reporoot)
        self.lastClosedRepoRootList = []
        self.progress(_('Reopening tabs'), None, '', '', None)

    @pyqtSlot()
    def repoTabChanged(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            self.updateHistoryActions()
            self.updateMenu()
            self.log.setCurrentRepoRoot(w.repoRootPath())
            self.reporegistry.setActiveTabRepo(w.repoRootPath())
            self._setupCustomTools(w.repo.ui)
            self._setupUrlCombo(w.repo)
        else:
            self.log.setCurrentRepoRoot(None)
            self.reporegistry.setActiveTabRepo('')
        repo = w and w.repo or None
        self.mqpatches.setrepo(repo)

    #@pyqtSlot(unicode)
    def _updateRepoTabTitle(self, title):
        index = self.repoTabsWidget.indexOf(self.sender())
        self.repoTabsWidget.setTabText(index, title)
        if index == self.repoTabsWidget.currentIndex():
            self._updateWindowTitle()

    #@pyqtSlot(QIcon)
    def _updateRepoTabIcon(self, icon):
        index = self.repoTabsWidget.indexOf(self.sender())
        self.repoTabsWidget.setTabIcon(index, icon)

    def addRepoTab(self, repoagent, bundle):
        '''opens the given repo in a new tab'''
        rw = RepoWidget(repoagent, self, bundle=bundle)
        rw.showMessageSignal.connect(self.showMessage)
        rw.progress.connect(lambda tp, p, i, u, tl:
            self.statusbar.progress(tp, p, i, u, tl, rw.repo.root))
        rw.output.connect(self._appendRepoWidgetOutput)
        rw.makeLogVisible.connect(self.log.setShown)
        rw.revisionSelected.connect(self.updateHistoryActions)
        rw.repoLinkClicked.connect(self.openLinkedRepo)
        rw.taskTabsWidget.currentChanged.connect(self.updateTaskViewMenu)
        rw.toolbarVisibilityChanged.connect(self.updateToolBarActions)

        tw = self.repoTabsWidget
        # We can open new tabs next to the current one or next to the last tab
        openTabAfterCurrent = self.ui.configbool('tortoisehg',
            'opentabsaftercurrent', True)
        if openTabAfterCurrent:
            index = self.repoTabsWidget.insertTab(
                tw.currentIndex()+1, rw, rw.title())
        else:
            index = self.repoTabsWidget.addTab(rw, rw.title())
        tw.setTabToolTip(index, repoagent.rootPath())
        tw.setCurrentIndex(index)
        rw.titleChanged.connect(self._updateRepoTabTitle)
        rw.showIcon.connect(self._updateRepoTabIcon)
        self.reporegistry.addRepo(repoagent.rootPath())

        self.updateMenu()
        return rw

    #@pyqtSlot(QString, QString)
    def _appendRepoWidgetOutput(self, msg, label):
        rw = self.sender()
        assert isinstance(rw, RepoWidget)
        self.log.appendLog(msg, label, rw.repoRootPath())

    def showMessage(self, msg):
        self.statusbar.showMessage(msg)

    @pyqtSlot(QString, object, QString, QString, object)
    def progress(self, topic, pos, item, unit, total=100, root=None):
        if self.progressDialog:
            if pos is None:
                self.progressDialog.close()
                return
            if total is None:
                total = 100
            pos = round(pos)
            total = round(total)
            self.progressDialog.setWindowTitle('TortoiseHg - %s' % topic)
            self.progressDialog.setLabelText('%s (%d / %d)' % (item, pos, total))
            self.progressDialog.setMaximum(total)
            self.progressDialog.show()
            self.progressDialog.setValue(pos)
        else:
            self.statusbar.progress(topic, pos, item, unit, total, root)

    def setHistoryColumns(self, *args):
        """Display the column selection dialog"""
        w = self.repoTabsWidget.currentWidget()
        dlg = ColumnSelectDialog('workbench', _('Workbench'),
                                 w and w.repoview.model() or None)
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

    def _repofwd(self, name, params=[], namedparams={}):
        """Return function to forward action to the current repo tab"""
        def forwarder():
            w = self.repoTabsWidget.currentWidget()
            if w:
                getattr(w, name)(*params, **namedparams)

        return forwarder

    # no @pyqtSlot(); as of PyQt 4.9.3, it makes self.sender() wrong through
    # the following path: reload -> titleChanged -> _updateRepoTabTitle,
    # if _updateRepoTabTitle is not decorated as @pyqtSlot.
    def refresh(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            getattr(w, 'reload')()
            self._setupUrlCombo(w.repo)

    @pyqtSlot(QAction)
    def _runSyncAction(self, action):
        w = self.repoTabsWidget.currentWidget()
        if w:
            op = str(action.data().toString())
            w.setSyncUrl(self._syncUrlFor(op) or '')
            getattr(w, op)()

    def serve(self):
        self._dialogs.open(Workbench._createServeDialog)

    def _createServeDialog(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            return serve.run(w.repo.ui, root=w.repo.root)
        else:
            return serve.run(self.ui)

    def loadall(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.repoview.model().loadall()

    def gotorev(self):
        rev, ok = qtlib.getTextInput(self,
                                     _("Goto revision"),
                                     _("Enter revision identifier"))
        w = self.repoTabsWidget.currentWidget()
        if ok and w:
            w.repoview.goto(rev)

    def newWorkbench(self):
        from tortoisehg.hgqt.run import portable_start_fork
        portable_start_fork(['--new'])

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
            self.openRepo(hglib.tounicode(path), False)

    def cloneRepository(self):
        """ Run clone dialog """
        # it might be better to reuse existing CloneDialog
        dlg = self._dialogs.openNew(Workbench._createCloneDialog)
        repoWidget = self.repoTabsWidget.currentWidget()
        if repoWidget:
            uroot = repoWidget.repoRootPath()
            dlg.setSource(uroot)
            dlg.setDestination(uroot + '-clone')

    def _createCloneDialog(self):
        from tortoisehg.hgqt.clone import CloneDialog
        dlg = CloneDialog(parent=self)
        dlg.clonedRepository.connect(self.showRepo)
        return dlg

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
        self.openRepo(path, False)

    def _findRepoWidget(self, root):
        """Iterates RepoWidget for the specified root"""
        def normpathandcase(path):
            return os.path.normcase(os.path.normpath(path))
        normroot = normpathandcase(root)
        tw = self.repoTabsWidget
        for idx in range(tw.count()):
            rw = tw.widget(idx)
            if normpathandcase(rw.repoRootPath()) == normroot:
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

    def onHelpExplorer(self, *args):
        """ Display online help for shell extension """
        qtlib.openhelpcontents('explorer.html')

    def onReadme(self, *args):
        """Display the README file or URL for the current repo, or the global
        README if no repo is open"""
        readme = None
        def getCurrentReadme(repo):
            """
            Get the README file that is configured for the current repo.

            README files can be set in 3 ways, which are checked in the
            following order of decreasing priority:
            - From the tortoisehg.readme key on the current repo's configuration
              file
            - An existing "README" file found on the repository root
                * Valid README files are those called README and whose extension
                  is one of the following:
                    ['', '.txt', '.html', '.pdf', '.doc', '.docx', '.ppt', '.pptx',
                     '.markdown', '.textile', '.rdoc', '.org', '.creole',
                     '.mediawiki','.rst', '.asciidoc', '.pod']
                * Note that the match is CASE INSENSITIVE on ALL OSs.
            - From the tortoisehg.readme key on the user's global configuration file
            """
            readme = None
            if repo:
                # Try to get the README configured for the repo of the current tab
                readmeglobal = self.ui.config('tortoisehg', 'readme', None)
                if readmeglobal:
                    # Note that repo.ui.config() falls back to the self.ui.config()
                    # if the key is not set on the current repo's configuration file
                    readme = repo.ui.config('tortoisehg', 'readme', None)
                    if readmeglobal != readme:
                        # The readme is set on the current repo configuration file
                        return readme

                # Otherwise try to see if there is a file at the root of the
                # repository that matches any of the valid README file names
                # (in a non case-sensitive way)
                # Note that we try to match the valid README names in order
                validreadmes = ['readme.txt', 'read.me', 'readme.html',
                                'readme.pdf', 'readme.doc', 'readme.docx',
                                'readme.ppt', 'readme.pptx',
                                'readme.md', 'readme.markdown', 'readme.mkdn',
                                'readme.rst', 'readme.textile', 'readme.rdoc',
                                'readme.asciidoc', 'readme.org', 'readme.creole',
                                'readme.mediawiki', 'readme.pod', 'readme']

                readmefiles = [filename for filename in os.listdir(repo.root)
                               if filename.lower().startswith('read')]
                for validname in validreadmes:
                    for filename in readmefiles:
                        if filename.lower() == validname:
                            return repo.wjoin(filename)

            # Otherwise try use the global setting (or None if readme is just
            # not configured)
            return readmeglobal

        w = self.repoTabsWidget.currentWidget()
        if w:
            # Try to get the help doc from the current repo tap
            readme = getCurrentReadme(w.repo)

        if readme:
            qtlib.openlocalurl(os.path.expandvars(os.path.expandvars(readme)))
        else:
            qtlib.WarningMsgBox(_("README not configured"),
                _("A README file is not configured for the current repository.<p>"
                "To configure a README file for a repository, "
                "open the repository settings file, add a '<i>readme</i>' "
                "key to the '<i>tortoisehg</i>' section, and set it "
                "to the filename or URL of your repository's README file."))

    def storeSettings(self):
        s = QSettings()
        wb = "Workbench/"
        s.setValue(wb + 'geometry', self.saveGeometry())
        s.setValue(wb + 'windowState', self.saveState())
        s.setValue(wb + 'saveRepos', self.actionSaveRepos.isChecked())
        repostosave = []
        lastactiverepo = ''
        if self.actionSaveRepos.isChecked():
            tw = self.repoTabsWidget
            for idx in range(tw.count()):
                rw = tw.widget(idx)
                repostosave.append(rw.repoRootPath())
            cw = tw.currentWidget()
            if cw is not None:
                lastactiverepo = cw.repoRootPath()
        s.setValue(wb + 'lastactiverepo', lastactiverepo)
        s.setValue(wb + 'openrepos', (',').join(repostosave))

    def restoreSettings(self):
        s = QSettings()
        wb = "Workbench/"
        self.restoreGeometry(s.value(wb + 'geometry').toByteArray())
        self.restoreState(s.value(wb + 'windowState').toByteArray())

        save = s.value(wb + 'saveRepos').toBool()
        self.actionSaveRepos.setChecked(save)

        # Reload the all the repos that were open on the last session.
        # This may be a lengthy operation, which happens before the Workbench
        # GUI is open. We use a progress dialog to let the user know that the
        # workbench is being loaded
        openreposvalue = unicode(s.value(wb + 'openrepos').toString())
        if openreposvalue:
            openrepos = openreposvalue.split(',')
        else:
            openrepos = []
        for n, upath in enumerate(openrepos):
            self.progress(_('Reopening tabs'), n,
                          _('Reopening repository %s') % upath, '',
                          len(openrepos))
            QCoreApplication.processEvents()
            self.openRepo(upath, False)
            QCoreApplication.processEvents()
        self.progress(_('Reopening tabs'), None, '', '', None)

        # Activate the tab that was last active on the last session (if any)
        # Note that if a "root" has been passed to the "thg" command,
        # this will have no effect
        lastactiverepo = s.value(wb + 'lastactiverepo').toString()
        if lastactiverepo:
            self.openRepo(lastactiverepo, True)

        # Clear the lastactiverepo and the openrepos list once the workbench state
        # has been reload, so that opening additional workbench windows does not
        # reopen these repos again
        s.setValue(wb + 'openrepos', '')
        s.setValue(wb + 'lastactiverepo', '')

    def goto(self, root, rev):
        for rw in self._findRepoWidget(hglib.tounicode(root)):
            rw.goto(rev)

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

    @pyqtSlot()
    def closeCurrentRepoTab(self):
        """close the current repo tab"""
        self.repoTabCloseRequested(self.repoTabsWidget.currentIndex())

    def explore(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            qtlib.openlocalurl(w.repo.root)

    def terminal(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            qtlib.openshell(w.repo.root, w.repo.displayname, w.repo.ui)

    def editSettings(self):
        tw = self.repoTabsWidget
        w = tw.currentWidget()
        twrepo = (w and w.repo.root or '')
        sd = SettingsDialog(configrepo=False,
                            parent=self, root=twrepo)
        sd.exec_()

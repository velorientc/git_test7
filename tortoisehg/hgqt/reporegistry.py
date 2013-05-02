# reporegistry.py - registry for a user's repositories
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os

from mercurial import commands, hg, ui, util

from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, repotreemodel, clone, settings

from PyQt4.QtCore import *
from PyQt4.QtGui import *

def settingsfilename():
    """Return path to thg-reporegistry.xml as unicode"""
    s = QSettings()
    dir = os.path.dirname(unicode(s.fileName()))
    return dir + '/' + 'thg-reporegistry.xml'


class RepoTreeView(QTreeView):
    showMessage = pyqtSignal(QString)
    menuRequested = pyqtSignal(object, object)
    openRepo = pyqtSignal(QString, bool)
    dropAccepted = pyqtSignal()
    updateSettingsFile = pyqtSignal()

    def __init__(self, parent):
        QTreeView.__init__(self, parent, allColumnsShowFocus=True)
        self.selitem = None
        self.msg = ''

        self.setHeaderHidden(True)
        self.setExpandsOnDoubleClick(False)
        self.setMouseTracking(True)

        # enable drag and drop
        # (see http://doc.qt.nokia.com/4.6/model-view-dnd.html)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setAutoScroll(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        if PYQT_VERSION >= 0x40700:
            self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.setEditTriggers(QAbstractItemView.DoubleClicked
                             | QAbstractItemView.EditKeyPressed)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        QShortcut('Return', self, self.showFirstTabOrOpen).setContext(
                  Qt.WidgetShortcut)
        QShortcut('Enter', self, self.showFirstTabOrOpen).setContext(
                  Qt.WidgetShortcut)
        QShortcut('Delete', self, self.removeSelected).setContext(
                  Qt.WidgetShortcut)

    def contextMenuEvent(self, event):
        if not self.selitem:
            return
        self.menuRequested.emit(event.globalPos(), self.selitem)

    def dragEnterEvent(self, event):
        if event.source() is self:
            # Use the default event handler for internal dragging
            super(RepoTreeView, self).dragEnterEvent(event)
            return

        d = event.mimeData()
        for u in d.urls():
            root = paths.find_root(hglib.fromunicode(u.toLocalFile()))
            if root:
                event.setDropAction(Qt.LinkAction)
                event.accept()
                self.setState(QAbstractItemView.DraggingState)
                break

    def dropLocation(self, event):
        index = self.indexAt(event.pos())

        # Determine where the item was dropped.
        target = index.internalPointer()
        if not target.isRepo():
            group = index
            row = -1
        else:
            indicator = self.dropIndicatorPosition()
            group = index.parent()
            row = index.row()
            if indicator == QAbstractItemView.BelowItem:
                row = index.row() + 1

        return index, group, row

    def startDrag(self, supportedActions):
        indexes = self.selectedIndexes()
        # Make sure that all selected items are of the same type
        if len(indexes) == 0:
            # Nothing to drag!
            return

        # Make sure that all items that we are dragging are of the same type
        firstItem = indexes[0].internalPointer()
        selectionInstanceType = type(firstItem)
        for idx in indexes[1:]:
            if selectionInstanceType != type(idx.internalPointer()):
                # Cannot drag mixed type items
                return

        # Each item type may support different drag & drop actions
        # For instance, suprepo items support Copy actions only
        supportedActions = firstItem.getSupportedDragDropActions()

        super(RepoTreeView, self).startDrag(supportedActions)

    def dropEvent(self, event):
        data = event.mimeData()
        index, group, row = self.dropLocation(event)

        if index:
            m = self.model()
            if event.source() is self:
                # Event is an internal move, so pass it to the model
                col = 0
                if m.dropMimeData(data, event.dropAction(), row, col, group):
                    event.accept()
                    self.dropAccepted.emit()
            else:
                # Event is a drop of an external repo
                accept = False
                for u in data.urls():
                    uroot = paths.find_root(unicode(u.toLocalFile()))
                    if uroot and not m.isKnownRepoRoot(uroot, standalone=True):
                        repoindex = m.addRepo(uroot, row, group)
                        m.loadSubrepos(repoindex)
                        accept = True
                if accept:
                    event.setDropAction(Qt.LinkAction)
                    event.accept()
                    self.dropAccepted.emit()
        self.setAutoScroll(False)
        self.setState(QAbstractItemView.NoState)
        self.viewport().update()
        self.setAutoScroll(True)

    def mouseMoveEvent(self, event):
        self.msg  = ''
        pos = event.pos()
        idx = self.indexAt(pos)
        if idx.isValid():
            item = idx.internalPointer()
            self.msg  = item.details()
        self.showMessage.emit(self.msg)

        if event.buttons() == Qt.NoButton:
            # Bail out early to avoid tripping over this bug:
            # http://bugreports.qt.nokia.com/browse/QTBUG-10180
            return
        super(RepoTreeView, self).mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self.msg != '':
            self.showMessage.emit('')

    def mouseDoubleClickEvent(self, event):
        if self.selitem and self.selitem.internalPointer().isRepo():
            # We can only open mercurial repositories and subrepositories
            repotype = self.selitem.internalPointer().repotype()
            if repotype == 'hg':
                self.showFirstTabOrOpen()
            else:
                qtlib.WarningMsgBox(
                    _('Unsupported repository type (%s)') % repotype,
                    _('Cannot open non Mercurial repositories or subrepositories'),
                    parent=self)
        else:
            # a double-click on non-repo rows opens an editor
            super(RepoTreeView, self).mouseDoubleClickEvent(event)

    def selectionChanged(self, selected, deselected):
        selection = self.selectedIndexes()
        if len(selection) == 0:
            self.selitem = None
        else:
            self.selitem = selection[0]

    def sizeHint(self):
        size = super(RepoTreeView, self).sizeHint()
        size.setWidth(QFontMetrics(self.font()).width('M') * 15)
        return size

    def showFirstTabOrOpen(self):
        'Enter or double click events, show existing or open a new repowidget'
        if self.selitem and self.selitem.internalPointer().isRepo():
            root = self.selitem.internalPointer().rootpath()
            self.openRepo.emit(hglib.tounicode(root), True)

    def removeSelected(self):
        'remove selected repository'
        s = self.selitem
        if not s:
            return
        item = s.internalPointer()
        if 'remove' not in item.menulist():  # check capability
            return
        if not item.okToDelete():
            labels = [(QMessageBox.Yes, _('&Delete')),
                      (QMessageBox.No, _('Cancel'))]
            if not qtlib.QuestionMsgBox(_('Confirm Delete'),
                                    _("Delete Group '%s' and all its entries?")%
                                    item.name, labels=labels, parent=self):
                return
        m = self.model()
        row = s.row()
        parent = s.parent()
        m.removeRows(row, 1, parent)
        self.selectionChanged(None, None)
        self.updateSettingsFile.emit()

class RepoRegistryView(QDockWidget):

    showMessage = pyqtSignal(QString)
    openRepo = pyqtSignal(QString, bool)
    removeRepo = pyqtSignal(QString)
    progressReceived = pyqtSignal(QString, object, QString, QString, object)

    def __init__(self, parent):
        QDockWidget.__init__(self, parent)

        self.watcher = None
        self._setupSettingActions()

        self.setFeatures(QDockWidget.DockWidgetClosable |
                         QDockWidget.DockWidgetMovable  |
                         QDockWidget.DockWidgetFloatable)
        self.setWindowTitle(_('Repository Registry'))

        mainframe = QFrame()
        mainframe.setLayout(QVBoxLayout())
        self.setWidget(mainframe)
        mainframe.layout().setContentsMargins(0, 0, 0, 0)

        self.contextmenu = QMenu(self)
        self.tview = tv = RepoTreeView(self)
        mainframe.layout().addWidget(tv)

        tv.setIndentation(10)
        tv.setFirstColumnSpanned(0, QModelIndex(), True)
        tv.setColumnHidden(1, True)

        tv.showMessage.connect(self.showMessage)
        tv.menuRequested.connect(self.onMenuRequest)
        tv.openRepo.connect(self.openRepo)
        tv.updateSettingsFile.connect(self.updateSettingsFile)
        tv.dropAccepted.connect(self.dropAccepted)

        self.createActions()
        self._loadSettings()
        self._updateSettingActions()

        sfile = settingsfilename()
        model = repotreemodel.RepoTreeModel(sfile, self,
            showShortPaths=self._isSettingEnabled('showShortPaths'))
        tv.setModel(model)

        # Setup a file system watcher to update the reporegistry
        # anytime it is modified by another thg instance
        # Note that we must make sure that the settings file exists before
        # setting thefile watcher
        if not os.path.exists(sfile):
            if not os.path.exists(os.path.dirname(sfile)):
                os.makedirs(os.path.dirname(sfile))
            tv.model().write(sfile)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.addPath(sfile)
        self._reloadModelTimer = QTimer(self, interval=2000, singleShot=True)
        self._reloadModelTimer.timeout.connect(self.reloadModel)
        self.watcher.fileChanged.connect(self._reloadModelTimer.start)

        QTimer.singleShot(0, self._initView)

    @pyqtSlot()
    def _initView(self):
        self.expand()
        self._updateColumnVisibility()
        if self._isSettingEnabled('showSubrepos'):
            self._scanAllRepos()

    def _loadSettings(self):
        defaultmap = {'showPaths': False, 'showSubrepos': False,
                      'showNetworkSubrepos': False, 'showShortPaths': True}
        s = QSettings()
        s.beginGroup('Workbench')  # for compatibility with old release
        for key, action in self._settingactions.iteritems():
            action.setChecked(s.value(key, defaultmap[key]).toBool())
        s.endGroup()

    def _saveSettings(self):
        s = QSettings()
        s.beginGroup('Workbench')  # for compatibility with old release
        for key, action in self._settingactions.iteritems():
            s.setValue(key, action.isChecked())
        s.endGroup()

    def _setupSettingActions(self):
        settingtable = [
            ('showPaths', _('Show &Paths'), self._updateColumnVisibility),
            ('showShortPaths', _('Show S&hort Paths'), self._updateCommonPath),
            ('showSubrepos', _('&Scan Repositories at Startup'), None),
            ('showNetworkSubrepos', _('Scan &Remote Repositories'), None),
            ]
        self._settingactions = {}
        for i, (key, text, slot) in enumerate(settingtable):
            a = QAction(text, self, checkable=True)
            a.setData(i)  # sort key
            if slot:
                a.triggered.connect(slot)
            a.triggered.connect(self._updateSettingActions)
            self._settingactions[key] = a

    @pyqtSlot()
    def _updateSettingActions(self):
        ax = self._settingactions
        ax['showNetworkSubrepos'].setEnabled(ax['showSubrepos'].isChecked())
        ax['showShortPaths'].setEnabled(ax['showPaths'].isChecked())

    def settingActions(self):
        return sorted(self._settingactions.itervalues(),
                      key=lambda a: a.data().toInt())

    def _isSettingEnabled(self, key):
        return self._settingactions[key].isChecked()

    @pyqtSlot()
    def _updateCommonPath(self):
        show = self._isSettingEnabled('showShortPaths')
        self.tview.model().updateCommonPaths(show)
        # FIXME: access violation; should be done by model
        self.tview.dataChanged(QModelIndex(), QModelIndex())

    def updateSettingsFile(self):
        # If there is a settings watcher, we must briefly stop watching the
        # settings file while we save it, otherwise we'll get the update signal
        # that we do not want
        sfile = settingsfilename()
        if self.watcher:
            self.watcher.removePath(sfile)
        self.tview.model().write(sfile)
        if self.watcher:
            self.watcher.addPath(sfile)

        # Whenver the settings file must be updated, it is also time to ensure
        # that the commonPaths are up to date
        QTimer.singleShot(0, self.tview.model().updateCommonPaths)

    @pyqtSlot()
    def dropAccepted(self):
        # Whenever a drag and drop operation is completed, update the settings
        # file
        QTimer.singleShot(0, self.updateSettingsFile)

    @pyqtSlot()
    def reloadModel(self):
        oldmodel = self.tview.model()
        activeroot = oldmodel.repoRoot(oldmodel.activeRepoIndex())
        newmodel = repotreemodel.RepoTreeModel(settingsfilename(), self,
            self._isSettingEnabled('showShortPaths'))
        self.tview.setModel(newmodel)
        oldmodel.deleteLater()
        if self._isSettingEnabled('showSubrepos'):
            self._scanAllRepos()
        self.expand()
        if activeroot:
            self.setActiveTabRepo(activeroot)
        self._reloadModelTimer.stop()

    def expand(self):
        self.tview.expandToDepth(0)

    def addRepo(self, uroot):
        """Add repo if not exists; called when the workbench has opened it"""
        m = self.tview.model()
        knownindex = m.indexFromRepoRoot(uroot)
        if knownindex.isValid():
            self._scanAddedRepo(knownindex)  # just scan stale subrepos
        else:
            index = m.addRepo(uroot)
            self._scanAddedRepo(index)
            self.updateSettingsFile()

    def setActiveTabRepo(self, root):
        """"The selected tab has changed on the workbench"""
        m = self.tview.model()
        index = m.indexFromRepoRoot(root)
        m.setActiveRepo(index)
        self.tview.scrollTo(index)

    @pyqtSlot()
    def _updateColumnVisibility(self):
        show = self._isSettingEnabled('showPaths')
        self.tview.setColumnHidden(1, not show)
        self.tview.setHeaderHidden(not show)
        if show:
            self.tview.resizeColumnToContents(0)
            self.tview.resizeColumnToContents(1)

    def close(self):
        # We must stop monitoring the settings file and then we can save it
        sfile = settingsfilename()
        self.watcher.removePath(sfile)
        self.tview.model().write(sfile)
        self._saveSettings()

    def _action_defs(self):
        a = [("reloadRegistry", _("&Refresh Repository List"), 'view-refresh',
                _("Refresh the Repository Registry list"), self.reloadModel),
             ("open", _("&Open"), 'thg-repository-open',
                _("Open the repository in a new tab"), self.open),
             ("openAll", _("&Open All"), 'thg-repository-open',
                _("Open all repositories in new tabs"), self.openAll),
             ("newGroup", _("New &Group"), 'new-group',
                _("Create a new group"), self.newGroup),
             ("rename", _("Re&name"), None,
                _("Rename the entry"), self.startRename),
             ("settings", _("Settin&gs"), 'settings_user',
                _("View the repository's settings"), self.startSettings),
             ("remove", _("Re&move from Registry"), 'menudelete',
                _("Remove the node and all its subnodes."
                  " Repositories are not deleted from disk."),
                  self.removeSelected),
             ("clone", _("Clon&e..."), 'hg-clone',
                _("Clone Repository"), self.cloneRepo),
             ("explore", _("E&xplore"), 'system-file-manager',
                _("Open the repository in a file browser"), self.explore),
             ("terminal", _("&Terminal"), 'utilities-terminal',
                _("Open a shell terminal in the repository root"), self.terminal),
             ("add", _("&Add Repository..."), 'hg',
                _("Add a repository to this group"), self.addNewRepo),
             ("addsubrepo", _("A&dd Subrepository..."), 'thg-add-subrepo',
                _("Convert an existing repository into a subrepository"),
                self.addSubrepo),
             ("copypath", _("Copy &Path"), '',
                _("Copy the root path of the repository to the clipboard"),
                self.copyPath),
             ("sortbyname", _("Sort by &Name"), '',
                _("Sort the group by short name"), self.sortbyname),
             ("sortbypath", _("Sort by &Path"), '',
                _("Sort the group by full path"), self.sortbypath),
             ("sortbyhgsub", _("&Sort by .hgsub"), '',
                _("Order the subrepos as in .hgsub"), self.sortbyhgsub),
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

    def onMenuRequest(self, point, selitem):
        menulist = selitem.internalPointer().menulist()
        if not menulist:
            return
        self.addtomenu(self.contextmenu, menulist)
        self.selitem = selitem
        self.contextmenu.exec_(point)

    def addtomenu(self, menu, actlist):
        menu.clear()
        for act in actlist:
            if isinstance(act, basestring) and act in self._actions:
                menu.addAction(self._actions[act])
            elif isinstance(act, tuple) and len(act) == 2:
                submenu = menu.addMenu(act[0])
                self.addtomenu(submenu, act[1])
            else:
                menu.addSeparator()

    #
    ## Menu action handlers
    #

    def cloneRepo(self):
        root = self.selitem.internalPointer().rootpath()
        d = clone.CloneDialog(args=[root, root + '-clone'], parent=self)
        d.finished.connect(d.deleteLater)
        d.clonedRepository.connect(self._openClone)
        d.show()

    def explore(self):
        root = self.selitem.internalPointer().rootpath()
        qtlib.openlocalurl(root)

    def terminal(self):
        repoitem = self.selitem.internalPointer()
        qtlib.openshell(repoitem.rootpath(), repoitem.shortname())

    def addNewRepo(self):
        'menu action handler for adding a new repository'
        caption = _('Select repository directory to add')
        FD = QFileDialog
        path = FD.getExistingDirectory(caption=caption,
                                       options=FD.ShowDirsOnly | FD.ReadOnly)
        if path:
            m = self.tview.model()
            uroot = paths.find_root(unicode(path))
            if uroot and not m.isKnownRepoRoot(uroot, standalone=True):
                index = m.addRepo(uroot, parent=self.selitem)
                self._scanAddedRepo(index)

    def addSubrepo(self):
        'menu action handler for adding a new subrepository'
        root = hglib.tounicode(self.selitem.internalPointer().rootpath())
        caption = _('Select an existing repository to add as a subrepo')
        FD = QFileDialog
        path = unicode(FD.getExistingDirectory(caption=caption,
            directory=root, options=FD.ShowDirsOnly | FD.ReadOnly))
        if path:
            path = os.path.normpath(path)
            sroot = paths.find_root(path)

            root = os.path.normcase(os.path.normpath(root))

            if not sroot:
                qtlib.WarningMsgBox(_('Cannot add subrepository'),
                    _('%s is not a valid repository') % path,
                    parent=self)
                return
            elif not os.path.isdir(sroot):
                qtlib.WarningMsgBox(_('Cannot add subrepository'),
                    _('"%s" is not a folder') % sroot,
                    parent=self)
                return
            elif os.path.normcase(sroot) == root:
                qtlib.WarningMsgBox(_('Cannot add subrepository'),
                    _('A repository cannot be added as a subrepo of itself'),
                    parent=self)
                return
            elif root != paths.find_root(os.path.dirname(os.path.normcase(path))):
                qtlib.WarningMsgBox(_('Cannot add subrepository'),
                    _('The selected folder:<br><br>%s<br><br>'
                    'is not inside the target repository.<br><br>'
                    'This may be allowed but is greatly discouraged.<br>'
                    'If you want to add a non trivial subrepository mapping '
                    'you must manually edit the <i>.hgsub</i> file') % root, parent=self)
                return
            else:
                # The selected path is the root of a repository that is inside
                # the selected repository

                # Use forward slashes for relative subrepo root paths
                srelroot = sroot[len(root)+1:]
                srelroot = util.pconvert(srelroot)

                # Is is already on the selected repository substate list?
                try:
                    repo = hg.repository(ui.ui(), hglib.fromunicode(root))
                except:
                    qtlib.WarningMsgBox(_('Cannot open repository'),
                        _('The selected repository:<br><br>%s<br><br>'
                        'cannot be open!') % root, parent=self)
                    return

                if hglib.fromunicode(srelroot) in repo['.'].substate:
                    qtlib.WarningMsgBox(_('Subrepository already exists'),
                        _('The selected repository:<br><br>%s<br><br>'
                        'is already a subrepository of:<br><br>%s<br><br>'
                        'as: "%s"') % (sroot, root, srelroot), parent=self)
                    return
                else:
                    # Already a subrepo!

                    # Read the current .hgsub file contents
                    lines = []
                    hasHgsub = os.path.exists(repo.wjoin('.hgsub'))
                    if hasHgsub:
                        try:
                            fsub = repo.wopener('.hgsub', 'r')
                            lines = fsub.readlines()
                            fsub.close()
                        except:
                            qtlib.WarningMsgBox(
                                _('Failed to add subrepository'),
                                _('Cannot open the .hgsub file in:<br><br>%s') \
                                % root, parent=self)
                            return

                    # Make sure that the selected subrepo (or one of its
                    # subrepos!) is not already on the .hgsub file
                    linesep = ''
                    for line in lines:
                        line = hglib.tounicode(line)
                        spath = line.split("=")[0].strip()
                        if not spath:
                            continue
                        if not linesep:
                            linesep = hglib.getLineSeparator(line)
                        spath = util.pconvert(spath)
                        if line.startswith(srelroot):
                            qtlib.WarningMsgBox(
                                _('Failed to add repository'),
                                _('The .hgsub file already contains the '
                                'line:<br><br>%s') % line, parent=self)
                            return
                    if not linesep:
                        linesep = os.linesep

                    # Append the new subrepo to the end of the .hgsub file
                    lines.append(hglib.fromunicode('%s = %s'
                                                   % (srelroot, srelroot)))
                    lines = [line.strip(linesep) for line in lines]

                    # and update the .hgsub file
                    try:
                        fsub = repo.wopener('.hgsub', 'w')
                        fsub.write(linesep.join(lines) + linesep)
                        fsub.close()
                        if not hasHgsub:
                            commands.add(ui.ui(), repo, repo.wjoin('.hgsub'))
                        qtlib.InfoMsgBox(
                            _('Subrepo added to .hgsub file'),
                            _('The selected subrepo:<br><br><i>%s</i><br><br>'
                            'has been added to the .hgsub file of the repository:<br><br><i>%s</i><br><br>'
                            'Remember that in order to finish adding the '
                            'subrepo <i>you must still <u>commit</u></i> the '
                            'changes to the .hgsub file in order to confirm '
                            'the addition of the subrepo.') \
                            % (srelroot, root), parent=self)
                    except:
                        qtlib.WarningMsgBox(
                            _('Failed to add repository'),
                            _('Cannot update the .hgsub file in:<br><br>%s') \
                            % root, parent=self)
                return

    def startSettings(self):
        root = self.selitem.internalPointer().rootpath()
        sd = settings.SettingsDialog(configrepo=True, focus='web.name',
                                     parent=self, root=root)
        sd.finished.connect(sd.deleteLater)
        sd.exec_()

    def openAll(self):
        for root in self.selitem.internalPointer().childRoots():
            self.openRepo.emit(hglib.tounicode(root), False)

    @pyqtSlot(unicode, unicode)
    def _openClone(self, root, sourceroot):
        m = self.tview.model()
        src = m.indexFromRepoRoot(sourceroot, standalone=True)
        if src.isValid() and not m.isKnownRepoRoot(root):
            index = m.addRepo(root, parent=src.parent())
            self._scanAddedRepo(index)
        self.open(root)

    def open(self, root=None):
        'open context menu action, open repowidget unconditionally'
        if not root:
            root = self.selitem.internalPointer().rootpath()
            repotype = self.selitem.internalPointer().repotype()
        else:
            root = hglib.fromunicode(root)
            if os.path.exists(os.path.join(root, '.hg')):
                repotype = 'hg'
            else:
                repotype = 'unknown'
        if repotype == 'hg':
            self.openRepo.emit(hglib.tounicode(root), False)
        else:
            qtlib.WarningMsgBox(
                _('Unsupported repository type (%s)') % repotype,
                _('Cannot open non Mercurial repositories or subrepositories'),
                parent=self)

    def copyPath(self):
        clip = QApplication.clipboard()
        clip.setText(hglib.tounicode(self.selitem.internalPointer().rootpath()))

    def startRename(self):
        self.tview.edit(self.tview.currentIndex())

    def newGroup(self):
        self.tview.model().addGroup(_('New Group'))

    def removeSelected(self):
        ip = self.selitem.internalPointer()
        if ip.isRepo():
            root = ip.rootpath()
        else:
            root = None

        self.tview.removeSelected()

        if root is not None:
            self.removeRepo.emit(hglib.tounicode(root))

    def sortbyname(self):
        childs = self.selitem.internalPointer().childs
        self.tview.model().sortchilds(childs, lambda x: x.shortname().lower())

    def sortbypath(self):
        childs = self.selitem.internalPointer().childs
        self.tview.model().sortchilds(childs, lambda x: util.normpath(x.rootpath()))

    def sortbyhgsub(self):
        ip = self.selitem.internalPointer()
        repo = hg.repository(ui.ui(), ip.rootpath())
        ctx = repo['.']
        wfile = '.hgsub'
        if wfile not in ctx:
            return self.sortbypath()
        data = ctx[wfile].data().strip()
        data = data.split('\n')
        getsubpath = lambda x: x.split('=')[0].strip()
        abspath = lambda x: util.normpath(repo.wjoin(x))
        hgsuborder = [abspath(getsubpath(x)) for x in data]
        def keyfunc(x):
            try:
                return hgsuborder.index(util.normpath(x.rootpath()))
            except:
                # If an item is not found, place it at the top
                return 0
        self.tview.model().sortchilds(ip.childs, keyfunc)

    @pyqtSlot(QString, QString)
    def shortNameChanged(self, uroot, uname):
        it = self.tview.model().getRepoItem(hglib.fromunicode(uroot))
        if it:
            it.setShortName(uname)
            self.tview.model().layoutChanged.emit()

    @pyqtSlot(QString, object)
    def baseNodeChanged(self, uroot, basenode):
        it = self.tview.model().getRepoItem(hglib.fromunicode(uroot))
        if it:
            it.setBaseNode(basenode)

    def _scanAddedRepo(self, index):
        m = self.tview.model()
        invalidpaths = m.loadSubrepos(index)
        if not invalidpaths:
            return

        root = m.repoRoot(index)
        if root in invalidpaths:
            qtlib.WarningMsgBox(_('Could not get subrepository list'),
                _('It was not possible to get the subrepository list for '
                  'the repository in:<br><br><i>%s</i>') % root, parent=self)
        else:
            qtlib.WarningMsgBox(_('Could not open some subrepositories'),
                _('It was not possible to fully load the subrepository '
                  'list for the repository in:<br><br><i>%s</i><br><br>'
                  'The following subrepositories may be missing, broken or '
                  'on an inconsistent state and cannot be accessed:'
                  '<br><br><i>%s</i>')
                % (root, "<br>".join(invalidpaths)), parent=self)

    @pyqtSlot(QString)
    def scanRepo(self, uroot):
        m = self.tview.model()
        index = m.indexFromRepoRoot(uroot)
        if index.isValid():
            m.loadSubrepos(index)

    def _scanAllRepos(self):
        m = self.tview.model()
        indexes = m.indexesOfRepoItems(standalone=True)
        if not self._isSettingEnabled('showNetworkSubrepos'):
            indexes = [idx for idx in indexes
                       if not paths.netdrive_status(m.repoRoot(idx))]

        topic = _('Updating repository registry')
        for n, idx in enumerate(indexes):
            self.progressReceived.emit(
                topic, n, _('Loading repository %s') % m.repoRoot(idx), '',
                len(indexes))
            m.loadSubrepos(idx)
        self.progressReceived.emit(
            topic, None, _('Repository Registry updated'), '', None)

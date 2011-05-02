# reporegistry.py - registry for a user's repositories
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os

from mercurial import error

from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, repotreemodel, clone, settings

from PyQt4.QtCore import *
from PyQt4.QtGui import *

import qtlib


def settingsfilename():
    """Return path to thg-reporegistry.xml as unicode"""
    s = QSettings()
    dir = os.path.dirname(unicode(s.fileName()))
    return dir + '/' + 'thg-reporegistry.xml'


class RepoTreeView(QTreeView):
    showMessage = pyqtSignal(QString)
    menuRequested = pyqtSignal(object, object)
    openRepo = pyqtSignal(QString, bool)

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
        self.setDropIndicatorShown(True)
        self.setEditTriggers(QAbstractItemView.DoubleClicked)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        QShortcut('Return', self, self.showFirstTabOrOpen).setContext(
                  Qt.WidgetShortcut)
        QShortcut('Enter', self, self.showFirstTabOrOpen).setContext(
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
        # Depth in tree: 1 = group, 2 = repo, and (eventually) 3+ = subrepo
        depth = self.model().depth(index)
        if depth == 1:
            group = index
            row = -1
        elif depth == 2:
            indicator = self.dropIndicatorPosition()
            group = index.parent()
            row = index.row()
            if indicator == QAbstractItemView.BelowItem:
                row = index.row() + 1
        else:
            index = group = row = None

        return index, group, row

    def dropEvent(self, event):
        data = event.mimeData()
        index, group, row = self.dropLocation(event)

        if index:
            if event.source() is self:
                # Event is an internal move, so pass it to the model
                col = 0
                drop = self.model().dropMimeData(data, Qt.MoveAction, row,
                                                 col, group)
                if drop:
                    event.setDropAction(Qt.MoveAction)
                    event.accept()
            else:
                # Event is a drop of an external repo
                accept = False
                for u in data.urls():
                    root = paths.find_root(hglib.fromunicode(u.toLocalFile()))
                    if root and not self.model().getRepoItem(root):
                        self.model().addRepo(group, root, row)
                        accept = True
                if accept:
                    event.setDropAction(Qt.LinkAction)
                    event.accept()
        self.setAutoScroll(False)
        self.setState(QAbstractItemView.NoState)
        self.viewport().update()

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
                    _('Cannot open non mercurial repositories or subrepositories'),
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


class RepoRegistryView(QDockWidget):

    showMessage = pyqtSignal(QString)
    openRepo = pyqtSignal(QString, bool)

    def __init__(self, parent):
        QDockWidget.__init__(self, parent)

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
        tv.setModel(repotreemodel.RepoTreeModel(settingsfilename(), self))
        mainframe.layout().addWidget(tv)

        tv.setIndentation(10)
        tv.setFirstColumnSpanned(0, QModelIndex(), True)
        tv.setColumnHidden(1, True)

        tv.showMessage.connect(self.showMessage)
        tv.menuRequested.connect(self.onMenuRequest)
        tv.openRepo.connect(self.openRepo)

        self.createActions()
        QTimer.singleShot(0, self.expand)

    def expand(self):
        self.tview.expandToDepth(0)

    def addRepo(self, root):
        'workbench has opened a new repowidget, ensure it is in the registry'
        m = self.tview.model()
        it = m.getRepoItem(root)
        if it == None:
            m.addRepo(None, root, -1)

    def showPaths(self, show):
        self.tview.setColumnHidden(1, not show)
        self.tview.setHeaderHidden(not show)
        if show:
            self.tview.resizeColumnToContents(0)
            self.tview.resizeColumnToContents(1)

    def close(self):
        self.tview.model().write(settingsfilename())

    def _action_defs(self):
        a = [("open", _("Open"), 'thg-repository-open',
                _("Open the repository in a new tab"), self.open),
             ("openAll", _("Open All"), 'thg-repository-open',
                _("Open all repositories in new tabs"), self.openAll),
             ("newGroup", _("New Group"), 'new-group',
                _("Create a new group"), self.newGroup),
             ("rename", _("Rename"), None,
                _("Rename the entry"), self.startRename),
             ("settings", _("Settings..."), 'settings_user',
                _("View the repository's settings"), self.startSettings),
             ("remove", _("Remove from registry"), 'menudelete',
                _("Remove the node and all its subnodes."
                  " Repositories are not deleted from disk."),
                  self.removeSelected),
             ("clone", _("Clone..."), 'hg-clone',
                _("Clone Repository"), self.cloneRepo),
             ("explore", _("Explore"), 'system-file-manager',
                _("Open the repository in a file browser"), self.explore),
             ("terminal", _("Terminal"), 'utilities-terminal',
                _("Open a shell terminal in the repository root"), self.terminal),
             ("add", _("Add repository..."), 'hg',
                _("Add a repository to this group"), self.addNewRepo),
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
                act.setIcon(qtlib.getmenuicon(icon))
            if tip:
                act.setStatusTip(tip)
            if cb:
                act.triggered.connect(cb)
            self.addAction(act)

    def onMenuRequest(self, point, selitem):
        menulist = selitem.internalPointer().menulist()
        if not menulist:
            return
        self.contextmenu.clear()
        for act in menulist:
            if act:
                self.contextmenu.addAction(self._actions[act])
            else:
                self.contextmenu.addSeparator()
        self.selitem = selitem
        self.contextmenu.exec_(point)

    #
    ## Menu action handlers
    #

    def cloneRepo(self):
        root = self.selitem.internalPointer().rootpath()
        d = clone.CloneDialog(args=[root, root + '-clone'], parent=self)
        d.finished.connect(d.deleteLater)
        d.clonedRepository.connect(self.open)
        d.show()

    def explore(self):
        root = self.selitem.internalPointer().rootpath()
        QDesktopServices.openUrl(QUrl.fromLocalFile(root))

    def terminal(self):
        root = self.selitem.internalPointer().rootpath()
        qtlib.openshell(root)

    def addNewRepo(self):
        'menu action handler for adding a new repository'
        caption = _('Select repository directory to add')
        FD = QFileDialog
        path = FD.getExistingDirectory(caption=caption,
                                       options=FD.ShowDirsOnly | FD.ReadOnly)
        if path:
            root = paths.find_root(hglib.fromunicode(path))
            if root and not self.tview.model().getRepoItem(root):
                try:
                    self.tview.model().addRepo(self.selitem, root)
                except error.RepoError:
                    qtlib.WarningMsgBox(
                        _('Failed to add repository'),
                        _('%s is not a valid repository') % path, parent=self)
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

    def open(self):
        'open context menu action, open repowidget unconditionally'
        root = self.selitem.internalPointer().rootpath()
        repotype = self.selitem.internalPointer().repotype()
        if repotype == 'hg':
            self.openRepo.emit(hglib.tounicode(root), False)
        else:
            qtlib.WarningMsgBox(
                _('Unsupported repository type (%s)') % repotype,
                _('Cannot open non mercurial repositories or subrepositories'),
                parent=self)

    def startRename(self):
        self.tview.edit(self.selitem)

    def newGroup(self):
        self.tview.model().addGroup(_('New Group'))

    def removeSelected(self):
        s = self.selitem
        item = s.internalPointer()
        if not item.okToDelete():
            labels = [(QMessageBox.Yes, _('&Delete')),
                      (QMessageBox.No, _('Cancel'))]
            if not qtlib.QuestionMsgBox(_('Confirm Delete'),
                                    _("Delete Group '%s' and all its entries?")%
                                    item.name, labels=labels, parent=self):
                return
        m = self.tview.model()
        row = s.row()
        parent = s.parent()
        m.removeRows(row, 1, parent)
        self.tview.selectionChanged(None, None)

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

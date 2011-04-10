# reporegistry.py - registry for a user's repositories
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os

from tortoisehg.util import hglib
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
    openRepo = pyqtSignal(QString, bool)
    menuRequested = pyqtSignal(object, object)

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
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDropIndicatorShown(True)
        self.setEditTriggers(QAbstractItemView.DoubleClicked)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

    def contextMenuEvent(self, event):
        if not self.selitem:
            return
        self.menuRequested.emit(event.globalPos(), self.selitem)

    def mouseMoveEvent(self, event):
        self.msg  = ''
        pos = event.pos()
        idx = self.indexAt(pos)
        if idx.isValid():
            item = idx.internalPointer()
            self.msg  = item.details()
        self.showMessage.emit(self.msg)
        super(RepoTreeView, self).mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Enter, Qt.Key_Return):
            if self.selitem and self.selitem.internalPointer().details():
                self.showFirstTabOrOpen()
        else:
            super(RepoTreeView, self).keyPressEvent(event)

    def leaveEvent(self, event):
        if self.msg != '':
            self.showMessage.emit('')

    def mouseDoubleClickEvent(self, event):
        if self.selitem and self.selitem.internalPointer().details():
            self.showFirstTabOrOpen()
        else:
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
        if not self.selitem:
            return
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
        tv.openRepo.connect(self.openRepo)
        tv.menuRequested.connect(self.onMenuRequest)

        self.createActions()
        QTimer.singleShot(0, self.expand)

    def expand(self):
        self.tview.expandToDepth(0)

    def addRepo(self, repo):
        'workbench has opened a new repowidget, ensure its in the registry'
        m = self.tview.model()
        it = m.getRepoItem(repo.root)
        if it == None:
            m.addRepo(None, repo)
        else:
            # ensure the registry item has a thgrepo instance
            it.ensureRepoLoaded()

    def showPaths(self, show):
        self.tview.setColumnHidden(1, not show)
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
                _("Open the repository in Windows Explorer"), self.explore),
             ("terminal", _("Terminal"), 'utilities-terminal',
                _("Open a shell terminal in repository root"), self.terminal),
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
            try:
                lpath = hglib.fromunicode(path)
                repo = thgrepo.repository(None, path=lpath)
                self.model().addRepo(self.selitem, repo)
            except error.RepoError:
                # NOTE: here we cannot pass parent=self because self
                # isn't a QWidget. Codes under `if not repo:` should
                # be handled by a widget, not by a model.
                qtlib.WarningMsgBox(
                    _('Failed to add repository'),
                    _('%s is not a valid repository') % path)
                return

    def startSettings(self):
        root = self.selitem.internalPointer().rootpath()
        sd = settings.SettingsDialog(configrepo=True, focus='web.name',
                                     parent=self, root=root)
        sd.exec_()

    def openAll(self):
        for root in self.selitem.internalPointer().childRoots():
            self.openRepo.emit(hglib.tounicode(root), False)

    def open(self):
        'open context menu action, open repowidget unconditionally'
        root = self.selitem.internalPointer().rootpath()
        self.openRepo.emit(hglib.tounicode(root), False)

    def startRename(self):
        self.tview.edit(self.selitem)

    def newGroup(self):
        self.tview.model().addGroup(_('New Group'))

    def removeSelected(self):
        s = self.selitem
        if not s.internalPointer().okToDelete():
            labels = [(QMessageBox.Yes, _('&Delete')),
                      (QMessageBox.No, _('Cancel'))]
            if not qtlib.QuestionMsgBox(_('Confirm Delete'),
                                    _("Delete Group '%s' and all its entries?")%
                                    self.name, labels=labels, parent=self):
                return
        m = self.tview.model()
        row = s.row()
        parent = s.parent()
        m.removeRows(row, 1, parent)
        self.tview.selectionChanged(None, None)


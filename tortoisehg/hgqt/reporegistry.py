# reporegistry.py - registry for a user's repositories
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os

from mercurial import url

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui, qtlib, thgrepo
from tortoisehg.hgqt.repotreemodel import RepoTreeModel
from tortoisehg.hgqt.pathedit import PathEditDialog
from tortoisehg.hgqt.clone import CloneDialog

from PyQt4.QtCore import *
from PyQt4.QtGui import *

connect = QObject.connect


def settingsfilename():
    s = QSettings()
    dir = os.path.dirname(str(s.fileName()))
    return dir + '/' + 'thg-reporegistry.xml'


class RepoTreeView(QTreeView):

    contextmenu = None

    def __init__(self, parent, workbench):
        QTreeView.__init__(self, parent, allColumnsShowFocus=True)
        self.workbench = workbench
        self.selitem = None
        self.msg  = ''

        self.setExpandsOnDoubleClick(False)
        self.setMouseTracking(True)

        # enable drag and drop
        # (see http://doc.qt.nokia.com/4.6/model-view-dnd.html)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDropIndicatorShown(True)

        self.createActions()
        self.setHeaderHidden(True)

    def contextMenuEvent(self, event):
        if not self.selitem:
            return
        menulist = self.selitem.internalPointer().menulist()
        if len(menulist) > 0:
            if not self.contextmenu:
                self.contextmenu = QMenu(self)
            else:
                self.contextmenu.clear()
            for act in menulist:
                if act:
                    self.contextmenu.addAction(self._actions[act])
                else:
                    self.contextmenu.addSeparator()
            self.contextmenu.exec_(event.globalPos())

    def mouseMoveEvent(self, event):
        self.msg  = ''
        pos = event.pos()
        idx = self.indexAt(pos)
        if idx.isValid():
            item = idx.internalPointer()
            self.msg  = item.details()
        self.workbench.showMessage(self.msg)
        super(RepoTreeView, self).mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self.msg != '':
            self.workbench.showMessage('')

    def mouseDoubleClickEvent(self, event):
        self.showFirstTabOrOpen()

    def selectionChanged(self, selected, deselected):
        selection = self.selectedIndexes()
        if len(selection) == 0:
            self.selitem = None
        else:
            self.selitem = selection[0]

    def _action_defs(self):
        a = [("open", _("Open"), None,
                _("Open the repository in a new tab"), None, self.open),
             ("newGroup", _("New Group"), None,
                _("Create a new group"), None, self.newGroup),
             ("rename", _("Rename"), None,
                _("Rename the entry"), None, self.startRename),
             ("settings", _("Settings..."), None,
                _("View the repository's settings"), None, self.startSettings),
             ("remove", _("Remove from registry"), None,
                _("Remove the node and all its subnodes."
                  " Repositories are not deleted from disk."),
                  None, self.removeSelected),
             ("clone", _("Clone..."), None,
                _("Clone Repository"), None, self.cloneRepo),
             ("explore", _("Explore"), None,
                _("Open the repository in Windows Explorer"), None, self.explore),
             ("terminal", _("Terminal"), None,
                _("Open a shell terminal in repository root"), None, self.terminal),
             ("add", _("Add repository..."), None,
                _("Add a repository to this group"), None, self.addRepo),
             ]
        return a

    def createActions(self):
        self._actions = {}
        for name, desc, icon, tip, key, cb in self._action_defs():
            self._actions[name] = QAction(desc, self)
        QTimer.singleShot(0, self.configureActions)

    def configureActions(self):
        for name, desc, icon, tip, key, cb in self._action_defs():
            act = self._actions[name]
            '''
            if icon:
                act.setIcon(qtlib.geticon(icon))
            '''
            if tip:
                act.setStatusTip(tip)
            if key:
                act.setShortcut(key)
            if cb:
                act.triggered.connect(cb)
            self.addAction(act)

    def startSettings(self):
        if not self.selitem:
            return
        self.selitem.internalPointer().startSettings(self.parent())

    def startRename(self):
        if not self.selitem:
            return
        self.edit(self.selitem)

    def open(self):
        if not self.selitem:
            return
        self.selitem.internalPointer().open()

    def showFirstTabOrOpen(self):
        if not self.selitem:
            return
        self.selitem.internalPointer().showFirstTabOrOpen(workbench=self.workbench)

    def newGroup(self):
        m = self.model()
        m.addGroup(_('New Group'))

    def removeSelected(self):
        if not self.selitem:
            return
        s = self.selitem
        if not s.internalPointer().okToDelete(self):
            return
        m = self.model()
        row = s.row()
        parent = s.parent()
        m.removeRows(row, 1, parent)

    def cloneRepo(self):
        if not self.selitem:
            return
        root = self.selitem.internalPointer().rootpath()
        d = CloneDialog(args=[root, root + '-clone'], parent=self)
        def cmdfinished(res):
            if res == 0:
                dest = d.getDest()
                self.workbench.openRepo(dest)
        d.cmdfinished.connect(cmdfinished)
        d.show()

    def explore(self):
        if not self.selitem:
            return
        root = self.selitem.internalPointer().rootpath()
        self.workbench.launchExplorer(root)

    def terminal(self):
        if not self.selitem:
            return
        root = self.selitem.internalPointer().rootpath()
        repo = thgrepo.repository(path=root)
        self.workbench.launchTerminal(repo)

    def addRepo(self):
        if not self.selitem:
            return
        m = self.model()
        m.addRepo(self.selitem, '')

    def sizeHint(self):
        size = super(RepoTreeView, self).sizeHint()
        size.setWidth(QFontMetrics(self.font()).width('M') * 15)
        return size

class RepoRegistryView(QDockWidget):

    openRepoSignal = pyqtSignal(QString)
    visibilityChanged = pyqtSignal(bool)

    def __init__(self, workbench):
        QDockWidget.__init__(self, workbench)

        self.setFeatures(QDockWidget.DockWidgetClosable |
                         QDockWidget.DockWidgetMovable  |
                         QDockWidget.DockWidgetFloatable)
        self.setWindowTitle(_('Repository Registry'))

        mainframe = QFrame()
        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        mainframe.setLayout(lay)
        self.setWidget(mainframe)

        self.tmodel = m = RepoTreeModel(self.openrepo, settingsfilename(),
                                        parent=self)

        self.tview = tv = RepoTreeView(self, workbench)
        lay.addWidget(tv)
        tv.setModel(m)

        tv.setIndentation(10)
        tv.setFirstColumnSpanned(0, QModelIndex(), True)

        self.tview.setColumnHidden(1, True)
        QTimer.singleShot(0, self.expand)

    def expand(self):
        self.tview.expandToDepth(0)

    def addRepo(self, reporoot):
        m = self.tmodel
        if m.getRepoItem(reporoot) == None:
            m.addRepo(None, reporoot)

    def openrepo(self, path):
        self.openRepoSignal.emit(hglib.tounicode(path))

    def showPaths(self, show):
        self.tview.setColumnHidden(1, not show)
        if show:
            self.tview.resizeColumnToContents(0)
            self.tview.resizeColumnToContents(1)

    def close(self):
        self.tmodel.write(settingsfilename())

    def showEvent(self, event):
        self.visibilityChanged.emit(True)

    def hideEvent(self, event):
        self.visibilityChanged.emit(False)
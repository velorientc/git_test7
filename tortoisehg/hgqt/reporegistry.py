# reporegistry.py - registry for a user's repositories
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os

from PyQt4 import QtCore, QtGui

from PyQt4.QtCore import Qt, QVariant, SIGNAL, SLOT
from PyQt4.QtCore import QModelIndex, QString

from PyQt4.QtGui import QWidget, QVBoxLayout

from tortoisehg.hgqt.i18n import _

connect = QtCore.QObject.connect

class RepoTreeItem:
    def __init__(self, parent=None):
        self._parent = parent
        self.childs = []
        self._row = 0

    def appendChild(self, child):
        child._row = len(self.childs)
        child._parent = self
        self.childs.append(child)

    def child(self, row):
        return self.childs[row]

    def childCount(self):
        return len(self.childs)

    def columnCount(self):
        return 2

    def data(self, column):
        return QVariant()

    def row(self):
        return self._row

    def parent(self):
        return self._parent


class RepoItem(RepoTreeItem):
    def __init__(self, rootpath, parent=None):
        RepoTreeItem.__init__(self, parent)
        self.rootpath = rootpath

    def data(self, column):
        if column == 0:
            return QVariant(os.path.basename(self.rootpath))
        elif column == 1:
            return QVariant(self.rootpath)
        return QVariant()


class RepoGroupItem(RepoTreeItem):
    def __init__(self, name, parent=None):
        RepoTreeItem.__init__(self, parent)
        self.name = name

    def data(self, column):
        if column == 0:
            return QVariant(self.name)
        return QVariant()


class RepoTreeModel(QtCore.QAbstractItemModel):
    def __init__(self, parent=None):
        QtCore.QAbstractItemModel.__init__(self, parent)

        self.rootItem = root = RepoTreeItem()

        self.allrepos = all = RepoGroupItem(_('All Repositories'))
        root.appendChild(all)

    # see http://doc.qt.nokia.com/4.6/model-view-model-subclassing.html

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if (not parent.isValid()):
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()
        childItem = parentItem.child(row)
        if childItem:
            return self.createIndex(row, column, childItem)
        else:
            return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        childItem = index.internalPointer()
        parentItem = childItem.parent()
        if parentItem is self.rootItem:
            return QModelIndex()
        return self.createIndex(parentItem.row(), 0, parentItem)

    def rowCount(self, parent):
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            parentItem = self.rootItem;
        else:
            parentItem = parent.internalPointer()
        return parentItem.childCount()
 
    def columnCount(self, parent):
        if parent.isValid():
            return parent.internalPointer().columnCount()
        else:
            return self.rootItem.columnCount()

    def data(self, index, role):
        if not index.isValid():
            return QVariant()
        if role != Qt.DisplayRole:
            return QVariant();
        item = index.internalPointer()
        return item.data(index.column())

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                if section == 1:
                    return QString(_('Path'))
        return QVariant()

    def flags(self, index):
        if not index.isValid():
            return 0
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    # functions not defined in QAbstractItemModel

    def allreposIndex(self):
        return self.createIndex(0, 0, self.allrepos)

    def addRepo(self, reporoot):
        all = self.allrepos
        cc = all.childCount()
        self.beginInsertRows(self.allreposIndex(), cc, cc + 1)
        all.appendChild(RepoItem(reporoot))
        self.endInsertRows()

    def getRepoItem(self, reporoot):
        for c in self.allrepos.childs:
            if c.rootpath == reporoot:
                return c
        return None


class RepoRegistryView(QWidget):
    def __init__(self, parent=None):
        QWidget.__init__(self, parent)

        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        self.setLayout(lay)

        self.tmodel = m = RepoTreeModel()

        self.tview = tv = QtGui.QTreeView()
        lay.addWidget(tv)
        tv.setModel(m)

        tv.setIndentation(10)
        tv.setFirstColumnSpanned(0, QModelIndex(), True)

        QtCore.QTimer.singleShot(0, self.expand)

    def expand(self):
        self.tview.expandToDepth(0)

    def addRepo(self, reporoot):
        m = self.tmodel
        if m.getRepoItem(reporoot) == None:
            m.addRepo(reporoot)

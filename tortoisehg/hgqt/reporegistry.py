# reporegistry.py - registry for a user's repositories
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

from PyQt4 import QtCore, QtGui

from PyQt4.QtCore import Qt, QVariant, SIGNAL, SLOT
from PyQt4.QtCore import QModelIndex

from PyQt4.QtGui import QWidget, QVBoxLayout

from tortoisehg.hgqt.i18n import _

connect = QtCore.QObject.connect

class RepoTreeItem:
    def __init__(self, name, parent=None):
        self.name = name
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
        return 1

    def data(self, column):
        return QVariant(self.name)

    def row(self):
        return self._row

    def parent(self):
        return self._parent


class RepoTreeModel(QtCore.QAbstractItemModel):
    def __init__(self, parent=None):
        QtCore.QAbstractItemModel.__init__(self, parent)

        self.rootItem = root = RepoTreeItem('')

        self.allrepos = all = RepoTreeItem(_('All Repositories'))
        root.appendChild(all)

        all.appendChild(RepoTreeItem('dummy-repo-A'))
        all.appendChild(RepoTreeItem('dummy-repo-B'))
        all.appendChild(RepoTreeItem('dummy-repo-C'))

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

    def flags(self, index):
        if not index.isValid():
            return 0
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


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
        tv.setHeaderHidden(True)

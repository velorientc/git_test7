# Copyright (c) 2009-2010 LOGILAB S.A. (Paris, FRANCE).
# http://www.logilab.fr/ -- mailto:contact@logilab.fr
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

from mercurial.node import short as short_hex

from tortoisehg.hgqt.i18n import _

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class _TreeItem(object):
    def __init__(self, data, parent=None):
        self.parentItem = parent
        self.itemData = data
        self.childItems = []

    def appendChild(self, item):
        self.childItems.append(item)
        return item
    addChild = appendChild

    def child(self, row):
        return self.childItems[row]

    def childCount(self):
        return len(self.childItems)

    def columnCount(self):
        return len(self.itemData)

    def data(self, column):
        return self.itemData[column]

    def parent(self):
        return self.parentItem

    def row(self):
        if self.parentItem:
            return self.parentItem.childItems.index(self)
        return 0

    def __getitem__(self, idx):
        return self.childItems[idx]

    def __len__(self):
        return len(self.childItems)

    def __iter__(self):
        for ch in self.childItems:
            yield ch

class ManifestModel(QAbstractItemModel):
    """
    Qt model to display a hg manifest, ie. the tree of files at a
    given revision. To be used with a QTreeView.
    """
    def __init__(self, repo, rev, parent=None):
        QAbstractItemModel.__init__(self, parent)

        self.repo = repo
        self.changectx = self.repo.changectx(rev)
        self.setupModelData()

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()

        item = index.internalPointer()
        if role == Qt.DecorationRole:
            return QApplication.style().standardIcon(
                item.childItems and QStyle.SP_DirIcon or QStyle.SP_FileIcon)
        if role == Qt.DisplayRole:
            return item.data(index.column())

        return QVariant()

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def index(self, row, column, parent=QModelIndex()):
        if row < 0 or column < 0 or row >= self.rowCount(parent) or column >= self.columnCount(parent):
            return QModelIndex()

        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()
        childItem = parentItem.child(row)
        if childItem is not None:
            return self.createIndex(row, column, childItem)
        else:
            return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        childItem = index.internalPointer()
        parentItem = childItem.parent()

        if parentItem == self.rootItem:
            return QModelIndex()

        return self.createIndex(parentItem.row(), 0, parentItem)

    def rowCount(self, parent):
        if parent.column() > 0:
            return 0

        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()
        return parentItem.childCount()

    def columnCount(self, parent):
        if parent.isValid():
            return parent.internalPointer().columnCount()
        else:
            return self.rootItem.columnCount()

    def setupModelData(self):
        self.rootItem = _TreeItem([''])

        for path in sorted(self.changectx.manifest()):
            path = path.split('/')
            node = self.rootItem

            for p in path:
                for ch in node:
                    if ch.data(0) == p:
                        node = ch
                        break
                else:
                    node = node.addChild(_TreeItem([p], node))

    def pathFromIndex(self, index):
        idxs = []
        while index.isValid():
            idxs.insert(0, index)
            index = self.parent(index)
        return '/'.join([index.internalPointer().data(0) for index in idxs])

    def indexFromPath(self, path):
        """Return index for the specified path if found; otherwise invalid index"""
        def search(paths, parent=QModelIndex()):
            if not paths:
                return parent
            for r in xrange(self.rowCount(parent)):
                i = self.index(r, 0, parent)
                if self.data(i) == paths[0]:
                    return search(paths[1:], i)
            return QModelIndex()  # not found

        return search(path.split('/'))

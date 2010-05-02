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

import os, os.path as osp

from mercurial.node import short as short_hex

from PyQt4 import QtCore

from tortoisehg.hgqt.repomodel import TreeItem


class ManifestModel(QtCore.QAbstractItemModel):
    """
    Qt model to display a hg manifest, ie. the tree of files at a
    given revision. To be used with a QTreeView.
    """
    def __init__(self, repo, rev, parent=None):
        QtCore.QAbstractItemModel.__init__(self, parent)

        self.repo = repo
        self.changectx = self.repo.changectx(rev)
        self.setupModelData()

    def data(self, index, role):
        if not index.isValid():
            return QtCore.QVariant()

        if role != QtCore.Qt.DisplayRole:
            return QtCore.QVariant()

        item = index.internalPointer()
        return QtCore.QVariant(item.data(index.column()))

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def headerData(self, section, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return QtCore.QVariant(self.rootItem.data(section))
        return QtCore.QVariant()

    def index(self, row, column, parent):
        if row < 0 or column < 0 or row >= self.rowCount(parent) or column >= self.columnCount(parent):
            return QtCore.QModelIndex()

        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()
        childItem = parentItem.child(row)
        if childItem is not None:
            return self.createIndex(row, column, childItem)
        else:
            return QtCore.QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QtCore.QModelIndex()

        childItem = index.internalPointer()
        parentItem = childItem.parent()

        if parentItem == self.rootItem:
            return QtCore.QModelIndex()

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
        rootData = ["rev %s:%s" % (self.changectx.rev(),
                                   short_hex(self.changectx.node()))]
        self.rootItem = TreeItem(rootData)

        for path in sorted(self.changectx.manifest()):
            path = path.split(osp.sep)
            node = self.rootItem

            for p in path:
                for ch in node:
                    if ch.data(0) == p:
                        node = ch
                        break
                else:
                    node = node.addChild(TreeItem([p], node))

    def pathFromIndex(self, index):
        idxs = []
        while index.isValid():
            idxs.insert(0, index)
            index = self.parent(index)
        return osp.sep.join([index.internalPointer().data(0) for index in idxs])

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

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import util

class ManifestModel(QAbstractItemModel):
    """
    Qt model to display a hg manifest, ie. the tree of files at a
    given revision. To be used with a QTreeView.
    """
    def __init__(self, repo, rev, parent=None):
        QAbstractItemModel.__init__(self, parent)

        self._repo = repo
        self._rev = rev

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return

        e = index.internalPointer()
        if role == Qt.DecorationRole:
            return QApplication.style().standardIcon(
                len(e) and QStyle.SP_DirIcon or QStyle.SP_FileIcon)
        if role == Qt.DisplayRole:
            return e.name

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def index(self, row, column, parent=QModelIndex()):
        try:
            return self.createIndex(row, column,
                                    self._parententry(parent).at(row))
        except IndexError:
            return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        e = index.internalPointer()
        if e.path:
            return self.indexFromPath(e.parent.path)
        else:
            return QModelIndex()

    def _parententry(self, parent):
        if parent.isValid():
            return parent.internalPointer()
        else:
            return self._rootentry

    def rowCount(self, parent=QModelIndex()):
        return len(self._parententry(parent))

    def columnCount(self, parent=QModelIndex()):
        return 1

    @util.propertycache
    def _rootentry(self):
        roote = _Entry()
        for path in self._repo[self._rev].manifest():
            path = path.split('/')
            e = roote

            for p in path:
                if not p in e:
                    e.addchild(p)
                e = e[p]

        roote.sort()
        return roote

    def pathFromIndex(self, index):
        if not index.isValid():
            return ''

        return index.internalPointer().path

    def indexFromPath(self, path):
        """Return index for the specified path if found; otherwise invalid index"""
        if not path:
            return QModelIndex()

        e = self._rootentry
        paths = path and path.split('/') or []
        try:
            for p in paths:
                e = e[p]
        except KeyError:
            return QModelIndex()

        return self.createIndex(e.parent.index(e.name), 0, e)

class _Entry(object):
    """Each file or directory"""
    def __init__(self, name='', parent=None):
        self._name = name
        self._parent = parent
        self._child = {}
        self._nameindex = []

    @property
    def parent(self):
        return self._parent

    @property
    def path(self):
        if self.parent is None or not self.parent.name:
            return self.name
        else:
            return self.parent.path + '/' + self.name

    @property
    def name(self):
        return self._name

    def __len__(self):
        return len(self._child)

    def __getitem__(self, name):
        return self._child[name]

    def addchild(self, name):
        if name not in self._child:
            self._nameindex.append(name)
        self._child[name] = self.__class__(name, parent=self)

    def __contains__(self, item):
        return item in self._child

    def at(self, index):
        return self._child[self._nameindex[index]]

    def index(self, name):
        return self._nameindex.index(name)

    def sort(self, reverse=False):
        """Sort the entries recursively; directories first"""
        for e in self._child.itervalues():
            e.sort(reverse=reverse)
        self._nameindex.sort(
            key=lambda s: '%s%s' % (self[s] and 'D' or 'F', s),
            reverse=reverse)

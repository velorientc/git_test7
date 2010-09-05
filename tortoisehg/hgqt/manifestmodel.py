# manifestmodel.py - Model for TortoiseHg manifest view
#
# Copyright (C) 2009-2010 LOGILAB S.A. <http://www.logilab.fr/>
# Copyright (C) 2010 Yuya Nishihara <yuya@tcha.org>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.

import itertools

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import util
from tortoisehg.hgqt import qtlib

class ManifestModel(QAbstractItemModel):
    """
    Qt model to display a hg manifest, ie. the tree of files at a
    given revision. To be used with a QTreeView.
    """
    _STATUS_ICONS = {'modified': 'modified',
                     'added': 'fileadd',
                     'removed': 'filedelete'}

    StatusRole = Qt.UserRole + 1
    """Role for file change status"""

    def __init__(self, repo, rev, parent=None):
        QAbstractItemModel.__init__(self, parent)

        self._repo = repo
        self._rev = rev

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return

        e = index.internalPointer()
        if role == Qt.DecorationRole:
            return self._iconforentry(e)
        if role == self.StatusRole:
            return e.status
        if role == Qt.DisplayRole:
            return e.name

    def _iconforentry(self, e):
        ic = QApplication.style().standardIcon(
            len(e) and QStyle.SP_DirIcon or QStyle.SP_FileIcon)
        if e.status:
            ic = _overlaidicon(ic, qtlib.geticon(self._STATUS_ICONS[e.status]))
        return ic

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
            return self.indexFromPath(e.parent.path, index.column())
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
        ctx = self._repo[self._rev]
        status = dict(zip(('modified', 'added', 'removed'),
                          self._repo.status(ctx.parents()[0], ctx)[:3]))
        for path in itertools.chain(ctx.manifest(), status['removed']):
            e = roote
            for p in path.split('/'):
                if not p in e:
                    e.addchild(p)
                e = e[p]

            for st, files in status.iteritems():
                if path in files:
                    # TODO: what if added & removed at once?
                    e.setstatus(st)
                    break

        roote.sort()
        return roote

    def filePath(self, index):
        if not index.isValid():
            return ''

        return index.internalPointer().path

    def indexFromPath(self, path, column=0):
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

        return self.createIndex(e.parent.index(e.name), column, e)

def _overlaidicon(base, overlay):
    """Generate overlaid icon"""
    # TODO: generalize this function as a utility
    pixmap = base.pixmap(16, 16)
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
    painter.drawPixmap(0, 0, overlay.pixmap(16, 16))
    del painter
    return QIcon(pixmap)

class _Entry(object):
    """Each file or directory"""
    def __init__(self, name='', parent=None):
        self._name = name
        self._parent = parent
        self._status = None
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

    @property
    def status(self):
        """Return 'modified', 'added', 'removed' or None"""
        return self._status

    def setstatus(self, status):
        assert status in ('modified', 'added', 'removed')
        self._status = status

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

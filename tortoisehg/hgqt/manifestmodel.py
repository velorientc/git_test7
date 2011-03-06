# manifestmodel.py - Model for TortoiseHg manifest view
#
# Copyright (C) 2009-2010 LOGILAB S.A. <http://www.logilab.fr/>
# Copyright (C) 2010 Yuya Nishihara <yuya@tcha.org>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.

import os, itertools

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import util
from tortoisehg.util import hglib
from tortoisehg.hgqt import qtlib, status, visdiff

class ManifestModel(QAbstractItemModel):
    """
    Qt model to display a hg manifest, ie. the tree of files at a
    given revision. To be used with a QTreeView.
    """

    StatusRole = Qt.UserRole + 1
    """Role for file change status"""

    def __init__(self, repo, rev, statusfilter='MAC', parent=None):
        QAbstractItemModel.__init__(self, parent)

        self._repo = repo
        self._rev = rev

        assert util.all(c in 'MARC' for c in statusfilter)
        self._statusfilter = statusfilter

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return

        if role == Qt.DecorationRole:
            return self.fileIcon(index)
        if role == self.StatusRole:
            return self.fileStatus(index)

        e = index.internalPointer()
        if role == Qt.DisplayRole:
            return e.name

    def filePath(self, index):
        """Return path at the given index [unicode]"""
        if not index.isValid():
            return ''

        return index.internalPointer().path

    def fileIcon(self, index):
        ic = QApplication.style().standardIcon(
            self.isDir(index) and QStyle.SP_DirIcon or QStyle.SP_FileIcon)
        if not index.isValid():
            return ic
        e = index.internalPointer()
        if not e.status:
            return ic
        st = status.statusTypes[e.status]
        if st.icon:
            ic = _overlaidicon(ic, qtlib.geticon(st.icon.rstrip('.ico')))  # XXX
        return ic

    def fileStatus(self, index):
        """Return the change status of the specified file"""
        if not index.isValid():
            return
        e = index.internalPointer()
        return e.status

    def isDir(self, index):
        if not index.isValid():
            return True  # root entry must be a directory
        e = index.internalPointer()
        return len(e) != 0

    def mimeData(self, indexes):
        def preparefiles():
            files = [self.filePath(i) for i in indexes if i.isValid()]
            if self._rev is not None:
                base, _fns = visdiff.snapshot(self._repo, files,
                                              self._repo[self._rev])
            else:  # working copy
                base = self._repo.root
            return iter(os.path.join(base, e) for e in files)

        m = QMimeData()
        m.setUrls([QUrl.fromLocalFile(e) for e in preparefiles()])
        return m

    def mimeTypes(self):
        return ['text/uri-list']

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if not (self.isDir(index) or self.fileStatus(index) == 'R'):
            f |= Qt.ItemIsDragEnabled
        return f

    def index(self, row, column, parent=QModelIndex()):
        try:
            return self.createIndex(row, column,
                                    self._parententry(parent).at(row))
        except IndexError:
            return QModelIndex()

    def indexFromPath(self, path, column=0):
        """Return index for the specified path if found [unicode]

        If not found, returns invalid index.
        """
        if not path:
            return QModelIndex()

        e = self._rootentry
        paths = path and unicode(path).split('/') or []
        try:
            for p in paths:
                e = e[p]
        except KeyError:
            return QModelIndex()

        return self.createIndex(e.parent.index(e.name), column, e)

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

    @pyqtSlot(str)
    def setStatusFilter(self, status):
        """Filter file tree by change status 'MARC'"""
        status = str(status)
        assert util.all(c in 'MARC' for c in status)
        if self._statusfilter == status:
            return  # for performance reason
        self._statusfilter = status
        self._buildrootentry()

    @property
    def statusFilter(self):
        """Return the current status filter"""
        return self._statusfilter

    @property
    def _rootentry(self):
        try:
            return self.__rootentry
        except (AttributeError, TypeError):
            self._buildrootentry()
            return self.__rootentry

    def _buildrootentry(self):
        """Rebuild the tree of files and directories"""
        roote = _Entry()
        ctx = self._repo[self._rev]

        status = dict(zip(('M', 'A', 'R'),
                          (set(a) for a in self._repo.status(ctx.parents()[0],
                                                             ctx)[:3])))
        uncleanpaths = status['M'] | status['A'] | status['R']
        def pathinstatus(path):
            """Test path is included by the status filter"""
            if util.any(c in self._statusfilter and path in e
                        for c, e in status.iteritems()):
                return True
            if 'C' in self._statusfilter and path not in uncleanpaths:
                return True
            return False

        for path in itertools.chain(ctx.manifest(), status['R']):
            if not pathinstatus(path):
                continue

            e = roote
            for p in hglib.tounicode(path).split('/'):
                if not p in e:
                    e.addchild(p)
                e = e[p]

            for st, files in status.iteritems():
                if path in files:
                    # TODO: what if added & removed at once?
                    e.setstatus(st)
                    break
            else:
                e.setstatus('C')

        roote.sort()

        self.beginResetModel()
        self.__rootentry = roote
        self.endResetModel()

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
        """Return file change status"""
        return self._status

    def setstatus(self, status):
        assert status in 'MARC'
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

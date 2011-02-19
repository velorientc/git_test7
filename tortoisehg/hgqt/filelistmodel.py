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

from tortoisehg.util import hglib

from tortoisehg.hgqt.qtlib import geticon

from PyQt4.QtCore import *
from PyQt4.QtGui import *

nullvariant = QVariant()

class HgFileListModel(QAbstractTableModel):
    """
    Model used for listing (modified) files of a given Hg revision
    """

    contextChanged = pyqtSignal(object)

    def __init__(self, repo, parent):
        """
        data is a HgHLRepo instance
        """
        QAbstractTableModel.__init__(self, parent)
        self.repo = repo
        self._boldfont = parent.font()
        self._boldfont.setBold(True)
        self._ctx = None
        self._files = []
        self._filesdict = {}
        self._fulllist = False
        self._secondParent = False

    @pyqtSlot(bool)
    def toggleFullFileList(self, value):
        self._fulllist = value
        self.loadFiles()
        self.layoutChanged.emit()

    @pyqtSlot(bool)
    def toggleSecondParent(self, value):
        self._secondParent = value
        self.layoutChanged.emit()

    def __len__(self):
        return len(self._files)

    def rowCount(self, parent=None):
        return len(self)

    def columnCount(self, parent=None):
        return 1

    def file(self, row):
        return self._files[row]['path']

    def setContext(self, ctx):
        self.contextChanged.emit(ctx)
        if not self._ctx or ctx.thgid() != self._ctx.thgid():
            self._ctx = ctx
            self.loadFiles()
            self.layoutChanged.emit()

    def fileFromIndex(self, index):
        if not index.isValid() or index.row()>=len(self) or not self._ctx:
            return None
        row = index.row()
        return self._files[row]['path']

    def revFromIndex(self, index):
        'return revision for index. index is guarunteed to be valid'
        if not bool(self._ctx.p2()):
            return self._ctx.p1().rev()
        row = index.row()
        data = self._files[row]
        if (data['wasmerged'] and self._secondParent) or \
           (data['parent'] == 1 and self._fulllist):
            return self._ctx.p2().rev()
        else:
            return self._ctx.p1().rev()

    def dataFromIndex(self, index):
        if not index.isValid() or index.row()>=len(self) or not self._ctx:
            return None
        row = index.row()
        return self._files[row]

    def indexFromFile(self, filename):
        if filename in self._filesdict:
            row = self._files.index(self._filesdict[filename])
            return self.index(row, 0)
        return QModelIndex()

    def _buildDesc(self, parent):
        files = []
        ctxfiles = self._ctx.files()
        modified, added, removed = self._ctx.changesToParent(parent)
        ismerge = bool(self._ctx.p2())
        if self._fulllist and ismerge:
            func = lambda x: True
        else:
            func = lambda x: x in ctxfiles
        for lst, flag in ((added, 'A'), (modified, 'M'), (removed, 'R')):
            for f in filter(func, lst):
                wasmerged = ismerge and f in ctxfiles
                files.append({'path': f, 'status': flag, 'parent': parent,
                              'wasmerged': wasmerged})
        return files

    def loadFiles(self):
        self._files = []
        self._files = self._buildDesc(0)
        if bool(self._ctx.p2()):
            _paths = [x['path'] for x in self._files]
            _files = self._buildDesc(1)
            self._files += [x for x in _files if x['path'] not in _paths]
        self._filesdict = dict([(f['path'], f) for f in self._files])

    def data(self, index, role):
        if not index.isValid() or index.row()>len(self) or not self._ctx:
            return nullvariant
        if index.column() != 0:
            return nullvariant

        row = index.row()
        column = index.column()

        current_file_desc = self._files[row]
        current_file = current_file_desc['path']

        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            return QVariant(hglib.tounicode(current_file))
        elif role == Qt.DecorationRole:
            if self._fulllist and bool(self._ctx.p2()):
                if current_file_desc['wasmerged']:
                    icn = geticon('leftright')
                elif current_file_desc['parent'] == 0:
                    icn = geticon('left')
                elif current_file_desc['parent'] == 1:
                    icn = geticon('right')
                return QVariant(icn.pixmap(20,20))
            elif current_file_desc['status'] == 'A':
                return QVariant(geticon('fileadd'))
            elif current_file_desc['status'] == 'R':
                return QVariant(geticon('filedelete'))
            #else:
            #    return QVariant(geticon('view-diff'))
        elif role == Qt.FontRole:
            if current_file_desc['wasmerged']:
                return QVariant(self._boldfont)
        else:
            return nullvariant

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

def ismerge(ctx):
    return len(ctx.parents()) > 1

class HgFileListModel(QAbstractTableModel):
    """
    Model used for listing (modified) files of a given Hg revision
    """
    def __init__(self, repo, parent=None):
        """
        data is a HgHLRepo instance
        """
        QAbstractTableModel.__init__(self, parent)
        self.repo = repo
        self._ctx = None
        self._files = []
        self._filesdict = {}
        self._fulllist = False

    def toggleFullFileList(self):
        self._fulllist = not self._fulllist
        self.loadFiles()
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
        if ctx != self._ctx:
            self._ctx = ctx
            self.loadFiles()
            self.layoutChanged.emit()

    def flagFromIndex(self, index):
        if not index.isValid() or index.row()>=len(self) or not self._ctx:
            return None
        row = index.row()
        return self._files[row]['flag']

    def fileFromIndex(self, index):
        if not index.isValid() or index.row()>=len(self) or not self._ctx:
            return None
        row = index.row()
        return self._files[row]['path']

    def revFromIndex(self, index):
        if self._fulllist and ismerge(self._ctx):
            if not index.isValid() or index.row()>=len(self) or not self._ctx:
                return None
            row = index.row()
            current_file_desc = self._files[row]
            if current_file_desc['parent'] == 1:
                return self._ctx.parents()[1].rev()
            else:
                return self._ctx.parents()[0].rev()
        return None

    def indexFromFile(self, filename):
        if filename in self._filesdict:
            row = self._files.index(self._filesdict[filename])
            return self.index(row, 0)
        return QModelIndex()

    def _buildDesc(self, parent):
        files = []
        ctxfiles = self._ctx.files()
        modified, added, removed = self._ctx.changesToParent(parent)
        if self._fulllist:
            func = lambda x: True
        else:
            func = lambda x: x in ctxfiles
        for lst, flag in ((added, 'A'), (modified, 'M'), (removed, 'R')):
            for f in filter(func, lst):
                files.append({'path': f, 'flag': flag,
                               'parent': parent,
                               'infiles': f in ctxfiles})
                # renamed/copied files are handled by background
                # filling process since it can be a bit long
        return files

    def loadFiles(self):
        self._files = []
        self._files = self._buildDesc(0)
        if ismerge(self._ctx):
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
            if self._fulllist and ismerge(self._ctx):
                if current_file_desc['infiles']:
                    icn = geticon('leftright')
                elif current_file_desc['parent'] == 0:
                    icn = geticon('left')
                elif current_file_desc['parent'] == 1:
                    icn = geticon('right')
                return QVariant(icn.pixmap(20,20))
            elif current_file_desc['flag'] == 'A':
                return QVariant(geticon('fileadd'))
            elif current_file_desc['flag'] == 'R':
                return QVariant(geticon('filedelete'))
        elif role == Qt.FontRole:
            if self._fulllist and current_file_desc['infiles']:
                font = self.font()
                font.setBold(True)
                return QVariant(font)
        else:
            return nullvariant

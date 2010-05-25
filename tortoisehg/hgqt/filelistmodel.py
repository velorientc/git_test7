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

import re

from mercurial.revlog import LookupError

from tortoisehg.util.util import isbfile, Curry

from tortoisehg.hgqt.graph import ismerge, diff as revdiff
from tortoisehg.hgqt.config import HgConfig
from tortoisehg.hgqt import icon as geticon

from PyQt4 import QtCore, QtGui
connect = QtCore.QObject.connect
SIGNAL = QtCore.SIGNAL
nullvariant = QtCore.QVariant()


replus = re.compile(r'^[+][^+].*', re.M)
reminus = re.compile(r'^[-][^-].*', re.M)

class HgFileListModel(QtCore.QAbstractTableModel):
    """
    Model used for listing (modified) files of a given Hg revision
    """
    def __init__(self, repo, parent=None):
        """
        data is a HgHLRepo instance
        """
        QtCore.QAbstractTableModel.__init__(self, parent)
        self.repo = repo
        self._datacache = {}
        self.load_config()
        self.current_ctx = None
        self._files = []
        self._filesdict = {}
        self.diffwidth = 100
        self._fulllist = False
        self._fill_iter = None

    def toggleFullFileList(self):
        self._fulllist = not self._fulllist
        self.loadFiles()
        self.emit(SIGNAL('layoutChanged()'))

    def load_config(self):
        cfg = HgConfig(self.repo.ui)
        self._flagcolor = {}
        self._flagcolor['='] = cfg.getFileModifiedColor(default='blue')
        self._flagcolor['-'] = cfg.getFileRemovedColor(default='red')
        self._flagcolor['-'] = cfg.getFileDeletedColor(default='red')
        self._flagcolor['+'] = cfg.getFileAddedColor(default='green')
        self._displaydiff = cfg.getDisplayDiffStats()

    def setDiffWidth(self, w):
        if w != self.diffwidth:
            self.diffwidth = w
            self._datacache = {}
            self.emit(SIGNAL('dataChanged(const QModelIndex &, const QModelIndex & )'),
                      self.index(1, 0),
                      self.index(1, self.rowCount()))

    def __len__(self):
        return len(self._files)

    def rowCount(self, parent=None):
        return len(self)

    def columnCount(self, parent=None):
        return 1 + self._displaydiff

    def file(self, row):
        return self._files[row]['path']

    def fileflag(self, fn):
        return self._filesdict[fn]['flag']

    def fileparentctx(self, fn, ctx=None):
        if ctx is None:
            return self._filesdict[fn]['parent']
        return ctx.parents()[0]

    def fileFromIndex(self, index):
        if not index.isValid() or index.row()>=len(self) or not self.current_ctx:
            return None
        row = index.row()
        return self._files[row]['path']

    def revFromIndex(self, index):
        if self._fulllist and ismerge(self.current_ctx):
            if not index.isValid() or index.row()>=len(self) or not self.current_ctx:
                return None
            row = index.row()
            current_file_desc = self._files[row]
            if current_file_desc['fromside'] == 'right':
                return self.current_ctx.parents()[1].rev()
            else:
                return self.current_ctx.parents()[0].rev()
        return None

    def indexFromFile(self, filename):
        if filename in self._filesdict:
            row = self._files.index(self._filesdict[filename])
            return self.index(row, 0)
        return QtCore.QModelIndex()

    def _filterFile(self, filename, ctxfiles):
        if self._fulllist:
            return True
        return filename in ctxfiles #self.current_ctx.files()

    def _buildDesc(self, parent, fromside):
        _files = []
        ctx = self.current_ctx
        ctxfiles = ctx.files()
        changes = self.repo.status(parent.node(), ctx.node())[:3]
        modified, added, removed = changes
        for lst, flag in ((added, '+'), (modified, '='), (removed, '-')):
            for f in [x for x in lst if self._filterFile(x, ctxfiles)]:
                _files.append({'path': f, 'flag': flag, 'desc': f,
                               'parent': parent, 'fromside': fromside,
                               'infiles': f in ctxfiles})
                # renamed/copied files are handled by background
                # filling process since it can be a bit long
        for fdesc in _files:
            bfile = isbfile(fdesc['path'])
            fdesc['bfile'] = bfile
            if bfile:
                fdesc['desc'] = fdesc['desc'].replace('.hgbfiles'+os.sep, '')

        return _files

    def loadFiles(self):
        self._fill_iter = None
        self._files = []
        self._datacache = {}
        self._files = self._buildDesc(self.current_ctx.parents()[0], 'left')
        if ismerge(self.current_ctx):
            _paths = [x['path'] for x in self._files]
            _files = self._buildDesc(self.current_ctx.parents()[1], 'right')
            self._files += [x for x in _files if x['path'] not in _paths]
        self._filesdict = dict([(f['path'], f) for f in self._files])
        self.fillFileStats()

    def setSelectedRev(self, ctx):
        if ctx != self.current_ctx:
            self.current_ctx = ctx
            self._datacache = {}
            self.loadFiles()
            self.emit(SIGNAL("layoutChanged()"))

    def fillFileStats(self):
        """
        Method called to start the background process of computing
        file stats, which are to be displayed in the 'Stats' column
        """
        self._fill_iter = self._fill()
        self._fill_one_step()

    def _fill_one_step(self):
        if self._fill_iter is None:
            return
        try:
            nextfill = self._fill_iter.next()
            if nextfill is not None:
                row, col = nextfill
                idx = self.index(row, col)
                self.emit(SIGNAL('dataChanged(const QModelIndex &, const QModelIndex &)'),
                          idx, idx)
            QtCore.QTimer.singleShot(10, lambda self=self: self._fill_one_step())

        except StopIteration:
            self._fill_iter = None

    def _fill(self):
        # the generator used to fill file stats as a background process
        for row, desc in enumerate(self._files):
            filename = desc['path']
            if desc['flag'] == '=' and self._displaydiff:
                diff = revdiff(self.repo, self.current_ctx, desc['parent'],
                               files=[filename])
                try:
                    tot = self.current_ctx.filectx(filename).data().count('\n')
                except LookupError:
                    tot = 0
                add = len(replus.findall(diff))
                rem = len(reminus.findall(diff))
                if tot == 0:
                    tot = max(add + rem, 1)
                desc['stats'] = (tot, add, rem)
                yield row, 1

            if desc['flag'] == '+':
                m = self.current_ctx.filectx(filename).renamed()
                if m:
                    removed = self.repo.status(desc['parent'].node(),
                                               self.current_ctx.node())[2]
                    oldname, node = m
                    if oldname in removed:
                        # removed.remove(oldname) XXX
                        desc['renamedfrom'] = (oldname, node)
                        desc['flag'] = '='
                        desc['desc'] += '\n (was %s)' % oldname
                    else:
                        desc['copiedfrom'] = (oldname, node)
                        desc['flag'] = '='
                        desc['desc'] += '\n (copy of %s)' % oldname
                    yield row, 0
            yield None

    def data(self, index, role):
        if not index.isValid() or index.row()>len(self) or not self.current_ctx:
            return nullvariant
        row = index.row()
        column = index.column()

        current_file_desc = self._files[row]
        current_file = current_file_desc['path']

        if column == 0:
            if role in (QtCore.Qt.DisplayRole, QtCore.Qt.ToolTipRole):
                return QtCore.QVariant(current_file_desc['desc'])
            elif role == QtCore.Qt.DecorationRole:
                if self._fulllist and ismerge(self.current_ctx):
                    if current_file_desc['infiles']:
                        icn = geticon('leftright')
                    elif current_file_desc['fromside'] == 'left':
                        icn = geticon('left')
                    elif current_file_desc['fromside'] == 'right':
                        icn = geticon('right')
                    return QtCore.QVariant(icn.pixmap(20,20))
                elif current_file_desc['flag'] == '+':
                    return QtCore.QVariant(geticon('fileadd'))
                elif current_file_desc['flag'] == '-':
                    return QtCore.QVariant(geticon('filedelete'))
            elif role == QtCore.Qt.FontRole:
                if self._fulllist and current_file_desc['infiles']:
                    font = QtGui.QFont()
                    font.setBold(True)
                    return QtCore.QVariant(font)
        return nullvariant

    def headerData(self, section, orientation, role):
        if ismerge(self.current_ctx):
            if self._fulllist:
                header = ('File (all)', '')
            else:
                header = ('File (merged only)', '')
        else:
            header = ('File','')

        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return QtCore.QVariant(header[section])

        return nullvariant

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
    
from PyQt4 import QtCore, QtGui, Qsci
Qt = QtCore.Qt
connect = QtCore.QObject.connect
SIGNAL = QtCore.SIGNAL

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.qtlib import geticon


class HgFileListView(QtGui.QTableView):
    """
    A QTableView for displaying a HgFileListModel
    """
    def __init__(self, parent=None):
        QtGui.QTableView.__init__(self, parent)
        self.setShowGrid(False)
        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(20)
        self.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.setTextElideMode(Qt.ElideLeft)

        self.horizontalHeader().setToolTip(_('Double click to toggle merge mode'))

        self.createActions()

        connect(self.horizontalHeader(), SIGNAL('sectionDoubleClicked(int)'),
                self.toggleFullFileList)

        connect(self.horizontalHeader(),
                SIGNAL('sectionResized(int, int, int)'),
                self.sectionResized)
        self._diff_dialogs = {}
        self._nav_dialogs = {}
        
    def setModel(self, model):
        QtGui.QTableView.setModel(self, model)
        connect(model, SIGNAL('layoutChanged()'),
                self.fileSelected)
        connect(self.selectionModel(),
                SIGNAL('currentRowChanged (const QModelIndex & , const QModelIndex & )'),
                self.fileSelected)
        self.horizontalHeader().setResizeMode(1, QtGui.QHeaderView.Stretch)

    def currentFile(self):
        index = self.currentIndex()
        return self.model().fileFromIndex(index)

    def fileSelected(self, index=None, *args):
        if index is None:
            index = self.currentIndex()
        sel_file = self.model().fileFromIndex(index)
        from_rev = self.model().revFromIndex(index)
        self.emit(SIGNAL('fileSelected'), sel_file, from_rev)

    def selectFile(self, filename):
        self.setCurrentIndex(self.model().indexFromFile(filename))

    def toggleFullFileList(self, *args):
        self.model().toggleFullFileList()

    def _action_defs(self):
        a = []
        return a

    def createActions(self):
        self._actions = {}
        for name, desc, icon, tip, key, cb in self._action_defs():
            act = QtGui.QAction(desc, self)
            if icon:
                act.setIcon(geticon(icon))
            if tip:
                act.setStatusTip(tip)
            if key:
                act.setShortcut(key)
            if cb:
                connect(act, SIGNAL('triggered()'), cb)
            self._actions[name] = act
            self.addAction(act)

    def contextMenuEvent(self, event):
        menu = QtGui.QMenu(self)
        for act in []:
            if act:
                menu.addAction(self._actions[act])
            else:
                menu.addSeparator()
        menu.exec_(event.globalPos())

    def resizeEvent(self, event):
        vp_width = self.viewport().width()
        col_widths = [self.columnWidth(i) \
                      for i in range(1, self.model().columnCount())]
        col_width = vp_width - sum(col_widths)
        col_width = max(col_width, 50)
        self.setColumnWidth(0, col_width)
        QtGui.QTableView.resizeEvent(self, event)

    def sectionResized(self, idx, oldsize, newsize):
        if idx == 1:
            self.model().setDiffWidth(newsize)

    def nextFile(self):
        row = self.currentIndex().row()
        self.setCurrentIndex(self.model().index(min(row+1,
                             self.model().rowCount() - 1), 0))
    def prevFile(self):
        row = self.currentIndex().row()
        self.setCurrentIndex(self.model().index(max(row - 1, 0), 0))

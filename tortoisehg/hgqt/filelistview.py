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

import os

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.qtlib import geticon
from tortoisehg.hgqt.filedialogs import FileLogDialog, FileDiffDialog 
from tortoisehg.hgqt import visdiff

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class HgFileListView(QTableView):
    """
    A QTableView for displaying a HgFileListModel
    """

    fileRevSelected = pyqtSignal(object, object, object)
    clearDisplay = pyqtSignal()
    contextmenu = None

    def __init__(self, parent=None):
        QTableView.__init__(self, parent)
        self.setShowGrid(False)
        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(20)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setTextElideMode(Qt.ElideLeft)

        hh = self.horizontalHeader()
        hh.setToolTip(_('Double click to toggle merge mode'))
        hh.sectionDoubleClicked.connect(self.toggleFullFileList)
        hh.sectionResized.connect(self.sectionResized)

        self.createActions()

        self.doubleClicked.connect(self.fileActivated)
        self._diff_dialogs = {}
        self._nav_dialogs = {}

    def setModel(self, model):
        QTableView.setModel(self, model)
        model.layoutChanged.connect(self.layoutChanged)
        self.selectionModel().currentRowChanged.connect(self.fileSelected)
        self.horizontalHeader().setResizeMode(1, QHeaderView.Stretch)

    def currentFile(self):
        index = self.currentIndex()
        return self.model().fileFromIndex(index)

    def layoutChanged(self):
        'file model has new contents'
        index = self.currentIndex()
        if index.row() >= len(self.model()):
            self.selectRow(0)
        else:
            self.selectRow(index.row())
        self.fileSelected()

    def fileSelected(self, index=None, *args):
        if index is None:
            index = self.currentIndex()
        sel_file = self.model().fileFromIndex(index)
        from_rev = self.model().revFromIndex(index)
        status = self.model().flagFromIndex(index)
        if sel_file:
            self.fileRevSelected.emit(sel_file, from_rev, status)
        else:
            self.clearDisplay.emit()

    def selectFile(self, filename):
        index = self.model().indexFromFile(filename)
        self.setCurrentIndex(index)

    def fileActivated(self, index, alternate=False):
        sel_file = self.model().fileFromIndex(index)
        if alternate:
            self.navigate(sel_file)
        else:
            self.diffNavigate(sel_file)

    def toggleFullFileList(self, *args):
        self.model().toggleFullFileList()

    def navigate(self, filename=None):
        self._navigate(filename, FileLogDialog, self._nav_dialogs)

    def diffNavigate(self, filename=None):
        self._navigate(filename, FileDiffDialog, self._diff_dialogs)

    def _navigate(self, filename, dlgclass, dlgdict):
        if not filename:
            filename = self.currentFile()
        model = self.model()
        if filename is not None and len(model.repo.file(filename))>0:
            if filename not in dlgdict:
                dlg = dlgclass(model.repo, filename,
                               repoviewer=self.window())
                dlgdict[filename] = dlg
                dlg.setWindowTitle(_('Hg file log viewer - %s') % filename)
            dlg = dlgdict[filename] 
            dlg.goto(model._ctx.rev())
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

    def _action_defs(self):
        a = [('navigate', _('File history'), None, _('Show the history of '
              'the selected file'), None, self.navigate),
             ('diffnavigate', _('Compare file revisions'), None, _('Compare '
              'revisions of the selected file'), None, self.diffNavigate),
             ]
        return a

    def createActions(self):
        self._actions = {}
        for name, desc, icon, tip, key, cb in self._action_defs():
            act = QAction(desc, self)
            if icon:
                act.setIcon(geticon(icon))
            if tip:
                act.setStatusTip(tip)
            if key:
                act.setShortcut(key)
            if cb:
                act.triggered.connect(cb)
            self._actions[name] = act
            self.addAction(act)

    def contextMenuEvent(self, event):
        if not self.contextmenu:
            self.contextmenu = QMenu(self)
            for act in ['navigate', 'diffnavigate']:
                if act:
                    self.contextmenu.addAction(self._actions[act])
                else:
                    self.contextmenu.addSeparator()
        self.contextmenu.exec_(event.globalPos())

    def resizeEvent(self, event):
        vp_width = self.viewport().width()
        col_widths = [self.columnWidth(i) \
                      for i in range(1, self.model().columnCount())]
        col_width = vp_width - sum(col_widths)
        col_width = max(col_width, 50)
        self.setColumnWidth(0, col_width)
        QTableView.resizeEvent(self, event)

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

    #
    ## Mouse drag
    #

    def selectedRows(self):
        return self.selectionModel().selectedRows()

    def dragObject(self):
        ctx = self.model()._ctx
        if type(ctx.rev()) == str:
            return
        paths = []
        for index in self.selectedRows():
            paths.append(self.model().fileFromIndex(index))
        if not paths:
            return
        if ctx.rev() is None:
            base = ctx._repo.root
        else:
            base, _ = visdiff.snapshot(ctx._repo, paths, ctx)
        urls = []
        for path in paths:
            u = QUrl()
            u.setPath('file://' + os.path.join(base, path))
            urls.append(u)
        if urls:
            d = QDrag(self)
            m = QMimeData()
            m.setUrls(urls)
            d.setMimeData(m)
            d.start(Qt.CopyAction)

    def mousePressEvent(self, event):
        self.pressPos = event.pos()
        self.pressTime = QTime.currentTime()
        return QTableView.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        d = event.pos() - self.pressPos
        if d.manhattanLength() < QApplication.startDragDistance():
            return QTableView.mouseMoveEvent(self, event)
        elapsed = self.pressTime.msecsTo(QTime.currentTime())
        if elapsed < QApplication.startDragTime():
            return QTableView.mouseMoveEvent(self, event)
        self.dragObject()
        return QTableView.mouseMoveEvent(self, event)

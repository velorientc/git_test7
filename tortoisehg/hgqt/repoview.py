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

from mercurial import error

from tortoisehg.util import hglib
from tortoisehg.hgqt.qtlib import geticon
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import htmldelegate

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class HgRepoView(QTableView):

    revisionClicked = pyqtSignal(object)
    revisionSelected = pyqtSignal(object)
    revisionActivated = pyqtSignal(object)
    menuRequested = pyqtSignal(QPoint, object)
    showMessage = pyqtSignal(unicode)

    def __init__(self, repo, parent=None):
        QTableView.__init__(self, parent)
        self.repo = repo
        self.init_variables()
        self.setShowGrid(False)

        vh = self.verticalHeader()
        vh.hide()
        vh.setDefaultSectionSize(20)

        self.horizontalHeader().setHighlightSections(False)

        self.standardDelegate = self.itemDelegate()
        self.htmlDelegate = htmldelegate.HTMLDelegate(self)

        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.doubleClicked.connect(self.revActivated)
        self.clicked.connect(self.revClicked)

    def setRepo(self, repo):
        self.repo = repo

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if not index.isValid():
            return
        if event.button() == Qt.MidButton:
            self.gotoAncestor(index)
            return
        QTableView.mousePressEvent(self, event)

    def contextMenuEvent(self, event):
        self.menuRequested.emit(event.globalPos(), self.selectedRevisions())

    def init_variables(self):
        # member variables
        self.current_rev = -1
        # rev navigation history (manage 'back' action)
        self._rev_history = []
        self._rev_pos = -1
        self._in_history = False # flag set when we are "in" the
        # history. It is required cause we cannot known, in
        # "revision_selected", if we are crating a new branch in the
        # history navigation or if we are navigating the history

    def setModel(self, model):
        self.init_variables()
        QTableView.setModel(self, model)
        self.selectionModel().currentRowChanged.connect(self.revSelected)
        self.resetDelegate()
        model.layoutChanged.connect(self.resetDelegate)

    def resetDelegate(self):
        # Model column layout has changed so we need to move
        # our column delegate to correct location
        if not self.model():
            return
        model = self.model()

        for c in range(model.columnCount(QModelIndex())):
            if model._columns[c] in ['Description', 'Changes']:
                self.setItemDelegateForColumn(c, self.htmlDelegate)
            else:
                self.setItemDelegateForColumn(c, self.standardDelegate)

    def resizeColumns(self, *args):
        # resize columns the smart way: the column holding Description
        # is resized according to the total widget size.
        if not self.model():
            return
        hh = self.horizontalHeader()
        hh.setStretchLastSection(False)
        self._resizeColumns()
        hh.setStretchLastSection(True)

    def _resizeColumns(self):
        # _resizeColumns misbehaves if called with last section streched
        model = self.model()
        col1_width = self.viewport().width()
        fontm = QFontMetrics(self.font())
        tot_stretch = 0.0
        for c in range(model.columnCount(QModelIndex())):
            if model._columns[c] in model._stretchs:
                tot_stretch += model._stretchs[model._columns[c]]
                continue
            w = model.maxWidthValueForColumn(c)
            if isinstance(w, int):
                self.setColumnWidth(c, w)
            elif w is not None:
                w = fontm.width(hglib.tounicode(str(w)) + 'w')
                self.setColumnWidth(c, w)
            else:
                w = self.sizeHintForColumn(c)
                self.setColumnWidth(c, w)
            col1_width -= self.columnWidth(c)
        col1_width = max(col1_width, 100)
        for c in range(model.columnCount(QModelIndex())):
            if model._columns[c] in model._stretchs:
                w = model._stretchs[model._columns[c]] / tot_stretch
                self.setColumnWidth(c, col1_width * w)

    def revFromindex(self, index):
        if not index.isValid():
            return
        model = self.model()
        if model and model.graph:
            row = index.row()
            gnode = model.graph[row]
            return gnode.rev

    def context(self, rev):
        return self.repo.changectx(rev)

    def revClicked(self, index):
        rev = self.revFromindex(index)
        self.revisionClicked.emit(rev)

    def revActivated(self, index):
        rev = self.revFromindex(index)
        if rev is not None:
            self.revisionActivated.emit(rev)

    def revSelected(self, index, index_from):
        rev = self.revFromindex(index)
        if self.current_rev == rev:
            return

        if not self._in_history:
            del self._rev_history[self._rev_pos+1:]
            self._rev_history.append(rev)
            self._rev_pos = len(self._rev_history)-1

        self._in_history = False
        self.current_rev = rev

        self.revisionSelected.emit(rev)

    def selectedRevisions(self):
        """Return the list of selected revisions"""
        selmodel = self.selectionModel()
        return [self.revFromindex(i) for i in selmodel.selectedRows()]

    def gotoAncestor(self, index):
        rev = self.revFromindex(index)
        if rev is None or self.current_rev is None:
            return
        ctx = self.context(self.current_rev)
        ctx2 = self.context(rev)
        if ctx.thgmqunappliedpatch() or ctx2.thgmqunappliedpatch():
            return
        ancestor = ctx.ancestor(ctx2)
        self.showMessage.emit(_("Goto ancestor of %s and %s") % (
                                ctx.rev(), ctx2.rev()))
        self.goto(ancestor.rev())

    def canGoBack(self):
        return bool(self._rev_history and self._rev_pos > 0)

    def canGoForward(self):
        return bool(self._rev_history
                    and self._rev_pos < len(self._rev_history) - 1)

    def back(self):
        if self.canGoBack():
            self._rev_pos -= 1
            idx = self.model().indexFromRev(self._rev_history[self._rev_pos])
            if idx is not None:
                self._in_history = True
                self.setCurrentIndex(idx)

    def forward(self):
        if self.canGoForward():
            self._rev_pos += 1
            idx = self.model().indexFromRev(self._rev_history[self._rev_pos])
            if idx is not None:
                self._in_history = True
                self.setCurrentIndex(idx)

    def goto(self, rev):
        """
        Select revision 'rev' (can be anything understood by repo.changectx())
        """
        if type(rev) is QString:
            rev = str(rev)
        try:
            rev = self.repo.changectx(rev).rev()
        except error.RepoError:
            self.showMessage.emit(_("Can't find revision '%s'") % rev)
        except LookupError, e:
            self.showMessage.emit(hglib.fromunicode(str(e)))
        else:
            idx = self.model().indexFromRev(rev)
            if idx is not None:
                self.setCurrentIndex(idx)

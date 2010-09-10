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

from mercurial.error import RepoError

from tortoisehg.util import hglib
from tortoisehg.hgqt.qtlib import geticon
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.quickbar import QuickBar
from tortoisehg.hgqt import htmllistview

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class GotoQuickBar(QuickBar):
    gotoSignal = pyqtSignal(unicode)

    def __init__(self, parent):
        QuickBar.__init__(self, "Goto", "Ctrl+G", "Goto", parent)

    def createActions(self, openkey, desc):
        QuickBar.createActions(self, openkey, desc)
        self._actions['go'] = QAction("Go", self)
        self._actions['go'].triggered.connect(self.goto)

    def goto(self):
        self.gotoSignal.emit(unicode(self.entry.text()))

    def createContent(self):
        QuickBar.createContent(self)
        self.compl_model = QStringListModel(['tip'])
        self.completer = QCompleter(self.compl_model, self)
        self.entry = QLineEdit(self)
        self.entry.setCompleter(self.completer)
        self.addWidget(self.entry)
        self.addAction(self._actions['go'])
        self.entry.returnPressed.connect(self._actions['go'].trigger)

    def setVisible(self, visible=True):
        QuickBar.setVisible(self, visible)
        if visible:
            self.entry.setFocus()
            self.entry.selectAll()

    def __del__(self):
        # prevent a warning in the console:
        # QObject::startTimer: QTimer can only be used with threads started with QThread
        self.entry.setCompleter(None)

class HgRepoView(QTableView):

    revisionClicked = pyqtSignal(object)
    revisionSelected = pyqtSignal(object)
    revisionActivated = pyqtSignal(object)
    menuRequested = pyqtSignal(QPoint, object)
    showMessage = pyqtSignal(unicode)

    def __init__(self, workbench, repo, parent=None):
        QTableView.__init__(self, parent)
        self.repo = repo
        self.init_variables()
        self.setShowGrid(False)

        vh = self.verticalHeader()
        vh.hide()
        vh.setDefaultSectionSize(20)

        self.horizontalHeader().setHighlightSections(False)

        self.standardDelegate = self.itemDelegate()
        self.htmlDelegate = htmllistview.HTMLDelegate(self)

        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.createToolbars()
        self.doubleClicked.connect(self.revActivated)
        self.clicked.connect(self.revClicked)

        self._actions = {}
        self._actions['back'] = workbench.actionBack
        self._actions['forward'] = workbench.actionForward

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if not index.isValid():
            return
        if event.button() == Qt.MidButton:
            self.gotoAncestor(index)
            return
        QTableView.mousePressEvent(self, event)

    def createToolbars(self):
        self.goto_toolbar = tb = GotoQuickBar(self)
        tb.setObjectName("goto_toolbar")
        tb.gotoSignal.connect(self.goto)

    def contextMenuEvent(self, event):
        selmodel = self.selectionModel()
        sels = [self.revFromindex(i) for i in selmodel.selectedRows()]
        self.menuRequested.emit(event.globalPos(), sels)

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
        self.goto_toolbar.compl_model.setStringList(self.repo.tags().keys())
        self.resetDelegate()
        model.layoutChanged.connect(self.resetDelegate)

    def resetDelegate(self):
        # Model column layout has changed so we need to move
        # our column delegate to correct location
        if not self.model():
            return
        model = self.model()

        for c in range(model.columnCount()):
            if model._columns[c] in ['Log', 'Changes']:
                self.setItemDelegateForColumn(c, self.htmlDelegate)
            else:
                self.setItemDelegateForColumn(c, self.standardDelegate)

    def resizeColumns(self, *args):
        # resize columns the smart way: the column holding Log
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
        for c in range(model.columnCount()):
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
        for c in range(model.columnCount()):
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
        self.updateActions()

    def gotoAncestor(self, index):
       if rev is None or self.current_rev is None:
           return
       ctx = self.context(self.current_rev)
       ctx2 = self.context(rev)
       if ctx.thgmqunappliedpatch() or ctx2.thgmqunappliedpatch():
           return
       ancestor = ctx.ancestor(ctx2)
       self.showMessage.emit(_("Goto ancestor of %s and %s")%(ctx.rev(), ctx2.rev()))
       self.goto(ancestor.rev())

    def updateActions(self):
        if len(self._rev_history) > 0:
            back = self._rev_pos > 0
            forw = self._rev_pos < len(self._rev_history)-1
        else:
            back = False
            forw = False
        self._actions['back'].setEnabled(back)
        self._actions['forward'].setEnabled(forw)

    def back(self):
        if self._rev_history and self._rev_pos>0:
            self._rev_pos -= 1
            idx = self.model().indexFromRev(self._rev_history[self._rev_pos])
            if idx is not None:
                self._in_history = True
                self.setCurrentIndex(idx)
        self.updateActions()

    def forward(self):
        if self._rev_history and self._rev_pos<(len(self._rev_history)-1):
            self._rev_pos += 1
            idx = self.model().indexFromRev(self._rev_history[self._rev_pos])
            if idx is not None:
                self._in_history = True
                self.setCurrentIndex(idx)
        self.updateActions()

    def goto(self, rev):
        """
        Select revision 'rev' (can be anything understood by repo.changectx())
        """
        if rev is not None:
            rev = str(rev) # might be a QString
        try:
            rev = self.repo.changectx(rev).rev()
        except RepoError:
            self.showMessage.emit(_("Can't find revision '%s'") % rev)
        else:
            idx = self.model().indexFromRev(rev)
            if idx is not None:
                self.goto_toolbar.setVisible(False)
                self.setCurrentIndex(idx)

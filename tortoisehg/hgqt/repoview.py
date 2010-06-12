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

from tortoisehg.hgqt.qtlib import geticon
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.quickbar import QuickBar

from PyQt4.QtCore import *
from PyQt4.QtGui import *

connect = QObject.connect


class GotoQuickBar(QuickBar):
    def __init__(self, parent):
        QuickBar.__init__(self, "Goto", "Ctrl+G", "Goto", parent)

    def createActions(self, openkey, desc):
        QuickBar.createActions(self, openkey, desc)
        self._actions['go'] = QAction("Go", self)
        connect(self._actions['go'], SIGNAL('triggered()'),
                self.goto)

    def goto(self):
        self.emit(SIGNAL('goto'), unicode(self.entry.text()))

    def createContent(self):
        QuickBar.createContent(self)
        self.compl_model = QStringListModel(['tip'])
        self.completer = QCompleter(self.compl_model, self)
        self.entry = QLineEdit(self)
        self.entry.setCompleter(self.completer)
        self.addWidget(self.entry)
        self.addAction(self._actions['go'])

        connect(self.entry, SIGNAL('returnPressed()'),
                self._actions['go'].trigger)

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
    """
    A QTableView for displaying a HgRepoListModel,
    with actions, shortcuts, etc.
    """
    def __init__(self, parent=None):
        QTableView.__init__(self, parent)
        self.init_variables()
        self.setShowGrid(False)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(20)
        self.horizontalHeader().setHighlightSections(False)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.createActions()
        self.createToolbars()
        connect(self,
                SIGNAL('doubleClicked (const QModelIndex &)'),
                self.revisionActivated)

        self._autoresize = True
        connect(self.horizontalHeader(),
                SIGNAL('sectionResized(int, int, int)'),
                self.disableAutoResize)

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
        connect(tb, SIGNAL('goto'), self.goto)

    def _action_defs(self):
        a = [('back', _('Back'), 'back', None,
              QKeySequence(QKeySequence.Back),
              self.back),
             ('forward', _('Forward'), 'forward', None,
              QKeySequence(QKeySequence.Forward),
              self.forward),
             ('manifest', _('Show at rev...'), None,
              _('Show the manifest at selected revision'), None,
              self.showAtRev),
             ('update', _('Update...'), 'update', None, None,
              self.updateToRev),
             ('merge', _('Merge with...'), 'merge', None, None,
              self.mergeWithRev),
             ('tag', _('Tag...'), 'tag', None, None,
              self.tagToRev),
             ('backout', _('Backout...'), None, None, None,
              self.backoutToRev),
             ]
        return a

    def createActions(self):
        self._actions = {}
        for name, desc, icon, tip, key, cb in self._action_defs():
            self._actions[name] = QAction(desc, self)
        QTimer.singleShot(0, self.configureActions)

    def configureActions(self):
        for name, desc, icon, tip, key, cb in self._action_defs():
            act = self._actions[name]
            if icon:
                act.setIcon(geticon(icon))
            if tip:
                act.setStatusTip(tip)
            if key:
                act.setShortcut(key)
            if cb:
                connect(act, SIGNAL('triggered()'), cb)
            self.addAction(act)

    def showAtRev(self):
        self.emit(SIGNAL('revisionActivated'), self.current_rev)

    def updateToRev(self):
        self.emit(SIGNAL('updateToRevision'), self.current_rev)

    def mergeWithRev(self):
        self.emit(SIGNAL('mergeWithRevision'), self.current_rev)

    def tagToRev(self):
        self.emit(SIGNAL('tagToRevision'), self.current_rev)

    def backoutToRev(self):
        self.emit(SIGNAL('backoutToRevision'), self.current_rev)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        for act in ['update', 'manifest', 'merge', 'tag', 'backout',
                    None, 'back', 'forward']:
            if act:
                menu.addAction(self._actions[act])
            else:
                menu.addSeparator()
        menu.exec_(event.globalPos())

    def init_variables(self):
        # member variables
        self.current_rev = None
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
        connect(self.selectionModel(),
                SIGNAL('currentRowChanged (const QModelIndex & , const QModelIndex & )'),
                self.revisionSelected)
        self.goto_toolbar.compl_model.setStringList(model.repo.tags().keys())

    def enableAutoResize(self, *args):
        self._autoresize =  True

    def disableAutoResize(self, *args):
        self._autoresize =  False
        QTimer.singleShot(100, self.enableAutoResize)

    def resizeEvent(self, event):
        # we catch this event to resize smartly tables' columns
        QTableView.resizeEvent(self, event)
        if self._autoresize:
            self.resizeColumns()

    def resizeColumns(self, *args):
        # resize columns the smart way: the column holding Log
        # is resized according to the total widget size.
        model = self.model()
        if not model:
            return
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
                w = fontm.width(unicode(w) + 'w')
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

    def revisionActivated(self, index):
        rev = self.revFromindex(index)
        if rev is not None:
            self.emit(SIGNAL('revisionActivated'), rev)

    def revisionSelected(self, index, index_from):
        """
        Callback called when a revision is selected in the revisions table
        """
        rev = self.revFromindex(index)
        if True:#rev is not None:
            model = self.model()
            if self.current_rev is not None and self.current_rev == rev:
                return
            if not self._in_history:
                del self._rev_history[self._rev_pos+1:]
                self._rev_history.append(rev)
                self._rev_pos = len(self._rev_history)-1

            self._in_history = False
            self.current_rev = rev

            self.emit(SIGNAL('revisionSelected'), rev)
            self.set_navigation_button_state()

    def gotoAncestor(self, index):
        rev = self.revFromindex(index)
        if rev is not None and self.current_rev is not None:
            repo = self.model().repo
            ctx = repo[self.current_rev]
            ctx2 = repo[rev]
            ancestor = ctx.ancestor(ctx2)
            self.emit(SIGNAL('showMessage'),
                      "Goto ancestor of %s and %s"%(ctx.rev(), ctx2.rev()), 2000)
            self.goto(ancestor.rev())

    def set_navigation_button_state(self):
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
        self.set_navigation_button_state()

    def forward(self):
        if self._rev_history and self._rev_pos<(len(self._rev_history)-1):
            self._rev_pos += 1
            idx = self.model().indexFromRev(self._rev_history[self._rev_pos])
            if idx is not None:
                self._in_history = True
                self.setCurrentIndex(idx)
        self.set_navigation_button_state()

    def goto(self, rev):
        """
        Select revision 'rev' (can be anything understood by repo.changectx())
        """
        rev = str(rev) # might be a QString
        repo = self.model().repo
        try:
            rev = repo.changectx(rev).rev()
        except RepoError:
            self.emit(SIGNAL('showMessage'), "Can't find revision '%s'"%rev, 2000)
        else:
            idx = self.model().indexFromRev(rev)
            if idx is not None:
                self.goto_toolbar.setVisible(False)
                self.setCurrentIndex(idx)

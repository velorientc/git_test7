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

from mercurial import extensions
from mercurial.error import RepoError

from tortoisehg.util import hglib
from tortoisehg.hgqt.qtlib import geticon
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.quickbar import QuickBar
from tortoisehg.hgqt import htmllistview

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

    revisionClicked = pyqtSignal(object)
    revisionSelected = pyqtSignal(object)
    revisionActivated = pyqtSignal(object)
    updateToRevision = pyqtSignal(object)
    mergeWithRevision = pyqtSignal(object)
    tagToRevision = pyqtSignal(object)
    backoutToRevision = pyqtSignal(object)
    emailRevision = pyqtSignal(object)
    archiveRevision = pyqtSignal(object)
    copyHashSignal = pyqtSignal(object)
    rebaseRevision = pyqtSignal(object)
    qimportRevision = pyqtSignal(object)
    qfinishRevision = pyqtSignal(object)
    qgotoRevision = pyqtSignal(str)
    stripRevision = pyqtSignal(object)
    showMessage = pyqtSignal(str)

    def __init__(self, workbench, parent=None):
        QTableView.__init__(self, parent)
        self.workbench = workbench
        self.init_variables()
        self.setShowGrid(False)

        vh = self.verticalHeader()
        vh.hide()
        vh.setDefaultSectionSize(20)

        self.horizontalHeader().setHighlightSections(False)

        self.standardDelegate = self.itemDelegate()
        self.htmlDelegate = htmllistview.HTMLDelegate(self)

        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.createActions()
        self.createToolbars()
        self.doubleClicked.connect(self.revActivated)
        self.clicked.connect(self.revClicked)

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
        exs = [name for name, module in extensions.extensions()]
        a = [('manifest', _('Show at rev...'), None,
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
             ('email', _('Email patch...'), None, None, None,
              self.emailRev),
             ('archive', _('Archive...'), None, None, None, self.archiveRev),
             ('copyhash', _('Copy hash'), None, None, None,
              self.copyHash),
             ]
        if 'rebase' in exs:
            a.append(('rebase', _('Rebase...'), None, None, None,
                     self.rebase))
        if 'mq' in exs:
            a.append(('qimport', _('Import Revision to MQ'), None, None, None,
                     self.qimport))
            a.append(('qfinish', _('Finish patch'), None, None, None,
                     self.qfinish))
            a.append(('strip', _('Strip Revision...'), None, None, None,
                     self.strip))
            a.append(('qgoto', _('Goto patch'), None, None, None,
                      self.qgoto))
        return a

    def createActions(self):
        self._actions = {}
        self._actions['back'] = self.workbench.actionBack
        self._actions['forward'] = self.workbench.actionForward
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
        self.revisionActivated.emit(self.current_rev)

    def updateToRev(self):
        self.updateToRevision.emit(self.current_rev)

    def mergeWithRev(self):
        self.mergeWithRevision.emit(self.current_rev)

    def tagToRev(self):
        self.tagToRevision.emit(self.current_rev)

    def backoutToRev(self):
        self.backoutToRevision.emit(self.current_rev)

    def emailRev(self):
        self.emailRevision.emit(self.current_rev)

    def archiveRev(self):
        self.archiveRevision.emit(self.current_rev)

    def copyHash(self):
        self.copyHashSignal.emit(self.current_rev)

    def rebase(self):
        self.rebaseRevision.emit(self.current_rev)

    def qimport(self):
        self.qimportRevision.emit(self.current_rev)

    def qfinish(self):
        self.qfinishRevision.emit(self.current_rev)

    def strip(self):
        self.stripRevision.emit(self.current_rev)

    def qgoto(self):
        ctx = self.context(self.current_rev)
        self.qgotoRevision.emit(ctx.thgmqpatchname())

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        for act in ['update', 'manifest', 'merge', 'tag', 'backout',
                    'email', 'archive', 'copyhash', None, 'back', 'forward',
                    None]:
            if act:
                menu.addAction(self._actions[act])
            else:
                menu.addSeparator()
        exs = [name for name, module in extensions.extensions()]
        if 'rebase' in exs:
            menu.addAction(self._actions['rebase'])
        if 'mq' in exs:
            menu.addAction(self._actions['qimport'])
            menu.addAction(self._actions['qfinish'])
            menu.addAction(self._actions['strip'])
            menu.addAction(self._actions['qgoto'])
        menu.exec_(event.globalPos())

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
        self.goto_toolbar.compl_model.setStringList(model.repo.tags().keys())
        self.resetDelegate()
        model.layoutChanged.connect(self.resetDelegate)

    def resetDelegate(self):
        # Model column layout has changed so we need to move
        # our column delegate to correct location
        if not self.model():
            return
        model = self.model()

        for c in range(model.columnCount()):
            if model._columns[c] == 'Log':
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
        return self.model().repo.changectx(rev)

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
       self.showMessage.emit("Goto ancestor of %s and %s"%(ctx.rev(), ctx2.rev()))
       self.goto(ancestor.rev())

    def updateActions(self):
        ctx = self.context(self.current_rev)
        enable = self.current_rev is not None and not ctx.thgmqunappliedpatch()
        self.workbench.actionDiffMode.setEnabled(enable)
        exclude = ('back', 'forward', 'qgoto')
        for name in self._actions:
            if name not in exclude:
                self._actions[name].setEnabled(enable)

        self._actions['qgoto'].setEnabled(ctx.thgmqappliedpatch() or ctx.thgmqunappliedpatch())

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
        rev = str(rev) # might be a QString
        repo = self.model().repo
        try:
            rev = repo.changectx(rev).rev()
        except RepoError:
            self.showMessage.emit("Can't find revision '%s'" % rev)
        else:
            idx = self.model().indexFromRev(rev)
            if idx is not None:
                self.goto_toolbar.setVisible(False)
                self.setCurrentIndex(idx)

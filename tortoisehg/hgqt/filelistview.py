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

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib
from tortoisehg.hgqt.filedialogs import FileLogDialog, FileDiffDialog 
from tortoisehg.hgqt import visdiff, wctxactions, revert

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

        self.createActions()

        self.doubleClicked.connect(self.fileActivated)
        self._diff_dialogs = {}
        self._nav_dialogs = {}

    def setModel(self, model):
        QTableView.setModel(self, model)
        model.layoutChanged.connect(self.layoutChanged)
        model.contextChanged.connect(self.contextChanged)
        self.selectionModel().currentRowChanged.connect(self.fileSelected)
        self.horizontalHeader().setResizeMode(1, QHeaderView.Stretch)
        self.actionShowAllMerge.setChecked(False)
        self.actionShowAllMerge.toggled.connect(model.toggleFullFileList)
        self.actionSecondParent.setChecked(False)
        self.actionSecondParent.toggled.connect(model.toggleSecondParent)
        if model._ctx is not None:
            self.contextChanged(model._ctx)

    def contextChanged(self, ctx):
        real = type(ctx.rev()) is int
        wd = ctx.rev() is None
        for act in ['navigate', 'diffnavigate', 'ldiff', 'edit']:
            self._actions[act].setEnabled(real)
        for act in ['diff', 'revert']:
            self._actions[act].setEnabled(real or wd)
        if len(ctx.parents()) == 2:
            self.actionShowAllMerge.setEnabled(True)
            self.actionSecondParent.setEnabled(True)
        else:
            self.actionShowAllMerge.setEnabled(False)
            self.actionSecondParent.setEnabled(False)

    def currentFile(self):
        index = self.currentIndex()
        return self.model().fileFromIndex(index)

    def layoutChanged(self):
        'file model has new contents'
        index = self.currentIndex()
        count = len(self.model())
        if index.row() == -1:
            # index is changing, fileSelected() called for us
            self.selectRow(0)
        elif index.row() >= count:
            if count:
                # index is changing, fileSelected() called for us
                self.selectRow(count-1)
            else:
                self.clearDisplay.emit()
                self.actionSecondParent.setEnabled(False)
        else:
            # redisplay previous row
            self.fileSelected()

    def fileSelected(self, index=None, *args):
        if index is None:
            index = self.currentIndex()
        data = self.model().dataFromIndex(index)
        if data:
            fromRev = self.model().revFromIndex(index)
            self.fileRevSelected.emit(data['path'], fromRev, data['status'])
            self.actionSecondParent.setEnabled(data['wasmerged'])
        else:
            self.clearDisplay.emit()
            self.actionSecondParent.setEnabled(False)

    def selectFile(self, filename):
        'Select given file, if found, else the first file'
        index = self.model().indexFromFile(filename)
        if index:
            self.setCurrentIndex(index)
            self.fileSelected(index)
        elif self.model().count():
            self.selectRow(0)

    def fileActivated(self, index, alternate=False):
        selFile = self.model().fileFromIndex(index)
        if alternate:
            self.navigate(selFile)
        else:
            self.diffNavigate(selFile)

    def navigate(self, filename=None):
        self._navigate(filename, FileLogDialog, self._nav_dialogs)

    def diffNavigate(self, filename=None):
        self._navigate(filename, FileDiffDialog, self._diff_dialogs)

    def vdiff(self):
        filename = self.currentFile()
        if filename is None:
            return
        model = self.model()
        pats = [filename]
        opts = {'change':model._ctx.rev()}
        dlg = visdiff.visualdiff(model.repo.ui, model.repo, pats, opts)
        if dlg:
            dlg.exec_()

    def vdifflocal(self):
        filename = self.currentFile()
        if filename is None:
            return
        model = self.model()
        pats = [filename]
        assert type(model._ctx.rev()) is int
        opts = {'rev':['rev(%d)' % (model._ctx.rev())]}
        dlg = visdiff.visualdiff(model.repo.ui, model.repo, pats, opts)
        if dlg:
            dlg.exec_()

    def editfile(self):
        filename = self.currentFile()
        if filename is None:
            return
        model = self.model()
        repo = model.repo
        rev = model._ctx.rev()
        if rev is None:
            files = [repo.wjoin(filename)]
            wctxactions.edit(self, repo.ui, repo, files)
        else:
            base, _ = visdiff.snapshot(repo, [filename], repo[rev])
            files = [os.path.join(base, filename)]
            wctxactions.edit(self, repo.ui, repo, files)

    def editlocal(self):
        filename = self.currentFile()
        if filename is None:
            return
        model = self.model()
        repo = model.repo
        path = repo.wjoin(filename)
        wctxactions.edit(self, repo.ui, repo, [path])

    def revertfile(self):
        filename = self.currentFile()
        if filename is None:
            return
        model = self.model()
        repo = model.repo
        rev = model._ctx.rev()
        if rev is None:
            rev = model._ctx.p1().rev()
        dlg = revert.RevertDialog(repo, filename, rev, self)
        dlg.exec_()

    def _navigate(self, filename, dlgclass, dlgdict):
        if not filename:
            filename = self.currentFile()
        model = self.model()
        if filename is not None and len(model.repo.file(filename))>0:
            if filename not in dlgdict:
                dlg = dlgclass(model.repo, filename,
                               repoviewer=self.window())
                dlgdict[filename] = dlg
                ufname = hglib.tounicode(filename)
                dlg.setWindowTitle(_('Hg file log viewer - %s') % ufname)
                dlg.setWindowIcon(qtlib.geticon('hg-log'))
            dlg = dlgdict[filename]
            dlg.goto(model._ctx.rev())
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

    def createActions(self):
        self.actionShowAllMerge = QAction(_('Show All'), self)
        self.actionShowAllMerge.setToolTip(
            _('Toggle display of all files and the direction they were merged'))
        self.actionShowAllMerge.setCheckable(True)
        self.actionShowAllMerge.setChecked(False)
        self.actionSecondParent = QAction(_('Other'), self)
        self.actionSecondParent.setToolTip(
            _('Toggle display of diffs to second (other) parent'))
        self.actionSecondParent.setCheckable(True)
        self.actionSecondParent.setChecked(False)
        self.actionSecondParent.setEnabled(False)

        self._actions = {}
        for name, desc, icon, key, tip, cb in [
            ('navigate', _('File history'), 'hg-log', 'Shift+Return',
              _('Show the history of the selected file'), self.navigate),
            ('diffnavigate', _('Compare file revisions'), 'compare-files', None,
              _('Compare revisions of the selected file'), self.diffNavigate),
            ('diff', _('Visual Diff'), 'visualdiff', 'Ctrl+D',
              _('View file changes in external diff tool'), self.vdiff),
            ('ldiff', _('Visual Diff to Local'), 'ldiff', 'Shift+Ctrl+D',
              _('View changes to current in external diff tool'),
              self.vdifflocal),
            ('edit', _('View at Revision'), 'view-at-revision', 'Alt+Ctrl+E',
              _('View file as it appeared at this revision'), self.editfile),
            ('ledit', _('Edit Local'), 'edit-file', 'Shift+Ctrl+E',
              _('Edit current file in working copy'), self.editlocal),
            ('revert', _('Revert to Revision'), 'hg-revert', 'Alt+Ctrl+T',
              _('Revert file(s) to contents at this revision'),
              self.revertfile),
            ]:
            act = QAction(desc, self)
            if icon:
                act.setIcon(qtlib.getmenuicon(icon))
            if key:
                act.setShortcut(key)
            if tip:
                act.setStatusTip(tip)
            if cb:
                act.triggered.connect(cb)
            self._actions[name] = act
            self.addAction(act)

    def contextMenuEvent(self, event):
        if not self.contextmenu:
            self.contextmenu = QMenu(self)
            for act in ['diff', 'ldiff', 'edit', 'ledit', 'revert',
                        'navigate', 'diffnavigate']:
                if act:
                    self.contextmenu.addAction(self._actions[act])
                else:
                    self.contextmenu.addSeparator()
        self.contextmenu.exec_(event.globalPos())

    def resizeEvent(self, event):
        if self.model() is not None:
            vp_width = self.viewport().width()
            col_widths = [self.columnWidth(i) \
                        for i in range(1, self.model().columnCount())]
            col_width = vp_width - sum(col_widths)
            col_width = max(col_width, 50)
            self.setColumnWidth(0, col_width)
        QTableView.resizeEvent(self, event)

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
            urls.append(QUrl.fromLocalFile(os.path.join(base, path)))
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

# resolve.py - TortoiseHg merge conflict resolve
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

import os

from mercurial import merge as mergemod

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, cmdui, wctxactions, visdiff

MARGINS = (8, 0, 0, 0)

class ResolveDialog(QDialog):
    def __init__(self, repo, parent=None):
        super(ResolveDialog, self).__init__(parent)
        self.setWindowFlags(Qt.Window)
        self.setWindowTitle(_('Resolve conflicts - %s') % repo.displayname)
        self.setWindowIcon(qtlib.geticon('merge'))
        self.repo = repo

        s = QSettings()
        self.restoreGeometry(s.value('resolve/geom').toByteArray())

        box = QVBoxLayout()
        box.setSpacing(5)
        self.setLayout(box)

        self.stlabel = QLabel()
        box.addWidget(self.stlabel)

        unres = qtlib.LabeledSeparator(_('Unresolved conflicts'))
        self.layout().addWidget(unres)

        hbox = QHBoxLayout()
        hbox.setSpacing(0)
        hbox.setContentsMargins(*MARGINS)
        self.layout().addLayout(hbox)

        self.utree = PathsTree(self.repo, self)
        hbox.addWidget(self.utree)

        vbox = QVBoxLayout()
        vbox.setContentsMargins(*MARGINS)
        hbox.addLayout(vbox)
        auto = QPushButton(_('Auto Resolve'))
        auto.setToolTip(_('Attempt automatic merge'))
        auto.clicked.connect(lambda: self.merge('internal:merge'))
        manual = QPushButton(_('Manual Resolve'))
        manual.setToolTip(_('Merge with selected merge tool'))
        manual.clicked.connect(self.merge)
        local = QPushButton(_('Take Local'))
        local.setToolTip(_('Accept the local file version (yours)'))
        local.clicked.connect(lambda: self.merge('internal:local'))
        other = QPushButton(_('Take Other'))
        other.setToolTip(_('Accept the other file version (theirs)'))
        other.clicked.connect(lambda: self.merge('internal:other'))
        res = QPushButton(_('Mark as Resolved'))
        res.setToolTip(_('Mark this file as resolved'))
        res.clicked.connect(self.markresolved)
        vbox.addWidget(auto)
        vbox.addWidget(manual)
        vbox.addWidget(local)
        vbox.addWidget(other)
        vbox.addWidget(res)
        vbox.addStretch(1)
        self.ubuttons = (auto, manual, local, other, res)

        res = qtlib.LabeledSeparator(_('Resolved conflicts'))
        self.layout().addWidget(res)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(*MARGINS)
        hbox.setSpacing(0)
        self.layout().addLayout(hbox)

        self.rtree = PathsTree(self.repo, self)
        hbox.addWidget(self.rtree)

        vbox = QVBoxLayout()
        vbox.setContentsMargins(*MARGINS)
        hbox.addLayout(vbox)
        edit = QPushButton(_('Edit File'))
        edit.setToolTip(_('Edit resolved file'))
        edit.clicked.connect(self.edit)
        v3way = QPushButton(_('3-Way Diff'))
        v3way.setToolTip(_('Visual three-way diff'))
        v3way.clicked.connect(self.v3way)
        vp0 = QPushButton(_('Diff to Local'))
        vp0.setToolTip(_('Visual diff between resolved file and first parent'))
        vp0.clicked.connect(self.vp0)
        vp1 = QPushButton(_('Diff to Other'))
        vp1.setToolTip(_('Visual diff between resolved file and second parent'))
        vp1.clicked.connect(self.vp1)
        ures = QPushButton(_('Mark as Unresolved'))
        ures.setToolTip(_('Mark this file as unresolved'))
        ures.clicked.connect(self.markunresolved)
        vbox.addWidget(edit)
        vbox.addWidget(v3way)
        vbox.addWidget(vp0)
        vbox.addWidget(vp1)
        vbox.addWidget(ures)
        vbox.addStretch(1)
        self.rbuttons = (edit, vp0, ures)
        self.rmbuttons = (vp1, v3way)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(*MARGINS)
        hbox.setSpacing(4)
        self.layout().addLayout(hbox)

        self.tcombo = ToolsCombo(self.repo, self)
        hbox.addWidget(QLabel(_('Detected merge/diff tools:')))
        hbox.addWidget(self.tcombo)
        hbox.addStretch(1)

        out = qtlib.LabeledSeparator(_('Command output'))
        self.layout().addWidget(out)
        self.cmd = cmdui.Widget(True, self)
        self.cmd.commandFinished.connect(self.refresh)
        self.cmd.show_output(True)
        self.layout().addWidget(self.cmd)

        BB = QDialogButtonBox
        bbox = QDialogButtonBox(BB.Ok|BB.Close)
        bbox.button(BB.Ok).setText('Refresh')
        bbox.accepted.connect(self.refresh)
        bbox.rejected.connect(self.reject)
        self.layout().addWidget(bbox)
        self.bbox = bbox

        self.refresh()
        self.utree.selectAll()
        self.utree.setFocus()
        repo.configChanged.connect(self.configChanged)
        repo.repositoryChanged.connect(self.repositoryChanged)

    def repositoryChanged(self):
        self.refresh()

    def getSelectedPaths(self, tree):
        paths = []
        repo = self.repo
        if not tree.selectionModel():
            return paths
        for idx in tree.selectionModel().selectedRows():
            path = hglib.fromunicode(idx.data().toString())
            paths.append(repo.wjoin(path))
        return paths

    def merge(self, tool=False):
        if not tool:
            tool = self.tcombo.readValue()
        cmd = ['resolve', '--repository', self.repo.root]
        if tool:
            cmd += ['--tool='+tool]
        paths = self.getSelectedPaths(self.utree)
        if paths:
            self.cmd.run(cmd + paths)

    def markresolved(self):
        paths = self.getSelectedPaths(self.utree)
        if paths:
            self.cmd.run(['resolve', '--repository', self.repo.root,
                          '--mark'] + paths)

    def markunresolved(self):
        paths = self.getSelectedPaths(self.rtree)
        if paths:
            self.cmd.run(['resolve', '--repository', self.repo.root,
                          '--unmark'] + paths)

    def edit(self):
        paths = self.getSelectedPaths(self.rtree)
        if paths:
            wctxactions.edit(self, self.repo.ui, self.repo, paths)

    def v3way(self):
        paths = self.getSelectedPaths(self.rtree)
        if paths:
            opts = {}
            opts['rev'] = []
            opts['tool'] = self.tcombo.readValue()
            visdiff.visualdiff(self.repo.ui, self.repo, paths, opts)

    def vp0(self):
        paths = self.getSelectedPaths(self.rtree)
        if paths:
            opts = {}
            opts['rev'] = [str(self.repo.parents()[0].rev()), '.']
            opts['tool'] = self.tcombo.readValue()
            visdiff.visualdiff(self.repo.ui, self.repo, paths, opts)

    def vp1(self):
        paths = self.getSelectedPaths(self.rtree)
        if paths:
            opts = {}
            opts['rev'] = [str(self.repo.parents()[1].rev()), '.']
            opts['tool'] = self.tcombo.readValue()
            visdiff.visualdiff(self.repo.ui, self.repo, paths, opts)

    def configChanged(self):
        'repository has detected a change to config files'
        self.tcombo.reset()

    def refresh(self):
        repo = self.repo

        def selpaths(tree):
            paths = []
            if not tree.selectionModel():
                return paths
            for idx in tree.selectionModel().selectedRows():
                path = hglib.fromunicode(idx.data().toString())
                paths.append(path)
            return paths

        ms = mergemod.mergestate(self.repo)
        u, r = [], []
        for path in ms:
            if ms[path] == 'u':
                u.append(path)
            else:
                r.append(path)
        paths = selpaths(self.utree)
        self.utree.setModel(PathsModel(u, self))
        self.utree.resizeColumnToContents(0)
        self.utree.resizeColumnToContents(1)

        model = self.utree.model()
        smodel = self.utree.selectionModel()
        sflags = QItemSelectionModel.Select | QItemSelectionModel.Columns
        for i, p in enumerate(u):
            if p in paths:
                smodel.select(model.index(i, 0), sflags)
                smodel.select(model.index(i, 1), sflags)

        def uchanged(l):
            full = not l.isEmpty()
            for b in self.ubuttons:
                b.setEnabled(full)
        self.utree.selectionModel().selectionChanged.connect(uchanged)
        uchanged(smodel.selection())

        paths = selpaths(self.rtree)
        self.rtree.setModel(PathsModel(r, self))
        self.rtree.resizeColumnToContents(0)
        self.rtree.resizeColumnToContents(1)

        model = self.rtree.model()
        smodel = self.rtree.selectionModel()
        for i, p in enumerate(r):
            if p in paths:
                smodel.select(model.index(i, 0), sflags)
                smodel.select(model.index(i, 1), sflags)

        def rchanged(l):
            full = not l.isEmpty()
            for b in self.rbuttons:
                b.setEnabled(full)
            merge = len(self.repo.parents()) > 1
            for b in self.rmbuttons:
                b.setEnabled(full and merge)
        self.rtree.selectionModel().selectionChanged.connect(rchanged)
        rchanged(smodel.selection())

        if u:
            txt = _('There are merge <b>conflicts</b> to be resolved')
        elif r:
            txt = _('All conflicts are resolved.')
        else:
            txt = _('There are no conflicting file merges.')
        self.stlabel.setText(u'<h2>' + txt + u'</h2>')

    def reject(self):
        s = QSettings()
        s.setValue('resolve/geom', self.saveGeometry())
        if len(self.utree.model()):
            main = _('Quit without finishing resolve?')
            text = _('Unresolved conflicts remain. Are you sure?')
            labels = ((QMessageBox.Yes, _('&Quit')),
                      (QMessageBox.No, _('Cancel')))
            if not qtlib.QuestionMsgBox(_('Confirm Exit'), main, text,
                                labels=labels, parent=self):
                return
        super(ResolveDialog, self).reject()

class PathsTree(QTreeView):
    def __init__(self, repo, parent):
        QTreeView.__init__(self, parent)
        self.repo = repo
        self.setSelectionMode(QTreeView.ExtendedSelection)
        self.setSortingEnabled(True)

    def dragObject(self):
        urls = []
        for index in self.selectionModel().selectedRows():
            index = index.sibling(index.row(), COL_PATH)
            path = index.data(Qt.DisplayRole).toString()
            u = QUrl()
            u.setPath('file://' + os.path.join(self.repo.root, path))
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
        return QTreeView.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        d = event.pos() - self.pressPos
        if d.manhattanLength() < QApplication.startDragDistance():
            return QTreeView.mouseMoveEvent(self, event)
        elapsed = self.pressTime.msecsTo(QTime.currentTime())
        if elapsed < QApplication.startDragTime():
            return QTreeView.mouseMoveEvent(self, event)
        self.dragObject()
        return QTreeView.mouseMoveEvent(self, event)

class PathsModel(QAbstractTableModel):
    def __init__(self, pathlist, parent):
        QAbstractTableModel.__init__(self, parent)
        self.headers = (_('Path'), _('Extension'))
        self.rows = []
        for path in pathlist:
            name, ext = os.path.splitext(path)
            self.rows.append([path, ext])

    def __len__(self):
        return len(self.rows)

    def rowCount(self, parent):
        if parent.isValid():
            return 0 # no child
        return len(self.rows)

    def columnCount(self, parent):
        if parent.isValid():
            return 0 # no child
        return len(self.headers)

    def data(self, index, role):
        if not index.isValid():
            return QVariant()
        if role == Qt.DisplayRole:
            data = self.rows[index.row()][index.column()]
            return QVariant(hglib.tounicode(data))
        return QVariant()

    def headerData(self, col, orientation, role):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return QVariant()
        else:
            return QVariant(self.headers[col])

class ToolsCombo(QComboBox):
    def __init__(self, repo, parent):
        QComboBox.__init__(self, parent)
        self.setEditable(False)
        self.loaded = False
        self.default = _('<default>')
        self.addItem(self.default)
        self.repo = repo

    def reset(self):
        self.loaded = False
        self.clear()
        self.addItem(self.default)

    def showPopup(self):
        if not self.loaded:
            self.loaded = True
            self.clear()
            self.addItem(self.default)
            for t in self.repo.mergetools:
                self.addItem(hglib.tounicode(t))
        QComboBox.showPopup(self)

    def readValue(self):
        if self.loaded:
            text = self.currentText()
            if text != self.default:
                return hglib.fromunicode(text)
        else:
            return None

def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    from tortoisehg.hgqt import thgrepo
    repo = thgrepo.repository(ui, path=paths.find_root())
    return ResolveDialog(repo, None)

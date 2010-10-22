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

from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, cmdui, thgrepo, wctxactions, visdiff

MARGINS = (8, 0, 0, 0)

class ResolveDialog(QDialog):
    def __init__(self, repo, parent=None):
        super(ResolveDialog, self).__init__(parent)
        self.setWindowTitle(_('Resolve conflicts - %s') % repo.displayname)
        self.setWindowIcon(qtlib.geticon('merge'))
        self.repo = repo

        s = QSettings()
        self.restoreGeometry(s.value('resolve/geom').toByteArray())

        box = QVBoxLayout()
        box.setContentsMargins(*MARGINS)
        box.setSpacing(5)
        self.setLayout(box)

        unres = qtlib.LabeledSeparator(_('Unresolved conflicts'))
        self.layout().addWidget(unres)

        hbox = QHBoxLayout()
        hbox.setSpacing(0)
        hbox.setContentsMargins(*MARGINS)
        self.layout().addLayout(hbox)

        self.utree = PathsTree(self)
        hbox.addWidget(self.utree)

        vbox = QVBoxLayout()
        vbox.setContentsMargins(*MARGINS)
        hbox.addLayout(vbox)
        auto = QPushButton(_('Auto'))
        auto.setToolTip(_('Attempt automatic merge'))
        auto.clicked.connect(lambda: self.merge('internal:merge'))
        manual = QPushButton(_('Manual'))
        manual.setToolTip(_('Merge with selected merge tool'))
        manual.clicked.connect(self.merge)
        local = QPushButton(_('Take Local'))
        local.setToolTip(_('Accept the local file version (yours)'))
        local.clicked.connect(lambda: self.merge('internal:local'))
        other = QPushButton(_('Take Other'))
        other.setToolTip(_('Accept the other file version (theirs)'))
        other.clicked.connect(lambda: self.merge('internal:other'))
        res = QPushButton(_('Mark'))
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

        self.rtree = PathsTree(self)
        hbox.addWidget(self.rtree)

        vbox = QVBoxLayout()
        vbox.setContentsMargins(*MARGINS)
        hbox.addLayout(vbox)
        edit = QPushButton(_('Edit'))
        edit.setToolTip(_('Edit resolved file'))
        edit.clicked.connect(self.edit)
        v3way = QPushButton(_('3-Way Diff'))
        v3way.setToolTip(_('Visual three-way diff'))
        v3way.clicked.connect(self.v3way)
        vp0 = QPushButton(_('To Local'))
        vp0.setToolTip(_('Visual diff between resolved file and first parent'))
        vp0.clicked.connect(self.vp0)
        vp1 = QPushButton(_('To Other'))
        vp1.setToolTip(_('Visual diff between resolved file and second parent'))
        vp1.clicked.connect(self.vp1)
        ures = QPushButton(_('Unmark'))
        ures.setToolTip(_('Mark this file as unresolved'))
        ures.clicked.connect(self.markunresolved)
        vbox.addWidget(edit)
        vbox.addWidget(v3way)
        vbox.addWidget(vp0)
        vbox.addWidget(vp1)
        vbox.addWidget(ures)
        vbox.addStretch(1)
        self.rbuttons = (edit, v3way, vp0, vp1, ures)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(*MARGINS)
        hbox.setSpacing(4)
        self.layout().addLayout(hbox)

        self.tcombo = ToolsCombo(self.repo)
        self.stlabel = QLabel()
        hbox.addWidget(QLabel(_('Detected merge/diff tools:')))
        hbox.addWidget(self.tcombo)
        hbox.addSpacing(12)
        hbox.addWidget(self.stlabel)
        hbox.addStretch(1)

        out = qtlib.LabeledSeparator(_('Command output'))
        self.layout().addWidget(out)
        self.cmd = cmdui.Widget(True, self)
        self.cmd.commandFinished.connect(self.refresh)
        self.cmd.show_output(True)
        self.layout().addWidget(self.cmd)

        self.refresh()
        self.utree.selectAll()
        self.utree.setFocus()
        repo.configChanged.connect(self.configChanged)

    def getSelectedPaths(self, tree):
        paths = []
        repo = self.repo
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
        cmdlines = []
        for path in self.getSelectedPaths(self.utree):
            cmdlines.append(cmd + [path])
        if cmdlines:
            self.cmd.run(*cmdlines)

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
            repo = self.repo
            wctxactions.edit(self, repo.ui, repo, paths)

    def v3way(self):
        paths = self.getSelectedPaths(self.rtree)
        if paths:
            repo = self.repo
            visdiff.visualdiff(repo.ui, repo, paths, {'rev':[]})

    def vp0(self):
        paths = self.getSelectedPaths(self.rtree)
        if paths:
            repo = self.repo
            pair = [str(repo.parents()[0].rev()), '.']
            visdiff.visualdiff(repo.ui, repo, paths, {'rev':pair})

    def vp1(self):
        paths = self.getSelectedPaths(self.rtree)
        if paths:
            repo = self.repo
            pair = [str(repo.parents()[1].rev()), '.']
            visdiff.visualdiff(repo.ui, repo, paths, {'rev':pair})

    def configChanged(self):
        'repository has detected a change to config files'
        self.tcombo.reset()

    def refresh(self):
        repo = self.repo
        ms = mergemod.mergestate(repo)
        u, r = [], []
        for path in ms:
            if ms[path] == 'u':
                u.append(path)
            else:
                r.append(path)
        self.utree.setModel(PathsModel(u, self))
        self.utree.resizeColumnToContents(0)
        self.utree.resizeColumnToContents(1)
        def uchanged(l):
            for b in self.ubuttons:
                b.setEnabled(not l.isEmpty())
        self.utree.selectionModel().selectionChanged.connect(uchanged)
        uchanged(QItemSelection())
        self.rtree.setModel(PathsModel(r, self))
        self.rtree.resizeColumnToContents(0)
        self.rtree.resizeColumnToContents(1)
        def rchanged(l):
            for b in self.rbuttons:
                b.setEnabled(not l.isEmpty())
        self.rtree.selectionModel().selectionChanged.connect(rchanged)
        rchanged(QItemSelection())
        
        if u:
            self.stlabel.setText(_('<b>Conflicts</b> must be resolved'))
        else:
            self.stlabel.setText(_('Test merge results, then commit'))

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
    def __init__(self, repo, parent=None):
        QTreeView.__init__(self, parent)
        self.repo = repo
        self.setSelectionMode(QTreeView.ExtendedSelection)

    def dragObject(self):
        urls = []
        for index in self.selectionModel().selectedRows():
            path = self.model().getRow(index)[COL_PATH]
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
    def __init__(self, pathlist, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.headers = (_('Path'), _('Ext'))
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
    def __init__(self, repo, parent=None):
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
    repo = thgrepo.repository(ui, path=paths.find_root())
    return ResolveDialog(repo, None)

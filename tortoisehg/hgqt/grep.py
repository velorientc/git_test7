# grep.py - Working copy and history search
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import re

from mercurial import ui, hg, error

from tortoisehg.hgqt import htmlui, visdiff
from tortoisehg.util import paths, hglib
from tortoisehg.util.i18n import _

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# This widget can be embedded in any application that would like to
# prove search features

# Technical Debt
#  uhm, do some searching
#  draggable matches from history
#  tortoisehg.editor with line number
#  smart visual diffs
#  context menu for matches
#  emit errors to parent's status bar
#  emit to parent's progress bar

class SearchWidget(QWidget):
    def __init__(self, root=None, parent=None):
        QWidget.__init__(self, parent)

        root = paths.find_root(root)
        repo = hg.repository(ui.ui(), path=root)
        assert(repo)

        layout = QVBoxLayout()
        layout.setMargin(0)
        self.setLayout(layout)

        hbox = QHBoxLayout()
        hbox.setMargin(0)
        lbl = QLabel(_('Regexp:'))
        le = QLineEdit()
        lbl.setBuddy(le)
        cb = QComboBox()
        cb.addItems([_('Working Copy'),
                     _('Parent Revision'),
                     _('All History')])
        chk = QCheckBox(_('Ignore case'))

        hbox.addWidget(lbl)
        hbox.addWidget(le, 1)
        hbox.addWidget(cb)
        hbox.addWidget(chk)
        layout.addLayout(hbox)

        tv = MatchTree(repo, self)
        tv.setItemsExpandable(False)
        tv.setRootIsDecorated(False)
        tm = MatchModel()
        tv.setModel(tm)
        layout.addWidget(tv)
        le.returnPressed.connect(self.searchActivated)
        self.repo = repo
        self.tv, self.le, self.cb, self.chk = tv, le, cb, chk

        if not parent:
            self.setWindowTitle(_('TortoiseHg Search'))
            self.resize(800, 500)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            return super(SearchWidget, self).keyPressEvent(event)

    def searchActivated(self):
        'User pressed [Return] in QLineEdit'
        model = self.tv.model()
        model.reset()
        regexp = hglib.fromunicode(self.le.text())
        icase = self.chk.isChecked()
        if not regexp:
            return
        self.le.selectAll()
        mode = self.cb.currentIndex()
        if mode == 0:
            ctx = self.repo[None]
        elif mode == 1:
            ctx = self.repo['.']
        else:
            # Full blown 'hg grep' call
            # show revision, user columns
            # hg grep [-i] -afn regexp
            return

        # hide revision, user columns
        # walk ctx.manifest, load file data, perform regexp, fill model
        model.appendRow('path', 'line', 'rev', 'user', 'text')

COL_PATH     = 0
COL_LINE     = 1
COL_REVISION = 2  # Hidden if wctx
COL_USER     = 3  # Hidden if wctx
COL_TEXT     = 4

class MatchTree(QTreeView):
    def __init__(self, repo, parent=None):
        QTreeView.__init__(self, parent)
        self.repo = repo
        self.setSelectionMode(QTreeView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.connect(self, SIGNAL('customContextMenuRequested(const QPoint &)'),
                     self.customContextMenuRequested)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_D and event.modifiers() == Qt.ControlModifier:
            selfiles = []
            for index in self.selectedRows():
                # TODO: record rev, prune dups
                selfiles.append(self.model().getRow(index)[COL_PATH])
            visdiff.visualdiff(self.repo.ui, self.repo, selfiles, {})
        else:
            return super(MatchTree, self).keyPressEvent(event)

    def dragObject(self):
        urls = []
        for index in self.selectedRows():
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

    def mouseMoveEvent(self, event):
        self.dragObject()

    def customContextMenuRequested(self, point):
        selrows = []
        for index in self.selectedRows():
            path, line, rev, user, text = self.model().getRow(index)
            selrows.append((rev, path, line))
        point = self.mapToGlobal(point)
        #action = wctxactions.wctxactions(self, point, self.repo, selrows)
        #if action:
        #    self.emit(SIGNAL('menuAction()'))

    def selectedRows(self):
        return self.selectionModel().selectedRows()



class MatchModel(QAbstractTableModel):
    def __init__(self, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.rows = []
        self.headers = (_('File'), _('Line'), _('Revision'), _('User'),
                        _('Match Text'))

    def rowCount(self, parent):
        return len(self.rows)

    def columnCount(self, parent):
        return len(self.headers)

    def data(self, index, role):
        if not index.isValid():
            return QVariant()
        if role == Qt.DisplayRole:
            return QVariant(self.rows[index.row()][index.column()])
        return QVariant()

    def headerData(self, col, orientation, role):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return QVariant()
        else:
            return QVariant(self.headers[col])

    def flags(self, index):
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled
        return flags

    def sort(self, col, order):
        self.emit(SIGNAL("layoutAboutToBeChanged()"))
        self.rows.sort(lambda x, y: cmp(x[col], y[col]))
        if order == Qt.DescendingOrder:
            self.rows.reverse()
        self.emit(SIGNAL("layoutChanged()"))

    ## Custom methods

    def appendRow(self, *args):
        self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows))
        self.rows.append(args)
        self.endInsertRows()
        self.emit(SIGNAL("dataChanged()"))

    def reset(self):
        self.beginRemoveRows(QModelIndex(), 0, len(self.rows)-1)
        self.rows = []
        self.endRemoveRows()

def run(ui, *pats, **opts):
    return SearchWidget()

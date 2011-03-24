# logcolumns.py - select and reorder columns in log model
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from tortoisehg.hgqt import qtlib
from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import repomodel

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class ColumnSelectDialog(QDialog):
    def __init__(self, all, curcolumns=None, parent=None):
        QDialog.__init__(self, parent)

        self.setWindowTitle(_('Workbench Log Columns'))
        self.setWindowFlags(self.windowFlags() & \
                            ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(250, 265)

        self.curcolumns = curcolumns
        if not self.curcolumns:
            s = QSettings()
            cols = s.value('workbench/columns').toStringList()
            if cols:
                self.curcolumns = [c for c in cols if c in all]
            else:
                self.curcolumns = all
        self.disabled = [c for c in all if c not in self.curcolumns]

        layout = QVBoxLayout()
        layout.setMargin(0)
        self.setLayout(layout)

        list = QListWidget()
        # enabled cols are listed in sorted order
        for c in self.curcolumns:
            item = QListWidgetItem(repomodel.COLUMNNAMES[c])
            item.columnid = c
            item.setFlags(Qt.ItemIsSelectable |
                          Qt.ItemIsEnabled |
                          Qt.ItemIsDragEnabled |
                          Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            list.addItem(item)
        # disabled cols are listed last
        for c in self.disabled:
            item = QListWidgetItem(repomodel.COLUMNNAMES[c])
            item.columnid = c
            item.setFlags(Qt.ItemIsSelectable |
                          Qt.ItemIsEnabled |
                          Qt.ItemIsDragEnabled |
                          Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            list.addItem(item)
        list.setDragDropMode(QListView.InternalMove)
        layout.addWidget(list)
        self.list = list

        layout.addWidget(QLabel(_('Drag to change order')))

        # dialog buttons
        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        self.apply_button = bb.button(BB.Apply)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(BB.Ok).setDefault(True)
        layout.addWidget(bb)

    def accept(self):
        s = QSettings()
        cols = []
        for i in xrange(self.list.count()):
            item = self.list.item(i)
            if item.checkState() == Qt.Checked:
                cols.append(item.columnid)
        s.setValue('workbench/columns', cols)
        QDialog.accept(self)

    def reject(self):
        QDialog.reject(self)

def run(ui, *pats, **opts):
    return ColumnSelectDialog(repomodel.ALLCOLUMNS)

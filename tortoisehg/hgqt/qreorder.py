# qreorder.py - reorder unapplied MQ patches
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from hgext import mq

from tortoisehg.hgqt import qtlib, thgrepo
from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# TODO:
#  This approach will nuke any user configured guards
#  It would be nice to show changeset summaries (status bar?)
#  Support qrename within this dialog
#  Explicit refresh

class QReorderDialog(QDialog):
    def __init__(self, repo, parent=None):
        QDialog.__init__(self, parent)

        self.setWindowTitle(_('Reorder Unapplied Patches'))
        self.setWindowFlags(self.windowFlags() &
                            ~Qt.WindowContextHelpButtonHint)

        self.repo = repo
        self.cached = None
        repo.repositoryChanged.connect(self.refresh)

        layout = QVBoxLayout()
        layout.setMargin(4)
        self.setLayout(layout)

        hb = QHBoxLayout()
        hb.setMargin(2)
        lbl = QLabel(_('Repository:'))
        hb.addWidget(lbl)
        le = QLineEdit()
        hb.addWidget(le)
        le.setReadOnly(True)
        le.setFont(qtlib.getfont('fontlist').font())
        le.setText(repo.displayname)
        le.setFocusPolicy(Qt.NoFocus)
        layout.addLayout(hb)
        hl = qtlib.LabeledSeparator('')
        layout.addWidget(hl)

        class PatchListWidget(QListWidget):
            def __init__(self, parent=None, dialog=None):
                QListWidget.__init__(self, parent)
                self.dlg=dialog
                self.setCurrentRow(0)
            def focusInEvent(self, e):
                i = self.item(self.currentRow())
                if i:
                    self.dlg.showSummary(i)
                QListWidget.focusInEvent(self, e)

        ugb = QGroupBox(_('Unapplied Patches - drag to reorder'))
        ugb.setLayout(QVBoxLayout())
        ugb.layout().setContentsMargins(*(0,)*4)
        self.ulw = PatchListWidget(dialog=self)
        self.ulw.setDragDropMode(QListView.InternalMove)
        ugb.layout().addWidget(self.ulw)
        self.ulw.currentItemChanged.connect(lambda:
                self.showSummary(self.ulw.item(self.ulw.currentRow())))
        layout.addWidget(ugb)

        agb = QGroupBox(_('Applied Patches'))
        agb.setLayout(QVBoxLayout())
        agb.layout().setContentsMargins(*(0,)*4)
        self.alw = PatchListWidget(dialog=self)
        agb.layout().addWidget(self.alw)
        self.alw.currentItemChanged.connect(lambda:
                self.showSummary(self.alw.item(self.alw.currentRow())))
        layout.addWidget(agb)

        slbl = QLabel(_('Summary:'))
        layout.addWidget(slbl)
        self.summ = QTextEdit()
        self.summ.setFont(qtlib.getfont('fontcomment').font())
        self.summ.setMinimumWidth(500)  # min 80 chars
        self.summ.setMaximumHeight(100)
        self.summ.setReadOnly(True)
        self.summ.setFocusPolicy(Qt.NoFocus)
        layout.addWidget(self.summ)

        self.refresh()

        # dialog buttons
        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        self.apply_button = bb.button(BB.Apply)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(BB.Ok).setDefault(True)
        layout.addWidget(bb)

        self.ulw.setFocus()

    def refresh(self):
        patchnames = self.repo.mq.series[:]
        applied = [p.name for p in self.repo.mq.applied]
        if (patchnames, applied) == self.cached:
            return

        alw, ulw = self.alw, self.ulw
        for p in reversed(patchnames):
            item = QListWidgetItem(hglib.tounicode(p))
            if p in applied:
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                item.setForeground(QColor(111,111,111)) # gray, like disabled
                alw.addItem(item)
            else:
                item.setFlags(Qt.ItemIsSelectable |
                              Qt.ItemIsEnabled |
                              Qt.ItemIsDragEnabled)
                ulw.addItem(item)
        self.cached = patchnames, applied

    def showSummary(self, item):
        patchname = hglib.fromunicode(item.text())
        q = self.repo.mq
        txt = hglib.toutf('\n'.join(mq.patchheader(q.join(patchname)).message))
        self.summ.setText(txt)

    def accept(self):
        lines = []
        for i in xrange(self.alw.count()-1, -1, -1):
            item = self.alw.item(i)
            lines.append(hglib.fromunicode(item.text()))
        for i in xrange(self.ulw.count()-1, -1, -1):
            item = self.ulw.item(i)
            lines.append(hglib.fromunicode(item.text()))
        if lines:
            fp = self.repo.opener('patches/series', 'wb')
            fp.write('\n'.join(lines))
            fp.close()
        QDialog.accept(self)

    def reject(self):
        QDialog.reject(self)

def run(ui, *pats, **opts):
    repo = thgrepo.repository(None, paths.find_root())
    return QReorderDialog(repo)

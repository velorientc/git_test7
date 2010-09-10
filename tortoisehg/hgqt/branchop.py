# branchop.py - branch operations dialog for TortoiseHg commit tool
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.hgqt.i18n import _
from tortoisehg.util import hglib

from tortoisehg.hgqt import qtlib

class BranchOpDialog(QDialog):
    'Dialog for manipulating wctx.branch()'
    def __init__(self, repo, oldbranchop, parent=None):
        QDialog.__init__(self, parent)
        layout = QVBoxLayout()
        self.setLayout(layout)
        wctx = repo[None]

        if len(wctx.parents()) == 2:
            lbl = QLabel('<b>'+_('Select branch of merge commit')+'</b>')
            layout.addWidget(lbl)
            branchCombo = QComboBox()
            for p in wctx.parents():
                branchCombo.addItem(hglib.tounicode(p.branch()))
            layout.addWidget(branchCombo)
        else:
            text = '<b>'+_('Changes take effect on next commit')+'</b>'
            lbl = QLabel(text)
            layout.addWidget(lbl)

            grid = QGridLayout()
            nochange = QRadioButton(_('No branch changes'))
            newbranch = QRadioButton(_('Open a new named branch'))
            closebranch = QRadioButton(_('Close current named branch'))
            branchCombo = QComboBox()
            branchCombo.setEditable(True)
            for name in hglib.getlivebranch(repo):
                if name == wctx.branch():
                    continue
                branchCombo.addItem(hglib.tounicode(name))
            branchCombo.activated.connect(self.accept)
            grid.addWidget(nochange, 0, 0)
            grid.addWidget(newbranch, 1, 0)
            grid.addWidget(branchCombo, 1, 1)
            grid.addWidget(closebranch, 2, 0)
            layout.addLayout(grid)

            newbranch.toggled.connect(branchCombo.setEnabled)
            branchCombo.setEnabled(False)
            if wctx.branch() == 'default':
                closebranch.setEnabled(False)
            if oldbranchop is None:
                nochange.setChecked(True)
            elif oldbranchop == False:
                closebranch.setChecked(True)
            else:
                bc = branchCombo
                names = [bc.itemText(i) for i in xrange(bc.count())]
                if oldbranchop in names:
                    bc.setCurrentIndex(names.index(oldbranchop))
                else:
                    bc.addItem(oldbranchop)
                    bc.setCurrentIndex(len(names))
                newbranch.setChecked(True)
            self.closebranch = closebranch

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(BB.Ok).setAutoDefault(True)
        layout.addWidget(bb)
        self.bb = bb
        self.branchCombo = branchCombo

    def keyPressEvent(self, event):
        # todo - is this necessary for a derivation of QDialog?
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() == Qt.ControlModifier:
                self.accept()  # Ctrl+Enter
            return
        elif event.key() == Qt.Key_Escape:
            self.reject()
            return
        return super(QDialog, self).keyPressEvent(event)

    def accept(self):
        '''Branch operation is one of:
            None  - leave wctx branch name untouched
            False - close current branch
            str   - open new named branch
        '''
        if self.branchCombo.isEnabled():
            self.branchop = self.branchCombo.currentText()
        elif self.closebranch.isChecked():
            self.branchop = False
        else:
            self.branchop = None
        QDialog.accept(self)

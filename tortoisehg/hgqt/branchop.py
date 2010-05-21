# branchop.py - branch operations dialog for TortoiseHg commit tool
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import util

from PyQt4 import QtCore, QtGui

from tortoisehg.hgqt.i18n import _
from tortoisehg.util import hglib

from tortoisehg.hgqt import qtlib

class BranchOpDialog(QtGui.QDialog):
    'Dialog for manipulating wctx.branch()'
    def __init__(self, repo, parent=None):
        QtGui.QDialog.__init__(self, parent)
        layout = QtGui.QVBoxLayout()
        self.setLayout(layout)
        wctx = repo[None]

        if len(wctx.parents()) == 2:
            lbl = QtGui.QLabel('<b>'+_('Select branch of merge commit')+'</b>')
            layout.addWidget(lbl)
            branchCombo = QtGui.QComboBox()
            for p in wctx.parents():
                branchCombo.addItem(hglib.tounicode(p.branch()))
            layout.addWidget(branchCombo)
        else:
            text = '<b>'+_('Changes take effect on next commit')+'</b>'
            lbl = QtGui.QLabel(text)
            layout.addWidget(lbl)

            grid = QtGui.QGridLayout()
            nochange = QtGui.QRadioButton(_('No Branch Changes'))
            newbranch = QtGui.QRadioButton(_('Open a new named branch'))
            closebranch = QtGui.QRadioButton(_('Close current named branch'))
            branchCombo = QtGui.QComboBox()
            branchCombo.setEditable(True)
            for name in hglib.getlivebranch(repo):
                if name == wctx.branch():
                    continue
                branchCombo.addItem(hglib.tounicode(name))
            grid.addWidget(nochange, 0, 0)
            grid.addWidget(newbranch, 1, 0)
            grid.addWidget(branchCombo, 1, 1)
            grid.addWidget(closebranch, 2, 0)
            layout.addLayout(grid)

            nochange.setChecked(True)
            newbranch.toggled.connect(branchCombo.setEnabled)
            branchCombo.setEnabled(False)
            if wctx.branch() == 'default':
                closebranch.setEnabled(False)

        BB = QtGui.QDialogButtonBox
        bb = QtGui.QDialogButtonBox(BB.Ok|BB.Cancel)
        self.connect(bb, QtCore.SIGNAL("accepted()"),
                     self, QtCore.SLOT("accept()"))
        self.connect(bb, QtCore.SIGNAL("rejected()"),
                     self, QtCore.SLOT("reject()"))
        bb.button(BB.Ok).setDefault(True)
        layout.addWidget(bb)
        self.bb = bb

    def keyPressEvent(self, event):
        # todo - is this necessary for a derivation of QDialog?
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if event.modifiers() == QtCore.Qt.ControlModifier:
                self.accept()  # Ctrl+Enter
            return
        elif event.key() == QtCore.Qt.Key_Escape:
            self.reject()
            return
        return super(QtGui.QDialog, self).keyPressEvent(event)

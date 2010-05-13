# quickop.py - TortoiseHg's dialog for quick dirstate operations
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import hg, ui, cmdutil, util

from PyQt4 import QtCore, QtGui

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, shlib, paths

from tortoisehg.hgqt import qtlib, status

LABELS = { 'add': (_('Select files to add'), _('Add')),
           'forget': (_('Select files to forget'), _('Forget')),
           'revert': (_('Select files to revert'), _('Revert')),
           'remove': (_('Select files to remove'), _('Remove')),}

# Technical Debt
#  command running functionality
#  perhaps a check for no applicable files

class QuickOpDialog(QtGui.QDialog):
    """ Dialog for performing quick dirstate operations """
    def __init__(self, command, pats, parent=None):
        QtGui.QDialog.__init__(self, parent)
        self.pats = pats

        # Handle rm alias
        if command == 'rm':
            command = 'remove'
        self.command = command

        repo = hg.repository(ui.ui(), path=paths.find_root())
        assert repo
        os.chdir(repo.root)
        self.setWindowTitle('%s - hg %s' % (hglib.get_reponame(repo), command))

        layout = QtGui.QVBoxLayout()
        self.setLayout(layout)

        lbl = QtGui.QLabel(LABELS[command][0])
        layout.addWidget(lbl)

        types = { 'add'    : 'I?',
                  'forget' : 'MAR!C',
                  'revert' : 'MAR!',
                  'remove' : 'MAR!CI?',
                }
        filetypes = types[self.command]

        opts = {}
        for s, val in status.statusTypes.iteritems():
            opts[val.name] = s in filetypes

        stwidget = status.StatusWidget(pats, opts, self)
        layout.addWidget(stwidget, 1)

        if self.command == 'revert':
            ## no backup checkbox
            chk = QtGui.QCheckBox(_('Do not save backup files (*.orig)'))
            layout.addWidget(chk)

        BB = QtGui.QDialogButtonBox
        bb = QtGui.QDialogButtonBox(BB.Ok|BB.Cancel)
        self.connect(bb, QtCore.SIGNAL("accepted()"),
                     self, QtCore.SLOT("accept()"))
        self.connect(bb, QtCore.SIGNAL("rejected()"),
                     self, QtCore.SLOT("reject()"))
        bb.button(BB.Ok).setDefault(True)
        bb.button(BB.Ok).setText(LABELS[command][1])
        layout.addWidget(bb)

        s = QtCore.QSettings()
        stwidget.restoreState(s.value('quickop/state').toByteArray())
        self.restoreGeometry(s.value('quickop/geom').toByteArray())
        self.stwidget = stwidget

    def accept(self):
        s = QtCore.QSettings()
        s.setValue('quickop/state', self.stwidget.saveState())
        s.setValue('quickop/geom', self.saveGeometry())
        QtGui.QDialog.accept(self)

    def reject(self):
        s = QtCore.QSettings()
        s.setValue('quickop/state', self.stwidget.saveState())
        s.setValue('quickop/geom', self.saveGeometry())
        QtGui.QDialog.reject(self)

def run(ui, *pats, **opts):
    pats = hglib.canonpaths(pats)
    if opts.get('canonpats'):
        pats = list(pats) + opts['canonpats']
    return QuickOpDialog(opts.get('alias'), pats)

# quickop.py - TortoiseHg's dialog for quick dirstate operations
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import hg, ui, cmdutil, util

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.hgqt.i18n import _
from tortoisehg.util import hglib, shlib, paths

from tortoisehg.hgqt import qtlib, status, cmdui

LABELS = { 'add': (_('Checkmark files to add'), _('Add')),
           'forget': (_('Checkmark files to forget'), _('Forget')),
           'revert': (_('Checkmark files to revert'), _('Revert')),
           'remove': (_('Checkmark files to remove'), _('Remove')),}

class QuickOpDialog(QDialog):
    """ Dialog for performing quick dirstate operations """
    def __init__(self, command, pats, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowFlags(self.windowFlags() &
                            ~Qt.WindowContextHelpButtonHint)
        self.pats = pats

        # Handle rm alias
        if command == 'rm':
            command = 'remove'
        self.command = command

        repo = hg.repository(ui.ui(), path=paths.find_root())
        assert repo
        os.chdir(repo.root)
        self.setWindowTitle('%s - hg %s' % (hglib.get_reponame(repo), command))

        layout = QVBoxLayout()
        self.setLayout(layout)

        hbox = QHBoxLayout()
        lbl = QLabel(LABELS[command][0])
        slbl = QLabel()
        hbox.addWidget(lbl)
        hbox.addStretch(1)
        hbox.addWidget(slbl)
        self.status_label = slbl
        layout.addLayout(hbox)

        types = { 'add'    : 'I?',
                  'forget' : 'MAR!C',
                  'revert' : 'MAR!',
                  'remove' : 'MAR!CI?',
                }
        filetypes = types[self.command]

        opts = {}
        for s, val in status.statusTypes.iteritems():
            opts[val.name] = s in filetypes

        stwidget = status.StatusWidget(pats, opts, repo.root, self)
        layout.addWidget(stwidget, 1)

        if self.command == 'revert':
            ## no backup checkbox
            chk = QCheckBox(_('Do not save backup files (*.orig)'))
            self.chk = chk
            layout.addWidget(chk)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        self.connect(bb, SIGNAL("accepted()"), self, SLOT("accept()"))
        self.connect(bb, SIGNAL("rejected()"), self, SLOT("reject()"))
        bb.button(BB.Ok).setDefault(True)
        bb.button(BB.Ok).setText(LABELS[command][1])
        layout.addWidget(bb)
        self.bb = bb

        cmd = cmdui.Widget()
        cmd.commandStarted.connect(self.commandStarted)
        cmd.commandFinished.connect(self.commandFinished)
        cmd.commandCanceling.connect(self.commandCanceled)
        layout.addWidget(cmd)
        cmd.setHidden(True)
        self.cmd = cmd

        s = QSettings()
        stwidget.restoreState(s.value('quickop/state').toByteArray())
        self.restoreGeometry(s.value('quickop/geom').toByteArray())
        self.stwidget = stwidget

        self.connect(self.stwidget, SIGNAL('errorMessage'),
                self.cmd.pmon.set_text)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() == Qt.ControlModifier:
                self.accept()  # Ctrl+Enter
            return
        elif event.key() == Qt.Key_Escape:
            self.reject()
            return
        return super(QDialog, self).keyPressEvent(event)

    def commandStarted(self):
        self.cmd.setShown(True)
        self.bb.button(QDialogButtonBox.Ok).setEnabled(False)

    def commandFinished(self, wrapper):
        self.bb.button(QDialogButtonBox.Ok).setEnabled(True)
        if wrapper.data is not 0:
            self.cmd.show_output(True)
        else:
            self.reject()

    def commandCanceled(self):
        self.bb.button(QDialogButtonBox.Ok).setEnabled(True)

    def accept(self):
        cmdline = [self.command]
        if hasattr(self, 'chk') and self.chk.isChecked():
            cmdline.append('--no-backup')
        files = self.stwidget.getChecked()
        if files:
            cmdline.extend(files)
        else:
            qtlib.WarningMsgBox(_('No files selected'),
                                _('No operation to perform'),
                                parent=self)
            return
        self.cmd.run(cmdline)

    def reject(self):
        if self.cmd.core.is_running():
            self.cmd.core.cancel()
        else:
            s = QSettings()
            s.setValue('quickop/state', self.stwidget.saveState())
            s.setValue('quickop/geom', self.saveGeometry())
            QDialog.reject(self)

def run(ui, *pats, **opts):
    pats = hglib.canonpaths(pats)
    if opts.get('canonpats'):
        pats = list(pats) + opts['canonpats']
    return QuickOpDialog(opts.get('alias'), pats)

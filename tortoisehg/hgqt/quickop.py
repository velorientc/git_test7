# quickop.py - TortoiseHg's dialog for quick dirstate operations
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import sys

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.hgqt.i18n import _
from tortoisehg.util import hglib, shlib, paths

from tortoisehg.hgqt import qtlib, status, cmdui, thgrepo

LABELS = { 'add': (_('Checkmark files to add'), _('Add')),
           'forget': (_('Checkmark files to forget'), _('Forget')),
           'revert': (_('Checkmark files to revert'), _('Revert')),
           'remove': (_('Checkmark files to remove'), _('Remove')),}

class QuickOpDialog(QDialog):
    """ Dialog for performing quick dirstate operations """
    def __init__(self, repo, command, pats, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowFlags(self.windowFlags() &
                            ~Qt.WindowContextHelpButtonHint)
        self.pats = pats
        self.repo = repo
        os.chdir(repo.root)

        # Handle rm alias
        if command == 'rm':
            command = 'remove'
        self.command = command

        self.setWindowTitle('%s - hg %s' % (repo.displayname, command))

        layout = QVBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setMargin(0)
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

        self.statusbar = cmdui.ThgStatusBar(self)
        self.statusbar.setSizeGripEnabled(False)
        stwidget.showMessage.connect(self.statusbar.showMessage)

        self.cmd = cmd = cmdui.Runner(parent=self)
        cmd.commandStarted.connect(self.commandStarted)
        cmd.commandFinished.connect(self.commandFinished)
        cmd.commandCanceling.connect(self.commandCanceled)
        cmd.progress.connect(self.statusbar.progress)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(BB.Ok).setDefault(True)
        bb.button(BB.Ok).setText(LABELS[command][1])
        layout.addWidget(bb)
        self.bb = bb

        hbox = QHBoxLayout()
        hbox.setMargin(0)
        hbox.setContentsMargins(*(0,)*4)
        hbox.addWidget(self.statusbar)
        hbox.addWidget(self.bb)
        layout.addLayout(hbox)

        s = QSettings()
        stwidget.restoreState(s.value('quickop/state').toByteArray())
        self.restoreGeometry(s.value('quickop/geom').toByteArray())
        self.stwidget = stwidget
        self.stwidget.refreshWctx()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() == Qt.ControlModifier:
                self.accept()  # Ctrl+Enter
            return
        elif event.matches(QKeySequence.Refresh):
            self.stwidget.refreshWctx()
        elif event.key() == Qt.Key_Escape:
            self.reject()
            return
        return super(QDialog, self).keyPressEvent(event)

    def commandStarted(self):
        self.bb.button(QDialogButtonBox.Ok).setEnabled(False)

    def commandFinished(self, ret):
        self.bb.button(QDialogButtonBox.Ok).setEnabled(True)
        if ret is 0:
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


instance = None
class HeadlessQuickop(QWidget):
    def __init__(self, repo, cmdline):
        QWidget.__init__(self)
        self.cmd = cmdui.Runner(parent=self)
        self.cmd.commandFinished.connect(self.commandFinished)
        self.cmd.run(cmdline)
        self.hide()

    def commandFinished(self, ret):
        if ret == 0:
            sys.exit(0)

def run(ui, *pats, **opts):
    pats = hglib.canonpaths(pats)
    if opts.get('canonpats'):
        pats = list(pats) + opts['canonpats']

    from tortoisehg.util import paths
    from tortoisehg.hgqt import thgrepo
    repo = thgrepo.repository(ui, path=paths.find_root())

    command = opts['alias']
    imm = repo.ui.config('tortoisehg', 'immediate', '')
    if command in imm.lower():
        cmdline = [command] + pats
        global instance
        instance = HeadlessQuickop(repo, cmdline)
        return None
    else:
        return QuickOpDialog(command, pats)

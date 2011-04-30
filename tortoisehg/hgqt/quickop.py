# quickop.py - TortoiseHg's dialog for quick dirstate operations
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import sys

from mercurial import util

from tortoisehg.util import hglib, shlib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, status, cmdui

from PyQt4.QtCore import *
from PyQt4.QtGui import *

LABELS = { 'add': (_('Checkmark files to add'), _('Add')),
           'forget': (_('Checkmark files to forget'), _('Forget')),
           'revert': (_('Checkmark files to revert'), _('Revert')),
           'remove': (_('Checkmark files to remove'), _('Remove')),}

ICONS = { 'add': 'fileadd',
           'forget': 'hg-remove',
           'revert': 'hg-revert',
           'remove': 'hg-remove',}

class QuickOpDialog(QDialog):
    """ Dialog for performing quick dirstate operations """
    def __init__(self, repo, command, pats, parent):
        QDialog.__init__(self, parent)
        self.setWindowFlags(Qt.Window)
        self.pats = pats
        self.repo = repo
        os.chdir(repo.root)

        # Handle rm alias
        if command == 'rm':
            command = 'remove'
        self.command = command

        self.setWindowTitle(_('%s - hg %s') % (repo.displayname, command))
        self.setWindowIcon(qtlib.geticon(ICONS[command]))

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

        opts['checkall'] = True # pre-check all matching files
        stwidget = status.StatusWidget(repo, pats, opts, self)
        layout.addWidget(stwidget, 1)

        if self.command == 'revert':
            ## no backup checkbox
            chk = QCheckBox(_('Do not save backup files (*.orig)'))
            self.chk = chk
            layout.addWidget(chk)

        self.statusbar = cmdui.ThgStatusBar(self)
        self.statusbar.setSizeGripEnabled(False)
        stwidget.showMessage.connect(self.statusbar.showMessage)

        self.cmd = cmd = cmdui.Runner(True, self)
        cmd.commandStarted.connect(self.commandStarted)
        cmd.commandFinished.connect(self.commandFinished)
        cmd.progress.connect(self.statusbar.progress)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Close)
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
        stwidget.loadSettings(s, 'quickop')
        self.restoreGeometry(s.value('quickop/geom').toByteArray())
        if hasattr(self, 'chk'):
            self.chk.setChecked(s.value('quickop/nobackup', True).toBool())
        self.stwidget = stwidget
        self.stwidget.refreshWctx()
        QShortcut(QKeySequence('Ctrl+Return'), self, self.accept)
        QShortcut(QKeySequence('Ctrl+Enter'), self, self.accept)
        QShortcut(QKeySequence.Refresh, self, self.stwidget.refreshWctx)
        QShortcut(QKeySequence('Escape'), self, self.reject)

    def commandStarted(self):
        self.bb.button(QDialogButtonBox.Ok).setEnabled(False)

    def commandFinished(self, ret):
        self.bb.button(QDialogButtonBox.Ok).setEnabled(True)
        if ret == 0:
            shlib.shell_notify(self.files)
            self.reject()

    def accept(self):
        cmdline = [self.command]
        if hasattr(self, 'chk') and self.chk.isChecked():
            cmdline.append('--no-backup')
        files = self.stwidget.getChecked()
        if not files:
            qtlib.WarningMsgBox(_('No files selected'),
                                _('No operation to perform'),
                                parent=self)
            return
        if self.command == 'remove':
            wctx = self.repo[None]
            for wfile in files:
                if wfile not in wctx:
                    try:
                        util.unlink(wfile)
                    except EnvironmentError:
                        pass
                    files.remove(wfile)
        if files:
            cmdline.extend(files)
            self.files = files
            self.cmd.run(cmdline)
        else:
            self.reject()

    def reject(self):
        if self.cmd.core.running():
            self.cmd.core.cancel()
        elif not self.stwidget.canExit():
            return
        else:
            s = QSettings()
            self.stwidget.saveSettings(s, 'quickop')
            s.setValue('quickop/geom', self.saveGeometry())
            if hasattr(self, 'chk'):
                s.setValue('quickop/nobackup', self.chk.isChecked())
            QDialog.reject(self)


instance = None
class HeadlessQuickop(QWidget):
    def __init__(self, repo, cmdline):
        QWidget.__init__(self)
        self.files = cmdline[1:]
        os.chdir(repo.root)
        self.cmd = cmdui.Runner(True, self)
        self.cmd.commandFinished.connect(self.commandFinished)
        self.cmd.run(cmdline)
        self.hide()

    def commandFinished(self, ret):
        if ret == 0:
            shlib.shell_notify(self.files)
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
        return QuickOpDialog(repo, command, pats, None)

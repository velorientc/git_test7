# revert.py - File revert dialog for TortoiseHg
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import util, error

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui, qtlib

class RevertDialog(QDialog):
    def __init__(self, repo, wfile, rev, parent):
        super(RevertDialog, self).__init__(parent)
        self.setWindowTitle(_('Revert - %s') % repo.displayname)

        f = self.windowFlags()
        self.setWindowFlags(f & ~Qt.WindowContextHelpButtonHint)
        self.repo = repo
        self.wfile = repo.wjoin(wfile)
        self.rev = str(rev)

        self.setLayout(QVBoxLayout())

        lbl = QLabel(_('<b>Revert %s to its contents at revision %d?</b>') % (
            wfile, rev))
        self.layout().addWidget(lbl)

        self.allchk = QCheckBox(_('Revert all files to this revision'))
        self.layout().addWidget(self.allchk)

        self.cmd = cmdui.Widget()
        self.cmd.show_output(False)
        self.cmd.stbar.setVisible(False)
        self.cmd.commandFinished.connect(self.finished)
        self.layout().addWidget(self.cmd, 1)

        BB = QDialogButtonBox
        bbox = QDialogButtonBox(BB.Ok|BB.Cancel)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        self.layout().addWidget(bbox)
        self.bbox = bbox

    def accept(self):
        if self.allchk.isChecked():
            if not qtlib.QuestionMsgBox(_('Confirm Revert'),
                     _('Reverting all files will discard changes and '
                       'leave affected files in a modified state.<br>'
                       '<br>Are you sure you want to use revert?<br><br>'
                       '(use update to checkout another revision)'),
                       parent=self):
                return
            cmdline = ['revert', '--repository', self.repo.root, '--all']
        else:
            cmdline = ['revert', '--repository', self.repo.root, self.wfile]
        cmdline += ['--rev', self.rev]
        self.cmd.show_output(True)
        self.cmd.stbar.setVisible(True)
        self.cmd.run(cmdline)

    def finished(self, ret):
        if ret == 0:
            self.bbox.button(QDialogButtonBox.Ok).setVisible(False)
            self.bbox.button(QDialogButtonBox.Cancel).setText(_('Close'))

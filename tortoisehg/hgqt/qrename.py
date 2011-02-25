# qrename.py - QRename dialog for TortoiseHg
#
# Copyright 2010 Steve Borho <steve@borho.org>
# Copyright 2010 Johan Samyn <johan.samyn@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui

class QRenameDialog(QDialog):

    output = pyqtSignal(QString, QString)
    makeLogVisible = pyqtSignal(bool)

    def __init__(self, repo, patchname, parent):
        super(QRenameDialog, self).__init__(parent)
        self.setWindowTitle(_('Patch rename - %s') % repo.displayname)

        f = self.windowFlags()
        self.setWindowFlags(f & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(400)
        self.repo = repo
        self.oldpatchname = patchname
        self.newpatchname = ''

        self.setLayout(QVBoxLayout())

        lbl = QLabel(_('Rename patch <b>%s</b> to:') % (self.oldpatchname))
        self.layout().addWidget(lbl)

        self.le = QLineEdit(hglib.tounicode(self.oldpatchname))
        self.layout().addWidget(self.le)

        self.cmd = cmdui.Runner(True, self)
        self.cmd.output.connect(self.output)
        self.cmd.makeLogVisible.connect(self.makeLogVisible)
        self.cmd.commandFinished.connect(self.reject)

        BB = QDialogButtonBox
        bbox = QDialogButtonBox(BB.Ok|BB.Cancel)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        self.layout().addWidget(bbox)
        self.bbox = bbox

        self.focus = self.le

    def accept(self):
        self.newpatchname = hglib.fromunicode(self.le.text())
        if self.newpatchname != self.oldpatchname:
            cmdline = ['qrename', '--repository', self.repo.root, '--',
                       self.oldpatchname, self.newpatchname]
            self.cmd.run(cmdline)
        else:
            self.close()


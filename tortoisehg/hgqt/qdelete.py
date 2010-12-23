# qdelete.py - QDelete dialog for TortoiseHg
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui

class QDeleteDialog(QDialog):
    output = pyqtSignal(QString, QString)
    makeLogVisible = pyqtSignal(bool)

    def __init__(self, repo, patches, parent):
        super(QDeleteDialog, self).__init__(parent)
        self.setWindowTitle(_('Patch remove - %s') % repo.displayname)

        f = self.windowFlags()
        self.setWindowFlags(f & ~Qt.WindowContextHelpButtonHint)
        self.repo = repo
        self.patches = patches

        self.setLayout(QVBoxLayout())

        lbl = QLabel(_('<b>Remove patches from queue?<ul><li>%s</ul></b>') %
                     '<li>'.join(patches))
        self.layout().addWidget(lbl)

        self.keepchk = QCheckBox(_('Keep patch files'))
        self.keepchk.setChecked(True)
        self.layout().addWidget(self.keepchk)

        self.cmd = cmdui.Runner()
        self.cmd.output.connect(self.output)
        self.cmd.makeLogVisible.connect(self.makeLogVisible)

        BB = QDialogButtonBox
        bbox = QDialogButtonBox(BB.Ok|BB.Cancel)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        self.layout().addWidget(bbox)
        self.bbox = bbox

    def accept(self):
        def finished(ret):
            self.repo.decrementBusyCount()
            self.reject()
        cmdline = ['qdelete', '--repository', self.repo.root]
        if self.keepchk.isChecked():
            cmdline += ['--keep']
        cmdline += self.patches
        self.repo.incrementBusyCount()
        self.cmd.commandFinished.connect(finished)
        self.cmd.run(cmdline)

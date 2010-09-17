# p4pending.py - Display pending p4 changelists, created by perfarce extension
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import error

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, cslist, cmdui


class PerforcePending(QDialog):
    'Dialog for selecting a revision'
    def __init__(self, repo, pending, parent):
        QDialog.__init__(self, parent)
        self.repo = repo
        self.pending = pending # dict of changelist -> hash tuple

        layout = QVBoxLayout()
        self.setLayout(layout)

        clcombo = QComboBox()
        layout.addWidget(clcombo)

        self.cslist = cslist.ChangesetList()
        layout.addWidget(self.cslist)

        self.cmd = cmdui.Widget()
        self.cmd.commandFinished.connect(self.commandFinished)
        self.cmd.setVisible(False)
        layout.addWidget(self.cmd)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel|BB.Discard)
        bb.rejected.connect(self.reject)
        bb.button(BB.Discard).setText('Revert')
        bb.button(BB.Discard).setAutoDefault(False)
        bb.button(BB.Discard).clicked.connect(self.revert)
        bb.button(BB.Discard).setEnabled(False)
        bb.button(BB.Ok).setText('Submit')
        bb.button(BB.Ok).setAutoDefault(True)
        bb.button(BB.Ok).clicked.connect(self.submit)
        bb.button(BB.Ok).setEnabled(False)
        layout.addWidget(bb)
        self.bb = bb

        clcombo.activated[QString].connect(self.p4clActivated)
        for changelist in self.pending:
            clcombo.addItem(hglib.tounicode(changelist))
        self.p4clActivated(clcombo.currentText())

        self.setWindowTitle(_('Pending Perforce Changelists - %s') % 
                            repo.displayname)

    @pyqtSlot(QString)
    def p4clActivated(self, curcl):
        'User has selected a changelist, fill cslist'
        curcl = hglib.fromunicode(curcl)
        try:
            hashes = self.pending[curcl]
            revs = [self.repo[hash] for hash in hashes]
        except error.Abort, e:
            revs = []
        self.cslist.clear()
        self.cslist.update(self.repo, revs)
        sensitive = not curcl.endswith('(submitted)')
        self.bb.button(QDialogButtonBox.Ok).setEnabled(sensitive)
        self.bb.button(QDialogButtonBox.Discard).setEnabled(sensitive)
        self.curcl = curcl

    def submit(self):
        assert(self.curcl.endswith('(pending)'))
        cmdline = ['p4submit', '--verbose', '--repository',
                self.repo.root, self.curcl[:-10]]
        self.repo.incrementBusyCount()
        self.cmd.setVisible(True)
        self.cmd.show_output(True)
        self.bb.button(QDialogButtonBox.Ok).setEnabled(False)
        self.bb.button(QDialogButtonBox.Discard).setEnabled(False)
        self.cmd.run(cmdline)

    def revert(self):
        assert(self.curcl.endswith('(pending)'))
        cmdline = ['p4revert', '--verbose', '--repository',
                self.repo.root, self.curcl[:-10]]
        self.repo.incrementBusyCount()
        self.cmd.setVisible(True)
        self.cmd.show_output(True)
        self.bb.button(QDialogButtonBox.Ok).setEnabled(False)
        self.bb.button(QDialogButtonBox.Discard).setEnabled(False)
        self.cmd.run(cmdline)

    def commandFinished(self, ret):
        self.repo.decrementBusyCount()
        self.bb.button(QDialogButtonBox.Ok).setEnabled(True)
        self.bb.button(QDialogButtonBox.Discard).setEnabled(True)
        if ret == 0:
            self.reject()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.cmd.isRunning():
                self.cmd.cancel()
            else:
                self.reject()
        else:
            return super(PerforcePending, self).keyPressEvent(event)

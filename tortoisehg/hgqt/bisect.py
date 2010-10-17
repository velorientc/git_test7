# bisect.py - Bisect dialog for TortoiseHg
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import util, error

from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui, qtlib, thgrepo

class BisectDialog(QDialog):
    def __init__(self, repo, opts, parent=None):
        super(BisectDialog, self).__init__(parent)
        self.setWindowTitle(_('Bisect - %s') % repo.displayname)
        #self.setWindowIcon(qtlib.geticon('bisect'))

        f = self.windowFlags()
        self.setWindowFlags(f & ~Qt.WindowContextHelpButtonHint)
        self.repo = repo

        # base layout box
        box = QVBoxLayout()
        box.setSpacing(6)
        self.setLayout(box)

        hbox = QHBoxLayout()
        hbox.addWidget(QLabel(_('Known good revision:')))
        gle = QLineEdit()
        hbox.addWidget(gle, 1)
        gb = QPushButton(_('Accept'))
        hbox.addWidget(gb)
        box.addLayout(hbox)

        hbox = QHBoxLayout()
        hbox.addWidget(QLabel(_('Known bad revision:')))
        ble = QLineEdit()
        ble.setEnabled(False)
        hbox.addWidget(ble, 1)
        bb = QPushButton(_('Accept'))
        bb.setEnabled(False)
        hbox.addWidget(bb)
        box.addLayout(hbox)

        ## command widget
        self.cmd = cmdui.Widget()
        self.cmd.show_output(True)
        box.addWidget(self.cmd, 1)

        hbox = QHBoxLayout()
        goodrev = QPushButton(_('Revision is Good'))
        hbox.addWidget(goodrev)
        badrev = QPushButton(_('Revision is Bad'))
        hbox.addWidget(badrev)
        skiprev = QPushButton(_('Skip this Revision'))
        hbox.addWidget(skiprev)
        box.addLayout(hbox)

        lbl = QLabel()
        box.addWidget(lbl)

        self.nextbuttons = (goodrev, badrev, skiprev)
        for b in self.nextbuttons:
            b.setEnabled(False)

        def cmdFinished(ret):
            out = self.cmd.core.get_rawoutput()
            if out.startswith('The first bad revision is:'):
                lbl.setText(_('Culprit found.'))
                return
            for b in self.nextbuttons:
                b.setEnabled(True)
            lbl.setText(_('Test this revision and report findings.'))
        self.cmd.commandFinished.connect(cmdFinished)

        prefix = ['bisect', '--repository', repo.root]

        def gverify():
            good = hglib.fromunicode(gle.text().simplified())
            try:
                ctx = repo[good]
                self.goodrev = ctx.rev()
                gb.setEnabled(False)
                gle.setEnabled(False)
                bb.setEnabled(True)
                ble.setEnabled(True)
                ble.setFocus()
            except (util.Abort, error.RepoLookupError), e:
                self.cmd.core.stbar.showMessage(hglib.tounicode(str(e)))
        def bverify():
            bad = hglib.fromunicode(ble.text().simplified())
            try:
                ctx = repo[bad]
                self.badrev = ctx.rev()
                ble.setEnabled(False)
                bb.setEnabled(False)
                cmds = []
                cmds.append(prefix + ['--reset'])
                cmds.append(prefix + ['--good', str(self.goodrev)])
                cmds.append(prefix + ['--bad', str(self.badrev)])
                self.cmd.run(*cmds)
            except (util.Abort, error.RepoLookupError), e:
                self.cmd.core.stbar.showMessage(hglib.tounicode(str(e)))

        gb.pressed.connect(gverify)
        bb.pressed.connect(bverify)
        gle.returnPressed.connect(gverify)
        ble.returnPressed.connect(bverify)

        def goodrevision():
            for b in self.nextbuttons:
                b.setEnabled(False)
            self.cmd.run(prefix + ['--good', '.'])
        def badrevision():
            for b in self.nextbuttons:
                b.setEnabled(False)
            self.cmd.run(prefix + ['--bad', '.'])
        def skiprevision():
            for b in self.nextbuttons:
                b.setEnabled(False)
            self.cmd.run(prefix + ['--skip', '.'])
        goodrev.clicked.connect(goodrevision)
        badrev.clicked.connect(badrevision)
        skiprev.clicked.connect(skiprevision)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        super(BisectDialog, self).keyPressEvent(event)


def run(ui, *pats, **opts):
    repo = thgrepo.repository(ui, path=paths.find_root())
    return BisectDialog(repo, opts)

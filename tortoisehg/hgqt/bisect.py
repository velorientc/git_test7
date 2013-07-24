# bisect.py - Bisect dialog for TortoiseHg
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import util, error

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui, qtlib

class BisectDialog(QDialog):
    def __init__(self, repoagent, opts, parent=None):
        super(BisectDialog, self).__init__(parent)
        self.setWindowTitle(_('Bisect - %s') % repoagent.rawRepo().displayname)
        self.setWindowIcon(qtlib.geticon('hg-bisect'))

        self.setWindowFlags(Qt.Window)
        self._repoagent = repoagent

        # base layout box
        box = QVBoxLayout()
        box.setSpacing(6)
        self.setLayout(box)

        hbox = QHBoxLayout()
        hbox.addWidget(QLabel(_('Known good revision:')))
        self._gle = gle = QLineEdit()
        gle.setText(opts.get('good', ''))
        hbox.addWidget(gle, 1)
        self._gb = gb = QPushButton(_('Accept'))
        hbox.addWidget(gb)
        box.addLayout(hbox)

        hbox = QHBoxLayout()
        hbox.addWidget(QLabel(_('Known bad revision:')))
        self._ble = ble = QLineEdit()
        ble.setText(opts.get('bad', ''))
        ble.setEnabled(False)
        hbox.addWidget(ble, 1)
        self._bb = bb = QPushButton(_('Accept'))
        bb.setEnabled(False)
        hbox.addWidget(bb)
        box.addLayout(hbox)

        ## command widget
        self.cmd = cmdui.Widget(True, True, self)
        self.cmd.setShowOutput(True)
        box.addWidget(self.cmd, 1)

        hbox = QHBoxLayout()
        goodrev = QPushButton(_('Revision is Good'))
        hbox.addWidget(goodrev)
        badrev = QPushButton(_('Revision is Bad'))
        hbox.addWidget(badrev)
        skiprev = QPushButton(_('Skip this Revision'))
        hbox.addWidget(skiprev)
        box.addLayout(hbox)

        hbox = QHBoxLayout()
        box.addLayout(hbox)
        self._lbl = lbl = QLabel()
        hbox.addWidget(lbl)
        hbox.addStretch(1)
        closeb = QPushButton(_('Close'))
        hbox.addWidget(closeb)
        closeb.clicked.connect(self.reject)

        self.nextbuttons = (goodrev, badrev, skiprev)
        for b in self.nextbuttons:
            b.setEnabled(False)
        self.lastrev = None

        self.cmd.commandFinished.connect(self._cmdFinished)

        gb.pressed.connect(self._verifyGood)
        bb.pressed.connect(self._verifyBad)
        gle.returnPressed.connect(self._verifyGood)
        ble.returnPressed.connect(self._verifyBad)

        goodrev.clicked.connect(self._markGoodRevision)
        badrev.clicked.connect(self._markBadRevision)
        skiprev.clicked.connect(self._skipRevision)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        super(BisectDialog, self).keyPressEvent(event)

    @property
    def repo(self):
        return self._repoagent.rawRepo()

    def _bisectcmd(self, *args, **opts):
        opts['repository'] = self.repo.root
        return hglib.buildcmdargs('bisect', *args, **opts)

    @pyqtSlot(int)
    def _cmdFinished(self, ret):
        lbl = self._lbl
        if ret != 0:
            lbl.setText(_('Error encountered.'))
            return
        self.repo.dirstate.invalidate()
        ctx = self.repo['.']
        if ctx.rev() == self.lastrev:
            lbl.setText(_('Culprit found.'))
            return
        self.lastrev = ctx.rev()
        for b in self.nextbuttons:
            b.setEnabled(True)
        lbl.setText('%s: %d (%s) -> %s' % (_('Revision'), ctx.rev(), ctx,
                    _('Test this revision and report findings. '
                      '(good/bad/skip)')))

    @pyqtSlot()
    def _verifyGood(self):
        good = hglib.fromunicode(self._gle.text().simplified())
        try:
            ctx = self.repo[good]
            self.goodrev = ctx.rev()
            self._gb.setEnabled(False)
            self._gle.setEnabled(False)
            self._bb.setEnabled(True)
            self._ble.setEnabled(True)
            self._ble.setFocus()
        except (error.LookupError, error.RepoLookupError), e:
            self.cmd.core.stbar.showMessage(hglib.tounicode(str(e)))
        except util.Abort, e:
            if e.hint:
                err = _('%s (hint: %s)') % (hglib.tounicode(str(e)),
                                            hglib.tounicode(e.hint))
            else:
                err = hglib.tounicode(str(e))
            self.cmd.core.stbar.showMessage(err)

    @pyqtSlot()
    def _verifyBad(self):
        bad = hglib.fromunicode(self._ble.text().simplified())
        try:
            ctx = self.repo[bad]
            self.badrev = ctx.rev()
            self._ble.setEnabled(False)
            self._bb.setEnabled(False)
            cmds = []
            cmds.append(self._bisectcmd(reset=True))
            cmds.append(self._bisectcmd(self.goodrev, good=True))
            cmds.append(self._bisectcmd(self.badrev, bad=True))
            self.cmd.run(*cmds)
        except (error.LookupError, error.RepoLookupError), e:
            self.cmd.core.stbar.showMessage(hglib.tounicode(str(e)))
        except util.Abort, e:
            if e.hint:
                err = _('%s (hint: %s)') % (hglib.tounicode(str(e)),
                                            hglib.tounicode(e.hint))
            else:
                err = hglib.tounicode(str(e))
            self.cmd.core.stbar.showMessage(err)

    @pyqtSlot()
    def _markGoodRevision(self):
        for b in self.nextbuttons:
            b.setEnabled(False)
        self.cmd.run(self._bisectcmd('.', good=True))

    @pyqtSlot()
    def _markBadRevision(self):
        for b in self.nextbuttons:
            b.setEnabled(False)
        self.cmd.run(self._bisectcmd('.', bad=True))

    @pyqtSlot()
    def _skipRevision(self):
        for b in self.nextbuttons:
            b.setEnabled(False)
        self.cmd.run(self._bisectcmd('.', skip=True))

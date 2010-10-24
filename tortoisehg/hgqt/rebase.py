# rebase.py - Rebase dialog for TortoiseHg
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

import os

from mercurial import util, merge as mergemod

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, csinfo, cmdui, resolve

BB = QDialogButtonBox

class RebaseDialog(QDialog):

    def __init__(self, repo, parent, **opts):
        super(RebaseDialog, self).__init__(parent)
        f = self.windowFlags()
        self.setWindowFlags(f & ~Qt.WindowContextHelpButtonHint)
        self.repo = repo
        self.opts = opts

        box = QVBoxLayout()
        box.setSpacing(8)
        box.setContentsMargins(*(6,)*4)
        self.setLayout(box)

        style = csinfo.panelstyle(selectable=True)

        srcb = QGroupBox( _('Rebase changeset and descendants'))
        srcb.setLayout(QVBoxLayout())
        srcb.layout().setContentsMargins(*(2,)*4)
        s = opts.get('source', '.')
        source = csinfo.create(self.repo, s, style, withupdate=True)
        srcb.layout().addWidget(source)
        self.layout().addWidget(srcb)

        destb = QGroupBox( _('To rebase destination'))
        destb.setLayout(QVBoxLayout())
        destb.layout().setContentsMargins(*(2,)*4)
        d = opts.get('dest', '.')
        dest = csinfo.create(self.repo, d, style, withupdate=True)
        destb.layout().addWidget(dest)
        self.layout().addWidget(destb)

        sep = qtlib.LabeledSeparator(_('Options'))
        self.layout().addWidget(sep)

        self.keepchk = QCheckBox(_('Keep original changesets'))
        self.keepchk.setChecked(opts.get('keep', False))
        self.layout().addWidget(self.keepchk)

        self.detachchk = QCheckBox(_('Force detach of rebased changesets '
                                     'from their original branch'))
        self.detachchk.setChecked(opts.get('detach', True))
        self.layout().addWidget(self.detachchk)

        sep = qtlib.LabeledSeparator(_('Status'))
        self.layout().addWidget(sep)

        self.reslabel = QLabel()
        self.reslabel.linkActivated.connect(self.linkActivated)
        self.layout().addWidget(self.reslabel)

        self.cmd = cmdui.Widget()
        self.cmd.commandFinished.connect(self.commandFinished)
        self.cmd.escapePressed.connect(self.reject)
        self.layout().addWidget(self.cmd, 2)

        bbox = QDialogButtonBox(BB.Cancel|BB.Ok)
        bbox.button(BB.Ok).setText('Rebase')
        bbox.button(BB.Cancel).setText('Abort')
        bbox.button(BB.Cancel).setEnabled(False)
        bbox.accepted.connect(self.rebase)
        bbox.rejected.connect(self.abort)
        self.layout().addWidget(bbox)
        self.bbox = bbox

        if self.checkResolve() or not (s or d):
            for w in (srcb, destb, sep, self.keepchk, self.detachchk):
                w.setHidden(True)
                self.cmd.show_output(True)

        self.setMinimumWidth(480)
        self.setMaximumHeight(800)
        self.resize(0, 340)
        self.setWindowTitle(_('Rebase - %s') % self.repo.displayname)

    def rebase(self):
        self.keepchk.setEnabled(False)
        self.detachchk.setEnabled(False)
        cmdline = ['rebase', '--repository', self.repo.root]
        cmdline += ['--config', 'ui.merge=internal:fail']
        if os.path.exists(self.repo.join('rebasestate')):
            cmdline += ['--continue']
        else:
            if self.keepchk.isChecked():
                cmdline += ['--keep']
            if self.detachchk.isChecked():
                cmdline += ['--detach']
            source = self.opts.get('source')
            dest = self.opts.get('dest')
            cmdline += ['--source', str(source), '--dest', str(dest)]
        self.repo.incrementBusyCount()
        self.cmd.run(cmdline)

    def abort(self):
        cmdline = ['rebase', '--repository', self.repo.root, '--abort']
        self.repo.incrementBusyCount()
        self.cmd.run(cmdline)

    def commandFinished(self, ret):
        self.repo.decrementBusyCount()
        if self.checkResolve() is False:
            self.reslabel.setText(_('<h3>Rebase is complete</h3>'))
            self.bbox.button(BB.Ok).setText(_('Close'))
            self.bbox.accepted.disconnect(self.rebase)
            self.bbox.accepted.connect(self.accept)

    def checkResolve(self):
        ms = mergemod.mergestate(self.repo)
        for path in ms:
            if ms[path] == 'u':
                txt = _('<h3>Rebase generated merge <b>conflicts</b> that must '
                        'be <a href="resolve"><b>resolved</b></a></h3>')
                self.bbox.button(BB.Ok).setEnabled(False)
                break
        else:
            self.bbox.button(BB.Ok).setEnabled(True)
            txt = _('<h3>You may continue the rebase</h3>')
        self.reslabel.setText(txt)

        if os.path.exists(self.repo.join('rebasestate')):
            self.bbox.button(BB.Cancel).setEnabled(True)
            self.bbox.button(BB.Ok).setText('Continue')
            return True
        else:
            self.bbox.button(BB.Cancel).setEnabled(False)
            return False

    def linkActivated(self, cmd):
        if cmd == 'resolve':
            dlg = resolve.ResolveDialog(self.repo, self)
            dlg.exec_()
        self.checkResolve()

    def reject(self):
        if os.path.exists(self.repo.join('rebasestate')):
            main = _('Rebase is incomplete, exiting is not recommended')
            text = _('Abort is recommended before exit.')
            labels = ((QMessageBox.Yes, _('&Exit')),
                      (QMessageBox.No, _('Cancel')))
            if not qtlib.QuestionMsgBox(_('Confirm Exit'), main, text,
                                        labels=labels, parent=self):
                return
        super(RebaseDialog, self).reject()

def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    from tortoisehg.hgqt import thgrepo
    repo = thgrepo.repository(ui, path=paths.find_root())
    if not opts['source'] or not opts['dest']:
        raise util.Abort('source and dest must be supplied')
    return RebaseDialog(repo, None, **opts)

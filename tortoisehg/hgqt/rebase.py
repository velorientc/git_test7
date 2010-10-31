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
from tortoisehg.hgqt import qtlib, csinfo, cmdui, resolve, commit

BB = QDialogButtonBox

class RebaseDialog(QDialog):
    showMessage = pyqtSignal(QString)

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
        self.destcsinfo = dest
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

        if 'hgsubversion' in repo.extensions():
            self.svnchk = QCheckBox(_('Rebase unpublished onto Subversion head'
                                      ' (override source, destination)'))
            self.layout().addWidget(self.svnchk)
        else:
            self.svnchk = None

        self.cmd = cmdui.Widget()
        self.cmd.commandFinished.connect(self.commandFinished)
        self.cmd.escapePressed.connect(self.reject)
        self.showMessage.connect(self.cmd.stbar.showMessage)
        self.cmd.stbar.linkActivated.connect(self.linkActivated)
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
        else:
            self.showMessage.emit(_('Checking...'))
            QTimer.singleShot(0, self.checkStatus)

        self.setMinimumWidth(480)
        self.setMaximumHeight(800)
        self.resize(0, 340)
        self.setWindowTitle(_('Rebase - %s') % self.repo.displayname)

    def checkStatus(self):
        repo = self.repo
        class CheckThread(QThread):
            def __init__(self, parent):
                QThread.__init__(self, parent)
                self.dirty = False

            def run(self):
                wctx = repo[None]
                if len(wctx.parents()) > 1:
                    self.dirty = True
                elif wctx.dirty():
                    self.dirty = True
                else:
                    ms = mergemod.mergestate(repo)
                    unresolved = False
                    for path in ms:
                        if ms[path] == 'u':
                            self.dirty = True
                            break
        def completed():
            self.th.wait()
            if self.th.dirty:
                self.bbox.button(BB.Ok).setEnabled(False)
                txt = _('Before rebase, you must <a href="commit">'
                        '<b>commit</b></a> or <a href="discard">'
                        '<b>discard</b></a> changes.')
            else:
                self.bbox.button(BB.Ok).setEnabled(True)
                txt = _('You may continue the rebase')
            self.showMessage.emit(txt)
        self.th = CheckThread(self)
        self.th.finished.connect(completed)
        self.th.start()

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
            if self.svnchk is not None and self.svnchk.isChecked():
                cmdline += ['--svn']
            else:
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
            self.showMessage.emit(_('Rebase is complete'))
            self.bbox.button(BB.Ok).setText(_('Close'))
            self.bbox.accepted.disconnect(self.rebase)
            self.bbox.accepted.connect(self.accept)

    def checkResolve(self):
        ms = mergemod.mergestate(self.repo)
        for path in ms:
            if ms[path] == 'u':
                txt = _('Rebase generated merge <b>conflicts</b> that must '
                        'be <a href="resolve"><b>resolved</b></a>')
                self.bbox.button(BB.Ok).setEnabled(False)
                break
        else:
            self.bbox.button(BB.Ok).setEnabled(True)
            txt = _('You may continue the rebase')
        self.showMessage.emit(txt)

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
        elif cmd == 'commit':
            dlg = commit.CommitDialog([], dict(root=self.repo.root), self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.exec_()
            self.destcsinfo.update(self.repo[None])
            self.checkStatus()
        elif cmd == 'discard':
            labels = [(QMessageBox.Yes, _('&Discard')),
                      (QMessageBox.No, _('Cancel'))]
            if not qtlib.QuestionMsgBox(_('Confirm Discard'), _('Discard'
                     ' outstanding changes in working directory?'),
                     labels=labels, parent=self):
                return
            def finished(ret):
                self.repo.decrementBusyCount()
                if ret == 0:
                    self.checkStatus()
            cmdline = ['update', '--clean', '--repository', self.repo.root,
                       '--rev', '.']
            self.runner = cmdui.Runner(_('Discard - TortoiseHg'), True, self)
            self.runner.commandFinished.connect(finished)
            self.repo.incrementBusyCount()
            self.runner.run(cmdline)

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
    if os.path.exists(repo.join('rebasestate')):
        print _('resuming rebase already in progress')
    elif not opts['source'] or not opts['dest']:
        print _('abort: source and dest must be supplied')
        import sys; sys.exit()
    return RebaseDialog(repo, None, **opts)

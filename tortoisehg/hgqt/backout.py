# backout.py - Backout dialog for TortoiseHg
#
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import merge as mergemod

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, csinfo, i18n, cmdui, status, resolve
from tortoisehg.hgqt import commit, qscilib, thgrepo

keep = i18n.keepgettext()

class BackoutDialog(QDialog):

    def __init__(self, repo, rev='tip', parent=None, opts={}):
        super(BackoutDialog, self).__init__(parent)
        f = self.windowFlags()
        self.setWindowFlags(f & ~Qt.WindowContextHelpButtonHint)
        self.setWindowIcon(qtlib.geticon('hg-revert'))
        self.repo = repo

        # main layout box
        box = QVBoxLayout()
        box.setSpacing(8)
        box.setContentsMargins(*(6,)*4)

        ## target revision
        target_sep = qtlib.LabeledSeparator(_('Target changeset'))
        box.addWidget(target_sep)

        style = csinfo.panelstyle(selectable=True)
        self.targetinfo = csinfo.create(self.repo, rev, style, withupdate=True)
        box.addWidget(self.targetinfo)

        ## backout message
        msg_sep = qtlib.LabeledSeparator(_('Backout commit message'))
        box.addWidget(msg_sep)

        revhex = self.targetinfo.get_data('revid')
        self.msgset = keep._('Backed out changeset: ')
        self.msgset['id'] += revhex
        self.msgset['str'] += revhex

        self.msgTextEdit = commit.MessageEntry(self)
        self.msgTextEdit.installEventFilter(qscilib.KeyPressInterceptor(self))
        self.msgTextEdit.refresh(repo)
        self.msgTextEdit.loadSettings(QSettings(), 'backout/message')
        self.msgTextEdit.setText(self.msgset['str'])
        box.addWidget(self.msgTextEdit, 2)

        ## options
        opt_sep = qtlib.LabeledSeparator(_('Options'))
        box.addWidget(opt_sep)

        obox = QVBoxLayout()
        obox.setSpacing(3)
        box.addLayout(obox)

        self.engChk = QCheckBox(_('Use English backout message'))
        self.engChk.toggled.connect(self.eng_toggled)
        engmsg = self.repo.ui.configbool('tortoisehg', 'engmsg', False)
        self.engChk.setChecked(engmsg)

        obox.addWidget(self.engChk)
        self.mergeChk = QCheckBox(_('Commit backout before merging with '
                                     'current working parent'))
        self.mergeChk.toggled.connect(self.merge_toggled)
        self.mergeChk.setChecked(bool(opts.get('merge')))
        self.msgTextEdit.setEnabled(False)
        obox.addWidget(self.mergeChk)

        self.autoresolve_chk = QCheckBox(_('Automatically resolve merge conflicts '
                                           'where possible'))
        self.autoresolve_chk.setChecked(
            repo.ui.configbool('tortoisehg', 'autoresolve', False))
        obox.addWidget(self.autoresolve_chk)

        if repo[revhex] == repo.parents()[0]:
            # backing out the working parent is a one-step process
            self.msgTextEdit.setEnabled(True)
            self.mergeChk.setVisible(False)
            self.autoresolve_chk.setVisible(False)
            self.backoutParent = True
        else:
            self.backoutParent = False

        self.reslabel = QLabel()
        self.reslabel.linkActivated.connect(self.link_activated)
        box.addWidget(self.reslabel)

        ## command widget
        self.cmd = cmdui.Widget(True, False, self)
        self.cmd.commandStarted.connect(self.command_started)
        self.cmd.commandFinished.connect(self.command_finished)
        self.cmd.commandCanceling.connect(self.command_canceling)
        box.addWidget(self.cmd, 1)

        ## bottom buttons
        buttons = QDialogButtonBox()
        self.cancelBtn = buttons.addButton(QDialogButtonBox.Cancel)
        self.cancelBtn.clicked.connect(self.cancel_clicked)
        self.closeBtn = buttons.addButton(QDialogButtonBox.Close)
        self.closeBtn.clicked.connect(self.reject)
        self.backoutBtn = buttons.addButton(_('&Backout'),
                                             QDialogButtonBox.ActionRole)
        self.backoutBtn.clicked.connect(self.backout)
        self.detailBtn = buttons.addButton(_('Detail'),
                                            QDialogButtonBox.ResetRole)
        self.detailBtn.setAutoDefault(False)
        self.detailBtn.setCheckable(True)
        self.detailBtn.toggled.connect(self.detail_toggled)
        box.addWidget(buttons)

        # dialog setting
        self.setLayout(box)
        self.setMinimumWidth(480)
        self.setMaximumHeight(800)
        self.resize(0, 340)
        self.setWindowTitle(_("Backout '%s' - %s") % (revhex,
                            self.repo.displayname))

        # prepare to show
        self.cmd.setHidden(True)
        self.cancelBtn.setHidden(True)
        self.detailBtn.setHidden(True)
        self.msgTextEdit.setFocus()
        self.msgTextEdit.moveCursorToEnd()

    ### Private Methods ###

    def merge_toggled(self, checked):
        self.msgTextEdit.setEnabled(checked)

    def eng_toggled(self, checked):
        msg = self.msgTextEdit.text()
        origmsg = (checked and self.msgset['str'] or self.msgset['id'])
        if msg != origmsg:
            if not qtlib.QuestionMsgBox(_('Confirm Discard Message'),
                         _('Discard current backout message?'), parent=self):
                self.engChk.blockSignals(True)
                self.engChk.setChecked(not checked)
                self.engChk.blockSignals(False)
                return
        newmsg = (checked and self.msgset['id'] or self.msgset['str'])
        self.msgTextEdit.setText(newmsg)

    def backout(self):
        user = qtlib.getCurrentUsername(self, self.repo)
        if not user:
            return
        # prepare command line
        revhex = self.targetinfo.get_data('revid')
        cmdline = ['backout', '--rev', revhex, '--repository', self.repo.root,
                   '--user', user]
        cmdline += ['--tool=internal:' +
                    (self.autoresolve_chk.isChecked() and 'merge' or 'fail')]
        if self.backoutParent:
            msg = self.msgTextEdit.text()
            cmdline += ['--message='+hglib.fromunicode(msg)]
            commandlines = [cmdline]
            pushafter = self.repo.ui.config('tortoisehg', 'cipushafter')
            if pushafter:
                cmd = ['push', '--repository', self.repo.root, pushafter]
                commandlines.append(cmd)
        elif self.mergeChk.isChecked():
            cmdline += ['--merge']
            msg = self.msgTextEdit.text()
            cmdline += ['--message', hglib.fromunicode(msg)]
            commandlines = [cmdline]
        else:
            commandlines = [cmdline]

        # start backing out
        self.cmdline = cmdline
        self.repo.incrementBusyCount()
        self.cmd.run(*commandlines)

    def commit(self):
        cmdline = ['commit', '--repository', self.repo.root]
        msg = self.msgTextEdit.text()
        cmdline += ['--message='+hglib.fromunicode(msg)]
        self.cmdline = cmdline
        commandlines = [cmdline]
        pushafter = self.repo.ui.config('tortoisehg', 'cipushafter')
        if pushafter:
            cmd = ['push', '--repository', self.repo.root, pushafter]
            commandlines.append(cmd)
        self.repo.incrementBusyCount()
        self.cmd.run(*commandlines)

    ### Signal Handlers ###

    def cancel_clicked(self):
        self.cmd.cancel()

    def detail_toggled(self, checked):
        self.cmd.setShowOutput(checked)

    def command_started(self):
        self.cmd.setShown(True)
        self.mergeChk.setVisible(False)
        self.closeBtn.setHidden(True)
        self.cancelBtn.setShown(True)
        self.detailBtn.setShown(True)
        self.backoutBtn.setEnabled(False)

    def command_canceling(self):
        self.cancelBtn.setDisabled(True)

    def command_finished(self, ret):
        self.repo.decrementBusyCount()
        self.cancelBtn.setHidden(True)

        # If the action wasn't successful, display the output and we're done
        if ret not in (0, 1):
            self.detailBtn.setChecked(True)
            self.closeBtn.setShown(True)
            self.closeBtn.setAutoDefault(True)
            self.closeBtn.setFocus()
        else:
            finished = True
            #If we backed out our parent, there is no second commit step
            if self.cmdline[0] == 'backout' and not self.backoutParent:
                 finished = False
                 self.msgTextEdit.setEnabled(True)
                 self.backoutBtn.setEnabled(True)
                 self.backoutBtn.setText(_('Commit', 'action button'))
                 self.backoutBtn.clicked.disconnect(self.backout)
                 self.backoutBtn.clicked.connect(self.commit)
                 self.checkResolve()

            if finished:
                if not self.cmd.outputShown():
                    self.accept()
                else:
                    self.closeBtn.clicked.disconnect(self.reject)
                    self.closeBtn.clicked.connect(self.accept)
                    self.closeBtn.setHidden(False)

    def checkResolve(self):
        for root, path, status in thgrepo.recursiveMergeStatus(self.repo):
            if status == 'u':
                txt = _('Backout generated merge <b>conflicts</b> that must '
                        'be <a href="resolve"><b>resolved</b></a>')
                self.backoutBtn.setEnabled(False)
                break
        else:
            self.backoutBtn.setEnabled(True)
            txt = _('You may commit the backed out changes after '
                    '<a href="status"><b>verifying</b></a> them')
        self.reslabel.setText(txt)

    @pyqtSlot(QString)
    def link_activated(self, cmd):
        if cmd == 'resolve':
            dlg = resolve.ResolveDialog(self.repo, self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.exec_()
            self.checkResolve()
        elif cmd == 'status':
            dlg = status.StatusDialog([], {}, self.repo.root, self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.exec_()
            self.checkResolve()

    def accept(self):
        self.msgTextEdit.saveSettings(QSettings(), 'backout/message')
        super(BackoutDialog, self).accept()

def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    repo = thgrepo.repository(ui, path=paths.find_root())
    kargs = {'opts': opts}
    if opts.get('rev'):
        kargs['rev'] = opts.get('rev')
    elif len(pats) == 1:
        kargs['rev'] = pats[0]
    return BackoutDialog(repo, **kargs)

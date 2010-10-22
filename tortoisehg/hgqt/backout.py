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

keep = i18n.keepgettext()

class BackoutDialog(QDialog):

    def __init__(self, repo, rev='tip', parent=None, opts={}):
        super(BackoutDialog, self).__init__(parent)
        f = self.windowFlags()
        self.setWindowFlags(f & ~Qt.WindowContextHelpButtonHint)
        self.repo = repo
        self.didbackout = False

        # main layout box
        box = QVBoxLayout()
        box.setSpacing(8)
        box.setContentsMargins(*(6,)*4)

        ## target revision
        target_sep = qtlib.LabeledSeparator(_('Target changeset'))
        box.addWidget(target_sep)

        style = csinfo.panelstyle(selectable=True)
        self.target_info = csinfo.create(self.repo, rev, style, withupdate=True)
        box.addWidget(self.target_info)

        ## backout message
        msg_sep = qtlib.LabeledSeparator(_('Backout commit message'))
        box.addWidget(msg_sep)

        revhex = self.target_info.get_data('revid')
        self.msgset = keep._('Backed out changeset: ')
        self.msgset['id'] += revhex
        self.msgset['str'] += revhex

        self.msg_text = QTextEdit()
        self.msg_text.setText(self.msgset['str'])
        box.addWidget(self.msg_text, 1)

        ## options
        opt_sep = qtlib.LabeledSeparator(_('Options'))
        box.addWidget(opt_sep)

        obox = QVBoxLayout()
        obox.setSpacing(3)
        box.addLayout(obox)

        self.eng_chk = QCheckBox(_('Use English backout message'))
        self.eng_chk.toggled.connect(self.eng_toggled)
        engmsg = self.repo.ui.configbool('tortoisehg', 'engmsg', False)
        self.eng_chk.setChecked(engmsg)

        obox.addWidget(self.eng_chk)
        self.merge_chk = QCheckBox(_('Commit backout before merging with '
                                     'current working parent'))
        self.merge_chk.toggled.connect(self.merge_toggled)
        self.msg_text.setEnabled(False)
        obox.addWidget(self.merge_chk)

        self.reslabel = QLabel()
        self.reslabel.linkActivated.connect(self.link_activated)
        box.addWidget(self.reslabel)

        ## command widget
        self.cmd = cmdui.Widget()
        self.cmd.commandStarted.connect(self.command_started)
        self.cmd.commandFinished.connect(self.command_finished)
        self.cmd.commandCanceling.connect(self.command_canceling)
        box.addWidget(self.cmd, 2)

        ## bottom buttons
        buttons = QDialogButtonBox()
        self.cancel_btn = buttons.addButton(QDialogButtonBox.Cancel)
        self.cancel_btn.clicked.connect(self.cancel_clicked)
        self.close_btn = buttons.addButton(QDialogButtonBox.Close)
        self.close_btn.clicked.connect(self.reject)
        self.backout_btn = buttons.addButton(_('&Backout'),
                                             QDialogButtonBox.ActionRole)
        self.backout_btn.clicked.connect(self.backout)
        self.detail_btn = buttons.addButton(_('Detail'),
                                            QDialogButtonBox.ResetRole)
        self.detail_btn.setAutoDefault(False)
        self.detail_btn.setCheckable(True)
        self.detail_btn.toggled.connect(self.detail_toggled)
        box.addWidget(buttons)

        # dialog setting
        self.setLayout(box)
        self.setMinimumWidth(480)
        self.setMaximumHeight(800)
        self.resize(0, 340)
        self.setWindowTitle(_("Backout '%s' - %s") % (revhex,
                            self.repo.displayname))

        self.merge_chk.setChecked(bool(opts.get('merge')))

        # prepare to show
        self.cmd.setHidden(True)
        self.cancel_btn.setHidden(True)
        self.detail_btn.setHidden(True)
        self.msg_text.setFocus()
        cursor = self.msg_text.textCursor()
        cursor.movePosition(QTextCursor.EndOfBlock)
        self.msg_text.setTextCursor(cursor)

    ### Private Methods ###

    def merge_toggled(self, checked):
        self.msg_text.setEnabled(checked)

    def eng_toggled(self, checked):
        msg = self.msg_text.toPlainText()
        origmsg = (checked and self.msgset['str'] or self.msgset['id'])
        if msg != origmsg:
            if not qtlib.QuestionMsgBox(_('Confirm Discard Message'),
                         _('Discard current backout message?'), parent=self):
                self.eng_chk.blockSignals(True)
                self.eng_chk.setChecked(not checked)
                self.eng_chk.blockSignals(False)
                return
        newmsg = (checked and self.msgset['id'] or self.msgset['str'])
        self.msg_text.setText(newmsg)

    def backout(self):
        # prepare command line
        revhex = self.target_info.get_data('revid')
        cmdline = ['backout', '--rev', revhex, '--repository', self.repo.root]
        cmdline += ['--config', 'ui.merge=internal:fail']
        if self.merge_chk.isChecked():
            cmdline += ['--merge']
            msg = self.msg_text.toPlainText()
            cmdline += ['--message', hglib.fromunicode(msg)]

        # start backing out
        self.cmdline = cmdline
        self.repo.incrementBusyCount()
        self.cmd.run(cmdline)

    def commit(self):
        cmdline = ['commit', '--repository', self.repo.root]
        msg = self.msg_text.toPlainText()
        cmdline += ['--message', hglib.fromunicode(msg)]
        self.cmdline = cmdline
        self.repo.incrementBusyCount()
        self.cmd.run(cmdline)

    ### Signal Handlers ###

    def cancel_clicked(self):
        self.cmd.cancel()

    def detail_toggled(self, checked):
        self.cmd.show_output(checked)

    def command_started(self):
        self.cmd.setShown(True)
        self.close_btn.setHidden(True)
        self.cancel_btn.setShown(True)
        self.detail_btn.setShown(True)

    def command_canceling(self):
        self.cancel_btn.setDisabled(True)

    def command_finished(self, ret):
        self.repo.decrementBusyCount()
        self.cancel_btn.setHidden(True)
        if ret not in (0, 1):
            self.detail_btn.setChecked(True)
            self.close_btn.setShown(True)
            self.close_btn.setAutoDefault(True)
            self.close_btn.setFocus()
        elif self.cmdline[0] == 'backout':
            self.didbackout = True
            self.merge_chk.setEnabled(False)
            self.msg_text.setEnabled(True)
            self.backout_btn.setText(_('Commit'))
            self.backout_btn.clicked.disconnect(self.backout)
            self.backout_btn.clicked.connect(self.commit)
            self.checkResolve()
        elif not self.cmd.is_show_output():
            self.accept()

    def checkResolve(self):
        ms = mergemod.mergestate(self.repo)
        for path in ms:
            if ms[path] == 'u':
                txt = _('Backout generated merge <b>conflicts</b> that must '
                        'be <a href="resolve"><b>resolved</b></a>')
                self.backout_btn.setEnabled(False)
                break
        else:
            self.backout_btn.setEnabled(True)
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

def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    from tortoisehg.hgqt import thgrepo
    repo = thgrepo.repository(ui, path=paths.find_root())
    kargs = {'opts': opts}
    if opts.get('rev'):
        kargs['rev'] = opts.get('rev')
    elif len(pats) == 1:
        kargs['rev'] = pats[0]
    return BackoutDialog(repo, **kargs)

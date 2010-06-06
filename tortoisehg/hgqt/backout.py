# backout.py - Backout dialog for TortoiseHg
#
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import hg, ui

from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, csinfo, i18n, cmdui

keep = i18n.keepgettext()

class BackoutDialog(QDialog):

    repoInvalidated = pyqtSignal()

    def __init__(self, repo=None, rev='tip', parent=None, opts={}):
        super(BackoutDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.ui = ui.ui()
        if repo:
            self.repo = repo
        else:
            root = paths.find_root()
            if root:
                self.repo = hg.repository(self.ui, path=root)
            else:
                raise 'not repository'

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
        self.merge_chk = QCheckBox(_('Merge with old dirstate parent '
                                     'after backout'))
        obox.addWidget(self.merge_chk)

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
        reponame = hglib.get_reponame(self.repo)
        self.setWindowTitle(_("Backout '%s' - %s") \
                                % (revhex, hglib.tounicode(reponame)))

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
        msg = self.msg_text.toPlainText()
        revhex = self.target_info.get_data('revid')
        cmdline = ['backout', '--rev', revhex]
        if self.merge_chk.isChecked():
            cmdline += ['--merge']
        cmdline += ['--message', hglib.fromunicode(msg)]

        # start backing out
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

    def command_finished(self, wrapper):
        if wrapper.data is not 0 or self.cmd.is_show_output():
            self.detail_btn.setChecked(True)
            self.close_btn.setShown(True)
            self.close_btn.setAutoDefault(True)
            self.close_btn.setFocus()
            self.cancel_btn.setHidden(True)
        else:
            self.repoInvalidated.emit()
            self.accept()

    def command_canceling(self):
        self.cancel_btn.setDisabled(True)

def run(ui, *pats, **opts):
    kargs = {'opts': opts}
    if opts.get('rev'):
        kargs['rev'] = opts.get('rev')
    elif len(pats) == 1:
        kargs['rev'] = pats[0]
    return BackoutDialog(**kargs)

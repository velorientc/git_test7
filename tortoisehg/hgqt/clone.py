# clone.py - Clone dialog for TortoiseHg
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from PyQt4.QtCore import Qt
from PyQt4.QtGui import QDialog, QDialogButtonBox, QVBoxLayout, QGridLayout
from PyQt4.QtGui import QComboBox, QPushButton, QLabel, QLayout, QCheckBox
from PyQt4.QtGui import QHBoxLayout, QLineEdit, QMessageBox

from mercurial import ui

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui

class CloneDialog(QDialog):

    def __init__(self, args=None, opts=None):
        super(CloneDialog, self).__init__(None, Qt.WindowTitleHint or
                                                Qt.WindowSystemMenuHint)
        self.ui = ui.ui()

        src = hglib.tounicode(os.getcwd())
        dest = src
        if len(args) > 1:
            src = args[0]
            dest = args[1]
        elif len(args):
            src = args[0]

        # base layout box
        box = QVBoxLayout()
        box.setSpacing(6)

        ## main layout grid
        grid = QGridLayout()
        grid.setSpacing(6)
        box.addLayout(grid)

        ### source combo and button
        self.src_combo = QComboBox()
        self.src_combo.setEditable(True)
        self.src_combo.setMinimumWidth(310)
        self.src_combo.setEditText(src)
        self.src_btn = QPushButton(_('Browse...'))
        self.src_btn.setAutoDefault(False)
        grid.addWidget(QLabel(_('Source:')), 0, 0)
        grid.addWidget(self.src_combo, 0, 1)
        grid.addWidget(self.src_btn, 0, 2)

        ### destination combo and button
        self.dest_combo = QComboBox()
        self.dest_combo.setEditable(True)
        self.dest_combo.setMinimumWidth(310)
        self.dest_combo.setEditText(dest)
        self.dest_btn = QPushButton(_('Browse...'))
        self.dest_btn.setAutoDefault(False)
        grid.addWidget(QLabel(_('Destination:')), 1, 0)
        grid.addWidget(self.dest_combo, 1, 1)
        grid.addWidget(self.dest_btn, 1, 2)

        ### options
        optbox = QVBoxLayout()
        optbox.setSpacing(6)
        self.optlabel = QLabel(_('Options:'))
        grid.addWidget(self.optlabel, 2, 0, Qt.AlignLeft | Qt.AlignTop)
        grid.addLayout(optbox, 2, 1, 1, 2)

        hbox = QHBoxLayout()
        hbox.setSpacing(0)
        optbox.addLayout(hbox)
        self.rev_chk = QCheckBox(_('Clone to revision:'))
        self.rev_chk.toggled.connect(
             lambda e: self.toggle_enabled(e, self.rev_text))
        self.rev_text = QLineEdit()
        hbox.addWidget(self.rev_chk)
        hbox.addWidget(self.rev_text)
        hbox.addStretch(40)

        self.noupdate_chk = QCheckBox(_('Do not update the new working directory'))
        self.pproto_chk = QCheckBox(_('Use pull protocol to copy metadata'))
        self.uncomp_chk = QCheckBox(_('Use uncompressed transfer'))
        optbox.addWidget(self.noupdate_chk)
        optbox.addWidget(self.pproto_chk)
        optbox.addWidget(self.uncomp_chk)

        self.proxy_chk = QCheckBox(_('Use proxy server'))
        optbox.addWidget(self.proxy_chk)
        useproxy = bool(self.ui.config('http_proxy', 'host'))
        self.proxy_chk.setEnabled(useproxy)
        self.proxy_chk.setChecked(useproxy)

        self.remote_chk = QCheckBox(_('Remote command:'))
        self.remote_chk.toggled.connect(
             lambda e: self.toggle_enabled(e, self.remote_text))
        self.remote_text = QLineEdit()
        optbox.addWidget(self.remote_chk)
        optbox.addWidget(self.remote_text)

        ## command widget
        self.cmd = cmdui.Widget()
        self.cmd.commandStarted.connect(self.command_started)
        self.cmd.commandFinished.connect(self.command_finished)
        self.cmd.commandCanceling.connect(self.command_canceling)
        box.addWidget(self.cmd)

        ## bottom buttons
        buttons = QDialogButtonBox()
        self.cancel_btn = buttons.addButton(QDialogButtonBox.Cancel)
        self.cancel_btn.clicked.connect(self.cancel_clicked)
        self.close_btn = buttons.addButton(QDialogButtonBox.Close)
        self.close_btn.clicked.connect(self.reject)
        self.close_btn.setAutoDefault(False)
        self.clone_btn = buttons.addButton(_('&Clone'),
                                           QDialogButtonBox.ActionRole)
        self.clone_btn.clicked.connect(self.clone)
        self.detail_btn = buttons.addButton(_('Detail'),
                                            QDialogButtonBox.ResetRole)
        self.detail_btn.setAutoDefault(False)
        self.detail_btn.setCheckable(True)
        self.detail_btn.toggled.connect(self.detail_toggled)
        self.options_btn = buttons.addButton(_('Options'),
                                             QDialogButtonBox.ResetRole)
        self.options_btn.setAutoDefault(False)
        self.options_btn.setCheckable(True)
        self.options_btn.toggled.connect(self.show_options)
        box.addWidget(buttons)

        # dialog setting
        self.setLayout(box)
        self.layout().setSizeConstraint(QLayout.SetFixedSize)
        self.setWindowTitle(_('Clone - TortoiseHg'))

        # prepare to show
        self.cmd.setHidden(True)
        self.cancel_btn.setHidden(True)
        self.detail_btn.setHidden(True)
        self.show_options(False)
        self.rev_text.setDisabled(True)
        self.remote_text.setDisabled(True)

        if opts.get('rev'):
            self.rev_chk.setChecked(True)
            self.rev_text.setText(hglib.tounicode(', '.join(opts['rev'])))
        self.noupdate_chk.setChecked(bool(opts['noupdate']))
        self.pproto_chk.setChecked(bool(opts['pull']))
        self.uncomp_chk.setChecked(bool(opts['uncompressed']))

        self.src_combo.setFocus()
        self.src_combo.lineEdit().selectAll()

    ### Private Methods ###

    def show_options(self, visible):
        self.optlabel.setVisible(visible)
        self.rev_chk.setVisible(visible)
        self.rev_text.setVisible(visible)
        self.noupdate_chk.setVisible(visible)
        self.pproto_chk.setVisible(visible)
        self.uncomp_chk.setVisible(visible)
        self.proxy_chk.setVisible(visible)
        self.remote_chk.setVisible(visible)
        self.remote_text.setVisible(visible)

    def clone(self):
        # prepare user input
        src = hglib.fromunicode(self.src_combo.currentText()).strip()
        dest = hglib.fromunicode(self.dest_combo.currentText()).strip()
        if not dest:
            dest = os.path.basename(src)
        remotecmd = hglib.fromunicode(self.remote_text.text()).strip()
        rev = hglib.fromunicode(self.rev_text.text()).strip() or None

        # verify input
        if src == '':
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle(_('TortoiseHg Clone'))
            msg.setStandardButtons(QMessageBox.Close)
            msg.setText(_('<b>Source path is empty</b>'))
            msg.setInformativeText(_('<nobr>Please enter a valid source path.</nobr>'))
            msg.exec_()
            self.src_combo.setFocus()
            return False

        if src == dest:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle(_('TortoiseHg Clone'))
            msg.setStandardButtons(QMessageBox.Close)
            msg.setText(_('Source and destination are the same'))
            msg.setInformativeText(_('<nobr>Please specify different paths.</nobr>'))
            msg.exec_()
            return False

        if dest == os.getcwd():
            if os.listdir(dest):
                # cur dir has files, specify no dest, let hg take
                # basename
                dest = None
            else:
                dest = '.'
        else:
            abs = os.path.abspath(dest)
            dirabs = os.path.dirname(abs)
            if dirabs == src:
                dest = os.path.join(os.path.dirname(dirabs), dest)

        # prepare command line
        cmdline = ['clone']
        if self.noupdate_chk.isChecked():
            cmdline.append('--noupdate')
        if self.uncomp_chk.isChecked():
            cmdline.append('--uncompressed')
        if self.pproto_chk.isChecked():
            cmdline.append('--pull')
        if self.ui.config('http_proxy', 'host'):
            if not self.proxy_chk.isChecked():
                cmdline += ['--config', 'http_proxy.host=']
        if remotecmd:
            cmdline.append('--remotecmd')
            cmdline.append(remotecmd)
        if rev:
            cmdline.append('--rev')
            cmdline.append(rev)

        cmdline.append('--verbose')
        cmdline.append(src)
        if dest:
            cmdline.append('--')
            cmdline.append(dest)

        # start cloning
        self.cmd.run(cmdline)

    ### Signal Handlers ###

    def toggle_enabled(self, checked, target):
        target.setEnabled(checked)
        if checked:
            target.setFocus()

    def cancel_clicked(self):
        self.cmd.cancel()

    def detail_toggled(self, checked):
        self.cmd.show_output(checked)

    def command_started(self):
        self.cmd.setShown(True)
        self.clone_btn.setHidden(True)
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
            self.reject()

    def command_canceling(self):
        self.cancel_btn.setDisabled(True)

def run(ui, *pats, **opts):
    return CloneDialog(pats, opts)

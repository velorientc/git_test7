# cmdui.py - A widget to execute Mercurial command for TortoiseHg
#
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import Qt, QString
from PyQt4.QtGui import QDialog, QDialogButtonBox, QLabel, QProgressBar
from PyQt4.QtGui import QTextEdit, QHBoxLayout, QGridLayout, QMessageBox

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _, localgettext
from tortoisehg.hgqt import qtlib, thread

local = localgettext()

class Dialog(QDialog):
    def __init__(self, cmdline, parent=None):
        super(Dialog, self).__init__(parent, Qt.WindowTitleHint or \
                                             Qt.WindowSystemMenuHint)

        # main layout grid
        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setContentsMargins(*(7,)*4)

        ## hbox for status and progress labels
        hbox = QHBoxLayout()
        grid.addLayout(hbox, 0, 0)

        self.status_label = QLabel('')
        hbox.addWidget(self.status_label, 1)

        self.prog_label = QLabel('')
        hbox.addWidget(self.prog_label, 0, Qt.AlignRight)

        self.pbar = QProgressBar()
        self.pbar.setTextVisible(False)
        self.pbar.setMinimum(0)
        grid.addWidget(self.pbar, 1, 0)

        # command output area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        grid.addWidget(self.log_text, 2, 0, 5, 0)
        grid.setRowStretch(2, 1)

        # bottom buttons
        buttons = QDialogButtonBox()
        self.cancel_btn = buttons.addButton(QDialogButtonBox.Cancel)
        self.cancel_btn.clicked.connect(self.cancel_clicked)
        self.close_btn = buttons.addButton(QDialogButtonBox.Close)
        self.close_btn.setHidden(True)
        self.close_btn.clicked.connect(self.reject)
        grid.addWidget(buttons, 7, 0)

        self.setLayout(grid)
        self.setWindowTitle(_('TortoiseHg Command Dialog'))
        self.resize(540, 420)

        # setup and start command thread
        self.cmd = thread.CmdThread(cmdline)
        self.cmd.outputReceived.connect(self.output_received)
        self.cmd.errorReceived.connect(self.error_received)
        self.cmd.progressReceived.connect(self.progress_received)
        self.cmd.started.connect(self.command_started)
        self.cmd.commandFinished.connect(self.command_finished)
        self.cmd.start()

    def reject(self):
        if self.cmd.isRunning():
            ret = QMessageBox.question(self, _('Confirm Exit'), _('Mercurial'
                        ' command is still running.\nAre you sure you want'
                        ' to terminate?'), QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No)
            if ret == QMessageBox.Yes:
                self.cancel_clicked()

            # don't close dialog
            return

        # close dialog
        QDialog.reject(self)

    def cancel_clicked(self):
        # trigger KeyboardInterrupt
        self.cmd.abort()

        # until thread is terminated
        self.cancel_btn.setDisabled(True)
        self.pbar.setMaximum(0)

    def command_started(self):
        # use indeterminate mode
        self.pbar.setMaximum(0)
        self.status_label.setText(_('Running...'))

    def command_finished(self, wrapper):
        ret = wrapper.data
        if ret is None or self.pbar.maximum() == 0:
            self.clear_progress()
        if ret is None:
            if self.cmd.abortbyuser:
                status = _('Terminated by user')
            else:
                status = _('Terminated')
        else:
            status = _('Finished')
        self.status_label.setText(status)
        self.cancel_btn.setHidden(True)
        self.close_btn.setShown(True)
        self.close_btn.setFocus()

    def append_output(self, msg, style=''):
        msg = hglib.tounicode(msg)
        msg = msg.replace('\n', '<br />')
        self.log_text.insertHtml('<pre style="%s">%s</pre>' % (style, msg))

    def output_received(self, wrapper):
        msg, label = wrapper.data
        style = qtlib.geteffect(label)
        style += ';font-size: 9pt'
        self.append_output(msg, style)

    def error_received(self, wrapper):
        msg, label = wrapper.data
        style = qtlib.geteffect(label)
        style += ';font-size: 9pt'
        self.append_output(msg, style)

    def clear_progress(self):
        self.pbar.reset()
        self.pbar.setMaximum(100)
        self.status_label.setText('')
        self.prog_label.setText('')
        self.inprogress = False

    def progress_received(self, wrapper):
        if self.cmd.isFinished():
            self.clear_progress()
            return

        counting = False
        topic, item, pos, total, unit = wrapper.data
        if pos is None:
            self.clear_progress()
            return
        if total is None:
            count = '%d' % pos
            counting = True
        else:
            self.pbar.setMaximum(total)
            self.pbar.setValue(pos)
            count = '%d / %d' % (pos, total)
        if unit:
            count += ' ' + unit
        self.prog_label.setText(hglib.tounicode(count))
        if item:
            status = '%s: %s' % (topic, item)
        else:
            status = local._('Status: %s') % topic
        self.status_label.setText(hglib.tounicode(status))
        self.inprogress = True

        if not self.inprogress or counting:
            # use indeterminate mode
            self.pbar.setMinimum(0)

# hginit.py - TortoiseHg dialog to initialize a repo
#
# Copyright 2008 Steve Borho <steve@borho.org>
# Copyright 2010 Johan Samyn <johan.samyn@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from PyQt4.QtCore import Qt
from PyQt4.QtGui import QDialog, QLineEdit, QCheckBox, QLabel, QPushButton
from PyQt4.QtGui import QVBoxLayout, QGridLayout, QHBoxLayout, QLayout
from PyQt4.QtGui import QFileDialog

from mercurial import hg, ui, error, util

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui, qtlib
from tortoisehg.util import hglib


class InitDialog(QDialog):
    """TortoiseHg init dialog"""

    def __init__(self, destdir=[], opts={}):
        super(InitDialog, self).__init__()

        # main layout
        self.vbox = QVBoxLayout()
        self.vbox.setSpacing(6)
        self.grid = QGridLayout()
        self.grid.setSpacing(6)
        self.vbox.addLayout(self.grid)

        # dest widgets
        self.dest_lbl = QLabel(_('Destination path:'))
        self.dest_edit = QLineEdit()
        self.dest_edit.setMinimumWidth(300)
        self.dest_btn = QPushButton(_('Browse...'))
        self.dest_btn.setAutoDefault(False)
        self.grid.addWidget(self.dest_lbl, 0, 0)
        self.grid.addWidget(self.dest_edit, 0, 1)
        self.grid.addWidget(self.dest_btn, 0, 2)

        # options checkboxes
        self.add_files_chk = QCheckBox(
                _('Add special files (.hgignore, ...)'))
        self.make_old_chk = QCheckBox(
                _('Make repo compatible with Mercurial 1.0'))
        self.grid.addWidget(self.add_files_chk, 1, 1)
        self.grid.addWidget(self.make_old_chk, 2, 1)

        # buttons
        self.init_btn = QPushButton(_('Create'))
        self.close_btn = QPushButton(_('&Close'))
        self.close_btn.setDefault(True)
        self.close_btn.setFocus()
        self.detail_btn = QPushButton(_('&Detail'))
        self.detail_btn.setAutoDefault(False)
        self.detail_btn.setHidden(True)
        self.cancel_btn = QPushButton(_('Cancel'))
        self.cancel_btn.setAutoDefault(False)
        self.cancel_btn.setHidden(True)
        self.hbox = QHBoxLayout()
        self.hbox.addWidget(self.detail_btn)
        self.hbox.addStretch(0)
        self.hbox.addWidget(self.init_btn)
        self.hbox.addWidget(self.close_btn)
        self.hbox.addWidget(self.cancel_btn)
        self.vbox.addLayout(self.hbox)

        # some extras
        self.hgcmd_lbl = QLabel(_('Hg command:'))
        self.hgcmd_lbl.setAlignment(Qt.AlignRight)
        self.hgcmd_txt = QLineEdit()
        self.hgcmd_txt.setReadOnly(True)
        self.keep_open_chk = QCheckBox(_('Always show output'))
        self.grid.addWidget(self.hgcmd_lbl, 4, 0)
        self.grid.addWidget(self.hgcmd_txt, 4, 1)
        self.grid.addWidget(self.keep_open_chk, 5, 1)

        # command widget
        self.cmd = cmdui.Widget()
        self.cmd.commandStarted.connect(self.command_started)
        self.cmd.commandFinished.connect(self.command_finished)
        self.cmd.commandCanceling.connect(self.command_canceling)
        self.cmd.setHidden(True)
        self.vbox.addWidget(self.cmd)

        # init defaults
        self.cwd = os.getcwd()
        path = os.path.abspath(destdir and destdir[0] or self.cwd)
        if os.path.isfile(path):
            path = os.path.dirname(path)
        self.dest_edit.setText(path)
        self.add_files_chk.setChecked(True)
        self.make_old_chk.setChecked(False)
        self.compose_command()

        # dialog settings
        self.setWindowTitle(_('Init'))
        self.setWindowIcon(qtlib.geticon('init'))
        self.setWindowFlags(
                self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setLayout(self.vbox)
        self.layout().setSizeConstraint(QLayout.SetFixedSize)
        self.dest_edit.setFocus()

        # connecting slots
        self.dest_edit.textChanged.connect(self.compose_command)
        self.dest_btn.clicked.connect(self.browse_clicked)
        self.init_btn.clicked.connect(self.init)
        self.detail_btn.clicked.connect(self.detail_clicked)
        self.close_btn.clicked.connect(self.close)

    def browse_clicked(self):
        """Select the destination directory"""
        dest = hglib.fromunicode(self.dest_edit.text())
        if not os.path.exists(dest):
            dest = os.path.dirname(dest)
        FD = QFileDialog
        caption = _('Select Destination Folder')
        path = FD.getExistingDirectory(parent=self, caption=caption,
                options=FD.ShowDirsOnly | FD.ReadOnly)
        response = str(path)
        if response:
            self.dest_edit.setText(response)

    def detail_clicked(self):
        if self.cmd.is_show_output():
            self.cmd.show_output(False)
        else:
            self.cmd.show_output(True)

    def cancel_clicked():
        self.cmd.cancel()

    def compose_command(self):
        # just a stub for extension with extra options (--mq, --ssh, ...)
        self.cmdline = ['init']
        self.cmdline.append(hglib.fromunicode(self.dest_edit.text()))
        self.hgcmd_txt.setText(' '.join(self.cmdline))

    def init(self):
        dest = hglib.fromunicode(self.dest_edit.text())

        if dest == '':
            qtlib.ErrorMsgBox(_('Error executing init'),
                    _('Destination path is empty'),
                    _('Please enter the directory path'))
            self.dest_edit.setFocus()
            return False

        if not os.path.exists(dest):
            try:
                # create the folder, just like Hg would
                os.mkdir(dest)
            except:
                qtlib.ErrorMsgBox(_('Error executing init'),
                        _('Cannot create folder %s' % dest))
                return False

        _ui = ui.ui()

        # fncache is the new default repo format in Mercurial 1.1
        if self.make_old_chk.isChecked():
            _ui.setconfig('format', 'usefncache', 'False')

        try:
            # create the new repo
            hg.repository(_ui, dest, create=1)
        except error.RepoError, inst:
            qtlib.ErrorMsgBox(_('Error executing init'),
                    _('Unable to create new repository'),
                    hglib.tounicode(str(inst)))
            return False
        except util.Abort, inst:
            qtlib.ErrorMsgBox(_('Error executing init'),
                    _('Error when creating repository'),
                    hglib.tounicode(str(inst)))
            return False
        except:
            import traceback
            qtlib.ErrorMsgBox(_('Error executing init'),
                    _('Error when creating repository'),
                    traceback.format_exc())
            return False

        # Create the .hg* file, mainly to workaround
        # Explorer's problem in creating files with a name
        # beginning with a dot.
        if (self.add_files_chk.isChecked() and
                os.path.exists(os.path.sep.join([dest, '.hg']))):
            hgignore = os.path.join(dest, '.hgignore')
            if not os.path.exists(hgignore):
                try:
                    open(hgignore, 'wb')
                except:
                    pass

    def command_started(self):
        self.dest_edit.setEnabled(False)
        self.dest_btn.setEnabled(False)
        self.add_files_chk.setEnabled(False)
        self.make_old_chk.setEnabled(False)
        self.hgcmd_txt.setEnabled(False)
        self.cmd.setShown(True)
        self.init_btn.setHidden(True)
        self.close_btn.setHidden(True)
        self.cancel_btn.setShown(True)
        self.detail_btn.setShown(True)

    def command_finished(self, wrapper):
        if wrapper.data is not 0 or self.cmd.is_show_output()\
                or self.keep_open_chk.isChecked():
            if not self.cmd.is_show_output():
                self.detail_btn.click()
            self.cancel_btn.setHidden(True)
            self.close_btn.setShown(True)
            self.close_btn.setAutoDefault(True)
            self.close_btn.setFocus()
        else:
            self.reject()

    def command_canceling(self):
        self.cancel_btn.setDisabled(True)


def run(ui, *pats, **opts):
    return InitDialog(pats, opts)

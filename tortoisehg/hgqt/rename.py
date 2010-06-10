# rename.py - TortoiseHg's dialogs for handling renames
#
# Copyright 2009 Steve Borho <steve@borho.org>
# Copyright 2010 Johan Samyn <johan.samyn@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.


import os
import sys
import cStringIO
import shutil

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import hg
from mercurial import ui
from mercurial import util
from mercurial import commands
from mercurial import error

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui
from tortoisehg.hgqt import qtlib
from tortoisehg.util import hglib
from tortoisehg.util import paths


class RenameDialog(QDialog):
    """TortoiseHg rename dialog"""

    def __init__(self, ui, pats, parent=None, **opts):
        super(RenameDialog, self).__init__(parent=None)
        src = ''
        dest = ''
        src, dest = self.init_data(ui, pats)
        if not src:
            self.reject()
        self.init_view(src, dest, opts.get('alias') == 'copy')

    def init_data(self, ui, pats):
        """calculate initial values for widgets"""
        fname = ''
        target = ''
        cwd = os.getcwd()
        try:
            self.root = paths.find_root()
            self.repo = hg.repository(ui, self.root)
        except (ImportError, error.RepoError):
            qtlib.ErrorMsgBox(_('Rename Error'),
                    _('Could not find or initialize the repository'
                      ' from folder<p>%s</p>' % cwd))
            return ('', '')
        try:
            fname = util.canonpath(self.root, cwd, pats[0])
            target = util.canonpath(self.root, cwd, pats[1])
        except:
            pass
        os.chdir(self.root)
        fname = util.normpath(fname)
        if target:
            target = hglib.toutf(util.normpath(target))
        else:
            target = hglib.toutf(fname)
        self.opts = {}
        self.opts['force'] = False # Checkbox? Nah.
        self.opts['after'] = True
        self.opts['dry_run'] = False
        return (fname, target)

    def init_view(self, src, dest, iscopy):
        """define the view"""

        # widgets
        self.src_lbl = QLabel(_('Source:'))
        self.src_lbl.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        self.src_txt = QLineEdit(src)
        self.src_txt.setMinimumWidth(300)
        self.src_btn = QPushButton(_('Browse'))
        self.dest_lbl = QLabel(_('Destination:'))
        self.dest_lbl.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        self.dest_txt = QLineEdit(dest)
        self.dest_btn = QPushButton(_('Browse'))
        self.copy_chk = QCheckBox(_('Copy source -> destination'))

        # some extras
        self.dummy_lbl = QLabel('')
        self.hgcmd_lbl = QLabel(_('Hg command:'))
        self.hgcmd_lbl.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        self.hgcmd_txt = QLineEdit()
        self.hgcmd_txt.setReadOnly(True)
        self.show_command(self.compose_command(self.get_src(), self.get_dest()))
        self.keep_open_chk = QCheckBox(_('Always show output'))

        # command widget
        self.cmd = cmdui.Widget()
        self.cmd.commandStarted.connect(self.command_started)
        self.cmd.commandFinished.connect(self.command_finished)
        self.cmd.commandCanceling.connect(self.command_canceling)
        self.cmd.setHidden(True)

        # bottom buttons
        self.rename_btn_txt = 'Rename'
        self.rename_btn = QPushButton(_(self.rename_btn_txt))
        self.rename_btn.setAutoDefault(False)
        self.close_btn = QPushButton(_('&Close'))
        self.close_btn.setDefault(True)
        self.close_btn.setFocus()
        self.detail_btn = QPushButton(_('&Detail'))
        self.detail_btn.setAutoDefault(False)
        self.detail_btn.setHidden(True)
        self.cancel_btn = QPushButton(_('Cancel'))
        self.cancel_btn.setAutoDefault(False)
        self.cancel_btn.setHidden(True)

        # connecting slots
        self.src_txt.textEdited.connect(self.src_dest_edited)
        self.src_btn.clicked.connect(self.src_btn_clicked)
        self.dest_txt.textEdited.connect(self.src_dest_edited)
        self.dest_btn.clicked.connect(self.dest_btn_clicked)
        self.copy_chk.toggled.connect(self.copy_chk_toggled)
        self.rename_btn.clicked.connect(self.rename)
        self.detail_btn.clicked.connect(self.detail_clicked)
        self.close_btn.clicked.connect(self.close)

        # main layout
        self.grid = QGridLayout()
        self.grid.setSpacing(6)
        self.grid.addWidget(self.src_lbl, 0, 0)
        self.grid.addWidget(self.src_txt, 0, 1)
        self.grid.addWidget(self.src_btn, 0, 2)
        self.grid.addWidget(self.dest_lbl, 1, 0)
        self.grid.addWidget(self.dest_txt, 1, 1)
        self.grid.addWidget(self.dest_btn, 1, 2)
        self.grid.addWidget(self.copy_chk, 2, 1)
        self.grid.addWidget(self.dummy_lbl, 3, 1)
        self.grid.addWidget(self.hgcmd_lbl, 4, 0)
        self.grid.addWidget(self.hgcmd_txt, 4, 1)
        self.grid.addWidget(self.keep_open_chk, 5, 1)
        self.hbox = QHBoxLayout()
        self.hbox.addWidget(self.detail_btn)
        self.hbox.addStretch(0)
        self.hbox.addWidget(self.rename_btn)
        self.hbox.addWidget(self.close_btn)
        self.hbox.addWidget(self.cancel_btn)
        self.vbox = QVBoxLayout()
        self.vbox.setSpacing(6)
        self.vbox.addLayout(self.grid)
        self.vbox.addWidget(self.cmd)
        self.vbox.addLayout(self.hbox)

        # dialog setting
        self.setWindowIcon(qtlib.geticon('rename'))
        self.reponame = hglib.get_reponame(self.repo)
        self.wintitle = _('Rename - %s') % hglib.tounicode(self.reponame)
        self.setWindowTitle(self.wintitle)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        if iscopy:
            self.copy_chk.setChecked(True)

        self.setLayout(self.vbox)
        self.layout().setSizeConstraint(QLayout.SetFixedSize)
        self.dest_txt.setFocus()

    def get_src(self):
        return hglib.fromunicode(self.src_txt.text())

    def get_dest(self):
        return hglib.fromunicode(self.dest_txt.text())

    def src_dest_edited(self):
        self.show_command(self.compose_command(self.get_src(), self.get_dest()))

    def src_btn_clicked(self):
        """Select the source file of folder"""
        self.get_file_or_folder('src')

    def dest_btn_clicked(self):
        """Select the destination file of folder"""
        self.get_file_or_folder('dest')

    def get_file_or_folder(self, mode):
        if mode == 'src':
            curr = self.get_src()
            capt = 'Source'
        else:
            curr = self.get_dest()
            capt = 'Destination'
        FD = QFileDialog
        if os.path.isfile(curr):
            caption = _('Select %s File') % capt
            filter = 'All Files (*.*)'
            filename = FD.getOpenFileName(parent=self, caption=caption,
                    options=FD.ReadOnly)
            response = str(filename)
        else:
            caption = _('Select %s Folder' % capt)
            path = FD.getExistingDirectory(parent=self, caption=caption,
                    options=FD.ShowDirsOnly | FD.ReadOnly)
            response = str(path)
        if response:
            response = os.path.relpath(response, start=self.root)
            if mode == 'src':
                self.src_txt.setText(response)
            else:
                self.dest_txt.setText(response)
            self.compose_command(self.get_src(), self.get_dest())

    def copy_chk_toggled(self):
        if self.copy_chk.isChecked():
            sw = self.wintitle.replace(_('Rename'), _('Copy'))
            sb = self.rename_btn_txt.replace(_('Rename'), _('Copy'))
        else:
            sw = self.wintitle.replace(_('Copy'), _('Rename'))
            sb = self.rename_btn_txt.replace(_('Copy'), _('Rename'))
        self.setWindowTitle(sw)
        self.rename_btn.setText(sb)

    def compose_command(self, src, dest):
        cmdline = ['rename']
        vcmdline = ['rename']
        for k, v in self.opts.items():
            cmdline.append(k)
            cmdline.append(v)
            vcmdline.append('--' + k.replace('_', '-') + "=" + str(v))
        cmdline.append(hglib.fromunicode(src))
        cmdline.append(hglib.fromunicode(dest))
        vcmdline.append(hglib.fromunicode(src))
        vcmdline.append(hglib.fromunicode(dest))
        vcmdline = ' '.join(vcmdline)
        return cmdline, vcmdline

    def show_command(self, clinfo):
        cl, vcl = clinfo
        self.hgcmd_txt.setText(vcl)

    def rename(self):
        """execute the rename"""

        # check inputs
        src = self.get_src()
        dest = self.get_dest()
        curr_name = os.path.relpath(src, start=self.root)
        self.src_txt.setText(curr_name)
        new_name = os.path.relpath(dest, start=self.root)
        self.dest_txt.setText(new_name)
        if src == dest:
            qtlib.ErrorMsgBox(_('Rename Error'),
                    _('Please give a destination that differs from the source'))
            return
        if os.path.exists(dest) and os.path.isfile(dest):
            res = qtlib.QuestionMsgBox(_('Rename'), '<p>%s</p><p>%s</p>' %
                    (_('Destination file already exists.'),
                    _('Are you sure you want to overwrite it ?')),
                    defaultbutton=QMessageBox.No)
            if not res:
                return
        if not os.path.exists(src):
            qtlib.WarningMsgBox(_('Rename'), _('Source does not exists.'))
            return

        # prepare command line
        #cmdline, vcl = self.compose_command(self.get_src(), self.get_dest())
        #qtlib.InfoMsgBox('from rename', cmdline)
        #return

        # start archiving
        #self.cmd.run(cmdline)

        opts = self.opts
        saved = sys.stderr
        errors = cStringIO.StringIO()
        try:
            sys.stderr = errors
            self.repo.ui.pushbuffer()
            self.repo.ui.quiet = True
            try:
                new_name = util.canonpath(self.root, self.root, new_name)
                targetdir = os.path.dirname(new_name) or '.'
                if not os.path.isdir(targetdir):
                    os.makedirs(targetdir)
                if self.copy_chk.isChecked():
                    if os.path.isfile(curr_name):
                        shutil.copy(curr_name, new_name)
                    else:
                        shutil.copytree(curr_name, new_name)
                    addopts = {}
                    commands.add(self.repo.ui, self.repo, new_name, **addopts)
                else:
                    shutil.move(curr_name, new_name)
                    commands.rename(self.repo.ui, self.repo, curr_name, new_name, **opts)
            except (OSError, IOError, util.Abort, error.RepoError), inst:
                qtlib.ErrorMsgBox(_('Rename Error'),
                        _('The following erorr was caught with rename :'),
                        str(inst))
        finally:
            sys.stderr = saved
            textout = errors.getvalue() + self.repo.ui.popbuffer()
            errors.close()
            if len(textout) > 1:
                qtlib.ErrorMsgBox(_('rename error'), textout)

    def detail_clicked(self):
        if self.cmd.is_show_output():
            self.cmd.show_output(False)
        else:
            self.cmd.show_output(True)

    def cancel_clicked():
        self.cmd.cancel()

    def command_started(self):
        self.src_txt.setEnabled(False)
        self.src_btn.setEnabled(False)
        self.dest_txt.setEnabled(False)
        self.dest_btn.setEnabled(False)
        self.cmd.setShown(True)
        self.rename_btn.setHidden(True)
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
    return RenameDialog(ui, pats, **opts)

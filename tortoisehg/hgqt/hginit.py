# hginit.py - TortoiseHg dialog to initialize a repo
#
# Copyright 2008 Steve Borho <steve@borho.org>
# Copyright 2010 Johan Samyn <johan.samyn@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import hg, ui, error, util

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib
from tortoisehg.util import hglib, shlib

from PyQt4.QtCore import *
from PyQt4.QtGui import *

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
        self.hbox = QHBoxLayout()
        self.hbox.addStretch(0)
        self.hbox.addWidget(self.init_btn)
        self.hbox.addWidget(self.close_btn)
        self.vbox.addLayout(self.hbox)

        # some extras
        self.hgcmd_lbl = QLabel(_('Hg command:'))
        self.hgcmd_lbl.setAlignment(Qt.AlignRight)
        self.hgcmd_txt = QLineEdit()
        self.hgcmd_txt.setReadOnly(True)
        self.grid.addWidget(self.hgcmd_lbl, 4, 0)
        self.grid.addWidget(self.hgcmd_txt, 4, 1)

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

        shlib.shell_notify([dest])

def run(ui, *pats, **opts):
    return InitDialog(pats, opts)

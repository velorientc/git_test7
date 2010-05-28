# archive.py - TortoiseHg's dialog for archiving a repo revision
#
# Copyright 2009 Emmanuel Rosa <goaway1000@gmail.com>
# Copyright 2010 Johan Samyn <johan.samyn@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.


# TODO:
#
# - Allow manually adapting the destination path.
# - Keep the selection via the browse btn as a basename (instead of repo.root).
# - Make what is typed in in the lineedit of the rev_combo change dest_edit (and hgcmd_txt)
# - Make what is manually changed in the dest_edit be reflected in the hgcmd.
# - Update the hgcmd lineedit when/after manually changing the dest_edit.
# - Make the hgcmd_txt expand to show it's complete content (multiline eventualy).
#
# - Save/load qt settings (window position, ...).


import os

from PyQt4.QtCore import Qt, SIGNAL, SLOT, QObject
from PyQt4.QtGui import QDialog, QComboBox, QVBoxLayout, QGridLayout, QLabel
from PyQt4.QtGui import QLineEdit, QPushButton, QLayout, QRadioButton
from PyQt4.QtGui import QHBoxLayout, QFileDialog, QCheckBox

from mercurial import hg, error

from tortoisehg.hgqt.i18n import _
from tortoisehg.util import hglib, paths
from tortoisehg.hgqt import cmdui, qtlib
#import tortoisehg.hgqt # import connect
connect = QObject.connect

WD_PARENT = _('= Working Directory Parent =')

class ArchiveDialog(QDialog):
    """ Dialog to archive a particular Mercurial revision """

    def __init__(self, ui, repo, rev=None, parent=None):
        super(ArchiveDialog, self).__init__(parent=None)
        self.ui = ui
        self.repo = repo
        self.initrev = rev

        # base layout box
        self.vbox = QVBoxLayout()
        self.vbox.setSpacing(6)

        # main layout grid
        self.grid = QGridLayout()
        self.grid.setSpacing(6)
        self.vbox.addLayout(self.grid)

        # revision combo
        self.rev_combo = QComboBox()
        self.rev_combo.setEditable(True)
        self.rev_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.rev_lbl = QLabel(_('Archive revision:'))
        self.rev_lbl.setAlignment(Qt.AlignRight)
        self.grid.addWidget(self.rev_lbl, 0, 0)
        self.grid.addWidget(self.rev_combo, 0, 1)
        self.files_in_rev_chk = QCheckBox(
                _('Only files modified/created in this revision'))
        self.grid.addWidget(self.files_in_rev_chk, 1, 1)

        # destination lineedit and button
        self.dest_edit = QLineEdit()
        self.dest_edit.setMinimumWidth(300)
        self.dest_btn = QPushButton(_('Browse...'))
        self.dest_btn.setAutoDefault(False)
        self.dest_lbl = QLabel(_('Destination path:'))
        self.dest_lbl.setAlignment(Qt.AlignRight)
        self.grid.addWidget(self.dest_lbl, 2, 0)
        self.grid.addWidget(self.dest_edit, 2, 1)
        self.grid.addWidget(self.dest_btn, 2, 2)

        # archive types
        def radio(label):
            return QRadioButton(label, None)
        self.filesradio = radio(_('Directory of files'))
        self.tarradio = radio(_('Uncompressed tar archive'))
        self.tbz2radio = radio(_('Tar archive compressed using bzip2'))
        self.tgzradio = radio(_('Tar archive compressed using gzip'))
        self.uzipradio = radio(_('Uncompressed zip archive'))
        self.zipradio = radio(_('Zip archive compressed using deflate'))

        self.types_lbl = QLabel(_('Archive types:'))
        self.types_lbl.setAlignment(Qt.AlignRight)
        self.grid.addWidget(self.types_lbl, 3, 0)
        self.grid.addWidget(self.filesradio, 3, 1)
        self.grid.addWidget(self.tarradio, 4, 1)
        self.grid.addWidget(self.tbz2radio, 5, 1)
        self.grid.addWidget(self.tgzradio, 6, 1)
        self.grid.addWidget(self.uzipradio, 7, 1)
        self.grid.addWidget(self.zipradio, 8, 1)

        # some extras
        self.keep_open_chk = QCheckBox(_('Always show output'))
        self.grid.addWidget(self.keep_open_chk, 10, 1)
        self.hgcmd_lbl = QLabel(_('Hg command:'))
        self.hgcmd_lbl.setAlignment(Qt.AlignRight)
        self.hgcmd_txt = QLineEdit()
        self.hgcmd_txt.setReadOnly(True)
        self.grid.addWidget(self.hgcmd_lbl, 9, 0)
        self.grid.addWidget(self.hgcmd_txt, 9, 1)

        # command widget
        self.cmd = cmdui.Widget()
        self.cmd.commandStarted.connect(self.command_started)
        self.cmd.commandFinished.connect(self.command_finished)
        self.cmd.commandCanceling.connect(self.command_canceling)
        self.cmd.setHidden(True)
        self.vbox.addWidget(self.cmd)

        # bottom buttons
        self.hbox = QHBoxLayout()
        self.arch_btn = QPushButton(_('&Archive'))
        self.arch_btn.setAutoDefault(False)
        self.close_btn = QPushButton(_('&Close'))
        self.close_btn.setDefault(True)
        self.close_btn.setFocus()
        self.detail_btn = QPushButton(_('&Detail'))
        self.detail_btn.setAutoDefault(False)
        self.detail_btn.setHidden(True)
        self.cancel_btn = QPushButton(_('Cancel'))
        self.cancel_btn.setAutoDefault(False)
        self.cancel_btn.setHidden(True)
        self.hbox.addWidget(self.detail_btn)
        self.hbox.addStretch(0)
        self.hbox.addWidget(self.arch_btn)
        self.hbox.addWidget(self.close_btn)
        self.hbox.addWidget(self.cancel_btn)
        self.vbox.addLayout(self.hbox)
        self.rev_combo.setFocus()

        # set default values
        self.prevtarget = None
        if self.initrev:
            self.rev_combo.addItem(str(self.initrev))
        else:
            self.rev_combo.addItem(WD_PARENT)
        self.rev_combo.setCurrentIndex(0)
        for b in self.repo.branchtags():
            self.rev_combo.addItem(b)
        tags = list(self.repo.tags())
        tags.sort()
        tags.reverse()
        for t in tags:
            self.rev_combo.addItem(t)
        self.rev_combo.setMaxVisibleItems(self.rev_combo.count())
        self.dest_edit.setText(self.repo.root)
        self.filesradio.setChecked(True)
        self.update_path()

        # connecting slots
        self.make_connects()

        # dialog setting
        reponame = hglib.get_reponame(self.repo)
        self.setWindowTitle(_('Archive - %s') % hglib.tounicode(reponame))
        self.setWindowIcon(qtlib.geticon('menucheckout'))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setLayout(self.vbox)
        self.layout().setSizeConstraint(QLayout.SetFixedSize)
        self.rev_combo.setFocus()

    def get_selected_archive_type(self):
        """Return a dictionary describing the selected archive type"""
        if self.tarradio.isChecked():
            return {'type': 'tar', 'ext': '.tar', 'label': _('Tar archives')}
        elif self.tbz2radio.isChecked():
            return {'type': 'tbz2', 'ext': '.tar.bz2',
                    'label': _('Bzip2 tar archives')}
        elif self.tgzradio.isChecked():
            return {'type': 'tgz', 'ext': '.tar.gz',
                    'label': _('Gzip tar archives')}
        elif self.uzipradio.isChecked():
            return {'type': 'uzip', 'ext': '.zip',
                    'label': ('Uncompressed zip archives')}
        elif self.zipradio.isChecked():
            return {'type': 'zip', 'ext': '.zip',
                    'label': _('Compressed zip archives')}
        return {'type': 'files', 'ext': '', 'label': _('Directory of files')}

    def update_path(self):
        def remove_ext(path):
            for ext in ('.tar', '.tar.bz2', '.tar.gz', '.zip'):
                if path.endswith(ext):
                    return path.replace(ext, '')
            return path
        def remove_rev(path):
            l = ''
            for i in xrange(self.rev_combo.count() - 1):
                l += hglib.fromunicode(self.rev_combo.itemText(i))
            revs = [rev[0] for rev in l]
            revs.append(wdrev)
            if not self.prevtarget is None:
                revs.append(self.prevtarget)
            for rev in ['_' + rev for rev in revs]:
                if path.endswith(rev):
                    return path.replace(rev, '')
            return path
        def add_rev(path, rev):
            return '%s_%s' % (path, rev)
        def add_ext(path):
            select = self.get_selected_archive_type()
            if select['type'] != 'files':
                path += select['ext']
            return path
        text = self.rev_combo.currentText()
        if len(text) == 0:
            return
        wdrev = str(self.repo['.'].rev())
        if text == WD_PARENT:
            text = wdrev
        else:
            try:
                self.repo[hglib.fromunicode(text)]
            except (error.RepoError, error.LookupError):
                return
        path = hglib.fromunicode(self.dest_edit.text())
        path = remove_ext(path)
        path = remove_rev(path)
        path = add_rev(path, text)
        path = add_ext(path)
        self.dest_edit.setText(path)
        self.prevtarget = text
        type = self.get_selected_archive_type()['type']
        self.compose_command(path, type)

    def make_connects(self):
        self.connect(self.rev_combo, SIGNAL('currentIndexChanged(int)'),
                     self.rev_combo_changed)
        self.dest_btn.clicked.connect(self.browse_clicked)
        self.filesradio.toggled.connect(self.update_path)
        self.tarradio.toggled.connect(self.update_path)
        self.tbz2radio.toggled.connect(self.update_path)
        self.tgzradio.toggled.connect(self.update_path)
        self.uzipradio.toggled.connect(self.update_path)
        self.zipradio.toggled.connect(self.update_path)
        self.arch_btn.clicked.connect(self.archive)
        self.detail_btn.clicked.connect(self.detail_clicked)
        self.close_btn.clicked.connect(self.close)

    def rev_combo_changed(self, index):
        self.update_path()

    def browse_clicked(self):
        """Select the destination directory or file"""
        dest = hglib.fromunicode(self.dest_edit.text())
        if not os.path.exists(dest):
            dest = os.path.dirname(dest)
        select = self.get_selected_archive_type()
        FD = QFileDialog
        if select['type'] == 'files':
            caption = _('Select Destination Folder')
            path = FD.getExistingDirectory(parent=self, caption=caption,
                    options=FD.ShowDirsOnly | FD.ReadOnly)
            response = str(path)
        else:
            caption = _('Open File')
            ext = '*' + select['ext']
            filter = '%s (%s)\nAll Files (*.*)' % (select['label'], ext)
            filename = FD.getOpenFileName(parent=self, caption=caption,
                    directory=dest, filter=filter, options=FD.ReadOnly );
            response = str(filename)
        if response:
            self.dest_edit.setText(response)
            self.update_path()

    def compose_command(self, dest, type):
        cmdline = ['archive']
        rev = self.rev_combo.currentText()
        if rev == WD_PARENT:
            rev = '.'
        else:
            rev = hglib.fromunicode(rev)
            cmdline.append('-r')
            cmdline.append(rev)
        cmdline.append('-t')
        cmdline.append(type)
        if self.files_in_rev_chk.isChecked():
            ctx = self.repo[rev]
            for f in ctx.files():
                cmdline.append('-I')
                cmdline.append(f)
        cmdline.append('--')
        cmdline.append(hglib.fromunicode(dest))
        self.hgcmd_txt.setText(' '.join(cmdline))
        return cmdline

    def archive(self):
        # verify input
        type = self.get_selected_archive_type()['type']
        dest = self.dest_edit.text()
        if os.path.exists(dest):
            if type == 'files':
                if os.path.isfile(dest):
                    qtlib.WarningMsgBox(_('Duplicate Name'),
                            _('The destination "%s" already exists as '
                              'a file!' % dest))
                    return False
                elif os.listdir(dest):
                    if not qtlib.QuestionMsgBox(_('Confirm Overwrite'),
                                 _('The directory "%s" is not empty!\n\n'
                                   'Do you want to overwrite it?') % dest,
                                 parent=self):
                        return False
            else:
                if os.path.isfile(dest):
                    if not qtlib.QuestionMsgBox(_('Confirm Overwrite'),
                                 _('The file "%s" already exists!\n\n'
                                   'Do you want to overwrite it?') % dest,
                                 parent=self):
                        return False
                else:
                    qtlib.WarningMsgBox(_('Duplicate Name'),
                          _('The destination "%s" already exists as '
                            'a folder!' % dest))
                    return False

        # prepare command line
        cmdline = self.compose_command(dest, type)

        # start archiving
        self.cmd.run(cmdline)

    def detail_clicked(self):
        if self.cmd.is_show_output():
            self.cmd.show_output(False)
        else:
            self.cmd.show_output(True)

    def cancel_clicked():
        self.cmd.cancel()

    def command_started(self):
        self.dest_edit.setEnabled(False)
        self.rev_combo.setEnabled(False)
        self.dest_edit.setEnabled(False)
        self.dest_btn.setEnabled(False)
        self.filesradio.setEnabled(False)
        self.tarradio.setEnabled(False)
        self.tbz2radio.setEnabled(False)
        self.tgzradio.setEnabled(False)
        self.uzipradio.setEnabled(False)
        self.zipradio.setEnabled(False)
        self.cmd.setShown(True)
        self.arch_btn.setHidden(True)
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


def run(ui, *revs, **opts):
    rev = opts.get('rev')
    repo = hg.repository(ui, paths.find_root())
    return ArchiveDialog(repo.ui, repo, rev)


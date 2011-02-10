# clone.py - Clone dialog for TortoiseHg
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import ui, cmdutil, commands

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui, qtlib

class CloneDialog(QDialog):

    cmdfinished = pyqtSignal(int)

    def __init__(self, args=None, opts={}, parent=None):
        super(CloneDialog, self).__init__(parent)
        f = self.windowFlags()
        self.setWindowFlags(f & ~Qt.WindowContextHelpButtonHint)
        self.ui = ui.ui()
        self.ret = None

        dest = src = cwd = hglib.tounicode(os.getcwd())
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
        self.src_combo.lineEdit().returnPressed.connect(self.clone)
        self.src_btn = QPushButton(_('Browse...'))
        self.src_btn.setAutoDefault(False)
        self.src_btn.clicked.connect(self.browse_src)
        grid.addWidget(QLabel(_('Source:')), 0, 0)
        grid.addWidget(self.src_combo, 0, 1)
        grid.addWidget(self.src_btn, 0, 2)

        ### destination combo and button
        self.dest_combo = QComboBox()
        self.dest_combo.setEditable(True)
        self.dest_combo.setMinimumWidth(310)
        self.dest_combo.lineEdit().returnPressed.connect(self.clone)
        self.dest_btn = QPushButton(_('Browse...'))
        self.dest_btn.setAutoDefault(False)
        self.dest_btn.clicked.connect(self.browse_dest)
        grid.addWidget(QLabel(_('Destination:')), 1, 0)
        grid.addWidget(self.dest_combo, 1, 1)
        grid.addWidget(self.dest_btn, 1, 2)

        s = QSettings()
        self.shist = s.value('clone/source').toStringList()
        for path in self.shist:
            if path: self.src_combo.addItem(path)
        self.src_combo.setEditText(src)

        self.dhist = s.value('clone/dest').toStringList()
        for path in self.dhist:
            if path: self.dest_combo.addItem(path)
        self.dest_combo.setEditText(dest)

        ### options
        expander = qtlib.ExpanderLabel(_('Options'), False)
        expander.expanded.connect(self.show_options)
        grid.addWidget(expander, 2, 0, Qt.AlignLeft | Qt.AlignTop)

        optbox = QVBoxLayout()
        optbox.setSpacing(6)
        grid.addLayout(optbox, 2, 1, 1, 2)

        def chktext(chklabel, stretch=None):
            hbox = QHBoxLayout()
            hbox.setSpacing(0)
            optbox.addLayout(hbox)
            chk = QCheckBox(chklabel)
            text = QLineEdit(enabled=False)
            chk.toggled.connect(
                 lambda e: self.toggle_enabled(e, text))
            hbox.addWidget(chk)
            hbox.addWidget(text)
            if stretch is not None:
                hbox.addStretch(stretch)
            return chk, text

        self.rev_chk, self.rev_text = chktext(_('Clone to revision:'),
                                              stretch=40)

        self.noupdate_chk = QCheckBox(_('Do not update the new working directory'))
        self.pproto_chk = QCheckBox(_('Use pull protocol to copy metadata'))
        self.uncomp_chk = QCheckBox(_('Use uncompressed transfer'))
        self.qclone_chk = QCheckBox(_('Include patch queue'))
        optbox.addWidget(self.noupdate_chk)
        optbox.addWidget(self.pproto_chk)
        optbox.addWidget(self.uncomp_chk)
        optbox.addWidget(self.qclone_chk)

        self.proxy_chk = QCheckBox(_('Use proxy server'))
        optbox.addWidget(self.proxy_chk)
        useproxy = bool(self.ui.config('http_proxy', 'host'))
        self.proxy_chk.setEnabled(useproxy)
        self.proxy_chk.setChecked(useproxy)

        self.remote_chk, self.remote_text = chktext(_('Remote command:'))

        # allow to specify start revision for p4 & svn repos.
        self.startrev_chk, self.startrev_text = chktext(_('Start revision:'),
                                                        stretch=40)

        ## command widget
        self.cmd = cmdui.Widget()
        self.cmd.commandStarted.connect(self.command_started)
        self.cmd.commandFinished.connect(self.command_finished)
        self.cmd.commandFinished.connect(self.cmdfinished)
        self.cmd.commandCanceling.connect(self.command_canceling)
        box.addWidget(self.cmd)

        ## bottom buttons
        buttons = QDialogButtonBox()
        self.cancel_btn = buttons.addButton(QDialogButtonBox.Cancel)
        self.cancel_btn.clicked.connect(self.cmd.cancel)
        self.close_btn = buttons.addButton(QDialogButtonBox.Close)
        self.close_btn.clicked.connect(self.onCloseClicked)
        self.close_btn.setAutoDefault(False)
        self.clone_btn = buttons.addButton(_('&Clone'),
                                           QDialogButtonBox.ActionRole)
        self.clone_btn.clicked.connect(self.clone)
        self.detail_btn = buttons.addButton(_('Detail'),
                                            QDialogButtonBox.ResetRole)
        self.detail_btn.setAutoDefault(False)
        self.detail_btn.setCheckable(True)
        self.detail_btn.toggled.connect(self.detail_toggled)
        box.addWidget(buttons)

        # dialog setting
        self.setLayout(box)
        self.layout().setSizeConstraint(QLayout.SetFixedSize)
        self.setWindowTitle(_('Clone - %s') % cwd)
        self.setWindowIcon(qtlib.geticon('clone'))

        # prepare to show
        self.cmd.setHidden(True)
        self.cancel_btn.setHidden(True)
        self.detail_btn.setHidden(True)
        self.show_options(False)

        rev = opts.get('rev')
        if rev:
            self.rev_chk.setChecked(True)
            self.rev_text.setText(hglib.tounicode(', '.join(rev)))
        self.noupdate_chk.setChecked(bool(opts.get('noupdate')))
        self.pproto_chk.setChecked(bool(opts.get('pull')))
        self.uncomp_chk.setChecked(bool(opts.get('uncompressed')))

        self.src_combo.setFocus()
        self.src_combo.lineEdit().selectAll()

    def getDest(self):
        return hglib.fromunicode(self.dest_combo.currentText()).strip()

    ### Private Methods ###

    def show_options(self, visible):
        self.rev_chk.setVisible(visible)
        self.rev_text.setVisible(visible)
        self.noupdate_chk.setVisible(visible)
        self.pproto_chk.setVisible(visible)
        self.uncomp_chk.setVisible(visible)
        self.proxy_chk.setVisible(visible)
        self.qclone_chk.setVisible(visible)
        self.remote_chk.setVisible(visible)
        self.remote_text.setVisible(visible)
        self.startrev_chk.setVisible(visible and self.startrev_available())
        self.startrev_text.setVisible(visible and self.startrev_available())

    def startrev_available(self):
        entry = cmdutil.findcmd('clone', commands.table)[1]
        longopts = set(e[1] for e in entry[1])
        return 'startrev' in longopts

    def clone(self):
        if self.cmd.core.running():
            return
        # prepare user input
        srcQ = self.src_combo.currentText().trimmed()
        src = hglib.fromunicode(srcQ)
        destQ = self.dest_combo.currentText().trimmed()
        dest = hglib.fromunicode(destQ)
        if not dest:
            dest = os.path.basename(src)
            destQ = QString(hglib.tounicode(dest))

        if not dest.startswith('ssh://'):
            if not os.path.exists(dest):
                try:
                    os.mkdir(dest)
                except EnvironmentError:
                    qtlib.ErrorMsgBox(_('TortoiseHg Clone'),
                    _('Error creating destination folder'),
                    _('Please specify a different path.'))
                    return False

        if srcQ:
            l = list(self.shist)
            if srcQ in l:
                l.remove(srcQ)
            l.insert(0, srcQ)
            self.shist = l[:10]
        if destQ:
            l = list(self.dhist)
            if destQ in l:
                l.remove(destQ)
            l.insert(0, destQ)
            self.dhist = l[:10]
        s = QSettings()
        s.setValue('clone/source', self.shist)
        s.setValue('clone/dest', self.dhist)

        remotecmd = hglib.fromunicode(self.remote_text.text().trimmed())
        rev = hglib.fromunicode(self.rev_text.text().trimmed())
        startrev = hglib.fromunicode(self.startrev_text.text().trimmed())

        # verify input
        if src == '':
            qtlib.ErrorMsgBox(_('TortoiseHg Clone'),
                  _('Source path is empty'),
                  _('Please enter a valid source path.'))
            self.src_combo.setFocus()
            return False

        if src == dest:
            qtlib.ErrorMsgBox(_('TortoiseHg Clone'),
                  _('Source and destination are the same'),
                  _('Please specify different paths.'))
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
        if self.qclone_chk.isChecked():
            cmdline = ['qclone']
        else:
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
        if self.remote_chk.isChecked() and remotecmd:
            cmdline.append('--remotecmd')
            cmdline.append(remotecmd)
        if self.rev_chk.isChecked() and rev:
            cmdline.append('--rev')
            cmdline.append(rev)
        if self.startrev_chk.isChecked() and startrev:
            cmdline.append('--startrev')
            cmdline.append(startrev)

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

    def detail_toggled(self, checked):
        self.cmd.setShowOutput(checked)

    def browse_src(self):
        FD = QFileDialog
        caption = _("Select source repository")
        path = FD.getExistingDirectory(self, caption)
        if path:
            self.src_combo.setEditText(path)
            self.src_combo.setFocus()

    def browse_dest(self):
        FD = QFileDialog
        caption = _("Select destination repository")
        path = FD.getExistingDirectory(self, caption)
        if path:
            self.dest_combo.setEditText(path)
            self.dest_combo.setFocus()

    def command_started(self):
        self.cmd.setShown(True)
        self.clone_btn.setHidden(True)
        self.close_btn.setHidden(True)
        self.cancel_btn.setShown(True)
        self.detail_btn.setShown(True)

    def command_finished(self, ret):
        self.ret = ret
        if ret is not 0 or self.cmd.outputShown():
            self.detail_btn.setChecked(True)
            self.clone_btn.setShown(True)
            self.close_btn.setShown(True)
            self.close_btn.setAutoDefault(True)
            self.close_btn.setFocus()
            self.cancel_btn.setHidden(True)
        else:
            self.accept()

    def onCloseClicked(self):
        if self.ret is 0:
            self.accept()
        else:
            self.reject()

    def command_canceling(self):
        self.cancel_btn.setDisabled(True)

def run(ui, *pats, **opts):
    return CloneDialog(pats, opts)

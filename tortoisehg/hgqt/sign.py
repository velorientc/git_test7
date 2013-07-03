# sign.py - Sign dialog for TortoiseHg
#
# Copyright 2013 Elson Wei <elson.wei@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, cmdui

class SignDialog(QDialog):
    showMessage = pyqtSignal(QString)
    output = pyqtSignal(QString, QString)
    makeLogVisible = pyqtSignal(bool)

    def __init__(self, repo, rev, parent=None):
        super(SignDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() &
                            ~Qt.WindowContextHelpButtonHint)
        self.repo = repo
        self.rev = rev

        # base layout box
        base = QVBoxLayout()
        base.setSpacing(0)
        base.setContentsMargins(*(0,)*4)
        base.setSizeConstraint(QLayout.SetFixedSize)
        self.setLayout(base)

        box = QVBoxLayout()
        box.setSpacing(8)
        box.setContentsMargins(*(8,)*4)
        self.layout().addLayout(box)

        ## main layout grid
        form = QFormLayout(fieldGrowthPolicy=QFormLayout.AllNonFixedFieldsGrow)
        box.addLayout(form)

        form.addRow(_('Revision:'), QLabel('%d (%s)' % (rev, repo[rev])))

        ### key line edit
        key = repo.ui.config("gpg", "key", None)
        self.keyLineEdit = QLineEdit()
        if key:
            self.keyLineEdit.setText(key)
        form.addRow(_('Key:'), self.keyLineEdit)

        ### options
        expander = qtlib.ExpanderLabel(_('Options'), False)
        expander.expanded.connect(self.show_options)
        box.addWidget(expander)

        optbox = QVBoxLayout()
        optbox.setSpacing(6)
        box.addLayout(optbox)

        hbox = QHBoxLayout()
        hbox.setSpacing(0)
        optbox.addLayout(hbox)

        self.localCheckBox = QCheckBox(_('Local sign'))
        self.localCheckBox.toggled.connect(self.updateStates)
        optbox.addWidget(self.localCheckBox)

        self.replaceCheckBox = QCheckBox(_('Sign even if the sigfile is '
                                           'modified (-f/--force)'))
        self.replaceCheckBox.toggled.connect(self.updateStates)
        optbox.addWidget(self.replaceCheckBox)

        self.nocommitCheckBox = QCheckBox(_('No commit'))
        self.nocommitCheckBox.toggled.connect(self.updateStates)
        optbox.addWidget(self.nocommitCheckBox)

        self.customCheckBox = QCheckBox(_('Use custom commit message:'))
        self.customCheckBox.toggled.connect(self.customMessageToggle)
        optbox.addWidget(self.customCheckBox)

        self.customTextLineEdit = QLineEdit()
        optbox.addWidget(self.customTextLineEdit)

        ## bottom buttons
        BB = QDialogButtonBox
        bbox = QDialogButtonBox()
        self.signBtn = bbox.addButton(_('&Sign'), BB.ActionRole)
        bbox.addButton(BB.Close)
        bbox.rejected.connect(self.reject)
        box.addWidget(bbox)

        self.signBtn.clicked.connect(self.onSign)

        ## horizontal separator
        self.sep = QFrame()
        self.sep.setFrameShadow(QFrame.Sunken)
        self.sep.setFrameShape(QFrame.HLine)
        self.layout().addWidget(self.sep)

        ## status line
        self.status = qtlib.StatusLabel()
        self.status.setContentsMargins(4, 2, 4, 4)
        self.layout().addWidget(self.status)

        self.cmd = cmdui.Runner(False, self)
        self.cmd.output.connect(self.output)
        self.cmd.makeLogVisible.connect(self.makeLogVisible)
        self.cmd.commandFinished.connect(self.commandFinished)

        # prepare to show
        self.setWindowTitle(_('Sign - %s') % repo.displayname)
        self.setWindowIcon(qtlib.geticon('hg-sign'))

        self.clear_status()
        self.show_options(False)
        self.customMessageToggle(False)
        self.keyLineEdit.setFocus()

    def show_options(self, visible):
        self.localCheckBox.setVisible(visible)
        self.replaceCheckBox.setVisible(visible)
        self.nocommitCheckBox.setVisible(visible)
        self.customCheckBox.setVisible(visible)
        self.customTextLineEdit.setVisible(visible)

    def commandFinished(self, ret):
        if ret == 0:
            self.set_status(_("Signature has been added"))

    @pyqtSlot()
    def updateStates(self):
        nocommit = self.nocommitCheckBox.isChecked()
        custom = self.customCheckBox.isChecked()
        self.customCheckBox.setEnabled(not nocommit)
        self.customTextLineEdit.setEnabled(not nocommit and custom)

    def onSign(self):
        if self.cmd.core.running():
            self.set_status(_('Repository command still running'), False)
            return

        keyu = self.keyLineEdit.text()
        key = hglib.fromunicode(keyu)
        local = self.localCheckBox.isChecked()
        force = self.replaceCheckBox.isChecked()
        nocommit = self.nocommitCheckBox.isChecked()
        if self.customCheckBox.isChecked():
            msgu = self.customTextLineEdit.text()
            msg = hglib.fromunicode(msgu)
        else:
            msg = None

        user = qtlib.getCurrentUsername(self, self.repo)
        if not user:
            return

        cmd = ['sign', '--repository', self.repo.root, '--user', user]

        if key:
            cmd.append('--key=%s' % key)

        if force:
            cmd.append('--force')

        if local:
            cmd.append('--local')

        if nocommit:
            cmd.append('--no-commit')
        else:
            if msg:
                cmd.append('--message=%s' % msg)

        cmd.append(str(self.rev))
        self.cmd.run(cmd)

    def customMessageToggle(self, checked):
        self.customTextLineEdit.setEnabled(checked)
        if checked:
            self.customTextLineEdit.setFocus()

    def set_status(self, text, icon=None):
        self.status.setShown(True)
        self.sep.setShown(True)
        self.status.set_status(text, icon)
        self.showMessage.emit(text)

    def clear_status(self):
        self.status.setHidden(True)
        self.sep.setHidden(True)

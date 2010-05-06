# update.py - Update dialog for TortoiseHg
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import QString, Qt
from PyQt4.QtGui import QDialog, QDialogButtonBox, QVBoxLayout, QGridLayout
from PyQt4.QtGui import QComboBox, QLabel, QLayout, QSpacerItem, QCheckBox
from PyQt4.QtGui import QPushButton

from mercurial import hg, ui, error

from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui, csinfo

class UpdateDialog(QDialog):

    def __init__(self, rev=None, repo=None, parent=None, opts=None):
        super(UpdateDialog, self).__init__(parent, Qt.WindowTitleHint or
                                                   Qt.WindowSystemMenuHint)

        self.ui = ui.ui()
        if repo:
            self.repo = repo
        else:
            root = paths.find_root()
            if root:
                self.repo = hg.repository(self.ui, path=root)
            else:
                raise 'not repository'

        # base layout box
        box = QVBoxLayout()
        box.setSpacing(6)

        ## main layout grid
        grid = QGridLayout()
        grid.setSpacing(6)
        box.addLayout(grid)

        ### target revision combo
        self.rev_combo = combo = QComboBox()
        combo.setEditable(True)
        grid.addWidget(QLabel(_('Update to:')), 0, 0)
        grid.addWidget(combo, 0, 1)

        if rev is None:
            combo.addItem(self.repo.dirstate.branch())
        else:
            combo.addItem(QString(rev))
        combo.setCurrentIndex(0)
        for name in hglib.getlivebranch(self.repo):
            combo.addItem(name)

        tags = list(self.repo.tags())
        tags.sort()
        tags.reverse()
        for tag in tags:
            combo.addItem(hglib.tounicode(tag))

        ### target revision info
        items = ('%(rev)s', ' %(branch)s', ' %(tags)s', '<br />%(summary)s')
        style = csinfo.labelstyle(contents=items, width=350)
        factory = csinfo.factory(self.repo, style=style)
        self.target_info = factory()
        grid.addWidget(QLabel(_('Target:')), 1, 0, Qt.AlignLeft | Qt.AlignTop)
        grid.addWidget(self.target_info, 1, 1)

        ### parent revision info
        self.ctxs = self.repo[None].parents()
        if len(self.ctxs) == 2:
            self.p1_info = factory()
            grid.addWidget(QLabel(_('Parent 1:')), 2, 0, Qt.AlignLeft | Qt.AlignTop)
            grid.addWidget(self.p1_info, 2, 1)
            self.p2_info = factory()
            grid.addWidget(QLabel(_('Parent 2:')), 3, 0, Qt.AlignLeft | Qt.AlignTop)
            grid.addWidget(self.p2_info, 3, 1)
        else:
            self.p1_info = factory()
            grid.addWidget(QLabel(_('Parent:')), 2, 0, Qt.AlignLeft | Qt.AlignTop)
            grid.addWidget(self.p1_info, 2, 1)

        ### options
        optbox = QVBoxLayout()
        optbox.setSpacing(6)
        grid.addWidget(QLabel(_('Options:')), 3, 0, Qt.AlignLeft | Qt.AlignTop)
        grid.addLayout(optbox, 3, 1)

        self.discard_chk = QCheckBox(_('Discard local changes, no backup (-C/--clean)'))
        self.merge_chk = QCheckBox(_('Always merge (when possible)'))
        self.showlog_chk = QCheckBox(_('Always show command log'))
        optbox.addWidget(self.discard_chk)
        optbox.addWidget(self.merge_chk)
        optbox.addWidget(self.showlog_chk)

        self.discard_chk.setChecked(bool(opts.get('clean', False)))

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
        self.update_btn = buttons.addButton(_('&Update'),
                                            QDialogButtonBox.ActionRole)
        self.update_btn.clicked.connect(self.update_clicked)
        box.addWidget(buttons)

        # signal handlers
        self.rev_combo.editTextChanged.connect(lambda *a: self.update_info())
        self.rev_combo.lineEdit().returnPressed.connect(self.update_clicked)
        self.discard_chk.toggled.connect(lambda *a: self.update_info())

        # dialog setting
        self.setLayout(box)
        self.layout().setSizeConstraint(QLayout.SetFixedSize)
        self.setWindowTitle(_('Update - %s') % hglib.get_reponame(self.repo))

        # prepare to show
        self.rev_combo.lineEdit().selectAll()
        self.cmd.setHidden(True)
        self.cancel_btn.setHidden(True)
        self.update_info()

    ### Private Methods ###

    def update_info(self):
        self.p1_info.update(self.ctxs[0])
        merge = len(self.ctxs) == 2
        if merge:
            self.p2_info.update(self.ctxs[1])
        new_rev = hglib.fromunicode(self.rev_combo.currentText())
        try:
            new_ctx = self.repo[new_rev]
            if not merge and new_ctx.rev() == self.ctxs[0].rev():
                self.target_info.setPlainText(_('(same as parent)'))
                clean = self.discard_chk.isChecked()
                self.update_btn.setEnabled(clean)
            else:
                self.target_info.update(self.repo[new_rev])
                self.update_btn.setEnabled(True)
        except (error.LookupError, error.RepoLookupError, error.RepoError):
            self.target_info.setPlainText(_('unknown revision!'))
            self.update_btn.setDisabled(True)

    ### Signal Handlers ###

    def update_clicked(self):
        self.cmd.run(['update', hglib.fromunicode(self.rev_combo.currentText())])

    def cancel_clicked(self):
        self.cmd.cancel()

    def command_started(self):
        self.cmd.setShown(True)
        if self.showlog_chk.isVisible():
            self.cmd.show_output(True)
        self.update_btn.setHidden(True)
        self.close_btn.setHidden(True)
        self.cancel_btn.setShown(True)

    def command_finished(self, wrapper):
        if wrapper.data is not 0 or self.cmd.is_show_output():
            self.cmd.show_output(True)
            self.close_btn.setShown(True)
            self.cancel_btn.setHidden(True)
        else:
            self.reject()

    def command_canceling(self):
        self.cancel_btn.setDisabled(True)

def run(ui, *pats, **opts):
    rev = None
    if opts.get('rev'):
        rev = opts.get('rev')
    elif len(pats) == 1:
        rev = pats[0]
    return UpdateDialog(rev, opts=opts)

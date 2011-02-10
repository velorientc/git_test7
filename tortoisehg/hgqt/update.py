# update.py - Update dialog for TortoiseHg
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import error, merge as mergemod

from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui, csinfo, qtlib, thgrepo, resolve

class UpdateDialog(QDialog):

    output = pyqtSignal(QString, QString)
    progress = pyqtSignal(QString, object, QString, QString, object)
    makeLogVisible = pyqtSignal(bool)

    def __init__(self, repo, rev=None, parent=None, opts={}):
        super(UpdateDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & \
                            ~Qt.WindowContextHelpButtonHint)

        self._finished = False
        self.repo = repo

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
            rev = self.repo.dirstate.branch()
        else:
            rev = str(rev)
        combo.addItem(hglib.tounicode(rev))
        combo.setCurrentIndex(0)
        for name in hglib.getlivebranch(self.repo):
            combo.addItem(hglib.tounicode(name))

        tags = list(self.repo.tags())
        tags.sort()
        tags.reverse()
        for tag in tags:
            combo.addItem(hglib.tounicode(tag))

        ### target revision info
        items = ('%(rev)s', ' %(branch)s', ' %(tags)s', '<br />%(summary)s')
        style = csinfo.labelstyle(contents=items, width=350, selectable=True)
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
        expander = qtlib.ExpanderLabel(_('Options:'), False)
        expander.expanded.connect(self.show_options)
        row = grid.rowCount()
        grid.addWidget(expander, row, 0, Qt.AlignLeft | Qt.AlignTop)
        grid.addLayout(optbox, row, 1)

        self.discard_chk = QCheckBox(_('Discard local changes, no backup'
                                       ' (-C/--clean)'))
        self.merge_chk = QCheckBox(_('Always merge (when possible)'))
        self.autoresolve_chk = QCheckBox(_('Automatically resolve merge conflicts '
                                           'where possible'))
        self.showlog_chk = QCheckBox(_('Always show command log'))
        optbox.addWidget(self.discard_chk)
        optbox.addWidget(self.merge_chk)
        optbox.addWidget(self.autoresolve_chk)
        optbox.addWidget(self.showlog_chk)

        self.discard_chk.setChecked(bool(opts.get('clean')))
        self.autoresolve_chk.setChecked(
            repo.ui.configbool('tortoisehg', 'autoresolve', False))

        ## command widget
        if self.parent:
            self.cmd = cmdui.Runner(_('TortoiseHg Update'), False, self)
        else:
            self.cmd = cmdui.Widget(True, self)
            box.addWidget(self.cmd)
        self.cmd.commandStarted.connect(self.command_started)
        self.cmd.commandFinished.connect(self.command_finished)
        self.cmd.commandCanceling.connect(self.command_canceling)
        self.cmd.output.connect(self.output)
        self.cmd.makeLogVisible.connect(self.makeLogVisible)
        self.cmd.progress.connect(self.progress)

        ## bottom buttons
        buttons = QDialogButtonBox()
        self.cancel_btn = buttons.addButton(QDialogButtonBox.Cancel)
        self.cancel_btn.clicked.connect(self.cancel_clicked)
        self.close_btn = buttons.addButton(QDialogButtonBox.Close)
        self.close_btn.clicked.connect(self.reject)
        self.close_btn.setAutoDefault(False)
        self.update_btn = buttons.addButton(_('&Update'),
                                            QDialogButtonBox.ActionRole)
        self.update_btn.clicked.connect(self.update)
        self.detail_btn = buttons.addButton(_('Detail'),
                                            QDialogButtonBox.ResetRole)
        self.detail_btn.setAutoDefault(False)
        self.detail_btn.setCheckable(True)
        self.detail_btn.toggled.connect(self.detail_toggled)
        box.addWidget(buttons)

        # signal handlers
        self.rev_combo.editTextChanged.connect(lambda *a: self.update_info())
        self.discard_chk.toggled.connect(lambda *a: self.update_info())

        # dialog setting
        self.setLayout(box)
        self.layout().setSizeConstraint(QLayout.SetFixedSize)
        self.setWindowTitle(_('Update - %s') % self.repo.displayname)
        self.setWindowIcon(qtlib.geticon('update'))

        # prepare to show
        self.rev_combo.lineEdit().selectAll()
        self.cmd.setHidden(True)
        self.cancel_btn.setHidden(True)
        self.detail_btn.setHidden(True)
        self.merge_chk.setHidden(True)
        self.autoresolve_chk.setHidden(True)
        self.showlog_chk.setHidden(True)
        self.update_info()

    ### Private Methods ###

    def update_info(self):
        self.p1_info.update(self.ctxs[0].node())
        merge = len(self.ctxs) == 2
        if merge:
            self.p2_info.update(self.ctxs[1])
        new_rev = hglib.fromunicode(self.rev_combo.currentText())
        if new_rev.lower() == 'null':
            self.update_btn.setEnabled(True)
            return
        try:
            new_ctx = self.repo[new_rev]
            if not merge and new_ctx.rev() == self.ctxs[0].rev():
                self.target_info.setText(_('(same as parent)'))
                clean = self.discard_chk.isChecked()
                self.update_btn.setEnabled(clean)
            else:
                self.target_info.update(self.repo[new_rev])
                self.update_btn.setEnabled(True)
        except (error.LookupError, error.RepoLookupError, error.RepoError):
            self.target_info.setText(_('unknown revision!'))
            self.update_btn.setDisabled(True)

    def update(self):
        cmdline = ['update', '--repository', self.repo.root, '--verbose']
        cmdline += ['--config', 'ui.merge=internal:' +
                    (self.autoresolve_chk.isChecked() and 'merge' or 'fail')]
        rev = hglib.fromunicode(self.rev_combo.currentText())
        cmdline.append('--rev')
        cmdline.append(rev)

        if self.discard_chk.isChecked():
            cmdline.append('--clean')
        else:
            cur = self.repo['.']
            try:
                node = self.repo[rev]
            except (error.LookupError, error.RepoLookupError, error.RepoError):
                return
            def isclean():
                '''whether WD is changed'''
                wc = self.repo[None]
                return not (wc.modified() or wc.added() or wc.removed())
            def ismergedchange():
                '''whether the local changes are merged (have 2 parents)'''
                wc = self.repo[None]
                return len(wc.parents()) == 2
            def iscrossbranch(p1, p2):
                '''whether p1 -> p2 crosses branch'''
                pa = p1.ancestor(p2)
                return p1.branch() != p2.branch() or (p1 != pa and p2 != pa)
            def islocalmerge(p1, p2, clean=None):
                if clean is None:
                    clean = isclean()
                pa = p1.ancestor(p2)
                return not clean and (p1 == pa or p2 == pa)
            def confirmupdate(clean=None):
                if clean is None:
                    clean = isclean()

                msg = _('Detected uncommitted local changes in working tree.\n'
                        'Please select to continue:\n\n')
                data = {'discard': (_('&Discard'),
                                    _('Discard - discard local changes, no backup')),
                        'shelve': (_('&Shelve'),
                                  _('Shelve - move local changes to a patch')),
                        'merge': (_('&Merge'),
                                  _('Merge - allow to merge with local changes')),}

                opts = [data['discard']]
                if not ismergedchange():
                    opts.append(data['shelve'])
                if islocalmerge(cur, node, clean):
                    opts.append(data['merge'])

                msg += '\n'.join([desc for label, desc in opts if desc])
                dlg = QMessageBox(QMessageBox.Question, _('Confirm Update'),
                                  msg, QMessageBox.Cancel, self)
                buttons = {}
                for name in ('discard', 'shelve', 'merge'):
                    label, desc = data[name]
                    buttons[name] = dlg.addButton(label, QMessageBox.ActionRole)
                dlg.exec_()
                return buttons, dlg.clickedButton()

            # If merge-by-default, we want to merge whenever possible,
            # without prompting user (similar to command-line behavior)
            defaultmerge = self.merge_chk.isChecked()
            clean = isclean()
            if clean:
                cmdline.append('--check')
            elif not (defaultmerge and islocalmerge(cur, node, clean)):
                buttons, clicked = confirmupdate(clean)
                if buttons['discard'] == clicked:
                    cmdline.append('--clean')
                elif buttons['shelve'] == clicked:
                    from tortoisehg.hgqt import shelve
                    dlg = shelve.ShelveDialog(self.repo, self)
                    dlg.finished.connect(dlg.deleteLater)
                    dlg.exec_()
                    return
                elif buttons['merge'] == clicked:
                    pass # no args
                else:
                    return

        # start updating
        self.repo.incrementBusyCount()
        self.cmd.run(cmdline)

    ### Signal Handlers ###

    def cancel_clicked(self):
        self.cmd.cancel()
        self.reject()

    def detail_toggled(self, checked):
        self.cmd.setShowOutput(checked)

    def show_options(self, visible):
        self.merge_chk.setShown(visible)
        self.autoresolve_chk.setShown(visible)
        self.showlog_chk.setShown(visible)

    def command_started(self):
        self.cmd.setShown(True)
        if self.showlog_chk.isChecked():
            self.detail_btn.setChecked(True)
        self.update_btn.setHidden(True)
        self.close_btn.setHidden(True)
        self.cancel_btn.setShown(True)
        self.detail_btn.setShown(not self.parent())

    def command_finished(self, ret):
        self.repo.decrementBusyCount()
        if ret not in (0, 1) or self.cmd.outputShown():
            self.detail_btn.setChecked(True)
            self.close_btn.setShown(True)
            self.close_btn.setAutoDefault(True)
            self.close_btn.setFocus()
            self.cancel_btn.setHidden(True)
        else:
            self.accept()

    def accept(self):
        ms = mergemod.mergestate(self.repo)
        for path in ms:
            if ms[path] == 'u':
                qtlib.InfoMsgBox(_('Merge caused file conflicts'),
                                 _('File conflicts need to be resolved'))
                dlg = resolve.ResolveDialog(self.repo, self)
                dlg.finished.connect(dlg.deleteLater)
                dlg.exec_()
                break
        super(UpdateDialog, self).accept()

    def command_canceling(self):
        self.cancel_btn.setDisabled(True)

def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    from tortoisehg.hgqt import thgrepo
    repo = thgrepo.repository(ui, path=paths.find_root())
    rev = None
    if opts.get('rev'):
        rev = opts.get('rev')
    elif len(pats) == 1:
        rev = pats[0]
    return UpdateDialog(repo, rev, None, opts)

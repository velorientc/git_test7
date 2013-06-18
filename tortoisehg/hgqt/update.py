# update.py - Update dialog for TortoiseHg
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from mercurial import error

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui, csinfo, qtlib, thgrepo, resolve

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class UpdateDialog(QDialog):

    output = pyqtSignal(QString, QString)
    progress = pyqtSignal(QString, object, QString, QString, object)
    makeLogVisible = pyqtSignal(bool)

    def __init__(self, repo, rev=None, parent=None, opts={}):
        super(UpdateDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & \
                            ~Qt.WindowContextHelpButtonHint)

        self.repo = repo

        # base layout box
        box = QVBoxLayout()
        box.setSpacing(6)

        ## main layout grid
        self.grid = QGridLayout()
        self.grid.setSpacing(6)
        box.addLayout(self.grid)

        ### target revision combo
        self.rev_combo = combo = QComboBox()
        combo.setEditable(True)
        self.grid.addWidget(QLabel(_('Update to:')), 0, 0)
        self.grid.addWidget(combo, 0, 1)

        # Give the combo box a minimum width that will ensure that the dialog is
        # large enough to fit the additional progress bar that will appear when
        # updating subrepositories.
        combo.setMinimumWidth(450)

        # always include integer revision
        try:
            assert not isinstance(rev, (unicode, QString))
            ctx = self.repo[rev]
            if isinstance(ctx.rev(), int):  # could be None or patch name
                combo.addItem(str(ctx.rev()))
        except error.RepoLookupError:
            pass

        for name in repo.namedbranches:
            combo.addItem(hglib.tounicode(name))

        tags = list(self.repo.tags()) + repo._bookmarks.keys()
        tags.sort(reverse=True)
        for tag in tags:
            combo.addItem(hglib.tounicode(tag))

        if rev is None:
            selecturev = hglib.tounicode(self.repo.dirstate.branch())
        else:
            selecturev = hglib.tounicode(str(rev))
        selectindex = combo.findText(selecturev)
        if selectindex >= 0:
            combo.setCurrentIndex(selectindex)
        else:
            combo.setEditText(selecturev)

        ### target revision info
        items = ('%(rev)s', ' %(branch)s', ' %(tags)s', '<br />%(summary)s')
        style = csinfo.labelstyle(contents=items, width=350, selectable=True)
        factory = csinfo.factory(self.repo, style=style)
        self.target_info = factory()
        self.grid.addWidget(QLabel(_('Target:')), 1, 0, Qt.AlignLeft | Qt.AlignTop)
        self.grid.addWidget(self.target_info, 1, 1)

        ### parent revision info
        self.ctxs = self.repo[None].parents()
        if len(self.ctxs) == 2:
            self.p1_info = factory()
            self.grid.addWidget(QLabel(_('Parent 1:')), 2, 0, Qt.AlignLeft | Qt.AlignTop)
            self.grid.addWidget(self.p1_info, 2, 1)
            self.p2_info = factory()
            self.grid.addWidget(QLabel(_('Parent 2:')), 3, 0, Qt.AlignLeft | Qt.AlignTop)
            self.grid.addWidget(self.p2_info, 3, 1)
        else:
            self.p1_info = factory()
            self.grid.addWidget(QLabel(_('Parent:')), 2, 0, Qt.AlignLeft | Qt.AlignTop)
            self.grid.addWidget(self.p1_info, 2, 1)

        ### options
        self.optbox = QVBoxLayout()
        self.optbox.setSpacing(6)
        expander = qtlib.ExpanderLabel(_('Options:'), False)
        expander.expanded.connect(self.show_options)
        row = self.grid.rowCount()
        self.grid.addWidget(expander, row, 0, Qt.AlignLeft | Qt.AlignTop)
        self.grid.addLayout(self.optbox, row, 1)

        self.verbose_chk = QCheckBox(_('List updated files (--verbose)'))
        self.discard_chk = QCheckBox(_('Discard local changes, no backup '
                                       '(-C/--clean)'))
        self.merge_chk = QCheckBox(_('Always merge (when possible)'))
        self.autoresolve_chk = QCheckBox(_('Automatically resolve merge conflicts '
                                           'where possible'))
        self.showlog_chk = QCheckBox(_('Always show command log'))
        self.optbox.addWidget(self.verbose_chk)
        self.optbox.addWidget(self.discard_chk)
        self.optbox.addWidget(self.merge_chk)
        self.optbox.addWidget(self.autoresolve_chk)
        self.optbox.addWidget(self.showlog_chk)

        s = QSettings()

        self.discard_chk.setChecked(bool(opts.get('clean')))

        #### Persisted Options
        self.merge_chk.setChecked(
            QSettings().value('update/merge', False).toBool())

        self.autoresolve_chk.setChecked(
            repo.ui.configbool('tortoisehg', 'autoresolve', False) or
                s.value('update/autoresolve', False).toBool())

        self.showlog_chk.setChecked(s.value('update/showlog', False).toBool())
        self.verbose_chk.setChecked(s.value('update/verbose', False).toBool())

        ## command widget
        self.cmd = cmdui.Widget(True, True, self)
        self.cmd.commandStarted.connect(self.command_started)
        self.cmd.commandFinished.connect(self.command_finished)
        self.cmd.commandCanceling.connect(self.command_canceling)
        self.cmd.output.connect(self.output)
        self.cmd.makeLogVisible.connect(self.makeLogVisible)
        self.cmd.progress.connect(self.progress)
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
        self.update_btn.clicked.connect(self.update)
        self.detail_btn = buttons.addButton(_('Detail'),
                                            QDialogButtonBox.ResetRole)
        self.detail_btn.setAutoDefault(False)
        self.detail_btn.setCheckable(True)
        self.detail_btn.toggled.connect(self.detail_toggled)
        box.addWidget(buttons)

        # signal handlers
        self.rev_combo.editTextChanged.connect(self.update_info)
        self.discard_chk.toggled.connect(self.update_info)

        # dialog setting
        self.setLayout(box)
        self.layout().setSizeConstraint(QLayout.SetFixedSize)
        self.setWindowTitle(_('Update - %s') % self.repo.displayname)
        self.setWindowIcon(qtlib.geticon('hg-update'))

        # prepare to show
        self.cmd.setHidden(True)
        self.cancel_btn.setHidden(True)
        self.detail_btn.setHidden(True)
        self.merge_chk.setHidden(True)
        self.autoresolve_chk.setHidden(True)
        self.showlog_chk.setHidden(True)
        self.update_info()
        if not self.update_btn.isEnabled():
            self.rev_combo.lineEdit().selectAll()  # need to change rev

        # expand options if a hidden one is checked
        hiddenOptionsChecked = self.hiddenSettingIsChecked()
        self.show_options(hiddenOptionsChecked)
        expander.set_expanded(hiddenOptionsChecked)

    ### Private Methods ###
    def hiddenSettingIsChecked(self):
        if self.merge_chk.isChecked() or self.autoresolve_chk.isChecked() or self.showlog_chk.isChecked():
            return True
        else:
            return False

    def saveSettings(self):
        QSettings().setValue('update/verbose', self.verbose_chk.isChecked())
        QSettings().setValue('update/merge', self.merge_chk.isChecked())
        QSettings().setValue('update/autoresolve', self.autoresolve_chk.isChecked())
        QSettings().setValue('update/showlog', self.showlog_chk.isChecked())

    def update_info(self, *args):
        self.p1_info.update(self.ctxs[0].node())
        merge = len(self.ctxs) == 2
        if merge:
            self.p2_info.update(self.ctxs[1])
        new_rev = hglib.fromunicode(self.rev_combo.currentText())
        if new_rev == 'null':
            self.target_info.setText(_('remove working directory'))
            self.update_btn.setEnabled(True)
            return
        try:
            new_ctx = self.repo[new_rev]
            if not merge and new_ctx.rev() == self.ctxs[0].rev() \
                    and not new_ctx.bookmarks():
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
        self.saveSettings()
        cmdline = ['update', '--repository', self.repo.root]
        if self.verbose_chk.isChecked():
            cmdline += ['--verbose']
        cmdline += ['--config', 'ui.merge=internal:' +
                    (self.autoresolve_chk.isChecked() and 'merge' or 'fail')]
        rev = hglib.fromunicode(self.rev_combo.currentText())

        activatebookmarkmode = self.repo.ui.config(
            'tortoisehg', 'activatebookmarks', 'prompt')
        if activatebookmarkmode != 'never':
            bookmarks = self.repo[rev].bookmarks()
            if bookmarks and rev not in bookmarks:
                # The revision that we are updating into has bookmarks,
                # but the user did not refer to the revision by one of them
                # (probably used a revision number or hash)
                # Ask the user if it wants to update to one of these bookmarks
                # instead
                selectedbookmark = None
                if len(bookmarks) == 1:
                    if activatebookmarkmode == 'auto':
                        activatebookmark = True
                    else:
                        activatebookmark = qtlib.QuestionMsgBox(
                            _('Activate bookmark?'),
                            _('The selected revision (%s) has a bookmark on it '
                            'called "<i>%s</i>".<p>Do you want to activate it?'
                            '<br></b><i>You can disable this prompt by configuring '
                            'Settings/Workbench/Activate Bookmarks</i>') \
                            % (hglib.tounicode(rev), bookmarks[0]))
                    if activatebookmark:
                        selectedbookmark = bookmarks[0]
                else:
                    # Even in auto mode, when there is more than one bookmark
                    # we must ask the user which one must be activated
                    selectedbookmark = qtlib.ChoicePrompt(
                        _('Activate bookmark?'),
                        _('The selected revision (<i>%s</i>) has <i>%d</i> '
                        'bookmarks on it.<p>Select the bookmark that you want '
                        'to activate and click <i>OK</i>.<p>Click <i>Cancel</i> '
                        'if you don\'t want to activate any of them.<p>'
                        '<p><i>You can disable this prompt by configuring '
                        'Settings/Workbench/Activate Bookmarks</i><p>') \
                        % (hglib.tounicode(rev), len(bookmarks)),
                        self, bookmarks, self.repo._bookmarkcurrent).run()
                if selectedbookmark:
                    rev = selectedbookmark
                elif self.repo[rev] == self.repo[self.repo._bookmarkcurrent]:
                    deactivatebookmark = qtlib.QuestionMsgBox(
                        _('Deactivate current bookmark?'),
                        _('Do you really want to deactivate the <i>%s</i> '
                        'bookmark?') % self.repo._bookmarkcurrent)
                    if deactivatebookmark:
                        cmdline = ['bookmark', '--repository', self.repo.root]
                        if self.verbose_chk.isChecked():
                            cmdline += ['--verbose']
                        cmdline += ['-i', self.repo._bookmarkcurrent]
                        self.repo.incrementBusyCount()
                        self.cmd.run(cmdline)
                    return

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
                try:
                    wc = self.repo[None]
                    if wc.modified() or wc.added() or wc.removed():
                        return False
                    for s in wc.substate:
                        if wc.sub(s).dirty():
                            return False
                except EnvironmentError:
                    return False
                return True
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
                        'Please select to continue:\n')
                data = {'discard': (_('&Discard'),
                                    _('Discard - discard local changes, no backup')),
                        'shelve': (_('&Shelve'),
                                  _('Shelve - move local changes to a patch')),
                        'merge': (_('&Merge'),
                                  _('Merge - allow to merge with local changes')),}

                opts = ['discard']
                if not ismergedchange():
                    opts.append('shelve')
                if islocalmerge(cur, node, clean):
                    opts.append('merge')

                dlg = QMessageBox(QMessageBox.Question, _('Confirm Update'),
                                  '', QMessageBox.Cancel, self)
                buttonnames = {}
                for name in opts:
                    label, desc = data[name]
                    msg += '\n'
                    msg += desc
                    btn = dlg.addButton(label, QMessageBox.ActionRole)
                    buttonnames[btn] = name
                dlg.setDefaultButton(QMessageBox.Cancel)
                dlg.setText(msg)
                dlg.exec_()
                clicked = buttonnames.get(dlg.clickedButton())
                return clicked

            # If merge-by-default, we want to merge whenever possible,
            # without prompting user (similar to command-line behavior)
            defaultmerge = self.merge_chk.isChecked()
            clean = isclean()
            if clean:
                cmdline.append('--check')
            elif not (defaultmerge and islocalmerge(cur, node, clean)):
                clicked = confirmupdate(clean)
                if clicked == 'discard':
                    cmdline.append('--clean')
                elif clicked == 'shelve':
                    from tortoisehg.hgqt import shelve
                    dlg = shelve.ShelveDialog(self.repo, self)
                    dlg.finished.connect(dlg.deleteLater)
                    dlg.exec_()
                    return
                elif clicked == 'merge':
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
        self.detail_btn.setShown(True)

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
        for root, path, status in thgrepo.recursiveMergeStatus(self.repo):
            if status == 'u':
                qtlib.InfoMsgBox(_('Merge caused file conflicts'),
                                 _('File conflicts need to be resolved'))
                dlg = resolve.ResolveDialog(self.repo, self)
                dlg.finished.connect(dlg.deleteLater)
                dlg.exec_()
                break
        super(UpdateDialog, self).accept()

    def command_canceling(self):
        self.cancel_btn.setDisabled(True)

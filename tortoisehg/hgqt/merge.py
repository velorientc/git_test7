# merge.py - Merge dialog for TortoiseHg
#
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import error
from mercurial import merge as mergemod

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, csinfo, i18n, cmdui, status, commit, resolve

keep = i18n.keepgettext()

MERGE_PAGE  = 0
COMMIT_PAGE = 1
RESULT_PAGE = 2

class MergeDialog(QWizard):

    def __init__(self, other, repo=None, parent=None):
        super(MergeDialog, self).__init__(parent)
        f = self.windowFlags()
        self.setWindowFlags(f & ~Qt.WindowContextHelpButtonHint)

        self.repo = repo
        self.other = str(other)
        self.local = str(self.repo['.'].rev())

        self.setWindowTitle(_('Merge - %s') % self.repo.displayname)
        self.setWindowIcon(qtlib.geticon('merge'))
        self.setMinimumSize(600, 512)
        self.setOption(QWizard.DisabledBackButtonOnLastPage, True)
        self.setOption(QWizard.HelpButtonOnRight, False)
        self.setDefaultProperty('QComboBox', 'currentText', 'editTextChanged()')

        # set pages
        self.setPage(MERGE_PAGE, MergePage(self))
        self.setPage(COMMIT_PAGE, CommitPage(self))
        self.setPage(RESULT_PAGE, ResultPage(self))

        repo.repositoryChanged.connect(self.repositoryChanged)
        repo.configChanged.connect(self.configChanged)

    def repositoryChanged(self):
        self.currentPage().repositoryChanged()

    def configChanged(self):
        self.currentPage().configChanged()

    def reject(self):
        page = self.currentPage()
        if hasattr(page, 'need_cleanup') and page.need_cleanup():
            main = _('Do you want to exit?')
            text = _('To complete merging, you need to commit merged files '
                     'in working directory.')
            labels = ((QMessageBox.Yes, _('&Exit')),
                      (QMessageBox.No, _('Cancel')))
            if not qtlib.QuestionMsgBox(_('Confirm Exit'), main, text,
                                        labels=labels, parent=self):
                return
        super(MergeDialog, self).reject()

MAIN_PANE    = 0
PERFORM_PANE = 1

class BasePage(QWizardPage):

    def __init__(self, parent=None):
        super(BasePage, self).__init__(parent)

        self.done = False

    def switch_pane(self, pane):
        self.setup_buttons(pane)
        self.layout().setCurrentIndex(pane)
        if pane == MAIN_PANE:
            self.ready()
        elif pane == PERFORM_PANE:
            self.cmd.core.clear_output()
            self.perform()
        else:
            raise 'unknown pane: %s' % pane

    ### Override Method ###

    def repositoryChanged(self):
        'repository has detected a change to changelog or parents'
        pass

    def configChanged(self):
        'repository has detected a change to config files'
        pass

    def initializePage(self):
        if self.layout():
            return

        stack = QStackedLayout()
        self.setLayout(stack)

        def wrap(layout):
            widget = QWidget()
            widget.setLayout(layout)
            return widget

        # main pane
        fpane = self.get_pane()
        num = stack.addWidget(wrap(fpane))
        assert num == MAIN_PANE

        # perform pane
        ppane = QVBoxLayout()
        ppane.addSpacing(4)
        self.cmd = cmdui.Widget()
        self.cmd.show_output(True)
        self.cmd.commandFinished.connect(self.command_finished)
        self.cmd.commandCanceling.connect(self.command_canceling)
        ppane.addWidget(self.cmd)
        num = stack.addWidget(wrap(ppane))
        assert num == PERFORM_PANE

    def setVisible(self, visible):
        super(BasePage, self).setVisible(visible)
        if visible:
            self.switch_pane(MAIN_PANE)

    def validatePage(self):
        return self.can_continue()

    ### Method to be overridden ###

    def get_pane(self):
        return QVBoxLayout()

    def get_perform_label(self):
        return None

    def setup_buttons(self, pane):
        if pane == MAIN_PANE:
            label = self.get_perform_label()
            if label:
                btn = QPushButton(label)
                self.wizard().setButton(QWizard.NextButton, btn)
                self.wizard().button(QWizard.NextButton).clicked.connect(
                              self.perform_clicked)
                self.wizard().button(QWizard.NextButton).setShown(True)
            self.wizard().setOption(QWizard.HaveHelpButton, False)
            self.wizard().setOption(QWizard.HaveCustomButton1, False)
        elif pane == PERFORM_PANE:
            button = QPushButton(_('Cancel'))
            self.wizard().setButton(QWizard.CustomButton1, button)
            self.wizard().setOption(QWizard.HaveCustomButton1, True)
            button.clicked.connect(self.cancel_clicked)
            self.wizard().button(QWizard.NextButton).setHidden(True)
            self.wizard().button(QWizard.CancelButton).setHidden(True)
        else:
            raise 'unknown pane: %s' % pane

    def ready(self):
        pass

    def perform(self):
        pass

    def cancel(self):
        self.cmd.cancel()

    def can_continue(self):
        return self.done

    def need_cleanup(self):
        return False

    ### Signal Handlers ###

    def perform_clicked(self):
        self.switch_pane(PERFORM_PANE)

    def cancel_clicked(self):
        self.cancel()

    def command_finished(self, ret):
        pass

    def command_canceling(self):
        pass

MARGINS = (8, 0, 0, 0)

class MergePage(BasePage):

    def __init__(self, parent=None):
        super(MergePage, self).__init__(parent)

        self.clean = None
        self.undo = False

    ### Override Methods ###

    def get_pane(self):
        repo = self.wizard().repo
        box = QVBoxLayout()

        contents = ('ishead',) + csinfo.PANEL_DEFAULT
        style = csinfo.panelstyle(contents=contents)
        def markup_func(widget, item, value):
            if item == 'ishead' and value is False:
                text = _('Not a head revision!')
                return qtlib.markup(text, fg='red', weight='bold')
            raise csinfo.UnknownItem(item)
        custom = csinfo.custom(markup=markup_func)
        create = csinfo.factory(repo, custom, style, withupdate=True)

        ## merge target
        other_sep = qtlib.LabeledSeparator(_('Merge from (other revision)'))
        box.addWidget(other_sep)
        try:
            other_info = create(self.wizard().other)
            other_info.setContentsMargins(5, 0, 0, 0)
            box.addWidget(other_info)
        except error.RepoLookupError:
            qtlib.InfoMsgBox(_('Unable to merge'),
                             _('Merge revision not specified or not found'))
            QTimer.singleShot(0, self.wizard().close)

        ### discard option
        discard_chk = QCheckBox(_('Discard all changes from merge target '
                                  '(other) revision'))
        self.registerField('discard', discard_chk)
        box.addWidget(discard_chk)

        ## auto-resolve
        autoresolve_chk = QCheckBox(_('Automatically resolve merge conflicts '
                                      'where possible'))
        autoresolve_chk.setChecked(
            repo.ui.configbool('tortoisehg', 'autoresolve', False))
        self.registerField('autoresolve', autoresolve_chk)
        box.addWidget(autoresolve_chk)

        ## current revision
        box.addSpacing(6)
        local_sep = qtlib.LabeledSeparator(_('Merge to (working directory)'))
        box.addWidget(local_sep)
        local_info = create(self.wizard().local)
        local_info.setContentsMargins(5, 0, 0, 0)
        box.addWidget(local_info)
        self.local_info = local_info

        ## working directory status
        box.addSpacing(6)
        wd_sep = qtlib.LabeledSeparator(_('Working directory status'))
        box.addWidget(wd_sep)

        self.groups = qtlib.WidgetGroups()

        wdbox = QHBoxLayout()
        wdbox.setContentsMargins(*MARGINS)
        box.addLayout(wdbox)
        self.wd_status = qtlib.StatusLabel()
        self.wd_status.set_status(_('Checking...'))
        wdbox.addWidget(self.wd_status)
        wd_prog = QProgressBar()
        wd_prog.setMaximum(0)
        wd_prog.setTextVisible(False)
        self.groups.add(wd_prog, 'prog')
        wdbox.addWidget(wd_prog, 1)
        wd_button = QPushButton(_('Stop'))
        self.groups.add(wd_button, 'prog')
        wdbox.addWidget(wd_button)
        wd_detail = QLabel(_('<a href="view">View changes...</a>'))
        wd_detail.linkActivated.connect(self.link_activated)
        self.groups.add(wd_detail, 'detail')
        wdbox.addWidget(wd_detail)
        wdbox.addSpacing(4)

        wd_merged = QLabel(_('The workding directory is already <b>merged</b>. '
                             '<a href="skip"><b>Continue</b></a> or '
                             '<a href="discard"><b>discard</b></a> existing '
                             'merge.'))
        wd_merged.setContentsMargins(*MARGINS)
        wd_merged.linkActivated.connect(self.link_activated)
        self.groups.add(wd_merged, 'merged')
        box.addWidget(wd_merged)

        text = _('Before merging, you must '
                 '<a href="commit"><b>commit</b></a>, ')
        if 'mq' in repo.extensions():
            text = text + _('<a href="mq"><b>save</b></a> to MQ patch, ')
        text = text + ('or <a href="discard"><b>discard</b></a> changes.')
        wd_text = QLabel(text)
        wd_text.setContentsMargins(*MARGINS)
        wd_text.linkActivated.connect(self.link_activated)
        self.wd_text = wd_text
        self.groups.add(wd_text, 'dirty')
        box.addWidget(wd_text)

        wdbox = QHBoxLayout()
        wdbox.setContentsMargins(*MARGINS)
        box.addLayout(wdbox)
        wd_alt = QLabel(_('Or use:'))
        self.groups.add(wd_alt, 'dirty')
        wdbox.addWidget(wd_alt)
        force_chk = QCheckBox(_('Force a merge with outstanding changes '
                                '(-f/--force)'))
        force_chk.toggled.connect(lambda c: self.completeChanged.emit())
        self.registerField('force', force_chk)
        self.groups.add(force_chk, 'dirty')
        wdbox.addWidget(force_chk)
        wdbox.addStretch(0)

        box.addStretch(0)

        return box

    def get_perform_label(self):
        return _('&Merge')

    def ready(self):
        self.done = False
        self.setTitle(_('Merge another revision to the working directory'))
        self.groups.set_visible(False, 'dirty')
        self.groups.set_visible(False, 'merged')
        self.groups.set_visible(False, 'detail')
        self.check_status()

        if self.undo:
            self.link_activated('discard:noconfirm')
            self.undo = False

    def perform(self):
        self.setTitle(_('Merging...'))
        self.setSubTitle(_('All conflicting files will be marked unresolved.'))

        if self.field('discard').toBool():
            # '.' is safer than self.localrev, in case the user has
            # pulled a fast one on us and updated from the CLI
            cmdline = ['debugsetparents', '.', self.wizard().other]
        else:
            tool = self.field('autoresolve') and 'merge' or 'fail'
            cmdline = ['--repository', self.wizard().repo.root, 'merge',
                       '--tool=internal:' + tool, 
                       self.wizard().other]
        self.cmd.run(cmdline)

    def cancel(self):
        main = _('Cancel merge and discard changes?')
        text = _('Discard unfinished local changes and restart merge?')
        labels = ((QMessageBox.Yes, _('&Discard')),
                  (QMessageBox.No, _('Cancel')))
        if qtlib.QuestionMsgBox(_('Confirm Clean Up'), main, text,
                                labels=labels, parent=self):
            o = self.cmd.output_text
            o.appendLog(_('Canceling merge...\n'), 'control')
            o.appendLog(_('(Please close any running merge tool)\n'), 'control')
            self.cmd.cancel()

    def isComplete(self):
        if self.clean:
            return True
        return self.wizard().field('force').toBool()

    ### Signal Handlers ###

    def command_finished(self, ret):
        repo = self.wizard().repo
        repo.dirstate.invalidate()
        if len(repo.parents()) == 2 and ret in (0, 1):
            repo.incrementBusyCount()
            repo.decrementBusyCount()
            self.done = True
            self.wizard().next()
        else:
            qtlib.InfoMsgBox(_('Merge failed'), _('Returning to first page'))
            self.link_activated('discard:noconfirm')
            self.switch_pane(MAIN_PANE)

    def repositoryChanged(self):
        'repository has detected a change to changelog or parents'
        pctx = self.wizard().repo['.']
        self.local_info.update(pctx)
        self.wizard().local = str(pctx.rev())

    def command_canceling(self):
        self.wizard().button(QWizard.CustomButton1).setDisabled(True)

    def link_activated(self, cmd):
        cmd = str(cmd)
        repo = self.wizard().repo
        if cmd == 'commit':
            dlg = commit.CommitDialog([], dict(root=repo.root), self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.exec_()
            self.check_status()
        elif cmd == 'mq':
            # TODO: need to check existing patches
            patch = 'patch1'
            def finished(ret):
                repo.decrementBusyCount()
                if ret == 0:
                    def callback():
                        text = _('Outstanding changes are saved to <b>'
                                 '%(name)s</b> in the patch queue.  <a href'
                                 '="rename:%(name)s"><b>Rename</b></a> it?')
                        self.wd_text.setText(text % dict(name=patch))
                        self.wd_text.setShown(True)
                    self.check_status(callback)
            self.runner = cmdui.Runner(_('MQ - TortoiseHg'), True, self)
            self.runner.commandFinished.connect(finished)
            repo.incrementBusyCount()
            self.runner.run(['qnew', '--repository', repo.root, patch],
                            ['qpop', '--repository', repo.root, '--all'])
        elif cmd.startswith('discard'):
            if cmd != 'discard:noconfirm':
                labels = [(QMessageBox.Yes, _('&Discard')),
                          (QMessageBox.No, _('Cancel'))]
                if not qtlib.QuestionMsgBox(_('Confirm Discard'), _('Discard'
                         ' outstanding changes in working directory?'),
                         labels=labels, parent=self):
                    return
            def finished(ret):
                repo.decrementBusyCount()
                if ret == 0:
                    self.check_status()
            cmdline = ['update', '--clean', '--repository', repo.root,
                       '--rev', '.']
            self.runner = cmdui.Runner(_('Discard - TortoiseHg'), True, self)
            self.runner.commandFinished.connect(finished)
            repo.incrementBusyCount()
            self.runner.run(cmdline)
        elif cmd.startswith('rename:'):
            patch = cmd[7:]
            name, ok = QInputDialog.getText(self, _('Rename Patch'),
                                    _('Input a new patch name:'), text=patch)
            if not ok or name == patch:
                return
            oldpatch = hglib.fromunicode(patch)
            newpatch = hglib.fromunicode(name)
            def finished(ret):
                repo.decrementBusyCount()
                if ret == 0:
                    text = _('The patch <b>%(old)s</b> is renamed to <b>'
                             '%(new)s</b>.  <a href="rename:%(new)s"><b>'
                             'Rename</b></a> again?')
                    self.wd_text.setText(text % dict(old=patch, new=name))
            self.runner = cmdui.Runner(_('Rename - TortoiseHg'), True, self)
            self.runner.commandFinished.connect(finished)
            repo.incrementBusyCount()
            self.runner.run(['qrename', '--repository', repo.root,
                              oldpatch, newpatch])
        elif cmd == 'view':
            dlg = status.StatusDialog([], {}, repo.root, self)
            dlg.exec_()
            self.check_status()
        elif cmd == 'skip':
            self.done = True
            self.wizard().next()
        else:
            raise 'unknown command: %s' % str(cmd)

    ### Private Methods ###

    def check_status(self, callback=None):
        repo = self.wizard().repo
        class CheckThread(QThread):
            def __init__(self, parent):
                QThread.__init__(self, parent)
                self.results = (False, 1)

            def run(self):
                ms = mergemod.mergestate(repo)
                unresolved = False
                for path in ms:
                    if ms[path] == 'u':
                        unresolved = True
                wctx = repo[None]
                dirty = bool(wctx.dirty()) or unresolved
                self.results = (dirty, len(wctx.parents()))

        def completed():
            self.th.wait()
            dirty, parents = self.th.results
            self.clean = not dirty
            self.groups.set_visible(False, 'prog')
            self.groups.set_visible(dirty, 'detail')
            if dirty:
                self.groups.set_visible(parents == 2, 'merged')
                self.groups.set_visible(parents == 1, 'dirty')
                self.wd_status.set_status(_('<b>Uncommitted local changes '
                                            'are detected</b>'), 'warning')
            else:
                self.groups.set_visible(False, 'dirty')
                self.groups.set_visible(False, 'merged')
                self.wd_status.set_status(_('Clean'), True)
            self.completeChanged.emit()
            if callable(callback):
                callback()
        self.th = CheckThread(self)
        self.th.finished.connect(completed)
        self.th.start()


class CommitPage(BasePage):

    def __init__(self, parent=None):
        super(CommitPage, self).__init__(parent)
        self.done = False

    ### Override Methods ###

    def get_pane(self):
        repo = self.wizard().repo
        box = QVBoxLayout()

        self.reslabel = QLabel()
        self.reslabel.linkActivated.connect(self.link_activated)
        box.addWidget(self.reslabel)

        # csinfo
        def label_func(widget, item):
            if item == 'rev':
                return _('Revision:')
            elif item == 'parents':
                return _('Parents')
            raise csinfo.UnknownItem()
        def data_func(widget, item, ctx):
            if item == 'rev':
                return _('Working Directory'), str(ctx)
            elif item == 'parents':
                parents = []
                cbranch = ctx.branch()
                for pctx in ctx.parents():
                    branch = None
                    if hasattr(pctx, 'branch') and pctx.branch() != cbranch:
                        branch = pctx.branch()
                    parents.append((str(pctx.rev()), str(pctx), branch, pctx))
                return parents
            raise csinfo.UnknownItem()
        def markup_func(widget, item, value):
            if item == 'rev':
                text, rev = value
                return '<a href="view">%s</a> (%s)' % (text, rev)
            elif item == 'parents':
                def branch_markup(branch):
                    opts = dict(fg='black', bg='#aaffaa')
                    return qtlib.markup(' %s ' % branch, **opts)
                csets = []
                for rnum, rid, branch, pctx in value:
                    line = '%s (%s)' % (rnum, rid)
                    if branch:
                        line = '%s %s' % (line, branch_markup(branch))
                    msg = widget.info.get_data('summary', widget,
                                               pctx, widget.custom)
                    if msg:
                        line = '%s %s' % (line, msg)
                    csets.append(line)
                return csets
            raise csinfo.UnknownItem()
        custom = csinfo.custom(label=label_func, data=data_func,
                               markup=markup_func)
        contents = ('rev', 'user', 'dateage', 'branch', 'parents')
        style = csinfo.panelstyle(contents=contents, margin=6)

        # merged files
        box.addSpacing(12)
        rev_sep = qtlib.LabeledSeparator(_('Working Directory (merged)'))
        box.addWidget(rev_sep)
        rev_info = csinfo.create(repo, None, style, custom=custom,
                                 withupdate=True)
        page = self.wizard().page(MERGE_PAGE)
        rev_info.linkActivated.connect(page.link_activated)
        box.addWidget(rev_info)

        # commit message area
        msg_sep = qtlib.LabeledSeparator(_('Commit message'))
        box.addWidget(msg_sep)
        msg_text = QTextEdit()
        engmsg = repo.ui.configbool('tortoisehg', 'engmsg', False)
        msgset = keep._('Merge ')
        msg_text.setText(engmsg and msgset['id'] or msgset['str'])
        msg_text.textChanged.connect(lambda: self.completeChanged.emit())
        self.msg_text = msg_text
        box.addWidget(msg_text)

        def tryperform():
            if self.isComplete():
                self.perform()
        actionEnter = QAction('alt-enter', self)
        actionEnter.setShortcuts([Qt.CTRL+Qt.Key_Return, Qt.CTRL+Qt.Key_Enter])
        actionEnter.triggered.connect(tryperform)
        self.addAction(actionEnter)
        return box

    def link_activated(self, cmd):
        if cmd == 'resolve':
            dlg = resolve.ResolveDialog(self.wizard().repo, self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.exec_()
            self.completeChanged.emit()

    def get_perform_label(self):
        return _('&Commit')

    def setup_buttons(self, pane):
        super(CommitPage, self).setup_buttons(pane)

        if pane == MAIN_PANE:
            undo = QPushButton(_('Undo'))
            undo.clicked.connect(self.wizard().back)
            self.wizard().setButton(QWizard.HelpButton, undo)
            self.wizard().setOption(QWizard.HaveHelpButton, True)
        elif pane == PERFORM_PANE:
            self.wizard().setOption(QWizard.HaveHelpButton, False)
        else:
            raise 'unknown pane: %s' % pane

    def ready(self):
        self.setTitle(_('Commit merged files'))

        # move cursor to end of commit message
        self.msg_text.setFocus()
        cursor = self.msg_text.textCursor()
        cursor.movePosition(QTextCursor.EndOfBlock)
        self.msg_text.setTextCursor(cursor)

    def perform(self):
        self.setTitle(_('Committing...'))
        self.setSubTitle(_('Please wait while committing merged files.'))

        # merges must be committed without specifying file list
        message = hglib.fromunicode(self.msg_text.toPlainText())
        cmdline = ['commit', '--verbose', '--message', message,
                   '--repository', self.wizard().repo.root]
        self.wizard().repo.incrementBusyCount()
        self.cmd.run(cmdline)

    def isComplete(self):
        ms = mergemod.mergestate(self.wizard().repo)
        for path in ms:
            if ms[path] == 'u':
                self.reslabel.setText(_('There were <b>merge conflicts</b> '
                                        'that must be <a href="resolve">'
                                        '<b>resolved</b></a>'))
                return False
        else:
            self.reslabel.setText(_('No merge conflicts, ready to commit'))
        return len(self.msg_text.toPlainText()) > 0

    def need_cleanup(self):
        return len(self.wizard().repo.parents()) == 2

    def repositoryChanged(self):
        'repository has detected a change to changelog or parents'
        if self.done:
            return
        if len(self.wizard().repo.parents()) == 1:
            self.wizard().restart()

    ### Private Method ###

    def undo(self):
        page = self.wizard().page(MERGE_PAGE)
        page.undo = True

    ### Signal Handlers ###

    def command_finished(self, ret):
        if ret == 0:
            self.done = True
            self.wizard().repo.decrementBusyCount()
            self.wizard().next()
        else:
            self.wizard().repo.decrementBusyCount()

    def command_canceling(self):
        page = self.wizard().page(MERGE_PAGE)
        page.undo = True

class ResultPage(QWizardPage):

    def __init__(self, parent=None):
        super(ResultPage, self).__init__(parent)

        self.setTitle(_('Finished'))

    ### Override Method ###

    def repositoryChanged(self):
        'repository has detected a change to changelog or parents'
        pass

    def initializePage(self):
        box = QVBoxLayout()
        self.setLayout(box)

        # merge changeset
        merge_sep = qtlib.LabeledSeparator(_('Merge changeset'))
        box.addWidget(merge_sep)
        merge_info = csinfo.create(self.wizard().repo, 'tip', withupdate=True)
        box.addWidget(merge_info)
        box.addStretch(0)

        self.wizard().setOption(QWizard.HaveHelpButton, False)
        self.wizard().setOption(QWizard.NoCancelButton, True)
        self.wizard().setOption(QWizard.HaveCustomButton1, False)

def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    from tortoisehg.hgqt import thgrepo
    rev = opts.get('rev') or None
    if not rev and len(pats):
        rev = pats[0]
    repo = thgrepo.repository(ui, path=paths.find_root())
    return MergeDialog(rev, repo)

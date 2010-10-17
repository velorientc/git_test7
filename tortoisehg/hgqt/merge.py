# merge.py - Merge dialog for TortoiseHg
#
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

import os

from mercurial import hg, ui, error
from mercurial import merge as mergemod

from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, csinfo, i18n, cmdui, status, thgrepo
from tortoisehg.hgqt import commit, wctxactions, visdiff

keep = i18n.keepgettext()

# TODO:
#  Connect merge page to repositoryChanged signal, refresh if current page

MERGE_PAGE  = 0
RESOLVE_PAGE = 1
COMMIT_PAGE = 2
RESULT_PAGE = 3

class MergeDialog(QWizard):

    def __init__(self, other, repo=None, parent=None):
        super(MergeDialog, self).__init__(parent)
        f = self.windowFlags()
        self.setWindowFlags(f & ~Qt.WindowContextHelpButtonHint)

        self.repo = repo
        self.other = str(other)
        self.local = str(self.repo.parents()[0].rev())

        self.setWindowTitle(_('Merge - %s') % self.repo.displayname)
        self.setWindowIcon(qtlib.geticon('merge'))
        self.setMinimumSize(600, 512)
        self.setOption(QWizard.DisabledBackButtonOnLastPage, True)
        self.setOption(QWizard.HelpButtonOnRight, False)
        self.setDefaultProperty('QComboBox', 'currentText', 'editTextChanged()')

        # set pages
        self.setPage(MERGE_PAGE, MergePage(self))
        self.setPage(RESOLVE_PAGE, ResolvePage(self))
        self.setPage(COMMIT_PAGE, CommitPage(self))
        self.setPage(RESULT_PAGE, ResultPage(self))

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

        ## current revision
        box.addSpacing(6)
        local_sep = qtlib.LabeledSeparator(_('Merge to (working directory)'))
        box.addWidget(local_sep)
        local_info = create(self.wizard().local)
        local_info.setContentsMargins(5, 0, 0, 0)
        box.addWidget(local_info)
        def refreshlocal():
            repo = self.wizard().repo
            if len(repo.parents()) == 1:
                local_info.update(repo['.'])
        self.completeChanged.connect(refreshlocal)

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

        wd_merged = QLabel(_('The workding directory looks already'
                             ' <b>merged</b>. <a href="skip"><b>Commit</b></a>'
                             ' or <a href="discard"><b>discard</b></a> merge.'))
        wd_merged.setContentsMargins(*MARGINS)
        wd_merged.linkActivated.connect(self.link_activated)
        self.groups.add(wd_merged, 'merged')
        box.addWidget(wd_merged)

        text = _('To start merging, you need to '
                 '<a href="commit"><b>commit</b></a> them')
        if 'mq' in repo.extensions():
            text = text + _(', <a href="mq"><b>save</b></a> as MQ patch')
        text = text + (' or <a href="discard"><b>discard</b></a> all.')
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
            cmdline = ['--repository', self.wizard().repo.root,
                       '--config', 'ui.merge=internal:fail', 'merge']
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

    def command_canceling(self):
        self.wizard().button(QWizard.CustomButton1).setDisabled(True)

    def link_activated(self, cmd):
        cmd = str(cmd)
        repo = self.wizard().repo
        if cmd == 'commit':
            dlg = commit.CommitDialog([], dict(root=repo.root), self)
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
            self.runner.run(['qnew', patch], ['qpop', '--all'])
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
            cmdline = ['update', '--clean', '--rev', self.wizard().local]
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
            self.runner.run(['qrename', oldpatch, newpatch])
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
            completed = pyqtSignal(bool, int)
            def run(self):
                ms = mergemod.mergestate(repo)
                unresolved = False
                for path in ms:
                    if ms[path] == 'u':
                        unresolved = True
                wctx = repo[None]
                dirty = bool(wctx.dirty()) or unresolved
                self.completed.emit(dirty, len(wctx.parents()))
        def completed(dirty, parents):
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
        self.th = CheckThread()
        self.th.completed.connect(completed)
        self.th.start()


class ResolvePage(QWizardPage):

    def __init__(self, parent=None):
        super(ResolvePage, self).__init__(parent)
        self.setTitle(_('Resolve conflicts'))

    ### Override Method ###

    def initializePage(self):
        if self.layout():
            self.refresh()
            self.utree.selectAll()
            self.utree.setFocus()
            return

        # created first for isComplete()
        self.utree = PathsTree(self)

        box = QVBoxLayout()
        box.setContentsMargins(*MARGINS)
        box.setSpacing(5)
        self.setLayout(box)

        unres = qtlib.LabeledSeparator(_('Unresolved conflicts'))
        self.layout().addWidget(unres)

        hbox = QHBoxLayout()
        hbox.setSpacing(0)
        hbox.setContentsMargins(*MARGINS)
        self.layout().addLayout(hbox)

        hbox.addWidget(self.utree)

        vbox = QVBoxLayout()
        vbox.setContentsMargins(*MARGINS)
        hbox.addLayout(vbox)
        auto = QPushButton(_('Auto'))
        auto.setToolTip(_('Attempt automatic merge'))
        auto.clicked.connect(lambda: self.merge('internal:merge'))
        manual = QPushButton(_('Manual'))
        manual.setToolTip(_('Merge with selected merge tool'))
        manual.clicked.connect(self.merge)
        local = QPushButton(_('Take Local'))
        local.setToolTip(_('Accept the local file version (yours)'))
        local.clicked.connect(lambda: self.merge('internal:local'))
        other = QPushButton(_('Take Other'))
        other.setToolTip(_('Accept the other file version (theirs)'))
        other.clicked.connect(lambda: self.merge('internal:other'))
        res = QPushButton(_('Mark'))
        res.setToolTip(_('Mark this file as resolved'))
        res.clicked.connect(self.markresolved)
        vbox.addWidget(auto)
        vbox.addWidget(manual)
        vbox.addWidget(local)
        vbox.addWidget(other)
        vbox.addWidget(res)
        vbox.addStretch(1)
        self.ubuttons = (auto, manual, local, other, res)

        res = qtlib.LabeledSeparator(_('Resolved conflicts'))
        self.layout().addWidget(res)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(*MARGINS)
        hbox.setSpacing(0)
        self.layout().addLayout(hbox)

        self.rtree = PathsTree(self)
        hbox.addWidget(self.rtree)

        vbox = QVBoxLayout()
        vbox.setContentsMargins(*MARGINS)
        hbox.addLayout(vbox)
        edit = QPushButton(_('Edit'))
        edit.setToolTip(_('Edit resolved file'))
        edit.clicked.connect(self.edit)
        v3way = QPushButton(_('3-Way Diff'))
        v3way.setToolTip(_('Visual three-way diff'))
        v3way.clicked.connect(self.v3way)
        vp0 = QPushButton(_('To Local'))
        vp0.setToolTip(_('Visual diff between resolved file and first parent'))
        vp0.clicked.connect(self.vp0)
        vp1 = QPushButton(_('To Other'))
        vp1.setToolTip(_('Visual diff between resolved file and second parent'))
        vp1.clicked.connect(self.vp1)
        ures = QPushButton(_('Unmark'))
        ures.setToolTip(_('Mark this file as unresolved'))
        ures.clicked.connect(self.markunresolved)
        vbox.addWidget(edit)
        vbox.addWidget(v3way)
        vbox.addWidget(vp0)
        vbox.addWidget(vp1)
        vbox.addWidget(ures)
        vbox.addStretch(1)
        self.rbuttons = (edit, v3way, vp0, vp1, ures)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(*MARGINS)
        hbox.setSpacing(0)
        self.layout().addLayout(hbox)

        self.tcombo = ToolsCombo(self.wizard().repo)
        hbox.addWidget(QLabel(_('Detected merge/diff tools:')))
        hbox.addWidget(self.tcombo)
        hbox.addStretch(1)

        out = qtlib.LabeledSeparator(_('Command output'))
        self.layout().addWidget(out)
        self.cmd = cmdui.Widget(True, self)
        self.cmd.commandFinished.connect(self.refresh)
        self.cmd.show_output(True)
        self.layout().addWidget(self.cmd)

        self.wizard().setOption(QWizard.HaveHelpButton, False)
        self.wizard().setOption(QWizard.NoCancelButton, True)
        self.wizard().setOption(QWizard.HaveCustomButton1, False)

        self.refresh()
        self.utree.selectAll()
        self.utree.setFocus()

    def getSelectedPaths(self, tree):
        paths = []
        for idx in tree.selectionModel().selectedRows():
            path = hglib.fromunicode(idx.data().toString())
            paths.append(path)
        return paths

    def merge(self, tool=False):
        if not tool:
            tool = self.tcombo.readValue()
        if not tool:
            cmd = ['resolve']
        else:
            cmd = ['resolve', '--config', 'ui.merge='+tool]
        cmdlines = []
        for path in self.getSelectedPaths(self.utree):
            cmdlines.append(cmd + [path])
        if cmdlines:
            self.cmd.run(*cmdlines)

    def markresolved(self):
        paths = self.getSelectedPaths(self.utree)
        if paths:
            self.cmd.run(['resolve', '--mark'] + paths)

    def markunresolved(self):
        paths = self.getSelectedPaths(self.rtree)
        if paths:
            self.cmd.run(['resolve', '--unmark'] + paths)

    def edit(self):
        paths = self.getSelectedPaths(self.rtree)
        if paths:
            repo = self.wizard().repo
            wctxactions.edit(self, repo.ui, repo, paths)

    def v3way(self):
        paths = self.getSelectedPaths(self.rtree)
        if paths:
            repo = self.wizard().repo
            visdiff.visualdiff(repo.ui, repo, paths, {'rev':[]})

    def vp0(self):
        paths = self.getSelectedPaths(self.rtree)
        if paths:
            repo = self.wizard().repo
            pair = [str(repo.parents()[0].rev()), '.']
            visdiff.visualdiff(repo.ui, repo, paths, {'rev':pair})

    def vp1(self):
        paths = self.getSelectedPaths(self.rtree)
        if paths:
            repo = self.wizard().repo
            pair = [str(repo.parents()[1].rev()), '.']
            visdiff.visualdiff(repo.ui, repo, paths, {'rev':pair})

    def refresh(self):
        repo = self.wizard().repo
        ms = mergemod.mergestate(repo)
        u, r = [], []
        for path in ms:
            if ms[path] == 'u':
                u.append(path)
            else:
                r.append(path)
        self.utree.setModel(PathsModel(u, self))
        self.utree.resizeColumnToContents(0)
        def uchanged(l):
            for b in self.ubuttons:
                b.setEnabled(not l.isEmpty())
        self.utree.selectionModel().selectionChanged.connect(uchanged)
        uchanged(QItemSelection())
        self.rtree.setModel(PathsModel(r, self))
        self.rtree.resizeColumnToContents(0)
        def rchanged(l):
            for b in self.rbuttons:
                b.setEnabled(not l.isEmpty())
        self.rtree.selectionModel().selectionChanged.connect(rchanged)
        rchanged(QItemSelection())
        self.completeChanged.emit()

    def isComplete(self):
        model = self.utree.model()
        if model is None:
            return False
        return len(model) == 0

    def need_cleanup(self):
        return True

class PathsTree(QTreeView):
    def __init__(self, repo, parent=None):
        QTreeView.__init__(self, parent)
        self.repo = repo
        self.setSelectionMode(QTreeView.ExtendedSelection)

    def dragObject(self):
        urls = []
        for index in self.selectionModel().selectedRows():
            path = self.model().getRow(index)[COL_PATH]
            u = QUrl()
            u.setPath('file://' + os.path.join(self.repo.root, path))
            urls.append(u)
        if urls:
            d = QDrag(self)
            m = QMimeData()
            m.setUrls(urls)
            d.setMimeData(m)
            d.start(Qt.CopyAction)

    def mousePressEvent(self, event):
        self.pressPos = event.pos()
        self.pressTime = QTime.currentTime()
        return QTreeView.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        d = event.pos() - self.pressPos
        if d.manhattanLength() < QApplication.startDragDistance():
            return QTreeView.mouseMoveEvent(self, event)
        elapsed = self.pressTime.msecsTo(QTime.currentTime())
        if elapsed < QApplication.startDragTime():
            return QTreeView.mouseMoveEvent(self, event)
        self.dragObject()
        return QTreeView.mouseMoveEvent(self, event)

class PathsModel(QAbstractTableModel):
    def __init__(self, pathlist, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.headers = (_('Path'), _('Ext'))
        self.rows = []
        for path in pathlist:
            name, ext = os.path.splitext(path)
            self.rows.append([path, ext])

    def __len__(self):
        return len(self.rows)

    def rowCount(self, parent):
        if parent.isValid():
            return 0 # no child
        return len(self.rows)

    def columnCount(self, parent):
        if parent.isValid():
            return 0 # no child
        return len(self.headers)

    def data(self, index, role):
        if not index.isValid():
            return QVariant()
        if role == Qt.DisplayRole:
            data = self.rows[index.row()][index.column()]
            return QVariant(hglib.tounicode(data))
        return QVariant()

    def headerData(self, col, orientation, role):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return QVariant()
        else:
            return QVariant(self.headers[col])

class ToolsCombo(QComboBox):
    def __init__(self, repo, parent=None):
        QComboBox.__init__(self, parent)
        self.setEditable(False)
        self.loaded = False
        self.setEditText(_('<default>'))
        self.repo = repo

    def showPopup(self):
        if not self.loaded:
            self.loaded = True
            self.clear()
            for t in self.repo.mergetools:
                self.addItem(hglib.tounicode(t))
        QComboBox.showPopup(self)

    def readValue(self):
        if self.loaded:
            return hglib.fromunicode(self.currentText())
        else:
            return None

class CommitPage(BasePage):

    def __init__(self, parent=None):
        super(CommitPage, self).__init__(parent)

    ### Override Methods ###

    def get_pane(self):
        repo = self.wizard().repo
        box = QVBoxLayout()

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

        return box

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
        self.cmd.run(cmdline)

    def isComplete(self):
        return len(self.msg_text.toPlainText()) > 0

    def need_cleanup(self):
        return len(self.wizard().repo.parents()) == 2

    def cleanupPage(self):
        self.undo()

    ### Private Method ###

    def undo(self):
        page = self.wizard().page(MERGE_PAGE)
        page.undo = True

    ### Signal Handlers ###

    def command_finished(self, ret):
        if ret == 0:
            self.wizard().repo.incrementBusyCount()
            self.wizard().repo.decrementBusyCount()
            self.done = True
            self.wizard().next()

    def command_canceling(self):
        page = self.wizard().page(MERGE_PAGE)
        page.undo = True

class ResultPage(QWizardPage):

    def __init__(self, parent=None):
        super(ResultPage, self).__init__(parent)

        self.setTitle(_('Finished'))

    ### Override Method ###

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

    def isFinalPage(self):
        return True

def run(ui, *pats, **opts):
    rev = opts.get('rev') or None
    if not rev and len(pats):
        rev = pats[0]
    repo = thgrepo.repository(ui, path=paths.find_root())
    return MergeDialog(rev, repo)

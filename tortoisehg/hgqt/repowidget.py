# -*- coding: iso-8859-1 -*-
#!/usr/bin/env python
# repowidget.py - TortoiseHg repository widget
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
# Copyright (C) 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

import binascii
import os

from tortoisehg.util import thgrepo, shlib, hglib, purge

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.qtlib import geticon, getfont, QuestionMsgBox, InfoMsgBox
from tortoisehg.hgqt.qtlib import CustomPrompt
from tortoisehg.hgqt.repomodel import HgRepoListModel
from tortoisehg.hgqt import cmdui, update, tag, backout, merge
from tortoisehg.hgqt import archive, thgimport, thgstrip, run

from tortoisehg.hgqt.repoview import HgRepoView
from tortoisehg.hgqt.revdetailswidget import RevDetailsWidget
from tortoisehg.hgqt.commit import CommitWidget
from tortoisehg.hgqt.sync import SyncWidget
from tortoisehg.hgqt.grep import SearchWidget

from PyQt4.QtCore import *
from PyQt4.QtGui import *

connect = QObject.connect

# TODO
# Unify use of cmdui.Runner, do not allow new runners while current is busy


class RepoWidget(QWidget):

    showMessageSignal = pyqtSignal(str)
    switchToSignal = pyqtSignal(QWidget)

    def __init__(self, repo, workbench):
        self.repo = repo
        self.workbench = workbench
        self._reload_rev = '.' # select working parent at startup
        self._scanForRepoChanges = True
        self.disab_shortcuts = []
        self.currentMessage = ''

        QWidget.__init__(self)

        self.load_config()
        self.setupUi()
        self.createActions()

        connect(self.repoview, SIGNAL('showMessage'), self.showMessage)

        self.setupModels()
        self.setupRevisionTable()

        self._repodate = self._getrepomtime()
        self._watchrepotimer = self.startTimer(500)

        self.restoreSettings()

    def setupUi(self):
        SP = QSizePolicy

        self.repotabs_splitter = QSplitter(orientation=Qt.Vertical)
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self.repotabs_splitter)

        self.repoview = HgRepoView(self.workbench)
        self.repotabs_splitter.addWidget(self.repoview)
        self.repotabs_splitter.setCollapsible(0, False)
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(1)
        sp.setHeightForWidth(self.repoview.sizePolicy().hasHeightForWidth())
        self.repoview.setSizePolicy(sp)
        self.repoview.setFrameShape(QFrame.StyledPanel)

        self._inittasktabs()

        w = RevDetailsWidget(self.repo, self.repoview)
        self.revDetailsStackedWidget.addWidget(w)
        w.revisionLinkClicked.connect(self.goto)
        self.revDetailsWidget = w

        w = BlankMessageWidget(self.repoview)
        self.revDetailsStackedWidget.addWidget(w)
        self.blankMessageWidget = w

    def _inittasktabs(self):
        self.taskTabsWidget = tt = QTabWidget()
        tt.setDocumentMode(True)
        tt.setTabPosition(QTabWidget.East)
        self.repotabs_splitter.addWidget(self.taskTabsWidget)

        self.revDetailsStackedWidget = sw = QStackedWidget()
        self.dummywidget = QWidget()
        self.revDetailsStackedWidget.addWidget(self.dummywidget)
        self.revDetailsStackedWidget.setCurrentWidget(self.dummywidget)
        sw.minimumSizeHint = lambda: QSize(0, 0)
        self.logTabIndex = idx = tt.addTab(sw, geticon('log'), '')
        tt.setTabToolTip(idx, _("Revision details"))

        self.commitStackedWidget = sw = QStackedWidget()
        sw.minimumSizeHint = lambda: QSize(0, 0)
        self.commitTabIndex = idx = tt.addTab(sw, geticon('commit'), '')
        tt.setTabToolTip(idx, _("Commit"))
        self.commitStackedWidget.addWidget(self.createCommitWidget())
        # TODO: unstack commit widget

        self.syncStackedWidget = sw = QStackedWidget()
        sw.minimumSizeHint = lambda: QSize(0, 0)
        self.syncTabIndex = idx = tt.addTab(sw, geticon('sync'), '')
        tt.setTabToolTip(idx, _("Synchronize"))
        self.syncStackedWidget.addWidget(self.createSyncWidget())
        # TODO: unstack sync widget

        self.grepStackedWidget = gw = QStackedWidget()
        gw.minimumSizeHint = lambda: QSize(0, 0)
        self.grepTabIndex = idx = tt.addTab(gw, geticon('grep'), '') # TODO
        tt.setTabToolTip(idx, _("Search"))
        self.grepStackedWidget.addWidget(self.createGrepWidget())
        # TODO: unstack grep widget

    def createCommitWidget(self):
        pats = {}
        opts = {}
        # TODO: pass repo directly instead of repo.root ?
        cw = CommitWidget(pats, opts, root=self.repo.root)
        cw.errorMessage.connect(self.workbench.showMessage)
        def commitcomplete():
            self.reload()
            cw.stwidget.refreshWctx()
        cw.commitComplete.connect(commitcomplete)
        b = QPushButton(_('Commit'))
        cw.buttonHBox.addWidget(b)
        b.clicked.connect(cw.commit)
        s = QSettings()
        cw.loadConfigs(s)
        return cw

    def createSyncWidget(self):
        # TODO: pass repo directly instead of repo.root ?
        # TODO: don't pass workbench
        sw = SyncWidget(root=self.repo.root, parent=self.workbench)
        return sw

    def createGrepWidget(self):
        # TODO: pass repo directly instead of repo.root ?
        upats = {}
        gw = SearchWidget(upats, self.repo.root, self)
        return gw

    def load_config(self):
        self._font = getfont(self.repo.ui, 'fontlog')
        self.rowheight = 8
        self.users, self.aliases = [], []
        self.hidefinddelay = False

    def reponame(self):
        return os.path.basename(self.repo.root)

    def showMessage(self, msg):
        self.currentMessage = msg
        if self.isVisible():
            self.showMessageSignal.emit(msg)

    def showEvent(self, event):
        QWidget.showEvent(self, event)
        self.showMessageSignal.emit(self.currentMessage)

    def timerEvent(self, event):
        if event.timerId() == self._watchrepotimer:
            if not self._scanForRepoChanges:
                return
            mtime = self._getrepomtime()
            if mtime > self._repodate:
                self.showMessage(_("Repository has been modified "
                                   "(reloading is recommended)"))

    def createActions(self):
        self.actionActivateRev = QAction('Activate rev.', self)
        self.actionActivateRev.setShortcuts([Qt.SHIFT+Qt.Key_Return, Qt.SHIFT+Qt.Key_Enter])
        connect(self.actionActivateRev, SIGNAL('triggered()'),
                self.revision_activated)
        self.addAction(self.actionActivateRev)
        self.disab_shortcuts.append(self.actionActivateRev)

    def back(self):
        self.repoview.back()

    def forward(self):
        self.repoview.forward()

    def thgimport(self):
        dlg = thgimport.ImportDialog(repo=self.repo, parent=self)
        dlg.exec_()

    def verify(self):
        cmdline = ['--repository', self.repo.root, 'verify']
        dlg = cmdui.Dialog(cmdline, self)
        dlg.exec_()

    def recover(self):
        cmdline = ['--repository', self.repo.root, 'recover']
        dlg = cmdui.Dialog(cmdline, self)
        dlg.exec_()

    def rollback(self):
        def read_undo():
            if os.path.exists(self.repo.sjoin('undo')):
                try:
                    args = self.repo.opener('undo.desc', 'r').read().splitlines()
                    if args[1] != 'commit':
                        return None
                    return args[1], int(args[0])
                except (IOError, IndexError, ValueError):
                    pass
            return None
        data = read_undo()
        if data is None:
            InfoMsgBox(_('No transaction available'),
                       _('There is no rollback transaction available'))
            return
        elif data[0] == 'commit':
            if not QuestionMsgBox(_('Undo last commit?'),
                   _('Undo most recent commit (%d), preserving file changes?') %
                   data[1]):
                return
        else:
            if not QuestionMsgBox(_('Undo last transaction?'),
                    _('Rollback to revision %d (undo %s)?') %
                    (data[1]-1, data[0])):
                return
            try:
                rev = self.repo['.'].rev()
            except Exception, e:
                InfoMsgBox(_('Repository Error'),
                           _('Unable to determine working copy revision\n') +
                           hglib.tounicode(e))
                return
            if rev >= data[1] and not QuestionMsgBox(
                    _('Remove current working revision?'),
                    _('Your current working revision (%d) will be removed '
                      'by this rollback, leaving uncommitted changes.\n '
                      'Continue?' % rev)):
                    return
        saved = self.repo.ui.quiet
        self.repo.ui.quiet = True
        self.repo.rollback()
        self.repo.ui.quiet = saved
        self.reload()
        QTimer.singleShot(500, lambda: shlib.shell_notify([self.repo.root]))

    def purge(self):
        try:
            wctx = self.repo[None]
            wctx.status(ignored=True, unknown=True)
        except Exception, e:
            InfoMsgBox(_('Repository Error'),
                       _('Unable to query unrevisioned files\n') +
                       hglib.tounicode(e))
            return
        U, I = wctx.unknown(), wctx.ignored()
        if not U and not I:
            InfoMsgBox(_('No unrevisioned files'),
                       _('There are no purgable unrevisioned files'))
            return
        elif not U:
            if not QuestionMsgBox(_('Purge ignored files'),
                    _('Purge (delete) all %d ignored files?') % len(I)):
                return
            dels = I
        else:
            res = CustomPrompt(_('Purge unrevisioned files'),
                _('%d unknown files\n'
                  '%d files ignored by .hgignore filter\n'
                  'Purge unknown, ignored, or both?') % (len(U), len(I)), self,
                (_('&Unknown'), _('&Ignored'), _('&Both'), _('&Cancel')),
                    0, 3, U+I).run()
            if res == 3:
                return
            elif res == 2:
                dels = U+I
            elif res == 1:
                dels = I
            else:
                dels = U
        res = CustomPrompt(_('Confirm file deletions'),
                _('Are you sure you want to delete these %d files?') %
                len(dels), self, (_('&Yes'), _('&No')), 1, 1, dels).run()
        if res == 1:
            return

        failures = purge.purge(self.repo, dels)
        if failures:
            CustomPrompt(_('Deletion failures'),
                _('Unable to delete %d files or folders') %
                len(failures), self, (_('&Ok'),), 0, 0, failures).run()

    def setMode(self, mode):
        self.revDetailsWidget.setMode(mode)
        self.updateActions()

    def setAnnotate(self, ann):
        self.revDetailsWidget.setAnnotate(ann)

    def nextDiff(self):
        self.revDetailsWidget.nextDiff()

    def prevDiff(self):
        self.revDetailsWidget.prevDiff()

    def create_models(self):
        self.repomodel = HgRepoListModel(self.repo)
        connect(self.repomodel, SIGNAL('filled'), self.on_filled)
        connect(self.repomodel, SIGNAL('loaded'), self.loaded)
        connect(self.repomodel, SIGNAL('showMessage'),
                self.showMessage, Qt.QueuedConnection)

    def setupModels(self):
        self.create_models()
        self.repoview.setModel(self.repomodel)
        self.revDetailsWidget.setupModels(self.repomodel)

    def setupRevisionTable(self):
        view = self.repoview
        view.installEventFilter(self)
        connect(view, SIGNAL('revisionSelected'), self.revision_selected)
        connect(view, SIGNAL('revisionActivated'), self.revision_activated)
        connect(view, SIGNAL('updateToRevision'), self.updateToRevision)
        connect(view, SIGNAL('mergeWithRevision'), self.mergeWithRevision)
        connect(view, SIGNAL('tagToRevision'), self.tagToRevision)
        connect(view, SIGNAL('backoutToRevision'), self.backoutToRevision)
        connect(view, SIGNAL('emailRevision'), self.emailRevision)
        connect(view, SIGNAL('archiveRevision'), self.archiveRevision)
        connect(view, SIGNAL('copyHash'), self.copyHash)
        connect(view, SIGNAL('rebaseRevision'), self.rebaseRevision)
        connect(view, SIGNAL('qimportRevision'), self.qimportRevision)
        connect(view, SIGNAL('qfinishRevision'), self.qfinishRevision)
        connect(view, SIGNAL('stripRevision'), self.stripRevision)
        #self.attachQuickBar(view.goto_toolbar)
        gotoaction = view.goto_toolbar.toggleViewAction()
        gotoaction.setIcon(geticon('goto'))
        #self.toolBar_edit.addAction(gotoaction)

    def on_filled(self):
        'initial batch of revisions loaded'
        self._repodate = self._getrepomtime()
        self.repoview.resizeColumns()
        if self._reload_rev is not None:
            try:
                self.repoview.goto(self._reload_rev)
                self.revDetailsWidget.on_filled()
            except IndexError:
                pass

    def loaded(self):
        'all revisions loaded (graph generator completed)'
        # Perhaps we can update a GUI element later, to indicate full load
        pass

    def revision_activated(self, rev=None):
        run.manifest(self.repo.ui, repo=self.repo,
                     rev=rev or self.repoview.current_rev)

    def setScanForRepoChanges(self, enable):
        saved = self._scanForRepoChanges
        self._scanForRepoChanges = enable
        return saved

    def updateToRevision(self, rev):
        saved = self.setScanForRepoChanges(False)
        dlg = update.UpdateDialog(rev, self.repo, self)
        if dlg.exec_():
            self.refresh()
        self.setScanForRepoChanges(saved)

    def mergeWithRevision(self, rev):
        saved = self.setScanForRepoChanges(False)
        dlg = merge.MergeDialog(rev, self.repo, self)
        def invalidated():
            self.reload()
        dlg.repoInvalidated.connect(invalidated)
        dlg.exec_()
        self.setScanForRepoChanges(saved)

    def tagToRevision(self, rev):
        origlen = len(self.repo)
        saved = self.setScanForRepoChanges(False)
        dlg = tag.TagDialog(self.repo, rev=str(rev), parent=self)
        def invalidated():
            self.repo.thginvalidate()
            if len(self.repo) != origlen:
                self.reload()
            else:
                self.refresh()
            origlen = len(self.repo)
        dlg.repoInvalidated.connect(invalidated)
        dlg.exec_()
        self.setScanForRepoChanges(saved)

    def backoutToRevision(self, rev):
        saved = self.setScanForRepoChanges(False)
        dlg = backout.BackoutDialog(self.repo, str(rev), self)
        if dlg.exec_():
            self.reload() # TODO: implement something less drastic than a full reload
        self.setScanForRepoChanges(saved)

    def stripRevision(self, rev):
        """Strip the selected revision and all descendants"""
        saved = self.setScanForRepoChanges(False)
        dlg = thgstrip.StripDialog(self.repo, rev=str(rev), parent=self)
        if dlg.exec_():
            self.reload() # TODO: implement something less drastic than a full reload
        self.setScanForRepoChanges(saved)

    def emailRevision(self, rev):
        run.email(self.repo.ui, rev=[str(rev)], repo=self.repo)

    def archiveRevision(self, rev):
        dlg = archive.ArchiveDialog(self.repo.ui, self.repo, rev, self)
        dlg.exec_()

    def copyHash(self, rev):
        clip = QApplication.clipboard()
        clip.setText(binascii.hexlify(self.repo[rev].node()))

    def rebaseRevision(self, srcrev):
        """Rebase selected revision on top of working directory parent"""
        dstrev = self.repo['.'].rev()
        saved = self.setScanForRepoChanges(False)
        main = _("Confirm Rebase Revision")
        text = _("Rebase revision %d on top of %d?") % (srcrev, dstrev)
        labels = ((QMessageBox.Yes, _('&Yes')),
                  (QMessageBox.No, _('&No')))
        cmdline = ['rebase', '--source', str(srcrev), '--dest', str(dstrev),
                   '--repository', self.repo.root]
        if QuestionMsgBox(_('Confirm Rebase'), main, text, labels=labels,
                          parent=self):
            self.runner = cmdui.Runner(_('Rebase - TortoiseHg'), self)
            def finished(ret):
                # TODO: implement something less drastic than a full reload
                self.reload()
                self.setScanForRepoChanges(saved)
            self.runner.commandFinished.connect(finished)
            self.runner.run(cmdline)

    def qimportRevision(self, rev):
        """QImport revision and all descendents to MQ"""
        saved = self.setScanForRepoChanges(False)
        if 'qparent' in self.repo.tags():
            endrev = 'qparent'
        else:
            endrev = ''
        cmdline = ['qimport', '--rev', '%s::%s' % (rev, endrev),
                   '--repository', self.repo.root]
        self.runner = cmdui.Runner(_('QImport - TortoiseHg'), self)
        def finished(ret):
            self.reload()
            self.setScanForRepoChanges(saved)
        self.runner.commandFinished.connect(finished)
        self.runner.run(cmdline)

    def qfinishRevision(self, rev):
        """Finish applied patches up to and including selected revision"""
        saved = self.setScanForRepoChanges(False)
        cmdline = ['qfinish', 'qbase::%s' % rev,
                   '--repository', self.repo.root]
        self.runner = cmdui.Runner(_('QFinish - TortoiseHg'), self)
        def finished(ret):
            self.reload()
            self.setScanForRepoChanges(saved)
        self.runner.commandFinished.connect(finished)
        self.runner.run(cmdline)

    def revision_selected(self, rev):
        if self.repomodel.graph is None:
            return
        if type(rev) == str: # unapplied patch
            self.revDetailsStackedWidget.setCurrentWidget(self.blankMessageWidget)
            self.taskTabsWidget.setCurrentIndex(self.logTabIndex)
            return

        ctx = self.repomodel.repo.changectx(rev)
        if ctx.rev() is None:
            self.taskTabsWidget.setCurrentIndex(self.commitTabIndex)
        else:
            self.revDetailsWidget.revision_selected(rev)
            self.taskTabsWidget.setCurrentIndex(self.logTabIndex)
        self.revDetailsStackedWidget.setCurrentWidget(self.revDetailsWidget)
        self.updateActions()

    def goto(self, rev):
        rev = str(rev)
        if len(self.repoview.model().graph):
            self.repoview.goto(rev)
        else:
            # store rev to show once it's available (when graph
            # filling is still running)
            self._reload_rev = rev

    def _getrepomtime(self):
        """Return the last modification time for the repo"""
        watchedfiles = [(self.repo.root, ".hg", "store", "00changelog.i"),
                        (self.repo.root, ".hg", "dirstate")]
        watchedfiles = [os.path.join(*wf) for wf in watchedfiles]
        mtime = [os.path.getmtime(wf) for wf in watchedfiles \
                 if os.path.isfile(wf)]
        if mtime:
            return max(mtime)
        # humm, directory has probably been deleted, exiting...
        self.close()

    def reload(self, rev=None):
        'Initiate a refresh of the repo model, rebuild graph'
        if rev == None:
            self._reload_rev = self.repoview.current_rev
        else:
            self._reload_rev = rev
        self.repo = thgrepo.repository(self.repo.ui, self.repo.root)
        self.repo.thginvalidate()
        self._repodate = self._getrepomtime()
        self.setupModels()
        cw = self.getCommitWidget()
        if cw:
            cw.stwidget.refreshWctx()
        self.revDetailsWidget.reload(rev)

    def refresh(self):
        'Refresh the repo model view, clear cached data'
        self.repo.thginvalidate()
        self.repomodel.invalidate()
        self.revDetailsWidget.on_filled()

    def getCommitWidget(self):
        return self.commitStackedWidget.currentWidget()

    def setRepomodel(self, branch, allparents=True):
        self.repomodel.setRepo(self.repo, branch=branch, allparents=allparents)

    def filterbranch(self):
        return self.repomodel.branch()

    def okToContinue(self):
        cw = self.getCommitWidget()
        if cw:
            return cw.canExit()
        return True

    def switchTo(self):
        self.switchToSignal.emit(self)

    def switchedTo(self):
        rev = self.repoview.current_rev
        if rev is None:
            self.taskTabsWidget.setCurrentIndex(self.commitTabIndex)
        elif type(rev) is str:
            self.revDetailsStackedWidget.setCurrentWidget(self.blankMessageWidget)
        else:
            self.revDetailsStackedWidget.setCurrentWidget(self.revDetailsWidget)
        self.updateActions()

    def updateActions(self):
        mode = self.revDetailsWidget.getMode()
        wb = self.workbench
        enable = self.repoview.current_rev is not None
        wb.actionDiffMode.setEnabled(enable)
        wb.actionDiffMode.setChecked(mode == 'diff')
        ann = self.revDetailsWidget.getAnnotate()
        wb.actionAnnMode.setChecked(ann)
        wb.actionAnnMode.setEnabled(enable and mode != 'diff')
        wb.actionNextDiff.setEnabled(enable and mode != 'diff')
        wb.actionPrevDiff.setEnabled(enable and mode != 'diff')
        self.repoview.updateActions()

    def storeSettings(self):
        self.revDetailsWidget.storeSettings()
        s = QSettings()
        # TODO: should it be 'repowidget/xxx' ?
        s.setValue('Workbench/repotabs_splitter',
                   self.repotabs_splitter.saveState())

    def restoreSettings(self):
        self.revDetailsWidget.restoreSettings()
        s = QSettings()
        # TODO: should it be 'repowidget/xxx' ?
        self.repotabs_splitter.restoreState(
            s.value('Workbench/repotabs_splitter').toByteArray())

    def closeRepoWidget(self):
        '''returns False if close should be aborted'''
        if not self.okToContinue():
            return False
        if self.isVisible():
            # assuming here that there is at most one RepoWidget visible
            self.storeSettings()
        self.revDetailsStackedWidget.removeWidget(self.revDetailsWidget)
        s = QSettings()
        cw = self.getCommitWidget()
        if cw:
            cw.storeConfigs(s)
        return True

class BlankMessageWidget(QWidget):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        la = QLabel("Can't yet display change details for unapplied patches")
        layout.addWidget(la)

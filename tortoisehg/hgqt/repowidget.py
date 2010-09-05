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
from tortoisehg.hgqt.qtlib import CustomPrompt, SharedWidget, DemandWidget
from tortoisehg.hgqt.repomodel import HgRepoListModel
from tortoisehg.hgqt.quickbar import FindInGraphlogQuickBar
from tortoisehg.hgqt import cmdui, update, tag, backout, merge, visdiff
from tortoisehg.hgqt import archive, thgimport, thgstrip, run

from tortoisehg.hgqt.repoview import HgRepoView
from tortoisehg.hgqt.revdetailswidget import RevDetailsWidget
from tortoisehg.hgqt.commit import CommitWidget
from tortoisehg.hgqt.manifestdialog import ManifestWidget
from tortoisehg.hgqt.sync import SyncWidget
from tortoisehg.hgqt.grep import SearchWidget

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class RepoWidget(QWidget):

    showMessageSignal = pyqtSignal(str)
    closeSelfSignal = pyqtSignal(QWidget)

    def __init__(self, repo, workbench):
        QWidget.__init__(self)

        self.repo = repo
        self.workbench = workbench
        self._reload_rev = '.' # select working parent at startup
        self._scanForRepoChanges = True
        self.currentMessage = ''
        self.runner = None

        self.load_config()
        self.setupUi()
        self.createActions()
        self.setupModels()

        self._repomtime = self._getrepomtime()
        self._dirstatemtime = self._getdirstatemtime()
        self._oldparents = repo.parents()
        self._watchrepotimer = self.startTimer(500)

        self.restoreSettings()

    def setupUi(self):
        SP = QSizePolicy

        self.repotabs_splitter = QSplitter(orientation=Qt.Vertical)
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self.repotabs_splitter)

        self.repoview = view = HgRepoView(self.workbench, self.repo)
        view.revisionSelected.connect(self.revision_selected)
        view.revisionClicked.connect(self.revision_clicked)
        view.revisionActivated.connect(self.revision_activated)
        view.showMessage.connect(self.showMessage)
        view.menuRequested.connect(self.viewMenuRequest)

        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(1)
        sp.setHeightForWidth(self.repoview.sizePolicy().hasHeightForWidth())
        view.setSizePolicy(sp)
        view.setFrameShape(QFrame.StyledPanel)

        self.repotabs_splitter.addWidget(self.repoview)
        self.repotabs_splitter.setCollapsible(0, False)

        self.taskTabsWidget = tt = QTabWidget()
        tt.setDocumentMode(True)
        tt.setTabPosition(QTabWidget.East)
        self.repotabs_splitter.addWidget(self.taskTabsWidget)

        self.revDetailsWidget = w = RevDetailsWidget(self.repo, self.repoview)
        w.revisionLinkClicked.connect(self.goto)
        self.logTabIndex = idx = tt.addTab(w, geticon('log'), '')
        tt.setTabToolTip(idx, _("Revision details"))

        self.commitDemand = w = DemandWidget(self.createCommitWidget)
        self.commitTabIndex = idx = tt.addTab(w, geticon('commit'), '')
        tt.setTabToolTip(idx, _("Commit"))

        self.manifestDemand = w = DemandWidget(self.createManifestWidget)
        self.manifestTabIndex = idx = tt.addTab(w, geticon('annotate'), '')
        tt.setTabToolTip(idx, _('Manifest'))

        self.syncDemand = w = DemandWidget(self.createSyncWidget)
        self.syncTabIndex = idx = tt.addTab(w, geticon('sync'), '')
        tt.setTabToolTip(idx, _("Synchronize"))

        self.grepDemand = w = DemandWidget(self.createGrepWidget)
        self.grepTabIndex = idx = tt.addTab(w, geticon('repobrowse'), '')
        tt.setTabToolTip(idx, _("Search"))

        d = self.revDetailsWidget
        self.findToolbar = tb = FindInGraphlogQuickBar(self)
        tb.revisionSelected.connect(self.repoview.goto)
        tb.fileSelected.connect(d.filelist.selectFile)
        tb.showMessage.connect(self.showMessage)
        tb.attachFileView(d.fileview)
        self.layout().addWidget(tb)

    def find(self):
        self.findToolbar.setVisible(True)

    def getCommitWidget(self):
        return getattr(self.repo, '_commitwidget', None)  # TODO: ugly

    def createCommitWidget(self):
        cw = self.getCommitWidget()
        if cw:
            cw.commitComplete.connect(self.reload)
            return SharedWidget(cw)

        pats = {}
        opts = {}
        b = QPushButton('Commit')
        cw = CommitWidget(pats, opts, root=self.repo.root)
        cw.showMessage.connect(self.showMessage)
        cw.commitComplete.connect(self.reload)
        cw.commitComplete.connect(cw.reload)
        cw.buttonHBox.addWidget(b)
        cw.commitButtonName.connect(lambda n: b.setText(n))
        cw.loadConfigs(QSettings())
        cw.reload()
        b.clicked.connect(cw.commit)
        self.repo._commitwidget = cw
        return SharedWidget(cw)

    def createManifestWidget(self):
        def filterrev(rev):
            if isinstance(rev, basestring):  # unapplied patch
                return None  # TODO
            else:
                return rev
        w = ManifestWidget(self.repo.ui, self.repo, rev=filterrev(self.rev),
                           parent=self)
        self.repoview.revisionClicked.connect(lambda rev:
                           w.setrev(filterrev(rev)))
        w.revchanged.connect(self.repoview.goto)
        return w

    def createSyncWidget(self):
        sw = SyncWidget(root=self.repo.root, log=self.workbench.log)
        sw.outgoingNodes.connect(self.setOutgoingNodes)
        sw.invalidate.connect(self.reload)
        sw.showMessage.connect(self.showMessage)
        return sw

    def setOutgoingNodes(self, nodes):
        self.repo._outgoing = nodes
        self.refresh()

    def createGrepWidget(self):
        upats = {}
        gw = SearchWidget(upats, self.repo.root, self)
        gw.setRevision(self.repoview.current_rev)
        return gw

    def load_config(self):
        self._font = getfont(self.repo.ui, 'fontlog')
        self.rowheight = 8
        self.users, self.aliases = [], []
        self.hidefinddelay = False

    def reponame(self):
        return os.path.basename(self.repo.root)

    @property
    def rev(self):
        """Returns the current active revision"""
        return self.repoview.current_rev

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
            self._checkuimtime()
            self._checkdirstate()
            mtime = self._getrepomtime()
            if mtime > self._repomtime:
                self.showMessage(_("Repository has been modified "
                                   "(reloading is recommended)"))

    def createActions(self):
        self.actionActivateRev = QAction('Activate rev.', self)
        self.actionActivateRev.setShortcuts([Qt.SHIFT+Qt.Key_Return,
                                             Qt.SHIFT+Qt.Key_Enter])
        self.actionActivateRev.triggered.connect(self.revision_activated)
        self.addAction(self.actionActivateRev)

        allactions = [
            ('manifest', _('Browse at rev...'), None,
                _('Show the manifest at selected revision'), None, self.manifestRevision),
            ('update', _('Update...'), 'update', None, None, self.updateToRevision),
            ('merge', _('Merge with...'), 'merge', None, None, self.mergeWithRevision),
            ('tag', _('Tag...'), 'tag', None, None, self.tagToRevision),
            ('backout', _('Backout...'), None, None, None, self.backoutToRevision),
            ('email', _('Email patch...'), None, None, None, self.emailRevision),
            ('archive', _('Archive...'), None, None, None, self.archiveRevision),
            ('copyhash', _('Copy hash'), None, None, None, self.copyHash),
            ('rebase', _('Rebase...'), None, None, None, self.rebaseRevision),
            ('qimport', _('Import Revision to MQ'), None, None, None,
                self.qimportRevision),
            ('qfinish', _('Finish patch'), None, None, None, self.qfinishRevision),
            ('strip', _('Strip Revision...'), None, None, None, self.stripRevision),
            ('qgoto', _('Goto patch'), None, None, None, self.qgotoRevision)
        ]

        self._actions = {}
        for name, desc, icon, tip, key, cb in allactions:
            self._actions[name] = act = QAction(desc, self)
            if icon:
                act.setIcon(geticon(icon))
            if tip:
                act.setStatusTip(tip)
            if key:
                act.setShortcut(key)
            if cb:
                act.triggered.connect(cb)
            self.addAction(act)

    def back(self):
        self.repoview.back()

    def forward(self):
        self.repoview.forward()

    def thgimport(self):
        l = len(self.repo)
        dlg = thgimport.ImportDialog(repo=self.repo, parent=self)
        dlg.repoInvalidated.connect(self.reload)
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
                (_('&Unknown'), _('&Ignored'), _('&Both'), _('Cancel')),
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

    def create_models(self):
        self.repomodel = HgRepoListModel(self.repo)
        self.repomodel.filled.connect(self.modelFilled)
        self.repomodel.loaded.connect(self.modelLoaded)
        self.repomodel.showMessage.connect(self.showMessage)
        self.findToolbar.setModel(self.repomodel)

    def setupModels(self):
        self.create_models()
        self.repoview.setModel(self.repomodel)
        self.revDetailsWidget.setupModels(self.repomodel)

    def modelFilled(self):
        'initial batch of revisions loaded'
        self.repoview.resizeColumns()
        if self._reload_rev is not None:
            try:
                self.repoview.goto(self._reload_rev)
                self.revDetailsWidget.on_filled()
            except IndexError:
                pass

    def modelLoaded(self):
        'all revisions loaded (graph generator completed)'
        # Perhaps we can update a GUI element later, to indicate full load
        pass

    def setScanForRepoChanges(self, enable):
        saved = self._scanForRepoChanges
        self._scanForRepoChanges = enable
        return saved

    def revision_clicked(self, rev):
        'User clicked on a repoview row'
        tw = self.taskTabsWidget
        if rev is None:
            tw.setCurrentIndex(self.commitTabIndex)
        else:
            revwidgets = (self.revDetailsWidget, self.manifestDemand)
            if tw.currentWidget() not in revwidgets:
                tw.setCurrentIndex(self.logTabIndex)

    def revision_selected(self, rev):
        'View selection changed, could be a reload'
        if self.repomodel.graph is None:
            return
        if type(rev) == str: # unapplied patch
            self.revDetailsWidget.revision_selected(None)
        else:
            self.revDetailsWidget.revision_selected(rev)
            self.grepDemand.forward('setRevision', rev)

    def goto(self, rev):
        rev = str(rev)
        if len(self.repoview.model().graph):
            self.repoview.goto(rev)
        else:
            # store rev to show once it's available (when graph
            # filling is still running)
            self._reload_rev = rev

    def revision_activated(self, rev=None):
        rev = rev or self.rev
        if isinstance(rev, basestring):  # unapplied patch
            return
        visdiff.visualdiff(self.repo.ui, self.repo, [], {'change':rev})

    def _getrepomtime(self):
        'Return the last modification time for the repo'
        watchedfiles = [self.repo.sjoin('00changelog.i'),
                        self.repo.join('patches/status')]
        try:
            mtime = [os.path.getmtime(wf) for wf in watchedfiles \
                     if os.path.isfile(wf)]
            if mtime:
                return max(mtime)
        except EnvironmentError:
            return None
        self._scanForRepoChanges = False
        self.closeSelfSignal.emit(self)

    def _getdirstatemtime(self):
        try:
            f = self.repo.join('dirstate')
            return os.path.getmtime(f)
        except EnvironmentError, ValueError:
            return None

    def _checkdirstate(self):
        'Check for new dirstate mtime, working parent changes'
        mtime = self._getdirstatemtime()
        if mtime <= self._dirstatemtime:
            return
        self._dirstatemtime = mtime
        self.repo.dirstate.invalidate()
        newp = self.repo.parents()
        if newp != self._oldparents:
            self._oldparents = newp
            self.showMessage(_('Working parent(s) have changed '
                               '(reloading is recommended)'))


    def _checkuimtime(self):
        'Check for modified config files, or a new .hg/hgrc file'
        try:
            oldmtime, files = self.repo.uifiles()
            files.add(self.repo.join('hgrc'))
            mtime = [os.path.getmtime(f) for f in files if os.path.isfile(f)]
            if max(mtime) > oldmtime:
                self.showMessage(_('Configuration change detected.'))
                self.repo.invalidateui()
                self.syncDemand.forward('reload')
                self.repomodel.invalidate() # username, author colors, fonts
        except EnvironmentError, ValueError:
            return None

    def reload(self, rev=None):
        'Initiate a refresh of the repo model, rebuild graph'
        if rev is None:
            self._reload_rev = self.rev
        else:
            self._reload_rev = rev
        self.showMessage('')
        self.repo.thginvalidate()
        self._repomtime = self._getrepomtime()
        self._dirstatemtime = self._getdirstatemtime()
        self._oldparents = self.repo.parents()
        self.setupModels()
        self.commitDemand.forward('reload')
        self.revDetailsWidget.reload()

    def reloadTaskTab(self):
        tti = self.taskTabsWidget.currentIndex()
        if tti == self.logTabIndex:
            ttw = self.revDetailsWidget
        elif tti == self.commitTabIndex:
            ttw = self.commitDemand.get()
        elif tti == self.manifestTabIndex:
            ttw = self.manifestDemand.get()
        elif tti == self.syncTabIndex:
            ttw = self.syncDemand.get()
        elif tti == self.grepTabIndex:
            ttw = self.grepDemand.get()
        if ttw:
            ttw.reload()

    def refresh(self):
        'Refresh the repo model view, clear cached data'
        self.repo.thginvalidate()
        self.repomodel.invalidate()
        self.revDetailsWidget.on_filled()

    def setBranch(self, branch, allparents=True):
        'Triggered by workbench on branch selection'
        self.repomodel.setBranch(branch=branch, allparents=allparents)

    def filterbranch(self):
        return self.repomodel.branch()

    def okToContinue(self):
        cw = self.getCommitWidget()
        if cw:
            return cw.canExit()
        return True

    def switchedTo(self):
        'Update back / forward actions'
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
        self.revDetailsWidget.storeSettings()
        s = QSettings()
        self.commitDemand.forward('storeConfigs', s)
        return True

    def runCommand(self, title, cmdline):
        if self.runner:
            InfoMsgBox(_('Unable to start'),
                       _('Previous command is still running'))
            return
        saved = self.setScanForRepoChanges(False)
        self.runner = cmdui.Runner(title, self)
        def finished(ret):
            self.reload()
            self.setScanForRepoChanges(saved)
            self.runner = None
            # When we run commands, we typically change working parent
            self.commitDemand.forward('reload')
        self.runner.commandFinished.connect(finished)
        self.runner.run(cmdline)

    ##
    ## Repoview context menu
    ##

    def viewMenuRequest(self, point, selection):
        'User requested a context menu in repo view widget'
        # TODO: selection is ignored at the moment
        menu = QMenu(self)
        for act in ['update', 'manifest', 'merge', 'tag', 'backout',
                    'email', 'archive', 'copyhash', None,
                    None]:
            if act:
                menu.addAction(self._actions[act])
            else:
                menu.addSeparator()
        exs = self.repo.extensions()
        if 'rebase' in exs:
            menu.addSeparator()
            menu.addAction(self._actions['rebase'])
        if 'mq' in exs:
            ctx = self.repo.changectx(self.rev)
            menu.addSeparator()
            if ctx.thgmqappliedpatch():
                menu.addAction(self._actions['qfinish'])
            elif ctx.thgmqunappliedpatch():
                menu.addAction(self._actions['qgoto'])
            else:
                menu.addAction(self._actions['qimport'])
            menu.addAction(self._actions['strip'])
        menu.exec_(point)

    def updateToRevision(self, rev=None):
        rev = rev or self.rev
        saved = self.setScanForRepoChanges(False)
        def finished(ret):
            if ret == 0:
                self.reload()
                self.commitDemand.forward('reload')
        dlg = update.UpdateDialog(rev, self.repo, self)
        dlg.cmdfinished.connect(finished)
        dlg.exec_()
        self.setScanForRepoChanges(saved)

    def manifestRevision(self, rev=None):
        rev = rev or self.rev
        run.manifest(self.repo.ui, repo=self.repo, rev=rev or self.rev)

    def mergeWithRevision(self, rev=None):
        rev = rev or self.rev
        saved = self.setScanForRepoChanges(False)
        dlg = merge.MergeDialog(rev, self.repo, self)
        def invalidated():
            self.reload()
        dlg.repoInvalidated.connect(invalidated)
        dlg.exec_()
        self.setScanForRepoChanges(saved)

    def tagToRevision(self, rev=None):
        rev = rev or self.rev
        saved = self.setScanForRepoChanges(False)
        dlg = tag.TagDialog(self.repo, rev=str(rev), parent=self)
        dlg.tagChanged.connect(self.reload)
        dlg.localTagChanged.connect(self.refresh)
        dlg.showMessage.connect(self.showMessage)
        dlg.exec_()
        self.setScanForRepoChanges(saved)

    def backoutToRevision(self, rev=None):
        rev = rev or self.rev
        saved = self.setScanForRepoChanges(False)
        dlg = backout.BackoutDialog(self.repo, str(rev), self)
        if dlg.exec_():
            self.reload()
        self.setScanForRepoChanges(saved)

    def stripRevision(self, rev=None):
        """Strip the selected revision and all descendants"""
        rev = rev or self.rev
        saved = self.setScanForRepoChanges(False)
        dlg = thgstrip.StripDialog(self.repo, rev=str(rev), parent=self)
        if dlg.exec_():
            self.reload()
        self.setScanForRepoChanges(saved)

    def emailRevision(self, rev=None):
        rev = rev or self.rev
        run.email(self.repo.ui, rev=[str(rev)], repo=self.repo)

    def archiveRevision(self, rev=None):
        rev = rev or self.rev
        dlg = archive.ArchiveDialog(self.repo.ui, self.repo, rev, self)
        dlg.exec_()

    def copyHash(self, rev=None):
        rev = rev or self.rev
        clip = QApplication.clipboard()
        clip.setText(binascii.hexlify(self.repo[rev].node()))

    def rebaseRevision(self, srcrev=None):
        """Rebase selected revision on top of working directory parent"""
        srcrev = srcrev or self.rev
        dstrev = self.repo['.'].rev()
        main = _("Confirm Rebase Revision")
        text = _("Rebase revision %d on top of %d?") % (srcrev, dstrev)
        labels = ((QMessageBox.Yes, _('&Yes')),
                  (QMessageBox.No, _('&No')))
        cmdline = ['rebase', '--source', str(srcrev), '--dest', str(dstrev),
                   '--repository', self.repo.root]
        if QuestionMsgBox(_('Confirm Rebase'), main, text, labels=labels,
                          parent=self):
            self.runCommand(_('Rebase - TortoiseHg'), cmdline)

    def qimportRevision(self, rev=None):
        """QImport revision and all descendents to MQ"""
        rev = rev or self.rev
        if 'qparent' in self.repo.tags():
            endrev = 'qparent'
        else:
            endrev = ''
        cmdline = ['qimport', '--rev', '%s::%s' % (rev, endrev),
                   '--repository', self.repo.root]
        self.runCommand(_('QImport - TortoiseHg'), cmdline)

    def qfinishRevision(self, rev=None):
        """Finish applied patches up to and including selected revision"""
        rev = rev or self.rev
        cmdline = ['qfinish', 'qbase::%s' % rev,
                   '--repository', self.repo.root]
        self.runCommand(_('QFinish - TortoiseHg'), cmdline)

    def qgotoRevision(self, patchname=None):
        """Make PATCHNAME the top applied patch"""
        patchname = patchname or self.rev
        cmdline = ['qgoto', str(patchname),  # FIXME force option
                   '--repository', self.repo.root]
        self.runCommand(_('QGoto - TortoiseHg'), cmdline)

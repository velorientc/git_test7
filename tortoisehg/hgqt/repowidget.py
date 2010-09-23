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

from tortoisehg.util import shlib, hglib

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.qtlib import geticon, getfont, QuestionMsgBox, InfoMsgBox
from tortoisehg.hgqt.qtlib import CustomPrompt, SharedWidget, DemandWidget
from tortoisehg.hgqt.repomodel import HgRepoListModel
from tortoisehg.hgqt.quickbar import FindInGraphlogQuickBar
from tortoisehg.hgqt import cmdui, update, tag, backout, merge, visdiff
from tortoisehg.hgqt import archive, thgimport, thgstrip, run, thgrepo, purge

from tortoisehg.hgqt.repoview import HgRepoView
from tortoisehg.hgqt.revdetails import RevDetailsWidget
from tortoisehg.hgqt.commit import CommitWidget
from tortoisehg.hgqt.manifestdialog import ManifestWidget
from tortoisehg.hgqt.sync import SyncWidget
from tortoisehg.hgqt.grep import SearchWidget

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class RepoWidget(QWidget):

    showMessageSignal = pyqtSignal(str)
    closeSelfSignal = pyqtSignal(QWidget)

    output = pyqtSignal(QString, QString)
    progress = pyqtSignal(QString, object, QString, QString, object)
    makeLogVisible = pyqtSignal(bool)

    def __init__(self, repo, workbench):
        QWidget.__init__(self)

        self.repo = repo
        repo.repositoryChanged.connect(self.repositoryChanged)
        repo.repositoryDestroyed.connect(self.repositoryDestroyed)
        repo.configChanged.connect(self.configChanged)
        self.workbench = workbench

        self._reload_rev = '.' # select working parent at startup
        self.currentMessage = ''
        self.runner = None
        self.dirty = False

        self.load_config()
        self.setupUi()
        self.createActions()
        self.setupModels()
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
        w.fileview.showDescSignal.connect(self.showMessage)
        self.logTabIndex = idx = tt.addTab(w, geticon('log'), '')
        tt.setTabToolTip(idx, _("Revision details"))

        self.commitDemand = w = DemandWidget(self.createCommitWidget)
        self.commitTabIndex = idx = tt.addTab(w, geticon('commit'), '')
        tt.setTabToolTip(idx, _("Commit"))

        self.manifestDemand = w = DemandWidget(self.createManifestWidget)
        self.manifestTabIndex = idx = tt.addTab(w, geticon('annotate'), '')
        tt.setTabToolTip(idx, _('Manifest'))

        self.grepDemand = w = DemandWidget(self.createGrepWidget)
        self.grepTabIndex = idx = tt.addTab(w, geticon('repobrowse'), '')
        tt.setTabToolTip(idx, _("Search"))

        self.syncDemand = w = DemandWidget(self.createSyncWidget)
        self.syncTabIndex = idx = tt.addTab(w, geticon('sync'), '')
        tt.setTabToolTip(idx, _("Synchronize"))

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
        cw = CommitWidget(pats, opts, self.repo.root, True, self)

        # Shared widgets must be connected directly to workbench
        cw.output.connect(self.workbench.log.output)
        cw.progress.connect(lambda tp, p, i, u, tl:
            self.workbench.statusbar.progress(tp, p, i, u, tl, self.repo.root))
        cw.makeLogVisible.connect(self.workbench.log.setShown)
        cw.linkActivated.connect(self.workbench.linkActivated)

        cw.showMessage.connect(self.showMessage)
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
        sw = getattr(self.repo, '_syncwidget', None)  # TODO: ugly
        if not sw:
            sw = SyncWidget(self.repo.root, True, self)
            # Shared widgets must be connected directly to workbench
            sw.output.connect(self.workbench.log.output)
            sw.progress.connect(lambda tp, p, i, u, tl:
                self.workbench.statusbar.progress(tp, p, i, u, tl,
                                                  self.repo.root))
            sw.makeLogVisible.connect(self.workbench.log.setShown)
            self.repo._syncwidget = sw
        sw.outgoingNodes.connect(self.setOutgoingNodes)
        sw.showMessage.connect(self.showMessage)
        return SharedWidget(sw)

    def setOutgoingNodes(self, nodes):
        self.repo._outgoing = nodes
        self.refresh()

    def createGrepWidget(self):
        upats = {}
        gw = SearchWidget(upats, self.repo, self)
        gw.setRevision(self.repoview.current_rev)
        gw.showMessage.connect(self.showMessage)
        return gw

    def load_config(self):
        self._font = getfont(self.repo.ui, 'fontlog')
        self.rowheight = 8
        self.users, self.aliases = [], []
        self.hidefinddelay = False

    def reponame(self):
        return self.repo.shortname

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
        if self.dirty:
            print 'page was dirty, reloading...'
            self.reload()
            self.dirty = False

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
            ('qimport', _('Import to MQ'), None, None, None,
                self.qimportRevision),
            ('qfinish', _('Finish patch'), None, None, None, self.qfinishRevision),
            ('strip', _('Strip...'), None, None, None, self.stripRevision),
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
                       hglib.tounicode(str(e)))
            return
        U, I = wctx.unknown(), wctx.ignored()
        if not U and not I:
            InfoMsgBox(_('No unrevisioned files'),
                       _('There are no purgable unrevisioned files'))
            return
        dlg = purge.PurgeDialog(self.repo, U, I, self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.exec_()

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
        self.repoview.goto(self._reload_rev) # emits revision_selected
        self.revDetailsWidget.finishReload()

    def modelLoaded(self):
        'all revisions loaded (graph generator completed)'
        # Perhaps we can update a GUI element later, to indicate full load
        pass

    def revision_clicked(self, rev):
        'User clicked on a repoview row'
        tw = self.taskTabsWidget
        if rev is None:
            tw.setCurrentIndex(self.commitTabIndex)
        elif tw.currentWidget() in (self.commitDemand, self.syncDemand):
            tw.setCurrentIndex(self.logTabIndex)

    def revision_selected(self, rev):
        'View selection changed, could be a reload'
        if self.repomodel.graph is None:
            return
        if type(rev) == str: # unapplied patch
            self.revDetailsWidget.revision_selected(None)
            self.manifestDemand.forward('setrev', None)
        else:
            self.revDetailsWidget.revision_selected(rev)
            self.manifestDemand.forward('setrev', rev)
            self.grepDemand.forward('setRevision', rev)

    def goto(self, rev):
        if rev is not None:
            rev = str(rev)
        self._reload_rev = rev
        if len(self.repoview.model().graph):
            self.repoview.goto(rev)

    def revision_activated(self, rev=None):
        rev = rev or self.rev
        if isinstance(rev, basestring):  # unapplied patch
            return
        visdiff.visualdiff(self.repo.ui, self.repo, [], {'change':rev})

    def reload(self):
        'Initiate a refresh of the repo model, rebuild graph'
        self.repo.thginvalidate()
        self.rebuildGraph()
        self.commitDemand.forward('reload')

    def rebuildGraph(self):
        self.showMessage('')
        if self.rev is not None and len(self.repo) >= self.rev:
            self._reload_rev = '.'
        else:
            self._reload_rev = self.rev
        self.setupModels()
        self.revDetailsWidget.record()

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
        self.revDetailsWidget.reload()

    def repositoryDestroyed(self):
        'Repository has detected itself to be deleted'
        self.closeSelfSignal.emit(self)

    def repositoryChanged(self):
        'Repository has detected a changelog / dirstate change'
        if self.isVisible():
            self.rebuildGraph()
        else:
            self.dirty = True

    def configChanged(self):
        'Repository is reporting its config files have changed'
        self.repomodel.invalidate()
        self.revDetailsWidget.reload()
        branch = self.repomodel.branch()
        if branch:
            tabtext = '%s [%s]' % (self.repo.shortname, branch)
        else:
            tabtext = self.repo.shortname
        idx = self.workbench.repoTabsWidget.indexOf(self)
        self.workbench.repoTabsWidget.setTabText(idx, tabtext)

    ##
    ## Workbench methods
    ##

    def setBranch(self, branch, allparents=True):
        'Triggered by workbench on branch selection'
        self.repomodel.setBranch(branch=branch, allparents=allparents)

    def filterbranch(self):
        return self.repomodel.branch()

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

    def okToContinue(self):
        return self.commitDemand.forward('canExit', default=True) and \
               self.syncDemand.forward('canExit', default=True)

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

    def incoming(self):
        self.syncDemand.get().incoming()

    def pull(self):
        self.syncDemand.get().pull()

    def outgoing(self):
        self.syncDemand.get().outgoing()

    def push(self):
        self.syncDemand.get().push()

    ##
    ## Repoview context menu
    ##

    def viewMenuRequest(self, point, selection):
        'User requested a context menu in repo view widget'
        # TODO: selection is ignored at the moment
        # It is a list of the currently selected revisions.  Integers
        # for changelog revisions, None for the working copy, or strings
        # for unapplied patches.
        menu = QMenu(self)
        
        allactions = [['all',    ['update', 'manifest', 'merge', 'tag', 
                                  'backout', 'email', 'archive', 'copyhash']],
                      ['rebase', ['rebase']],
                      ['mq',     ['qgoto', 'qimport', 'qfinish', 'strip']]]

        exs = self.repo.extensions()        
        for ext, actions in allactions:
            if ext == 'all' or ext in exs:
                for act in actions:
                    menu.addAction(self._actions[act])
            menu.addSeparator()

        ctx = self.repo.changectx(self.rev)

        workingdir = self.rev is None
        appliedpatch = ctx.thgmqappliedpatch() 
        unappliedpatch = ctx.thgmqunappliedpatch()
        patch = appliedpatch or unappliedpatch
        realrev = not unappliedpatch and not workingdir
        normalrev = not patch and not workingdir

        enabled = {'update': normalrev,
                   'manifest': not unappliedpatch,
                   'merge': normalrev,
                   'tag': normalrev,
                   'backout': normalrev,
                   'email': not workingdir,
                   'archive': realrev,
                   'copyhash': realrev,
                   'rebase': normalrev,
                   'qgoto': patch,
                   'qimport': normalrev,
                   'qfinish': appliedpatch,
                   'strip': normalrev}
        for action, enabled in enabled.iteritems():
            self._actions[action].setEnabled(enabled)

        menu.exec_(point)

    def updateToRevision(self):
        dlg = update.UpdateDialog(self.rev, self.repo, self)
        dlg.output.connect(self.output)
        dlg.makeLogVisible.connect(self.makeLogVisible)
        dlg.progress.connect(self.progress)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()

    def manifestRevision(self):
        run.manifest(self.repo.ui, repo=self.repo, rev=self.rev)

    def mergeWithRevision(self):
        dlg = merge.MergeDialog(self.rev, self.repo, self)
        dlg.exec_()

    def tagToRevision(self):
        dlg = tag.TagDialog(self.repo, rev=str(self.rev), parent=self)
        dlg.localTagChanged.connect(self.refresh)
        dlg.showMessage.connect(self.showMessage)
        dlg.exec_()

    def backoutToRevision(self):
        dlg = backout.BackoutDialog(self.repo, str(self.rev), self)
        dlg.exec_()

    def stripRevision(self):
        'Strip the selected revision and all descendants'
        dlg = thgstrip.StripDialog(self.repo, rev=str(self.rev), parent=self)
        dlg.exec_()

    def emailRevision(self):
        run.email(self.repo.ui, rev=self.repoview.selectedRevisions(),
                  repo=self.repo)

    def archiveRevision(self):
        dlg = archive.ArchiveDialog(self.repo.ui, self.repo, self.rev, self)
        dlg.makeLogVisible.connect(self.makeLogVisible)
        dlg.output.connect(self.output)
        dlg.progress.connect(self.progress)
        dlg.exec_()

    def copyHash(self):
        clip = QApplication.clipboard()
        clip.setText(binascii.hexlify(self.repo[self.rev].node()))

    def rebaseRevision(self):
        """Rebase selected revision on top of working directory parent"""
        srcrev = self.rev
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

    def qimportRevision(self):
        """QImport revision and all descendents to MQ"""
        if 'qparent' in self.repo.tags():
            endrev = 'qparent'
        else:
            endrev = ''
        cmdline = ['qimport', '--rev', '%s::%s' % (self.rev, endrev),
                   '--repository', self.repo.root]
        self.runCommand(_('QImport - TortoiseHg'), cmdline)

    def qfinishRevision(self):
        """Finish applied patches up to and including selected revision"""
        cmdline = ['qfinish', 'qbase::%s' % self.rev,
                   '--repository', self.repo.root]
        self.runCommand(_('QFinish - TortoiseHg'), cmdline)

    def qgotoRevision(self):
        """Make REV the top applied patch"""
        patchname = self.repo.changectx(self.rev).thgmqpatchname()
        cmdline = ['qgoto', str(patchname),  # FIXME force option
                   '--repository', self.repo.root]
        self.runCommand(_('QGoto - TortoiseHg'), cmdline)

    def runCommand(self, title, cmdline):
        if self.runner:
            InfoMsgBox(_('Unable to start'),
                       _('Previous command is still running'))
            return
        def finished(ret):
            self.repo.decrementBusyCount()
            self.runner = None
        self.runner = cmdui.Runner(title, False, self)
        self.runner.output.connect(self.output)
        self.runner.progress.connect(self.progress)
        self.runner.makeLogVisible.connect(self.makeLogVisible)
        self.runner.commandFinished.connect(finished)
        self.repo.incrementBusyCount()
        self.runner.run(cmdline)

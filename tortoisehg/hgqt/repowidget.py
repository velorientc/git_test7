# repowidget.py - TortoiseHg repository widget
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
# Copyright (C) 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

import binascii
import os

from mercurial import util, revset

from tortoisehg.util import shlib, hglib

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.qtlib import geticon, getfont, QuestionMsgBox, InfoMsgBox
from tortoisehg.hgqt.qtlib import CustomPrompt, SharedWidget, DemandWidget
from tortoisehg.hgqt.repomodel import HgRepoListModel
from tortoisehg.hgqt import cmdui, update, tag, backout, merge, visdiff
from tortoisehg.hgqt import archive, thgimport, thgstrip, run, purge, bookmark
from tortoisehg.hgqt import bisect, rebase, resolve, thgrepo, compress
from tortoisehg.hgqt import qdelete, qreorder, qrename

from tortoisehg.hgqt.repofilter import RepoFilterBar
from tortoisehg.hgqt.repoview import HgRepoView
from tortoisehg.hgqt.revdetails import RevDetailsWidget
from tortoisehg.hgqt.commit import CommitWidget
from tortoisehg.hgqt.manifestdialog import ManifestTaskWidget
from tortoisehg.hgqt.sync import SyncWidget
from tortoisehg.hgqt.grep import SearchWidget
from tortoisehg.hgqt.quickbar import GotoQuickBar
from tortoisehg.hgqt.pbranch import PatchBranchWidget

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class RepoWidget(QWidget):

    showMessageSignal = pyqtSignal(QString)
    closeSelfSignal = pyqtSignal(QWidget)

    output = pyqtSignal(QString, QString)
    progress = pyqtSignal(QString, object, QString, QString, object)
    makeLogVisible = pyqtSignal(bool)

    titleChanged = pyqtSignal(unicode)
    """Emitted when changed the expected title for the RepoWidget tab"""

    singlecmenu = None
    unappcmenu = None
    paircmenu = None
    multicmenu = None

    def __init__(self, repo, workbench):
        QWidget.__init__(self, acceptDrops=True)

        self.repo = repo
        repo.repositoryChanged.connect(self.repositoryChanged)
        repo.repositoryDestroyed.connect(self.repositoryDestroyed)
        repo.configChanged.connect(self.configChanged)
        self.workbench = workbench
        self.revsetfilter = False
        self.branch = ''
        self.bundle = None
        self.revset = set()

        if repo.parents()[0].rev() == -1:
            self._reload_rev = 'tip'
        else:
            self._reload_rev = '.'
        self.currentMessage = ''
        self.runner = None
        self.dirty = False

        self.setupUi()
        self.createActions()
        self.restoreSettings()
        self.setupModels()

    def setupUi(self):
        SP = QSizePolicy

        self.repotabs_splitter = QSplitter(orientation=Qt.Vertical)
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)
        self.layout().addLayout(hbox)

        self.gototb = tb = GotoQuickBar(self)
        tb.setObjectName('gototb')
        tb.gotoSignal.connect(self.goto)
        hbox.addWidget(tb)

        self.bundleAccept = b = QPushButton(_('Accept'))
        b.setShown(False)
        b.setToolTip(_('Pull incoming changesets into your repository'))
        b.clicked.connect(self.acceptBundle)
        hbox.addWidget(b)
        self.bundleReject = b = QPushButton(_('Reject'))
        b.setToolTip(_('Reject incoming changesets'))
        b.clicked.connect(self.rejectBundle)
        b.setShown(False)
        hbox.addWidget(b)

        self.filterbar = RepoFilterBar(self.repo, self)
        self.filterbar.branchChanged.connect(self.setBranch)
        self.filterbar.progress.connect(self.progress)
        self.filterbar.showMessage.connect(self.showMessage)
        self.filterbar.revisionSet.connect(self.setRevisionSet)
        self.filterbar.clearSet.connect(self.clearSet)
        self.filterbar.filterToggled.connect(self.filterToggled)
        hbox.addWidget(self.filterbar)

        self.filterbar.hide()

        self.revsetfilter = self.filterbar.filtercb.isChecked()

        self.layout().addWidget(self.repotabs_splitter)

        self.repoview = view = HgRepoView(self.repo, self)
        view.revisionSelected.connect(self.revision_selected)
        view.revisionSelected.connect(self.updateHistoryActions)
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
        self.repotabs_splitter.setStretchFactor(0, 1)

        tt = QTabWidget()
        tt.setDocumentMode(True)
        tt.setTabPosition(QTabWidget.East)
        if not self.repo.ui.configbool('tortoisehg', 'tasktabs'):
            tt.tabBar().hide()

        self.taskTabsWidget = tt
        self.repotabs_splitter.addWidget(self.taskTabsWidget)
        self.repotabs_splitter.setStretchFactor(1, 1)

        self.revDetailsWidget = w = RevDetailsWidget(self.repo)
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

        self.pbranchDemand = w = DemandWidget(self.createPatchBranchWidget)
        self.updatePatchBranchTab()

    def title(self):
        """Returns the expected title for this widget [unicode]"""
        if self.bundle:
            return _('%s <incoming>') % self.repo.shortname
        elif self.branch:
            return '%s [%s]' % (self.repo.shortname, self.branch)
        else:
            return self.repo.shortname

    @pyqtSlot()
    def toggleSearchBar(self):
        """Toggle display of tasktab-specific search bar if available"""
        curtt = self.taskTabsWidget.currentWidget()
        show = getattr(curtt, 'toggleSearchBar', None)
        if show:
            show()

    @pyqtSlot()
    def toggleFilterBar(self):
        """Toggle display repowidget filter bar"""
        vis = self.filterbar.isVisible()
        self.filterbar.setVisible(not vis)

    @pyqtSlot()
    def toggleGotoBar(self):
        """Toggle display repowidget goto bar"""
        vis = self.gototb.isVisible()
        self.gototb.setVisible(not vis)

    def getCommitWidget(self):
        return getattr(self.repo, '_commitwidget', None)  # TODO: ugly

    def createCommitWidget(self):
        cw = self.getCommitWidget()
        if cw:
            cw.commitComplete.connect(self.reload)
            return SharedWidget(cw)

        pats = {}
        opts = {}
        b = QPushButton(_('Commit'))
        b.setAutoDefault(True)
        f = b.font()
        f.setWeight(QFont.Bold)
        b.setFont(f)
        cw = CommitWidget(pats, opts, self.repo.root, True, self)

        # Shared widgets must be connected directly to workbench
        cw.output.connect(self.workbench.log.output)
        cw.progress.connect(lambda tp, p, i, u, tl:
            self.workbench.statusbar.progress(tp, p, i, u, tl, self.repo.root))
        cw.makeLogVisible.connect(self.workbench.log.setShown)

        def openlink(link):
            if unicode(link).startswith('subrepo:'):
                self.workbench.showRepo(link[8:])
        cw.linkActivated.connect(openlink)

        cw.showMessage.connect(self.showMessage)
        cw.buttonHBox.addWidget(b)
        cw.commitButtonName.connect(lambda n: b.setText(n))
        cw.loadConfigs(QSettings())
        QTimer.singleShot(0, cw.reload)
        b.clicked.connect(cw.commit)
        self.repo._commitwidget = cw
        return SharedWidget(cw)

    def createManifestWidget(self):
        def filterrev(rev):
            if isinstance(rev, basestring):  # unapplied patch
                return None  # TODO
            else:
                return rev
        w = ManifestTaskWidget(self.repo.ui, self.repo, rev=filterrev(self.rev),
                               parent=self)
        self.repoview.revisionClicked.connect(lambda rev:
                           w.setRev(filterrev(rev)))
        w.revChanged.connect(self.repoview.goto)
        w.revisionHint.connect(self.showMessage)
        w.grepRequested.connect(self.grep)
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
        sw.incomingBundle.connect(self.setBundle)
        return SharedWidget(sw)

    @pyqtSlot(QString)
    def setBundle(self, bfile):
        self.bundle = unicode(bfile)
        oldlen = len(self.repo)
        self.repo = thgrepo.repository(self.repo.ui, self.repo.root,
                                       bundle=self.bundle)
        self.repoview.setRepo(self.repo)
        self.revDetailsWidget.setRepo(self.repo)
        self.bundleAccept.setHidden(False)
        self.bundleReject.setHidden(False)
        self.filterbar.revsetle.setText('incoming()')
        self.filterbar.setEnabled(False)
        self.filterbar.show()
        self.titleChanged.emit(self.title())
        newlen = len(self.repo)
        self.revset = [self.repo[n].node() for n in range(oldlen, newlen)]
        self.repomodel.revset = self.revset
        self.reload()

    def clearBundle(self):
        self.bundleAccept.setHidden(True)
        self.bundleReject.setHidden(True)
        self.filterbar.setEnabled(True)
        self.filterbar.revsetle.setText('')
        self.revset = []
        self.repomodel.revset = self.revset
        self.bundle = None
        self.titleChanged.emit(self.title())
        self.repo = thgrepo.repository(self.repo.ui, self.repo.root)
        self.repoview.setRepo(self.repo)
        self.revDetailsWidget.setRepo(self.repo)

    def acceptBundle(self):
        self.taskTabsWidget.setCurrentIndex(self.syncTabIndex)
        self.syncDemand.pullBundle(self.bundle, None)
        self.clearBundle()

    def pullToRev(self):
        self.taskTabsWidget.setCurrentIndex(self.syncTabIndex)
        self.syncDemand.pullBundle(self.bundle, self.rev)
        removed = [self.repo[self.rev]]
        while removed:
            ctx = removed.pop()
            if ctx.node() in self.revset:
                self.revset.remove(ctx.node())
                removed.extend(ctx.parents())
        self.repomodel.revset = self.revset
        if not self.revset:
            self.clearBundle()
        self.refresh()

    def rejectBundle(self):
        self.clearBundle()
        self.reload()

    def clearSet(self):
        self.revset = []
        if self.revsetfilter:
            self.reload()
        else:
            self.repomodel.revset = []
            self.refresh()

    def setRevisionSet(self, nodes):
        self.revset = [self.repo[n].node() for n in nodes]
        if self.revsetfilter:
            self.reload()
        else:
            self.repomodel.revset = self.revset
            self.refresh()

    @pyqtSlot(bool)
    def filterToggled(self, checked):
        self.revsetfilter = checked
        if self.revset:
            self.repomodel.filterbyrevset = checked
            self.reload()

    def setOutgoingNodes(self, nodes):
        self.filterbar.revsetle.setText('outgoing()')
        self.filterbar.show()
        self.setRevisionSet(nodes)

    def createGrepWidget(self):
        upats = {}
        gw = SearchWidget(upats, self.repo, self)
        gw.setRevision(self.repoview.current_rev)
        gw.showMessage.connect(self.showMessage)
        gw.progress.connect(self.progress)
        return gw

    def createPatchBranchWidget(self):
        pbw = PatchBranchWidget(self.repo, parent=self)
        pbw.output.connect(self.workbench.log.output)
        pbw.progress.connect(lambda tp, p, i, u, tl:
            self.workbench.statusbar.progress(tp, p, i, u, tl, self.repo.root))
        pbw.makeLogVisible.connect(self.workbench.log.setShown)
        return pbw

    def updatePatchBranchTab(self):
        "Only show pbranch tab when pbranch extension is installed"
        tt = self.taskTabsWidget
        w = self.pbranchDemand
        self.pbranchTabIndex = idx = tt.indexOf(w)
        if 'pbranch' in self.repo.extensions():
            if idx == -1:
                self.pbranchTabIndex = idx = tt.addTab(w, geticon('branch'), '')
                tt.setTabToolTip(idx, _("Patch Branch"))

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
        QShortcut(QKeySequence('CTRL+P'), self, self.gotoParent)

    def dragEnterEvent(self, event):
        paths = [unicode(u.toLocalFile()) for u in event.mimeData().urls()]
        if util.any(os.path.isfile(p) for p in paths):
            event.setDropAction(Qt.CopyAction)
            event.accept()

    def dropEvent(self, event):
        paths = [unicode(u.toLocalFile()) for u in event.mimeData().urls()]
        filepaths = [p for p in paths if os.path.isfile(p)]
        if filepaths:
            self.thgimport(filepaths)
            event.setDropAction(Qt.CopyAction)
            event.accept()

    def back(self):
        self.repoview.back()

    def forward(self):
        self.repoview.forward()

    def bisect(self, paths=None):
        dlg = bisect.BisectDialog(self.repo, {}, self)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()

    def resolve(self, paths=None):
        dlg = resolve.ResolveDialog(self.repo, self)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()

    def thgimport(self, paths=None):
        dlg = thgimport.ImportDialog(repo=self.repo, parent=self)
        dlg.finished.connect(dlg.deleteLater)
        if paths:
            dlg.setfilepaths(paths)
        dlg.exec_()

    def verify(self):
        cmdline = ['--repository', self.repo.root, 'verify', '--verbose']
        dlg = cmdui.Dialog(cmdline, self)
        dlg.exec_()

    def recover(self):
        cmdline = ['--repository', self.repo.root, 'recover', '--verbose']
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
        cmdline = ['rollback', '--repository', self.repo.root, '--verbose']
        self.runCommand(_('Rollback - TortoiseHg'), cmdline)

    def purge(self):
        dlg = purge.PurgeDialog(self.repo, self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.showMessage.connect(self.showMessage)
        dlg.progress.connect(self.progress)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()

    @pyqtSlot(unicode, dict)
    def grep(self, pattern='', opts={}):
        """Open grep task tab"""
        opts = dict((str(k), str(v)) for k, v in opts.iteritems())
        self.taskTabsWidget.setCurrentIndex(self.grepTabIndex)
        self.grepDemand.setSearch(pattern, **opts)

    def setupModels(self):
        # Filter revision set in case revisions were removed
        self.revset = [r for r in self.revset if r in self.repo]
        self.repomodel = HgRepoListModel(self.repo, self.branch, self.revset,
                                         self.revsetfilter, self)
        self.repomodel.filled.connect(self.modelFilled)
        self.repomodel.loaded.connect(self.modelLoaded)
        self.repomodel.showMessage.connect(self.showMessage)
        self.repoview.setModel(self.repomodel)
        self.gototb.setCompletionKeys(self.repo.tags().keys())

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
        if type(rev) == str: # unapplied patch
            tw.setCurrentIndex(self.logTabIndex)
        elif rev is None:
            tw.setCurrentIndex(self.commitTabIndex)
        elif tw.currentWidget() in (self.commitDemand, self.syncDemand):
            tw.setCurrentIndex(self.logTabIndex)

    def revision_selected(self, rev):
        'View selection changed, could be a reload'
        if self.repomodel.graph is None:
            return
        if type(rev) == str: # unapplied patch
            # FIXME remove unapplied patch branch when
            # patches fully handled downstream
            self.revDetailsWidget.revision_selected(rev)
            # grep and manifest are unlikely to ever be able to use a
            # patch ctx
        else:
            self.revDetailsWidget.revision_selected(rev)
            self.manifestDemand.forward('setRev', rev)
            self.grepDemand.forward('setRevision', rev)

    def gotoParent(self):
        self.repoview.clearSelection()
        self.goto('.')

    def goto(self, rev):
        self._reload_rev = rev
        self.repoview.goto(rev)

    def revision_activated(self, rev=None):
        rev = rev or self.rev
        if isinstance(rev, basestring):  # unapplied patch
            return
        dlg = visdiff.visualdiff(self.repo.ui, self.repo, [], {'change':rev})
        if dlg:
            dlg.exec_()

    def reload(self):
        'Initiate a refresh of the repo model, rebuild graph'
        self.repo.thginvalidate()
        self.rebuildGraph()
        self.filterbar.refresh()
        if self.taskTabsWidget.currentIndex() == self.commitTabIndex:
            self.commitDemand.forward('reload')

    def rebuildGraph(self):
        self.showMessage('')
        if self.rev is None or len(self.repo) > self.rev:
            self._reload_rev = self.rev
        else:
            self._reload_rev = 'tip'
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
        elif tti == self.pbranchTabIndex:
            ttw = self.pbranchDemand.get()
        if ttw:
            ttw.reload()

    def refresh(self):
        'Refresh the repo model view, clear cached data'
        self.repo.thginvalidate()
        self.repomodel.invalidate()
        self.revDetailsWidget.reload()
        self.filterbar.refresh()

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
        self.updatePatchBranchTab()
        self.titleChanged.emit(self.title())
        # TODO: emit only if actually changed

    @pyqtSlot(unicode, bool)
    def setBranch(self, branch, allparents=True):
        'Change the branch filter'
        self.branch = branch
        self.repomodel.setBranch(branch=branch, allparents=allparents)
        self.titleChanged.emit(self.title())

    ##
    ## Workbench methods
    ##

    @pyqtSlot()
    def updateHistoryActions(self):
        'Update back / forward actions'
        self.workbench.actionBack.setEnabled(self.repoview.canGoBack())
        self.workbench.actionForward.setEnabled(self.repoview.canGoForward())

    def storeSettings(self):
        self.revDetailsWidget.storeSettings()
        s = QSettings()
        repoid = str(self.repo[0])
        s.setValue('repowidget/splitter-'+repoid,
                   self.repotabs_splitter.saveState())

    def restoreSettings(self):
        self.revDetailsWidget.restoreSettings()
        s = QSettings()
        repoid = str(self.repo[0])
        self.repotabs_splitter.restoreState(
            s.value('repowidget/splitter-'+repoid).toByteArray())

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
        self.filterbar.storeConfigs(s)
        return True

    def incoming(self):
        self.syncDemand.get().incoming()

    def pull(self):
        self.syncDemand.get().pull()

    def outgoing(self):
        self.syncDemand.get().outgoing()

    def push(self):
        self.syncDemand.get().push()

    def qpush(self):
        """QPush a patch from MQ"""
        cmdline = ['qpush',
                   '--repository', self.repo.root]
        self.runCommand(_('QPush - TortoiseHg'), cmdline)

    def qpop(self):
        """QPop a patch from MQ"""
        cmdline = ['qpop',
                   '--repository', self.repo.root]
        self.runCommand(_('QPop - TortoiseHg'), cmdline)

    ##
    ## Repoview context menu
    ##

    def viewMenuRequest(self, point, selection):
        'User requested a context menu in repo view widget'

        # selection is a list of the currently selected revisions.
        # Integers for changelog revisions, None for the working copy,
        # or strings for unapplied patches.

        if len(selection) == 0:
            return
        allunapp = False
        if 'mq' in self.repo.extensions():
            for rev in selection:
                if not self.repo.changectx(rev).thgmqunappliedpatch():
                    break
            else:
                allunapp = True
        if self.bundle:
            # Special menu for applied bundle
            menu = QMenu(self) # TODO: save in repowidget
            act = QAction(_('Pull to here'), self)
            act.triggered.connect(self.pullToRev)
            menu.addAction(act)
            menu.exec_(point)
            return
        elif allunapp:
            self.unnapliedPatchMenu(point, selection)
        elif len(selection) == 1:
            self.singleSelectionMenu(point, selection)
        elif len(selection) == 2:
            self.doubleSelectionMenu(point, selection)
        else:
            self.multipleSelectionMenu(point, selection)

    def unnapliedPatchMenu(self, point, selection):
        def qdeleteact():
            """Delete unapplied patch(es)"""
            patches = [self.repo.changectx(r).thgmqpatchname() \
                       for r in self.menuselection]
            dlg = qdelete.QDeleteDialog(self.repo, patches, self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.output.connect(self.output)
            dlg.makeLogVisible.connect(self.makeLogVisible)
            dlg.exec_()
        def qreorderact():
            dlg = qreorder.QReorderDialog(self.repo, self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.exec_()

        # Special menu for unapplied patches
        if not self.unappcmenu:
            menu = QMenu(self)
            acts = []
            for name, cb in (
                (_('Goto patch'), self.qgotoRevision),
                (_('Rename patch'), self.qrenameRevision),
                (_('Delete patches'), qdeleteact),
                (_('Reorder patches'), qreorderact)):
                act = QAction(name, self)
                act.triggered.connect(cb)
                acts.append(act)
                menu.addAction(act)
            self.unappcmenu = menu
            self.unappacts = acts
        self.menuselection = selection
        self.unappacts[0].setEnabled(len(selection) == 1)
        self.unappacts[1].setEnabled(len(selection) == 1)
        self.unappcmenu.exec_(point)

    def singleSelectionMenu(self, point, selection):
        if not self.singlecmenu:
            items = []

            # isrev = the changeset has an integer revision number
            # isctx = changectx or workingctx, not PatchContext
            # fixed = the changeset is considered permanent
            # patch = any patch applied or not
            # qpar  = patch queue parent
            isrev   = lambda ap, up, qp, wd: not (up or wd)
            isctx   = lambda ap, up, qp, wd: not up
            fixed   = lambda ap, up, qp, wd: not (ap or up or wd)
            patch   = lambda ap, up, qp, wd: ap or up
            qpar    = lambda ap, up, qp, wd: qp
            applied = lambda ap, up, qp, wd: ap
            unapp   = lambda ap, up, qp, wd: up

            exs = self.repo.extensions()
            menu = QMenu(self)
            for ext, func, desc, icon, cb in (
                (None, isrev, _('Update...'), 'update',
                    self.updateToRevision),
                (None, fixed, _('Merge with...'), 'merge',
                    self.mergeWithRevision),
                (None, isctx, _('Browse at rev...'), None,
                    self.manifestRevision),
                (None, fixed, _('Tag...'), 'tag', self.tagToRevision),
                ('bookmarks', fixed, _('Bookmark...'), 'bookmark',
                    self.bookmarkRevision),
                (None, fixed, _('Backout...'), None, self.backoutToRevision),
                (None, fixed, _('Push to here'), None, self.pushToRevision),
                (None, isrev, _('Export patch'), None, self.exportRevisions),
                (None, isrev, _('Email patch...'), None, self.emailRevision),
                (None, isrev, _('Archive...'), None, self.archiveRevision),
                (None, isrev, _('Copy hash'), None, self.copyHash),
                ('transplant', fixed, _('Transplant to local'), None,
                    self.transplantRevision),
                ('rebase', None, None, None, None),
                ('rebase', fixed, _('Rebase...'), None, self.rebaseRevision),
                ('mq', None, None, None, None),
                ('mq', fixed, _('Import to MQ'), None, self.qimportRevision),
                ('mq', applied, _('Finish patch'), None, self.qfinishRevision),
                ('mq', qpar, _('Pop all patches'), None, self.qpopAllRevision),
                ('mq', patch, _('Goto patch'), None, self.qgotoRevision),
                ('mq', patch, _('Rename patch'), None, self.qrenameRevision),
                ('mq', fixed, _('Strip...'), None, self.stripRevision),
                ('reviewboard', fixed, _('Post to Review Board...'),
                    'reviewboard', self.sendToReviewBoard)):
                if ext and ext not in exs:
                    continue
                if desc is None:
                    menu.addSeparator()
                else:
                    act = QAction(desc, self)
                    act.triggered.connect(cb)
                    if icon:
                        act.setIcon(geticon(icon))
                    act.enableFunc = func
                    menu.addAction(act)
                    items.append(act)
            self.singlecmenu = menu
            self.singlecmenuitems = items

        ctx = self.repo.changectx(self.rev)
        applied = ctx.thgmqappliedpatch()
        unapp = ctx.thgmqunappliedpatch()
        qparent = 'qparent' in ctx.tags()
        working = self.rev is None

        for item in self.singlecmenuitems:
            enabled = item.enableFunc(applied, unapp, qparent, working)
            item.setEnabled(enabled)

        self.singlecmenu.exec_(point)

    def exportRevisions(self, revisions):
        if not revisions:
            revisions = [self.rev]
        epath = os.path.join(self.repo.root, self.repo.shortname + '_%r.patch')
        cmdline = ['export', '--repository', self.repo.root, '--verbose',
                   '--output', epath]
        for rev in revisions:
            cmdline.extend(['--rev', str(rev)])
        self.runCommand(_('Export - TortoiseHg'), cmdline)

    def doubleSelectionMenu(self, point, selection):
        for r in selection:
            # No pair menu if working directory or unapplied patch
            if type(r) is not int:
                return
        def dagrange():
            revA, revB = self.menuselection
            if revA > revB:
                B, A = self.menuselection
            else:
                A, B = self.menuselection
            func = revset.match('%s::%s' % (A, B))
            return [c for c in func(self.repo, range(len(self.repo)))]

        def exportPair():
            self.exportRevisions(self.menuselection)
        def exportDagRange():
            l = dagrange()
            if l:
                self.exportRevisions(l)
        def diffPair():
            revA, revB = self.menuselection
            dlg = visdiff.visualdiff(self.repo.ui, self.repo, [],
                    {'rev':(str(revA), str(revB))})
            if dlg:
                dlg.exec_()
        def emailPair():
            run.email(self.repo.ui, rev=self.menuselection, repo=self.repo)
        def emailDagRange():
            l = dagrange()
            if l:
                run.email(self.repo.ui, rev=l, repo=self.repo)
        def bisectNormal():
            revA, revB = self.menuselection
            opts = {'good':str(revA), 'bad':str(revB)}
            dlg = bisect.BisectDialog(self.repo, opts, self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.exec_()
        def bisectReverse():
            revA, revB = self.menuselection
            opts = {'good':str(revB), 'bad':str(revA)}
            dlg = bisect.BisectDialog(self.repo, opts, self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.exec_()
        def compressDlg():
            ctxa = self.repo[self.menuselection[0]]
            ctxb = self.repo[self.menuselection[1]]
            if ctxa.ancestor(ctxb) == ctxb:
                revs = self.menuselection[:]
            elif ctxa.ancestor(ctxb) == ctxa:
                revs = self.menuselection[:]
                revs.reverse()
            else:
                InfoMsgBox(_('Unable to compress history'),
                           _('Selected changeset pair not related'))
                return
            dlg = compress.CompressDialog(self.repo, revs, self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.exec_()


        if not self.paircmenu:
            menu = QMenu(self)
            for name, cb in (
                    (_('Visual Diff...'), diffPair),
                    (_('Export Pair'), exportPair),
                    (_('Email Pair...'), emailPair),
                    (_('Export DAG Range'), exportDagRange),
                    (_('Email DAG Range...'), emailDagRange),
                    (_('Bisect - Good, Bad...'), bisectNormal),
                    (_('Bisect - Bad, Good...'), bisectReverse),
                    (_('Compress History...'), compressDlg)
                    ):
                a = QAction(name, self)
                a.triggered.connect(cb)
                menu.addAction(a)
            if 'reviewboard' in self.repo.extensions():
                a = QAction(_('Post Pair to Review Board...'), self)
                a.triggered.connect(self.sendToReviewBoard)
                menu.addAction(a)
            self.paircmenu = menu
        self.menuselection = selection
        self.paircmenu.exec_(point)

    def multipleSelectionMenu(self, point, selection):
        for r in selection:
            # No multi menu if working directory or unapplied patch
            if type(r) is not int:
                return
        def exportSel():
            self.exportRevisions(self.menuselection)
        def emailSel():
            run.email(self.repo.ui, rev=self.menuselection, repo=self.repo)
        if not self.multicmenu:
            menu = QMenu(self)
            for name, cb in (
                    (_('Export Selected'), exportSel),
                    (_('Email Selected...'), emailSel),
                    ):
                a = QAction(name, self)
                a.triggered.connect(cb)
                menu.addAction(a)
            if 'reviewboard' in self.repo.extensions():
                a = QAction(_('Post Selected to Review Board...'), self)
                a.triggered.connect(self.sendToReviewBoard)
                menu.addAction(a)
            self.multicmenu = menu
        self.menuselection = selection
        self.multicmenu.exec_(point)

    def updateToRevision(self):
        dlg = update.UpdateDialog(self.repo, self.rev, self)
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
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()

    def bookmarkRevision(self):
        dlg = bookmark.BookmarkDialog(self.repo, str(self.rev), self)
        dlg.showMessage.connect(self.showMessage)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()

    def transplantRevision(self):
        cmdline = ['transplant', '--repository', self.repo.root, str(self.rev)]
        self.runCommand(_('Transplant - TortoiseHg'), cmdline)

    def pushToRevision(self):
        self.taskTabsWidget.setCurrentIndex(self.syncTabIndex)
        self.syncDemand.pushToRevision(self.rev)

    def backoutToRevision(self):
        dlg = backout.BackoutDialog(self.repo, str(self.rev), self)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()

    def stripRevision(self):
        'Strip the selected revision and all descendants'
        dlg = thgstrip.StripDialog(self.repo, rev=str(self.rev), parent=self)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()

    def sendToReviewBoard(self):
        run.postreview(self.repo.ui, rev=self.repoview.selectedRevisions(),
          repo=self.repo)

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
        opts = {'source' : self.rev, 'dest': self.repo['.'].rev()}
        dlg = rebase.RebaseDialog(self.repo, self, **opts)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()

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

    def qpopAllRevision(self):
        """Unapply all patches"""
        cmdline = ['qpop', '--all',
                   '--repository', self.repo.root]
        self.runCommand(_('QPop All - TortoiseHg'), cmdline)

    def qgotoRevision(self):
        """Make REV the top applied patch"""
        patchname = self.repo.changectx(self.rev).thgmqpatchname()
        cmdline = ['qgoto', str(patchname),  # FIXME force option
                   '--repository', self.repo.root]
        self.runCommand(_('QGoto - TortoiseHg'), cmdline)

    def qrenameRevision(self):
        """Rename the selected MQ patch"""
        patchname = self.repo.changectx(self.rev).thgmqpatchname()
        dlg = qrename.QRenameDialog(self.repo, patchname, self)
        dlg.finished.connect(dlg.deleteLater)
        dlg.output.connect(self.output)
        dlg.makeLogVisible.connect(self.makeLogVisible)
        dlg.exec_()

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

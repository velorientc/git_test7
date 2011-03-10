# repowidget.py - TortoiseHg repository widget
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
# Copyright (C) 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

import binascii
import os

from mercurial import util, revset, error

from tortoisehg.util import shlib, hglib

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib
from tortoisehg.hgqt.qtlib import QuestionMsgBox, InfoMsgBox
from tortoisehg.hgqt.qtlib import CustomPrompt, SharedWidget, DemandWidget
from tortoisehg.hgqt.repomodel import HgRepoListModel
from tortoisehg.hgqt import cmdui, update, tag, backout, merge, visdiff
from tortoisehg.hgqt import archive, thgimport, thgstrip, run, purge, bookmark
from tortoisehg.hgqt import bisect, rebase, resolve, thgrepo, compress, mq
from tortoisehg.hgqt import qdelete, qreorder, qfold, shelve

from tortoisehg.hgqt.repofilter import RepoFilterBar
from tortoisehg.hgqt.repoview import HgRepoView
from tortoisehg.hgqt.revdetails import RevDetailsWidget
from tortoisehg.hgqt.commit import CommitWidget
from tortoisehg.hgqt.manifestdialog import ManifestTaskWidget
from tortoisehg.hgqt.sync import SyncWidget
from tortoisehg.hgqt.grep import SearchWidget
from tortoisehg.hgqt.pbranch import PatchBranchWidget

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class RepoWidget(QWidget):

    showMessageSignal = pyqtSignal(QString)
    closeSelfSignal = pyqtSignal(QWidget)
    toolbarVisibilityChanged = pyqtSignal()

    output = pyqtSignal(QString, QString)
    progress = pyqtSignal(QString, object, QString, QString, object)
    makeLogVisible = pyqtSignal(bool)

    revisionSelected = pyqtSignal(object)

    titleChanged = pyqtSignal(unicode)
    """Emitted when changed the expected title for the RepoWidget tab"""

    repoLinkClicked = pyqtSignal(unicode)
    """Emitted when clicked a link to open repository"""

    def __init__(self, repo, parent=None):
        QWidget.__init__(self, parent, acceptDrops=True)

        self.repo = repo
        repo.repositoryChanged.connect(self.repositoryChanged)
        repo.repositoryDestroyed.connect(self.repositoryDestroyed)
        repo.configChanged.connect(self.configChanged)
        self.revsetfilter = False
        self.branch = ''
        self.bundle = None
        self.revset = set()
        self.namedTabs = {}
        self.repolen = len(repo)
        self.destroyed.connect(self.repo.thginvalidate)

        if repo.parents()[0].rev() == -1:
            self._reload_rev = 'tip'
        else:
            self._reload_rev = '.'
        self.currentMessage = ''
        self.dirty = False

        self.setupUi()
        self.createActions()
        self.loadSettings()
        self.setupModels()

        self.runner = cmdui.Runner(False, self)
        self.runner.output.connect(self.output)
        self.runner.progress.connect(self.progress)
        self.runner.makeLogVisible.connect(self.makeLogVisible)
        self.runner.commandFinished.connect(self.onCommandFinished)

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
        hbox.addWidget(self.filterbar)

        self.filterbar.branchChanged.connect(self.setBranch)
        self.filterbar.progress.connect(self.progress)
        self.filterbar.showMessage.connect(self.showMessage)
        self.filterbar.setRevisionSet.connect(self.setRevisionSet)
        self.filterbar.clearRevisionSet.connect(self.clearRevisionSet)
        self.filterbar.filterToggled.connect(self.filterToggled)
        self.filterbar.hide()
        self.revsetfilter = self.filterbar.filtercb.isChecked()

        self.layout().addWidget(self.repotabs_splitter)

        self.repoview = view = HgRepoView(self.repo, 'repoWidget', self)
        view.revisionClicked.connect(self.onRevisionClicked)
        view.revisionSelected.connect(self.onRevisionSelected)
        view.revisionAltClicked.connect(self.onRevisionSelected)
        view.revisionActivated.connect(self.onRevisionActivated)
        view.showMessage.connect(self.showMessage)
        view.menuRequested.connect(self.viewMenuRequest)

        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(1)
        sp.setHeightForWidth(self.repoview.sizePolicy().hasHeightForWidth())
        view.setSizePolicy(sp)
        view.setFrameShape(QFrame.StyledPanel)

        self.repotabs_splitter.addWidget(self.repoview)
        self.repotabs_splitter.setCollapsible(0, True)
        self.repotabs_splitter.setStretchFactor(0, 1)

        self.taskTabsWidget = tt = QTabWidget()
        self.repotabs_splitter.addWidget(self.taskTabsWidget)
        self.repotabs_splitter.setStretchFactor(1, 1)
        tt.setDocumentMode(True)
        self.updateTaskTabs()

        self.revDetailsWidget = w = RevDetailsWidget(self.repo)
        w.linkActivated.connect(self._openLink)
        w.revisionSelected.connect(self.repoview.goto)
        w.grepRequested.connect(self.grep)
        w.showMessage.connect(self.showMessage)
        w.updateToRevision.connect(lambda rev: self.updateToRevision())
        self.logTabIndex = idx = tt.addTab(w, qtlib.geticon('hg-log'), '')
        tt.setTabToolTip(idx, _("Revision details"))

        self.commitDemand = w = DemandWidget(self.createCommitWidget)
        self.commitTabIndex = idx = tt.addTab(w, qtlib.geticon('hg-commit'), '')
        tt.setTabToolTip(idx, _("Commit"))

        self.syncDemand = w = DemandWidget(self.createSyncWidget)
        self.syncTabIndex = idx = tt.addTab(w, qtlib.geticon('thg-sync'), '')
        tt.setTabToolTip(idx, _("Synchronize"))

        self.manifestDemand = w = DemandWidget(self.createManifestWidget)
        self.manifestTabIndex = idx = tt.addTab(w, qtlib.geticon('hg-annotate'), '')
        tt.setTabToolTip(idx, _('Manifest'))

        self.grepDemand = w = DemandWidget(self.createGrepWidget)
        self.grepTabIndex = idx = tt.addTab(w, qtlib.geticon('hg-grep'), '')
        tt.setTabToolTip(idx, _("Search"))

        self.mqDemand = w = DemandWidget(self.createMQWidget)
        if 'mq' in self.repo.extensions():
            self.mqTabIndex = idx = tt.addTab(w, qtlib.geticon('thg-mq'), '')
            tt.setTabToolTip(idx, _("Patch Queue"))
            self.namedTabs['mq'] = idx
        else:
            self.mqTabIndex = -1

        self.pbranchDemand = w = DemandWidget(self.createPatchBranchWidget)
        if 'pbranch' in self.repo.extensions():
            self.pbranchTabIndex = idx = tt.addTab(w, qtlib.geticon('branch'), '')
            tt.setTabToolTip(idx, _("Patch Branch"))
            self.namedTabs['pbranch'] = idx
        else:
            self.pbranchTabIndex = -1

    def switchToNamedTaskTab(self, tabname):
        if tabname in self.namedTabs:
            idx = self.namedTabs[tabname]
            self.taskTabsWidget.setCurrentIndex(idx)

    def title(self):
        """Returns the expected title for this widget [unicode]"""
        if self.bundle:
            return _('%s <incoming>') % self.repo.shortname
        elif self.branch:
            return '%s [%s]' % (self.repo.shortname, self.branch)
        else:
            return self.repo.shortname

    def filterBarVisible(self):
        return self.filterbar.isVisible()

    @pyqtSlot(bool)
    def toggleFilterBar(self, checked):
        """Toggle display repowidget filter bar"""
        self.filterbar.setVisible(checked)

    @pyqtSlot(unicode)
    def _openLink(self, link):
        link = unicode(link)
        handlers = {'cset': self.goto,
                    'subrepo': self.repoLinkClicked.emit,
                    'shelve' : self.shelve}
        if ':' in link:
            scheme, param = link.split(':', 1)
            hdr = handlers.get(scheme)
            if hdr:
                return hdr(param)

        QDesktopServices.openUrl(QUrl(link))

    def getCommitWidget(self):
        return getattr(self.repo, '_commitwidget', None)  # TODO: ugly

    def createCommitWidget(self):
        cw = self.getCommitWidget()
        if not cw:
            pats = {}
            opts = {}
            b = QPushButton(_('Commit'))
            b.setAutoDefault(True)
            f = b.font()
            f.setWeight(QFont.Bold)
            b.setFont(f)
            cw = CommitWidget(pats, opts, self.repo.root, True, self)
            cw.buttonHBox.addWidget(b)
            cw.commitButtonEnable.connect(b.setEnabled)
            b.clicked.connect(cw.commit)
            cw.loadSettings(QSettings(), 'workbench')
            QTimer.singleShot(0, cw.reload)
            self.repo._commitwidget = cw

        cw = SharedWidget(cw)
        cw.output.connect(self.output)
        cw.progress.connect(self.progress)
        cw.makeLogVisible.connect(self.makeLogVisible)
        cw.linkActivated.connect(self._openLink)

        cw.showMessage.connect(self.showMessage)
        return cw

    def createManifestWidget(self):
        if isinstance(self.rev, basestring):
            rev = None
        else:
            rev = self.rev
        w = ManifestTaskWidget(self.repo, rev, self)
        w.loadSettings(QSettings(), 'workbench')
        w.revChanged.connect(self.repoview.goto)
        w.revisionHint.connect(self.showMessage)
        w.grepRequested.connect(self.grep)
        return w

    def createSyncWidget(self):
        sw = getattr(self.repo, '_syncwidget', None)  # TODO: ugly
        if not sw:
            sw = SyncWidget(self.repo, self)
            self.repo._syncwidget = sw
        sw = SharedWidget(sw)
        sw.output.connect(self.output)
        sw.progress.connect(self.progress)
        sw.makeLogVisible.connect(self.makeLogVisible)
        sw.outgoingNodes.connect(self.setOutgoingNodes)
        sw.showMessage.connect(self.showMessage)
        sw.incomingBundle.connect(self.setBundle)
        sw.refreshTargets(self.rev)
        return sw

    @pyqtSlot(QString)
    def setBundle(self, bfile):
        if self.bundle:
            self.clearBundle()
        self.bundle = hglib.fromunicode(bfile)
        oldlen = len(self.repo)
        self.repo = thgrepo.repository(self.repo.ui, self.repo.root,
                                       bundle=self.bundle)
        self.repoview.setRepo(self.repo)
        self.revDetailsWidget.setRepo(self.repo)
        self.manifestDemand.forward('setRepo', self.repo)
        self.bundleAccept.setHidden(False)
        self.bundleReject.setHidden(False)
        self.filterbar.revsetle.setText('incoming()')
        self.filterbar.setEnableFilter(False)
        self.filterbar.show()
        self.toolbarVisibilityChanged.emit()
        self.titleChanged.emit(self.title())
        newlen = len(self.repo)
        self.revset = range(oldlen, newlen)
        self.repomodel.revset = self.revset
        self.reload()
        self.repoview.resetBrowseHistory(self.revset)
        self._reload_rev = self.revset[0]

    def clearBundle(self):
        self.bundleAccept.setHidden(True)
        self.bundleReject.setHidden(True)
        self.filterbar.setEnableFilter(True)
        self.filterbar.revsetle.setText('')
        self.revset = []
        self.repomodel.revset = self.revset
        self.bundle = None
        self.titleChanged.emit(self.title())
        self.repo = thgrepo.repository(self.repo.ui, self.repo.root)
        self.repoview.setRepo(self.repo)
        self.revDetailsWidget.setRepo(self.repo)
        self.manifestDemand.forward('setRepo', self.repo)

    def acceptBundle(self):
        self.taskTabsWidget.setCurrentIndex(self.syncTabIndex)
        self.syncDemand.pullBundle(self.bundle, None)
        self.clearBundle()

    def pullBundleToRev(self):
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

    def clearRevisionSet(self):
        if not self.revset:
            return
        self.revset = []
        if self.revsetfilter:
            self.reload()
        else:
            self.repomodel.revset = []
            self.refresh()

    def setRevisionSet(self, revisions):
        revs = revisions[:]
        revs.sort(reverse=True)
        self.revset = revs
        if self.revsetfilter:
            self.reload()
        else:
            self.repomodel.revset = self.revset
            self.refresh()
        self.repoview.resetBrowseHistory(self.revset)
        self._reload_rev = self.revset[0]

    @pyqtSlot(bool)
    def filterToggled(self, checked):
        self.revsetfilter = checked
        if self.revset:
            self.repomodel.filterbyrevset = checked
            self.reload()
            self.repoview.resetBrowseHistory(self.revset)
            self._reload_rev = self.revset[0]

    def setOutgoingNodes(self, nodes):
        self.filterbar.revsetle.setText('outgoing()')
        self.filterbar.show()
        self.toolbarVisibilityChanged.emit()
        self.setRevisionSet([self.repo[n].rev() for n in nodes])

    def createGrepWidget(self):
        upats = {}
        gw = SearchWidget(upats, self.repo, self)
        gw.setRevision(self.repoview.current_rev)
        gw.showMessage.connect(self.showMessage)
        gw.progress.connect(self.progress)
        gw.revisionSelected.connect(self.goto)
        return gw

    def createMQWidget(self):
        mqw = mq.MQWidget(self.repo, self)
        mqw.output.connect(self.output)
        mqw.progress.connect(self.progress)
        mqw.makeLogVisible.connect(self.makeLogVisible)
        mqw.showMessage.connect(self.showMessage)
        return mqw

    def createPatchBranchWidget(self):
        pbw = PatchBranchWidget(self.repo, parent=self)
        pbw.output.connect(self.output)
        pbw.progress.connect(self.progress)
        pbw.makeLogVisible.connect(self.makeLogVisible)
        return pbw

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
        self.generateSingleMenu()
        self.generatePairMenu()
        self.generateUnappliedPatchMenu()
        self.generateMultipleSelectionMenu()
        self.generateBundleMenu()

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

    ## Begin Workbench event forwards

    def back(self):
        self.repoview.back()

    def forward(self):
        self.repoview.forward()

    def bisect(self):
        dlg = bisect.BisectDialog(self.repo, {}, self)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()

    def resolve(self):
        dlg = resolve.ResolveDialog(self.repo, self)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()

    def thgimport(self, paths=None):
        dlg = thgimport.ImportDialog(self.repo, self)
        dlg.finished.connect(dlg.deleteLater)
        dlg.patchImported.connect(self.gotoTip)
        if paths:
            dlg.setfilepaths(paths)
        dlg.exec_()

    def shelve(self, arg=None):
        dlg = shelve.ShelveDialog(self.repo, self)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()

    def verify(self):
        cmdline = ['--repository', self.repo.root, 'verify', '--verbose']
        dlg = cmdui.Dialog(cmdline, self)
        dlg.setWindowIcon(qtlib.geticon('hg-verify'))
        dlg.setWindowTitle(_('%s - verify repository') % self.repo.shortname)
        dlg.exec_()

    def recover(self):
        cmdline = ['--repository', self.repo.root, 'recover', '--verbose']
        dlg = cmdui.Dialog(cmdline, self)
        dlg.setWindowIcon(qtlib.geticon('hg-recover'))
        dlg.setWindowTitle(_('%s - recover repository') % self.repo.shortname)
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
        self.runCommand(cmdline)

    def purge(self):
        dlg = purge.PurgeDialog(self.repo, self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.showMessage.connect(self.showMessage)
        dlg.progress.connect(self.progress)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()

    ## End workbench event forwards

    @pyqtSlot(unicode, dict)
    def grep(self, pattern='', opts={}):
        """Open grep task tab"""
        opts = dict((str(k), str(v)) for k, v in opts.iteritems())
        self.taskTabsWidget.setCurrentIndex(self.grepTabIndex)
        self.grepDemand.setSearch(pattern, **opts)

    def setupModels(self):
        # Filter revision set in case revisions were removed
        self.revset = [r for r in self.revset if r < len(self.repo)]
        self.repomodel = HgRepoListModel(self.repo, self.branch, self.revset,
                                         self.revsetfilter, self)
        self.repomodel.filled.connect(self.modelFilled)
        self.repomodel.loaded.connect(self.modelLoaded)
        self.repomodel.showMessage.connect(self.showMessage)
        self.repoview.setModel(self.repomodel)
        try:
            self._last_series = self.repo.mq.series[:]
        except AttributeError:
            self._last_series = []

    def modelFilled(self):
        'initial batch of revisions loaded'
        self.repoview.goto(self._reload_rev) # emits revisionSelected
        self.repoview.resizeColumns()

    def modelLoaded(self):
        'all revisions loaded (graph generator completed)'
        # Perhaps we can update a GUI element later, to indicate full load
        pass

    def onRevisionClicked(self, rev):
        'User clicked on a repoview row'
        tw = self.taskTabsWidget
        if rev is None:
            # Clicking on working copy switches to commit tab
            tw.setCurrentIndex(self.commitTabIndex)
        else:
            # Clicking on a normal revision switches from commit tab
            tw.setCurrentIndex(self.logTabIndex)

    def onRevisionSelected(self, rev):
        'View selection changed, could be a reload'
        self.showMessage('')
        if self.repomodel.graph is None:
            return
        try:
            self.revDetailsWidget.onRevisionSelected(rev)
            self.revisionSelected.emit(rev)
            if type(rev) != str: # unapplied patch
                self.manifestDemand.forward('setRev', rev)
                self.grepDemand.forward('setRevision', rev)
                self.syncDemand.forward('refreshTargets', rev)
            else:
                self.manifestDemand.forward('setRev', None)
        except (IndexError, error.RevlogError, error.Abort), e:
            self.showMessage(hglib.tounicode(str(e)))

    def gotoParent(self):
        self.repoview.clearSelection()
        self.goto('.')

    def gotoTip(self):
        self.repoview.clearSelection()
        self.goto('tip')

    def goto(self, rev):
        self._reload_rev = rev
        self.repoview.goto(rev)

    def onRevisionActivated(self, rev):
        qgoto = False
        if isinstance(rev, basestring):
            qgoto = True
        else:
            ctx = self.repo.changectx(rev)
            if 'qparent' in ctx.tags() or ctx.thgmqappliedpatch():
                qgoto = True
            if 'qtip' in ctx.tags():
                qgoto = False
        if qgoto:
            self.qgotoRevision()
        else:
            self.visualDiffRevision()

    def reload(self):
        'Initiate a refresh of the repo model, rebuild graph'
        self.repo.thginvalidate()
        self.rebuildGraph()
        self.reloadTaskTab()

    def rebuildGraph(self):
        'Called by repositoryChanged signals, and during reload'
        self.showMessage('')

        if len(self.repo) < self.repolen:
            # repo has been stripped, invalidate active revision sets
            if self.bundle:
                self.clearBundle()
                self.showMessage(_('Repository stripped, incoming preview '
                                   'cleared'))
            elif self.revset:
                self.revset = []
                self.filterbar.revsetle.setText('')
                self.showMessage(_('Repository stripped, revision set cleared'))
        if not self.bundle:
            self.repolen = len(self.repo)

        self._reload_rev = self.rev
        if self.rev is None:
            pass
        elif type(self.rev) is str:
            try:
                if self.rev not in self.repo.mq.series:
                    # patch is no longer in the series, find a neighbor
                    idx = self._last_series.index(self._reload_rev) - 1
                    self._reload_rev = self._last_series[idx]
                    while self._reload_rev not in self.repo.mq.series and idx:
                        idx -= 1
                        self._reload_rev = self._last_series[idx]
            except (AttributeError, IndexError):
                self._reload_rev = 'tip'
        elif len(self.repo) <= self.rev:
            self._reload_rev = 'tip'

        self.setupModels()
        self.filterbar.refresh()
        self.repoview.saveSettings()

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
        elif tti == self.mqTabIndex:
            ttw = self.mqDemand.get()
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
            try:
                self.rebuildGraph()
            except (error.RevlogError, error.RepoError), e:
                self.showMessage(hglib.tounicode(str(e)))
                self.repomodel = HgRepoListModel(None, None, None, False, self)
                self.repoview.setModel(self.repomodel)
        else:
            self.dirty = True

    def configChanged(self):
        'Repository is reporting its config files have changed'
        self.repomodel.invalidate()
        self.revDetailsWidget.reload()
        self.titleChanged.emit(self.title())
        self.updateTaskTabs()

    def updateTaskTabs(self):
        val = self.repo.ui.config('tortoisehg', 'tasktabs', 'off').lower()
        if val == 'east':
            self.taskTabsWidget.setTabPosition(QTabWidget.East)
            self.taskTabsWidget.tabBar().show()
        elif val == 'west':
            self.taskTabsWidget.setTabPosition(QTabWidget.West)
            self.taskTabsWidget.tabBar().show()
        else:
            self.taskTabsWidget.tabBar().hide()

    @pyqtSlot(unicode, bool)
    def setBranch(self, branch, allparents=True):
        'Change the branch filter'
        self.branch = branch
        self.repomodel.setBranch(branch=branch, allparents=allparents)
        self.titleChanged.emit(self.title())

    ##
    ## Workbench methods
    ##

    def canGoBack(self):
        return self.repoview.canGoBack()

    def canGoForward(self):
        return self.repoview.canGoForward()

    def loadSettings(self):
        s = QSettings()
        repoid = str(self.repo[0])
        self.revDetailsWidget.loadSettings(s)
        self.filterbar.loadSettings(s)
        self.repotabs_splitter.restoreState(
            s.value('repowidget/splitter-'+repoid).toByteArray())

    def okToContinue(self):
        if not self.commitDemand.forward('canExit', default=True):
            self.taskTabsWidget.setCurrentIndex(self.commitTabIndex)
            self.showMessage(_('Commit tab cannot exit'))
            return False
        if not self.syncDemand.forward('canExit', default=True):
            self.taskTabsWidget.setCurrentIndex(self.syncTabIndex)
            self.showMessage(_('Sync tab cannot exit'))
            return False
        if not self.mqDemand.forward('canExit', default=True):
            self.taskTabsWidget.setCurrentIndex(self.mqTabIndex)
            self.showMessage(_('MQ tab cannot exit'))
            return False
        if not self.grepDemand.forward('canExit', default=True):
            self.taskTabsWidget.setCurrentIndex(self.grepTabIndex)
            self.showMessage(_('Search tab cannot exit'))
            return False
        if self.runner.core.running():
            self.showMessage(_('Repository command still running'))
            return False
        return True

    def closeRepoWidget(self):
        '''returns False if close should be aborted'''
        if not self.okToContinue():
            return False
        s = QSettings()
        if self.isVisible():
            repoid = str(self.repo[0])
            s.setValue('repowidget/splitter-'+repoid,
                       self.repotabs_splitter.saveState())
        self.revDetailsWidget.saveSettings(s)
        self.commitDemand.forward('saveSettings', s, 'workbench')
        self.manifestDemand.forward('saveSettings', s, 'workbench')
        self.grepDemand.forward('saveSettings', s)
        self.filterbar.saveSettings(s)
        self.repoview.saveSettings(s)
        return True

    def incoming(self):
        self.taskTabsWidget.setCurrentIndex(self.syncTabIndex)
        self.syncDemand.get().incoming()

    def pull(self):
        self.taskTabsWidget.setCurrentIndex(self.syncTabIndex)
        self.syncDemand.get().pull()

    def outgoing(self):
        self.taskTabsWidget.setCurrentIndex(self.syncTabIndex)
        self.syncDemand.get().outgoing()

    def push(self):
        self.taskTabsWidget.setCurrentIndex(self.syncTabIndex)
        self.syncDemand.get().push()

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

        if self.bundle:
            if len(selection) == 1:
                self.bundlemenu.exec_(point)
            return

        self.menuselection = selection
        allunapp = False
        if 'mq' in self.repo.extensions():
            for rev in selection:
                if not self.repo.changectx(rev).thgmqunappliedpatch():
                    break
            else:
                allunapp = True
        if allunapp:
            self.unappliedPatchMenu(point, selection)
        elif len(selection) == 1:
            self.singleSelectionMenu(point, selection)
        elif len(selection) == 2:
            self.doubleSelectionMenu(point, selection)
        else:
            self.multipleSelectionMenu(point, selection)

    def singleSelectionMenu(self, point, selection):
        ctx = self.repo.changectx(self.rev)
        applied = ctx.thgmqappliedpatch()
        working = self.rev is None
        tags = ctx.tags()

        for item in self.singlecmenuitems:
            enabled = item.enableFunc(applied, working, tags)
            item.setEnabled(enabled)

        self.singlecmenu.exec_(point)

    def doubleSelectionMenu(self, point, selection):
        for r in selection:
            # No pair menu if working directory or unapplied patch
            if type(r) is not int:
                return
        self.paircmenu.exec_(point)

    def multipleSelectionMenu(self, point, selection):
        for r in selection:
            # No multi menu if working directory or unapplied patch
            if type(r) is not int:
                return
        self.multicmenu.exec_(point)

    def unappliedPatchMenu(self, point, selection):
        q = self.repo.mq
        ispushable = False
        unapplied = 0
        for i in xrange(q.series_end(), len(q.series)):
            pushable, reason = q.pushable(i)
            if pushable:
                if unapplied == 0:
                    qnext = q.series[i]
                if self.rev == q.series[i]:
                    ispushable = True
                unapplied += 1
        self.unappacts[0].setEnabled(ispushable and len(selection) == 1)
        self.unappacts[1].setEnabled(ispushable and len(selection) == 1 and \
                                     self.rev != qnext)
        self.unappacts[2].setEnabled('qtip' in self.repo.tags())
        self.unappacts[3].setEnabled(True)
        self.unappacts[4].setEnabled(unapplied > 1)
        self.unappcmenu.exec_(point)

    def generateSingleMenu(self):
        items = []

        # This menu will never be opened for an unapplied patch, they
        # have their own menu.
        #
        # isrev = the changeset has an integer revision number
        # isctx = changectx or workingctx
        # fixed = the changeset is considered permanent
        # applid = an applied patch
        # qgoto = applied patch or qparent
        isrev   = lambda ap, wd, tags: not wd
        isctx   = lambda ap, wd, tags: True
        fixed   = lambda ap, wd, tags: not (ap or wd)
        applied = lambda ap, wd, tags: ap
        qgoto   = lambda ap, wd, tags: ('qparent' in tags) or \
                                       (ap and ('qtip' not in tags))

        exs = self.repo.extensions()

        def entry(menu, ext=None, func=None, desc=None, icon=None, cb=None):
            if ext and ext not in exs:
                return
            if desc is None:
                menu.addSeparator()
                return
            act = QAction(desc, self)
            act.triggered.connect(cb)
            if icon:
                act.setIcon(qtlib.getmenuicon(icon))
            act.enableFunc = func
            menu.addAction(act)
            items.append(act)

        menu = QMenu(self)

        entry(menu, None, isrev, _('Update...'), 'hg-update',
              self.updateToRevision)
        entry(menu)
        entry(menu, None, isctx, _('Visual diff...'), 'visualdiff',
              self.visualDiffRevision)
        entry(menu, None, isrev, _('Diff to local...'), 'ldiff',
              self.visualDiffToLocal)
        entry(menu, None, isctx, _('Browse at rev...'), 'hg-annotate',
              self.manifestRevision)
        entry(menu)
        entry(menu, None, fixed, _('Merge with local...'), 'hg-merge',
              self.mergeWithRevision)
        entry(menu)
        entry(menu, None, fixed, _('Tag...'), 'hg-tag',
              self.tagToRevision)
        entry(menu, None, fixed, _('Bookmark...'), 'hg-bookmarks',
              self.bookmarkRevision)
        entry(menu)
        entry(menu, None, fixed, _('Backout...'), 'hg-revert',
              self.backoutToRevision)
        entry(menu)

        submenu = menu.addMenu(_('Export'))
        entry(submenu, None, isrev, _('Export patch...'), 'hg-export',
              self.exportRevisions)
        entry(submenu, None, isrev, _('Email patch...'), 'mail-forward',
              self.emailRevision)
        entry(submenu, None, isrev, _('Archive...'), 'hg-archive',
              self.archiveRevision)
        entry(submenu, None, isctx, _('Copy patch'), 'copy-patch',
              self.copyPatch)
        entry(menu)

        entry(menu, None, isrev, _('Copy hash'), 'copy-hash',
              self.copyHash)
        entry(menu)

        entry(menu, 'transplant', fixed, _('Transplant to local'), 'hg-transplant',
              self.transplantRevision)

        if 'mq' in exs or 'rebase' in exs:
            submenu = menu.addMenu(_('Modify history'))
            entry(submenu, 'mq', qgoto, _('QGoto'), 'hg-qgoto',
                  self.qgotoRevision)
            entry(submenu, 'mq', fixed, _('Import to MQ'), 'qimport',
                  self.qimportRevision)
            entry(submenu, 'mq', applied, _('Finish patch'), 'qfinish',
                  self.qfinishRevision)
            entry(submenu, 'mq')
            entry(submenu, 'rebase', fixed, _('Rebase...'), 'hg-rebase',
                  self.rebaseRevision)
            entry(submenu, 'rebase')
            entry(submenu, 'mq', fixed, _('Strip...'), 'menudelete',
                  self.stripRevision)

        entry(menu, 'reviewboard', fixed, _('Post to Review Board...'), 'reviewboard',
              self.sendToReviewBoard)

        self.singlecmenu = menu
        self.singlecmenuitems = items

    def generatePairMenu(self):
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

        menu = QMenu(self)
        for name, cb, icon in (
                (_('Visual Diff...'), diffPair, 'visualdiff'),
                (_('Export Selected...'), exportPair, 'hg-export'),
                (_('Email Selected...'), emailPair, 'mail-forward'),
                (_('Export DAG Range...'), exportDagRange, 'hg-export'),
                (_('Email DAG Range...'), emailDagRange, 'mail-forward'),
                (_('Bisect - Good, Bad...'), bisectNormal, 'hg-bisect-good-bad'),
                (_('Bisect - Bad, Good...'), bisectReverse, 'hg-bisect-bad-good'),
                (_('Compress History...'), compressDlg, 'hg-compress')
                ):
            a = QAction(name, self)
            if icon:
                a.setIcon(qtlib.getmenuicon(icon))
            a.triggered.connect(cb)
            menu.addAction(a)
        if 'reviewboard' in self.repo.extensions():
            a = QAction(_('Post Pair to Review Board...'), self)
            a.triggered.connect(self.sendToReviewBoard)
            menu.addAction(a)
        self.paircmenu = menu

    def generateUnappliedPatchMenu(self):
        def qdeleteact():
            """Delete unapplied patch(es)"""
            dlg = qdelete.QDeleteDialog(self.repo, self.menuselection, self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.output.connect(self.output)
            dlg.makeLogVisible.connect(self.makeLogVisible)
            dlg.exec_()
        def qreorderact():
            def checkGuardsOrComments():
                cont = True
                for p in self.repo.mq.full_series:
                    if '#' in p:
                        cont = QuestionMsgBox('Confirm qreorder',
                                _('<p>ATTENTION!<br>'
                                  'Guard or comment found.<br>'
                                  'Reordering patches will destroy them.<br>'
                                  '<br>Continue?</p>'), parent=self,
                                  defaultbutton=QMessageBox.No)
                        break
                return cont
            if checkGuardsOrComments():
                dlg = qreorder.QReorderDialog(self.repo, self)
                dlg.finished.connect(dlg.deleteLater)
                dlg.exec_()
        def qfoldact():
            dlg = qfold.QFoldDialog(self.repo, self.menuselection, self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.output.connect(self.output)
            dlg.makeLogVisible.connect(self.makeLogVisible)
            dlg.exec_()

        menu = QMenu(self)
        acts = []
        for name, cb, icon in (
            (_('QGoto'), self.qgotoRevision, 'hg-qgoto'),
            (_('QPush --move'), self.qpushMoveRevision, 'hg-qpush'),
            (_('Fold patches...'), qfoldact, 'hg-qfold'),
            (_('Delete patches...'), qdeleteact, 'hg-qdelete'),
            (_('Reorder patches...'), qreorderact, 'hg-qreorder')):
            act = QAction(name, self)
            act.triggered.connect(cb)
            if icon:
                act.setIcon(qtlib.getmenuicon(icon))
            acts.append(act)
            menu.addAction(act)
        self.unappcmenu = menu
        self.unappacts = acts

    def generateMultipleSelectionMenu(self):
        def exportSel():
            self.exportRevisions(self.menuselection)
        def emailSel():
            run.email(self.repo.ui, rev=self.menuselection, repo=self.repo)
        menu = QMenu(self)
        for name, cb, icon in (
                (_('Export Selected...'), exportSel, 'hg-export'),
                (_('Email Selected...'), emailSel, 'mail-forward'),
                ):
            a = QAction(name, self)
            if icon:
                a.setIcon(qtlib.getmenuicon(icon))
            a.triggered.connect(cb)
            menu.addAction(a)
        if 'reviewboard' in self.repo.extensions():
            a = QAction(_('Post Selected to Review Board...'), self)
            a.triggered.connect(self.sendToReviewBoard)
            menu.addAction(a)
        self.multicmenu = menu

    def generateBundleMenu(self):
        menu = QMenu(self)
        for name, cb, icon in (
                (_('Pull to here...'), self.pullBundleToRev, 'hg-pull-to-here'),
                (_('Visual diff...'), self.visualDiffRevision, 'visualdiff'),
                ):
            a = QAction(name, self)
            a.triggered.connect(cb)
            if icon:
                a.setIcon(qtlib.getmenuicon(icon))
            menu.addAction(a)
        self.bundlemenu = menu

    def exportRevisions(self, revisions):
        if not revisions:
            revisions = [self.rev]
        dir = QFileDialog.getExistingDirectory(self, _('Export patch'),
                                               hglib.tounicode(self.repo.root))
        if not dir:
            return
        epath = os.path.join(hglib.fromunicode(dir),
                             self.repo.shortname + '_%r.patch')
        cmdline = ['export', '--repository', self.repo.root, '--verbose',
                   '--output', epath]
        for rev in revisions:
            cmdline.extend(['--rev', str(rev)])
        self.runCommand(cmdline)

    def visualDiffRevision(self):
        opts = dict(change=self.rev)
        dlg = visdiff.visualdiff(self.repo.ui, self.repo, [], opts)
        if dlg:
            dlg.exec_()

    def visualDiffToLocal(self):
        assert type(self.rev) is int
        opts = dict(rev=['rev(%d)' % self.rev])
        dlg = visdiff.visualdiff(self.repo.ui, self.repo, [], opts)
        if dlg:
            dlg.exec_()

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
        dlg.showMessage.connect(self.showMessage)
        dlg.output.connect(self.output)
        dlg.makeLogVisible.connect(self.makeLogVisible)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()

    def bookmarkRevision(self):
        dlg = bookmark.BookmarkDialog(self.repo, self.rev, self)
        dlg.showMessage.connect(self.showMessage)
        dlg.output.connect(self.output)
        dlg.makeLogVisible.connect(self.makeLogVisible)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()

    def transplantRevision(self):
        cmdline = ['transplant', '--repository', self.repo.root, str(self.rev)]
        self.runCommand(cmdline)

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

    def copyPatch(self):
        from mercurial import commands, ui
        _ui = self.repo.ui
        _ui.pushbuffer()
        try:
            if self.rev:
                class Writable(object):
                    def write(self, *args, **opts): _ui.write(*args, **opts)
                    def close(self): pass
                commands.export(_ui, self.repo, self.rev, output=Writable())
            else:
                commands.diff(_ui, self.repo)
        except Exception, e:
            _ui.popbuffer()
            self.showMessage(hglib.tounicode(str(e)))
            if 'THGDEBUG' in os.environ:
                import traceback
                traceback.print_exc()
            return
        output = _ui.popbuffer()
        QApplication.clipboard().setText(hglib.tounicode(output))

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
        self.runCommand(cmdline)

    def qfinishRevision(self):
        """Finish applied patches up to and including selected revision"""
        cmdline = ['qfinish', 'qbase::%s' % self.rev,
                   '--repository', self.repo.root]
        self.runCommand(cmdline)

    def qgotoRevision(self):
        """Make REV the top applied patch"""
        ctx = self.repo.changectx(self.rev)
        if 'qparent' in ctx.tags():
            cmdline = ['qpop', '--all', '--repository', self.repo.root]
            self.runCommand(cmdline)
        else:
            patchname = self.repo.changectx(self.rev).thgmqpatchname()
            self.taskTabsWidget.setCurrentIndex(self.mqTabIndex)
            self.mqDemand.forward('qgotoRevision', patchname)

    def qpushMoveRevision(self):
        """Make REV the top applied patch"""
        ctx = self.repo.changectx(self.rev)
        patchname = self.repo.changectx(self.rev).thgmqpatchname()
        cmdline = ['qpush', '--move', str(patchname),
                   '--repository', self.repo.root]
        self.runCommand(cmdline)

    def onCommandFinished(self, ret):
        self.repo.decrementBusyCount()

    def runCommand(self, cmdline):
        if self.runner.core.running():
            InfoMsgBox(_('Unable to start'),
                       _('Previous command is still running'))
            return
        self.repo.incrementBusyCount()
        self.runner.run(cmdline)

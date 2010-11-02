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
from tortoisehg.hgqt import archive, thgimport, thgstrip, run, purge
from tortoisehg.hgqt import bisect, rebase, resolve, thgrepo

from tortoisehg.hgqt.repofilter import RepoFilterBar
from tortoisehg.hgqt.repoview import HgRepoView
from tortoisehg.hgqt.revdetails import RevDetailsWidget
from tortoisehg.hgqt.commit import CommitWidget
from tortoisehg.hgqt.manifestdialog import ManifestTaskWidget
from tortoisehg.hgqt.sync import SyncWidget
from tortoisehg.hgqt.grep import SearchWidget
from tortoisehg.hgqt.quickbar import GotoQuickBar

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

        self._reload_rev = '.' # select working parent at startup
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

        self.filterbar = RepoFilterBar(self.repo)
        self.filterbar.branchChanged.connect(self.setBranch)
        self.filterbar.progress.connect(self.progress)
        self.filterbar.showMessage.connect(self.showMessage)
        self.filterbar.revisionSet.connect(self.setRevisionSet)
        self.filterbar.clearSet.connect(self.clearSet)
        self.filterbar.filterToggled.connect(self.filterToggled)
        hbox.addWidget(self.filterbar)

        self.revsetfilter = self.filterbar.filtercb.isChecked()

        self.layout().addWidget(self.repotabs_splitter)
        QShortcut(QKeySequence('CTRL+P'), self, self.gotoParent)

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
        self.repotabs_splitter.setStretchFactor(0, 1)

        self.taskTabsWidget = tt = QTabWidget()
        tt.setDocumentMode(True)
        tt.setTabPosition(QTabWidget.East)
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

    def title(self):
        """Returns the expected title for this widget [unicode]"""
        if self.bundle:
            return _('%s <incoming>') % self.repo.shortname
        elif self.branch:
            return '%s [%s]' % (self.repo.shortname, self.branch)
        else:
            return self.repo.shortname

    @pyqtSlot()
    def showSearchBar(self):
        """Show tasktab-specific search bar if available"""
        curtt = self.taskTabsWidget.currentWidget()
        show = getattr(curtt, 'showSearchBar', None)
        if show:
            show()

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

        def openlink(link):
            if unicode(link).startswith('subrepo:'):
                self.workbench.showRepo(link[8:])
        cw.linkActivated.connect(openlink)

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
        self.setRevisionSet(nodes)

    def createGrepWidget(self):
        upats = {}
        gw = SearchWidget(upats, self.repo, self)
        gw.setRevision(self.repoview.current_rev)
        gw.showMessage.connect(self.showMessage)
        return gw

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
            ('pushto', _('Push to here'), None, None, None, self.pushToRevision),
            ('export', _('Export patch'), None, None, None, self.exportRevisions),
            ('email', _('Email patch...'), None, None, None, self.emailRevision),
            ('archive', _('Archive...'), None, None, None, self.archiveRevision),
            ('copyhash', _('Copy hash'), None, None, None, self.copyHash),
            ('rebase', _('Rebase...'), None, None, None, self.rebaseRevision),
            ('qimport', _('Import to MQ'), None, None, None,
                self.qimportRevision),
            ('qfinish', _('Finish patch'), None, None, None, self.qfinishRevision),
            ('qdelete', _('Delete patch'), None, None, None, self.qdeleteRevision),
            ('strip', _('Strip...'), None, None, None, self.stripRevision),
            ('qpop-all', _('Pop all patches'), None, None, None, self.qpopAllRevision),
            ('qgoto', _('Goto patch'), None, None, None, self.qgotoRevision),
            ('postreview', _('Post to Review Board...'), 'reviewboard', None, None, self.sendToReviewBoard)
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
        self.repo.incrementBusyCount()
        try:
            saved = self.repo.ui.quiet
            self.repo.ui.quiet = True
            self.repo.rollback()
            self.repo.ui.quiet = saved
        finally:
            self.repo.decrementBusyCount()
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
        self.filterbar.refresh()

    def rebuildGraph(self):
        self.showMessage('')
        if self.rev is not None and len(self.repo) >= self.rev:
            self._reload_rev = self.rev
        else:
            self._reload_rev = '.'
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

    def switchedTo(self):
        'Update back / forward actions'
        self.repoview.updateActions()

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
        elif self.bundle:
            # Special menu for applied bundle
            menu = QMenu(self) # TODO: save in repowidget
            act = QAction(_('Pull to here'), self)
            act.triggered.connect(self.pullToRev)
            menu.addAction(act)
            menu.exec_(point)
            return
        elif len(selection) == 1:
            self.singleSelectionMenu(point, selection)
        elif len(selection) == 2:
            self.doubleSelectionMenu(point, selection)
        else:
            self.multipleSelectionMenu(point, selection)
    
    def singleSelectionMenu(self, point, selection):

        if not self.singlecmenu:
            menu = QMenu(self)
            allactions = [[None, ['update', 'manifest', 'merge', 'tag',
                                  'backout', 'pushto', 'export',
                                  'email', 'archive', 'copyhash']],
                      ['rebase', ['rebase']],
                      ['mq',     ['qgoto', 'qpop-all', 'qimport', 'qfinish',
                                  'qdelete', 'strip']],
                      ['reviewboard', ['postreview']]]

            exs = self.repo.extensions()
            for ext, actions in allactions:
                if ext is None or ext in exs:
                    for act in actions:
                        menu.addAction(self._actions[act])
                menu.addSeparator()
            self.singlecmenu = menu

        ctx = self.repo.changectx(self.rev)

        workingdir = self.rev is None
        appliedpatch = ctx.thgmqappliedpatch() 
        unappliedpatch = ctx.thgmqunappliedpatch()
        qparent = 'qparent' in ctx.tags()
        patch = appliedpatch or unappliedpatch
        realrev = not unappliedpatch and not workingdir
        normalrev = not patch and not workingdir

        enabled = {'update': not unappliedpatch,
                   'manifest': not unappliedpatch,
                   'merge': normalrev,
                   'tag': normalrev,
                   'backout': normalrev,
                   'export': not workingdir,
                   'email': not workingdir,
                   'pushto': realrev,
                   'archive': realrev,
                   'copyhash': realrev,
                   'rebase': not unappliedpatch,
                   'qgoto': patch,
                   'qpop-all': qparent,
                   'qimport': normalrev,
                   'qfinish': appliedpatch,
                   'qdelete': unappliedpatch,
                   'strip': normalrev,
                   'postreview': normalrev}

        for action, enabled in enabled.iteritems():
            self._actions[action].setEnabled(enabled)

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
            if revA > revB:
                B, A = selection
            else:
                A, B = selection
            func = revset.match('%s::%s' % (A, B))
            func(self.repo, range(0, 1))
            return [c for c in func(self.repo, range(len(self.repo)))]

        def exportPair():
            self.exportRevisions(selection)
        def exportDagRange():
            l = dagrange()
            if l:
                self.exportRevisions(l)
        def diffPair():
            revA, revB = selection
            visdiff.visualdiff(self.repo.ui, self.repo, [],
                    {'rev':'%s:%s' % (revA, revB)})
        def emailPair():
            run.email(self.repo.ui, rev=selection, repo=self.repo)
        def emailDagRange():
            l = dagrange()
            if l:
                run.email(self.repo.ui, rev=l, repo=self.repo)
        def bisectNormal():
            revA, revB = selection
            opts = {'good':str(revA), 'bad':str(revB)}
            dlg = bisect.BisectDialog(self.repo, opts, self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.exec_()
        def bisectReverse():
            revA, revB = selection
            opts = {'good':str(revB), 'bad':str(revA)}
            dlg = bisect.BisectDialog(self.repo, opts, self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.exec_()

        if not self.paircmenu:
            menu = QMenu(self)
            for name, cb in (
                    (_('Visual Diff'), diffPair),
                    (_('Export Pair'), exportPair),
                    (_('Email Pair'), emailPair),
                    (_('Export DAG Range'), exportDagRange),
                    (_('Email DAG Range'), emailDagRange),
                    (_('Bisect - Good, Bad'), bisectNormal),
                    (_('Bisect - Bad, Good'), bisectReverse),
                    (_('Post Pair to Review Board'), self.sendToReviewBoard),
                    ):
                a = QAction(name, self)
                a.triggered.connect(cb)
                menu.addAction(a)
            self.paircmenu = menu
        self.paircmenu.exec_(point)

    def multipleSelectionMenu(self, point, selection):
        for r in selection:
            # No multi menu if working directory or unapplied patch
            if type(r) is not int:
                return
        def exportSel():
            self.exportRevisions(selection)
        def emailSel():
            run.email(self.repo.ui, rev=selection, repo=self.repo)
        if not self.multicmenu:
            menu = QMenu(self)
            for name, cb in (
                    (_('Export Selected'), exportSel),
                    (_('Email Selected'), emailSel),
                    (_('Post Selected to Review Board'), self.sendToReviewBoard),
                    ):
                a = QAction(name, self)
                a.triggered.connect(cb)
                menu.addAction(a)
            self.multicmenu = menu
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
        dlg.exec_()

    def pushToRevision(self):
        self.taskTabsWidget.setCurrentIndex(self.syncTabIndex)
        self.syncDemand.pushToRevision(self.rev)

    def backoutToRevision(self):
        dlg = backout.BackoutDialog(self.repo, str(self.rev), self)
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

    def qdeleteRevision(self):
        """Delete unapplied patch"""
        patchname = self.repo.changectx(self.rev).thgmqpatchname()
        cmdline = ['qdelete', str(patchname),
                   '--repository', self.repo.root]
        self.runCommand(_('QDelete - TortoiseHg'), cmdline)

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

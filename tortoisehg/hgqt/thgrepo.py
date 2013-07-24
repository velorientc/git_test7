# thgrepo.py - TortoiseHg additions to key Mercurial classes
#
# Copyright 2010 George Marrows <george.marrows@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.
#
# See mercurial/extensions.py, comments to wrapfunction, for this approach
# to extending repositories and change contexts.

import os
import sys
import shutil
import tempfile
import re
import time

from PyQt4.QtCore import *

from mercurial import hg, util, error, bundlerepo, extensions, filemerge, node
from mercurial import merge, subrepo
from mercurial import ui as uimod
from mercurial.util import propertycache

from tortoisehg.util import hglib, paths
from tortoisehg.util.patchctx import patchctx

_repocache = {}
_kbfregex = re.compile(r'^\.kbf/')
_lfregex = re.compile(r'^\.hglf/')

if 'THGDEBUG' in os.environ:
    def dbgoutput(*args):
        sys.stdout.write(' '.join([str(a) for a in args])+'\n')
else:
    def dbgoutput(*args):
        pass

# thgrepo.repository() will be deprecated
def repository(_ui=None, path='', bundle=None):
    '''Returns a subclassed Mercurial repository to which new
    THG-specific methods have been added. The repository object
    is obtained using mercurial.hg.repository()'''
    if bundle:
        if _ui is None:
            _ui = uimod.ui()
        repo = bundlerepo.bundlerepository(_ui, path, bundle)
        repo.__class__ = _extendrepo(repo)
        agent = RepoAgent(repo)
        return agent.rawRepo()
    if path not in _repocache:
        if _ui is None:
            _ui = uimod.ui()
        try:
            repo = hg.repository(_ui, path)
            # get unfiltered repo in version safe manner
            repo = getattr(repo, 'unfiltered', lambda: repo)()
            repo.__class__ = _extendrepo(repo)
            agent = RepoAgent(repo)
            _repocache[path] = agent.rawRepo()
            return agent.rawRepo()
        except EnvironmentError:
            raise error.RepoError('Cannot open repository at %s' % path)
    if not os.path.exists(os.path.join(path, '.hg/')):
        del _repocache[path]
        # this error must be in local encoding
        raise error.RepoError('%s is not a valid repository' % path)
    return _repocache[path]

class _LockStillHeld(Exception):
    'Raised to abort status check due to lock existence'

class RepoWatcher(QObject):
    """Notify changes of repository by optionally monitoring filesystem"""

    configChanged = pyqtSignal()
    repositoryChanged = pyqtSignal()
    repositoryDestroyed = pyqtSignal()
    workingBranchChanged = pyqtSignal()

    def __init__(self, repo, parent=None):
        super(RepoWatcher, self).__init__(parent)
        self.repo = repo
        self._fswatcher = None
        self.recordState()
        self._uimtime = time.time()

    def startMonitoring(self):
        """Start filesystem monitoring to notify changes automatically"""
        if not self._fswatcher:
            self._fswatcher = QFileSystemWatcher(self)
            self._fswatcher.directoryChanged.connect(self._pollChanges)
            self._fswatcher.fileChanged.connect(self._pollChanges)
        self._fswatcher.addPath(hglib.tounicode(self.repo.path))
        self._fswatcher.addPath(hglib.tounicode(self.repo.spath))
        self.addMissingPaths()
        self._fswatcher.blockSignals(False)

    def stopMonitoring(self):
        """Stop filesystem monitoring by removing all watched paths"""
        if not self._fswatcher:
            return
        self._fswatcher.blockSignals(True)  # ignore pending events
        dirs = self._fswatcher.directories()
        if dirs:
            self._fswatcher.removePaths(dirs)
        files = self._fswatcher.files()
        if files:
            self._fswatcher.removePaths(files)

    def isMonitoring(self):
        """True if filesystem monitor is running"""
        if not self._fswatcher:
            return False
        return not self._fswatcher.signalsBlocked()

    @pyqtSlot()
    def _pollChanges(self):
        '''Catch writes or deletions of files, or writes to .hg/ folder,
        most importantly lock files'''
        self.pollStatus()
        # filesystem monitor may be stopped inside pollStatus()
        if self.isMonitoring():
            self.addMissingPaths()

    def addMissingPaths(self):
        'Add files to watcher that may have been added or replaced'
        existing = [f for f in self._getwatchedfiles() if os.path.isfile(f)]
        files = [unicode(f) for f in self._fswatcher.files()]
        for f in existing:
            if hglib.tounicode(f) not in files:
                dbgoutput('add file to watcher:', f)
                self._fswatcher.addPath(hglib.tounicode(f))
        for f in self.repo.uifiles():
            if f and os.path.exists(f) and hglib.tounicode(f) not in files:
                dbgoutput('add ui file to watcher:', f)
                self._fswatcher.addPath(hglib.tounicode(f))

    def pollStatus(self):
        if not os.path.exists(self.repo.path):
            dbgoutput('Repository destroyed', self.repo.root)
            self.repositoryDestroyed.emit()
            return
        if self.locked():
            dbgoutput('locked, aborting')
            return
        try:
            if self._checkdirstate():
                dbgoutput('dirstate changed, exiting')
                return
            self._checkrepotime()
            self._checkuimtime()
        except _LockStillHeld:
            dbgoutput('lock still held - ignoring for now')

    def locked(self):
        if os.path.lexists(self.repo.join('wlock')):
            return True
        if os.path.lexists(self.repo.sjoin('lock')):
            return True
        return False

    def recordState(self):
        try:
            self._parentnodes = self._getrawparents()
            self._repomtime = self._getrepomtime()
            self._dirstatemtime = os.path.getmtime(self.repo.join('dirstate'))
            self._branchmtime = os.path.getmtime(self.repo.join('branch'))
            self._rawbranch = self.repo.opener('branch').read()
        except EnvironmentError:
            self._dirstatemtime = None
            self._branchmtime = None
            self._rawbranch = None

    def _getrawparents(self):
        try:
            return self.repo.opener('dirstate').read(40)
        except EnvironmentError:
            return None

    def _getwatchedfiles(self):
        watchedfiles = [self.repo.sjoin('00changelog.i')]
        watchedfiles.append(self.repo.sjoin('phaseroots'))
        watchedfiles.append(self.repo.join('localtags'))
        if hasattr(self.repo, 'mq'):
            watchedfiles.append(self.repo.mq.path)
            watchedfiles.append(self.repo.mq.join('series'))
            watchedfiles.append(self.repo.mq.join('guards'))
            watchedfiles.append(self.repo.join('patches.queue'))
        return watchedfiles

    def _getrepomtime(self):
        'Return the last modification time for the repo'
        try:
            existing = [f for f in self._getwatchedfiles() if os.path.isfile(f)]
            mtime = [os.path.getmtime(wf) for wf in existing]
            if mtime:
                return max(mtime)
        except EnvironmentError:
            return None

    def _checkrepotime(self):
        'Check for new changelog entries, or MQ status changes'
        if self._repomtime < self._getrepomtime():
            dbgoutput('detected repository change')
            if self.locked():
                raise _LockStillHeld
            self.recordState()
            self.repositoryChanged.emit()

    def _checkdirstate(self):
        'Check for new dirstate mtime, then working parent changes'
        try:
            mtime = os.path.getmtime(self.repo.join('dirstate'))
        except EnvironmentError:
            return False
        if mtime <= self._dirstatemtime:
            return False
        changed = self._checkparentchanges() or self._checkbranch()
        self._dirstatemtime = mtime
        return changed

    def _checkparentchanges(self):
        nodes = self._getrawparents()
        if nodes != self._parentnodes:
            dbgoutput('dirstate change found')
            if self.locked():
                raise _LockStillHeld
            self.recordState()
            self.repositoryChanged.emit()
            return True
        return False

    def _checkbranch(self):
        try:
            mtime = os.path.getmtime(self.repo.join('branch'))
        except EnvironmentError:
            return False
        if mtime <= self._branchmtime:
            return False
        changed = self._checkbranchcontent()
        self._branchmtime = mtime
        return changed

    def _checkbranchcontent(self):
        try:
            newbranch = self.repo.opener('branch').read()
        except EnvironmentError:
            return False
        if newbranch != self._rawbranch:
            dbgoutput('branch time change')
            if self.locked():
                raise _LockStillHeld
            self._rawbranch = newbranch
            self.workingBranchChanged.emit()
            return True
        return False

    def _checkuimtime(self):
        'Check for modified config files, or a new .hg/hgrc file'
        try:
            files = self.repo.uifiles()
            mtime = max(os.path.getmtime(f) for f in files if os.path.isfile(f))
            if mtime > self._uimtime:
                dbgoutput('config change detected')
                self._uimtime = mtime
                self.configChanged.emit()
        except (EnvironmentError, ValueError):
            pass


class RepoAgent(QObject):
    """Proxy access to repository and keep its states up-to-date"""

    configChanged = pyqtSignal()
    repositoryChanged = pyqtSignal()
    repositoryDestroyed = pyqtSignal()
    workingBranchChanged = pyqtSignal()

    busyChanged = pyqtSignal(bool)

    def __init__(self, repo):
        QObject.__init__(self)
        self._repo = repo
        self._busycount = 0
        # TODO: remove repo-to-agent references later; all widgets should own
        # RepoAgent instead of thgrepository.
        repo._pyqtobj = self
        repo.configChanged = self.configChanged
        repo.repositoryChanged = self.repositoryChanged
        repo.repositoryDestroyed = self.repositoryDestroyed
        repo.workingBranchChanged = self.workingBranchChanged

        self._watcher = watcher = RepoWatcher(repo, self)
        watcher.configChanged.connect(self._onConfigChanged)
        watcher.repositoryChanged.connect(self._onRepositoryChanged)
        watcher.repositoryDestroyed.connect(self._onRepositoryDestroyed)
        watcher.workingBranchChanged.connect(self._onWorkingBranchChanged)

    def startMonitoringIfEnabled(self):
        """Start filesystem monitoring on repository open by RepoManager or
        running command finished"""
        repo = self._repo
        monitorrepo = repo.ui.config('tortoisehg', 'monitorrepo', 'always')
        if monitorrepo == 'never':
            dbgoutput('watching of F/S events is disabled by configuration')
        elif isinstance(repo, bundlerepo.bundlerepository):
            dbgoutput('not watching F/S events for bundle repository')
        elif monitorrepo == 'localonly' and paths.netdrive_status(repo.path):
            dbgoutput('not watching F/S events for network drive')
        elif self.isBusy():
            dbgoutput('not watching F/S events while busy')
        else:
            self._watcher.startMonitoring()

    def stopMonitoring(self):
        """Stop filesystem monitoring on repository closed by RepoManager or
        command about to run"""
        self._watcher.stopMonitoring()

    def rawRepo(self):
        return self._repo

    def rootPath(self):
        return hglib.tounicode(self._repo.root)

    def pollStatus(self):
        """Force checking changes to emit corresponding signals"""
        self._watcher.pollStatus()

    @pyqtSlot()
    def _onConfigChanged(self):
        self._repo.invalidateui()
        self.configChanged.emit()

    @pyqtSlot()
    def _onRepositoryChanged(self):
        self._repo.thginvalidate()
        self.repositoryChanged.emit()

    @pyqtSlot()
    def _onRepositoryDestroyed(self):
        if self._repo.root in _repocache:
            del _repocache[self._repo.root]
        self.stopMonitoring()  # avoid further changed/destroyed signals
        self.repositoryDestroyed.emit()

    @pyqtSlot()
    def _onWorkingBranchChanged(self):
        self._repo.thginvalidate()
        self.workingBranchChanged.emit()

    def isBusy(self):
        return self._busycount > 0

    def _incrementBusyCount(self):
        self._busycount += 1
        if self._busycount == 1:
            self.stopMonitoring()
            self.busyChanged.emit(self.isBusy())

    def _decrementBusyCount(self):
        self._busycount -= 1
        if self._busycount == 0:
            self.pollStatus()
            self.startMonitoringIfEnabled()
            self.busyChanged.emit(self.isBusy())
        else:
            # A lot of logic will depend on invalidation happening within
            # the context of this call. Signals will not be emitted till later,
            # but we at least invalidate cached data in the repository
            self._repo.thginvalidate()


def _normreporoot(path):
    """Normalize repo root path in the same manner as localrepository"""
    # see localrepo.localrepository and scmutil.vfs
    lpath = hglib.fromunicode(path)
    lpath = os.path.realpath(util.expandpath(lpath))
    return hglib.tounicode(lpath)

class RepoManager(QObject):
    """Cache open RepoAgent instances and bundle their signals"""

    repositoryOpened = pyqtSignal(unicode)
    repositoryClosed = pyqtSignal(unicode)

    configChanged = pyqtSignal(unicode)
    repositoryChanged = pyqtSignal(unicode)
    repositoryDestroyed = pyqtSignal(unicode)

    def __init__(self, ui, parent=None):
        super(RepoManager, self).__init__(parent)
        self._ui = ui
        self._openagents = {}  # path: (agent, refcount)

    def openRepoAgent(self, path):
        """Return RepoAgent for the specified path and increment refcount"""
        path = _normreporoot(path)
        if path in self._openagents:
            agent, refcount = self._openagents[path]
            self._openagents[path] = (agent, refcount + 1)
            return agent

        # TODO: move repository creation from thgrepo.repository()
        self._ui.debug('opening repo: %s\n' % hglib.fromunicode(path))
        agent = repository(self._ui, hglib.fromunicode(path))._pyqtobj
        assert agent.parent() is None
        agent.setParent(self)
        for sig, slot in self._mappedSignals(agent):
            sig.connect(slot)
        agent.startMonitoringIfEnabled()

        assert agent.rootPath() == path
        self._openagents[path] = (agent, 1)
        self.repositoryOpened.emit(path)
        return agent

    def releaseRepoAgent(self, path):
        """Decrement refcount of RepoAgent and close it if possible"""
        path = _normreporoot(path)
        agent, refcount = self._openagents[path]
        if refcount > 1:
            self._openagents[path] = (agent, refcount - 1)
            return

        self._ui.debug('closing repo: %s\n' % hglib.fromunicode(path))
        agent, _refcount = self._openagents.pop(path)
        agent.stopMonitoring()
        for sig, slot in self._mappedSignals(agent):
            sig.disconnect(slot)
        agent.setParent(None)
        self.repositoryClosed.emit(path)

    def repoAgent(self, path):
        """Peek open RepoAgent for the specified path without refcount change;
        None for unknown path"""
        path = _normreporoot(path)
        return self._openagents.get(path, (None, 0))[0]

    def repoRootPaths(self):
        """Return list of root paths of open repositories"""
        return self._openagents.keys()

    def _mappedSignals(self, agent):
        return [
            (agent.configChanged,           self._mapConfigChanged),
            (agent.repositoryChanged,       self._mapRepositoryChanged),
            (agent.repositoryDestroyed,     self._mapRepositoryDestroyed),
            ]

    #@pyqtSlot()
    def _mapConfigChanged(self):
        agent = self.sender()
        self.configChanged.emit(agent.rootPath())

    #@pyqtSlot()
    def _mapRepositoryChanged(self):
        agent = self.sender()
        self.repositoryChanged.emit(agent.rootPath())

    #@pyqtSlot()
    def _mapRepositoryDestroyed(self):
        agent = self.sender()
        self.repositoryDestroyed.emit(agent.rootPath())


_uiprops = '''_uifiles postpull tabwidth maxdiff
              deadbranches _exts _thghiddentags displayname summarylen
              shortname mergetools namedbranches'''.split()
_thgrepoprops = '''_thgmqpatchnames thgmqunappliedpatches
                   _branchheads'''.split()

def _extendrepo(repo):
    class thgrepository(repo.__class__):

        def __getitem__(self, changeid):
            '''Extends Mercurial's standard __getitem__() method to
            a) return a thgchangectx with additional methods
            b) return a patchctx if changeid is the name of an MQ
            unapplied patch
            c) return a patchctx if changeid is an absolute patch path
            '''

            # Mercurial's standard changectx() (rather, lookup())
            # implies that tags and branch names live in the same namespace.
            # This code throws patch names in the same namespace, but as
            # applied patches have a tag that matches their patch name this
            # seems safe.
            if changeid in self.thgmqunappliedpatches:
                q = self.mq # must have mq to pass the previous if
                return genPatchContext(self, q.join(changeid), rev=changeid)
            elif type(changeid) is str and '\0' not in changeid and \
                    os.path.isabs(changeid) and os.path.isfile(changeid):
                return genPatchContext(repo, changeid)

            changectx = super(thgrepository, self).__getitem__(changeid)
            changectx.__class__ = _extendchangectx(changectx)
            return changectx

        @propertycache
        def _thghiddentags(self):
            ht = self.ui.config('tortoisehg', 'hidetags', '')
            return [t.strip() for t in ht.split()]

        @propertycache
        def thgmqunappliedpatches(self):
            '''Returns a list of (patch name, patch path) of all self's
            unapplied MQ patches, in patch series order, first unapplied
            patch first.'''
            if not hasattr(self, 'mq'): return []

            q = self.mq
            applied = set([p.name for p in q.applied])

            return [pname for pname in q.series if not pname in applied]

        @propertycache
        def _thgmqpatchnames(self):
            '''Returns all tag names used by MQ patches. Returns []
            if MQ not in use.'''
            if not hasattr(self, 'mq'): return []

            self.mq.parseseries()
            return self.mq.series[:]

        @property
        def thgactivemqname(self):
            '''Currenty-active qqueue name (see hgext/mq.py:qqueue)'''
            if not hasattr(self, 'mq'):
                return
            n = os.path.basename(self.mq.path)
            if n.startswith('patches-'):
                return n[8:]
            else:
                return n

        @propertycache
        def _uifiles(self):
            cfg = self.ui._ucfg
            files = set()
            for line in cfg._source.values():
                f = line.rsplit(':', 1)[0]
                files.add(f)
            files.add(self.join('hgrc'))
            return files

        @propertycache
        def _exts(self):
            lclexts = []
            allexts = [n for n,m in extensions.extensions()]
            for name, path in self.ui.configitems('extensions'):
                if name.startswith('hgext.'):
                    name = name[6:]
                if name in allexts:
                    lclexts.append(name)
            return lclexts

        @propertycache
        def postpull(self):
            pp = self.ui.config('tortoisehg', 'postpull')
            if pp in ('rebase', 'update', 'fetch', 'updateorrebase'):
                return pp
            return 'none'

        @propertycache
        def tabwidth(self):
            tw = self.ui.config('tortoisehg', 'tabwidth')
            try:
                tw = int(tw)
                tw = min(tw, 16)
                return max(tw, 2)
            except (ValueError, TypeError):
                return 8

        @propertycache
        def maxdiff(self):
            maxdiff = self.ui.config('tortoisehg', 'maxdiff')
            try:
                maxdiff = int(maxdiff)
                if maxdiff < 1:
                    return sys.maxint
            except (ValueError, TypeError):
                maxdiff = 1024 # 1MB by default
            return maxdiff * 1024

        @propertycache
        def summarylen(self):
            slen = self.ui.config('tortoisehg', 'summarylen')
            try:
                slen = int(slen)
                if slen < 10:
                    return 80
            except (ValueError, TypeError):
                slen = 80
            return slen

        @propertycache
        def deadbranches(self):
            db = self.ui.config('tortoisehg', 'deadbranch', '')
            return [b.strip() for b in db.split(',')]

        @propertycache
        def displayname(self):
            'Display name is for window titles and similar'
            if self.ui.configbool('tortoisehg', 'fullpath'):
                name = self.root
            elif self.ui.config('web', 'name', False):
                name = self.ui.config('web', 'name')
            else:
                name = os.path.basename(self.root)
            return hglib.tounicode(name)

        @propertycache
        def shortname(self):
            'Short name is for tables, tabs, and sentences'
            if self.ui.config('web', 'name', False):
                name = self.ui.config('web', 'name')
            else:
                name = os.path.basename(self.root)
            return hglib.tounicode(name)

        @propertycache
        def mergetools(self):
            seen, installed = [], []
            for key, value in self.ui.configitems('merge-tools'):
                t = key.split('.')[0]
                if t not in seen:
                    seen.append(t)
                    if filemerge._findtool(self.ui, t):
                        installed.append(t)
            return installed

        @propertycache
        def namedbranches(self):
            allbranches = self.branchtags()
            openbrnodes = []
            for br in allbranches.iterkeys():
                openbrnodes.extend(self.branchheads(br, closed=False))
            dead = self.deadbranches
            return sorted(br for br, n in allbranches.iteritems()
                          if n in openbrnodes and br not in dead)

        @propertycache
        def _branchheads(self):
            heads = []
            for branchname, nodes in self.branchmap().iteritems():
                heads.extend(nodes)
            return heads

        def uifiles(self):
            'Returns complete list of config files'
            return self._uifiles

        def extensions(self):
            'Returns list of extensions enabled in this repository'
            return self._exts

        def thgmqtag(self, tag):
            'Returns true if `tag` marks an applied MQ patch'
            return tag in self._thgmqpatchnames

        def getcurrentqqueue(self):
            'Returns the name of the current MQ queue'
            if 'mq' not in self._exts:
                return None
            cur = os.path.basename(self.mq.path)
            if cur.startswith('patches-'):
                cur = cur[8:]
            return cur

        def thgshelves(self):
            self.shelfdir = sdir = self.join('shelves')
            if os.path.isdir(sdir):
                def getModificationTime(x):
                    try:
                        return os.path.getmtime(os.path.join(sdir, x))
                    except EnvironmentError:
                        return 0
                shelves = sorted(os.listdir(sdir),
                    key=getModificationTime, reverse=True)
                return [s for s in shelves if \
                           os.path.isfile(os.path.join(self.shelfdir, s))]
            return []

        def makeshelf(self, patch):
            if not os.path.exists(self.shelfdir):
                os.mkdir(self.shelfdir)
            f = open(os.path.join(self.shelfdir, patch), "wb")
            f.close()

        def thginvalidate(self):
            'Should be called when mtime of repo store/dirstate are changed'
            self.dirstate.invalidate()
            if not isinstance(repo, bundlerepo.bundlerepository):
                self.invalidate()
            # mq.queue.invalidate does not handle queue changes, so force
            # the queue object to be rebuilt
            if 'mq' in self.__dict__:
                delattr(self, 'mq')
            for a in _thgrepoprops + _uiprops:
                if a in self.__dict__:
                    delattr(self, a)

        def invalidateui(self):
            'Should be called when mtime of ui files are changed'
            self.ui = uimod.ui()
            self.ui.readconfig(self.join('hgrc'))
            for a in _uiprops:
                if a in self.__dict__:
                    delattr(self, a)

        # TODO: replace manual busycount handling by RepoAgent's
        def incrementBusyCount(self):
            'A GUI widget is starting a transaction'
            self._pyqtobj._incrementBusyCount()

        def decrementBusyCount(self):
            'A GUI widget has finished a transaction'
            self._pyqtobj._decrementBusyCount()

        def thgbackup(self, path):
            'Make a backup of the given file in the repository "trashcan"'
            # The backup name will be the same as the orginal file plus '.bak'
            trashcan = self.join('Trashcan')
            if not os.path.isdir(trashcan):
                os.mkdir(trashcan)
            if not os.path.exists(path):
                return
            name = os.path.basename(path)
            root, ext = os.path.splitext(name)
            dest = tempfile.mktemp(ext+'.bak', root+'_', trashcan)
            shutil.copyfile(path, dest)

        def isStandin(self, path):
            if 'largefiles' in self.extensions():
                if _lfregex.match(path):
                    return True
            if 'largefiles' in self.extensions() or 'kbfiles' in self.extensions():
                if _kbfregex.match(path):
                    return True
            return False

        def removeStandin(self, path):
            if 'largefiles' in self.extensions():
                path = _lfregex.sub('', path)
            if 'largefiles' in self.extensions() or 'kbfiles' in self.extensions():
                path = _kbfregex.sub('', path)
            return path

        def bfStandin(self, path):
            return '.kbf/' + path

        def lfStandin(self, path):
            return '.hglf/' + path

    return thgrepository

_maxchangectxclscache = 10
_changectxclscache = {}  # parentcls: extendedcls

def _extendchangectx(changectx):
    # cache extended changectx class, since we may create bunch of instances
    parentcls = changectx.__class__
    try:
        return _changectxclscache[parentcls]
    except KeyError:
        pass

    # in case each changectx instance is wrapped by some extension, there's
    # limit on cache size. it may be possible to use weakref.WeakKeyDictionary
    # on Python 2.5 or later.
    if len(_changectxclscache) >= _maxchangectxclscache:
        _changectxclscache.clear()
    _changectxclscache[parentcls] = cls = _createchangectxcls(parentcls)
    return cls

def _createchangectxcls(parentcls):
    class thgchangectx(parentcls):
        def sub(self, path):
            srepo = super(thgchangectx, self).sub(path)
            if isinstance(srepo, subrepo.hgsubrepo):
                r = srepo._repo
                # get unfiltered repo in version safe manner
                r = getattr(r, 'unfiltered', lambda: r)()
                r.__class__ = _extendrepo(r)
                srepo._repo = r
            return srepo

        def thgtags(self):
            '''Returns all unhidden tags for self'''
            htlist = self._repo._thghiddentags
            return [tag for tag in self.tags() if tag not in htlist]

        def thgwdparent(self):
            '''True if self is a parent of the working directory'''
            return self.rev() in [ctx.rev() for ctx in self._repo.parents()]

        def _thgmqpatchtags(self):
            '''Returns the set of self's tags which are MQ patch names'''
            mytags = set(self.tags())
            patchtags = self._repo._thgmqpatchnames
            result = mytags.intersection(patchtags)
            assert len(result) <= 1, "thgmqpatchname: rev has more than one tag in series"
            return result

        def thgmqappliedpatch(self):
            '''True if self is an MQ applied patch'''
            return self.rev() is not None and bool(self._thgmqpatchtags())

        def thgmqunappliedpatch(self):
            return False

        def thgid(self):
            return self._node

        def thgmqpatchname(self):
            '''Return self's MQ patch name. AssertionError if self not an MQ patch'''
            patchtags = self._thgmqpatchtags()
            assert len(patchtags) == 1, "thgmqpatchname: called on non-mq patch"
            return list(patchtags)[0]

        def thgbranchhead(self):
            '''True if self is a branch head'''
            return self.node() in self._repo._branchheads

        def changesToParent(self, whichparent):
            parent = self.parents()[whichparent]
            return self._repo.status(parent.node(), self.node())[:3]

        def longsummary(self):
            if self._repo.ui.configbool('tortoisehg', 'longsummary'):
                limit = 80
            else:
                limit = None
            return hglib.longsummary(self.description(), limit)

        def hasStandin(self, file):
            if 'largefiles' in self._repo.extensions():
                if self._repo.lfStandin(file) in self.manifest():
                    return True
            elif 'largefiles' in self._repo.extensions() or 'kbfiles' in self._repo.extensions():
                if self._repo.bfStandin(file) in self.manifest():
                    return True
            return False

        def isStandin(self, path):
            return self._repo.isStandin(path)

        def removeStandin(self, path):
            return self._repo.removeStandin(path)

        def findStandin(self, file):
            if 'largefiles' in self._repo.extensions():
                if self._repo.lfStandin(file) in self.manifest():
                    return self._repo.lfStandin(file)
            return self._repo.bfStandin(file)

    return thgchangectx

_pctxcache = {}
def genPatchContext(repo, patchpath, rev=None):
    global _pctxcache
    try:
        if os.path.exists(patchpath) and patchpath in _pctxcache:
            cachedctx = _pctxcache[patchpath]
            if cachedctx._mtime == os.path.getmtime(patchpath) and \
               cachedctx._fsize == os.path.getsize(patchpath):
                return cachedctx
    except EnvironmentError:
        pass
    # create a new context object
    ctx = patchctx(patchpath, repo, rev=rev)
    _pctxcache[patchpath] = ctx
    return ctx

def recursiveMergeStatus(repo):
    ms = merge.mergestate(repo)
    for wfile in ms:
        yield repo.root, wfile, ms[wfile]
    try:
        wctx = repo[None]
        for s in wctx.substate:
            sub = wctx.sub(s)
            if isinstance(sub, subrepo.hgsubrepo):
                for root, file, status in recursiveMergeStatus(sub._repo):
                    yield root, file, status
    except (EnvironmentError, error.Abort, error.RepoError):
        pass

def relatedRepositories(repoid):
    'Yields root paths for local related repositories'
    from tortoisehg.hgqt import reporegistry, repotreemodel
    if repoid == node.nullid:  # empty repositories shouldn't be related
        return

    f = QFile(reporegistry.settingsfilename())
    f.open(QIODevice.ReadOnly)
    try:
        for e in repotreemodel.iterRepoItemFromXml(f):
            if e.basenode() == repoid:
                yield e.rootpath(), e.shortname()
    except:
        f.close()
        raise
    else:
        f.close()

def isBfStandin(path):
    return _kbfregex.match(path)

def isLfStandin(path):
    return _lfregex.match(path)

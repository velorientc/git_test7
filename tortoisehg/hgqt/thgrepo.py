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

from PyQt4.QtCore import *

from mercurial import hg, util, error, bundlerepo, extensions, filemerge, node
from mercurial import ui as uimod
from mercurial.util import propertycache

from tortoisehg.util import hglib
from tortoisehg.util.patchctx import patchctx

_repocache = {}

if 'THGDEBUG' in os.environ:
    def dbgoutput(*args):
        sys.stdout.write(' '.join([str(a) for a in args])+'\n')
else:
    def dbgoutput(*args):
        pass

def repository(_ui=None, path='', create=False, bundle=None):
    '''Returns a subclassed Mercurial repository to which new
    THG-specific methods have been added. The repository object
    is obtained using mercurial.hg.repository()'''
    if bundle:
        if _ui is None:
            _ui = uimod.ui()
        repo = bundlerepo.bundlerepository(_ui, path, bundle)
        repo._pyqtobj = ThgRepoWrapper(repo)
        repo.__class__ = _extendrepo(repo)
        return repo
    if create or path not in _repocache:
        if _ui is None:
            _ui = uimod.ui()
        repo = hg.repository(_ui, path, create)
        repo._pyqtobj = ThgRepoWrapper(repo)
        repo.__class__ = _extendrepo(repo)
        _repocache[path] = repo
        return repo
    if not os.path.exists(os.path.join(path, '.hg/')):
        del _repocache[path]
        # this error must be in local encoding
        raise error.RepoError('%s is not a valid repository' % path)
    return _repocache[path]

class ThgRepoWrapper(QObject):

    configChanged = pyqtSignal()
    repositoryChanged = pyqtSignal()
    repositoryDestroyed = pyqtSignal()
    workingBranchChanged = pyqtSignal()

    def __init__(self, repo):
        QObject.__init__(self)
        self.repo = repo
        self.busycount = 0
        repo.configChanged = self.configChanged
        repo.repositoryChanged = self.repositoryChanged
        repo.workingBranchChanged = self.workingBranchChanged
        repo.repositoryDestroyed = self.repositoryDestroyed
        self.recordState()
        try:
            freq = repo.ui.config('tortoisehg', 'pollfreq', '500')
            freq = max(100, int(freq))
        except:
            freq = 500
        self._timerevent = self.startTimer(freq)

    def timerEvent(self, event):
        if not os.path.exists(self.repo.path):
            dbgoutput('Repository destroyed', self.repo.root)
            self.repositoryDestroyed.emit()
            self.killTimer(self._timerevent)
            if self.repo.root in _repocache:
                del _repocache[self.repo.root]
        elif self.busycount == 0:
            self.pollStatus()
        else:
            dbgoutput('no poll, busy', self.busycount)

    def pollStatus(self):
        if not os.path.exists(self.repo.path) or self.locked():
            return
        if self._checkdirstate():
            return
        self._checkrepotime()
        self._checkuimtime()

    def locked(self):
        if os.path.exists(self.repo.join('wlock')):
            return True
        if os.path.exists(self.repo.sjoin('lock')):
            return True
        return False

    def recordState(self):
        try:
            self._parentnodes = self._getrawparents()
            self._repomtime = self._getrepomtime()
            self._dirstatemtime = os.path.getmtime(self.repo.join('dirstate'))
            self._branchmtime = os.path.getmtime(self.repo.join('branch'))
            self._rawbranch = self.repo.opener('branch').read()
        except EnvironmentError, ValueError:
            self._dirstatemtime = None
            self._branchmtime = None
            self._rawbranch = None

    def _getrawparents(self):
        try:
            return self.repo.opener('dirstate').read(40)
        except EnvironmentError:
            return None

    def _getrepomtime(self):
        'Return the last modification time for the repo'
        watchedfiles = [self.repo.sjoin('00changelog.i'),
                        self.repo.join('patches/series')]
        try:
            mtime = [os.path.getmtime(wf) for wf in watchedfiles \
                     if os.path.isfile(wf)]
            if mtime:
                return max(mtime)
        except EnvironmentError:
            return None

    def _checkrepotime(self):
        'Check for new changelog entries, or MQ status changes'
        if self._repomtime < self._getrepomtime():
            dbgoutput('detected repository change')
            if self.locked():
                dbgoutput('lock still held - ignoring for now')
                return
            self.recordState()
            self.repo.thginvalidate()
            self.repositoryChanged.emit()

    def _checkdirstate(self):
        'Check for new dirstate mtime, then working parent changes'
        try:
            mtime = os.path.getmtime(self.repo.join('dirstate'))
        except EnvironmentError:
            return False
        if mtime <= self._dirstatemtime:
            return False
        self._dirstatemtime = mtime
        nodes = self._getrawparents()
        if nodes != self._parentnodes:
            dbgoutput('dirstate change found')
            if self.locked():
                dbgoutput('lock still held - ignoring for now')
                return True
            self.recordState()
            self.repo.thginvalidate()
            self.repositoryChanged.emit()
            return True
        try:
            mtime = os.path.getmtime(self.repo.join('branch'))
        except EnvironmentError:
            return False
        if mtime <= self._branchmtime:
            return False
        self._branchmtime = mtime
        try:
            newbranch = self.repo.opener('branch').read()
        except EnvironmentError:
            return False
        if newbranch != self._rawbranch:
            dbgoutput('branch time change')
            if self.locked():
                dbgoutput('lock still held - ignoring for now')
                return True
            self._rawbranch = newbranch
            self.repo.thginvalidate()
            self.workingBranchChanged.emit()
            return True
        return False

    def _checkuimtime(self):
        'Check for modified config files, or a new .hg/hgrc file'
        try:
            oldmtime, files = self.repo.uifiles()
            mtime = [os.path.getmtime(f) for f in files if os.path.isfile(f)]
            if max(mtime) > oldmtime:
                dbgoutput('config change detected')
                self.repo.invalidateui()
                self.configChanged.emit()
        except (EnvironmentError, ValueError):
            pass

_uiprops = '''_uifiles _uimtime _shell postpull tabwidth wsvisible maxdiff
              deadbranches _exts _thghiddentags displayname summarylen
              shortname mergetools bookmarks bookmarkcurrent'''.split()
_thgrepoprops = '''_thgmqpatchnames thgmqunappliedpatches
                   _branchheads'''.split()

def _extendrepo(repo):
    class thgrepository(repo.__class__):

        def changectx(self, changeid):
            '''Extends Mercurial's standard changectx() method to
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
            elif type(changeid) is str and os.path.isabs(changeid) and \
                    os.path.isfile(changeid):
                return genPatchContext(repo, changeid)

            changectx = super(thgrepository, self).changectx(changeid)
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

            self.mq.parse_series()
            return self.mq.series[:]

        @propertycache
        def _shell(self):
            s = self.ui.config('tortoisehg', 'shell')
            if s:
                return s
            if sys.platform == 'darwin':
                return None # Terminal.App does not support open-to-folder
            elif os.name == 'nt':
                return 'cmd.exe'
            else:
                return 'xterm'

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
        def _uimtime(self):
            mtimes = [0] # zero will be taken if no config files
            for f in self._uifiles:
                try:
                    if os.path.exists(f):
                        mtimes.append(os.path.getmtime(f))
                except EnvironmentError:
                    pass
            return max(mtimes)

        @propertycache
        def _exts(self):
            lclexts = []
            allexts = [n for n,m in extensions.extensions()]
            for name, path in self.ui.configitems('extensions'):
                if name in allexts:
                    lclexts.append(name)
            return lclexts

        @propertycache
        def postpull(self):
            pp = self.ui.config('tortoisehg', 'postpull')
            if pp in ('rebase', 'update', 'fetch'):
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
        def wsvisible(self):
            val = self.ui.config('tortoisehg', 'wsvisible')
            if val in ('Visible', 'VisibleAfterIndent'):
                return val
            else:
                return 'Invisible'

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
            if self.ui.config('tortoisehg', 'fullpath', False):
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
        def bookmarks(self):
            if 'bookmarks' in self._exts:
                return self._bookmarks
            else:
                return {}

        @propertycache
        def bookmarkcurrent(self):
            if 'bookmarks' in self._exts:
                return self._bookmarkcurrent
            else:
                return None

        @propertycache
        def _branchheads(self):
            return [self.changectx(x) for x in self.branchmap()]

        def shell(self):
            'Returns terminal shell configured for this repo'
            return self._shell

        def uifiles(self):
            'Returns latest mtime and complete list of config files'
            return self._uimtime, self._uifiles

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
                return [os.path.join(sdir, s) for s in os.listdir(sdir)]
            return []

        def thginvalidate(self):
            'Should be called when mtime of repo store/dirstate are changed'
            self.dirstate.invalidate()
            if not isinstance(repo, bundlerepo.bundlerepository):
                self.invalidate()
            if hasattr(self, 'mq'):
                self.mq.invalidate()
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
            # todo: extensions.loadall(self.ui)

        def incrementBusyCount(self):
            'A GUI widget is starting a transaction'
            self._pyqtobj.busycount += 1

        def decrementBusyCount(self):
            'A GUI widget has finished a transaction'
            self._pyqtobj.busycount -= 1
            if self._pyqtobj.busycount == 0:
                self._pyqtobj.pollStatus()
            else:
                # A lot of logic will depend on invalidation happening
                # within the context of this call.  Signals will not be
                # emitted till later, but we at least invalidate cached
                # data in the repository
                self.thginvalidate()

    return thgrepository


def _extendchangectx(changectx):
    class thgchangectx(changectx.__class__):
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

        def thgmqpatchname(self):
            '''Return self's MQ patch name. AssertionError if self not an MQ patch'''
            patchtags = self._thgmqpatchtags()
            assert len(patchtags) == 1, "thgmqpatchname: called on non-mq patch"
            return list(patchtags)[0]

        def thgbranchhead(self):
            '''True if self is a branch head'''
            return self in self._repo._branchheads

        def changesToParent(self, whichparent):
            parent = self.parents()[whichparent]
            return self._repo.status(parent.node(), self.node())[:3]

        def longsummary(self):
            summary = hglib.tounicode(self.description())
            if self._repo.ui.configbool('tortoisehg', 'longsummary'):
                limit = 80
                lines = summary.splitlines()
                if lines:
                    summary = lines.pop(0)
                    while len(summary) < limit and lines:
                        summary += u'  ' + lines.pop(0)
                    summary = summary[0:limit]
                else:
                    summary = ''
            else:
                lines = summary.splitlines()
                summary = lines and lines[0] or ''
            return summary

    return thgchangectx



_pctxcache = {}
def genPatchContext(repo, patchpath, rev=None):
    global _pctxcache
    holder = _pctxcache.get(patchpath, None)
    if os.path.exists(patchpath):
        mtime = os.path.getmtime(patchpath)
        if holder is not None and mtime == holder[0]:
            return holder[1]
    # create a new context object
    ctx = patchctx(patchpath, repo, rev=rev)
    _pctxcache[patchpath] = (mtime, ctx)
    return ctx

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

from mercurial import hg, patch, util, error, bundlerepo, ui, extensions
from mercurial.util import propertycache

from tortoisehg.util import hglib

_repocache = {}

def repository(_ui=None, path='', create=False):
    '''Returns a subclassed Mercurial repository to which new
    THG-specific methods have been added. The repository object
    is obtained using mercurial.hg.repository()'''
    if create or path not in _repocache:
        if _ui is None:
            _ui = ui.ui()
        repo = hg.repository(_ui, path, create)
        repo._pyqtobj = ThgRepoWrapper(repo)
        repo.__class__ = _extendrepo(repo)
        _repocache[path] = repo
        return repo
    return _repocache[path]

class ThgRepoWrapper(QObject):

    configChanged = pyqtSignal()
    repositoryChanged = pyqtSignal()
    workingBranchChanged = pyqtSignal()

    def __init__(self, repo):
        QObject.__init__(self)
        self.repo = repo
        self.busycount = 0
        repo.configChanged = self.configChanged
        repo.repositoryChanged = self.repositoryChanged
        repo.workingBranchChanged = self.workingBranchChanged
        self.recordState()
        self.startTimer(500)

    def timerEvent(self, event):
        if self.busycount == 0:
            self.pollStatus()
        else:
            print 'no poll, busy', self.busycount

    def pollStatus(self):
        self._checkrepotime()
        self._checkdirstate()
        self._checkuimtime()

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
                        self.repo.join('patches/status')]
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
            print 'detected repository change'
            self.recordState()
            self.repo.thginvalidate()
            self.repositoryChanged.emit()

    def _checkdirstate(self):
        'Check for new dirstate mtime, then working parent changes'
        try:
            mtime = os.path.getmtime(self.repo.join('dirstate'))
        except EnvironmentError:
            return
        if mtime <= self._dirstatemtime:
            return
        self._dirstatemtime = mtime
        nodes = self._getrawparents()
        if nodes != self._parentnodes:
            print 'dirstate change found'
            self.recordState()
            self.repo.dirstate.invalidate()
            self.repositoryChanged.emit()
            return
        try:
            mtime = os.path.getmtime(self.repo.join('branch'))
        except EnvironmentError:
            return
        if mtime <= self._branchmtime:
            return
        self._branchmtime = mtime
        try:
            newbranch = self.repo.opener('branch').read()
        except EnvironmentError:
            return
        if newbranch != self._rawbranch:
            print 'branch time change'
            self._rawbranch = newbranch
            self.repo.dirstate.invalidate()
            self.workingBranchChanged.emit()

    def _checkuimtime(self):
        'Check for modified config files, or a new .hg/hgrc file'
        try:
            oldmtime, files = self.repo.uifiles()
            mtime = [os.path.getmtime(f) for f in files if os.path.isfile(f)]
            if max(mtime) > oldmtime:
                print 'config change detected'
                self.repo.invalidateui()
                self.configChanged.emit()
        except EnvironmentError, ValueError:
            pass

_uiprops = '''_uifiles _uimtime _shell postpull tabwidth wsvisible
              _exts _thghiddentags displayname shortname'''.split()
_thgrepoprops = '''_thgmqpatchnames thgmqunappliedpatches'''.split()

def _extendrepo(repo):
    class thgrepository(repo.__class__):

        def changectx(self, changeid):
            '''Extends Mercurial's standard changectx() method to
            a) return a thgchangectx with additional methods
            b) return a PatchContext if changeid is the name of an MQ
            unapplied patch'''

            # Mercurial's standard changectx() (rather, lookup())
            # implies that tags and branch names live in the same namespace.
            # This code throws patch names in the same namespace, but as
            # applied patches have a tag that matches their patch name this
            # seems safe.
            if changeid in self.thgmqunappliedpatches:
                q = self.mq # must have mq to pass the previous if
                return PatchContext(self, q.join(changeid), rev=changeid)

            changectx = super(thgrepository, self).changectx(changeid)
            changectx.__class__ = _extendchangectx(changectx)
            return changectx

        @propertycache
        def _thghiddentags(self):
            t = self.ui.config('tortoisehg', 'hidetags', '')
            hiddentags_opt = hglib.tounicode(t)
            return [t.strip() for t in hiddentags_opt.split()]

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
            self.ui = ui.ui()
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
        def _thgrawtags(self):
            '''Returns the tags for self, converted to UTF-8 but
            unfiltered for hidden tags'''
            return [hglib.toutf(tag) for tag in self.tags()]

        def thgtags(self):
            '''Returns all unhidden tags for self, converted to UTF-8'''
            value = self._thgrawtags()
            htlist = self._repo._thghiddentags
            return [tag for tag in value if tag not in htlist]

        def thgwdparent(self):
            '''True if self is a parent of the working directory'''
            # FIXME doesn't handle error.Abort apparently raiseable by self._repo.parents()
            # see old __init__ for repomodel
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
            return bool(self._thgmqpatchtags())

        def thgmqunappliedpatch(self): return False

        def thgmqpatchname(self):
            '''Return self's MQ patch name. AssertionError if self not an MQ patch'''
            patchtags = self._thgmqpatchtags()
            assert len(patchtags) == 1, "thgmqpatchname: called on non-mq patch"
            return list(patchtags)[0]

        def thgbranchhead(self):
            '''True if self is a branch head'''
            return self in [self._repo[x] for x in self._repo.branchmap()]



    return thgchangectx



_pctxcache = {}

def PatchContext(repo, patchpath, rev=None):
    # check path
    if not os.path.isabs(patchpath) or not os.path.isfile(patchpath):
        return None
    # check cache
    global _pctxcache
    mtime = os.path.getmtime(patchpath)
    key = repo.root + patchpath
    holder = _pctxcache.get(key, None)
    if holder is not None and mtime == holder[0]:
        return holder[1]
    # create a new context object
    ctx = patchctx(patchpath, repo, rev=rev)
    _pctxcache[key] = (mtime, ctx)
    return ctx


class patchctx(object):

    def __init__(self, patchpath, repo, patchHandle=None, rev=None):
        """ Read patch context from file
        :param patchHandle: If set, then the patch is a temporary.
            The provided handle is used to read the patch and
            the patchpath contains the name of the patch.
            The handle is NOT closed.
        """
        self._path = patchpath
        self._patchname = os.path.basename(patchpath)
        self._repo = repo
        if patchHandle:
            pf = patchHandle
            pf_start_pos = pf.tell()
        else:
            pf = open(patchpath)
        try:
            data = patch.extract(self._repo.ui, pf)
            tmpfile, msg, user, date, branch, node, p1, p2 = data
            if tmpfile:
                os.unlink(tmpfile)
        finally:
            if patchHandle:
                pf.seek(pf_start_pos)
            else:
                pf.close()
        if not msg and hasattr(repo, 'mq'):
            # attempt to get commit message
            from hgext import mq
            msg = mq.patchheader(repo.mq.join(self._patchname)).message
            if msg:
                msg = '\n'.join(msg)
        self._node = node
        self._user = user and hglib.tounicode(user) or ''
        self._date = date and util.parsedate(date) or util.makedate()
        self._desc = msg and msg or ''
        self._branch = branch and hglib.tounicode(branch) or ''
        self._parents = []
        self._rev = rev
        for p in (p1, p2):
            if not p:
                continue
            try:
                self._parents.append(repo[p])
            except (error.LookupError, error.RepoLookupError, error.RepoError):
                self._parents.append(p)

    def __str__(self):
        node = self.node()
        if node:
            return node[:12]
        return ''

    def __int__(self):
        return self.rev()

    def node(self): return self._node
    def rev(self): return self._rev
    def hex(self):
        node = self.node()
        if node:
            return hex(node)
        return ''
    def user(self): return self._user
    def date(self): return self._date
    def description(self): return self._desc
    def branch(self): return self._branch
    def tags(self): return ()
    def parents(self): return self._parents
    def children(self): return ()
    def extra(self): return {}
    def thgtags(self): return []
    def thgwdparent(self): return False
    def thgmqappliedpatch(self): return False
    def thgmqpatchname(self): return self._patchname
    def thgbranchhead(self): return False
    def thgmqunappliedpatch(self): return True

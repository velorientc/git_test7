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

from mercurial import hg, patch, util, error, bundlerepo
from mercurial.util import propertycache

from util import hglib

def repository(ui, path='', create=False):
    '''Returns a subclassed Mercurial repository to which new 
    THG-specific methods have been added. The repository object
    is obtained using mercurial.hg.repository()'''
    repo = hg.repository(ui, path, create)  
    repo.__class__ = _extendrepo(repo)
    return repo

_thgrepoprops = '_thgmqpatchnames _thghiddentags thgmqunappliedpatches'.split()

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
            hiddentags_opt = hglib.toutf(self.ui.config('tortoisehg', 'hidetags', ''))
            return [t.strip() for t in hiddentags_opt.split()]
        
        @propertycache
        def _thgmqpatchnames(self):
            '''Returns all tag names used by MQ patches. Returns [] 
            if MQ not in use.'''
            if not hasattr(self, 'mq'): return []

            self.mq.parse_series()
            return self.mq.series[:]

        def thgmqtag(self, tag):
            '''True if tag is used to mark an applied MQ patch'''
            return tag in self._thgmqpatchnames

        def thginvalidate(self):
            self.dirstate.invalidate()
            if not isinstance(repo, bundlerepo.bundlerepository):
                self.invalidate()
            if hasattr(self, 'mq'):
                self.mq.invalidate()
            for a in _thgrepoprops:
                if a in self.__dict__:
                    delattr(self, a)

        @propertycache
        def thgmqunappliedpatches(self):
            '''Returns a list of (patch name, patch path) of all self's 
            unapplied MQ patches, in patch series order, first unapplied
            patch first.'''
            if not hasattr(self, 'mq'): return []
            
            q = self.mq 
            applied = set([p.name for p in q.applied])
            
            return [pname for pname in q.series if not pname in applied]
                    
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

        def thgmqpatch(self):
            '''True if self is an MQ applied patch'''
            mytags = set(self.tags())
            patchtags = self._repo._thgmqpatchnames
            return not not mytags.intersection(patchtags)

        def thgmqunappliedpatch(self): return False

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
        self._user = user and hglib.toutf(user) or ''
        self._date = date and util.parsedate(date) or None
        self._desc = msg and msg or ''
        self._branch = branch and hglib.toutf(branch) or ''
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
    def thgmqpatch(self): return False
    def thgbranchhead(self): return False
    def thgmqunappliedpatch(self): return True

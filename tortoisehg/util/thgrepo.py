# thgrepo.py - TortoiseHg additions to key Mercurial classes
#
# Copyright 2010 George Marrows <george.marrows@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.
#
# See mercurial/extensions.py, comments to wrapfunction, for this approach
# to extending repositories and change contexts.

from mercurial import hg
from mercurial.util import propertycache

from util import hglib

def repository(ui, path='', create=False):
    '''Returns a subclassed Mercurial repository to which new 
    THG-specific methods have been added. The repository object
    is obtained using mercurial.hg.repository()'''
    repo = hg.repository(ui, path, create)  
    repo.__class__ = _extendrepo(repo)
    return repo


def _extendrepo(repo):
    class thgrepository(repo.__class__):
        def changectx(self, changeid):
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

        def thgbranchhead(self):
            '''True if self is a branch head'''
            return self in [self._repo[x] for x in self._repo.branchmap()]

    return thgchangectx

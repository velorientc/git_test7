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

    return thgrepository
        
def _extendchangectx(changectx):
    class thgchangectx(changectx.__class__):
        pass

    return thgchangectx

# Copyright (c) 2003-2010 LOGILAB S.A. (Paris, FRANCE).
# http://www.logilab.fr/ -- mailto:contact@logilab.fr
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

"""helper functions and classes to ease hg revision graph building

Based on graphlog's algorithm, with insipration stolen from TortoiseHg
revision grapher (now stolen back).
"""

import difflib
import time
import os
import itertools

from mercurial import patch, util, match, error

from tortoisehg.util.util import isbfile
from tortoisehg.util.hglib import tounicode

def diff(repo, ctx1, ctx2, files):
    """
    Compute the diff of files between 2 changectx
    """
    if ctx2 is None:
        ctx2 = ctx1.p1()
    if files is None:
        m = match.always(repo.root, repo.getcwd())
    else:
        m = match.exact(repo.root, repo.getcwd(), files)
    diffdata = '\n'.join(patch.diff(repo, ctx2.node(), ctx1.node(), match=m))
    return tounicode(diffdata)


def getparents(ctx, branch):
    """
    Return non-null parents of `rev`. If branch is given, only return
    parents that belongs to names branch `branch` (beware that this is
    much slower).
    """
    if not branch:
        return [x.rev() for x in ctx.parents() if x]
    return [x.rev() for x in ctx.parents() if x and x.branch() == branch]


def ismerge(ctx):
    return len(ctx.parents()) > 1

def revision_grapher(repo, start_rev=None, stop_rev=0, branch=None,
                     follow=False, allparents=True):
    """incremental revision grapher

    This generator function walks through the revision history from
    revision start_rev to revision stop_rev (which must be less than
    or equal to start_rev) and for each revision emits tuples with the
    following elements:

      - current revision
      - column of the current node in the set of ongoing edges
      - color of the node (?)
      - lines; a list of (col, next_col, color) indicating the edges between
        the current row and the next row
      - parent revisions of current revision
      - author of the current revision

    If follow is True, only generated the subtree from the start_rev head.

    If branch is set, only generated the subtree for the given named branch. 

    If allparents is set, include the branch heads for the selected named
    branch heads and all ancestors. If not set, include only the revisions
    on the selected named branch.
    """
    assert start_rev is None or start_rev >= stop_rev
    curr_rev = start_rev
    revs = []
    rev_color = {}
    nextcolor = 0
    if allparents:
        getbranch = None
    else:
        getbranch = branch
    while curr_rev is None or curr_rev >= stop_rev:
        ctx = repo[curr_rev]
        # Compute revs and next_revs.
        if curr_rev not in revs:
            if branch:
                if ctx.branch() != branch:
                    if curr_rev is None:
                        curr_rev = len(repo)
                    else:
                        curr_rev -= 1
                    yield None
                    continue
                    
            # New head.
            if start_rev and follow and curr_rev != start_rev:
                curr_rev -= 1
                continue
            revs.append(curr_rev)
            rev_color[curr_rev] = curcolor = nextcolor
            nextcolor += 1
            p_revs = getparents(ctx, getbranch)
            while p_revs:
                rev0 = p_revs[0]
                if rev0 < stop_rev or rev0 in rev_color:
                    break
                rev_color[rev0] = curcolor
                p_revs = getparents(repo[rev0], getbranch)
        curcolor = rev_color[curr_rev]
        rev_index = revs.index(curr_rev)
        next_revs = revs[:]

        # Add parents to next_revs.
        parents = getparents(ctx, getbranch)
        try:
            author = ctx.user()
        except error.Abort:
            author = ''
        parents_to_add = []
        if len(parents) > 1:
            preferred_color = None
        else:
            preferred_color = curcolor
        for parent in parents:
            if parent not in next_revs:
                parents_to_add.append(parent)
                if parent not in rev_color:
                    if preferred_color:
                        rev_color[parent] = preferred_color
                        preferred_color = None
                    else:
                        rev_color[parent] = nextcolor
                        nextcolor += 1
            preferred_color = None

        # parents_to_add.sort()
        next_revs[rev_index:rev_index + 1] = parents_to_add

        lines = []
        for i, rev in enumerate(revs):
            if rev in next_revs:
                color = rev_color[rev]
                lines.append( (i, next_revs.index(rev), color) )
            elif rev == curr_rev:
                for parent in parents:
                    color = rev_color[parent]
                    lines.append( (i, next_revs.index(parent), color) )

        yield (curr_rev, rev_index, curcolor, lines, parents, author)
        revs = next_revs
        if curr_rev is None:
            curr_rev = len(repo)
        else:
            curr_rev -= 1


def filelog_grapher(repo, path):
    '''
    Graph the ancestry of a single file (log).  Deletions show
    up as breaks in the graph.
    '''
    filerev = len(repo.file(path)) - 1
    fctx = repo.filectx(path, fileid=filerev)
    rev = fctx.rev()

    flog = fctx.filelog()
    heads = [repo.filectx(path, fileid=flog.rev(x)).rev() for x in flog.heads()]
    assert rev in heads
    heads.remove(rev)

    revs = []
    rev_color = {}
    nextcolor = 0
    _paths = {}

    while rev >= 0:
        # Compute revs and next_revs
        if rev not in revs:
            revs.append(rev)
            rev_color[rev] = nextcolor ; nextcolor += 1
        curcolor = rev_color[rev]
        index = revs.index(rev)
        next_revs = revs[:]

        # Add parents to next_revs
        fctx = repo.filectx(_paths.get(rev, path), changeid=rev)
        for pfctx in fctx.parents():
            _paths[pfctx.rev()] = pfctx.path()
        parents = [pfctx.rev() for pfctx in fctx.parents()]# if f.path() == path]
        parents_to_add = []
        for parent in parents:
            if parent not in next_revs:
                parents_to_add.append(parent)
                if len(parents) > 1:
                    rev_color[parent] = nextcolor ; nextcolor += 1
                else:
                    rev_color[parent] = curcolor
        parents_to_add.sort()
        next_revs[index:index + 1] = parents_to_add

        lines = []
        for i, nrev in enumerate(revs):
            if nrev in next_revs:
                color = rev_color[nrev]
                lines.append( (i, next_revs.index(nrev), color) )
            elif nrev == rev:
                for parent in parents:
                    color = rev_color[parent]
                    lines.append( (i, next_revs.index(parent), color) )

        pcrevs = [pfc.rev() for pfc in fctx.parents()]
        yield (fctx.rev(), index, curcolor, lines, pcrevs,
               _paths.get(fctx.rev(), path), fctx.user())
        revs = next_revs

        if revs:
            rev = max(revs)
        else:
            rev = -1
        if heads and rev <= heads[-1]:
            rev = heads.pop()

def mq_patch_grapher(repo):
    """Graphs unapplied MQ patches"""
    for patchname in reversed(repo.thgmqunappliedpatches):
        yield (patchname, 0, "", [], [], "")

class GraphNode(object):
    """
    Simple class to encapsulate e hg node in the revision graph. Does
    nothing but declaring attributes.
    """
    def __init__(self, rev, xposition, color, lines, parents, ncols=None,
                 extra=None):
        self.rev = rev
        self.x = xposition
        self.color = color
        if ncols is None:
            ncols = len(lines)
        self.cols = ncols
        self.parents = parents
        self.bottomlines = lines
        self.toplines = []
        self.extra = extra

class Graph(object):
    """
    Graph object to ease hg repo navigation. The Graph object
    instanciate a `revision_grapher` generator, and provide a `fill`
    method to build the graph progressively.
    """
    #@timeit
    def __init__(self, repo, grapher, maxfilesize=100000, include_mq=False):
        self.maxfilesize = maxfilesize
        self.repo = repo
        self.maxlog = len(repo)
        if include_mq:
            patch_grapher = mq_patch_grapher(self.repo)
            self.grapher = itertools.chain(patch_grapher, grapher)
        else:
            self.grapher = grapher
        self.nodes = []
        self.nodesdict = {}
        self.max_cols = 0
        self.authors = set()

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            # XXX TODO: ensure nodes are built
            return self.nodes.__getitem__(idx)
        if idx >= len(self.nodes):
            # build as many graph nodes as required to answer the
            # requested idx
            self.build_nodes(idx)
        if idx > len(self):
            return self.nodes[-1]
        return self.nodes[idx]

    def __len__(self):
        # len(graph) is the number of actually built graph nodes
        return len(self.nodes)

    def build_nodes(self, nnodes=None, rev=None):
        """
        Build up to `nnodes` more nodes in our graph, or build as many
        nodes required to reach `rev`.

        If both rev and nnodes are set, build as many nodes as
        required to reach rev plus nnodes more.
        """
        if self.grapher is None:
            return False

        usetimer = nnodes is None and rev is None
        if usetimer:
            if os.name == "nt":
                timer = time.clock
            else:
                timer = time.time
            startsec = timer()

        stopped = False
        mcol = [self.max_cols]

        for vnext in self.grapher:
            if vnext is None:
                continue
            nrev, xpos, color, lines, parents, author = vnext[:6]
            self.authors.add(author)
            if not type(nrev) == str and nrev >= self.maxlog:
                continue
            gnode = GraphNode(nrev, xpos, color, lines, parents,
                              extra=vnext[5:])
            if self.nodes:
                gnode.toplines = self.nodes[-1].bottomlines
            self.nodes.append(gnode)
            self.nodesdict[nrev] = gnode
            mcol.append(gnode.cols)
            if rev is not None and nrev <= rev:
                rev = None # we reached rev, switching to nnode counter
            if rev is None:
                if nnodes is not None:
                    nnodes -= 1
                    if not nnodes:
                        break
            if usetimer:
                cursec = timer()
                if cursec < startsec or cursec > startsec + 0.1:
                    break
        else:
            self.grapher = None
            stopped = True

        self.max_cols = max(mcol)
        return not stopped

    def isfilled(self):
        return self.grapher is None

    def index(self, rev):
        if len(self) == 0: # graph is empty, let's build some nodes
            self.build_nodes(10)
        if rev is not None and rev < self.nodes[-1].rev:
            self.build_nodes(self.nodes[-1].rev - rev)
        if rev in self.nodesdict:
            return self.nodes.index(self.nodesdict[rev])
        return -1

    #
    # File graph method
    #

    def filename(self, rev):
        return self.nodesdict[rev].extra[0]

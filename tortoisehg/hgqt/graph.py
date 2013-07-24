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
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""helper functions and classes to ease hg revision graph building

Based on graphlog's algorithm, with inspiration stolen from TortoiseHg
revision grapher (now stolen back).

The primary interface are the *_grapher functions, which are generators
of Graph instances that describe a revision set graph. These generators
are used by repomodel.py which renders them on a widget.
"""

import time
import os
import itertools

from mercurial import repoview

LINE_TYPE_PARENT = 0
LINE_TYPE_GRAFT = 1

def revision_grapher(repo, **opts):
    """incremental revision grapher

    param repo       The repository
    opt   start_rev  Tip-most revision of range to graph
    opt   stop_rev   0-most revision of range to graph
    opt   follow     True means graph only ancestors of start_rev
    opt   revset     set of revisions to graph.
                     If used, then start_rev, stop_rev, and follow is ignored
    opt   branch     Only graph this branch
    opt   allparents If set in addition to branch, then cset outside the
                     branch that are ancestors to some cset inside the branch
                     is also graphed

    This generator function walks through the revision history from
    revision start_rev to revision stop_rev (which must be less than
    or equal to start_rev) and for each revision emits tuples with the
    following elements:

      - current revision
      - column of the current node in the set of ongoing edges
      - color of the node (?)
      - lines: a list of (col, next_col, color_no, line_type, children, parent)
          children: tuple of revs which connected to top of this line.
                    (or current rev if node is on the line.)
          parent:   rev which connected to bottom of this line.
        defining the edges between the current row and the next row
      - parent revisions of current revision
    """

    revset = opts.get('revset', None)
    branch = opts.get('branch', None)
    showhidden = opts.get('showhidden', None)
    if showhidden:
        revhidden = []
    else:
        revhidden = repoview.filterrevs(repo, 'visible')
    if revset:
        start_rev = max(revset)
        stop_rev = min(revset)
        follow = False
        hidden = lambda rev: (rev not in revset) or (rev in revhidden)
    else:
        start_rev = opts.get('start_rev', None)
        stop_rev = opts.get('stop_rev', 0)
        follow = opts.get('follow', False)
        hidden = lambda rev: rev in revhidden

    assert start_rev is None or start_rev >= stop_rev

    curr_rev = start_rev
    revs = []
    children = [()]
    links = [] # smallest link type that applies

    if opts.get('allparents') or not branch:
        def getparents(ctx):
            return [x for x in ctx.parents() if x]
    else:
        def getparents(ctx):
            return [x for x in ctx.parents()
                    if x and x.branch() == branch]

    rev_color = RevColorPalette(getparents)

    while curr_rev is None or curr_rev >= stop_rev:
        if hidden(curr_rev):
            curr_rev -= 1
            continue

        # Compute revs and next_revs.
        ctx = repo[curr_rev]
        if curr_rev not in revs:
            if branch and ctx.branch() != branch:
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
            links.append(LINE_TYPE_PARENT)
            children.append(())
            rev_color.addheadctx(ctx)
        curcolor = rev_color[curr_rev]
        rev_index = revs.index(curr_rev)
        next_revs = revs[:]
        next_links = links[:]
        next_children = children[:]

        # Add parents to next_revs.
        parents = [(p.rev(), LINE_TYPE_PARENT) for p in getparents(ctx)
                   if not hidden(p.rev())]
        if 'source' in ctx.extra():
            src_rev_str = ctx.extra()['source']
            if src_rev_str in repo:
                src_rev = repo[src_rev_str].rev()
                if stop_rev <= src_rev < curr_rev and not hidden(src_rev):
                    parents.append((src_rev, LINE_TYPE_GRAFT))
        parents_to_add = []
        links_to_add = []
        children_to_add = []
        if len(parents) > 1:
            preferred_color = None
        else:
            preferred_color = curcolor
        for parent, link_type in parents:
            if parent not in next_revs:
                parents_to_add.append(parent)
                links_to_add.append(link_type)
                children_to_add.append((curr_rev,))
                if parent not in rev_color:
                    rev_color.assigncolor(parent, preferred_color)
                    preferred_color = None
            else:
                # Merging lines should have the most solid style
                #  (= lowest style value)
                i = next_revs.index(parent)
                next_links[i] = min(next_links[i], link_type)
                next_children[i] += (curr_rev,)
            preferred_color = None

        # parents_to_add.sort()
        next_revs[rev_index:rev_index + 1] = parents_to_add
        next_links[rev_index:rev_index + 1] = links_to_add
        next_children[rev_index:rev_index + 1] = children_to_add

        lines = []
        for i, rev in enumerate(revs):
            if rev in next_revs:
                color = rev_color[rev]
                lines.append((i, next_revs.index(rev), color, links[i],
                              children[i], rev))
            elif rev == curr_rev:
                for parent, link_type in parents:
                    color = rev_color[parent]
                    lines.append((i, next_revs.index(parent), color, link_type,
                                  (curr_rev,), parent))

        yield GraphNode(curr_rev, rev_index, curcolor, lines, parents)
        revs = next_revs
        links = next_links
        children = next_children
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
    children = [()]
    rev_color = {}
    nextcolor = 0
    _paths = {}

    while rev >= 0:
        # Compute revs and next_revs
        if rev not in revs:
            revs.append(rev)
            rev_color[rev] = nextcolor ; nextcolor += 1
            children.append(())
        curcolor = rev_color[rev]
        index = revs.index(rev)
        next_revs = revs[:]
        next_children = children[:]

        # Add parents to next_revs
        fctx = repo.filectx(_paths.get(rev, path), changeid=rev)
        for pfctx in fctx.parents():
            _paths[pfctx.rev()] = pfctx.path()
        parents = [pfctx.rev() for pfctx in fctx.parents()]
                   # if f.path() == path]
        parents_to_add = []
        children_to_add = []
        for parent in parents:
            if parent not in next_revs:
                parents_to_add.append(parent)
                children_to_add.append((rev,))
                if len(parents) > 1:
                    rev_color[parent] = nextcolor ; nextcolor += 1
                else:
                    rev_color[parent] = curcolor
        parents_to_add.sort()
        next_revs[index:index + 1] = parents_to_add
        next_children[index:index + 1] = children_to_add

        lines = []
        for i, nrev in enumerate(revs):
            if nrev in next_revs:
                color = rev_color[nrev]
                lines.append((i, next_revs.index(nrev), color, LINE_TYPE_PARENT,
                              children[i], nrev))
            elif nrev == rev:
                for parent in parents:
                    color = rev_color[parent]
                    lines.append((i, next_revs.index(parent), color,
                                  LINE_TYPE_PARENT, (rev,), parent))

        pcrevs = [pfc.rev() for pfc in fctx.parents()]
        yield GraphNode(fctx.rev(), index, curcolor, lines, pcrevs,
                        extra=[_paths.get(fctx.rev(), path)])
        revs = next_revs
        children = next_children

        if revs:
            rev = max(revs)
        else:
            rev = -1
        if heads and rev <= heads[-1]:
            rev = heads.pop()

def mq_patch_grapher(repo):
    """Graphs unapplied MQ patches"""
    for patchname in reversed(repo.thgmqunappliedpatches):
        yield GraphNode(patchname, 0, "", [], [])

class RevColorPalette(object):
    """Assign node and line colors for each revision"""

    def __init__(self, getparents):
        self._getparents = getparents
        self._pendingheads = []
        self._knowncolors = {}
        self._nextcolor = 0

    def addheadctx(self, ctx):
        color = self.assigncolor(ctx.rev())
        p_ctxs = self._getparents(ctx)
        self._pendingheads.append((p_ctxs, color))

    def _fillpendingheads(self, stoprev):
        if stoprev is None:
            return  # avoid filling everything (int_rev < None is False)

        nextpendingheads = []
        for p_ctxs, color in self._pendingheads:
            pending = self._fillancestors(p_ctxs, color, stoprev)
            if pending:
                nextpendingheads.append((pending, color))
        self._pendingheads = nextpendingheads

    def _fillancestors(self, p_ctxs, curcolor, stoprev):
        while p_ctxs:
            ctx0 = p_ctxs[0]
            rev0 = ctx0.rev()
            if rev0 < stoprev:
                return p_ctxs
            if rev0 in self._knowncolors:
                return
            self._knowncolors[rev0] = curcolor
            p_ctxs = self._getparents(ctx0)

    def assigncolor(self, rev, color=None):
        self._fillpendingheads(rev)
        if color is None:
            color = self._nextcolor
            self._nextcolor += 1
        self._knowncolors[rev] = color
        return color

    def __getitem__(self, rev):
        self._fillpendingheads(rev)
        return self._knowncolors[rev]

    def __contains__(self, rev):
        self._fillpendingheads(rev)
        return rev in self._knowncolors

class GraphNode(object):
    """
    Simple class to encapsulate a hg node in the revision graph. Does
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
    instantiate a `revision_grapher` generator, and provide a `fill`
    method to build the graph progressively.
    """
    #@timeit
    def __init__(self, repo, grapher, include_mq=False):
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

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            # XXX TODO: ensure nodes are built
            return self.nodes.__getitem__(idx)
        if idx >= len(self.nodes):
            # build as many graph nodes as required to answer the
            # requested idx
            self.build_nodes(idx)
        if idx >= len(self):
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
        mcol = set([self.max_cols])

        for gnode in self.grapher:
            if gnode is None:
                continue
            if not type(gnode.rev) == str and gnode.rev >= self.maxlog:
                continue
            if self.nodes:
                gnode.toplines = self.nodes[-1].bottomlines
            self.nodes.append(gnode)
            self.nodesdict[gnode.rev] = gnode
            mcol = mcol.union(set([gnode.x]))
            mcol = mcol.union(set([max(x[:2]) for x in gnode.bottomlines]))
            if rev is not None and gnode.rev <= rev:
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

        self.max_cols = max(mcol) + 1
        return not stopped

    def isfilled(self):
        return self.grapher is None

    def index(self, rev):
        if len(self) == 0: # graph is empty, let's build some nodes
            self.build_nodes(10)
        if rev is not None and len(self) > 0 and rev < self.nodes[-1].rev:
            self.build_nodes(self.nodes[-1].rev - rev)
        if rev in self.nodesdict:
            return self.nodes.index(self.nodesdict[rev])
        return -1

    #
    # File graph method
    #

    def filename(self, rev):
        return self.nodesdict[rev].extra[0]

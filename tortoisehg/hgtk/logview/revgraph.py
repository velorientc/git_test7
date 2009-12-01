"""Directed graph production.

This module contains the code to produce an ordered directed graph of a
Mercurial repository, such as we display in the tree view at the top of the
history window.  Original code was from graphlog extension.

The generator functions walks through the revision history and for the
selected revision emits tuples with the following elements:
    
       (curr_rev, node, lines, parents)

  - Current revision.
  - node; defined as tuple (rev_column, rev_color)
  - lines; a list of (col, next_col, color, type) indicating the edges between
    the current row and the next row
  - parent revisions of current revision
  
The node tuple has the following elements:
  - rev_column: Column for the node "circle"
  - rev_color: Color used to render the circle
  - rev_status: 
        0 for normal circle, 
        1 for add up arrow (outgoing cset)
        2 for add star (new cset)
        3 for add down arrow (incoming cset)
        All above +4 for larger circle = current workdir parent
      
The lines tuple has the following elements:
  - col: Column for the upper end of the line.
  - nextcol: Column for the lower end of the line.
  - color: Colour used for line
  - type: 0 for plain line, 1 for loose upper end, 2 for loose lower end
    loose ends are rendered as dashed lines. They indicate that the
    edge of the graph does not really end here. This is used to render 
    a branch view where the focus is on branches instead of revisions.
    
The data is used in treeview.populate with the following signature
    (rev, node, lines, parents) = self.grapher.next()
and stored in treeview.graphdata

The treeview.model is an instance of treemodel which references 
treeview.graphdata

treemodel stores it in self.line_graph_data, and extracts it 
in on_get_value, where it is mapped to several columns.
    REVID, NODE, LINES, PARENTS, LAST_LINES
LAST_LINES is a copy of LINES from the previous row

treeview maps columns 
    treemodel.NODE, treemodel.LAST_LINES, treemodel.LINES
to CellRendererGraph attributes
    "node", "in-lines", "out-lines"
which stores it in varables
    node, in_lines, out_lines
"""

__copyright__ = "Copyright 2007 Joel Rosdahl, 2008 Steve Borho"
__author__    = "Joel Rosdahl <joel@rosdahl.net>, Steve Borho <steve@borho.org>"

import re

from mercurial.node import nullrev
from mercurial import cmdutil, util, match

from tortoisehg.util import hglib

def __get_parents(repo, rev):
    return [x for x in repo.changelog.parentrevs(rev) if x != nullrev]

known_branch_colors = {} # cache for repository colour configuration

def _get_known_branch_colors(repo):
    global known_branch_colors

    repo_setting = repo.ui.config('tortoisehg', 'branchcolors')

    if known_branch_colors:
        branch_colors, setting = known_branch_colors
        if repo_setting == setting:
            return branch_colors

    branchcolors = repo_setting
    if not branchcolors:
        return {}

    branchcolors = hglib.tounicode(branchcolors)
    branchcolors = [x for x in re.split(r'(?:(?<=\\\\)|(?<!\\)) ', branchcolors) if x]
    values = {}
    for branchcolor in branchcolors:
        parts = re.split(r'(?:(?<=\\\\)|(?<!\\)):', branchcolor)
        if len(parts) != 2:
            continue # ignore badly formed entry

        # Mercurial branch names are encoded in utf-8 so we must
        # make sure to encode back to that after having unescaped
        # the string.
        branch_name = hglib.toutf(parts[0].replace('\\:', ':').replace('\\ ', ' ').decode('unicode_escape'))
        values[branch_name] = hglib.toutf(parts[1])

    known_branch_colors = values, repo_setting
    return values

def _color_of_branch(repo, rev):
    branch = repo[rev].branch()

    candidates = _get_known_branch_colors(repo)

    if branch in candidates:
        return candidates[branch]

    if branch == 'default':
        color = 0
    else:
        color = sum([ord(c) for c in branch])
    return color

def _color_of(repo, rev, nextcolor, preferredcolor, branch_color=False):
    if not branch_color:
        if preferredcolor[0]:
            rv = preferredcolor[0]
            preferredcolor[0] = None
        else:
            rv = nextcolor[0]
            nextcolor[0] = nextcolor[0] + 1
        return rv
    else:
        return _color_of_branch(repo, rev)

type_PLAIN = 0
type_LOOSE_LOW = 1
type_LOOSE_HIGH = 2

def revision_grapher(repo, start_rev, stop_rev, branch=None, noheads=False, branch_color=False):
    """incremental revision grapher

    This grapher generates a full graph where every edge is visible.
    This means that repeated merges between two branches may make
    the graph very wide.
    
    if branch is set to the name of a branch, only this branch is shown.
    if noheads is True, other heads than start_rev is hidden. Use this
    to show ancestors of a revision.
    if branch_color is True, the branch colour is determined by a hash
    of the branch tip, and will thus always be the same.
    """

    assert start_rev >= stop_rev
    curr_rev = start_rev
    revs = []
    rev_color = {}
    nextcolor = [0]
    while curr_rev >= stop_rev:
        # Compute revs and next_revs.
        if curr_rev not in revs:
            if noheads and curr_rev != start_rev:
                curr_rev -= 1
                continue
            if branch:
                ctx = repo.changectx(curr_rev)
                if ctx.branch() != branch:
                    curr_rev -= 1
                    continue
            # New head.
            revs.append(curr_rev)
            rev_color[curr_rev] = _color_of(repo, curr_rev, nextcolor, [None], branch_color)
            r = __get_parents(repo, curr_rev)
            while r:
                r0 = r[0]
                if r0 < stop_rev: break
                if r0 in rev_color: break
                if not branch_color:
                    rev_color[r0] = rev_color[curr_rev]
                else:
                    rev_color[r0] = _color_of(repo, r0, None, None, True)
                r = __get_parents(repo, r0)
        rev_index = revs.index(curr_rev)
        next_revs = revs[:]

        # Add parents to next_revs.
        parents = __get_parents(repo, curr_rev)
        parents_to_add = []
        preferred_color = [rev_color[curr_rev]]
        for parent in parents:
            if parent not in next_revs:
                parents_to_add.append(parent)
                if parent not in rev_color:
                    rev_color[parent] = _color_of(repo, parent, nextcolor, preferred_color, branch_color)
        next_revs[rev_index:rev_index + 1] = parents_to_add

        lines = []
        for i, rev in enumerate(revs):
            if rev in next_revs:
                color = rev_color[rev]
                lines.append( (i, next_revs.index(rev), color, type_PLAIN) )
            elif rev == curr_rev:
                for parent in parents:
                    color = rev_color[parent]
                    lines.append( (i, next_revs.index(parent), color, type_PLAIN) )

        yield (curr_rev, (rev_index, rev_color[curr_rev]), lines, None)
        revs = next_revs
        curr_rev -= 1


class BranchGrapher:
    """Incremental branch grapher

    This generator function produces a graph that uses loose ends to keep
    focus on branches. All revisions in the range are shown, but not all edges.
    The function identifies branches and may use loose ends if an edge links
    two branches.
    """
    
    def __init__(self, repo, start_rev, stop_rev, branch_filter, branch_color):
        ''' 
        start_rev - first (newest) changeset to cover
        stop_rev - last (oldest) changeset to cover
        branch_filter - if not None, show this branch and all its ancestors
        branch_color - true if branch name determines colours
        '''
        assert start_rev >= stop_rev
        self.repo = repo
        
        #
        #  Iterator content
        #  Variables that keep track of the iterator
        #
        
        # The current revision to process
        self.curr_rev = start_rev
        
        # Process all revs from start_rev to and including stop_rev
        self.stop_rev = stop_rev

        # List current branches. For each branch the next rev is listed
        # The order of branches determine their columns
        self.curr_branches = [start_rev]
        
        # For each branch, tell the next version that will show up
        self.next_in_branch = {}
        
        #
        #  Graph variables
        #  These hold information related to the graph. Most are computed lazily.
        #  The graph is split into a number of "branches", defined as paths within
        #  a named branch.
        #
        
        # Map rev to next rev in branch = parent with same branch name
        # If two parents, use first that has same branch name.
        # The parent of last rev in a branch is undefined, 
        # even if the revsion has a parent rev.
        self.parent_of = {}
        
        # Map rev to newest rev in branch. This identifies the branch that the rev
        # is part of
        self.branch4rev = {}
        
        # Last revision in branch
        self.branch_tail = {}
        
        # Map branch-id (head-rev of branch) to color
        self.color4branch = {}
        
        # Next colour used. for branches
        self.nextcolor = 0
        
        # If set, show only this branch and all descendants.
        self.branch_filter = branch_filter
        
        # Flag to indicate if coloring is done pr micro-branch or pr named branch
        self.branch_color = branch_color

    def _get_parents(self, rev):
        return [x for x in self.repo.changelog.parentrevs(rev) if x != nullrev]
        
    def _branch_name(self, rev):
        return self.repo[rev].branch()
        
    def _covered_rev(self, rev):
        """True if rev is inside the revision range for the iterator"""
        return self.stop_rev <= rev
        
    def _new_branch(self, branch_head):
        """Mark all unknown revisions in range that are direct ancestors
        of branch_head as part of the same branch. Stops when stop_rev
        is passed or a known revision is found"""
        assert not branch_head in self.branch4rev
        if self.branch_color:
            self.color4branch[branch_head] = \
                _color_of_branch(self.repo, branch_head)
        else:
            self.color4branch[branch_head] = self.nextcolor
            self.nextcolor += 1
        self.next_in_branch[branch_head] = branch_head
        branch_name = self._branch_name(branch_head)
        rev = branch_head
        while not rev in self.branch4rev:
            # Add rev to branch
            self.branch4rev[rev] = branch_head
            self.branch_tail[branch_head] = rev
            # Exit if rev is outside visible range
            if not self._covered_rev(rev):
                # rev is outside visible range, so we don't know tail location
                self.branch_tail[branch_head] = 0 # Prev revs wasn't tail
                return
            # Find next revision in branch
            self.parent_of[rev] = None
            for parent in self._get_parents(rev):
                if self._branch_name(parent) == branch_name:
                    self.parent_of[rev] = parent
                    break
            if self.parent_of[rev] is None:
                return
            rev = self.parent_of[rev]

    def _get_rev_branch(self, rev):
        """Find revision branch or create a new branch"""
        branch = self.branch4rev.get(rev)
        if branch is None:
            branch = rev
            self._new_branch(branch)
        assert rev in self.branch4rev
        assert branch in self.branch_tail
        return branch
        
    def _compute_next_branches(self):
        """Compute next row of branches"""
        next_branches = self.curr_branches[:]
        # Find branch used by current revision
        curr_branch = self._get_rev_branch(self.curr_rev)
        self.next_in_branch[curr_branch] = self.parent_of[self.curr_rev]
        branch_index = self.curr_branches.index(curr_branch)
        # Insert branches if parents point to new branches
        new_parents = 0
        for parent in self._get_parents(self.curr_rev):
            branch = self._get_rev_branch(parent)
            if not branch in next_branches:
                new_parents += 1
                next_branches.insert(branch_index + new_parents, branch)
        # Delete branch if last revision
        if self.curr_rev == self.branch_tail[curr_branch]:
            del next_branches[branch_index]
        # Return result
        return next_branches
    
    def _rev_color(self, rev):
        """Map a revision to a color"""
        return self.color4branch[self.branch4rev[rev]]

    def _compute_lines(self, parents, next_branches):
        # Compute lines (from CUR to NEXT branch row)
        lines = []
        curr_rev_branch = self.branch4rev[self.curr_rev]
        for curr_column, branch in enumerate(self.curr_branches):
            if branch == curr_rev_branch:
                # Add lines from current branch to parents
                for par_rev in parents:
                    par_branch = self._get_rev_branch(par_rev)
                    color = self.color4branch[par_branch]
                    next_column = next_branches.index(par_branch)
                    line_type = type_PLAIN
                    if par_rev != self.next_in_branch.get(par_branch):
                        line_type = type_LOOSE_LOW
                    lines.append( (curr_column, next_column, color, line_type) )
            else:
                # Continue unrelated branch
                color = self.color4branch[branch]
                next_column = next_branches.index(branch)
                lines.append( (curr_column, next_column, color, type_PLAIN) )
        return lines
        
    def more(self):
        return self.curr_rev >= self.stop_rev
        
    def next(self):
        """Perform one iteration of the branch grapher"""
        
        # Compute revision (on CUR branch row)
        while self.more():
            rev = self.curr_rev
            rev_branch = self._get_rev_branch(rev)
            if rev_branch in self.curr_branches:
                # Follow parent from known child
                break
            elif self.branch_filter is None:
                # New head - no branch name filter
                self.curr_branches.append(rev_branch)
                break
            elif self._branch_name(rev) == self.branch_filter:
                # New head - matches branch name filter
                self.curr_branches.append(rev_branch)
                break
            else:
                # Skip this revision
                self.curr_rev -= 1
        
        # Compute parents (indicates the branches on NEXT branch row that curr_rev links to)
        parents = self._get_parents(rev)
        # BUG: __get_parents is not defined - why?
        
        # Compute lines (from CUR to NEXT branch row)
        next_branches = self._compute_next_branches()
        lines = self._compute_lines(parents, next_branches)
        
        # Compute node info (for CUR branch row)
        rev_column = self.curr_branches.index(rev_branch)
        rev_color = self.color4branch[rev_branch]
        node = (rev_column, rev_color)
        
        # Next loop
        self.curr_branches = next_branches
        self.curr_rev -= 1
        
        # Return result
        return (rev, node, lines, None)
    
def branch_grapher(repo, start_rev, stop_rev, branch=None, branch_color=False):
    grapher = BranchGrapher(repo, start_rev, stop_rev, branch, branch_color)
    while grapher.more():
        yield grapher.next()            


def filelog_grapher(repo, path):
    '''
    Graph the ancestry of a single file (log).  Deletions show
    up as breaks in the graph.
    '''
    fctx = repo.file(path)
    if not len(fctx):
        return
    paths = { path : len(fctx)-1 }
    revs = []
    rev_color = {}
    nextcolor = 0
    type = type_PLAIN
    while paths:

        # pick largest revision from known filenames
        fctx = None
        for path, filerev in paths.iteritems():
            f = repo.filectx(path, fileid=filerev)
            if not fctx or f.rev() > fctx.rev():
                fctx = f

        # Compute revs and next_revs.
        if fctx.rev() not in revs:
            revs.append(fctx.rev())
            rev_color[fctx.rev()] = nextcolor ; nextcolor += 1
        curcolor = rev_color[fctx.rev()]
        index = revs.index(fctx.rev())
        next_revs = revs[:]

        # Add parents to next_revs.
        parents_to_add = []
        for pfctx in fctx.parents():
            if pfctx.path() != fctx.path():
                continue
            if pfctx.rev() not in next_revs:
                parents_to_add.append(pfctx.rev())
                if len(fctx.parents()) > 1:
                    rev_color[pfctx.rev()] = nextcolor ; nextcolor += 1
                else:
                    rev_color[pfctx.rev()] = curcolor

        ret = fctx.renamed()
        if ret:
            renpath, fnode = ret
            flog = repo.file(renpath)
            filerev = flog.rev(fnode)
            paths[renpath] = filerev
            rfctx = repo.filectx(renpath, fileid=filerev)
            if rfctx.rev() not in revs:
                parents_to_add.append(rfctx.rev())
                rev_color[rfctx.rev()] = nextcolor ; nextcolor += 1

        parents_to_add.sort()
        next_revs[index:index + 1] = parents_to_add

        lines = []
        for i, rev in enumerate(revs):
            if rev in next_revs:
                color = rev_color[rev]
                lines.append((i, next_revs.index(rev), color, type))
            elif rev == fctx.rev():
                for pfctx in fctx.parents():
                    color = rev_color[pfctx.rev()]
                    lines.append((i, next_revs.index(pfctx.rev()), color, type))

        if fctx.filerev() == 0:
            del paths[fctx.path()]
        else:
            paths[fctx.path()] = fctx.filerev()-1
        revs = next_revs
        yield (fctx.rev(), (index, curcolor), lines, fctx.path())



def dumb_log_generator(repo, revs):
    for revname in revs:
        node = repo.lookup(revname)
        rev = repo.changelog.rev(node)
        yield (rev, (0,0), [], None)

def filtered_log_generator(repo, pats, opts):
    '''Fill view model iteratively
       repo - Mercurial repository object
       pats - list of file names or patterns
       opts - command line options for log command
    '''
    matching_revs = []
    only_branch = opts.get('branch', None)
    df = False
    if opts['date']:
        df = util.matchdate(opts['date'])

    def prep(ctx, fns):
        if only_branch and ctx.branch() != only_branch:
            return
        if opts['no_merges'] and len(ctx.parents()) == 2:
            return
        if opts['only_merges'] and len(ctx.parents()) != 2:
            return
        if df and not df(ctx.date()[0]):
            return
        if opts['user'] and not [k for k in opts['user'] if k in ctx.user()]:
            return
        if opts['keyword']:
            for k in [kw.lower() for kw in opts['keyword']]:
                if (k in ctx.user().lower() or
                    k in ctx.description().lower() or
                    k in " ".join(ctx.files()).lower()):
                    break
            else:
                return
        matching_revs.append(ctx.rev())

    m = match.match(repo.root, repo.root, pats)
    for ctx in cmdutil.walkchangerevs(repo, m, opts, prep):
        if ctx.rev() in matching_revs:
            yield (ctx.rev(), (0,0), [], None)

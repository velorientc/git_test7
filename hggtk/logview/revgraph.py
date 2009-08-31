"""Directed graph production.

This module contains the code to produce an ordered directed graph of a
Mercurial repository, such as we display in the tree view at the top of the
history window.  Original code was from graphlog extension.

The generator functions walks through the revision history and for the
selected revision emits tuples with the following elements:
    
       (curr_rev, node, lines, parents)

  - Current revision.
  - node; defined as tuple (rev_column, rev_color)
  - lines; a list of (col, next_col, color) indicating the edges between
    the current row and the next row
  - parent revisions of current revision
  
The node tuple has the following elements:
  - rev_column: Column for the node "circle"
  - rev_color: Color used to render the circle
      
The lines tuple has the following elements:
  - col: Column for the upper end of the line.
  - nextcol: Column for the lower end of the line.
  - color: Colour used for line
    
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

from mercurial.node import nullrev
from mercurial import cmdutil, util

def __get_parents(repo, rev):
    return [x for x in repo.changelog.parentrevs(rev) if x != nullrev]

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
        return sum([ord(c) for c in repo[rev].branch()])

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
                lines.append( (i, next_revs.index(rev), color) )
            elif rev == curr_rev:
                for parent in parents:
                    color = rev_color[parent]
                    lines.append( (i, next_revs.index(parent), color) )

        yield (curr_rev, (rev_index, rev_color[curr_rev]), lines, parents)
        revs = next_revs
        curr_rev -= 1


def filelog_grapher(repo, path):
    '''
    Graph the ancestry of a single file (log).  Deletions show
    up as breaks in the graph.
    '''
    filerev = len(repo.file(path)) - 1
    revs = []
    rev_color = {}
    nextcolor = 0
    while filerev >= 0:
        fctx = repo.filectx(path, fileid=filerev)

        # Compute revs and next_revs.
        if filerev not in revs:
            revs.append(filerev)
            rev_color[filerev] = nextcolor ; nextcolor += 1
        curcolor = rev_color[filerev]
        index = revs.index(filerev)
        next_revs = revs[:]

        # Add parents to next_revs.
        parents = [f.filerev() for f in fctx.parents() if f.path() == path]
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
        for i, rev in enumerate(revs):
            if rev in next_revs:
                color = rev_color[rev]
                lines.append( (i, next_revs.index(rev), color) )
            elif rev == filerev:
                for parent in parents:
                    color = rev_color[parent]
                    lines.append( (i, next_revs.index(parent), color) )

        pcrevs = [pfc.rev() for pfc in fctx.parents()]
        yield (fctx.rev(), (index, curcolor), lines, pcrevs)
        revs = next_revs
        filerev -= 1


def dumb_log_generator(repo, revs):
    for revname in revs:
        node = repo.lookup(revname)
        rev = repo.changelog.rev(node)
        yield (rev, (0,0), [], __get_parents(repo, rev))

def filtered_log_generator(repo, pats, opts):
    '''Fill view model iteratively
       repo - Mercurial repository object
       pats - list of file names or patterns
       opts - command line options for log command
    '''
    # Log searches: pattern, keyword, date, etc
    df = False
    if opts['date']:
        df = util.matchdate(opts['date'])

    stack = []
    get = util.cachefunc(lambda r: repo.changectx(r).changeset())
    pats = ['path:'+p for p in pats]
    changeiter, matchfn = cmdutil.walkchangerevs(repo.ui, repo, pats, get, opts)
    for st, rev, fns in changeiter:
        if st == 'iter':
            if stack:
                yield stack.pop()
            continue
        if st != 'add':
            continue
        parents = __get_parents(repo, rev)
        if opts['no_merges'] and len(parents) == 2:
            continue
        if opts['only_merges'] and len(parents) != 2:
            continue

        if df:
            changes = get(rev)
            if not df(changes[2][0]):
                continue

        # TODO: add copies/renames later
        if opts['keyword']:
            changes = get(rev)
            miss = 0
            for k in [kw.lower() for kw in opts['keyword']]:
                if not (k in changes[1].lower() or
                        k in changes[4].lower() or
                        k in " ".join(changes[3]).lower()):
                    miss = 1
                    break
            if miss:
                continue
        stack.append((rev, (0,0), [], parents))

"""Directed graph production.

This module contains the code to produce an ordered directed graph of a
Mercurial repository, such as we display in the tree view at the top of the
history window.  Original code was from graphlog extension.
"""

__copyright__ = "Copyright 2007 Joel Rosdahl"
__author__    = "Joel Rosdahl <joel@rosdahl.net>"

from mercurial.node import nullrev
from mercurial import cmdutil, util, ui

def revision_grapher(repo, start_rev, stop_rev):
    """incremental revision grapher

    This generator function walks through the revision history from
    revision start_rev to revision stop_rev (which must be less than
    or equal to start_rev) and for each revision emits tuples with the
    following elements:

      - Current revision.
      - lines; a list of (col, next_col, color) indicating the edges between
        the current row and the next row
      - Column of the current node in the set of ongoing edges.
      - parent revisions of current revision
    """

    assert start_rev >= stop_rev
    curr_rev = start_rev
    changelog = repo.changelog
    revs = []
    rev_color = {}
    nextcolor = 0
    while curr_rev >= stop_rev:
        node = changelog.node(curr_rev)

        # Compute revs and next_revs.
        if curr_rev not in revs:
            # New head.
            revs.append(curr_rev)
            rev_color[curr_rev] = nextcolor ; nextcolor += 1
        curcolor = rev_color[curr_rev]
        rev_index = revs.index(curr_rev)
        next_revs = revs[:]

        # Add parents to next_revs.
        parents = [x for x in changelog.parentrevs(curr_rev) if x != nullrev]
        parents_to_add = []
        for parent in parents:
            if parent not in next_revs:
                parents_to_add.append(parent)
                if len(parents) > 1:
                    rev_color[parent] = nextcolor ; nextcolor += 1
                else:
                    rev_color[parent] = curcolor
        parents_to_add.sort()
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

        yield (curr_rev, (rev_index, curcolor), lines, parents)

        revs = next_revs
        curr_rev -= 1

def filtered_log_generator(repo, revs, pats, opts):
    '''Fill view model iteratively
       repo - Mercurial repository object
       revs - list of revision specifiers (revno, hash, tags, etc)
       pats - list of file names or patterns
    '''
    def get_parents(rev):
        return [x for x in repo.changelog.parentrevs(rev) if x != nullrev]

    # User specified list of revisions, pretty easy
    for revname in revs:
        node = repo.lookup(revname)
        rev = repo.changelog.rev(node)
        yield (rev, (0,0), [], get_parents(rev))
    if revs: return

    # 'All revisions' filter, even easier
    if pats == [''] and not opts['keyword'] and not opts['date']:
        rev = repo.changelog.count()-1
        while rev >= 0:
            yield (rev, (0,0), [], get_parents(rev))
            rev = rev-1
        return

    # pattern, keyword, or date search.  respects merge, no_merge options
    # TODO: add copies/renames later
    df = False
    if opts['date']:
        df = util.matchdate(opts['date'])

    if not opts.has_key('merges'):
        opts['merges'] = None
    if not opts.has_key('no_merges'):
        opts['no_merges'] = None

    stack = []
    get = util.cachefunc(lambda r: repo.changectx(r).changeset())
    changeiter, matchfn = cmdutil.walkchangerevs(repo.ui, repo, pats, get, opts)
    for st, rev, fns in changeiter:
        if st == 'iter':
            if stack:
                yield stack.pop()
            continue
        if st != 'add':
            continue
        parents = get_parents(rev)
        if opts['no_merges'] and len(parents) == 2:
            continue
        if opts['merges'] and len(parents) != 2:
            continue

        if df:
            changes = get(rev)
            if not df(changes[2][0]):
                continue

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

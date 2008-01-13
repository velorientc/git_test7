"""Directed graph production.

This module contains the code to produce an ordered directed graph of a
Mercurial repository, such as we display in the tree view at the top of the
history window.  Original code was from graphlog extension.
"""

__copyright__ = "Copyright 2007 Joel Rosdahl"
__author__    = "Joel Rosdahl <joel@rosdahl.net>"

from mercurial.node import nullrev

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


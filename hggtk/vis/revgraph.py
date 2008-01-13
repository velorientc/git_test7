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
    while curr_rev >= stop_rev:
        node = changelog.node(curr_rev)

        # Compute revs and next_revs.
        if curr_rev not in revs:
            # New head.
            revs.append(curr_rev)
        rev_index = revs.index(curr_rev)
        next_revs = revs[:]

        # Add parents to next_revs.
        parents = [x for x in changelog.parentrevs(curr_rev) if x != nullrev]
        parents_to_add = []
        for parent in parents:
            if parent not in next_revs:
                parents_to_add.append(parent)
        parents_to_add.sort()
        next_revs[rev_index:rev_index + 1] = parents_to_add

        lines = []
        for i, rev in enumerate(revs):
            if rev in next_revs:
                lines.append( (i, next_revs.index(rev), 0) )
            elif rev == curr_rev:
                for parent in parents:
                    lines.append( (i, next_revs.index(parent), 0) )

        yield (curr_rev, lines, rev_index, parents)

        revs = next_revs
        curr_rev -= 1


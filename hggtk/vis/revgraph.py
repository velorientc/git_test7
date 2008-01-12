"""Directed graph production.

This module contains the code to produce an ordered directed graph of a
Mercurial repository, such as we display in the tree view at the top of the
history window.
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
      - Current node.
      - Column of the current node in the set of ongoing edges.
      - Edges; a list of (col, next_col) indicating the edges between
        the current node and its parents.
      - Number of columns (ongoing edges) in the current revision.
      - parent revisions of current revision
      - children revisions of current revision
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

        edges = []
        for parent in parents:
            edges.append((rev_index, next_revs.index(parent)))

        n_columns_diff = len(next_revs) - len(revs)
        yield (curr_rev, node, rev_index, edges, len(revs),
                n_columns_diff, parents)

        revs = next_revs
        curr_rev -= 1


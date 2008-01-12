''' Mercurial revision DAG visualization library

  Implements a gtk.TreeModel which visualizes a Mercurial repository
  revision history.

Portions of this code stolen mercilessly from bzr-gtk visualization
dialog.  Other portions stolen from graphlog extension.
'''

import gtk
import gobject
import re
from time import (strftime, localtime)
from mercurial.node import nullrev

# treemodel row enumerated attributes
REVID = 0
NODE = 1
LINES = 2
LAST_LINES = 3
MESSAGE = 4
COMMITER = 5
TIMESTAMP = 6
REVISION = 7
PARENTS = 8
CHILDREN = 9

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
      - current revision parents
      - current revision children
    """

    assert start_rev >= stop_rev
    curr_rev = start_rev
    revs = []
    while curr_rev >= stop_rev:
        node = repo.changelog.node(curr_rev)

        # Compute revs and next_revs.
        if curr_rev not in revs:
            # New head.
            revs.append(curr_rev)
        rev_index = revs.index(curr_rev)
        next_revs = revs[:]

        # Add parents to next_revs.
        parents = [x for x in repo.changelog.parentrevs(curr_rev) if x != nullrev]
        parents_to_add = []
        for parent in parents:
            if parent not in next_revs:
                parents_to_add.append(parent)
        parents_to_add.sort()
        next_revs[rev_index:rev_index + 1] = parents_to_add

        edges = []
        for parent in parents:
            edges.append((rev_index, next_revs.index(parent)))

        children = repo.changelog.children(node)
        yield (curr_rev, node, rev_index, edges, len(revs), parents, children)

        revs = next_revs
        curr_rev -= 1

class TreeModel(gtk.GenericTreeModel):

    def __init__ (self, repo, graph_generator):
        gtk.GenericTreeModel.__init__(self)
        self.revisions = {}
        self.repo = repo
        self.grapher = graph_generator
        self.line_graph_data = []

    def on_get_flags(self):
        return gtk.TREE_MODEL_LIST_ONLY

    def on_get_n_columns(self):
        return 11

    def on_get_column_type(self, index):
        if index == REVID: return gobject.TYPE_STRING
        if index == NODE: return gobject.TYPE_PYOBJECT
        if index == LINES: return gobject.TYPE_PYOBJECT
        if index == LAST_LINES: return gobject.TYPE_PYOBJECT
        if index == MESSAGE: return gobject.TYPE_STRING
        if index == COMMITER: return gobject.TYPE_STRING
        if index == TIMESTAMP: return gobject.TYPE_STRING
        if index == REVISION: return gobject.TYPE_PYOBJECT
        if index == PARENTS: return gobject.TYPE_PYOBJECT
        if index == CHILDREN: return gobject.TYPE_PYOBJECT

    def on_get_iter(self, path):
        return path[0]

    def on_get_path(self, rowref):
        return rowref

    def on_get_value(self, rowref, column):
        (revid, node, lines, parents, children) = self.line_graph_data[rowref]

        if column == REVID: return revid
        if column == NODE: return node
        if column == LINES: return lines
        if column == PARENTS: return parents
        if column == CHILDREN: return children
        if column == LAST_LINES:
            if rowref>0:
                return self.line_graph_data[rowref-1][2]
            return []

        if revid not in self.revisions:
            # TODO: not sure about this
            ctx = self.repo.changectx(revid)
            revision = (ctx.user(), ctx.date(), ctx.description())
            self.revisions[revid] = revision
        else:
            revision = self.revisions[revid]

        if column == REVISION: return revision
        if column == MESSAGE: return revision[2].split('\n')[0]
        if column == COMMITER: return re.sub('<.*@.*>', '',
                                             revision[0]).strip(' ')
        if column == TIMESTAMP:
            return strftime("%Y-%m-%d %H:%M", localtime(revision[1][0]))

    def on_iter_next(self, rowref):
        # Dynamically generate graph rows on demand
        while rowref >= len(self.line_graph_data)-1:
            try:
                (rev, node, node_index, edges,
                    n_columns, parents, children) = self.grapher.next()
            except StopIteration:
                break
            # TODO: add color later on
            lines = [(s, e, 0) for (s, e) in edges]
            self.line_graph_data.append( (rev, (node_index, 0),
                lines, parents, children) )
        if rowref < len(self.line_graph_data) - 1:
            return rowref+1
        return None

    def on_iter_children(self, parent):
        if parent is None: return 0
        return None

    def on_iter_has_child(self, rowref):
        return False

    def on_iter_n_children(self, rowref):
        if rowref is None: return len(self.line_graph_data)
        return 0

    def on_iter_nth_child(self, parent, n):
        if parent is None: return n
        return None

    def on_iter_parent(self, child):
        return None

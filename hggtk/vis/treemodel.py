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

class TreeModel(gtk.GenericTreeModel):

    def __init__ (self, repo, graphdata):
        gtk.GenericTreeModel.__init__(self)
        self.revisions = {}
        self.repo = repo
        self.line_graph_data = graphdata

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

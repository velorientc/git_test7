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
from mercurial import util

# treemodel row enumerated attributes
LINES = 0
NODE = 1
REVID = 2
LAST_LINES = 3
MESSAGE = 4
COMMITER = 5
TIMESTAMP = 6
REVISION = 7
PARENTS = 8

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

    def on_get_iter(self, path):
        return path[0]

    def on_get_path(self, rowref):
        return rowref

    def on_get_value(self, rowref, column):
        (revid, node, lines, parents) = self.line_graph_data[rowref]

        if column == REVID: return revid
        if column == NODE: return node
        if column == LINES: return lines
        if column == PARENTS: return parents
        if column == LAST_LINES:
            if rowref>0:
                return self.line_graph_data[rowref-1][2]
            return []

        if revid not in self.revisions:
            ctx = self.repo.changectx(revid)
            revision = (None, node, revid, None, ctx.description(),
                    ctx.user(), ctx.date(), None, parents)
            self.revisions[revid] = revision
        else:
            revision = self.revisions[revid]

        if column == REVISION:
            return revision
        if column == MESSAGE:
            summary = revision[MESSAGE].split('\n')[0]
            return gobject.markup_escape_text(summary)
        if column == COMMITER: 
            author = revision[COMMITER]
            if '<' in author:
                author = re.sub('<.*@.*>', '', author).strip(' ')
            else:
                author = util.shortuser(author)
            #return object.markup_escape_text(author)
            return author
        if column == TIMESTAMP:
            return strftime("%Y-%m-%d %H:%M",
                    localtime(revision[TIMESTAMP][0]))

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

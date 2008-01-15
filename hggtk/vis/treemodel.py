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
WCPARENT = 9
TAGS = 10

class TreeModel(gtk.GenericTreeModel):

    def __init__ (self, repo, graphdata):
        gtk.GenericTreeModel.__init__(self)
        self.revisions = {}
        self.repo = repo
        self.parents = [x.rev() for x in repo.workingctx().parents()]
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
        if index == WCPARENT: return gobject.TYPE_STRING
        if index == TAGS: return gobject.TYPE_STRING

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

            summary = ctx.description().replace('\0', '')
            summary = summary.split('\n')[0]
            summary = gobject.markup_escape_text(summary)
            node = self.repo.lookup(revid)
            tags = ', '.join(self.repo.nodetags(node))

            if '<' in ctx.user():
                author = re.sub('<.*@.*>', '', ctx.user()).strip(' ')
            else:
                author = util.shortuser(ctx.user())

            date = strftime("%Y-%m-%d %H:%M:%S", localtime(ctx.date()[0]))

            wc_parent = revid in self.parents and gtk.STOCK_HOME or ''

            revision = (None, node, revid, None, summary,
                    author, date, None, parents, wc_parent, tags)
            self.revisions[revid] = revision
        else:
            revision = self.revisions[revid]

        if column == REVISION:
            return revision
        if column == MESSAGE:
            return revision[MESSAGE]
        if column == COMMITER: 
            return revision[COMMITER]
        if column == TIMESTAMP:
            return revision[TIMESTAMP]
        if column == WCPARENT:
            return revision[WCPARENT]
        if column == TAGS:
            return revision[TAGS]

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

''' Mercurial revision DAG visualization library

  Implements a gtk.TreeModel which visualizes a Mercurial repository
  revision history.

Portions of this code stolen mercilessly from bzr-gtk visualization
dialog.  Other portions stolen from graphlog extension.
'''

import gtk
import gobject
import re
from mercurial import util
from mercurial.hgweb import webutil
from thgutil import hglib
from hggtk import gtklib

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
HEAD = 10
TAGS = 11
FGCOLOR = 12
HEXID = 13
UTC = 14
BRANCHES = 15

class TreeModel(gtk.GenericTreeModel):

    def __init__ (self, repo, graphdata, color_func):
        gtk.GenericTreeModel.__init__(self)
        self.revisions = {}
        self.branch_names = {}
        self.repo = repo
        self.line_graph_data = graphdata
        self.author_re = re.compile('<.*@.*>', 0)
        self.color_func = color_func
        self.parents = [x.rev() for x in repo.parents()]
        self.heads = [repo[x].rev() for x in repo.heads()]
        self.tagrevs = [repo[r].rev() for t, r in repo.tagslist()]
        self.branchtags = repo.branchtags()

    def refresh(self):
        repo = self.repo
        oldtags, oldheads, oldparents = self.tagrevs, self.heads, self.parents
        oldbranches = [repo[n].rev() for n in self.branchtags.values()]

        repo.invalidate()
        repo.dirstate.invalidate()

        self.parents = [x.rev() for x in repo.parents()]
        self.heads = [repo[x].rev() for x in repo.heads()]
        self.tagrevs = [repo[r].rev() for t, r in repo.tagslist()]
        self.branchtags = repo.branchtags()
        brevs = [repo[n].rev() for n in self.branchtags.values()]
        allrevs = set(oldtags + oldheads + oldparents + oldbranches +
                      brevs + self.parents + self.heads + self.tagrevs)
        for rev in allrevs:
            if rev in self.revisions:
                del self.revisions[rev]

    def on_get_flags(self):
        return gtk.TREE_MODEL_LIST_ONLY

    def on_get_n_columns(self):
        return 15

    def on_get_column_type(self, index):
        if index == NODE: return gobject.TYPE_PYOBJECT
        if index == LINES: return gobject.TYPE_PYOBJECT
        if index == REVID: return gobject.TYPE_STRING
        if index == LAST_LINES: return gobject.TYPE_PYOBJECT
        if index == MESSAGE: return gobject.TYPE_STRING
        if index == COMMITER: return gobject.TYPE_STRING
        if index == TIMESTAMP: return gobject.TYPE_STRING
        if index == REVISION: return gobject.TYPE_PYOBJECT
        if index == PARENTS: return gobject.TYPE_PYOBJECT
        if index == WCPARENT: return gobject.TYPE_BOOLEAN
        if index == HEAD: return gobject.TYPE_BOOLEAN
        if index == TAGS: return gobject.TYPE_STRING
        if index == FGCOLOR: return gobject.TYPE_STRING
        if index == HEXID: return gobject.TYPE_STRING
        if index == BRANCHES: return gobject.TYPE_STRING
        if index == UTC: return gobject.TYPE_STRING

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
            ctx = self.repo[revid]

            summary = ctx.description().replace('\0', '')
            if self.repo.ui.configbool('tortoisehg', 'longsummary'):
                lines = summary.split('\n')
                summary = lines.pop(0)
                while len(summary) < 80 and lines:
                    summary += '  ' + lines.pop(0)
                summary = summary[0:80]
            else:
                summary = summary.split('\n')[0]
            summary = gtklib.markup_escape_text(hglib.toutf(summary))
            node = self.repo.lookup(revid)
            tags = self.repo.nodetags(node)
            taglist = hglib.toutf(', '.join(tags))
            tstr = ''
            for tag in tags:
                tstr += '<span color="%s" background="%s"> %s </span> ' % \
                        ('black', '#ffffaa', tag)

            branch = ctx.branch()
            bstr = ''
            if self.branchtags.get(branch) == ctx.node():
                bstr += '<span color="%s" background="%s"> %s </span> ' % \
                        ('black', '#aaffaa', branch)

            if '<' in ctx.user():
                author = self.author_re.sub('', ctx.user()).strip(' ')
            else:
                author = util.shortuser(ctx.user())

            author = hglib.toutf(author)
            date = hglib.displaytime(ctx.date())
            utc = hglib.utctime(ctx.date())

            wc_parent = revid in self.parents
            head = revid in self.heads
            color = self.color_func(parents, revid, author)
            if wc_parent:
                sumstr = bstr + tstr + '<b><u>' + summary + '</u></b>'
            else:
                sumstr = bstr + tstr + summary
            
            revision = (None, node, revid, None, sumstr,
                    author, date, None, parents, wc_parent, head, taglist,
                    color, str(ctx), utc)
            self.revisions[revid] = revision
            self.branch_names[revid] = branch
        else:
            revision = self.revisions[revid]
            branch = self.branch_names[revid]

        if column == REVISION:
            return revision
        if column == BRANCHES:
            return branch
        return revision[column]

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

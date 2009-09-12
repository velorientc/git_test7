# treemodel.py - changelog viewer data model
#
# Copyright 2008 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

''' Mercurial revision DAG visualization library

  Implements a gtk.TreeModel which visualizes a Mercurial repository
  revision history.

Portions of this code stolen mercilessly from bzr-gtk visualization
dialog.  Other portions stolen from graphlog extension.
'''

import gtk
import gobject
from mercurial import util, templatefilters
from thgutil import hglib
from hggtk import gtklib

# treemodel row enumerated attributes
LINES = 0           # These elements come from the changelog walker
GRAPHNODE = 1
REVID = 2
LAST_LINES = 3

BRANCH = 4          # calculated on demand, not cached
HEXID = 5
LOCALTIME = 6
UTC = 7

MESSAGE = 8         # calculated on demand, cached
COMMITER = 9
TAGS = 10
FGCOLOR = 11
AGE = 12

class TreeModel(gtk.GenericTreeModel):

    def __init__ (self, repo, graphdata, color_func):
        gtk.GenericTreeModel.__init__(self)
        self.repo = repo
        self.revisions = {}
        self.graphdata = graphdata
        self.color_func = color_func
        self.parents = [x.rev() for x in repo.parents()]
        self.tagrevs = [repo[r].rev() for t, r in repo.tagslist()]
        self.branchtags = repo.branchtags()

    def refresh(self):
        repo = self.repo
        oldtags, oldparents = self.tagrevs, self.parents
        oldbranches = [repo[n].rev() for n in self.branchtags.values()]

        repo.invalidate()
        repo.dirstate.invalidate()

        self.parents = [x.rev() for x in repo.parents()]
        self.tagrevs = [repo[r].rev() for t, r in repo.tagslist()]
        self.branchtags = repo.branchtags()
        brevs = [repo[n].rev() for n in self.branchtags.values()]
        allrevs = set(oldtags + oldparents + oldbranches +
                      brevs + self.parents + self.tagrevs)
        for rev in allrevs:
            if rev in self.revisions:
                del self.revisions[rev]

    def on_get_flags(self):
        return gtk.TREE_MODEL_LIST_ONLY

    def on_get_n_columns(self):
        return 13

    def on_get_column_type(self, index):
        if index == GRAPHNODE: return gobject.TYPE_PYOBJECT
        if index == LINES: return gobject.TYPE_PYOBJECT
        if index == REVID: return int
        if index == LAST_LINES: return gobject.TYPE_PYOBJECT

        if index == BRANCH: return str
        if index == HEXID: return str
        if index == LOCALTIME: return str
        if index == UTC: return str

        if index == MESSAGE: return str
        if index == COMMITER: return str
        if index == TAGS: return str
        if index == FGCOLOR: return str
        if index == AGE: return str

    def on_get_iter(self, path):
        return path[0]

    def on_get_path(self, rowref):
        return rowref

    def on_get_value(self, rowref, column):
        (revid, graphnode, lines, parents) = self.graphdata[rowref]

        if column == REVID: return revid
        if column == GRAPHNODE: return graphnode
        if column == LINES: return lines
        if column == LAST_LINES:
            if rowref>0:
                return self.graphdata[rowref-1][2]
            return []

        if column in (HEXID, BRANCH, LOCALTIME, UTC):
            try:
                ctx = self.repo[revid]
            except IndexError:
                return None
            if column == HEXID:
                return str(ctx)
            if column == BRANCH:
                return ctx.branch()
            if column == LOCALTIME:
                return hglib.displaytime(ctx.date())
            if column == UTC:
                return hglib.utctime(ctx.date())

        if revid not in self.revisions:
            try:
                ctx = self.repo[revid]
            except IndexError:
                return None

            # convert to Unicode for valid string operations
            summary = hglib.tounicode(ctx.description()).replace(u'\0', '')
            if self.repo.ui.configbool('tortoisehg', 'longsummary'):
                limit = 80
                lines = summary.splitlines()
                summary = lines.pop(0)
                while len(summary) < limit and lines:
                    summary += u'  ' + lines.pop(0)
                summary = summary[0:limit]
            else:
                summary = summary.splitlines()[0]
            summary = gtklib.markup_escape_text(hglib.toutf(summary))
            node = ctx.node()
            tags = self.repo.nodetags(node)
            taglist = hglib.toutf(', '.join(tags))
            tstr = ''
            for tag in tags:
                tstr += '<span color="%s" background="%s"> %s </span> ' % \
                        ('black', '#ffffaa', tag)

            branch = ctx.branch()
            bstr = ''
            if self.branchtags.get(branch) == node:
                bstr += '<span color="%s" background="%s"> %s </span> ' % \
                        ('black', '#aaffaa', branch)

            author = templatefilters.person(ctx.user())
            if not author:
                author = util.shortuser(ctx.user())
            author = hglib.toutf(author)
            age = templatefilters.age(ctx.date())

            color = self.color_func(parents, revid, author)
            if revid in self.parents:
                sumstr = bstr + tstr + '<b><u>' + summary + '</u></b>'
            else:
                sumstr = bstr + tstr + summary
            
            revision = (sumstr, author, taglist, color, age)
            self.revisions[revid] = revision
        else:
            revision = self.revisions[revid]
        return revision[column-MESSAGE]

    def on_iter_next(self, rowref):
        if rowref < len(self.graphdata) - 1:
            return rowref+1
        return None

    def on_iter_children(self, parent):
        if parent is None: return 0
        return None

    def on_iter_has_child(self, rowref):
        return False

    def on_iter_n_children(self, rowref):
        if rowref is None: return len(self.graphdata)
        return 0

    def on_iter_nth_child(self, parent, n):
        if parent is None: return n
        return None

    def on_iter_parent(self, child):
        return None

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
import re

from mercurial import util, templatefilters
from tortoisehg.util import hglib
from tortoisehg.hgtk import gtklib

# treemodel row enumerated attributes
LINES = 0           # These elements come from the changelog walker
GRAPHNODE = 1
REVID = 2
LAST_LINES = 3
WFILE = 4

BRANCH = 5          # calculated on demand, not cached
HEXID = 6
LOCALTIME = 7
UTC = 8

MESSAGE = 9         # calculated on demand, cached
COMMITER = 10
TAGS = 11
FGCOLOR = 12
AGE = 13

class TreeModel(gtk.GenericTreeModel):

    def __init__ (self, repo, graphdata, opts):
        gtk.GenericTreeModel.__init__(self)
        self.repo = repo
        self.outgoing = opts['outgoing']
        self.origtip = opts['orig-tip']
        self.npreviews = opts['npreviews']
        self.showgraph = opts['show-graph']
        self.revisions = {}
        self.graphdata = graphdata
        self.set_author_color()
        self.hidetags = self.repo.ui.config(
            'tortoisehg', 'hidetags', '').split()
        self.wcparents, self.tagrevs, self.branchtags = [], [], {}
        try:
            self.tagrevs = [repo[r].rev() for t, r in repo.tagslist()]
            self.branchtags = repo.branchtags()
            self.wcparents = [x.rev() for x in repo.parents()]
        except hglib.Abort:
            pass

    def refresh(self):
        repo = self.repo
        oldtags, oldparents = self.tagrevs, self.wcparents
        oldbranches = [repo[n].rev() for n in self.branchtags.values()]

        repo.invalidate()
        repo.dirstate.invalidate()

        self.wcparents = [x.rev() for x in repo.parents()]
        self.tagrevs = [repo[r].rev() for t, r in repo.tagslist()]
        self.branchtags = repo.branchtags()
        brevs = [repo[n].rev() for n in self.branchtags.values()]
        allrevs = set(oldtags + oldparents + oldbranches +
                      brevs + self.wcparents + self.tagrevs)
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
        if index == WFILE: return str

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
        (revid, graphnode, lines, path) = self.graphdata[rowref]

        if column == REVID: return revid
        if column == LINES: return lines
        if column == LAST_LINES:
            if rowref>0:
                return self.graphdata[rowref-1][2]
            return []
        if column == WFILE: return path or ''

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
                if lines:
                    summary = lines.pop(0)
                    while len(summary) < limit and lines:
                        summary += u'  ' + lines.pop(0)
                    summary = summary[0:limit]
                else:
                    summary = ''
            else:
                lines = summary.splitlines()
                summary = lines and lines[0] or ''
            summary = gtklib.markup_escape_text(hglib.toutf(summary))
            node = ctx.node()
            tags = self.repo.nodetags(node)
            taglist = hglib.toutf(', '.join(tags))
            tstr = ''
            for tag in tags:
                if tag not in self.hidetags:
                    tstr += '<span color="%s" background="%s"> %s </span> ' % \
                            ('black', '#ffffaa', tag)

            branch = ctx.branch()
            bstr = ''
            if self.branchtags.get(branch) == node:
                bstr += '<span color="%s" background="%s"> %s </span> ' % \
                        ('black', '#aaffaa', branch)

            author = hglib.toutf(hglib.username(ctx.user()))
            age = hglib.age(ctx.date())

            color = self.color_func(revid, author)
            if revid in self.wcparents:
                sumstr = bstr + tstr + '<b><u>' + summary + '</u></b>'
                status = 4
            else:
                sumstr = bstr + tstr + summary
                status = 0

            if node in self.outgoing:
                # outgoing
                if not self.showgraph:
                    marker = hglib.toutf(u'\u2191 ') # up arrow
                    sumstr = marker + sumstr
                status += 1
            elif revid >= self.origtip:
                if revid >= len(self.repo) - self.npreviews:
                    # incoming
                    if not self.showgraph:
                        marker = hglib.toutf(u'\u2193 ') # down arrow
                        sumstr = marker + sumstr
                    status += 3
                else:
                    # new
                    status += 2

            revision = (sumstr, author, taglist, color, age, status)
            self.revisions[revid] = revision
        else:
            revision = self.revisions[revid]
        if column == GRAPHNODE:
            column, color = graphnode
            return (column, color, revision[5])
        else:
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

    def set_author_color(self):
        # If user has configured authorcolor in [tortoisehg], color
        # rows by author matches
        self.author_pats = []
        self.color_func =  self.text_color_default

        if self.repo is not None:
            for k, v in self.repo.ui.configitems('tortoisehg'):
                if not k.startswith('authorcolor.'): continue
                pat = k[12:]
                self.author_pats.append((re.compile(pat, re.I), v))
            try:
                enabled = self.repo.ui.configbool('tortoisehg', 'authorcolor')
            except hglib.ConfigError:
                enabled = False
            if self.author_pats or enabled:
                self.color_func = self.text_color_author

    def text_color_default(self, rev, author):
        return int(rev) >= self.origtip and 'darkgreen' or 'black'

    colors = '''black blue deeppink mediumorchid blue burlywood4 goldenrod
     slateblue red2 navy dimgrey'''.split()
    color_cache = {}

    def text_color_author(self, rev, author):
        if int(rev) >= self.origtip:
            return 'darkgreen'
        for re, v in self.author_pats:
            if (re.search(author)):
                return v
        if author not in self.color_cache:
            color = self.colors[len(self.color_cache.keys()) % len(self.colors)]
            self.color_cache[author] = color
        return self.color_cache[author]


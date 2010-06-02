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

from mercurial import util, error
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
REVHEX = 7
LOCALTIME = 8
UTC = 9

MESSAGE = 10        # calculated on demand, cached
COMMITER = 11
TAGS = 12
FGCOLOR = 13
AGE = 14
CHANGES = 15

class TreeModel(gtk.GenericTreeModel):

    def __init__ (self, repo, graphdata, opts):
        gtk.GenericTreeModel.__init__(self)
        self.repo = repo
        self.outgoing = opts['outgoing']
        self.origtip = opts['orig-tip']
        self.npreviews = opts['npreviews']
        self.showgraph = opts['show-graph']
        self.graphdata = graphdata
        self.revisions, self.parents = {}, {}
        self.wcparents, self.tagrevs, self.branchtags = [], [], {}
        self.refresh()

    def refresh(self):
        repo = self.repo
        oldtags, oldparents = self.tagrevs, self.wcparents
        try:
            oldbranches = [repo[n].rev() for n in self.branchtags.values()]
        except error.RepoLookupError:
            oldbranches = []

        hglib.invalidaterepo(repo)

        self.longsummary = repo.ui.configbool('tortoisehg', 'longsummary', False)
        self.set_author_color()
        self.hidetags = hglib.gethidetags(repo.ui)

        self.curbookmark = hglib.get_repo_bookmarkcurrent(repo)
        try:
            self.wcparents = [x.rev() for x in repo.parents()]
            self.tagrevs = [repo[r].rev() for t, r in repo.tagslist()]
            self.branchtags = repo.branchtags()
        except util.Abort:
            pass
        brevs = [repo[n].rev() for n in self.branchtags.values()]
        allrevs = set(oldtags + oldparents + oldbranches +
                      brevs + self.wcparents + self.tagrevs)
        for rev in allrevs:
            if rev in self.revisions:
                del self.revisions[rev]

        self.mqpatches = []
        if hasattr(self.repo, 'mq'):
            self.repo.mq.parse_series()
            self.mqpatches = [p.name for p in self.repo.mq.applied]

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
        if index == REVHEX: return str
        if index == LOCALTIME: return str
        if index == UTC: return str

        if index == MESSAGE: return str
        if index == COMMITER: return str
        if index == TAGS: return str
        if index == FGCOLOR: return str
        if index == AGE: return str
        if index == CHANGES: return str

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

        try:
            ctx = self.repo[revid]
        except IndexError:
            return None

        # non-cached columns

        if column in (HEXID, REVHEX, BRANCH, LOCALTIME, UTC):
            if column == HEXID:
                return str(ctx)
            if column == REVHEX:
                hexid = gtklib.markup(str(ctx), face='monospace')
                return '%s: %s' % (revid, hexid)
            if column == BRANCH:
                return ctx.branch()
            if column == LOCALTIME:
                return hglib.displaytime(ctx.date())
            if column == UTC:
                return hglib.utctime(ctx.date())

        # cached columns

        if revid not in self.revisions:
            self.revisions[revid] = {}
        cache = self.revisions[revid]

        if cache.has_key(column):
            return cache[column]

        if column in (COMMITER, FGCOLOR):
            cache[COMMITER] = hglib.toutf(hglib.username(ctx.user()))

        if column == TAGS:
            tags = self.repo.nodetags(ctx.node())
            cache[TAGS] = hglib.toutf(', '.join(tags))

        elif column == AGE:
            cache[AGE] = hglib.age(ctx.date())

        elif column == FGCOLOR:
            cache[FGCOLOR] = self.color_func(revid, cache[COMMITER])

        elif column == CHANGES:
            parent = self.parents.get(revid, None)
            if parent is None:
                parent = ctx.parents()[0].node()
            M, A, R = self.repo.status(parent, ctx.node())[:3]
            common = dict(color=gtklib.BLACK)
            M = M and gtklib.markup(' %s ' % len(M),
                             background=gtklib.PORANGE, **common) or ''
            A = A and gtklib.markup(' %s ' % len(A),
                             background=gtklib.PGREEN, **common) or ''
            R = R and gtklib.markup(' %s ' % len(R),
                             background=gtklib.PRED, **common) or ''
            cache[CHANGES] = ''.join((M, A, R))

        elif column in (MESSAGE, GRAPHNODE):
            # convert to Unicode for valid string operations
            summary = hglib.tounicode(ctx.description()).replace(u'\0', '')
            if self.longsummary:
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
            escape = gtklib.markup_escape_text
            summary = escape(hglib.toutf(summary))

            node = ctx.node()
            tags = self.repo.nodetags(node)
            tstr = ''
            for tag in tags:
                if tag not in self.hidetags:
                    bg = gtklib.PYELLOW
                    if tag == self.curbookmark:
                        bg = gtklib.PORANGE
                    elif tag in self.mqpatches:
                        bg = gtklib.PBLUE
                    style = {'color': gtklib.BLACK, 'background': bg}
                    tstr += gtklib.markup(' %s ' % tag, **style) + ' '

            branch = ctx.branch()
            bstr = ''
            status = 0
            if self.branchtags.get(branch) == node:
                bstr += gtklib.markup(' %s ' % branch, color=gtklib.BLACK,
                                      background=gtklib.PGREEN) + ' '
                status = 8

            if revid in self.wcparents:
                sumstr = bstr + tstr + '<b><u>' + summary + '</u></b>'
                status += 4
            else:
                sumstr = bstr + tstr + summary
                status += 0

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

            cache[MESSAGE] = sumstr
            gcolumn, gcolor = graphnode
            cache[GRAPHNODE] = (gcolumn, gcolor, status)

        return cache[column]

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
            enabled = self.repo.ui.configbool('tortoisehg', 'authorcolor', False)
            if self.author_pats or enabled:
                self.color_func = self.text_color_author

    def text_color_default(self, rev, author):
        return int(rev) >= self.origtip and gtklib.NEW_REV_COLOR or gtklib.NORMAL  
    color_cache = {}

    def hash_author(self, author):
        h = hash(author) % 0x1000000; #hash, not HSV hue

        r = h % 0x100
        h /= 0x100

        g = h % 0x100
        h /= 0x100

        b = h % 0x100

        c= [r,g,b]

        #For a dark theme, use upper two thirds of the RGB scale.
        if gtklib.is_dark_theme():
            c = [2*x/3 + 85 for x in c]
        #Else, use bottom two thirds. 
        else:
            c = [2*x/3 for x in c]

        return "#%02x%02x%02x" % (c[0],c[1],c[2])

    def text_color_author(self, rev, author):
        if int(rev) >= self.origtip:
            return gtklib.NEW_REV_COLOR
        for re, v in self.author_pats:
            if (re.search(author)):
                return v
        if author not in self.color_cache:
            color = self.hash_author(author)
            self.color_cache[author] = color
        return self.color_cache[author]

    def set_parent(self, rev, parent):
        self.parents[rev] = parent
        if rev in self.revisions:
            del self.revisions[rev]

    def clear_parents(self):
        for rev in self.parents.keys():
            if rev in self.revisions:
                del self.revisions[rev]
        self.parents = {}

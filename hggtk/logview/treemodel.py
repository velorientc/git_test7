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
WCPARENT = 7
TAGS = 8
FGCOLOR = 9
HEXID = 10
UTC = 11
BRANCH = 12

class ChangeLogCache:
    def __init__ (self, repo, color_func):
        self.repo = repo
        self.color_func = color_func
        self.parents = [x.rev() for x in repo.parents()]
        self.tagrevs = [repo[r].rev() for t, r in repo.tagslist()]
        self.branchtags = repo.branchtags()
        self.lastlines = []

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

    def create_row(self, rev, graphnode, lines):
        revid = int(rev)
        try:
            ctx = self.repo[rev]
        except IndexError:
            return None

        summary = ctx.description().replace('\0', '')
        if self.repo.ui.configbool('tortoisehg', 'longsummary'):
            sumlines = summary.split('\n')
            summary = lines.pop(0)
            while len(summary) < 80 and sumlines:
                summary += '  ' + sumlines.pop(0)
            summary = summary[0:80]
        else:
            summary = summary.split('\n')[0]
        summary = gtklib.markup_escape_text(hglib.toutf(summary))
        node = ctx.node()
        tags = ctx.tags()
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
        date = hglib.displaytime(ctx.date())
        utc = hglib.utctime(ctx.date())

        wc_parent = revid in self.parents
        if wc_parent:
            sumstr = bstr + tstr + '<b><u>' + summary + '</u></b>'
        else:
            sumstr = bstr + tstr + summary
        
        color = self.color_func(ctx.parents(), revid, author)
        lastlines = self.lastlines
        self.lastlines = lines
        return (lines, graphnode, revid, lastlines, sumstr,
                author, date, wc_parent, taglist,
                color, str(ctx), utc, ctx.branch())

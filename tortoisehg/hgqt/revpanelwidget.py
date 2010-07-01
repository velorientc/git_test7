# -*- coding: iso-8859-1 -*-
#!/usr/bin/env python
# repowidget.py - TortoiseHg repository widget
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
# Copyright (C) 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.


from tortoisehg.hgqt.i18n import _

from tortoisehg.hgqt import csinfo, qtlib

from tortoisehg.util import hglib

from mercurial import error


def RevPanelWidget(repo, repoview):
    '''creates a rev panel widget and returns it
    
    repoview is a HgRepoView object'''

    def label_func(widget, item):
        if item == 'cset':
            return _('Changeset:')
        elif item == 'parents':
            return _('Parent:')
        elif item == 'children':
            return _('Child:')
        elif item == 'patch':
            return _('Patch:')
        raise csinfo.UnknownItem(item)
    def revid_markup(revid, **kargs):
        opts = dict(family='monospace', size='9pt')
        opts.update(kargs)
        return qtlib.markup(revid, **opts)
    def data_func(widget, item, ctx):
        def summary_line(desc):
            desc = desc.replace('\0', '').split('\n')[0]
            return hglib.tounicode(desc)[:80]
        def revline_data(ctx, hl=False, branch=None):
            if isinstance(ctx, basestring):
                return ctx
            desc = ctx.description()
            return (str(ctx.rev()), str(ctx), summary_line(desc), hl, branch)
        if item == 'cset':
            return revline_data(ctx)
        elif item == 'branch':
            value = hglib.tounicode(ctx.branch())
            return value != 'default' and value or None
        elif item == 'parents':
            # TODO: need to put 'diff to other' checkbox
            #pindex = self.diff_other_parent() and 1 or 0
            pindex = 0 # always show diff with first parent
            pctxs = ctx.parents()
            parents = []
            for pctx in pctxs:
                highlight = len(pctxs) == 2 and pctx == pctxs[pindex]
                branch = None
                if hasattr(pctx, 'branch') and pctx.branch() != ctx.branch():
                    branch = pctx.branch()
                parents.append(revline_data(pctx, highlight, branch))
            return parents
        elif item == 'children':
            children = []
            for cctx in ctx.children():
                branch = None
                if hasattr(cctx, 'branch') and cctx.branch() != ctx.branch():
                    branch = cctx.branch()
                children.append(revline_data(cctx, branch=branch))
            return children
        elif item in ('transplant', 'p4', 'svn'):
            ts = widget.get_data(item, usepreset=True)
            if not ts:
                return None
            try:
                tctx = repo[ts]
                return revline_data(tctx)
            except (error.LookupError, error.RepoLookupError, error.RepoError):
                return ts
        elif item == 'patch':
            if hasattr(ctx, '_patchname'):
                desc = ctx.description()
                return (ctx._patchname, str(ctx), summary_line(desc))
            return None
        raise csinfo.UnknownItem(item)
    def markup_func(widget, item, value):
        def link_markup(revnum, revid, enable=True):
            mrevid = revid_markup(revid)
            if not enable:
                return '%s (%s)' % (revnum, mrevid)
            link = 'cset://%s:%s' % (revnum, revid)
            return '<a href="%s">%s (%s)</a>' % (link, revnum, mrevid)
        def revline_markup(revnum, revid, summary, highlight=None,
                           branch=None, link=True):
            def branch_markup(branch):
                opts = dict(fg='black', bg='#aaffaa')
                return qtlib.markup(' %s ' % branch, **opts)
            summary = qtlib.markup(summary)
            if branch:
                branch = branch_markup(branch)
            if revid:
                rev = link_markup(revnum, revid, link)
                if branch:
                    return '%s %s %s' % (rev, branch, summary)
                return '%s %s' % (rev, summary)
            else:
                revnum = qtlib.markup(revnum)
                if branch:
                    return '%s - %s %s' % (revnum, branch, summary)
                return '%s - %s' % (revnum, summary)
        if item in ('cset', 'transplant', 'patch', 'p4', 'svn'):
            link = item != 'cset'
            if isinstance(value, basestring):
                return revid_markup(value)
            return revline_markup(link=link, *value)
        elif item in ('parents', 'children'):
            csets = []
            for cset in value:
                if isinstance(cset, basestring):
                    csets.append(revid_markup(cset))
                else:
                    csets.append(revline_markup(*cset))
            return csets
        raise csinfo.UnknownItem(item)

    custom = csinfo.custom(data=data_func, label=label_func,
                           markup=markup_func)
    style = csinfo.panelstyle(contents=('cset', 'branch', 'user',
                   'dateage', 'parents', 'children', 'tags', 'transplant',
                   'p4', 'svn'), selectable=True, expandable=True)
    revpanel = csinfo.create(repo, style=style, custom=custom)
    def activated(url):
        if url.startsWith('cset://'):
            rev = url[7:].split(':')[0]
            repoview.goto(rev)
    revpanel.linkActivated.connect(activated)

    return revpanel

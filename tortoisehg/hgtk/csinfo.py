# csinfo.py - embeddable changeset summary
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

'''embeddable changeset summary'''

import re
import os
import gtk

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths

from tortoisehg.hgtk import gtklib

PANEL_DEFAULT = ('rev', 'summary', 'user', 'date', 'branch', 'tags')

def create(rev, style=None, repo=None, custom=None):
    if style is None:
        style = panelstyle()
    if repo is None:
        try:
            rpath = paths.find_root()
            repo = hg.repository(ui.ui(), path=rpath)
        except hglib.RepoError:
            raise _('failed to get repo: %s') % rpath
    if custom is None:
        custom = {}
    if 'type' in style:
        type = style['type']
        if type == 'panel':
            if 'contents' not in style:
                style['contents'] = PANEL_DEFAULT
            return ChangesetPanel(rev, style, repo, custom)
        elif type == 'label':
            return ChangesetLabel(rev, style, repo, custom)
        raise _('unknown csinfo type: %s') % type
    raise _('no csinfo type specified')

def factory(*base, **kbase):
    def bind(*over, **kover):
        args = base + over
        kargs = kbase.copy()
        # override base options
        kargs.update(kover)
        if 'style' in kargs and 'style' in kover:
            # override style options
            kargs['style'] = kbase['style'].copy()
            kargs['style'].update(kover['style'])
        return create(*args, **kargs)
    return bind

def panelstyle(**kargs):
    kargs['type'] = 'panel'
    return kargs

def labelstyle(**kargs):
    kargs['type'] = 'label'
    return kargs

def custom(**kargs):
    return kargs

class ChangesetWidget(object):

    LABELS = {'rev': _('rev:'), 'revnum': _('rev:'), 'revid': _('rev:'),
              'summary': _('summary:'), 'user': _('user:'),
              'date': _('date:'), 'branch': _('branch:'), 'tags': _('tags:')}

    def __init__(self, rev, repo, custom):
        self.rev = str(rev)
        self.repo = repo
        self.custom = custom

    def get_data(self, item):
        def default_func(widget, ctx):
            return None
        def preset_func(widget, ctx):
            if item == 'rev':
                revnum = self.get_data('revnum')
                revid = self.get_data('revid')
                return '%s (%s)' % (revnum, revid)
            elif item == 'revnum':
                return str(ctx.rev())
            elif item == 'revid':
                return str(ctx)
            elif item == 'summary':
                desc = ctx.description().replace('\0', '')
                value = hglib.toutf(desc.split('\n')[0][:80])
                if len(value) == 0:
                    return  None
                return value
            elif item == 'user':
                return hglib.toutf(ctx.user())
            elif item == 'date':
                return hglib.displaytime(ctx.date())
            elif item == 'branch':
                if ctx.node() in self.repo.branchtags().values():
                    return hglib.toutf(ctx.branch())
                return None
            elif item == 'tags':
                value = hglib.toutf(', '.join(ctx.tags()))
                if len(value) == 0:
                    return None
                return value
            return default_func(widget, ctx)
        ctx = self.repo[self.rev]
        if self.custom.has_key(item) and self.custom[item].has_key('data'):
            return self.custom[item]['data'](self, ctx)
        return preset_func(self, ctx)

    def get_label(self, item):
        def default_func(widget):
            return ''
        def preset_func(widget):
            try:
                return self.LABELS[item]
            except:
                return default_func(widget)
        if self.custom.has_key(item) and self.custom[item].has_key('label'):
            return self.custom[item]['label'](self)
        return preset_func(self)

    def get_markup(self, item):
        def default_func(widget, value):
            return gtklib.markup_escape_text(value)
        def preset_func(widget, value):
            if item in ('rev', 'revnum', 'revid'):
                return gtklib.markup(value, face='monospace', size='9000')
            elif item == 'branch':
                return gtklib.markup(' %s ' % value, color='black',
                                     background='#aaffaa')
            elif item == 'tags':
                opts = dict(color='black', background='#ffffaa')
                tags = value.split(', ')
                tags = [gtklib.markup(' %s ' % tag, **opts) for tag in tags]
                return ' '.join(tags)
            return default_func(widget, value)
        value = self.get_data(item)
        if value is None:
            return None
        if self.custom.has_key(item) and self.custom[item].has_key('markup'):
            return self.custom[item]['markup'](self, value)
        return preset_func(self, value)

    def update(self, rev=None, repo=None, custom=None):
        if rev is not None:
            self.rev = str(rev)
        if repo is not None:
            self.repo = repo
        if custom is not None:
            self.custom = custom

class ChangesetPanel(ChangesetWidget, gtk.Frame):

    def __init__(self, rev, style, repo, custom):
        ChangesetWidget.__init__(self, rev, repo, custom)
        gtk.Frame.__init__(self)

        self.set_shadow_type(gtk.SHADOW_NONE)
        self.csstyle = style

        # layout table for contents
        self.table = gtklib.LayoutTable(ypad=1, headopts={'weight': 'bold'})
        self.add(self.table)

        self.update()

    def update(self, rev=None, style=None, repo=None, custom=None):
        ChangesetWidget.update(self, rev, repo, custom)
        if style is not None:
            self.csstyle = style

        if 'label' in self.csstyle:
            label = self.csstyle['label']
            assert isinstance(label, basestring)
            self.set_label(label)
            self.set_shadow_type(gtk.SHADOW_ETCHED_IN)

        if 'margin' in self.csstyle:
            margin = self.csstyle['margin']
            # 'border' range is 0-65535
            assert isinstance(margin, (int, long))
            assert 0 <= margin and margin <= 65535
            self.set_border_width(margin)

        if 'padding' in self.csstyle:
            padding = self.csstyle['padding']
            # 'border' range is 0-65535
            assert isinstance(padding, (int, long))
            assert 0 <= padding and padding <= 65535
            self.table.set_border_width(padding)

        contents = self.csstyle.get('contents', None)
        assert contents

        # build info
        self.table.clear_rows()
        for item in contents:
            text = self.get_markup(item)
            if text:
                body = gtk.Label()
                body.set_markup(text)
                self.table.add_row(self.get_label(item), body)

class ChangesetLabel(ChangesetWidget, gtk.Label):

    def __init__(self, rev, style, repo, custom):
        ChangesetWidget.__init__(self, rev, repo, custom)
        gtk.Label.__init__(self)

        self.set_alignment(0, 0.5)
        self.csstyle = style

        self.update()

    def update(self, rev=None, style=None, repo=None, custom=None):
        ChangesetWidget.update(self, rev, repo, custom)
        if style is not None:
            self.csstyle = style

        if 'selectable' in self.csstyle:
            sel = self.csstylestyle['selectable']
            assert isinstance(sel, bool)
            self.set_selectable(sel)

        if 'width' in self.csstyle or 'height' in self.csstyle:
            width = self.csstyle.get('width', -1)
            assert isinstance(width, (int, long))
            height = self.csstyle.get('height', -1)
            assert isinstance(height, (int, long))
            self.set_size_request(width, height)
            self.set_line_wrap(True)

        contents = self.csstyle.get('contents', None)
        assert contents

        # build info
        info = ''
        pat = re.compile(r'(?:(?<=%%)|(?<!%)%\()(\w+)(?:\)s)')
        for snip in contents:
            # extract all placeholders
            items = pat.findall(snip)
            # fetch required data
            data = {}
            for item in items:
                text = self.get_markup(item)
                if text:
                    data[item] = text
            if len(data) == 0:
                continue
            # insert data & append to label
            info += snip % data
        self.set_markup(info)

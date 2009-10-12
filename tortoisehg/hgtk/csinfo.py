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
                return hglib.toutf(ctx.branch())
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

class ChangesetPanel(ChangesetWidget, gtk.VBox):

    def __init__(self, rev, style, repo, custom):
        ChangesetWidget.__init__(self, rev, repo, custom)
        gtk.VBox.__init__(self)

        self.csstyle = style

        if 'label' in style and style['label'] is not None:
            label = style['label']
            assert isinstance(label, basestring)
            frame = gtk.Frame(label)
            self.add(frame)
            vbox = gtk.VBox()
            frame.add(vbox)
        else:
            vbox = self

        if 'margin' in style:
            margin = style['margin']
            # 'border' range is 0-65535
            assert isinstance(margin, (int, long))
            assert 0 <= margin and margin <= 65535
            self.set_border_width(margin)

        table = gtklib.LayoutTable(ypad=1, headopts={'weight': 'bold'})
        vbox.add(table)

        if 'padding' in style:
            padding = style['padding']
            # 'border' range is 0-65535
            assert isinstance(padding, (int, long))
            assert 0 <= padding and padding <= 65535
            table.set_border_width(padding)

        contents = style.get('contents', None)
        assert contents

        # build info
        for item in contents:
            text = self.get_markup(item)
            if text:
                body = gtk.Label()
                body.set_markup(text)
                table.add_row(self.get_label(item), body)

class ChangesetLabel(ChangesetWidget, gtk.Label):

    def __init__(self, rev, style, repo, custom):
        ChangesetWidget.__init__(self, rev, repo, custom)
        gtk.Label.__init__(self)

        self.set_alignment(0, 0.5)
        self.csstyle = style

        self.update(rev)

    def update(self, rev=None, style=None, repo=None):
        if rev is None:
            rev = self.rev
        else:
            self.rev = str(rev)
        if repo is None:
            repo = self.repo
        else:
            self.repo = repo
        if style is None:
            style = self.csstyle
        else:
            self.csstyle = style

        if 'selectable' in style:
            sel = style['selectable']
            assert isinstance(sel, bool)
            self.set_selectable(sel)

        if 'width' in style or 'height' in style:
            width = style.get('width', -1)
            assert isinstance(width, (int, long))
            height = style.get('height', -1)
            assert isinstance(height, (int, long))
            self.set_size_request(width, height)
            self.set_line_wrap(True)

        contents = style.get('contents', None)
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

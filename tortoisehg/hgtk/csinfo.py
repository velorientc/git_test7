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

def create(repo, rev, style=None, custom=None):
    return CachedFactory(repo, custom, style, rev)()

def factory(*args, **kargs):
    return CachedFactory(*args, **kargs)

def panelstyle(**kargs):
    kargs['type'] = 'panel'
    return kargs

def labelstyle(**kargs):
    kargs['type'] = 'label'
    return kargs

def custom(**kargs):
    return kargs

class CachedFactory(object):

    def __init__(self, repo=None, custom=None, style=None, rev=None,
                 widgetcache=False):
        if repo is None:
            try:
                root = paths.find_root()
                repo = hg.repository(ui.ui(), path=root)
            except hglib.RepoError:
                raise _('failed to get repo: %s') % root
        self.repo = repo
        if custom is None:
            custom = {}
        self.custom = custom
        if style is None:
            style = panelstyle(contents=PANEL_DEFAULT)
        self.csstyle = style
        if rev is None:
            rev = 'tip'
        self.rev = rev
        self.info = CachedChangesetInfo()

        if widgetcache:
            self.cache = {}

    def __call__(self, rev=None, style=None, custom=None, repo=None):
        if rev is None:
            rev = self.rev
        if style is None:
            style = self.csstyle
        else:
            # need to override styles
            newstyle = self.csstyle.copy()
            newstyle.update(style)
            style = newstyle
        if custom is None:
            custom = self.custom
        else:
            # need to override customs
            newcustom = self.custom.copy()
            newcustom.update(custom)
            custom = newcustom
        if repo is None:
            repo = self.repo

        # check cache
        if hasattr(self, 'cache'):
            key = style['type'] + str(rev) + str(style) + str(custom) + str(id(repo))
            try:
                widget = self.cache[key]
                return widget
            except KeyError:
                pass

        if 'type' in style:
            args = (rev, style, custom, repo, self.info)
            type = style['type']
            if type == 'panel':
                if 'contents' not in style:
                    style['contents'] = PANEL_DEFAULT
                panel = ChangesetPanel(*args)
                if hasattr(self, 'cache'):
                    self.cache[key] = panel
                return panel
            elif type == 'label':
                label = ChangesetLabel(*args)
                if hasattr(self, 'cache'):
                    self.cache[key] = label
                return label
            else:
                raise _("unknown 'type': %s") % type
        else:
            raise _("must be specified 'type' in style")

class ChangesetInfo(object):

    LABELS = {'rev': _('rev:'), 'revnum': _('rev:'), 'revid': _('rev:'),
              'summary': _('summary:'), 'user': _('user:'),
              'date': _('date:'), 'branch': _('branch:'), 'tags': _('tags:'),
              'rawbranch': _('branch:')}

    def __init__(self):
        pass

    def get_data(self, widget, item, rev, custom, repo):
        def default_func(widget, ctx):
            return None
        def preset_func(widget, ctx):
            if item == 'rev':
                revnum = self.get_data(widget, 'revnum', rev, custom, repo)
                revid = self.get_data(widget, 'revid', rev, custom, repo)
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
            elif item == 'rawbranch':
                if ctx.node() in repo.branchtags().values():
                    return hglib.toutf(ctx.branch())
                return None
            elif item == 'branch':
                value = self.get_data(widget, 'rawbranch', rev, custom, repo)
                if value:
                    dblist = repo.ui.config('tortoisehg', 'deadbranch', '')
                    if dblist and value in [hglib.toutf(b.strip()) \
                                            for b in dblist.split(',')]:
                        value = None
                return value
            elif item == 'tags':
                value = hglib.toutf(', '.join(ctx.tags()))
                if len(value) == 0:
                    return None
                return value
            elif item == 'ishead':
                return len(ctx.children()) == 0
            return default_func(widget, ctx)
        ctx = repo[rev]
        if custom.has_key(item) and custom[item].has_key('data'):
            return custom[item]['data'](widget, ctx)
        return preset_func(widget, ctx)

    def get_label(self, widget, item, rev, custom, repo):
        def default_func(widget):
            return ''
        def preset_func(widget):
            try:
                return self.LABELS[item]
            except:
                return default_func(widget)
        if custom.has_key(item) and custom[item].has_key('label'):
            return custom[item]['label'](widget)
        return preset_func(widget)

    def get_markup(self, widget, item, rev, custom, repo):
        def default_func(widget, value):
            return gtklib.markup_escape_text(value)
        def preset_func(widget, value):
            if item in ('rev', 'revnum', 'revid'):
                return gtklib.markup(value, face='monospace', size='9000')
            elif item in ('rawbranch', 'branch'):
                return gtklib.markup(' %s ' % value, color='black',
                                     background='#aaffaa')
            elif item == 'tags':
                opts = dict(color='black', background='#ffffaa')
                tags = value.split(', ')
                tags = [gtklib.markup(' %s ' % tag, **opts) for tag in tags]
                return ' '.join(tags)
            return default_func(widget, value)
        value = self.get_data(widget, item, rev, custom, repo)
        if value is None:
            return None
        if custom.has_key(item) and custom[item].has_key('markup'):
            return custom[item]['markup'](widget, value)
        return preset_func(widget, value)

class CachedChangesetInfo(ChangesetInfo):

    def __init__(self):
        ChangesetInfo.__init__(self)
        self.cache = {}

    def try_cache(self, target, func, *args):
        widget, item, rev, custom, repo = args
        key = target + item + str(rev) + str(custom) + str(id(repo))
        try:
            return self.cache[key]
        except KeyError:
            pass
        self.cache[key] = value = func(self, *args)
        return value

    def get_data(self, *args):
        return self.try_cache('data', ChangesetInfo.get_data, *args)

    def get_label(self, *args):
        return self.try_cache('label', ChangesetInfo.get_label, *args)

    def get_markup(self, *args):
        return self.try_cache('markup', ChangesetInfo.get_markup, *args)

class ChangesetBase(object):

    def __init__(self, rev, custom, repo, info=None):
        self.rev = str(rev)
        self.custom = custom
        self.repo = repo
        if info is None:
            info = ChangesetInfo()
        self.info = info

    def get_data(self, item):
        return self.info.get_data(self, item, self.rev, self.custom, self.repo)

    def get_label(self, item):
        return self.info.get_label(self, item, self.rev, self.custom, self.repo)

    def get_markup(self, item):
        return self.info.get_markup(self, item, self.rev, self.custom, self.repo)

    def update(self, rev=None, custom=None, repo=None):
        if rev is not None:
            self.rev = str(rev)
        if custom is not None:
            self.custom = custom
        if repo is not None:
            self.repo = repo

class ChangesetPanel(ChangesetBase, gtk.Frame):

    def __init__(self, rev, style, custom, repo, info=None):
        ChangesetBase.__init__(self, rev, custom, repo, info)
        gtk.Frame.__init__(self)

        self.set_shadow_type(gtk.SHADOW_NONE)
        self.csstyle = style

        # layout table for contents
        self.table = gtklib.LayoutTable(ypad=1, headopts={'weight': 'bold'})
        self.add(self.table)

        self.update()

    def update(self, rev=None, style=None, custom=None, repo=None):
        ChangesetBase.update(self, rev, custom, repo)
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

class ChangesetLabel(ChangesetBase, gtk.Label):

    def __init__(self, rev, style, custom, repo, info=None):
        ChangesetBase.__init__(self, rev, custom, repo, info)
        gtk.Label.__init__(self)

        self.set_alignment(0, 0.5)
        self.csstyle = style

        self.update()

    def update(self, rev=None, style=None, custom=None, repo=None):
        ChangesetBase.update(self, rev, custom, repo)
        if style is not None:
            self.csstyle = style

        if 'selectable' in self.csstyle:
            sel = self.csstyle['selectable']
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

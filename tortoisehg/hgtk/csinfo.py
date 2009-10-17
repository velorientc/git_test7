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

def create(repo, rev=None, style=None, custom=None, **kargs):
    return CachedFactory(repo, custom, style, rev, **kargs)()

def factory(*args, **kargs):
    return CachedFactory(*args, **kargs)

def panelstyle(**kargs):
    kargs['type'] = 'panel'
    if 'contents' not in kargs:
        kargs['contents'] = PANEL_DEFAULT
    return kargs

def labelstyle(**kargs):
    kargs['type'] = 'label'
    return kargs

def custom(**kargs):
    return kargs

class CachedFactory(object):

    def __init__(self, repo=None, custom=None, style=None, rev=None,
                 withupdate=False, widgetcache=False):
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
            style = panelstyle()
        self.csstyle = style
        if rev is None:
            rev = 'tip'
        self.rev = rev
        self.info = CachedChangesetInfo()

        self.withupdate = withupdate
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
                widget = ChangesetPanel(*args)
            elif type == 'label':
                widget = ChangesetLabel(*args)
            else:
                raise _("unknown 'type': %s") % type
            if hasattr(self, 'cache'):
                self.cache[key] = widget
            if self.withupdate:
                widget.update()
            return widget
        else:
            raise _("must be specified 'type' in style")

class UnknownItem(Exception):
    pass

class ChangesetInfo(object):

    LABELS = {'rev': _('rev:'), 'revnum': _('rev:'), 'revid': _('rev:'),
              'summary': _('summary:'), 'user': _('user:'),
              'date': _('date:'), 'branch': _('branch:'), 'tags': _('tags:'),
              'rawbranch': _('branch:'), 'rawtags': _('tags:')}

    def __init__(self):
        pass

    def get_data(self, item, *args):
        widget, rev, custom, repo = args
        def default_func(widget, item, ctx):
            return None
        def preset_func(widget, item, ctx):
            if item == 'rev':
                revnum = self.get_data('revnum', *args)
                revid = self.get_data('revid', *args)
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
                value = self.get_data('rawbranch', *args)
                if value:
                    dblist = repo.ui.config('tortoisehg', 'deadbranch', '')
                    if dblist and value in [hglib.toutf(b.strip()) \
                                            for b in dblist.split(',')]:
                        value = None
                return value
            elif item == 'rawtags':
                value = [hglib.toutf(tag) for tag in ctx.tags()]
                if len(value) == 0:
                    return None
                return value
            elif item == 'tags':
                value = self.get_data('rawtags', *args)
                if value:
                    htags = repo.ui.config('tortoisehg', 'hidetags', '')
                    htags = [hglib.toutf(b.strip()) for b in htags.split()]
                    value = [tag for tag in value if tag not in htags]
                    if len(value) == 0:
                        value = None
                return value
            elif item == 'ishead':
                return len(ctx.children()) == 0
            raise UnknownItem(item)
        ctx = repo[rev]
        if custom.has_key('data'):
            try:
                return custom['data'](widget, item, ctx)
            except UnknownItem:
                pass
        try:
            return preset_func(widget, item, ctx)
        except UnknownItem:
            pass
        return default_func(widget, item, ctx)

    def get_label(self, item, widget, rev, custom, repo):
        def default_func(widget, item):
            return ''
        def preset_func(widget, item):
            try:
                return self.LABELS[item]
            except KeyError:
                raise UnknownItem(item)
        if custom.has_key('label'):
            try:
                return custom['label'](widget, item)
            except UnknownItem:
                pass
        try:
            return preset_func(widget, item)
        except UnknownItem:
            pass
        return default_func(widget, item)

    def get_markup(self, item, widget, rev, custom, repo):
        def default_func(widget, item, value):
            return ''
        def preset_func(widget, item, value):
            if item in ('rev', 'revnum', 'revid'):
                return gtklib.markup(value, face='monospace', size='9000')
            elif item in ('rawbranch', 'branch'):
                return gtklib.markup(' %s ' % value, color='black',
                                     background='#aaffaa')
            elif item in ('rawtags', 'tags'):
                opts = dict(color='black', background='#ffffaa')
                tags = [gtklib.markup(' %s ' % tag, **opts) for tag in value]
                return ' '.join(tags)
            elif item in ('summary', 'user', 'date'):
                return gtklib.markup(value)
            raise UnknownItem(item)
        value = self.get_data(item, widget, rev, custom, repo)
        if value is None:
            return None
        if custom.has_key('markup'):
            try:
                return custom['markup'](widget, item, value)
            except UnknownItem:
                pass
        try:
            return preset_func(widget, item, value)
        except UnknownItem:
            pass
        return default_func(widget, item, value)

class CachedChangesetInfo(ChangesetInfo):

    def __init__(self):
        ChangesetInfo.__init__(self)
        self.cache = {}

    def try_cache(self, target, func, *args):
        item, widget, rev, custom, repo = args
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
        return self.info.get_data(item, self, self.rev, self.custom, self.repo)

    def get_label(self, item):
        return self.info.get_label(item, self, self.rev, self.custom, self.repo)

    def get_markup(self, item):
        return self.info.get_markup(item, self, self.rev, self.custom, self.repo)

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

        sel = self.csstyle.get('selectable', False)
        assert isinstance(sel, bool)

        # build info
        self.table.clear_rows()
        for item in contents:
            markups = self.get_markup(item)
            if not markups:
                continue
            if isinstance(markups, basestring):
                markups = (markups,)
            for text in markups:
                body = gtk.Label()
                body.set_markup(text)
                body.set_selectable(sel)
                self.table.add_row(self.get_label(item), body)
        self.show_all()

class ChangesetLabel(ChangesetBase, gtk.Label):

    def __init__(self, rev, style, custom, repo, info=None):
        ChangesetBase.__init__(self, rev, custom, repo, info)
        gtk.Label.__init__(self)

        self.set_alignment(0, 0.5)
        self.csstyle = style

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
                markups = self.get_markup(item)
                if not markups:
                    continue
                if isinstance(markups, basestring):
                    markups = (markups,)
                data[item] = ', '.join(markups)
            if len(data) == 0:
                continue
            # insert data & append to label
            info += snip % data
        self.set_markup(info)

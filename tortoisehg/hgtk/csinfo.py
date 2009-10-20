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

from mercurial import patch, util
from mercurial.node import short, hex

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths

from tortoisehg.hgtk import gtklib

PANEL_DEFAULT = ('rev', 'summary', 'user', 'date', 'branch', 'tags')

def create(repo, target=None, style=None, custom=None, **kargs):
    return CachedFactory(repo, custom, style, target, **kargs)()

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

    def __init__(self, repo, custom=None, style=None, target=None,
                 withupdate=False, widgetcache=False):
        if repo is None:
            raise _('must be specified repository')
        self.repo = repo
        self.target = target
        if custom is None:
            custom = {}
        self.custom = custom
        if style is None:
            style = panelstyle()
        self.csstyle = style
        self.info = CachedSummaryInfo()

        self.withupdate = withupdate
        if widgetcache:
            self.cache = {}

    def __call__(self, target=None, style=None, custom=None, repo=None):
        # try to create a context object
        if target is None:
            target = self.target
        if repo is None:
            repo = self.repo

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

        if 'type' not in style:
            raise _("must be specified 'type' in style")
        type = style['type']
        assert type in ('panel', 'label')

        # check widgets cache
        if target is None or repo is None:
            key = None
        else:
            key = type + str(target) + str(style) + str(custom) + repo.root
        if hasattr(self, 'cache') and key:
            try:
                return self.cache[key]
            except KeyError:
                pass

        # create widget
        args = (target, style, custom, repo, self.info)
        if type == 'panel':
            widget = SummaryPanel(*args)
        else:
            widget = SummaryLabel(*args)
        if hasattr(self, 'cache') and key:
            self.cache[key] = widget
        if self.withupdate:
            widget.update()
        return widget

class UnknownItem(Exception):
    pass

def create_context(repo, target):
    if repo is None or target is None:
        return None
    ctx = PatchContext(repo, target)
    if ctx is None:
        ctx = ChangesetContext(repo, target)
    return ctx

def ChangesetContext(repo, rev):
    if repo is None or rev is None:
        return None
    try:
        ctx = repo[rev]
    except (hglib.LookupError, hglib.RepoLookupError, hglib.RepoError):
        ctx = None
    return ctx

def PatchContext(repo, patchpath, cache={}):
    if repo is None or patchpath is None:
        return None
    # check path
    if not os.path.isabs(patchpath) or not os.path.isfile(patchpath):
        return None
    # check cache
    mtime = os.path.getmtime(patchpath)
    key = repo.root + patchpath
    holder = cache.get(key, None)
    if holder is not None and mtime == holder[0]:
        return holder[1]
    # create a new context object
    ctx = patchctx(patchpath, repo)
    cache[key] = (mtime, ctx)
    return ctx

class patchctx(object):

    def __init__(self, patchpath, repo):
        self._path = patchpath
        self._patchname = os.path.basename(patchpath)
        self._repo = repo
        pf = open(patchpath)
        try:
            data = patch.extract(self._repo.ui, pf)
            tmpfile, msg, user, date, branch, node, p1, p2 = data
            if tmpfile:
                os.unlink(tmpfile)
        finally:
            pf.close()
        self._node = node
        self._user = user and hglib.toutf(user) or ''
        self._date = date and util.parsedate(date) or None
        self._desc = msg and hglib.toutf(msg.rstrip('\r\n')) or ''
        self._branch = branch and hglib.toutf(branch) or ''
        self._parents = []
        for p in (p1, p2):
            if not p:
                continue
            try:
                self._parents.append(repo[p])
            except (hglib.LookupError, hglib.RepoLookupError, hglib.RepoError):
                self._parents.append(p)

    def __str__(self):
        return short(self.node())

    def __int__(self):
        return self.rev()

    def node(self): return self._node
    def rev(self): return None
    def hex(self): return hex(self.node())
    def user(self): return self._user
    def date(self): return self._date
    def description(self): return self._desc
    def branch(self): return self._branch
    def tags(self): return ()
    def parents(self): return self._parents
    def children(self): return ()

class SummaryInfo(object):

    LABELS = {'rev': _('Revision:'), 'revnum': _('Revision:'),
              'revid': _('Revision:'), 'summary': _('Summary:'),
              'user': _('User:'), 'age': _('Age:'), 'date': _('Date:'),
              'branch': _('Branch:'), 'tags': _('Tags:'),
              'rawbranch': _('Branch:'), 'rawtags': _('Tags:')}

    def __init__(self):
        pass

    def get_data(self, item, *args):
        widget, ctx, custom = args
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
            elif item == 'desc':
                return hglib.toutf(ctx.description().replace('\0', ''))
            elif item == 'summary':
                desc = self.get_data('desc', *args)
                value = desc.split('\n')[0][:80]
                if len(value) == 0:
                    return  None
                return value
            elif item == 'user':
                return hglib.toutf(ctx.user())
            elif item == 'date':
                return hglib.displaytime(ctx.date())
            elif item == 'age':
                return hglib.age(ctx.date())
            elif item == 'rawbranch':
                return hglib.toutf(ctx.branch())
            elif item == 'branch':
                value = self.get_data('rawbranch', *args)
                if value:
                    repo = ctx._repo
                    if ctx.node() not in repo.branchtags().values():
                        return None
                    dblist = repo.ui.config('tortoisehg', 'deadbranch', '')
                    if dblist and value in [hglib.toutf(b.strip()) \
                                            for b in dblist.split(',')]:
                        return None
                return value
            elif item == 'rawtags':
                value = [hglib.toutf(tag) for tag in ctx.tags()]
                if len(value) == 0:
                    return None
                return value
            elif item == 'tags':
                value = self.get_data('rawtags', *args)
                if value:
                    repo = ctx._repo
                    htags = repo.ui.config('tortoisehg', 'hidetags', '')
                    htags = [hglib.toutf(b.strip()) for b in htags.split()]
                    value = [tag for tag in value if tag not in htags]
                    if len(value) == 0:
                        return None
                return value
            elif item == 'ishead':
                return len(ctx.children()) == 0
            raise UnknownItem(item)
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

    def get_label(self, item, widget, ctx, custom):
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

    def get_markup(self, item, widget, ctx, custom):
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
            elif item in ('desc', 'summary', 'user', 'date', 'age'):
                return gtklib.markup(value)
            raise UnknownItem(item)
        value = self.get_data(item, widget, ctx, custom)
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

class CachedSummaryInfo(SummaryInfo):

    def __init__(self):
        SummaryInfo.__init__(self)
        self.cache = {}

    def try_cache(self, target, func, *args):
        item, widget, ctx, custom = args
        root = ctx._repo.root
        repoid = id(ctx._repo)
        try:
            cacheinfo = self.cache[root]
            if cacheinfo[0] != repoid:
                # clear cache
                del self.cache[root] 
                cacheinfo = None
        except KeyError:
            cacheinfo = None
        if cacheinfo is None:
            cacheinfo = (repoid, {})
            self.cache[root] = cacheinfo
        key = target + item + ctx.hex() + str(custom)
        try:
            return cacheinfo[1][key]
        except KeyError:
            pass
        cacheinfo[1][key] = func(self, *args)
        return cacheinfo[1][key]

    def get_data(self, *args):
        return self.try_cache('data', SummaryInfo.get_data, *args)

    def get_label(self, *args):
        return self.try_cache('label', SummaryInfo.get_label, *args)

    def get_markup(self, *args):
        return self.try_cache('markup', SummaryInfo.get_markup, *args)


class SummaryBase(object):

    def __init__(self, target, custom, repo, info=None):
        if target is None:
            self.target = None
        else:
            self.target = str(target)
        self.custom = custom
        self.repo = repo
        if info is None:
            info = SummaryInfo()
        self.info = info
        self.ctx = create_context(repo, self.target)

    def get_data(self, item):
        return self.info.get_data(item, self, self.ctx, self.custom)

    def get_label(self, item):
        return self.info.get_label(item, self, self.ctx, self.custom)

    def get_markup(self, item):
        return self.info.get_markup(item, self, self.ctx, self.custom)

    def update(self, target=None, custom=None, repo=None):
        if target is None:
            target = self.target
        if target is not None:
            target = str(target)
        if custom is not None:
            self.custom = custom
        if repo is None:
            repo = self.repo
        self.ctx = create_context(repo, target)
        if self.ctx is None:
            return False # cannot update
        self.target = target
        self.repo = repo
        return True

class SummaryPanel(SummaryBase, gtk.Frame):

    def __init__(self, target, style, custom, repo, info=None):
        SummaryBase.__init__(self, target, custom, repo, info)
        gtk.Frame.__init__(self)

        self.set_shadow_type(gtk.SHADOW_NONE)
        self.csstyle = style

        self.expander = gtk.Expander()
        self.expander.set_expanded(True)
        self.add(self.expander)

        # layout table for contents
        self.table = gtklib.LayoutTable(ypad=1, headopts={'weight': 'bold'})

        self.expander.add(self.table)

    def update(self, target=None, style=None, custom=None, repo=None):
        if not SummaryBase.update(self, target, custom, repo):
            return False # cannot update

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
        first = True
        self.table.clear_rows()
        for item in contents:
            markups = self.get_markup(item)
            if not markups:
                continue
            if isinstance(markups, basestring):
                markups = (markups,)
            for text in markups:
                body = gtk.Label()
                body.set_selectable(sel)
                body.set_markup(text)
                if first:
                    self.expander.set_label_widget(body)
                    first = False
                else:
                    self.table.add_row(self.get_label(item), body)
        self.show_all()

        return True

class SummaryLabel(SummaryBase, gtk.Label):

    def __init__(self, target, style, custom, repo, info=None):
        SummaryBase.__init__(self, target, custom, repo, info)
        gtk.Label.__init__(self)

        self.set_alignment(0, 0.5)
        self.csstyle = style

    def update(self, target=None, style=None, custom=None, repo=None):
        if not SummaryBase.update(self, target, custom, repo):
            return False # cannot update

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

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
import binascii

from mercurial import patch, util, error
from mercurial.node import hex

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths

from tortoisehg.hgtk import gtklib

PANEL_DEFAULT = ('rev', 'summary', 'user', 'dateage', 'branch', 'tags', 'transplant', 'p4', 'svn')

def create(repo, target=None, style=None, custom=None, **kargs):
    return Factory(repo, custom, style, target, **kargs)()

def factory(*args, **kargs):
    return Factory(*args, **kargs)

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

class Factory(object):

    def __init__(self, repo, custom=None, style=None, target=None,
                 withupdate=False):
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

        # create widget
        args = (target, style, custom, repo, self.info)
        if type == 'panel':
            widget = SummaryPanel(*args)
        else:
            widget = SummaryLabel(*args)
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
    except (error.LookupError, error.RepoLookupError, error.RepoError):
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

    def __init__(self, patchpath, repo, patchHandle=None):
        """ Read patch context from file
        :param patchHandle: If set, then the patch is a temporary.
            The provided handle is used to read the patch and
            the patchpath contains the name of the patch. 
            The handle is NOT closed.
        """
        self._path = patchpath
        self._patchname = os.path.basename(patchpath)
        self._repo = repo
        if patchHandle:
            pf = patchHandle
            pf_start_pos = pf.tell()
        else:
            pf = open(patchpath)
        try:
            data = patch.extract(self._repo.ui, pf)
            tmpfile, msg, user, date, branch, node, p1, p2 = data
            if tmpfile:
                os.unlink(tmpfile)
        finally:
            if patchHandle:
                pf.seek(pf_start_pos)
            else:
                pf.close()
        if not msg and hasattr(repo, 'mq'):
            # attempt to get commit message
            from hgext import mq
            msg = mq.patchheader(repo.mq.join(self._patchname)).message
            if msg:
                msg = '\n'.join(msg)
        self._node = node
        self._user = user and hglib.toutf(user) or ''
        self._date = date and util.parsedate(date) or None
        self._desc = msg and msg or ''
        self._branch = branch and hglib.toutf(branch) or ''
        self._parents = []
        for p in (p1, p2):
            if not p:
                continue
            try:
                self._parents.append(repo[p])
            except (error.LookupError, error.RepoLookupError, error.RepoError):
                self._parents.append(p)

    def __str__(self):
        node = self.node()
        if node:
            return node[:12]
        return ''

    def __int__(self):
        return self.rev()

    def node(self): return self._node
    def rev(self): return None
    def hex(self):
        node = self.node()
        if node:
            return hex(node)
        return ''
    def user(self): return self._user
    def date(self): return self._date
    def description(self): return self._desc
    def branch(self): return self._branch
    def tags(self): return ()
    def parents(self): return self._parents
    def children(self): return ()
    def extra(self): return {}

class SummaryInfo(object):

    LABELS = {'rev': _('Revision:'), 'revnum': _('Revision:'),
              'revid': _('Revision:'), 'summary': _('Summary:'),
              'user': _('User:'), 'date': _('Date:'),'age': _('Age:'),
              'dateage': _('Date:'), 'branch': _('Branch:'),
              'tags': _('Tags:'), 'rawbranch': _('Branch:'),
              'rawtags': _('Tags:'), 'transplant': _('Transplant:'),
              'p4': _('Perforce:'), 'svn': _('Subversion:'),
              'shortuser': _('User:')}

    def __init__(self):
        pass

    def get_data(self, item, widget, ctx, custom, **kargs):
        args = (widget, ctx, custom)
        def default_func(widget, item, ctx):
            return None
        def preset_func(widget, item, ctx):
            if item == 'rev':
                revnum = self.get_data('revnum', *args)
                revid = self.get_data('revid', *args)
                if revid:
                    return (revnum, revid)
                return None
            elif item == 'revnum':
                return ctx.rev()
            elif item == 'revid':
                return str(ctx)
            elif item == 'desc':
                return hglib.toutf(ctx.description().replace('\0', ''))
            elif item == 'summary':
                value = ctx.description().replace('\0', '').split('\n')[0]
                if len(value) == 0:
                    return  None
                return hglib.toutf(hglib.tounicode(value)[:80])
            elif item == 'user':
                return hglib.toutf(ctx.user())
            elif item == 'shortuser':
                return hglib.toutf(hglib.username(ctx.user()))
            elif item == 'dateage':
                date = self.get_data('date', *args)
                age = self.get_data('age', *args)
                if date and age:
                    return (date, age)
                return None
            elif item == 'date':
                date = ctx.date()
                if date:
                    return hglib.displaytime(date)
                return None
            elif item == 'age':
                date = ctx.date()
                if date:
                    return hglib.age(date)
                return None
            elif item == 'rawbranch':
                value = ctx.branch()
                if value:
                    return hglib.toutf(value)
                return None
            elif item == 'branch':
                value = self.get_data('rawbranch', *args)
                if value:
                    repo = ctx._repo
                    if ctx.node() not in repo.branchtags().values():
                        return None
                    dblist = hglib.getdeadbranch(repo.ui)
                    if value in dblist:
                        return None
                    return value
                return None
            elif item == 'rawtags':
                value = [hglib.toutf(tag) for tag in ctx.tags()]
                if len(value) == 0:
                    return None
                return value
            elif item == 'tags':
                value = self.get_data('rawtags', *args)
                if value:
                    htlist = hglib.gethidetags(ctx._repo.ui)
                    tags = [tag for tag in value if tag not in htlist]
                    if len(tags) == 0:
                        return None
                    return tags
                return None
            elif item == 'transplant':
                extra = ctx.extra()
                try:
                    ts = extra['transplant_source']
                    if ts:
                        return binascii.hexlify(ts)
                except KeyError:
                    pass
                return None
            elif item == 'p4':
                extra = ctx.extra()
                p4cl = extra.get('p4', None)
                return p4cl and ('changelist %s' % p4cl)
            elif item == 'svn':
                extra = ctx.extra()
                cvt = extra.get('convert_revision', '')
                if cvt.startswith('svn:'):
                    result = cvt.split('/', 1)[-1]
                    if cvt != result:
                        return result
                    return cvt.split('@')[-1]
                else:
                    return None
            elif item == 'ishead':
                childbranches = [cctx.branch() for cctx in ctx.children()]
                return ctx.branch() not in childbranches
            raise UnknownItem(item)
        if custom.has_key('data') and not kargs.get('usepreset', False):
            try:
                return custom['data'](widget, item, ctx)
            except UnknownItem:
                pass
        try:
            return preset_func(widget, item, ctx)
        except UnknownItem:
            pass
        return default_func(widget, item, ctx)

    def get_label(self, item, widget, ctx, custom, **kargs):
        def default_func(widget, item):
            return ''
        def preset_func(widget, item):
            try:
                return self.LABELS[item]
            except KeyError:
                raise UnknownItem(item)
        if custom.has_key('label') and not kargs.get('usepreset', False):
            try:
                return custom['label'](widget, item)
            except UnknownItem:
                pass
        try:
            return preset_func(widget, item)
        except UnknownItem:
            pass
        return default_func(widget, item)

    def get_markup(self, item, widget, ctx, custom, **kargs):
        args = (widget, ctx, custom)
        mono = dict(face='monospace', size='9000')
        def default_func(widget, item, value):
            return ''
        def preset_func(widget, item, value):
            if item == 'rev':
                revnum, revid = value
                revid = gtklib.markup(revid, **mono)
                if revnum is not None and revid is not None:
                    return '%s (%s)' % (revnum, revid)
                return '%s' % revid
            elif item in ('revid', 'transplant'):
                return gtklib.markup(value, **mono)
            elif item in ('revnum', 'p4', 'svn'):
                return str(value)
            elif item in ('rawbranch', 'branch'):
                return gtklib.markup(' %s ' % value, color=gtklib.BLACK,
                                     background=gtklib.PGREEN)
            elif item in ('rawtags', 'tags'):
                opts = dict(color=gtklib.BLACK, background=gtklib.PYELLOW)
                tags = [gtklib.markup(' %s ' % tag, **opts) for tag in value]
                return ' '.join(tags)
            elif item in ('desc', 'summary', 'user', 'shortuser',
                          'date', 'age'):
                return gtklib.markup(value)
            elif item == 'dateage':
                return gtklib.markup('%s (%s)' % value)
            raise UnknownItem(item)
        value = self.get_data(item, *args)
        if value is None:
            return None
        if custom.has_key('markup') and not kargs.get('usepreset', False):
            try:
                return custom['markup'](widget, item, value)
            except UnknownItem:
                pass
        try:
            return preset_func(widget, item, value)
        except UnknownItem:
            pass
        return default_func(widget, item, value)

    def get_widget(self, item, widget, ctx, custom, **kargs):
        args = (widget, ctx, custom)
        def default_func(widget, item, markups):
            if isinstance(markups, basestring):
                markups = (markups,)
            labels = []
            for text in markups:
                label = gtk.Label()
                label.set_markup(text)
                labels.append(label)
            return labels
        markups = self.get_markup(item, *args)
        if not markups:
            return None
        if custom.has_key('widget') and not kargs.get('usepreset', False):
            try:
                return custom['widget'](widget, item, markups)
            except UnknownItem:
                pass
        return default_func(widget, item, markups)

class CachedSummaryInfo(SummaryInfo):

    def __init__(self):
        SummaryInfo.__init__(self)
        self.clear_cache()

    def try_cache(self, target, func, *args, **kargs):
        item, widget, ctx, custom = args
        if target != 'widget': # no cache for widget
            root = ctx._repo.root
            repoid = id(ctx._repo)
            try:
                cacheinfo = self.cache[root]
                if cacheinfo[0] != repoid:
                    del self.cache[root] # clear cache
                    cacheinfo = None
            except KeyError:
                cacheinfo = None
            if cacheinfo is None:
                self.cache[root] = cacheinfo = (repoid, {})
            revid = ctx.hex()
            if not revid and hasattr(ctx, '_path'):
                revid = ctx._path
            key = target + item + revid + str(custom)
            try:
                return cacheinfo[1][key]
            except KeyError:
                pass
        value = func(self, *args, **kargs)
        if target != 'widget': # do not cache widgets
            cacheinfo[1][key] = value
        return value

    def get_data(self, *args, **kargs):
        return self.try_cache('data', SummaryInfo.get_data, *args, **kargs)

    def get_label(self, *args, **kargs):
        return self.try_cache('label', SummaryInfo.get_label, *args, **kargs)

    def get_markup(self, *args, **kargs):
        return self.try_cache('markup', SummaryInfo.get_markup, *args, **kargs)

    def get_widget(self, *args, **kargs):
        return self.try_cache('widget', SummaryInfo.get_widget, *args, **kargs)

    def clear_cache(self):
        self.cache = {}

class SummaryBase(object):

    def __init__(self, target, custom, repo, info):
        if target is None:
            self.target = None
        else:
            self.target = str(target)
        self.custom = custom
        self.repo = repo
        self.info = info
        self.ctx = create_context(repo, self.target)

    def get_data(self, item, **kargs):
        return self.info.get_data(item, self, self.ctx, self.custom, **kargs)

    def get_label(self, item, **kargs):
        return self.info.get_label(item, self, self.ctx, self.custom, **kargs)

    def get_markup(self, item, **kargs):
        return self.info.get_markup(item, self, self.ctx, self.custom, **kargs)

    def get_widget(self, item, **kargs):
        return self.info.get_widget(item, self, self.ctx, self.custom, **kargs)

    def update(self, target=None, custom=None, repo=None):
        self.ctx = None
        if type(target) == patchctx:
            # If a patchctx is specified as target, use it instead
            # of creating a context from revision or patch file
            self.ctx = target
            target = None
            self.target = None
        if target is None:
            target = self.target
        if target is not None:
            target = str(target)
            self.target = target
        if custom is not None:
            self.custom = custom
        if repo is None:
            repo = self.repo
        if repo is not None:
            self.repo = repo
        if self.ctx is None:
            self.ctx = create_context(repo, target)
        if self.ctx is None:
            return False # cannot update
        return True

class SummaryPanel(SummaryBase, gtk.Frame):

    def __init__(self, target, style, custom, repo, info):
        SummaryBase.__init__(self, target, custom, repo, info)
        gtk.Frame.__init__(self)

        self.set_shadow_type(gtk.SHADOW_NONE)
        self.csstyle = style

        self.expander = gtk.Expander()
        self.expander.set_expanded(False)

        # layout table for contents
        self.table = gtklib.LayoutTable(ypad=1, headopts={'weight': 'bold'})

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

        use_expander = self.csstyle.get('expander', False)

        # build info
        first = True
        self.table.clear_rows()
        for item in contents:
            widgets = self.get_widget(item)
            if not widgets:
                continue
            if isinstance(widgets, gtk.Widget):
                widgets = (widgets,)
            if not self.get_child():
                if use_expander:
                    self.add(self.expander)
                    self.expander.add(self.table)
                else:
                    self.add(self.table)
            for widget in widgets:
                if hasattr(widget, 'set_selectable'):
                    widget.set_selectable(sel)
                if use_expander and first:
                    self.expander.set_label_widget(widget)
                    first = False
                else:
                    self.table.add_row(self.get_label(item), widget)
        self.show_all()

        return True

class SummaryLabel(SummaryBase, gtk.Label):

    def __init__(self, target, style, custom, repo, info):
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

        return True

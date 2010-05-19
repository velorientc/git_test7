# csinfo.py - An embeddable widget for changeset summary
#
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import re
import os
import binascii

from PyQt4.QtCore import Qt, QSize
from PyQt4.QtGui import QWidget, QLabel, QHBoxLayout, QPushButton

from mercurial import patch, util, error
from mercurial.node import hex

from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, icon

PANEL_DEFAULT = ('rev', 'summary', 'user', 'dateage', 'branch', 'tags',
                 'transplant', 'p4', 'svn')

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
        self.info = SummaryInfo()

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
        mono = dict(family='monospace', size='9pt', space='pre')
        def default_func(widget, item, value):
            return ''
        def preset_func(widget, item, value):
            if item == 'rev':
                revnum, revid = value
                revid = qtlib.markup(revid, **mono)
                if revnum is not None and revid is not None:
                    return '%s (%s)' % (revnum, revid)
                return '%s' % revid
            elif item in ('revid', 'transplant'):
                return qtlib.markup(value, **mono)
            elif item in ('revnum', 'p4', 'svn'):
                return str(value)
            elif item in ('rawbranch', 'branch'):
                opts = dict(fg='black', bg='#aaffaa')
                return qtlib.markup(' %s ' % value, **opts)
            elif item in ('rawtags', 'tags'):
                opts = dict(fg='black', bg='#ffffaa')
                tags = [qtlib.markup(' %s ' % tag, **opts) for tag in value]
                return ' '.join(tags)
            elif item in ('desc', 'summary', 'user', 'shortuser',
                          'date', 'age'):
                return qtlib.markup(value)
            elif item == 'dateage':
                return qtlib.markup('%s (%s)' % value)
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
                label = QLabel()
                label.setText(text)
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

PANEL_TMPL = '<tr><td style="padding-right:6px">%s</td><td>%s</td></tr>'

class SummaryPanel(SummaryBase, QWidget):

    def __init__(self, target, style, custom, repo, info):
        SummaryBase.__init__(self, target, custom, repo, info)
        QWidget.__init__(self)

        self.csstyle = style

        hbox = QHBoxLayout()
        hbox.setMargin(0)
        hbox.setSpacing(0)
        self.setLayout(hbox)
        self.revlabel = None
        self.expand_btn = None

    def update(self, target=None, style=None, custom=None, repo=None):
        if not SummaryBase.update(self, target, custom, repo):
            return False # cannot update

        if style is not None:
            self.csstyle = style

        if self.revlabel is None:
            self.revlabel = QLabel()
            self.layout().addWidget(self.revlabel, alignment=Qt.AlignTop)

        if 'expandable' in self.csstyle and self.csstyle['expandable']:
            if self.expand_btn is None:
                self.expand_btn = qtlib.PMButton()
                self.expand_btn.clicked.connect(lambda: self.update())
                margin = QHBoxLayout()
                margin.setMargin(3)
                margin.addWidget(self.expand_btn, alignment=Qt.AlignTop)
                self.layout().insertLayout(0, margin)
            self.expand_btn.setShown(True)
        elif self.expand_btn is not None:
            self.expand_btn.setHidden(True)

        if 'selectable' in self.csstyle:
            sel = self.csstyle['selectable']
            val = sel and Qt.TextSelectableByMouse or Qt.TextBrowserInteraction
            self.revlabel.setTextInteractionFlags(val)

        # build info
        contents = self.csstyle.get('contents', ())
        if 'expandable' in self.csstyle and self.expand_btn is not None \
                                        and self.expand_btn.is_collapsed():
            contents = contents[0:1]

        if 'margin' in self.csstyle:
            margin = self.csstyle['margin']
            assert isinstance(margin, (int, long))
            buf = '<table style="margin: %spx">' % margin
        else:
            buf = '<table>'

        for item in contents:
            markups = self.get_markup(item)
            if not markups:
                continue
            label = qtlib.markup(self.get_label(item), weight='bold')
            if isinstance(markups, basestring):
                markups = [markups,]
            buf += PANEL_TMPL % (label, markups.pop(0))
            for markup in markups:
                buf += PANEL_TMPL % ('&nbsp;', markup)
        buf += '</table>'
        self.revlabel.setText(buf)

        return True

LABEL_PAT = re.compile(r'(?:(?<=%%)|(?<!%)%\()(\w+)(?:\)s)')

class SummaryLabel(SummaryBase, QLabel):

    def __init__(self, target, style, custom, repo, info):
        SummaryBase.__init__(self, target, custom, repo, info)
        QLabel.__init__(self)

        self.csstyle = style

    def update(self, target=None, style=None, custom=None, repo=None):
        if not SummaryBase.update(self, target, custom, repo):
            return False # cannot update

        if style is not None:
            self.csstyle = style

        if 'selectable' in self.csstyle:
            sel = self.csstyle['selectable']
            val = sel and Qt.TextSelectableByMouse or Qt.TextBrowserInteraction
            self.setTextInteractionFlags(val)

        if 'width' in self.csstyle:
            width = self.csstyle.get('width', 0)
            self.setMinimumWidth(width)

        if 'height' in self.csstyle:
            height = self.csstyle.get('height', 0)
            self.setMinimumHeight(height)

        contents = self.csstyle.get('contents', None)

        # build info
        info = ''
        for snip in contents:
            # extract all placeholders
            items = LABEL_PAT.findall(snip)
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
        self.setText(info)

        return True

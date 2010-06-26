# hglib.py - Mercurial API wrappers for TortoiseHg
#
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import sys
import shlex
import time
import inspect

from mercurial import ui, util, extensions, match, bundlerepo, url, cmdutil
from mercurial import dispatch, encoding, templatefilters, filemerge

_encoding = encoding.encoding
_encodingmode = encoding.encodingmode
_fallbackencoding = encoding.fallbackencoding

# extensions which can cause problem with TortoiseHg
_extensions_blacklist = ('color', 'pager', 'progress')

from tortoisehg.util import paths
from tortoisehg.util.i18n import _
from tortoisehg.util.hgversion import hgversion

def tounicode(s):
    """
    Convert the encoding of string from MBCS to Unicode.

    Based on mercurial.util.tolocal().
    Return 'unicode' type string.
    """
    if isinstance(s, unicode):
        return s
    for e in ('utf-8', _encoding):
        try:
            return s.decode(e, 'strict')
        except UnicodeDecodeError:
            pass
    return s.decode(_fallbackencoding, 'replace')

def toutf(s):
    """
    Convert the encoding of string from MBCS to UTF-8.

    Return 'str' type string.
    """
    return tounicode(s).encode('utf-8').replace('\0','')

def fromutf(s):
    """
    Convert the encoding of string from UTF-8 to MBCS

    Return 'str' type string.
    """
    try:
        return s.decode('utf-8').encode(_encoding)
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    try:
        return s.decode('utf-8').encode(_fallbackencoding)
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    u = s.decode('utf-8', 'replace') # last ditch
    return u.encode(_encoding, 'replace')

_tabwidth = None
def gettabwidth(ui):
    global _tabwidth
    if _tabwidth is not None:
        return _tabwidth
    tabwidth = ui.config('tortoisehg', 'tabwidth')
    try:
        tabwidth = int(tabwidth)
        if tabwidth < 1 or tabwidth > 16:
            tabwidth = 0
    except (ValueError, TypeError):
        tabwidth = 0
    _tabwidth = tabwidth
    return tabwidth

_maxdiff = None
def getmaxdiffsize(ui):
    global _maxdiff
    if _maxdiff is not None:
        return _maxdiff
    maxdiff = ui.config('tortoisehg', 'maxdiff')
    try:
        maxdiff = int(maxdiff)
        if maxdiff < 1:
            maxdiff = sys.maxint
    except (ValueError, TypeError):
        maxdiff = 1024 # 1MB by default
    _maxdiff = maxdiff * 1024
    return _maxdiff

_deadbranch = None
def getdeadbranch(ui):
    '''return a list of dead branch names in UTF-8'''
    global _deadbranch
    if _deadbranch is None:
        db = toutf(ui.config('tortoisehg', 'deadbranch', ''))
        dblist = [b.strip() for b in db.split(',')]
        _deadbranch = dblist
    return _deadbranch

def getlivebranch(repo):
    '''return a list of live branch names in UTF-8'''
    lives = []
    deads = getdeadbranch(repo.ui)
    cl = repo.changelog
    for branch, heads in repo.branchmap().iteritems():
        # branch encoded in UTF-8
        if branch in deads:
            # ignore branch names in tortoisehg.deadbranch
            continue
        bheads = [h for h in heads if ('close' not in cl.read(h)[5])]
        if not bheads:
            # ignore branches with all heads closed
            continue
        lives.append(branch.replace('\0', ''))
    return lives

def getlivebheads(repo):
    '''return a list of revs of live branch heads'''
    bheads = []
    for b, ls in repo.branchmap().iteritems():
        bheads += [repo[x] for x in ls]
    heads = [x.rev() for x in bheads if not x.extra().get('close')]
    heads.sort()
    heads.reverse()
    return heads

_hidetags = None
def gethidetags(ui):
    global _hidetags
    if _hidetags is None:
        tags = toutf(ui.config('tortoisehg', 'hidetags', ''))
        taglist = [t.strip() for t in tags.split()]
        _hidetags = taglist
    return _hidetags

def getfilteredtags(repo):
    filtered = []
    hides = gethidetags(repo.ui)
    for tag in list(repo.tags()):
        if tag not in hides:
            filtered.append(tag)
    return filtered

def diffexpand(line):
    'Expand tabs in a line of diff/patch text'
    if _tabwidth is None:
        gettabwidth(ui.ui())
    if not _tabwidth or len(line) < 2:
        return line
    return line[0] + line[1:].expandtabs(_tabwidth)

_fontconfig = None
def getfontconfig(_ui=None):
    global _fontconfig
    if _fontconfig is None:
        if _ui is None:
            _ui = ui.ui()
        # defaults
        _fontconfig = {'fontcomment': 'monospace 10',
                       'fontdiff': 'monospace 10',
                       'fontlist': 'sans 9',
                       'fontlog': 'monospace 10'}
        # overwrite defaults with configured values
        for name, val in _ui.configitems('gtools'):
            if val and name.startswith('font'):
                _fontconfig[name] = val
    return _fontconfig

def invalidaterepo(repo):
    repo.dirstate.invalidate()
    if isinstance(repo, bundlerepo.bundlerepository):
        # Work around a bug in hg-1.3.  repo.invalidate() breaks
        # overlay bundlerepos
        return
    repo.invalidate()
    # way _bookmarks / _bookmarkcurrent cached changed
    # from 1.4 to 1.5...
    for cachedAttr in ('_bookmarks', '_bookmarkcurrent'):
        # Check if it's a property or normal value...
        if is_descriptor(repo, cachedAttr):
            # The very act of calling hasattr would
            # re-cache the property, so just assume it's
            # already cached, and catch the error if it wasn't.
            try:
                delattr(repo, cachedAttr)
            except AttributeError:
                pass
        elif hasattr(repo, cachedAttr):
            setattr(repo, cachedAttr, None)
    if 'mq' in repo.__dict__: #do not create if it does not exist
        repo.mq.invalidate()

def loadextension(ui, name):
    # Between Mercurial revisions 1.2 and 1.3, extensions.load() stopped
    # calling uisetup() after loading an extension.  This could do
    # unexpected things if you use an hg version < 1.3
    extensions.load(ui, name, None)
    mod = extensions.find(name)
    uisetup = getattr(mod, 'uisetup', None)
    if uisetup:
        uisetup(ui)

def _loadextensionwithblacklist(orig, ui, name, path):
    if name.startswith('hgext.') or name.startswith('hgext/'):
        shortname = name[6:]
    else:
        shortname = name
    if shortname in _extensions_blacklist and not path:  # only bundled ext
        return

    return orig(ui, name, path)

def wrapextensionsloader():
    """Wrap extensions.load(ui, name) for blacklist to take effect"""
    extensions.wrapfunction(extensions, 'load',
                            _loadextensionwithblacklist)

def canonpaths(list):
    'Get canonical paths (relative to root) for list of files'
    # This is a horrible hack.  Please remove this when HG acquires a
    # decent case-folding solution.
    canonpats = []
    cwd = os.getcwd()
    root = paths.find_root(cwd)
    for f in list:
        try:
            canonpats.append(util.canonpath(root, cwd, f))
        except util.Abort:
            # Attempt to resolve case folding conflicts.
            fu = f.upper()
            cwdu = cwd.upper()
            if fu.startswith(cwdu):
                canonpats.append(util.canonpath(root, cwd, f[len(cwd+os.sep):]))
            else:
                # May already be canonical
                canonpats.append(f)
    return canonpats

def escapepath(path):
    'Before passing a file path to hg API, it may need escaping'
    p = path
    if '[' in p or '{' in p or '*' in p or '?' in p:
        return 'path:' + p
    else:
        return p

def normpats(pats):
    'Normalize file patterns'
    normpats = []
    for pat in pats:
        kind, p = match._patsplit(pat, None)
        if kind:
            normpats.append(pat)
        else:
            if '[' in p or '{' in p or '*' in p or '?' in p:
                normpats.append('glob:' + p)
            else:
                normpats.append('path:' + p)
    return normpats


def mergetools(ui, values=None):
    'returns the configured merge tools and the internal ones'
    if values == None:
        values = []
    for key, value in ui.configitems('merge-tools'):
        t = key.split('.')[0]
        if t not in values:
            # Ensure the tool is installed
            if filemerge._findtool(ui, t):
                values.append(t)
    values.append('internal:merge')
    values.append('internal:prompt')
    values.append('internal:dump')
    values.append('internal:local')
    values.append('internal:other')
    values.append('internal:fail')
    return values


_difftools = None
def difftools(ui):
    global _difftools
    if _difftools:
        return _difftools

    def fixup_extdiff(diffopts):
        if '$child' not in diffopts:
            diffopts.append('$parent1')
            diffopts.append('$child')
        if '$parent2' in diffopts:
            mergeopts = diffopts[:]
            diffopts.remove('$parent2')
        else:
            mergeopts = []
        return diffopts, mergeopts

    tools = {}
    for cmd, path in ui.configitems('extdiff'):
        if cmd.startswith('cmd.'):
            cmd = cmd[4:]
            if not path:
                path = cmd
            diffopts = ui.config('extdiff', 'opts.' + cmd, '')
            diffopts = shlex.split(diffopts)
            diffopts, mergeopts = fixup_extdiff(diffopts)
            tools[cmd] = [path, diffopts, mergeopts]
        elif cmd.startswith('opts.'):
            continue
        else:
            # command = path opts
            if path:
                diffopts = shlex.split(path)
                path = diffopts.pop(0)
            else:
                path, diffopts = cmd, []
            diffopts, mergeopts = fixup_extdiff(diffopts)
            tools[cmd] = [path, diffopts, mergeopts]
    mt = []
    mergetools(ui, mt)
    for t in mt:
        if t.startswith('internal:'):
            continue
        dopts = ui.config('merge-tools', t + '.diffargs', '')
        mopts = ui.config('merge-tools', t + '.diff3args', '')
        dopts, mopts = shlex.split(dopts), shlex.split(mopts)
        tools[t] = [filemerge._findtool(ui, t), dopts, mopts]
    _difftools = tools
    return tools


def hgcmd_toq(q, label, args):
    '''
    Run an hg command in a background thread, pipe all output to a Queue
    object.  Assumes command is completely noninteractive.
    '''
    class Qui(ui.ui):
        def __init__(self, src=None):
            super(Qui, self).__init__(src)
            self.setconfig('ui', 'interactive', 'off')

        def write(self, *args, **opts):
            if self._buffers:
                self._buffers[-1].extend([str(a) for a in args])
            else:
                for a in args:
                    if label:
                        q.put((str(a), opts.get('label', '')))
                    else:
                        q.put(str(a))

        def plain(self):
            return True

    u = Qui()
    oldterm = os.environ.get('TERM')
    os.environ['TERM'] = 'dumb'
    ret = dispatch._dispatch(u, list(args))
    if oldterm:
        os.environ['TERM'] = oldterm
    return ret

def get_reponame(repo):
    if repo.ui.config('tortoisehg', 'fullpath', False):
        name = repo.root
    elif repo.ui.config('web', 'name', False):
        name = repo.ui.config('web', 'name')
    else:
        name = os.path.basename(repo.root)
    return toutf(name)

def displaytime(date):
    return util.datestr(date, '%Y-%m-%d %H:%M:%S %1%2')

def utctime(date):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(date[0]))

def age(date):
    return templatefilters.age(date)

def username(user):
    author = templatefilters.person(user)
    if not author:
        author = util.shortuser(user)
    return author

def validate_synch_path(path, repo):
    '''
    Validate the path that must be used to sync operations (pull,
    push, outgoing and incoming)
    '''
    return_path = path
    for alias, path_aux in repo.ui.configitems('paths'):
        if path == alias:
            return_path = path_aux
        elif path == url.hidepassword(path_aux):
            return_path = path_aux
    return return_path

def get_repo_bookmarks(repo, values=False):
    """
    Will return the bookmarks for the given repo if the
    bookmarks extension is loaded.
    
    By default, returns a list of bookmark names; if
    values is True, returns a dict mapping names to 
    nodes.
    
    If the extension is not loaded, returns an empty
    list/dict.
    """
    try:
        bookmarks = extensions.find('bookmarks')
    except KeyError:
        return values and {} or []
    if bookmarks:
        # Bookmarks changed from 1.4 to 1.5...
        if hasattr(bookmarks, 'parse'):
            marks = bookmarks.parse(repo)
        elif hasattr(repo, '_bookmarks'):
            marks = repo._bookmarks
        else:
            marks = {}
    else:
        marks = {}
            
    if values:
        return marks
    else:
        return marks.keys()
    
def get_repo_bookmarkcurrent(repo):
    """
    Will return the current bookmark for the given repo
    if the bookmarks extension is loaded, and the
    track.current option is on.
    
    If the extension is not loaded, or track.current
    is not set, returns None
    """
    try:
        bookmarks = extensions.find('bookmarks')
    except KeyError:
        return None
    if bookmarks and repo.ui.configbool('bookmarks', 'track.current'):
        # Bookmarks changed from 1.4 to 1.5...
        if hasattr(bookmarks, 'current'):
            return bookmarks.current(repo)
        elif hasattr(repo, '_bookmarkcurrent'):
            return repo._bookmarkcurrent
    return None

def is_rev_current(repo, rev):
    '''
    Returns True if the revision indicated by 'rev' is the current
    working directory parent.
    
    If rev is '' or None, it is assumed to mean 'tip'.
    '''
    if rev in ('', None):
        rev = 'tip'
    rev = repo.lookup(rev)
    parents = repo.parents()
    
    if len(parents) > 1:
        return False
    
    return rev == parents[0].node()

def is_descriptor(obj, attr):
    """
    Returns True if obj.attr is a descriptor - ie, accessing
    the attribute will actually invoke the '__get__' method of
    some object.

    Returns False if obj.attr exists, but is not a descriptor,
    and None if obj.attr was not found at all.
    """
    for cls in inspect.getmro(obj.__class__):
        if attr in cls.__dict__:
            return hasattr(cls.__dict__[attr], '__get__')
    return None
    
def export(repo, revs, template='hg-%h.patch', fp=None, switch_parent=False,
           opts=None):
    '''
    export changesets as hg patches.
    
    Mercurial moved patch.export to cmdutil.export after version 1.5
    (change e764f24a45ee in mercurial).
    '''   

    try:
        return cmdutil.export(repo, revs, template, fp, switch_parent, opts)
    except AttributeError:
        from mercurial import patch
        return patch.export(repo, revs, template, fp, switch_parent, opts)

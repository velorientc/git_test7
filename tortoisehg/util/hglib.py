# hglib.py - Mercurial API wrappers for TortoiseHg
#
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import sys
import traceback
import shlib
import time
from mercurial import hg, ui, util, extensions, commands, hook, match

from i18n import _
import paths

from mercurial.error import RepoError, ParseError, LookupError
from mercurial.error import UnknownCommand, AmbiguousCommand
from mercurial import dispatch, encoding, util
_encoding = encoding.encoding
_encodingmode = encoding.encodingmode
_fallbackencoding = encoding.fallbackencoding

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
    return tounicode(s).encode('utf-8')

def fromutf(s):
    """
    Convert the encoding of string from UTF-8 to MBCS

    Return 'str' type string.
    """
    try:
        return s.decode('utf-8').encode(_encoding)
    except UnicodeDecodeError:
        pass
    except UnicodeEncodeError:
        pass
    return s.decode('utf-8').encode(_fallbackencoding)

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

def diffexpand(line):
    'Expand tabs in a line of diff/patch text'
    if _tabwidth is None:
        gettabwidth(ui.ui())
    if not _tabwidth or len(line) < 2:
        return line
    return line[0] + line[1:].expandtabs(_tabwidth)

def uiwrite(u, args):
    '''
    write args if there are buffers
    returns True if the caller shall handle writing
    '''
    if u._buffers:
        ui.ui.write(u, *args)
        return False
    return True

def invalidaterepo(repo):
    repo.invalidate()
    repo.dirstate.invalidate()
    if 'mq' in repo.__dict__: #do not create if it does not exist
        repo.mq.invalidate()

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
    from mercurial import filemerge
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


def hgcmd_toq(path, q, *args):
    '''
    Run an hg command in a background thread, pipe all output to a Queue
    object.  Assumes command is completely noninteractive.
    '''
    class Qui(ui.ui):
        def __init__(self, src=None):
            super(Qui, self).__init__(src)
            self.setconfig('ui', 'interactive', 'off')

        def write(self, *args):
            if uiwrite(self, args):
                for a in args:
                    q.put(str(a))
    u = Qui()
    for k, v in u.configitems('defaults'):
        u.setconfig('defaults', k, '')
    return dispatch._dispatch(u, list(args))

def displaytime(date):
    return util.datestr(date, '%Y-%m-%d %H:%M:%S %1%2')

def utctime(date):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(date[0]))

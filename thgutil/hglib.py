"""
hglib.py
 Copyright (C) 2007 Steve Borho <steve@borho.org>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.
"""

import os
import sys
import traceback
import shlib
import time
from mercurial import hg, ui, util, extensions, commands, hook

from i18n import _
import paths

from mercurial.error import RepoError, ParseError, LookupError
from mercurial.error import UnknownCommand, AmbiguousCommand
from mercurial import dispatch, encoding, util
_encoding = encoding.encoding
_encodingmode = encoding.encodingmode
_fallbackencoding = encoding.fallbackencoding
hgversion = util.version()

def toutf(s):
    """
    Convert a string to UTF-8 encoding

    Based on mercurial.util.tolocal()
    """
    for e in ('utf-8', _encoding):
        try:
            return s.decode(e, 'strict').encode('utf-8')
        except UnicodeDecodeError:
            pass
    return s.decode(_fallbackencoding, 'replace').encode('utf-8')

def fromutf(s):
    """
    Convert UTF-8 encoded string to local.

    It's primarily used on strings converted to UTF-8 by toutf().
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
    return dispatch._dispatch(u, list(args))


def displaytime(date):
    return util.datestr(date, '%Y-%m-%d %H:%M:%S %1%2')

def utctime(date):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(date[0]))

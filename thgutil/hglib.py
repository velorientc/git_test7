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

try:
    from mercurial.error import RepoError, ParseError, LookupError
    from mercurial.error import UnknownCommand, AmbiguousCommand
except ImportError:
    from mercurial.cmdutil import UnknownCommand, AmbiguousCommand
    from mercurial.repo import RepoError
    from mercurial.dispatch import ParseError
    from mercurial.revlog import LookupError

from mercurial import dispatch

try:
    from mercurial import encoding
    _encoding = encoding.encoding
    _encodingmode = encoding.encodingmode
    _fallbackencoding = encoding.fallbackencoding
except ImportError:
    _encoding = util._encoding
    _encodingmode = util._encodingmode
    _fallbackencoding = util._fallbackencoding

try:
    # post 1.1.2
    from mercurial import util
    hgversion = util.version()
except AttributeError:
    # <= 1.1.2
    from mercurial import version
    hgversion = version.get_version()

try:
    from mercurial.util import WinIOError
except:
    class WinIOError(Exception):
        'WinIOError stub'

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
    buffers = getattr(u, '_buffers', None)
    if buffers == None:
        buffers = u.buffers
    if buffers:
        ui.ui.write(u, *args)
        return False
    return True

def calliffunc(f):
    return hasattr(f, '__call__') and f() or f


def invalidaterepo(repo):
    repo.invalidate()
    repo.dirstate.invalidate()
    if 'mq' in repo.__dict__: #do not create if it did not exist
        mq = repo.mq
        if hasattr(mq, 'invalidate'):
            #Mercurial 1.3
            mq.invalidate()
        else:
            #Mercurial 1.2
            mqclass = mq.__class__
            repo.mq = mqclass(mq.ui, mq.basepath, mq.path)


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
    if hasattr(ui.ui, 'copy'):
        # Mercurial 1.3
        return dispatch._dispatch(u, list(args))
    else:
        return thgdispatch(u, path, list(args))


def displaytime(date):
    return util.datestr(date, '%Y-%m-%d %H:%M:%S %1%2')

def utctime(date):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(date[0]))

# the remaining functions are only needed for Mercurial versions < 1.3
def _earlygetopt(aliases, args):
    """Return list of values for an option (or aliases).

    The values are listed in the order they appear in args.
    The options and values are removed from args.
    """
    try:
        argcount = args.index("--")
    except ValueError:
        argcount = len(args)
    shortopts = [opt for opt in aliases if len(opt) == 2]
    values = []
    pos = 0
    while pos < argcount:
        if args[pos] in aliases:
            if pos + 1 >= argcount:
                # ignore and let getopt report an error if there is no value
                break
            del args[pos]
            values.append(args.pop(pos))
            argcount -= 2
        elif args[pos][:2] in shortopts:
            # short option can have no following space, e.g. hg log -Rfoo
            values.append(args.pop(pos)[2:])
            argcount -= 1
        else:
            pos += 1
    return values

_loaded = {}
def thgdispatch(ui, path=None, args=[], nodefaults=True):
    '''
    Replicate functionality of mercurial dispatch but force the use
    of the passed in ui for all purposes
    '''

    # clear all user-defined command defaults
    if nodefaults:
        for k, v in ui.configitems('defaults'):
            ui.setconfig('defaults', k, '')

    # read --config before doing anything else
    # (e.g. to change trust settings for reading .hg/hgrc)
    config = _earlygetopt(['--config'], args)
    if config:
        for section, name, value in dispatch._parseconfig(config):
            ui.setconfig(section, name, value)

    # check for cwd
    cwd = _earlygetopt(['--cwd'], args)
    if cwd:
        os.chdir(cwd[-1])

    # read the local repository .hgrc into a local ui object
    path = paths.find_root(path) or ""
    if path:
        try:
            ui.readconfig(os.path.join(path, ".hg", "hgrc"))
        except IOError:
            pass

    # now we can expand paths, even ones in .hg/hgrc
    rpath = _earlygetopt(["-R", "--repository", "--repo"], args)
    if rpath:
        path = ui.expandpath(rpath[-1])

    extensions.loadall(ui)
    if not hasattr(extensions, 'extensions'):
        extensions.extensions = lambda: () # pre-0.9.5, loadall did below
    for name, module in extensions.extensions():
        if name in _loaded:
            continue

        # setup extensions
        extsetup = getattr(module, 'extsetup', None)
        if extsetup:
            extsetup()

        cmdtable = getattr(module, 'cmdtable', {})
        overrides = [cmd for cmd in cmdtable if cmd in commands.table]
        if overrides:
            ui.warn(_("extension '%s' overrides commands: %s\n") %
                    (name, " ".join(overrides)))
        commands.table.update(cmdtable)
        _loaded[name] = 1

    # check for fallback encoding
    fallback = ui.config('ui', 'fallbackencoding')
    if fallback:
        _fallbackencoding = fallback

    fullargs = args
    cmd, func, args, options, cmdoptions = dispatch._parse(ui, args)

    if options["encoding"]:
        _encoding = options["encoding"]
    if options["encodingmode"]:
        _encodingmode = options["encodingmode"]
    if options['verbose'] or options['debug'] or options['quiet']:
        ui.setconfig('ui', 'verbose', str(bool(options['verbose'])))
        ui.setconfig('ui', 'debug', str(bool(options['debug'])))
        ui.setconfig('ui', 'quiet', str(bool(options['quiet'])))
    if options['traceback']:
        ui.setconfig('ui', 'traceback', 'on')
    if options['noninteractive']:
        ui.setconfig('ui', 'interactive', 'off')

    if options['help']:
        return commands.help_(ui, cmd, options['version'])
    elif options['version']:
        return commands.version_(ui)
    elif not cmd:
        return commands.help_(ui, 'shortlist')

    repo = None
    if cmd not in commands.norepo.split():
        try:
            repo = hg.repository(ui, path=path)
            repo.ui = ui
            ui.setconfig("bundle", "mainreporoot", repo.root)
            if not repo.local():
                raise util.Abort(_("repository '%s' is not local") % path)
        except RepoError:
            if cmd not in commands.optionalrepo.split():
                if not path:
                    raise RepoError(_('There is no Mercurial repository here'
                                         ' (.hg not found)'))
                raise
        d = lambda: func(ui, repo, *args, **cmdoptions)
    else:
        d = lambda: func(ui, *args, **cmdoptions)

    # run pre-hook, and abort if it fails
    ret = hook.hook(ui, repo, "pre-%s" % cmd, False, args=" ".join(fullargs))
    if ret:
        return ret

    # Run actual command
    try:
        ret = d()
    except TypeError:
        # was this an argument error?
        tb = traceback.extract_tb(sys.exc_info()[2])
        if len(tb) != 2: # no
            raise
        raise ParseError(cmd, _('invalid arguments'))

    # run post-hook, passing command result
    hook.hook(ui, repo, "post-%s" % cmd, False, args=" ".join(fullargs),
            result = ret)

    if repo:
        shlib.update_thgstatus(repo.ui, repo.root, wait=True)

    return ret

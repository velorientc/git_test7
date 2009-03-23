import os
from mercurial import hg, cmdutil, util, ui
import thgutil
import sys
try:
    from mercurial.error import RepoError
except ImportError:
    from mercurial.repo import RepoError

try:
    from win32api import GetTickCount
    CACHE_TIMEOUT = 5000
except ImportError:
    from time import time as GetTickCount
    CACHE_TIMEOUT = 5.0

UNCHANGED = "unchanged"
ADDED = "added"
MODIFIED = "modified"
UNKNOWN = "unknown"
IGNORED = "ignored"
NOT_IN_REPO = "n/a"
ROOT = "root"

# file status cache
overlay_cache = {}
cache_tick_count = 0
cache_root = None
cache_pdir = None


def add_dirs(list):
    dirs = set()
    if list:
        dirs.add('')
    for f in list:
        pdir = os.path.dirname(f)
        if pdir in dirs:
            continue
        while pdir:
            dirs.add(pdir)
            pdir = os.path.dirname(pdir)
    list.extend(dirs)


def get_state(upath, repo=None):
    """
    Get the state of a given path in source control.
    """
    return get_states(upath, repo)[-1]


def get_states(upath, repo=None):
    """
    Get the states of a given path in source control.
    """
    global overlay_cache, cache_tick_count
    global cache_root, cache_pdir

    #print "called: _get_state(%s)" % path
    tc = GetTickCount()

    try:
        # handle some Asian charsets
        path = upath.encode('mbcs')
    except:
        path = upath
     # check if path is cached
    pdir = os.path.dirname(path)
    if cache_pdir == pdir and overlay_cache:
        if tc - cache_tick_count < CACHE_TIMEOUT:
            status = overlay_cache.get(path)
            if not status:
                if os.path.isdir(os.path.join(path, '.hg')):
                    add(path, ROOT)
                    status = ROOT,
                else:
                    status = overlay_cache.get(pdir, [NOT_IN_REPO])
            print "%s: %s (cached)" % (path, status)
            return status
        else:
            print "Timed out!! ",
            overlay_cache.clear()
            cache_tick_count = GetTickCount()
     # path is a drive
    if path.endswith(":\\"):
        add(path, NOT_IN_REPO)
        return [NOT_IN_REPO]
     # open repo
    if cache_pdir == pdir:
        root = cache_root
    else:
        print "find new root ",
        root = thgutil.find_root(path)
        if root == path:
            add(path, ROOT)
            return [ROOT]
        cache_root = root
        cache_pdir = pdir

    print "_get_state: root = ", root
    if root is None:
        print "_get_state: not in repo"
        overlay_cache = {None: None}
        cache_tick_count = GetTickCount()
        return [NOT_IN_REPO]
    hgdir = os.path.join(root, '.hg', '')
    if pdir == hgdir[:-1] or pdir.startswith(hgdir):
        add(pdir, NOT_IN_REPO)
        return [NOT_IN_REPO]
    try:
        tc1 = GetTickCount()
        if not repo or (repo.root != root and repo.root != os.path.realpath(root)):
            repo = hg.repository(ui.ui(), path=root)
            print "hg.repository() took %g ticks" % (GetTickCount() - tc1)
        # check if to display overlay icons in this repo
        overlayopt = repo.ui.config('tortoisehg', 'overlayicons', ' ').lower()
        print "%s: repo overlayicons = " % path, overlayopt
        if overlayopt == 'localdisk':
            overlayopt = bool(thgutil.netdrive_status(path))
        if not overlayopt or overlayopt in 'false off no'.split():
            print "%s: overlayicons disabled" % path
            overlay_cache = {None: None}
            cache_tick_count = GetTickCount()
            return [NOT_IN_REPO]
    except RepoError:
        # We aren't in a working tree
        print "%s: not in repo" % pdir
        add(pdir, IGNORED)
        return [IGNORED]
    except StandardError, e:
        print "error while handling %s:" % pdir
        print e
        add(pdir, UNKNOWN)
        return [UNKNOWN]
     # get file status
    tc1 = GetTickCount()

    try:
        matcher = cmdutil.match(repo, [pdir])
        repostate = repo.status(match=matcher, ignored=True,
                        clean=True, unknown=True)
    except util.Abort, inst:
        print "abort: %s" % inst
        print "treat as unknown : %s" % path
        return [UNKNOWN]

    print "status() took %g ticks" % (GetTickCount() - tc1)
    modified, added, removed, deleted, unknown, ignored, clean = repostate
    # cached file info
    tc = GetTickCount()
    overlay_cache = {}
    for grp, st in (
            (ignored, IGNORED),
            (unknown, UNKNOWN),
            (clean, UNCHANGED),
            (added, ADDED),
            (removed, MODIFIED),
            (deleted, MODIFIED),
            (modified, MODIFIED)):
        add_dirs(grp)
        for f in grp:
            fpath = os.path.join(root, os.path.normpath(f))
            add(fpath, st)
    add(root, ROOT)
    status = overlay_cache.get(path, [UNKNOWN])
    print "\n%s: %s" % (path, status)
    cache_tick_count = GetTickCount()
    return status


def add(path, state):
    c = overlay_cache.setdefault(path, [])
    c.append(state)

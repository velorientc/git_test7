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

# file status cache
overlay_cache = {}
cache_tick_count = 0
cache_root = None
cache_pdir = None


def add_dirs(list):
    dirs = set()
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
            status = overlay_cache.get(path, NOT_IN_REPO)
            print "%s: %s (cached)" % (path, status)
            return status
        else:
            print "Timed out!!"
            overlay_cache.clear()
     # path is a drive
    if path.endswith(":\\"):
        overlay_cache[path] = UNKNOWN
        return NOT_IN_REPO
     # open repo
    if cache_pdir == pdir:
        root = cache_root
    else:
        print "find new root"
        cache_pdir = pdir
        cache_root = root = thgutil.find_root(pdir)
    print "_get_state: root = ", root
    if root is None:
        print "_get_state: not in repo"
        overlay_cache = {None: None}
        cache_tick_count = GetTickCount()
        return NOT_IN_REPO
    try:
        tc1 = GetTickCount()
        if not repo or repo.root == cache_root:
            repo = hg.repository(ui.ui(), path=root)
        print "hg.repository() took %d ticks" % (GetTickCount() - tc1)
        # check if to display overlay icons in this repo
        global_opts = ui.ui().configlist('tortoisehg', 'overlayicons', [])
        repo_opts = repo.ui.configlist('tortoisehg', 'overlayicons', [])

        print "%s: global overlayicons = " % path, global_opts
        print "%s: repo overlayicons = " % path, repo_opts
        is_netdrive = thgutil.netdrive_status(path) is not None
        if (is_netdrive and 'localdisks' in global_opts) \
                or 'False' in repo_opts:
            print "%s: overlayicons disabled" % path
            overlay_cache = {None: None}
            cache_tick_count = GetTickCount()
            return NOT_IN_REPO
    except RepoError:
        # We aren't in a working tree
        print "%s: not in repo" % pdir
        overlay_cache[path] = UNKNOWN
        return NOT_IN_REPO
     # get file status
    tc1 = GetTickCount()

    try:
        matcher = cmdutil.match(repo, [pdir])
        repostate = repo.status(match=matcher, ignored=True,
                        clean=True, unknown=True)
        # add directory status to list
        for grp in repostate:
            add_dirs(grp)
    except util.Abort, inst:
        print "abort: %s" % inst
        print "treat as unknown : %s" % path
        return UNKNOWN

    print "status() took %d ticks" % (GetTickCount() - tc1)
    print repostate###
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
        for f in grp:
            fpath = os.path.join(repo.root, os.path.normpath(f))
            overlay_cache[fpath] = st
    if path in overlay_cache:
        status = overlay_cache[path]
    else:
        status = overlay_cache[path] = UNKNOWN
    print "%s: %s" % (path, status)
    cache_tick_count = GetTickCount()
    return status

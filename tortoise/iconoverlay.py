# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

import os
import win32api
import win32con
from win32com.shell import shell, shellcon
import _winreg
from mercurial import hg, repo, ui, cmdutil, util
import thgutil
import sys

# file/directory status
UNCHANGED = "unchanged"
ADDED = "added"
MODIFIED = "modified"
UNKNOWN = "unknown"
NOT_IN_TREE = "not in tree"
NO_DIRSTATE = "dirstate not found"
CONTROL_FILE = "control file"

# file status cache
CACHE_TIMEOUT = 3000
CACHE_SIZE = 400
overlay_cache = {}

# some misc constants
S_OK = 0
S_FALSE = 1

def subdirs(p):
    oldp = ""
    if os.path.isdir(p):    
        yield p
    while 1:
        oldp = p
        p = os.path.dirname(p)
        if p == oldp:
            return
        yield p

def get_cache_list(path, size):
    """"
    get a sorted list (of size 'size') of file/folders which reside in  
    the same directory as 'path' and windowed around 'path' on the list. 
    The .hg directory will be ignore. Other directories will also be 
    ignored unless path is a directory itself.
    """
    pathdir = os.path.dirname(path)
    dlist = [x for x in os.listdir(pathdir) if x <> ".hg"]
    if not os.path.isdir(path):
        dlist = [x for x in dlist if not os.path.isdir(x)]
    dlist.sort()
    try:
        idx = dlist.index(os.path.basename(path))
    except:
        idx = 0
    begin = max(0, idx - size/2)
    end = idx + size/2
    cache_list = dlist[begin : end]
    cache_list = [os.path.join(pathdir, x) for x in cache_list]
    return cache_list

def get_dirs(list):
    return set([os.path.dirname(p) for p in list])
    
def add_dirs(list):
    dirs = set()
    for f in list:
        dir = os.path.dirname(f)
        if dir in dirs:
           continue
        while dir:
            dirs.add(dir)
            dir = os.path.dirname(dir)
    list.extend(dirs)

class IconOverlayExtension(object):
    """
    Class to implement icon overlays for source controlled files.

    Displays a different icon based on version control status.

    NOTE: The system allocates only 15 slots in _total_ for all
        icon overlays; we (will) use 6, tortoisecvs uses 7... not a good
        recipe for a happy system.
    """
    
    counter = 0

    _com_interfaces_ = [shell.IID_IShellIconOverlayIdentifier]
    _public_methods_ = [
        "GetOverlayInfo", "GetPriority", "IsMemberOf"
        ]

    def GetOverlayInfo(self): 
        icon = thgutil.get_icon_path("status", self.icon)
        print "icon = ", icon

        if icon:
            return (icon, 0, shellcon.ISIOI_ICONFILE)
        else:
            return ("", 0, 0) 

    def GetPriority(self):
        return 0

    def _get_installed_overlays():
        key = win32api.RegOpenKeyEx(win32con.HKEY_LOCAL_MACHINE,
                                    "Software\\Microsoft\\Windows\\" +
                                        "CurrentVersion\\Explorer\\" +
                                        "ShellIconOverlayIdentifiers",
                                    0,
                                    win32con.KEY_READ)
        keys = win32api.RegEnumKeyEx(key)
        handlercount = len(keys)
        print "number of overlay handlers installed = %d" % handlercount
        for i, k in enumerate(keys):
            print i, k
        win32api.RegCloseKey(key)
        return handlercount
        
    def _get_state(self, path):
        """
        Get the state of a given path in source control.
        """
        global overlay_cache
        #print "called: _get_state(%s)" % path
        tc = win32api.GetTickCount()
        
        # check if path is cached
        if overlay_cache.has_key(path):
            if tc - overlay_cache[path]['ticks'] < CACHE_TIMEOUT:
                print "%s: %s (cached)" % (path, overlay_cache[path]['status'])
                return overlay_cache[path]['status']

        if os.path.basename(path) == ".hg":
            print "%s: skip directory" % path
            overlay_cache[path] = {'ticks': tc, 'status': UNKNOWN}
            return NOT_IN_TREE      # ignore .hg directories (for efficiency)

        # open repo
        root = thgutil.find_root(path)
        #print "_get_state: root = ", root
        if root is None:
            #print "_get_state: not in repo"
            overlay_cache[path] = {'ticks': tc, 'status': UNKNOWN}
            return NOT_IN_TREE

        # skip root direcory to improve speed
        if root == path:
            #print "_get_state: skip repo root"
            overlay_cache[path] = {'ticks': tc, 'status': UNKNOWN}
            return NOT_IN_TREE
            
        # can't get correct status without dirstate
        if not os.path.exists(os.path.join(root, ".hg", "dirstate")):
            #print "_get_state: dirstate not found"
            return NO_DIRSTATE
            
        try:
            repo = hg.repository(ui.ui(), path=root)
        except repo.RepoError:
            # We aren't in a working tree
            print "%s: not in repo" % dir
            overlay_cache[path] = {'ticks': tc, 'status': UNKNOWN}
            return NOT_IN_TREE

        # get file status
        tc1 = win32api.GetTickCount()
        cache_list = get_cache_list(path, CACHE_SIZE)
        #print "cache_list: ", "\n".join(cache_list)
        
        dirstate_list = [ os.path.normpath(os.path.join(root, x[0])) 
                          for x in repo.dirstate._map.items() ]
        ndirs = []
        for d in get_dirs(dirstate_list):
            ndirs.extend(subdirs(d))
        dirstate_list.extend(set(ndirs))
        #print "dirstate_list: ", "\n".join(dirstate_list)
        
        tracked_list = [ x for x in cache_list if x in dirstate_list ]
        #print "tracked_list: ", "\n".join(tracked_list)

        modified, added, removed, deleted = [], [], [], []
        unknown, ignored, clean = [], [], []
        files = []
        if tracked_list:
            try:
                files, matchfn, anypats = cmdutil.matchpats(repo, tracked_list)
                modified, added, removed, deleted, unknown, ignored, clean = [
                        n for n in repo.status(files=files, list_clean=True)]

                # add directory status to list
                add_dirs(clean)
                add_dirs(modified)
                add_dirs(added)
                add_dirs(removed)
                add_dirs(deleted)
            except util.Abort, inst:
                print "abort: %s" % inst
                print "treat as unknown : %s" % path
                return UNKNOWN
            
            print "status() took %d ticks" % (win32api.GetTickCount() - tc1)
                
        # cached file info
        tc = win32api.GetTickCount()
        overlay_cache = {}
        for f in files:
            if f in modified:
                status = MODIFIED
            elif f in added:
                status = ADDED
            elif f in clean:
                status = UNCHANGED
            else:
                status = UNKNOWN
            fpath = os.path.join(repo.root, os.path.normpath(f))
            overlay_cache[fpath] = {'ticks': tc, 'status': status}
            #print "cache:", fpath, status
        
        for f in cache_list:
            if not f in overlay_cache:
                overlay_cache[f] = {'ticks': tc, 'status': UNKNOWN}

        if overlay_cache.has_key(path):
            status = overlay_cache[path]['status']
        else:
            status = UNKNOWN
        print "%s: %s" % (path, status)
        return status

    def IsMemberOf(self, path, attrib):
        if self._get_state(path) == self.state:
            return S_OK
        return S_FALSE

def make_icon_overlay(name, icon, state, clsid):
    """
    Make an icon overlay COM class.

    Used to create different COM server classes for highlighting the
    files with different source controlled states (eg: unchanged, 
    modified, ...).
    """
    classname = "%sOverlay" % name
    prog_id = "Mercurial.ShellExtension.%s" % classname
    desc = "Merucurial icon overlay shell extension for %s files" % name.lower()
    reg = [
        (_winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\%s" % name) ]
    cls = type(
            classname,
            (IconOverlayExtension, ),
            dict(_reg_clsid_=clsid, _reg_progid_=prog_id, _reg_desc_=desc, registry_keys=reg, icon=icon, state=state))

    _overlay_classes.append(cls)
    # We need to register the class as global, as pythoncom will
    # create an instance of it.
    globals()[classname] = cls

_overlay_classes = []
make_icon_overlay("Changed", "changed.ico", MODIFIED, "{102C6A24-5F38-4186-B64A-237011809FAB}")
make_icon_overlay("Unchanged", "unchanged.ico", UNCHANGED, "{00FEE959-5773-424B-88AC-A01BFC8E4555}")
make_icon_overlay("Added", "added.ico", ADDED, "{8447DB75-5875-4BA8-9F38-A727DAA484A0}")

def get_overlay_classes():
    """
    Get a list of all registerable icon overlay classes
    """
    return _overlay_classes

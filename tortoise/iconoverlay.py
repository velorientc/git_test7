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

UNCHANGED = "unchanged"
ADDED = "added"
MODIFIED = "modified"
UNKNOWN = "unknown"
NOT_IN_TREE = "not in tree"
CONTROL_FILE = "control file"

CACHE_TIMEOUT = 3000
CACHE_SIZE = 400
overlay_cache = {}

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
        import win32api

        # only support Overlays In Explorer
        print "GetOverlayInfo: checking if in explorer"
        modname = win32api.GetModuleFileName(win32api.GetModuleHandle(None))
        print "modname = %s" % modname
        if not modname.lower().endswith("\\explorer.exe"):
            print "GetOverlayInfo: not in explorer"
            return ("", 0, 0) 
 
        icon = os.path.join(os.path.dirname(__file__), "..", "icons",
                            "status", self.icon)
        return (icon, 0, shellcon.ISIOI_ICONFILE)

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
        print "called: _get_state(%s)" % path
        
        # debugging
        if IconOverlayExtension.counter > 10000:
            IconOverlayExtension.counter = 0
        else:
            IconOverlayExtension.counter += 1
        print "counter = %d" % IconOverlayExtension.counter
        
        if 0 and os.path.isdir(path):
            print "%s: skip directory" % path
            return NOT_IN_TREE      # ignore directories (for efficiency)

        # check if path is cached
        tc = win32api.GetTickCount()
        if overlay_cache.has_key(path):
            if tc - overlay_cache[path]['ticks'] < CACHE_TIMEOUT:
                print "%s: %s (cached)" % (path, overlay_cache[path]['status'])
                return overlay_cache[path]['status']

        # open repo
        root = thgutil.find_root(path)
        print "_get_state: root = ", root
        if root is None:
            print "_get_state: not in repo"
            return NOT_IN_TREE

        # skip root direcory to improve speed
        if root == path:
            print "_get_state: skip repo root"
            return NOT_IN_TREE

        u = ui.ui()
        try:
            repo = hg.repository(u, path=root)
        except repo.RepoError:
            # We aren't in a working tree
            print "%s: not in repo" % dir
            return NOT_IN_TREE

        # get file status
        tc1 = win32api.GetTickCount()
        cache_list = get_cache_list(path, CACHE_SIZE)
        #print "cache_list: ", "\n".join(cache_list)
        try:
            files, matchfn, anypats = cmdutil.matchpats(repo, cache_list)
            modified, added, removed, deleted, unknown, ignored, clean = [
                    n for n in repo.status(files=files, list_clean=True)]
        except util.Abort, inst:
            print "abort: %s" % inst
            print "treat as unknown : %s" % path
            return UNKNOWN
        print "status() took %d ticks" % (win32api.GetTickCount() - tc1)
        
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

        # add directory status to list
        add_dirs(clean)
        add_dirs(modified)
        add_dirs(added)
        add_dirs(removed)
        add_dirs(deleted)
        
        # cached file info
        tc = win32api.GetTickCount()
        overlay_cache = {}
        for f in files:
            if f in added:
                status = ADDED
            elif f in modified:
                status = MODIFIED
            elif f in clean:
                status = UNCHANGED
            else:
                status = UNKNOWN
            fpath = os.path.join(repo.root, os.path.normpath(f))
            overlay_cache[fpath] = {'ticks': tc, 'status': status}
            #print "cache:", fpath, status

        if overlay_cache.has_key(path):
            status = overlay_cache[path]['status']
        else:
            status = UNKNOWN
        print "%s: %s" % (path, status)
        return status

    def IsMemberOf(self, path, attrib):
        S_OK = 0
        S_FALSE = 1
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

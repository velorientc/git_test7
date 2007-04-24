# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>

import os.path
import win32api
from win32com.shell import shell, shellcon
import _winreg

UNCHANGED = "unchanged"
ADDED = "added"
MODIFIED = "modified"
UNKNOWN = "unknown"
NOT_IN_TREE = "not in tree"
CONTROL_FILE = "control file"

CACHE_TIMEOUT = 1000

class IconOverlayExtension(object):
    """
    Class to implement icon overlays for source controlled files.

    Displays a different icon based on version control status.

    NOTE: The system allocates only 15 slots in _total_ for all
        icon overlays; we (will) use 6, tortoisecvs uses 7... not a good
        recipe for a happy system.
    """
    
    counter = 0
    last_path = ""
    last_status = UNKNOWN
    last_tick = 0
    
    _com_interfaces_ = [shell.IID_IShellIconOverlayIdentifier]
    _public_methods_ = [
        "GetOverlayInfo", "GetPriority", "IsMemberOf"
        ]

    def GetOverlayInfo(self):
        icon = os.path.join(os.path.dirname(__file__), "..", "icons", "status", self.icon)
        return (icon, 0, shellcon.ISIOI_ICONFILE)

    def GetPriority(self):
        return 0

    def _get_state(self, path):
        """
        Get the state of a given path in source control.
        """
        
        print "called: __get_state__(%s)" % path
        
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
        elapsed = tc - IconOverlayExtension.last_tick
        if IconOverlayExtension.last_path == path and elapsed < CACHE_TIMEOUT:
            return IconOverlayExtension.last_status

        from mercurial import hg, repo, ui, cmdutil

        # open repo
        u = ui.ui()
        if os.path.isdir(path):
            dir, filename = path, ''
        else:
            dir, filename = os.path.split(path)

        os.chdir(dir)
        try:
            repo = hg.repository(u, path='')
        except repo.RepoError:
            # We aren't in a working tree
            print "%s: not in repo" % dir
            # cached path and status
            IconOverlayExtension.last_status = NOT_IN_TREE
            IconOverlayExtension.last_path = path
            IconOverlayExtension.last_tick = tc
            return NOT_IN_TREE

        # get file status
        files, matchfn, anypats = cmdutil.matchpats(repo, [filename])
        modified, added, removed, deleted, unknown, ignored, clean = [
                n for n in repo.status(files=files, list_clean=True)]

        if added:
            status = ADDED
        elif modified:
            status = MODIFIED
        elif clean:
            status = UNCHANGED
        else:
            status = UNKNOWN

        # cached file info
        IconOverlayExtension.last_status = status
        IconOverlayExtension.last_path = path
        IconOverlayExtension.last_tick = tc

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
    prog_id = "Bazaar.ShellExtension.%s" % classname
    desc = "Bazaar icon overlay shell extension for %s files" % name.lower()
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
make_icon_overlay("Unchanged", "unchanged.ico", UNCHANGED, "{00FEE959-5773-424B-88AC-A01BFC8E4555}")
make_icon_overlay("Added", "added.ico", ADDED, "{8447DB75-5875-4BA8-9F38-A727DAA484A0}")
make_icon_overlay("Changed", "changed.ico", MODIFIED, "{102C6A24-5F38-4186-B64A-237011809FAB}")
make_icon_overlay("Unknown", "unknown.ico", UNKNOWN, "{A8AFEA16-5F0C-4BE2-A64B-80C41C50D911}")

def get_overlay_classes():
    """
    Get a list of all registerable icon overlay classes
    """
    return _overlay_classes

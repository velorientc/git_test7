# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

import os
import win32api
import win32con
from win32com.shell import shell, shellcon
import _winreg
from mercurial import hg, cmdutil, util
import thgutil
import sys
import threading
import cachethg
from cachethg import debugf

try:
    from mercurial.error import RepoError
except ImportError:
    from mercurial.repo import RepoError

cache_lock = threading.Semaphore()

# some misc constants
S_OK = 0
S_FALSE = 1


class IconOverlayExtension(object):
    """
    Class to implement icon overlays for source controlled files.
    Specialized classes are created for each overlay icon.

    Displays a different icon based on version control status.

    NOTE: The system allocates only 15 slots in _total_ for all
        icon overlays; we (will) use 6, tortoisecvs uses 7... not a good
        recipe for a happy system. By utilizing the TortoiseOverlay.dll
        we can share overlay slots with the other tortoises.
    """
    
    counter = 0

    _com_interfaces_ = [shell.IID_IShellIconOverlayIdentifier]
    _public_methods_ = [
        "GetOverlayInfo", "GetPriority", "IsMemberOf"
        ]
    _reg_threading_ = 'Apartment'

    def GetOverlayInfo(self): 
        return ("", 0, 0) 

    def GetPriority(self):
        return 0
        
    def IsMemberOf(self, path, attrib):                  
        global cache_lock
        try:
            cache_lock.acquire()
            tc = win32api.GetTickCount()
            if cachethg.get_state(path) in self.state:
                return S_OK
            return S_FALSE
        finally:
            cache_lock.release()
            debugf("IsMemberOf(%s): _get_state() took %d ticks",
                    (self.state, win32api.GetTickCount() - tc))
            
def make_icon_overlay(name, icon_type, state, clsid):
    """
    Make an icon overlay COM class.

    Used to create different COM server classes for highlighting the
    files with different source controlled states (eg: unchanged, 
    modified, ...).
    """
    classname = "%sOverlay" % name
    prog_id = "Mercurial.ShellExtension.%s" % classname
    desc = "Mercurial icon overlay shell extension for %s files" % name.lower()
    reg = [
            (_winreg.HKEY_LOCAL_MACHINE,
             r"Software\TortoiseOverlays\%s" % icon_type,
             [("TortoiseHg", clsid)])
        ]
    cls = type(
            classname,
            (IconOverlayExtension, ),
            dict(_reg_clsid_=clsid, _reg_progid_=prog_id, _reg_desc_=desc, registry_keys=reg, stringKey="HG", state=state))

    _overlay_classes.append(cls)
    # We need to register the class as global, as pythoncom will
    # create an instance of it.
    globals()[classname] = cls

_overlay_classes = []
modified = cachethg.REMOVED + cachethg.DELETED + cachethg.MODIFIED

make_icon_overlay("Changed", "Modified", modified, "{4D0F33E1-654C-4A1B-9BE8-E47A98752BAB}")
make_icon_overlay("Unchanged", "Normal", cachethg.UNCHANGED, "{4D0F33E2-654C-4A1B-9BE8-E47A98752BAB}")
make_icon_overlay("Added", "Added", cachethg.ADDED, "{4D0F33E3-654C-4A1B-9BE8-E47A98752BAB}")
make_icon_overlay("Ignored", "Ignored", cachethg.IGNORED, "{4D0F33E4-654C-4A1B-9BE8-E47A98752BAB}")
make_icon_overlay("Conflict", "Conflict", cachethg.UNRESOLVED, "{4D0F33E5-654C-4A1B-9BE8-E47A98752BAB}")

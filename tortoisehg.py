#
# Simple TortoiseSVN-like Mercurial plugin for the Windows Shell
# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Jelmer Vernooij <jelmer@samba.org>
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import sys
if hasattr(sys, "frozen") and sys.frozen == 'dll':
    import win32traceutil

# shell extension classes
from tortoise.contextmenu import ContextMenuExtension
from tortoise.iconoverlay import ChangedOverlay, AddedOverlay, UnchangedOverlay

# for COM registration via py2exe
def DllRegisterServer():
    RegisterServer(ContextMenuExtension)
    RegisterServer(ChangedOverlay)
    RegisterServer(AddedOverlay)
    RegisterServer(UnchangedOverlay)

# for COM registration via py2exe
def DllUnregisterServer():
    UnregisterServer(ContextMenuExtension)
    UnregisterServer(ChangedOverlay)
    UnregisterServer(AddedOverlay)
    UnregisterServer(UnchangedOverlay)

def RegisterServer(cls):
    import _winreg
    import os.path

    # Add mercurial to the library path
    try:
        import mercurial
    except ImportError:
        from win32com.server import register
        register.UnregisterClasses(cls)
        raise "Error: Failed to find mercurial module!"

    hg_path = os.path.dirname(os.path.dirname(mercurial.__file__))
    try:
        key = "CLSID\\%s\\PythonCOMPath" % cls._reg_clsid_
        path = _winreg.QueryValue(_winreg.HKEY_CLASSES_ROOT, key)
        _winreg.SetValue(_winreg.HKEY_CLASSES_ROOT, key, _winreg.REG_SZ, "%s;%s" % (path, hg_path))
    except:
        pass
        
    # Add the appropriate shell extension registry keys
    for category, keyname in cls.registry_keys: 
        _winreg.SetValue(category, keyname, _winreg.REG_SZ, cls._reg_clsid_)

    print cls._reg_desc_, "registration complete."

def UnregisterServer(cls):
    import _winreg
    for category, keyname in cls.registry_keys:
        try:
            _winreg.DeleteKey(category, keyname)
        except WindowsError, details:
            import errno
            if details.errno != errno.ENOENT:
                raise
    print cls._reg_desc_, "unregistration complete."

if __name__=='__main__':
    from win32com.server import register
    register.UseCommandLine(ContextMenuExtension,
            finalize_register = lambda: RegisterServer(ContextMenuExtension),
            finalize_unregister = lambda: UnregisterServer(ContextMenuExtension))
    
    for cls in (ChangedOverlay, AddedOverlay, UnchangedOverlay):
        register.UseCommandLine(cls,
                finalize_register = lambda: RegisterServer(cls),
                finalize_unregister = lambda: UnregisterServer(cls))

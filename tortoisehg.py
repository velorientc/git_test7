#
# Simple TortoiseSVN-like Mercurial plugin for the Windows Shell
# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Jelmer Vernooij <jelmer@samba.org>
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import pythoncom
from mercurial import demandimport
demandimport.ignore.append('win32traceutil')
demandimport.enable()

import os
import sys
import _winreg

if hasattr(sys, "frozen") and sys.frozen == 'dll':
    import win32traceutil

# shell extension classes
from tortoise.contextmenu import ContextMenuExtension
import tortoise.iconoverlay

overlays = [getattr(tortoise.iconoverlay, overlay) for overlay in
            tortoise.iconoverlay.__dict__ if overlay.endswith('Overlay')]

bin_path = os.path.dirname(os.path.join(os.getcwd(), sys.argv[0]))
print "bin path = ", bin_path

def check_tortoise_overlays():
    # TortoiseOverlays must be installed, and we must be able to write there.
    try:
        hkey = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,
                               r"Software\TortoiseOverlays", 0,
                               _winreg.KEY_ALL_ACCESS)
    except WindowsError:
        print "TortoiseOverlays is not installed."
        sys.exit(1)

# TortoiseHg registry setup
def register_tortoise_path(unregister=False):
    key = r"Software\TortoiseHg"
    cat = _winreg.HKEY_LOCAL_MACHINE
    if (unregister):
        try:
            _winreg.DeleteKey(cat, key)
            print "TortoiseHg unregistered"
        except WindowsError:
            print 'TortoiseHg was not registered'
    else:
        _winreg.SetValue(cat, key, _winreg.REG_SZ, bin_path)
        print "TortoiseHg registered"

# for COM registration via py2exe
def DllRegisterServer():
    check_tortoise_overlays()
    RegisterServer(ContextMenuExtension)
    for overlay in overlays:
        RegisterServer(overlay)
    register_tortoise_path()

# for COM registration via py2exe
def DllUnregisterServer():
    UnregisterServer(ContextMenuExtension)
    for for overlay in overlays:
        UnregisterServer(overlay)
    register_tortoise_path(unregister=True)

def RegisterServer(cls):
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
    for category, keyname, values in cls.registry_keys:
        hkey = _winreg.CreateKey(category, keyname)
        for (name, val) in values:
            # todo: handle ints?
            _winreg.SetValueEx(hkey, name, 0, _winreg.REG_SZ, val)
        
    # register the extension on Approved list
    try:
        apath = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved'
        key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, apath, 0, _winreg.KEY_WRITE)
        _winreg.SetValueEx(key, cls._reg_clsid_, 0, _winreg.REG_SZ, 'TortoiseHg')
    except:
        pass

    print cls._reg_desc_, "registration complete."

def UnregisterServer(cls):
    for category, keyname, values in cls.registry_keys:
        hkey = _winreg.OpenKey(category, keyname, 0, _winreg.KEY_ALL_ACCESS)
        for (name, val) in values:
            # todo: handle ints?
            try:
                _winreg.DeleteValue(hkey, name)
            except WindowsError, exc:
                print "Failed to remove registry key %s: %s" % (keyname, exc)

    # unregister the extension from Approved list
    try:
        apath = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved'
        key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, apath, 0, _winreg.KEY_WRITE)
        _winreg.DeleteValue(key, cls._reg_clsid_)
    except:
        pass

    print cls._reg_desc_, "unregistration complete."

if __name__=='__main__':
    check_tortoise_overlays()

    from win32com.server import register
    register.UseCommandLine(ContextMenuExtension,
            finalize_register = lambda: RegisterServer(ContextMenuExtension),
            finalize_unregister = lambda: UnregisterServer(ContextMenuExtension))
    
    for cls in (ChangedOverlay, AddedOverlay, UnchangedOverlay):
        register.UseCommandLine(cls,
                finalize_register = lambda: RegisterServer(cls),
                finalize_unregister = lambda: UnregisterServer(cls))

    if "--unregister" in sys.argv[1:]:
        register_tortoise_path(unregister=True)
    else:
        register_tortoise_path()

    

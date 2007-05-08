# Simple TortoiseSVN-like Mercurial plugin for the Windows Shell
# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Jelmer Vernooij <jelmer@samba.org>
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

import os.path
import _winreg


def DllRegisterServer(cls):
    import _winreg

    # Add mercurial to the library path
    try:
        import mercurial
    except ImportError:
        import sys
        from win32com.server import register
        register.UnregisterClasses(cls)
        sys.exit("Error: Failed to find mercurial module! Include the path to mercurial in PYTHONPATH environment variable while registering component.")
    hg_path = os.path.dirname(os.path.dirname(mercurial.__file__))
    key = "CLSID\\%s\\PythonCOMPath" % cls._reg_clsid_
    path = _winreg.QueryValue(_winreg.HKEY_CLASSES_ROOT, key)
    _winreg.SetValue(_winreg.HKEY_CLASSES_ROOT, key, _winreg.REG_SZ, "%s;%s" % (path, hg_path))

    # Add the appropriate shell extension registry keys
    for category, keyname in cls.registry_keys: 
        _winreg.SetValue(category, keyname, _winreg.REG_SZ, cls._reg_clsid_)

    print cls._reg_desc_, "registration complete."

def DllUnregisterServer(cls):
    import _winreg
    for category, keyname in cls.registry_keys:
        try:
            _winreg.DeleteKey(category, keyname)
        except WindowsError, details:
            import errno
            if details.errno != errno.ENOENT:
                raise
    print cls._reg_desc_, "unregistration complete."

if __name__ == '__main__':
    from win32com.server import register
    from tortoise.contextmenu import ContextMenuExtension
    import tortoise.iconoverlay
    
    register.UseCommandLine(ContextMenuExtension,
                   finalize_register = lambda: DllRegisterServer(ContextMenuExtension),
                   finalize_unregister = lambda: DllUnregisterServer(ContextMenuExtension))

    # Register all of the icon overlay extensions
    for icon_class in tortoise.iconoverlay.get_overlay_classes():
        register.UseCommandLine(icon_class,
                       finalize_register = lambda: DllRegisterServer(icon_class),
                       finalize_unregister = lambda: DllUnregisterServer(icon_class))

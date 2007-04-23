# Simple TortoiseSVN-like Bazaar plugin for the Windows Shell
# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Jelmer Vernooij <jelmer@samba.org>
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>

import os.path
import _winreg


def DllRegisterServer(cls):
    import _winreg

    # Add bzrlib to the library path
    try:
        import bzrlib
    except ImportError:
        import sys
        from win32com.server import register
        register.UnregisterClasses(cls)
        sys.exit("Error: Failed to find bzrlib module! Include the path to bzrlib in PYTHONPATH environment variable while registering component.")
    bzr_path = os.path.dirname(os.path.dirname(bzrlib.__file__))
    key = "CLSID\\%s\\PythonCOMPath" % cls._reg_clsid_
    path = _winreg.QueryValue(_winreg.HKEY_CLASSES_ROOT, key)
    _winreg.SetValue(_winreg.HKEY_CLASSES_ROOT, key, _winreg.REG_SZ, "%s;%s" % (path, bzr_path))

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
    register.UseCommandLine(ContextMenuExtension,
                   finalize_register = lambda: DllRegisterServer(ContextMenuExtension),
                   finalize_unregister = lambda: DllUnregisterServer(ContextMenuExtension))

    # Register all of the icon overlay extensions
    import tortoise.iconoverlay
    for icon_class in tortoise.iconoverlay.get_overlay_classes():
        register.UseCommandLine(icon_class,
                       finalize_register = lambda: DllRegisterServer(icon_class),
                       finalize_unregister = lambda: DllUnregisterServer(icon_class))

"""
shlib.py - TortoiseHg shell utilities
 Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.

"""

import os

def set_tortoise_icon(window, icon):
    '''Find a tortoise icon, apply to PyGtk window'''
    # The context menu should set this variable
    var = os.environ.get('THG_ICON_PATH', None)
    paths = var and [ var ] or []
    try:
        # Else try relative paths from hggtk, the repository layout
        dir = os.path.dirname(__file__)
        paths.append(os.path.join(dir, '..', 'icons'))
        # ... or the source installer layout
        paths.append(os.path.join(dir, '..', '..', '..',
            'share', 'tortoisehg', 'icons'))
    except NameError: # __file__ is not always available
        pass
    for p in paths:
        path = os.path.join(p, 'tortoise', icon)
        if os.path.isfile(path):
            window.set_icon_from_file(path)
            return
    else:
        print 'icon not found', icon
        return None

if os.name == 'nt':
    from win32com.shell import shell, shellcon
    def shell_notify(paths):
        for path in paths:
            abspath = os.path.abspath(path)
            pidl, ignore = shell.SHILCreateFromPath(abspath, 0)
            #print "notify: ", shell.SHGetPathFromIDList(pidl)
            shell.SHChangeNotify(shellcon.SHCNE_UPDATEITEM, 
                                 shellcon.SHCNF_IDLIST | shellcon.SHCNF_FLUSHNOWAIT,
                                 pidl,
                                 None)
else:
    def shell_notify(paths):
        pass

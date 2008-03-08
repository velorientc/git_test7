"""
shlib.py - TortoiseHg shell utilities
 Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.

"""

import os
import shelve
import time

class Settings(dict):
    def __init__(self, key):
        self.key = key
        self.path = os.path.join(os.path.expanduser('~'), '.hgext', 'tortoisehg')
        if not os.path.exists(os.path.dirname(self.path)):
            os.makedirs(os.path.dirname(self.path))
        self.read()
        
    def read(self):
        self.clear()
        dbase = shelve.open(self.path)
        self.update(dbase.get(self.key, {}))
        dbase.close()

    def write(self):
        dbase = shelve.open(self.path)
        dbase[self.key] = dict(self)
        dbase.close()

def get_system_times():
    t = os.times()
    if t[4] == 0.0: # Windows leaves this as zero, so use time.clock()
        t = (t[0], t[1], t[2], t[3], time.clock())
    return t
    
def set_tortoise_icon(window, icon):
    window.set_icon_from_file(get_tortoise_icon(icon))

def get_tortoise_icon(icon):
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
            return path
    else:
        print 'icon not found', icon
        return None

if os.name == 'nt':
    def shell_notify(paths):
        try:
            from win32com.shell import shell, shellcon
        except ImportError:
            return
        for path in paths:
            abspath = os.path.abspath(path)
            pidl, ignore = shell.SHILCreateFromPath(abspath, 0)
            if pidl is None:
                continue
            shell.SHChangeNotify(shellcon.SHCNE_UPDATEITEM, 
                                 shellcon.SHCNF_IDLIST | shellcon.SHCNF_FLUSH,
                                 pidl,
                                 None)
else:
    def shell_notify(paths):
        pass

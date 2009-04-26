"""
shlib.py - TortoiseHg shell utilities
 Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.

"""

import dumbdbm, anydbm
anydbm._defaultmod = dumbdbm

import os
import gtk
import shelve
import time
import hgtk
import gobject
from mercurial.i18n import _

class SimpleMRUList(object):
    def __init__(self, size=10, reflist=[], compact=True):
        self._size = size
        self._list = reflist
        if compact:
            self.compact()

    def __iter__(self):
        for elem in self._list:
            yield elem

    def add(self, val):
        if val in self._list:
            self._list.remove(val)
        self._list.insert(0, val)
        self.flush()

    def get_size(self):
        return self._size

    def set_size(self, size):
        self._size = size
        self.flush()

    def flush(self):
        while len(self._list) > self._size:
            del self._list[-1]

    def compact(self):
        ''' remove duplicate in list '''
        newlist = []
        for v in self._list:
            if v not in newlist:
                newlist.append(v)
        self._list[:] = newlist


class Settings(object):
    version = 1.0

    def __init__(self, appname, path=None):
        self._appname = appname
        self._data = {}
        self._path = path and path or self._get_path(appname)
        self._audit()
        self.read()

    def get_value(self, key, default=None, create=False):
        if key in self._data:
            return self._data[key]
        elif create:
            self._data[key] = default
        return default

    def set_value(self, key, value):
        self._data[key] = value

    def mrul(self, key, size=10):
        ''' wrapper method to create a most-recently-used (MRU) list '''
        ls = self.get_value(key, [], True)
        ml = SimpleMRUList(size=size, reflist=ls)
        return ml
    
    def get_keys(self):
        return self._data.keys()

    def get_appname(self):
        return self._appname

    def read(self):
        self._data.clear()
        if not os.path.exists(self._path+'.dat'):
            return
        dbase = shelve.open(self._path)
        self._dbappname = dbase['APPNAME']
        self.version = dbase['VERSION']
        self._data.update(dbase.get('DATA', {}))
        dbase.close()

    def write(self):
        self._write(self._path, self._data)

    def _write(self, appname, data):
        dbase = shelve.open(self._get_path(appname))
        dbase['VERSION'] = Settings.version
        dbase['APPNAME'] = appname
        dbase['DATA'] = data
        try:
            dbase.close()
        except IOError:
            pass # Don't care too much about permission errors


    def _get_path(self, appname):
        if os.name == 'nt':
            return os.path.join(os.environ.get('APPDATA'), 'TortoiseHg', appname)
        else:
            return os.path.join(os.path.expanduser('~'), '.tortoisehg',
                    'settings', appname)

    def _audit(self):
        if os.path.exists(os.path.dirname(self._path)):
            return
        os.makedirs(os.path.dirname(self._path))

def get_system_times():
    t = os.times()
    if t[4] == 0.0: # Windows leaves this as zero, so use time.clock()
        t = (t[0], t[1], t[2], t[3], time.clock())
    return t
    
def set_tortoise_icon(window, thgicon):
    ico = get_tortoise_icon(thgicon)
    if ico: window.set_icon_from_file(ico)

def set_tortoise_keys(window):
    'Set default TortoiseHg keyboard accelerators'
    accelgroup = gtk.AccelGroup()
    window.add_accel_group(accelgroup)
    key, modifier = gtk.accelerator_parse('<Control>w')
    window.add_accelerator('thg-close', accelgroup, key, modifier,
            gtk.ACCEL_VISIBLE)
    key, modifier = gtk.accelerator_parse('<Control>q')
    window.add_accelerator('thg-exit', accelgroup, key, modifier,
            gtk.ACCEL_VISIBLE)
    key, modifier = gtk.accelerator_parse('F5')
    window.add_accelerator('thg-refresh', accelgroup, key, modifier,
            gtk.ACCEL_VISIBLE)
    key, modifier = gtk.accelerator_parse('<Control>Return')
    window.add_accelerator('thg-accept', accelgroup, key, modifier,
            gtk.ACCEL_VISIBLE)

    # connect ctrl-w and ctrl-q to every window
    window.connect('thg-close', thgclose)
    window.connect('thg-exit', thgexit)

def thgexit(window):
    if thgclose(window):
        gobject.idle_add(hgtk.thgexit, window)

def thgclose(window):
    if hasattr(window, 'should_live'):
        if window.should_live():
            return False
    window.destroy()
    return True

def get_tortoise_icon(thgicon):
    '''Find a tortoise icon, apply to PyGtk window'''
    # The context menu should set this variable
    var = os.environ.get('THG_ICON_PATH', None)
    paths = var and [ var ] or []
    try:
        # Else try relative paths from hggtk, the repository layout
        fdir = os.path.dirname(__file__)
        paths.append(os.path.join(fdir, '..', 'icons'))
        # ... or the unix installer layout
        paths.append(os.path.join(fdir, '..', '..', '..',
            'share', 'pixmaps', 'tortoisehg', 'icons'))
        paths.append(os.path.join(fdir, '..', '..', '..', '..',
            'share', 'pixmaps', 'tortoisehg', 'icons'))
    except NameError: # __file__ is not always available
        pass
    for p in paths:
        path = os.path.join(p, 'tortoise', thgicon)
        if os.path.isfile(path):
            return path
    else:
        print _('icon not found'), thgicon
        return None

def version():
    try:
        import __version__
        return __version__.version
    except ImportError:
        return _('unknown')

if os.name == 'nt':
    def shell_notify(paths):
        try:
            from win32com.shell import shell, shellcon
        except ImportError:
            return
        dirs = []
        for path in paths:
            abspath = os.path.abspath(path)
            if not os.path.isdir(abspath):
                abspath = os.path.dirname(abspath)
            if abspath not in dirs:
                dirs.append(abspath)
        # send notifications to deepest directories first
        dirs.sort(lambda x, y: len(y) - len(x))
        for dir in dirs:
            pidl, ignore = shell.SHILCreateFromPath(dir, 0)
            if pidl is None:
                continue
            shell.SHChangeNotify(shellcon.SHCNE_UPDATEITEM, 
                                 shellcon.SHCNF_IDLIST | shellcon.SHCNF_FLUSH,
                                 pidl, None)
else:
    def shell_notify(paths):
        pass

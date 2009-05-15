"""
shlib.py - TortoiseHg shell utilities
 Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.

"""

import os
import sys
import cPickle
import time
from mercurial.i18n import _
from mercurial import util
from mercurial import hg

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
        if os.path.exists(self._path):
            try:
                f = file(self._path, 'rb')
                self._data = cPickle.loads(f.read())
                f.close()
            except Exception:
                pass

    def write(self):
        self._write(self._path, self._data)

    def _write(self, appname, data):
        s = cPickle.dumps(data)
        f = util.atomictempfile(appname, 'wb', None)
        f.write(s)
        f.rename()

    def _get_path(self, appname):
        if os.name == 'nt':
            return os.path.join(os.environ.get('APPDATA'), 'TortoiseHg',
                    appname)
        else:
            return os.path.join(os.path.expanduser('~'), '.tortoisehg',
                    appname)

    def _audit(self):
        if os.path.exists(os.path.dirname(self._path)):
            return
        os.makedirs(os.path.dirname(self._path))

def get_system_times():
    t = os.times()
    if t[4] == 0.0: # Windows leaves this as zero, so use time.clock()
        t = (t[0], t[1], t[2], t[3], time.clock())
    return t

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
            import pywintypes
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
            try:
                pidl, ignore = shell.SHILCreateFromPath(dir, 0)
            except pywintypes.com_error:
                return
            if pidl is None:
                continue
            shell.SHChangeNotify(shellcon.SHCNE_UPDATEITEM,
                                 shellcon.SHCNF_IDLIST | shellcon.SHCNF_FLUSH,
                                 pidl, None)

    def update_thgstatus(ui, root, wait=False):
        '''Rewrite the file .hg/thgstatus

        Caches the information provided by repo.status() in the file 
        .hg/thgstatus, which can then be read by the overlay shell extension
        to display overlay icons for directories.

        The file .hg/thgstatus contains one line for each directory that has
        removed, modified or added files (in that order of preference). Each
        line consists of one char for the status of the directory (r, m or a),
        followed by the relative path of the directory in the repo. If the
        file .hg/thgstatus is empty, then the repo's working directory is
        clean.

        Specify wait=True to wait until the system clock ticks to the next
        second before accessing Mercurial's dirstate. This is useful when
        Mercurial's .hg/dirstate contains unset entries (in output of
        "hg debugstate"). unset entries happen if .hg/dirstate was updated
        within the same second as Mercurial updated the respective file in
        the working tree. This happens with a high probability for example
        when cloning a repo. The overlay shell extension will display unset
        dirstate entries as (potentially false) modified. Specifying wait=True
        ensures that there are no unset entries left in .hg/dirstate when this
        function exits.
        '''
        if wait:
            tref = time.time()
            tdelta = float(int(tref)) + 1.0 - tref
            if (tdelta > 0.0):
                time.sleep(tdelta)
        repo = hg.repository(ui, root) # a fresh repo object is needed
        repostate = repo.status() # will update .hg/dirstate as a side effect
        modified, added, removed, deleted, unknown, ignored, clean = repostate
        dirstatus = {}
        def dirname(f):
            return '/'.join(f.split('/')[:-1])
        for fn in added:
            dirstatus[dirname(fn)] = 'a'
        for fn in modified:
            dirstatus[dirname(fn)] = 'm'
        for fn in removed:
            dirstatus[dirname(fn)] = 'r'
        f = open(repo.root + "\\.hg\\thgstatus", 'wb')
        for dn in sorted(dirstatus):
            f.write(dirstatus[dn] + dn + '\n')
        f.close()

else:
    def shell_notify(paths):
        if not paths:
            return
        notify = os.environ.get('THG_NOTIFY', '.tortoisehg/notify')
        if not os.path.isabs(notify):
            notify = os.path.join(os.path.expanduser('~'), notify)
            os.environ['THG_NOTIFY'] = notify
        if not os.path.isfile(notify):
            return
        f_notify = open(notify, 'w')
        try:
            f_notify.write('\n'.join([os.path.abspath(path) for path in paths]))
        finally:
            f_notify.close()

    def update_thgstatus():
        pass


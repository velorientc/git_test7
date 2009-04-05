# setup.py
# A distutils setup script to install TortoiseHg in Windows and Posix
# environments.
#
# On Windows, this script is mostly used to build a stand-alone
# TortoiseHg package.  See installer\build.txt for details. The other
# use is to report the current version of the TortoiseHg source.


import time
import sys
import os
from distutils.core import setup

def setup_windows():
    # Specific definitios for Windows NT-alike installations
    _scripts = []
    _data_files = []
    _packages = ['hggtk', 'hggtk.vis', 'hggtk.iniparse', 'tortoise']
    extra = {}
    hgextmods = []

    # ModuleFinder can't handle runtime changes to __path__, 
    # but win32com uses them

    try:
        # if this doesn't work, try import modulefinder
        import py2exe.mf as modulefinder
        import win32com
        for p in win32com.__path__[1:]:
            modulefinder.AddPackagePath("win32com", p)
        for e in ["win32com.shell"]: #,"win32com.mapi"
            __import__(e)
            m = sys.modules[e]
            for p in m.__path__[1:]:
                modulefinder.AddPackagePath(e, p)
    except ImportError:
        # no build path setup, no worries.
        pass

    try: import py2exe
    except ImportError:
        if '--version' not in sys.argv:
            raise

    if 'py2exe' in sys.argv:
        # FIXME: quick hack to include installed hg extensions in py2exe binary
        import hgext
        hgextdir = os.path.dirname(hgext.__file__)
        hgextmods = set(["hgext." + os.path.splitext(f)[0]
                      for f in os.listdir(hgextdir)])
        _data_files = [(root, [os.path.join(root, file_) for file_ in files])
                            for root, dirs, files in os.walk('icons')]
        extra['windows'] = [
                {"script":"contrib/tracelog.py",
                            "icon_resources": [(1, "icons/tortoise/python.ico")]}
                ]
        extra['com_server'] = ["tortoisehg"]
        extra['console'] = ["contrib/hg", "hgtk"]

    # add library files to support PyGtk-based dialogs/windows
    includes = ['dbhash', 'pango', 'atk', 'pangocairo', 'cairo', 'gobject']

    # Manually include other modules py2exe can't find by itself.
    if 'hgext.highlight' in hgextmods:
        includes += ['pygments.*', 'pygments.lexers.*', 'pygments.formatters.*',
                     'pygments.filters.*', 'pygments.styles.*']
    if 'hgext.patchbomb' in hgextmods:
        includes += ['email.*', 'email.mime.*']

    extra['options'] = {
       "py2exe" : {
           # This is one way to ensure that hgtk can find its icons when
           # running in a py2exe environment. It also makes debugging easier.
           "skip_archive" : 1,

           # Don't pull in all this MFC stuff used by the makepy UI.
           "excludes" : "pywin,pywin.dialogs,pywin.dialogs.list",

           # add library files to support PyGtk-based dialogs/windows
           # Note:
           #    after py2exe build, copy GTK's etc and lib directories into
           #    the dist directory created by py2exe.
           #    also needed is the GTK's share/themes (as dist/share/themes), 
           #    for dialogs to display in MS-Windows XP theme.
           "includes" : includes + list(hgextmods),
           "optimize" : 1,
       }
    }

    return _scripts, _packages, _data_files, extra


def setup_posix():
    # Specific definitios for Posix installations
    _extra = {}
    _scripts = ['hgtk']
    _packages = ['hggtk', 'hggtk.vis', 'hggtk.iniparse', 'tortoise']
    _data_files = [(os.path.join('share/pixmaps/tortoisehg', root),
        [os.path.join(root, file_) for file_ in files])
        for root, dirs, files in os.walk('icons')]
    _data_files += [('lib/nautilus/extensions-2.0/python',
                     ['contrib/nautilus-thg.py'])]

    return _scripts, _packages, _data_files, _extra


if os.name == "nt":
    (scripts, packages, data_files, extra) = setup_windows()
    desc='Windows shell extension for Mercurial VCS'
else:
    (scripts, packages, data_files, extra) = setup_posix()
    desc='TortoiseHg dialogs for Mercurial VCS'

try:
    l = os.popen('hg id -it').read().split()
    while len(l) > 1 and l[-1][0].isalpha(): # remove non-numbered tags
        l.pop()
    version = l and l[-1] or 'unknown' # latest tag or revision number
    if version.endswith('+'):
        version += time.strftime('%Y%m%d')
except OSError:
    version = "unknown"

f = file(os.path.join("hggtk", "__version__.py"), "w")
f.write('# this file is autogenerated by setup.py\n')
f.write('version = "%s"\n' % version)
f.close()

setup(name="tortoisehg",
        version=version,
        author='TK Soh',
        author_email='teekaysoh@gmail.com',
        url='http://bitbucket.org/tortoisehg/stable/',
        description=desc,
        license='GNU GPL2',
        scripts=scripts,
        packages=packages,
        data_files=data_files,
        **extra
    )

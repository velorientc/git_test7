# setup.py
# A distutils setup script to register TortoiseHg COM server
#

# To build stand-alone package, use 'python setup.py py2exe' then use
# InnoSetup to build the installer.  By default, the installer will be
# created as dist\Output\setup.exe.

# To build a source installer for use with the Mercurial NSI
# installer, use 
# 'python setup.py bdist_wininst --install-script=thg_postinstall.py'

import time
import sys
import os

# ModuleFinder can't handle runtime changes to __path__, but win32com uses them

try:
    # if this doesn't work, try import modulefinder
    import py2exe.mf as modulefinder
    import win32com
    for p in win32com.__path__[1:]:
        modulefinder.AddPackagePath("win32com", p)
    for extra in ["win32com.shell"]: #,"win32com.mapi"
        __import__(extra)
        m = sys.modules[extra]
        for p in m.__path__[1:]:
            modulefinder.AddPackagePath(extra, p)
except ImportError:
    # no build path setup, no worries.
    pass

from distutils.core import setup
import py2exe

_data_files = []
extra = {}
hgextmods = []

if 'py2exe' in sys.argv:
    # FIXME: quick hack to include installed hg extensions in py2exe binary
    import hgext
    hgextdir = os.path.dirname(hgext.__file__)
    hgextmods = set(["hgext." + os.path.splitext(f)[0]
                  for f in os.listdir(hgextdir)])
    _data_files = [(root, [os.path.join(root, file_) for file_ in files])
                        for root, dirs, files in os.walk('icons')]
    extra['windows'] = [
            {"script":"hgproc.py",
                        "icon_resources": [(1, "icons/tortoise/hg.ico")]},
            {"script":"hggtk/tracelog.py",
                        "icon_resources": [(1, "icons/tortoise/python.ico")]}
            ]
    extra['com_server'] = ["tortoisehg"]
    extra['console'] = ["contrib/hg", "hgutils/simplemerge"]

elif 'bdist_msi' in sys.argv or 'bdist_wininst' in sys.argv:
    # C:\Python25\share\tortoisehg\icons\...
    _data_files = [(os.path.join('share/tortoisehg', root),
                [os.path.join(root, file_) for file_ in files])
                for root, dirs, files in os.walk('icons')]

    # C:\Python25\share\tortoisehg\*.bat, *.py
    _data_files.append(('share/tortoisehg',
        ['hgproc.py', 'hgproc.bat', 'tortoisehg.py']))

    # C:\Python25\mercurial\hgrc.d\tortoisehg.rc
    _data_files.append(('mercurial/hgrc.d', ['installer/tortoisehg.rc']))

    # C:\Python25\Scripts\tracelog.bat, thg_postinstall.py
    extra['scripts'] = ['installer/tracelog.bat', 'installer/thg_postinstall.py']

opts = {
   "py2exe" : {
       # Don't pull in all this MFC stuff used by the makepy UI.
       "excludes" : "pywin,pywin.dialogs,pywin.dialogs.list",

       # add library files to support PyGtk-based dialogs/windows
       # Note:
       #    after py2exe build, copy GTK's etc and lib directories into
       #    the dist directory created by py2exe.
       #    also needed is the GTK's share/themes (as dist/share/themes), 
       #    for dialogs to display in MS-Windows XP theme.
       "includes" : "pango,atk,pangocairo,cairo,gobject," + ",".join(hgextmods),
   }
}

# specify version string, otherwise 'hg identify' will be used:
version = ''

import tortoise.version
tortoise.version.remember_version(version)

setup(name="TortoiseHg",
        version=tortoise.version.get_version(),
        author='TK Soh',
        author_email='teekaysoh@gmail.com',
        url='http://tortoisehg.sourceforge.net',
        description='Windows shell extension for Mercurial VCS',
        license='GNU GPL2',
        packages=['tortoise', 'hggtk'],
        data_files = _data_files,
        options=opts,
        **extra
    )

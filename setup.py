# setup.py
# A distutils setup script to register TortoiseHg COM server
#

# By default, the installer will be created as dist\Output\setup.exe.

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

# FIXME: quick hack to include installed hg extensions in py2exe binary
import hgext
hgextdir = os.path.dirname(hgext.__file__)
hgextmods = set(["hgext." + os.path.splitext(f)[0]
                  for f in os.listdir(hgextdir)])

py2exe_options = dict(
        # Don't pull in all this MFC stuff used by the makepy UI.
        excludes = "pywin,pywin.dialogs,pywin.dialogs.list",
        
        # add library files to support PyGtk-based dialogs/windows
        # Note:
        #    after py2exe build, copy GTK's etc and lib directories into
        #    the dist directory created by py2exe.
        #    also needed is the GTK's share/themes (as dist/share/themes), 
        #    for dialogs to display in MS-Windows XP theme.
        includes = "pango,atk,pangocairo,cairo,gobject," + ",".join(hgextmods),
    )

setup(name="TortoiseHg COM server",
        com_server=["tortoisehg"],
        console=[
                 "hg",
                 "hgproc.py",
                 "hgutils/simplemerge",         
                ],
        windows=[{"script":"hggtk/tracelog.py",
                  "icon_resources":[(1, "icons/tortoise/python.ico")]}],
        options = dict(py2exe=py2exe_options),
        data_files=[(os.path.join('', root),
                [os.path.join(root, file_) for file_ in files])
                for root, dirs, files in os.walk('icons')],
    )

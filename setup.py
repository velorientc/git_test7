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

# Don't pull in all this MFC stuff used by the makepy UI.
py2exe_options = dict(
        excludes = "pywin,pywin.dialogs,pywin.dialogs.list",
        includes = "pango,atk,pangocairo,cairo,gobject",
    )

setup(name="TortoiseHg COM server",
        com_server=["tortoisehg"],
        console=["hgproc.py", "hgutils\simplemerge"],
        options = dict(py2exe=py2exe_options),
        modules="win32com.shell",
        data_files=[(os.path.join('', root),
                [os.path.join(root, file_) for file_ in files])
                for root, dirs, files in os.walk('icons')],
    )

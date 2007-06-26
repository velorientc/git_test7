"""
shlib.py - TortoiseHg shell utilities
 Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.

"""

import os

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

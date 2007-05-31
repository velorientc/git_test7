"""
util.py - TortoiseHg utility functions
 Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.

"""

import os.path, re
from win32com.shell import shell, shellcon

_quotere = None
def shellquote(s):
    global _quotere
    if _quotere is None:
        _quotere = re.compile(r'(\\*)("|\\$)')
    return '"%s"' % _quotere.sub(r'\1\1\\\2', s)
    return "'%s'" % s.replace("'", "'\\''")

def find_path(pgmname):
    """ return first executable found in search path """
    ospath = os.environ['PATH'].split(os.pathsep)
    pathext = os.environ.get('PATHEXT', '.COM;.EXE;.BAT;.CMD')
    pathext = pathext.lower().split(os.pathsep)

    for path in ospath:
        for ext in pathext:
            ppath = os.path.join(path, pgmname + ext)
            if os.path.exists(ppath):
                return ppath

    return None

def find_root(path):
    p = os.path.isdir(path) and path or os.path.dirname(path)
    while not os.path.isdir(os.path.join(p, ".hg")):
        oldp = p
        p = os.path.dirname(p)
        if p == oldp:
            return None
    return p

def shell_notify(path):
    pidl, ignore = shell.SHILCreateFromPath(path, 0)
    print "notify: ", shell.SHGetPathFromIDList(pidl)
    shell.SHChangeNotify(shellcon.SHCNE_UPDATEITEM, 
                         shellcon.SHCNF_IDLIST | shellcon.SHCNF_FLUSHNOWAIT,
                         pidl,
                         None)

def get_icon_path(*args):
    icon = os.path.join(os.path.dirname(__file__), "..", "icons", *args)
    if not os.path.isfile(icon):
        return None
    return icon
    
def icon_to_bitmap(iconPathName, type="SMICON"):
    """
    create a bitmap based converted from an icon.

    adapted from pywin32's demo program win32gui_menu.py
    """
    from win32gui import *
    from win32api import *
    import win32con

    # Create one with an icon - this is a fair bit more work, as we need
    # to convert the icon to a bitmap.
    # First load the icon.
    if "MENUCHECK":
        ico_x = GetSystemMetrics(win32con.SM_CXMENUCHECK)
        ico_y = GetSystemMetrics(win32con.SM_CYMENUCHECK)
    else:
        ico_x = GetSystemMetrics(win32con.SM_CXSMICON)
        ico_y = GetSystemMetrics(win32con.SM_CYSMICON)
        
    hicon = LoadImage(0, iconPathName, win32con.IMAGE_ICON, ico_x, ico_y, win32con.LR_LOADFROMFILE)

    hdcBitmap = CreateCompatibleDC(0)
    hdcScreen = GetDC(0)
    hbm = CreateCompatibleBitmap(hdcScreen, ico_x, ico_y)
    hbmOld = SelectObject(hdcBitmap, hbm)
    # Fill the background.
    brush = GetSysColorBrush(win32con.COLOR_MENU)
    FillRect(hdcBitmap, (0, 0, ico_x, ico_y), brush)
    # unclear if brush needs to be feed.  Best clue I can find is:
    # "GetSysColorBrush returns a cached brush instead of allocating a new
    # one." - implies no DeleteObject
    # draw the icon
    DrawIconEx(hdcBitmap, 0, 0, hicon, ico_x, ico_y, 0, 0, win32con.DI_NORMAL)
    SelectObject(hdcBitmap, hbmOld)
    DeleteDC(hdcBitmap)
    return hbm

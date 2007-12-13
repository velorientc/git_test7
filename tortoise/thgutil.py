"""
util.py - TortoiseHg utility functions
 Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.

"""

import os.path, re
from win32com.shell import shell, shellcon
from win32gui import *
from win32api import *
import win32con

_quotere = None
def shellquote(s):
    global _quotere
    if _quotere is None:
        _quotere = re.compile(r'(\\*)("|\\$)')
    return '"%s"' % _quotere.sub(r'\1\1\\\2', s)
    return "'%s'" % s.replace("'", "'\\''")

def find_path(pgmname, path=None, ext=None):
    """ return first executable found in search path """
    print "find_path: ", pgmname, path, ext
    ospath = path and path or os.environ['PATH']
    ospath = ospath.split(os.pathsep)
    pathext = ext and ext or os.environ.get('PATHEXT', '.COM;.EXE;.BAT;.CMD')
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
    import sys
    dir = get_prog_root()
    icon = os.path.join(dir, "icons", *args)
    if not os.path.isfile(icon):
        return None
    return icon
    
def get_prog_root():
    import sys
    import _winreg
    
    key = r"Software\TortoiseHg"
    cat = _winreg.HKEY_CURRENT_USER     # HKEY_LOCAL_MACHINE
    dir = _winreg.QueryValue(cat, key)
    return dir

bitmap_cache = {}
def icon_to_bitmap(iconPathName):
    """
    create a bitmap based converted from an icon.

    adapted from pywin32's demo program win32gui_menu.py
    """
    global bitmap_cache
        
    cx = GetSystemMetrics(win32con.SM_CXMENUCHECK)
    cy = GetSystemMetrics(win32con.SM_CYMENUCHECK)
    
    # use icon image with size smaller but closer to menu size
    if cx >= 16:
        ico_x = ico_y = 16
    else:
        ico_x = ico_y = 12
    ico_idx = "%d:%d", (cx, cy)
    
    print "menucheck c_xy = ", cx, cy
    print "menucheck ico_xy = ", ico_x, ico_y
    
    # see if icon has been cached
    try:
        return bitmap_cache[iconPathName][ico_idx]
    except:
        pass

    hicon = LoadImage(0, iconPathName, win32con.IMAGE_ICON, ico_x, ico_y, 
            win32con.LR_LOADFROMFILE)

    hdcBitmap = CreateCompatibleDC(0)
    hdcScreen = GetDC(0)
    hbm = CreateCompatibleBitmap(hdcScreen, cx, cy)
    hbmOld = SelectObject(hdcBitmap, hbm)

    # Fill the background.
    brush = GetSysColorBrush(win32con.COLOR_MENU)
    FillRect(hdcBitmap, (0, 0, cx, cy), brush)
    
    # we try to center the icon image within the bitmap without resizing
    # the icon, so that the icon will be display as closely level to the
    # menu text as possible.
    startx = int((cx-ico_x)/2)
    starty = int((cx-ico_y)/2)    
    DrawIconEx(hdcBitmap, startx, starty, hicon, ico_x, ico_y, 0, 0,
            win32con.DI_NORMAL)
            
    # store bitmap to cache
    if not bitmap_cache.has_key(iconPathName):
        bitmap_cache[iconPathName] = {}
    bitmap_cache[iconPathName][ico_idx] = hbm
    
    # restore settings
    SelectObject(hdcBitmap, hbmOld)
    DeleteDC(hdcBitmap)
    DestroyIcon(hicon)
    
    return hbm

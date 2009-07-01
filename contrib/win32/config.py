"""
config.py
 Copyright (C) 2009 Steve Borho <steve@borho.org>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.
"""

# This version of config.py is used in the binary installer
# distributions of TortoiseHg on Windows.  Since we no longer need to
# worry about Python shell extensions, we can use the path of the
# current executable to find our package data.

import os
import sys
import win32api, win32process

proc = win32api.GetCurrentProcess()
try:
    # This will fail on windows < NT
    procpath = win32process.GetModuleFileNameEx(proc, 0)
except:
    procpath = win32api.GetModuleFileName(0)

bin_path = os.path.dirname(procpath)
license_path = os.path.join(bin_path, 'COPYING.txt')
locale_path = os.path.join(bin_path, 'locale')
icon_path = os.path.join(bin_path, 'icons')

enc = sys.getfilesystemencoding()
if enc:
    bin_path = bin_path.encode(enc)
    license_path = license_path.encode(enc)
    locale_path = locale_path.encode(enc)
    icon_path = icon_path.encode(enc)

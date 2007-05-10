"""
util.py - TortoiseHg utility functions
 Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.

"""

import os.path, re

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

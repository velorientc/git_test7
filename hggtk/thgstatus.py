#
# thgstatus.py - update TortoiseHg status cache
#
# Copyright (C) 2009 Adrian Buehlmann
#

'''update TortoiseHg status cache'''

from mercurial import hg
from thgutil import paths, shlib
import os

def cachefilepath(repo):
    return repo.join("thgstatus")

def run(_ui, *pats, **opts):
    root = paths.find_root()
    if opts.get('repository'):
        root = opts.get('repository')
    if root is None:
        _ui.status("no repository\n")
        return

    repo = hg.repository(_ui, root)

    if opts.get('remove'):
        try:
            os.remove(cachefilepath(repo))
        except OSError:
            pass
        return

    if opts.get('show'):
        try:
            f = open(cachefilepath(repo), 'rb')
            for e in f:
                _ui.status("%s %s\n" % (e[0], e[1:-1]))
            f.close()
        except IOError:
            _ui.status("*no status*\n")
        return

    wait = opts.get('delay') is not None
    shlib.update_thgstatus(_ui, root, wait=wait)

    if opts.get('notify'):
        shlib.shell_notify(opts.get('notify'))
    _ui.note("thgstatus updated\n") 

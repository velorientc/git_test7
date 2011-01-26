#!/usr/bin/env python
# ipythg.py - Run TortoiseHg Qt from IPython
#
# Copyright 2011 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.
"""Interactive Python shell for TortoiseHg

?         -> Introduction and overview of IPython's features.
%quickref -> Quick reference.
help      -> Python's own help system.
object?   -> Details about 'object'. ?object also works, ?? prints more.

hg        -> Run hg command in cmdui.Dialog. Usage: hg verify
thg       -> Run thg command. Usage: thg log -R mercurial

dialogs   -> List of currently-opened dialogs.
repos     -> Dict of repository objects.
run       -> Module to run TortoiseHg dialogs. Usage: run.log(ui)
ui        -> Mercurial's ui object.
"""
import os, sys, shlex
from IPython import ipapi
from IPython.Shell import IPShellQt4
from PyQt4 import QtCore, QtGui

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                '..')))
if 'HGPATH' in os.environ and os.path.isdir(os.environ['HGPATH']):
    sys.path.insert(1, os.environ['HGPATH'])

from mercurial import ui
from tortoisehg.hgqt import cmdui, thgrepo, run

def _runhgcommand(self, arg):
    def newdlg(ui):
        return cmdui.Dialog(shlex.split(arg))
    run.qtrun(newdlg, self.user_ns['ui'])

def _runthgcommand(self, arg):
    run.runcommand(self.user_ns['ui'], shlex.split(arg))

def _banner():
    lines = __doc__.splitlines()
    lines[2:2] = [run.shortlicense.strip(), '']
    return '\n'.join(lines) + '\n'

def _execipyshell(ui):
    """Setup IPython shell and enter mainloop"""
    ns = {}
    for mod in (QtCore, QtGui):
        ns.update((k, v) for k, v in vars(mod).iteritems()
                  if not k.startswith('_'))
    ns.update({'dialogs': run.qtrun._dialogs, 'repos': thgrepo._repocache,
               'run': run, 'ui': ui})
    shell = IPShellQt4(argv=[], user_ns=ns)
    ip = ipapi.IPApi(shell.IP)
    ip.expose_magic('hg', _runhgcommand)
    ip.expose_magic('thg', _runthgcommand)
    shell.mainloop(banner=_banner())

def _hookqtrun(ui):
    """Hook qtrun() at dlgfunc() to hijack exec_()"""
    run.qtrun._mainapp.exec_ = lambda: _execipyshell(ui)

def main():
    os.environ['THGDEBUG'] = '1'
    os.environ['THG_GUI_SPAWN'] = '1'
    run.qtrun(_hookqtrun, ui.ui())

if __name__ == '__main__':
    main()

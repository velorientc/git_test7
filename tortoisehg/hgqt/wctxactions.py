# wctxactions.py - menu and responses for working copy files
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import util, cmdutil, error, merge, commands
from tortoisehg.hgqt import qtlib, htmlui
from tortoisehg.util import hglib, shlib
from tortoisehg.util.i18n import _

from PyQt4.QtCore import Qt, SIGNAL
from PyQt4.QtGui import QAction, QMenu, QMessageBox

def wctxactions(parent, point, repo, selrows):
    if not selrows:
        return
    alltypes = set()
    for t, path in selrows:
        alltypes |= t

    def make(text, func, types, icon=None):
        files = [f for t, f in selrows if t & types]
        if not files:
            return None
        action = menu.addAction(text)
        if icon:
            action.setIcon(icon)
        action.wrapper = lambda files=files: run(func, parent, files, repo)
        parent.connect(action, SIGNAL('triggered()'), action.wrapper)
        return action

    menu = QMenu(parent)
    make(_('&Visual Diff'), vdiff, frozenset('MAR!'))
    make(_('Edit'), edit, frozenset('MACI?'))
    make(_('View missing'), viewmissing, frozenset('R!'))
    if len(repo.parents()) > 1:
        make(_('View other'), other, frozenset('MA'))
    menu.addSeparator()
    make(_('&Revert'), revert, frozenset('MAR!'))
    menu.addSeparator()
    make(_('L&og'), log, frozenset('MARC!'))
    menu.addSeparator()
    make(_('&Forget'), forget, frozenset('MAC!'))
    make(_('&Add'), add, frozenset('I?'))
    make(_('&Guess Rename...'), guessRename, frozenset('?!'))
    make(_('&Ignore'), ignore, frozenset('?'))
    make(_('Remove versioned'), remove, frozenset('C'))
    make(_('&Delete unversioned'), delete, frozenset('?I'))
    if len(selrows) == 1:
        menu.addSeparator()
        make(_('&Copy...'), copy, frozenset('MC'))
        make(_('Rename...'), rename, frozenset('MC'))
    menu.addSeparator()
    make(_('Mark unresolved'), unmark, frozenset('r'))
    make(_('Mark resolved'), mark, frozenset('u'))
    f = make(_('Restart Merge...'), resolve, frozenset('u'))
    if f:
        files = [f for t, f in selrows if 'u' in t]
        rmenu = QMenu(_('Restart merge with'))
        for tool in hglib.mergetools(repo.ui):
            action = rmenu.addAction(tool)
            action.wrapper = lambda tool=tool: resolve_with(tool, repo, files)
            parent.connect(action, SIGNAL('triggered()'), action.wrapper)
        menu.addMenu(rmenu)
    return menu.exec_(point)

def run(func, parent, files, repo):
    'run wrapper for all action methods'
    hu = htmlui.htmlui()
    name = func.__name__.title()
    notify = False
    cwd = os.getcwd()
    os.chdir(repo.root)
    try:
        # All operations should quietly succeed.  Any error should
        # result in a message box
        notify = func(parent, hu, repo, files)
        o, e = hu.getdata()
        if e:
            QMessageBox.warning(parent, name + _(' reported errors'), str(e))
        elif o:
            QMessageBox.information(parent, name + _(' output'), str(o))
        elif notify:
            wfiles = [repo.wjoin(x) for x in files]
            shlib.shell_notify(wfiles)
    except (util.Abort, IOError, OSError), e:
        QMessageBox.critical(parent, name + _(' Aborted'), str(e))
    except (error.LookupError), e:
        QMessageBox.critical(parent, name + _(' Aborted'), str(e))
    os.chdir(cwd)
    return notify

def vdiff(parent, ui, repo, files):
    raise NotImplementedError()

def edit(parent, ui, repo, files):
    raise NotImplementedError()

def viewmissing(parent, ui, repo, files):
    raise NotImplementedError()

def other(parent, ui, repo, files):
    raise NotImplementedError()

def revert(parent, ui, repo, files):
    revertopts = {'date': None, 'rev': '.'}

    if len(repo.parents()) > 1:
        res = qtlib.CustomPrompt(
                _('Uncommited merge - please select a parent revision'),
                _('Revert files to local or other parent?'), parent,
                (_('&Local'), _('&Other'), ('&Cancel')), 0, 2, files).run()
        if res == 0:
            revertopts['rev'] = repo[None].p1().rev()
        elif res == 1:
            revertopts['rev'] = repo[None].p2().rev()
        else:
            return
        commands.revert(ui, repo, *files, **revertopts)
    else:
        res = qtlib.CustomPrompt(
                 _('Confirm Revert'),
                 _('Revert changes to files?'), parent,
                 (_('&Yes (backup changes)'), _('Yes (&discard changes)'),
                  _('&Cancel')), 2, 2, files).run()
        if res == 2:
            return False
        if res == 1:
            revertopts['no_backup'] = True
        commands.revert(ui, repo, *files, **revertopts)
        return True

def log(parent, ui, repo, files):
    raise NotImplementedError()

def forget(parent, ui, repo, files):
    commands.forget(ui, repo, *files)
    return True

def add(parent, ui, repo, files):
    raise NotImplementedError()

def guessRename(parent, ui, repo, files):
    raise NotImplementedError()

def ignore(parent, ui, repo, files):
    raise NotImplementedError()

def remove(parent, ui, repo, files):
    commands.remove(ui, repo, *files)
    return True

def delete(parent, ui, repo, files):
    raise NotImplementedError()

def copy(parent, ui, repo, files):
    raise NotImplementedError()

def rename(parent, ui, repo, files):
    raise NotImplementedError()

def resolve(parent, ui, repo, files):
    raise NotImplementedError()

def unmark(parent, ui, repo, files):
    raise NotImplementedError()

def mark(parent, ui, repo, files):
    raise NotImplementedError()

def resolve_with(tool, repo, files):
    raise NotImplementedError()

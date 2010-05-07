# wctxactions.py - menu and responses for working copy files
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

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
        action.wrapper = lambda files=files: run(func, files, repo)
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

def run(func, files, repo):
    'run wrapper for all action methods'
    wfiles = [repo.wjoin(x) for x in files]
    hu = htmlui.htmlui()
    name = func.__name__.title()
    try:
        # All operations should quietly succeed.  Any error should
        # result in a message box
        notify = func(hu, wfiles, repo)
        o, e = hu.getdata()
        if e:
            QMessageBox.warning(None, name + _(' reported errors'), str(e))
        elif o:
            QMessageBox.information(None, name + _(' reported errors'), str(o))
        elif notify:
            shlib.shell_notify(wfiles)
        return notify
    except (util.Abort, IOError, OSError), e:
        QMessageBox.critical(None, name + _(' Aborted'), str(e))
    except (error.LookupError), e:
        QMessageBox.critical(None, name + _(' Aborted'), str(e))
    return False

def filelist(files):
    'utility function to present file list'
    text = '\n'.join(files[:5])
    if len(files) > 5:
        text += '  ...\n'
    return hglib.tounicode(text)

def vdiff(ui, repo, files):
    raise NotImplementedError()

def edit(ui, repo, files):
    raise NotImplementedError()

def viewmissing(ui, repo, files):
    raise NotImplementedError()

def other(ui, repo, files):
    raise NotImplementedError()

def revert(ui, repo, files):
    raise NotImplementedError()
    # Needs work
    revertopts = {}

    if len(repo.parents()) > 1:
        res = QMessageBox.Question(
                None,
                _('Uncommited merge - please select a parent revision'),
                _('Revert files to local or other parent?'),
                (_('&Local'), _('&Other'), _('&Cancel')), 2).run()
        if res == 0:
            revertopts['rev'] = repo[None].p1().rev()
        elif res == 1:
            revertopts['rev'] = repo[None].p2().rev()
        else:
            return
        response = None
    else:
        # response: 0=Yes, 1=Yes,no backup, 2=Cancel
        revs = revertopts['rev']
        if revs and type(revs) == list:
            revertopts['rev'] = revs[0]
        else:
            revertopts['rev'] = str(self.stat.repo['.'].rev())
        response = gdialog.CustomPrompt(_('Confirm Revert'),
                _('Revert files to revision %s?\n\n%s') % (revertopts['rev'],
                filelist(files)), self.stat, (_('&Yes (backup changes)'),
                                         _('Yes (&discard changes)'),
                                         _('&Cancel')), 2, 2).run()
    if response in (None, 0, 1):
        if response == 1:
            revertopts['no_backup'] = True
        commands.revert(ui, repo, *wfiles, **revertopts)
        return True

def log(ui, repo, files):
    raise NotImplementedError()

def forget(ui, repo, files):
    commands.forget(ui, repo, *files)
    return True

def add(ui, repo, files):
    raise NotImplementedError()

def guessRename(ui, repo, files):
    raise NotImplementedError()

def ignore(ui, repo, files):
    raise NotImplementedError()

def remove(ui, repo, files):
    commands.remove(ui, repo, *files)
    return True

def delete(ui, repo, files):
    raise NotImplementedError()

def copy(ui, repo, files):
    raise NotImplementedError()

def rename(ui, repo, files):
    raise NotImplementedError()

def resolve(ui, repo, files):
    raise NotImplementedError()

def unmark(ui, repo, files):
    raise NotImplementedError()

def mark(ui, repo, files):
    raise NotImplementedError()

def resolve_with(tool, repo, files):
    raise NotImplementedError()

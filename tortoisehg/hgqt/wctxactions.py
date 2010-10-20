# wctxactions.py - menu and responses for working copy files
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import re
import subprocess

from mercurial import util, error, merge, commands
from tortoisehg.hgqt import qtlib, htmlui, visdiff
from tortoisehg.util import hglib, shlib
from tortoisehg.hgqt.i18n import _

from PyQt4.QtCore import Qt
from PyQt4.QtGui import QAction, QMenu, QMessageBox, QFileDialog, QDialog

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
        action.args = (func, parent, files, repo)
        action.run = lambda: run(*action.args)
        action.triggered.connect(action.run)
        return action

    menu = QMenu(parent)
    make(_('&Visual Diff'), vdiff, frozenset('MAR!'))
    make(_('Edit'), edit, frozenset('MACI?'))
    make(_('View missing'), viewmissing, frozenset('R!'))
    if len(repo.parents()) > 1:
        make(_('View other'), viewother, frozenset('MA'))
    menu.addSeparator()
    make(_('&Revert'), revert, frozenset('MAR!'))
    make(_('&Add'), add, frozenset('R'))
    menu.addSeparator()
    make(_('File History'), log, frozenset('MARC!'))
    make(_('&Annotate'), annotate, frozenset('MARC!'))
    menu.addSeparator()
    make(_('&Forget'), forget, frozenset('MAC!'))
    make(_('&Add'), add, frozenset('I?'))
    make(_('&Detect Renames...'), guessRename, frozenset('A?!'))
    make(_('&Ignore'), ignore, frozenset('?'))
    make(_('Remove versioned'), remove, frozenset('C'))
    make(_('&Delete unversioned'), delete, frozenset('?I'))
    if len(selrows) == 1:
        menu.addSeparator()
        t, path = selrows[0]
        wctx = repo[None]
        if t & frozenset('?') and wctx.deleted():
            rmenu = QMenu(_('Was renamed from'))
            for d in wctx.deleted()[:15]:
                action = rmenu.addAction(hglib.tounicode(d))
                action.args = (repo, d, path)
                action.run = lambda: renamefromto(*action.args)
                action.triggered.connect(action.run)
            menu.addMenu(rmenu)
        else:
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
            action.args = (tool, repo, files)
            action.run = lambda: resolve_with(*action.args)
            action.triggered.connect(action.run)
        menu.addMenu(rmenu)
    return menu.exec_(point)

def run(func, parent, files, repo):
    'run wrapper for all action methods'
    hu = htmlui.htmlui()
    name = func.__name__.title()
    notify = False
    cwd = os.getcwd()
    try:
        os.chdir(repo.root)
        try:
            # All operations should quietly succeed.  Any error should
            # result in a message box
            notify = func(parent, hu, repo, files)
            o, e = hu.getdata()
            if e:
                QMessageBox.warning(parent, name + _(' errors'), str(e))
            elif o:
                QMessageBox.information(parent, name + _(' output'), str(o))
            elif notify:
                wfiles = [repo.wjoin(x) for x in files]
                shlib.shell_notify(wfiles)
        except (util.Abort, IOError, OSError), e:
            QMessageBox.critical(parent, name + _(' Aborted'), str(e))
        except (error.LookupError), e:
            QMessageBox.critical(parent, name + _(' Aborted'), str(e))
        except NotImplementedError:
            QMessageBox.critical(parent, name + _(' not implemented'), 
                    'Please add it :)')
    finally:
        os.chdir(cwd)
    return notify

def renamefromto(repo, deleted, unknown):
    repo.remove([deleted]) # !->R
    repo.copy(deleted, unknown)

def vdiff(parent, ui, repo, files):
    visdiff.visualdiff(ui, repo, files, {})

def edit(parent, ui, repo, files, lineno=None, search=None):
    files = [util.shellquote(util.localpath(f)) for f in files]
    editor = ui.config('tortoisehg', 'editor')
    assert len(files) == 1 or lineno == None
    if editor:
        try:
            regexp = re.compile('\[([^\]]*)\]')
            expanded = []
            pos = 0
            for m in regexp.finditer(editor):
                expanded.append(editor[pos:m.start()-1])
                phrase = editor[m.start()+1:m.end()-1]
                pos=m.end()+1
                if '$LINENUM' in phrase:
                    if lineno is None:
                        # throw away phrase
                        continue
                    phrase = phrase.replace('$LINENUM', str(lineno))
                elif '$SEARCH' in phrase:
                    if search is None:
                        # throw away phrase
                        continue
                    phrase = phrase.replace('$SEARCH', search)
                if '$FILE' in phrase:
                    phrase = phrase.replace('$FILE', files[0])
                    files = []
                expanded.append(phrase)
            expanded.append(editor[pos:])
            cmdline = ' '.join(expanded + files)
        except ValueError, e:
            # '[' or ']' not found
            cmdline = ' '.join([editor] + files)
        except TypeError, e:
            # variable expansion failed
            cmdline = ' '.join([editor] + files)
    else:
        editor = os.environ.get('HGEDITOR') or ui.config('ui', 'editor') or \
                 os.environ.get('EDITOR', 'vi')
        cmdline = ' '.join([editor] + files)
    if os.path.basename(editor) in ('vi', 'vim', 'hgeditor'):
        res = QMessageBox.critical(parent,
                       _('No visual editor configured'),
                       _('Please configure a visual editor.'))
        from tortoisehg.hgqt.settings import SettingsDialog
        dlg = SettingsDialog(False, focus='tortoisehg.editor')
        dlg.exec_()
        return

    cmdline = util.quotecommand(cmdline)
    try:
        subprocess.Popen(cmdline, shell=True, creationflags=visdiff.openflags,
                         stderr=None, stdout=None, stdin=None)
    except (OSError, EnvironmentError), e:
        QMessageBox.warning(parent,
                 _('Editor launch failure'),
                 _('%s : %s') % (cmd, str(e)))
    return False


def viewmissing(parent, ui, repo, files):
    base, _ = visdiff.snapshot(repo, files, repo['.'])
    edit(parent, ui, repo, [os.path.join(base, f) for f in files])

def viewother(parent, ui, repo, files):
    wctx = repo[None]
    assert bool(wctx.p2())
    base, _ = visdiff.snapshot(repo, files, wctx.p2())
    edit(parent, ui, repo, [os.path.join(base, f) for f in files])

def revert(parent, ui, repo, files):
    revertopts = {'date': None, 'rev': '.'}

    if len(repo.parents()) > 1:
        res = qtlib.CustomPrompt(
                _('Uncommited merge - please select a parent revision'),
                _('Revert files to local or other parent?'), parent,
                (_('&Local'), _('&Other'), _('Cancel')), 0, 2, files).run()
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
                  _('Cancel')), 2, 2, files).run()
        if res == 2:
            return False
        if res == 1:
            revertopts['no_backup'] = True
        commands.revert(ui, repo, *files, **revertopts)
        return True

def log(parent, ui, repo, files):
    raise NotImplementedError()

def annotate(parent, ui, repo, files):
    from tortoisehg.hgqt import annotate
    dlg = annotate.AnnotateDialog(files[0], parent=parent)
    dlg.show()
    return False

def forget(parent, ui, repo, files):
    commands.forget(ui, repo, *files)
    return True

def add(parent, ui, repo, files):
    commands.add(ui, repo, *files)
    return True

def guessRename(parent, ui, repo, files):
    from tortoisehg.hgqt.guess import DetectRenameDialog
    dlg = DetectRenameDialog(parent, repo.root, *files)
    def matched():
        ret = True
    ret = False
    dlg.matchAccepted.connect(matched)
    dlg.exec_()
    return ret

def ignore(parent, ui, repo, files):
    from tortoisehg.hgqt.hgignore import HgignoreDialog
    dlg = HgignoreDialog(parent, repo.root, *files)
    return dlg.exec_() == QDialog.Accepted

def remove(parent, ui, repo, files):
    commands.remove(ui, repo, *files)
    return True

def delete(parent, ui, repo, files):
    res = qtlib.CustomPrompt(
            _('Confirm Delete Unrevisioned'),
            _('Delete the following unrevisioned files?'),
            parent, (_('&Delete'), _('Cancel')), 1, 1, files).run()
    if res == 1:
        return
    for wfile in files:
        os.unlink(wfile)
    return True

def copy(parent, ui, repo, files):
    assert len(files) == 1
    wfile = repo.wjoin(files[0])
    fd = QFileDialog(parent)
    fname = fd.getSaveFileName(parent, _('Copy file to'), wfile)
    if not fname:
        return
    fname = hglib.fromunicode(fname)
    wfiles = [wfile, fname]
    commands.copy(ui, repo, *wfiles)
    return True

def rename(parent, ui, repo, files):
    # needs rename dialog
    raise NotImplementedError()

def unmark(parent, ui, repo, files):
    ms = merge.mergestate(repo)
    for wfile in files:
        ms.mark(wfile, 'u')
    ms.commit()
    return True

def mark(parent, ui, repo, files):
    ms = merge.mergestate(repo)
    for wfile in files:
        ms.mark(wfile, 'r')
    ms.commit()
    return True

def resolve(parent, ui, repo, files):
    commands.resolve(ui, repo, *files)
    return True

def resolve_with(tool, repo, files):
    opts = {'tool': tool}
    commands.resolve(repo.ui, repo, *files, **opts)
    return True

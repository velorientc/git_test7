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
from PyQt4.QtGui import *

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
            action.setIcon(qtlib.getmenuicon(icon))
        action.args = (func, parent, files, repo)
        action.run = lambda: run(*action.args)
        action.triggered.connect(action.run)
        return action

    if hasattr(parent, 'contextmenu'):
        menu = parent.contextmenu
        menu.clear()
    else:
        menu = QMenu(parent)
        parent.contextmenu = menu
    make(_('&Visual Diff'), vdiff, frozenset('MAR!'), 'visualdiff')
    make(_('Copy patch'), copyPatch, frozenset('MAR!'), 'copy-patch')
    make(_('Edit'), edit, frozenset('MACI?'), 'edit-file')
    make(_('View missing'), viewmissing, frozenset('R!'))
    if len(repo.parents()) > 1:
        make(_('View other'), viewother, frozenset('MA'))
    menu.addSeparator()
    make(_('&Revert'), revert, frozenset('MAR!'), 'hg-revert')
    make(_('&Add'), add, frozenset('R'), 'fileadd')
    menu.addSeparator()
    make(_('File History'), log, frozenset('MARC!'), 'hg-log')
    make(_('&Annotate'), annotate, frozenset('MARC!'), 'hg-annotate')
    menu.addSeparator()
    make(_('&Forget'), forget, frozenset('MAC!'), 'filedelete')
    make(_('&Add'), add, frozenset('I?'), 'fileadd')
    make(_('&Detect Renames...'), guessRename, frozenset('A?!'), 'detect_rename')
    make(_('&Ignore'), ignore, frozenset('?'), 'ignore')
    make(_('Remove versioned'), remove, frozenset('C'), 'remove')
    make(_('&Delete unversioned'), delete, frozenset('?I'), 'hg-purge')
    if len(selrows) == 1:
        menu.addSeparator()
        t, path = selrows[0]
        wctx = repo[None]
        if t & frozenset('?') and wctx.deleted():
            rmenu = QMenu(_('Was renamed from'))
            for d in wctx.deleted()[:15]:
                def mkaction(deleted):
                    a = rmenu.addAction(hglib.tounicode(deleted))
                    a.triggered.connect(lambda: renamefromto(repo, deleted, path))
                mkaction(d)
            menu.addMenu(rmenu)
        else:
            make(_('&Copy...'), copy, frozenset('MC'), 'edit-copy')
            make(_('Rename...'), rename, frozenset('MC'), 'hg-rename')
    menu.addSeparator()
    make(_('Mark unresolved'), unmark, frozenset('r'))
    make(_('Mark resolved'), mark, frozenset('u'))
    f = make(_('Restart Merge...'), resolve, frozenset('u'))
    if f:
        files = [f for t, f in selrows if 'u' in t]
        rmenu = QMenu(_('Restart merge with'))
        for tool in hglib.mergetools(repo.ui):
            def mkaction(rtool):
                a = rmenu.addAction(hglib.tounicode(rtool))
                a.triggered.connect(lambda: resolve_with(rtool, repo, files))
            mkaction(tool)
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
                QMessageBox.warning(parent, name + _(' errors'),
                                    hglib.tounicode(str(e)))
            elif o:
                QMessageBox.information(parent, name + _(' output'),
                                        hglib.tounicode(str(o)))
            elif notify:
                wfiles = [repo.wjoin(x) for x in files]
                shlib.shell_notify(wfiles)
        except (IOError, OSError), e:
            err = hglib.tounicode(str(e))
            QMessageBox.critical(parent, name + _(' Aborted'), err)
        except util.Abort, e:
            if e.hint:
                err = _('%s (hint: %s)') % (hglib.tounicode(str(e)),
                                            hglib.tounicode(e.hint))
            else:
                err = hglib.tounicode(str(e))
            QMessageBox.critical(parent, name + _(' Aborted'), err)
        except (error.LookupError), e:
            err = hglib.tounicode(str(e))
            QMessageBox.critical(parent, name + _(' Aborted'), err)
        except NotImplementedError:
            QMessageBox.critical(parent, name + _(' not implemented'),
                    'Please add it :)')
    finally:
        os.chdir(cwd)
    return notify

def renamefromto(repo, deleted, unknown):
    repo[None].copy(deleted, unknown)
    repo[None].remove([deleted], unlink=False) # !->R

def copyPatch(parent, ui, repo, files):
    ui.pushbuffer()
    try:
        commands.diff(ui, repo, *files)
    except Exception, e:
        ui.popbuffer()
        if 'THGDEBUG' in os.environ:
            import traceback
            traceback.print_exc()
        return
    output = ui.popbuffer()
    QApplication.clipboard().setText(hglib.tounicode(output))

def vdiff(parent, ui, repo, files):
    dlg = visdiff.visualdiff(ui, repo, files, {})
    if dlg:
        dlg.exec_()

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
                 _('Revert local file changes?'), parent,
                 (_('&Revert with backup'), _('&Discard changes'),
                  _('Cancel')), 2, 2, files).run()
        if res == 2:
            return False
        if res == 1:
            revertopts['no_backup'] = True
        commands.revert(ui, repo, *files, **revertopts)
        return True

def log(parent, ui, repo, files):
    from tortoisehg.hgqt.workbench import run
    from tortoisehg.hgqt.run import qtrun
    opts = {'root': repo.root}
    qtrun(run, repo.ui, *files, **opts)
    return False

def annotate(parent, ui, repo, files):
    from tortoisehg.hgqt.annotate import run
    from tortoisehg.hgqt.run import qtrun
    opts = {'root': repo.root}
    qtrun(run, repo.ui, *files, **opts)
    return False

def forget(parent, ui, repo, files):
    commands.forget(ui, repo, *files)
    return True

def add(parent, ui, repo, files):
    commands.add(ui, repo, *files)
    return True

def guessRename(parent, ui, repo, files):
    from tortoisehg.hgqt.guess import DetectRenameDialog
    dlg = DetectRenameDialog(repo, parent, *files)
    def matched():
        ret = True
    ret = False
    dlg.matchAccepted.connect(matched)
    dlg.finished.connect(dlg.deleteLater)
    dlg.exec_()
    return ret

def ignore(parent, ui, repo, files):
    from tortoisehg.hgqt.hgignore import HgignoreDialog
    dlg = HgignoreDialog(repo, parent, *files)
    dlg.finished.connect(dlg.deleteLater)
    return dlg.exec_() == QDialog.Accepted

def remove(parent, ui, repo, files):
    commands.remove(ui, repo, *files)
    return True

def delete(parent, ui, repo, files):
    res = qtlib.CustomPrompt(
            _('Confirm Delete Unversioned'),
            _('Delete the following unversioned files?'),
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
    from tortoisehg.hgqt.rename import RenameDialog
    assert len(files) == 1
    dlg = RenameDialog(repo, files, parent)
    dlg.finished.connect(dlg.deleteLater)
    dlg.exec_()
    return True

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

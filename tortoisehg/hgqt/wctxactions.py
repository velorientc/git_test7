# wctxactions.py - menu and responses for working copy files
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import util, error, merge, commands, extensions
from tortoisehg.hgqt import qtlib, htmlui, visdiff, lfprompt, customtools
from tortoisehg.hgqt import filedialogs
from tortoisehg.util import hglib, shlib
from tortoisehg.hgqt.i18n import _

from PyQt4.QtCore import Qt, QObject, QDir, pyqtSignal, pyqtSlot
from PyQt4.QtGui import *

class WctxActions(QObject):
    'container class for working context actions'

    refreshNeeded = pyqtSignal()
    runCustomCommandRequested = pyqtSignal(str, list)

    def __init__(self, repoagent, parent, checkable=True):
        super(WctxActions, self).__init__(parent)

        self.menu = QMenu(parent)
        self._repoagent = repoagent
        self._filedialogs = qtlib.DialogKeeper(WctxActions._createFileDialog,
                                               parent=self)
        allactions = []

        def make(text, func, types, icon=None, keys=None, slot=self.runAction):
            action = QAction(text, parent)
            action._filetypes = types
            action._runfunc = func
            if icon:
                action.setIcon(qtlib.geticon(icon))
            if keys:
                action.setShortcut(QKeySequence(keys))
            action.triggered.connect(slot)
            parent.addAction(action)
            allactions.append(action)

        make(_('&Diff to Parent'), vdiff, frozenset('MAR!'), 'visualdiff', 'CTRL+D')
        make(_('&Copy Patch'), copyPatch, frozenset('MAR!'), 'copy-patch')
        make(_('&Edit'), edit, frozenset('MACI?'), 'edit-file', 'SHIFT+CTRL+E')
        make(_('&Open'), openfile, frozenset('MACI?'), '', 'SHIFT+CTRL+L')
        allactions.append(None)
        make(_('Open S&ubrepository'), opensubrepo, frozenset('S'),
            'thg-repository-open')
        make(_('E&xplore Subrepository'), explore, frozenset('S'),
            'system-file-manager')
        make(_('Open &Terminal'), terminal, frozenset('S'),
            'utilities-terminal')
        allactions.append(None)
        make(_('Copy &Path'), copyPath, frozenset('MARC?!IS'), '')
        make(_('&View Missing'), viewmissing, frozenset('R!'))
        allactions.append(None)
        make(_('&Revert...'), revert, frozenset('SMAR!'), 'hg-revert')
        make(_('&Add'), add, frozenset('R'), 'fileadd')
        allactions.append(None)
        make(_('File &History'), None, frozenset('MARC!'), 'hg-log',
             slot=self.log)
        allactions.append(None)
        make(_('&Forget'), forget, frozenset('MC!'), 'filedelete')
        make(_('&Add'), add, frozenset('I?'), 'fileadd')
        if 'largefiles' in self.repo.extensions():
            make(_('Add &Largefiles...'), addlf, frozenset('I?'))
        make(_('De&tect Renames...'), guessRename, frozenset('A?!'),
             'detect_rename', slot=self.runDialogAction)
        make(_('&Ignore...'), ignore, frozenset('?'), 'ignore',
             slot=self.runDialogAction)
        make(_('Re&move Versioned'), remove, frozenset('C'), 'remove')
        make(_('&Delete Unversioned...'), delete, frozenset('?I'), 'hg-purge')
        allactions.append(None)
        make(_('&Mark Unresolved'), unmark, frozenset('r'))
        make(_('&Mark Resolved'), mark, frozenset('u'))
        if checkable:
            # no &-shortcut because check/uncheck can be done by space key
            allactions.append(None)
            make(_('Check'), check, frozenset('MARC?!IS'), '')
            make(_('Uncheck'), uncheck, frozenset('MARC?!IS'), '')
        self.allactions = allactions

    @property
    def repo(self):
        return self._repoagent.rawRepo()

    def updateActionSensitivity(self, selrows):
        'Enable/Disable permanent actions based on current selection'
        self.selrows = selrows
        alltypes = set()
        for types, wfile in selrows:
            alltypes |= types
        for action in self.allactions:
            if action is not None:
                action.setEnabled(bool(action._filetypes & alltypes))

    def makeMenu(self, selrows):
        self.selrows = selrows
        repo, menu = self.repo, self.menu

        alltypes = set()
        for types, wfile in selrows:
            alltypes |= types

        menu.clear()
        addedActions = False
        for action in self.allactions:
            if action is None:
                if addedActions:
                    menu.addSeparator()
                    addedActions = False
            elif action._filetypes & alltypes:
                menu.addAction(action)
                addedActions = True

        def make(text, func, types=None, icon=None, inmenu=None,
                 slot=self.runAction):
            if not types & alltypes:
                return
            if inmenu is None:
                inmenu = menu
            action = inmenu.addAction(text)
            action._filetypes = types
            action._runfunc = func
            if icon:
                action.setIcon(qtlib.geticon(icon))
            if func is not None:
                action.triggered.connect(slot)
            return action

        if len(repo.parents()) > 1:
            make(_('View O&ther'), viewother, frozenset('MA'))

        if len(selrows) == 1:
            menu.addSeparator()
            make(_('&Copy...'), copy, frozenset('MC'), 'edit-copy',
                 slot=self.runDialogAction)
            make(_('Re&name...'), rename, frozenset('MC'), 'hg-rename',
                 slot=self.runDialogAction)

        menu.addSeparator()
        customtools.addCustomToolsSubmenu(menu, repo.ui,
            location='workbench.commit.custom-menu',
            make=make,
            slot=self._runCustomCommandByMenu)

        # Add 'was renamed from' actions for unknown files
        t, path = selrows[0]
        wctx = self.repo[None]
        if t & frozenset('?') and wctx.deleted():
            rmenu = QMenu(_('Was renamed from'), self.parent())
            for d in wctx.deleted()[:15]:
                def mkaction(deleted):
                    a = rmenu.addAction(hglib.tounicode(deleted))
                    a.triggered.connect(lambda: renamefromto(repo, deleted, path))
                mkaction(d)
            menu.addSeparator()
            menu.addMenu(rmenu)

        # Add restart merge actions for resolved files
        if alltypes & frozenset('u'):
            f = make(_('Restart Mer&ge'), resolve, frozenset('u'))
            files = [f for t, f in selrows if 'u' in t]
            rmenu = QMenu(_('Restart Merge &with'), self.parent())
            for tool in hglib.mergetools(repo.ui):
                def mkaction(rtool):
                    a = rmenu.addAction(hglib.tounicode(rtool))
                    a.triggered.connect(lambda: resolve_with(rtool, repo, files))
                mkaction(tool)
            menu.addSeparator()
            menu.addMenu(rmenu)
        return menu

    def _filesForAction(self, action):
        return [wfile for t, wfile in self.selrows if t & action._filetypes]

    @pyqtSlot(QAction)
    def _runCustomCommandByMenu(self, action):
        files = self._filesForAction(action)
        self.runCustomCommandRequested.emit(
            str(action.data().toString()), files)

    def runAction(self):
        'run wrapper for direct action methods'

        repo, action, parent = self.repo, self.sender(), self.parent()
        func = action._runfunc
        files = self._filesForAction(action)

        hu = htmlui.htmlui()
        name = hglib.tounicode(func.__name__.title())
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
                        hglib.tounicode(e))
                elif o:
                    QMessageBox.information(parent, name + _(' output'),
                        hglib.tounicode(o))
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
        finally:
            os.chdir(cwd)

        if notify:
            self.refreshNeeded.emit()

    #@pyqtSlot()
    def runDialogAction(self):
        'run wrapper for modal dialog action methods'

        repo, action, parent = self.repo, self.sender(), self.parent()
        func = action._runfunc
        files = self._filesForAction(action)

        notify = func(parent, self._repoagent, files)
        if notify:
            wfiles = [repo.wjoin(x) for x in files]
            shlib.shell_notify(wfiles)
            self.refreshNeeded.emit()

    #@pyqtSlot()
    def log(self):
        for path in self._filesForAction(self.sender()):
            self._filedialogs.open(path)

    def _createFileDialog(self, path):
        return filedialogs.FileLogDialog(self._repoagent, path)

def renamefromto(repo, deleted, unknown):
    repo[None].copy(deleted, unknown)
    repo[None].forget([deleted]) # !->R

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

def copyPath(parent, ui, repo, files):
    clip = QApplication.clipboard()
    absfiles = [hglib.fromunicode(QDir.toNativeSeparators(repo.wjoin(fname)))
         for fname in files]
    clip.setText(hglib.tounicode(os.linesep.join(absfiles)))

def vdiff(parent, ui, repo, files):
    dlg = visdiff.visualdiff(ui, repo, files, {})
    if dlg:
        dlg.exec_()

def edit(parent, ui, repo, files, lineno=None, search=None):
    qtlib.editfiles(repo, files, lineno, search, parent)

def openfile(parent, ui, repo, files):
    qtlib.openfiles(repo, files, parent)

def opensubrepo(parent, ui, repo, files):
    for filename in files:
        path = os.path.join(repo.root, filename)
        if os.path.isdir(path):
            parent.linkActivated.emit(u'repo:' + hglib.tounicode(path))
        else:
            QMessageBox.warning(parent,
                _("Cannot open subrepository"),
                _("The selected subrepository does not exist on the working directory"))

def explore(parent, ui, repo, files):
    qtlib.openfiles(repo, files, parent)

def terminal(parent, ui, repo, files):
    for filename in files:
        root = repo.wjoin(filename)
        if os.path.isdir(root):
            qtlib.openshell(root, filename, repo.ui)

def viewmissing(parent, ui, repo, files):
    base, _ = visdiff.snapshot(repo, files, repo['.'])
    edit(parent, ui, repo, [os.path.join(base, f) for f in files])

def viewother(parent, ui, repo, files):
    wctx = repo[None]
    assert bool(wctx.p2())
    base, _ = visdiff.snapshot(repo, files, wctx.p2())
    edit(parent, ui, repo, [os.path.join(base, f) for f in files])

def revert(parent, ui, repo, files):
    revertopts = {'date': None, 'rev': '.', 'all': False}

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
            return False
        commands.revert(ui, repo, *files, **revertopts)
    else:
        wctx = repo[None]
        if [file for file in files if file in wctx.modified()]:
            res = qtlib.CustomPrompt(
                _('Confirm Revert'),
                _('Revert local file changes?'), parent,
                (_('&Revert with backup'), _('&Discard changes'),
                _('Cancel')), 2, 2, files).run()
            if res == 2:
                return False
            if res == 1:
                revertopts['no_backup'] = True
        else:
            res = qtlib.CustomPrompt(
                    _('Confirm Revert'),
                    _('Revert the following files?'),
                    parent, (_('&Revert'), _('Cancel')), 1, 1, files).run()
            if res == 1:
                return False
        commands.revert(ui, repo, *files, **revertopts)
        return True

def forget(parent, ui, repo, files):
    commands.forget(ui, repo, *files)
    return True

def add(parent, ui, repo, files):
    if 'largefiles' in repo.extensions():
        result = lfprompt.promptForLfiles(parent, ui, repo, files)
        if not result:
            return False
        files, lfiles = result
        if files:
            commands.add(ui, repo, normal=True, *files)
        if lfiles:
            commands.add(ui, repo, lfsize='', normal=False, large=True, *lfiles)
    else:
        commands.add(ui, repo, *files)
    return True

def addlf(parent, ui, repo, files):
    commands.add(ui, repo, lfsize='', normal=None, large=True, *files)
    return True

def guessRename(parent, repoagent, files):
    from tortoisehg.hgqt.guess import DetectRenameDialog
    dlg = DetectRenameDialog(repoagent, parent, *files)
    def matched():
        ret[0] = True
    ret = [False]
    dlg.matchAccepted.connect(matched)
    dlg.finished.connect(dlg.deleteLater)
    dlg.exec_()
    return ret[0]

def ignore(parent, repoagent, files):
    from tortoisehg.hgqt.hgignore import HgignoreDialog
    dlg = HgignoreDialog(repoagent, parent, *files)
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
        return False
    for wfile in files:
        os.unlink(wfile)
    return True

def copy(parent, repoagent, files):
    from tortoisehg.hgqt.rename import RenameDialog
    assert len(files) == 1
    dlg = RenameDialog(repoagent, files, parent, iscopy=True)
    dlg.finished.connect(dlg.deleteLater)
    dlg.exec_()
    return True

def rename(parent, repoagent, files):
    from tortoisehg.hgqt.rename import RenameDialog
    assert len(files) == 1
    dlg = RenameDialog(repoagent, files, parent)
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
    paths = [repo.wjoin(f) for f in files]
    commands.resolve(repo.ui, repo, *paths, **opts)
    return True

def check(parent, ui, repo, files):
    parent.tv.model().check(files, True)
    return True

def uncheck(parent, ui, repo, files):
    parent.tv.model().check(files, False)
    return True

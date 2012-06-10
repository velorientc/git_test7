# filectxactions.py - context menu actions for repository files
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
# Copyright 2010 Steve Borho <steve@borho.org>
# Copyright 2012 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import util

from tortoisehg.hgqt import qtlib, revert, visdiff
from tortoisehg.hgqt.filedialogs import FileLogDialog, FileDiffDialog
from tortoisehg.hgqt.i18n import _
from tortoisehg.util import hglib

class FilectxActions(QObject):
    """Container for repository file actions"""

    linkActivated = pyqtSignal(unicode)

    def __init__(self, repo, parent=None, rev=None):
        super(FilectxActions, self).__init__(parent)
        if parent is not None and not isinstance(parent, QWidget):
            raise ValueError('parent must be a QWidget')

        self.repo = repo
        self.ctx = self.repo[rev]
        self._selectedfiles = []  # local encoding
        self._currentfile = None  # local encoding
        self._itemissubrepo = False

        self._diff_dialogs = {}
        self._nav_dialogs = {}
        self.filecontextmenu = None
        self.subrepocontextmenu = None

        self._actions = {}
        for name, desc, icon, key, tip, cb in [
            ('navigate', _('File history'), 'hg-log', 'Shift+Return',
              _('Show the history of the selected file'), self.navigate),
            ('diffnavigate', _('Compare file revisions'), 'compare-files', None,
              _('Compare revisions of the selected file'), self.diffNavigate),
            ('diff', _('Diff to parent'), 'visualdiff', 'Ctrl+D',
              _('View file changes in external diff tool'), self.vdiff),
            ('ldiff', _('Diff to local'), 'ldiff', 'Shift+Ctrl+D',
              _('View changes to current in external diff tool'),
              self.vdifflocal),
            ('edit', _('View at Revision'), 'view-at-revision', 'Alt+Ctrl+E',
              _('View file as it appeared at this revision'), self.editfile),
            ('save', _('Save at Revision'), None, 'Alt+Ctrl+S',
              _('Save file as it appeared at this revision'), self.savefile),
            ('ledit', _('Edit Local'), 'edit-file', 'Shift+Ctrl+E',
              _('Edit current file in working copy'), self.editlocal),
            ('lopen', _('Open Local'), '', 'Shift+Ctrl+O',
              _('Edit current file in working copy'), self.openlocal),
            ('copypath', _('Copy Path'), '', 'Shift+Ctrl+C',
              _('Copy full path of file(s) to the clipboard'),
              self.copypath),
            ('revert', _('Revert to Revision'), 'hg-revert', 'Alt+Ctrl+T',
              _('Revert file(s) to contents at this revision'),
              self.revertfile),
            ('opensubrepo', _('Open subrepository'), 'thg-repository-open',
              'Alt+Ctrl+O', _('Open the selected subrepository'),
              self.opensubrepo),
            ('explore', _('Explore subrepository'), 'system-file-manager',
              'Alt+Ctrl+E', _('Open the selected subrepository'),
              self.explore),
            ('terminal', _('Open terminal in subrepository'),
              'utilities-terminal', 'Alt+Ctrl+T',
              _('Open a shell terminal in the selected subrepository root'),
              self.terminal),
            ]:
            act = QAction(desc, self)
            if icon:
                act.setIcon(qtlib.getmenuicon(icon))
            if key:
                act.setShortcut(key)
            if tip:
                act.setStatusTip(tip)
            if cb:
                act.triggered.connect(cb)
            self._actions[name] = act

    def setRepo(self, repo):
        self.repo = repo

    def setRev(self, rev):
        self.ctx = self.repo[rev]
        real = type(rev) is int
        wd = rev is None
        for act in ['navigate', 'diffnavigate', 'ldiff', 'edit', 'save']:
            self._actions[act].setEnabled(real)
        for act in ['diff', 'revert']:
            self._actions[act].setEnabled(real or wd)

    def setPaths_(self, selectedfiles, currentfile=None, itemissubrepo=False):
        """Set selected files [local encoding]"""
        if not currentfile and selectedfiles:
            currentfile = selectedfiles[0]
        self._selectedfiles = list(selectedfiles)
        self._currentfile = currentfile
        self._itemissubrepo = itemissubrepo

    def actions(self):
        """List of the actions; The owner widget should register them"""
        return self._actions.values()

    def menu(self):
        """Menu for the current selection if available; otherwise None"""
        # Subrepos and regular items have different context menus
        if self._itemissubrepo:
            contextmenu = self.subrepocontextmenu
            actionlist = ['opensubrepo', 'explore', 'terminal', None, 'revert']
        else:
            contextmenu = self.filecontextmenu
            actionlist = ['diff', 'ldiff', None, 'edit', 'save', None,
                            'ledit', 'lopen', 'copypath', None, 'revert', None,
                            'navigate', 'diffnavigate']

        if not contextmenu:
            contextmenu = QMenu(self.parent())
            for act in actionlist:
                if act:
                    contextmenu.addAction(self._actions[act])
                else:
                    contextmenu.addSeparator()

            if self._itemissubrepo:
                self.subrepocontextmenu = contextmenu
            else:
                self.filecontextmenu = contextmenu

        ln = len(self._selectedfiles)
        if ln == 0:
            return
        if ln > 1 and not self._itemissubrepo:
            singlefileactions = False
        else:
            singlefileactions = True
        self._actions['navigate'].setEnabled(singlefileactions)
        self._actions['diffnavigate'].setEnabled(singlefileactions)
        return contextmenu

    def navigate(self, filename=None):
        self._navigate(filename, FileLogDialog, self._nav_dialogs)

    def diffNavigate(self, filename=None):
        self._navigate(filename, FileDiffDialog, self._diff_dialogs)

    def vdiff(self):
        filenames = self._selectedfiles
        if not filenames:
            return
        rev = self.ctx.rev()
        if rev in self.repo.thgmqunappliedpatches:
            QMessageBox.warning(self,
                _("Cannot display visual diff"),
                _("Visual diffs are not supported for unapplied patches"))
            return
        opts = {'change': rev}
        dlg = visdiff.visualdiff(self.repo.ui, self.repo, filenames, opts)
        if dlg:
            dlg.exec_()

    def vdifflocal(self):
        filenames = self._selectedfiles
        if not filenames:
            return
        assert type(self.ctx.rev()) is int
        opts = {'rev':['rev(%d)' % (self.ctx.rev())]}
        dlg = visdiff.visualdiff(self.repo.ui, self.repo, filenames, opts)
        if dlg:
            dlg.exec_()

    def editfile(self):
        filenames = self._selectedfiles
        if not filenames:
            return
        rev = self.ctx.rev()
        if rev is None:
            qtlib.editfiles(self.repo, filenames, parent=self.parent())
        else:
            base, _ = visdiff.snapshot(self.repo, filenames, self.ctx)
            files = [os.path.join(base, filename)
                     for filename in filenames]
            qtlib.editfiles(self.repo, files, parent=self.parent())

    def savefile(self):
        filenames = self._selectedfiles
        if not filenames:
            return
        qtlib.savefiles(self.repo, filenames, self.ctx.rev(),
                        parent=self.parent())

    def editlocal(self):
        filenames = self._selectedfiles
        if not filenames:
            return
        qtlib.editfiles(self.repo, filenames, parent=self.parent())

    def openlocal(self):
        filenames = self._selectedfiles
        if not filenames:
            return
        qtlib.openfiles(self.repo, filenames)

    def copypath(self):
        absfiles = [util.localpath(self.repo.wjoin(f))
                    for f in self._selectedfiles]
        QApplication.clipboard().setText(hglib.tounicode(os.linesep.join(absfiles)))

    def revertfile(self):
        fileSelection = self._selectedfiles
        if len(fileSelection) == 0:
            return
        rev = self.ctx.rev()
        if rev is None:
            rev = self.ctx.p1().rev()
        dlg = revert.RevertDialog(self.repo, fileSelection, rev,
                                  parent=self.parent())
        dlg.exec_()

    def _navigate(self, filename, dlgclass, dlgdict):
        if not filename:
            filename = self._selectedfiles[0]
        if filename is not None and len(self.repo.file(filename))>0:
            if filename not in dlgdict:
                # dirty hack to pass workbench only if available
                from tortoisehg.hgqt import workbench  # avoid cyclic dep
                repoviewer = None
                if self.parent() and isinstance(self.parent().window(),
                                                workbench.Workbench):
                    repoviewer = self.parent().window()
                dlg = dlgclass(self.repo, filename, repoviewer=repoviewer)
                dlgdict[filename] = dlg
                ufname = hglib.tounicode(filename)
                dlg.setWindowTitle(_('Hg file log viewer - %s') % ufname)
                dlg.setWindowIcon(qtlib.geticon('hg-log'))
            dlg = dlgdict[filename]
            dlg.goto(self.ctx.rev())
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

    def opensubrepo(self):
        path = os.path.join(self.repo.root, self._currentfile)
        if os.path.isdir(path):
            self.linkActivated.emit(u'subrepo:'+hglib.tounicode(path))
        else:
            QMessageBox.warning(self,
                _("Cannot open subrepository"),
                _("The selected subrepository does not exist on the working directory"))

    def explore(self):
        root = self.repo.wjoin(self._currentfile)
        if os.path.isdir(root):
            qtlib.openlocalurl(root)

    def terminal(self):
        root = self.repo.wjoin(self._currentfile)
        if os.path.isdir(root):
            qtlib.openshell(root, self._currentfile)

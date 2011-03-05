# manifestdialog.py - Dialog and widget for TortoiseHg manifest view
#
# Copyright (C) 2003-2010 LOGILAB S.A. <http://www.logilab.fr/>
# Copyright (C) 2010 Yuya Nishihara <yuya@tcha.org>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.

import os

from mercurial import util

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.util import paths, hglib

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, qscilib, annotate, status, thgrepo
from tortoisehg.hgqt import visdiff, wctxactions, revert
from tortoisehg.hgqt.filedialogs import FileLogDialog, FileDiffDialog 
from tortoisehg.hgqt.manifestmodel import ManifestModel

class ManifestDialog(QMainWindow):
    """
    Qt4 dialog to display all files of a repo at a given revision
    """

    finished = pyqtSignal(int)

    def __init__(self, repo, rev=None, parent=None):
        QMainWindow.__init__(self, parent)
        self._repo = repo
        self.setWindowIcon(qtlib.geticon('hg-annotate'))
        self.resize(400, 300)

        self._manifest_widget = ManifestWidget(repo, rev)
        self._manifest_widget.revChanged.connect(self._updatewindowtitle)
        self._manifest_widget.pathChanged.connect(self._updatewindowtitle)
        self._manifest_widget.editSelected.connect(self._openInEditor)
        self._manifest_widget.grepRequested.connect(self._openSearchWidget)
        self.setCentralWidget(self._manifest_widget)
        self.addToolBar(self._manifest_widget.toolbar)

        self._searchbar = qscilib.SearchToolBar()
        connectsearchbar(self._manifest_widget, self._searchbar)
        self.addToolBar(self._searchbar)
        QShortcut(QKeySequence.Find, self,
            lambda: self._searchbar.setFocus(Qt.OtherFocusReason))

        self.setStatusBar(QStatusBar())
        self._manifest_widget.revisionHint.connect(self.statusBar().showMessage)

        self._readsettings()
        self._updatewindowtitle()

    @pyqtSlot()
    def _updatewindowtitle(self):
        self.setWindowTitle(_('Manifest %s@%s') % (
            self._manifest_widget.path, self._manifest_widget.rev))

    def closeEvent(self, event):
        self._writesettings()
        super(ManifestDialog, self).closeEvent(event)
        self.finished.emit(0)  # mimic QDialog exit

    def _readsettings(self):
        s = QSettings()
        self.restoreGeometry(s.value('manifest/geom').toByteArray())
        self._manifest_widget.loadSettings(s, 'manifest')

    def _writesettings(self):
        s = QSettings()
        s.setValue('manifest/geom', self.saveGeometry())
        self._manifest_widget.saveSettings(s, 'manifest')

    def setSource(self, path, rev, line=None):
        self._manifest_widget.setSource(path, rev, line)

    def setSearchPattern(self, text):
        """Set search pattern [unicode]"""
        self._searchbar.setPattern(text)

    @pyqtSlot(unicode, dict)
    def _openSearchWidget(self, pattern, opts):
        opts = dict((str(k), str(v)) for k, v in opts.iteritems())
        from tortoisehg.hgqt import run
        run.grep(self._repo.ui, hglib.fromunicode(pattern), **opts)

    @pyqtSlot(unicode, object, int)
    def _openInEditor(self, path, rev, line):
        """Open editor to show the specified file"""
        _openineditor(self._repo, path, rev, line,
                      pattern=self._searchbar.pattern(), parent=self)

class ManifestWidget(QWidget):
    """Display file tree and contents at the specified revision"""

    revChanged = pyqtSignal(object)
    """Emitted (rev) when the current revision changed"""

    pathChanged = pyqtSignal(unicode)
    """Emitted (path) when the current file path changed"""

    revisionHint = pyqtSignal(unicode)
    """Emitted when to show revision summary as a hint"""

    searchRequested = pyqtSignal(unicode)
    """Emitted (pattern) when user request to search content"""

    editSelected = pyqtSignal(unicode, object, int)
    """Emitted (path, rev, line) when user requests to open editor"""

    grepRequested = pyqtSignal(unicode, dict)
    """Emitted (pattern, opts) when user request to search changelog"""

    contextmenu = None

    def __init__(self, repo, rev=None, parent=None):
        super(ManifestWidget, self).__init__(parent)
        self._repo = repo
        self._rev = rev
        self._diff_dialogs = {}
        self._nav_dialogs = {}

        self._initwidget()
        self._initactions()
        self._setupmodel()
        self._treeview.setCurrentIndex(self._treemodel.index(0, 0))

        self.setRev(self._rev)

    def _initwidget(self):
        self.setLayout(QVBoxLayout())
        self._splitter = QSplitter()
        self.layout().addWidget(self._splitter)
        self.layout().setContentsMargins(2, 2, 2, 2)

        navlayout = QVBoxLayout(spacing=0)
        navlayout.setContentsMargins(0, 0, 0, 0)
        self._toolbar = QToolBar()
        self._toolbar.setIconSize(QSize(16,16))
        self._treeview = QTreeView(self, headerHidden=True, dragEnabled=True)
        self._treeview.setContextMenuPolicy(Qt.CustomContextMenu)
        self._treeview.customContextMenuRequested.connect(self.menuRequest)
        navlayout.addWidget(self._toolbar)
        navlayout.addWidget(self._treeview)
        navlayoutw = QWidget()
        navlayoutw.setLayout(navlayout)

        self._contentview = QStackedWidget()
        self._splitter.addWidget(navlayoutw)
        self._splitter.addWidget(self._contentview)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 3)

        self._nullcontent = QWidget()
        self._contentview.addWidget(self._nullcontent)
        self._fileview = annotate.AnnotateView(self._repo)
        self._fileview.sourceChanged.connect(self.setSource)
        self._contentview.addWidget(self._fileview)
        for name in ('revisionHint', 'searchRequested', 'editSelected',
                     'grepRequested'):
            getattr(self._fileview, name).connect(getattr(self, name))

    def loadSettings(self, qs, prefix):
        prefix += '/manifest'
        self._fileview.loadSettings(qs, prefix+'/fileview')
        self._splitter.restoreState(qs.value(prefix+'/splitter').toByteArray())

    def saveSettings(self, qs, prefix):
        prefix += '/manifest'
        self._fileview.saveSettings(qs, prefix+'/fileview')
        qs.setValue(prefix+'/splitter', self._splitter.saveState())

    def _initactions(self):
        self._statusfilter = _StatusFilterButton(statustext='MAC')
        self._toolbar.addWidget(self._statusfilter)

        self._action_annotate_mode = QAction(_('Annotate'), self, checkable=True)
        self._action_annotate_mode.toggled.connect(
            self._fileview.setAnnotationEnabled)
        self._action_annotate_mode.setEnabled(self.rev is not None)
        self._toolbar.addAction(self._action_annotate_mode)

        if hasattr(self, '_searchbar'):
            self._action_find = self._searchbar.toggleViewAction()
            self._action_find.setIcon(qtlib.geticon('edit-find'))
            self._action_find.setShortcut(QKeySequence.Find)
            self._toolbar.addAction(self._action_find)

        self._actions = {}
        for name, desc, icon, key, tip, cb in [
            ('navigate', _('File history'), 'hg-log', 'Shift+Return',
              _('Show the history of the selected file'), self.navigate),
            ('diffnavigate', _('Compare file revisions'), 'compare-files', None,
              _('Compare revisions of the selected file'), self.diffNavigate),
            ('diff', _('Visual Diff'), 'visualdiff', 'Ctrl+D',
              _('View file changes in external diff tool'), self.vdiff),
            ('ldiff', _('Visual Diff to Local'), 'ldiff', 'Shift+Ctrl+D',
              _('View changes to current in external diff tool'),
              self.vdifflocal),
            ('edit', _('View at Revision'), 'view-at-revision', 'Alt+Ctrl+E',
              _('View file as it appeared at this revision'), self.editfile),
            ('ledit', _('Edit Local'), 'edit-file', 'Shift+Ctrl+E',
              _('Edit current file in working copy'), self.editlocal),
            ('revert', _('Revert to Revision'), 'hg-revert', 'Alt+Ctrl+T',
              _('Revert file(s) to contents at this revision'),
              self.revertfile),
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
            self.addAction(act)

    def navigate(self, filename=None):
        self._navigate(filename, FileLogDialog, self._nav_dialogs)

    def diffNavigate(self, filename=None):
        self._navigate(filename, FileDiffDialog, self._diff_dialogs)

    def vdiff(self):
        if self.path is None:
            return
        pats = [self.path]
        opts = {'change':self.rev}
        dlg = visdiff.visualdiff(self._repo.ui, self._repo, pats, opts)
        if dlg:
            dlg.exec_()

    def vdifflocal(self):
        if self.path is None:
            return
        pats = [self.path]
        assert type(self.rev) is int
        opts = {'rev':['rev(%d)' % self.rev]}
        dlg = visdiff.visualdiff(self._repo.ui, self._repo, pats, opts)
        if dlg:
            dlg.exec_()

    def editfile(self):
        if self.path is None:
            return
        if self.rev is None:
            files = [self._repo.wjoin(self.path)]
            wctxactions.edit(self, self._repo.ui, self._repo, files)
        else:
            base, _ = visdiff.snapshot(self._repo, [self.path],
                                       self._repo[self.rev])
            files = [os.path.join(base, self.path)]
            wctxactions.edit(self, self._repo.ui, self._repo, files)

    def editlocal(self):
        if self.path is None:
            return
        path = self._repo.wjoin(self.path)
        wctxactions.edit(self, self._repo.ui, self._repo, [path])

    def revertfile(self):
        if self.path is None:
            return
        if self.rev is None:
            rev = self._repo['.'].rev()
        dlg = revert.RevertDialog(self._repo, self.path, self.rev, self)
        dlg.exec_()

    def _navigate(self, filename, dlgclass, dlgdict):
        if not filename:
            filename = self.path
        if filename not in dlgdict:
            dlg = dlgclass(self._repo, filename,
                            repoviewer=self.window())
            dlgdict[filename] = dlg
            ufname = hglib.tounicode(filename)
            dlg.setWindowTitle(_('Hg file log viewer - %s') % ufname)
        dlg = dlgdict[filename]
        dlg.goto(self.rev)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def menuRequest(self, point):
        point = self.mapToGlobal(point)
        if not self.contextmenu:
            self.contextmenu = QMenu(self)
            for act in ['diff', 'ldiff', 'edit', 'ledit', 'revert',
                        'navigate', 'diffnavigate']:
                if act:
                    self.contextmenu.addAction(self._actions[act])
                else:
                    self.contextmenu.addSeparator()
        self.contextmenu.exec_(point)

    @property
    def toolbar(self):
        """Return toolbar for manifest widget"""
        return self._toolbar

    @pyqtSlot(unicode, bool, bool, bool)
    def find(self, pattern, icase=False, wrap=False, forward=True):
        return self._fileview.find(pattern, icase, wrap, forward)

    @pyqtSlot(unicode, bool)
    def highlightText(self, pattern, icase=False):
        self._fileview.highlightText(pattern, icase)

    def _setupmodel(self):
        self._treemodel = ManifestModel(self._repo, self._rev,
                                        statusfilter=self._statusfilter.status(),
                                        parent=self)
        oldmodel = self._treeview.model()
        oldselmodel = self._treeview.selectionModel()
        self._treeview.setModel(self._treemodel)
        if oldmodel:
            oldmodel.deleteLater()
        if oldselmodel:
            oldselmodel.deleteLater()

        selmodel = self._treeview.selectionModel()
        selmodel.currentChanged.connect(self._updatecontent)
        selmodel.currentChanged.connect(self._emitPathChanged)

        self._statusfilter.statusChanged.connect(self._treemodel.setStatusFilter)
        self._statusfilter.statusChanged.connect(self._autoexpandtree)
        self._autoexpandtree()

    @pyqtSlot()
    def _autoexpandtree(self):
        """expand file tree if the number of the items isn't large"""
        if 'C' not in self._statusfilter.status():
            self._treeview.expandAll()

    def reload(self):
        # TODO
        pass

    def setRepo(self, repo):
        self._repo = repo
        #self._fileview.setRepo(repo)
        self._fileview.repo = repo
        if len(repo) <= self._rev:
            self._rev = len(repo)-1
        self._setupmodel()

    @property
    def rev(self):
        """Return current revision"""
        return self._rev

    @pyqtSlot(object)
    def setRev(self, rev):
        """Change revision to show"""
        self.setSource(self.path, rev)
        real = type(rev) is int
        self._actions['ldiff'].setEnabled(real)
        for act in ['diff', 'edit']:
            self._actions[act].setEnabled(real or rev is None)
        self._actions['revert'].setEnabled(real)

    @pyqtSlot(unicode, object)
    @pyqtSlot(unicode, object, int)
    def setSource(self, path, rev, line=None):
        """Change path and revision to show at once"""
        revchanged = self._rev != rev
        if revchanged:
            self._rev = rev
            self._setupmodel()
        self.setPath(path)
        if self.path in self._repo[rev]:
            self._fileview.setSource(path, rev, line)
        if revchanged:
            # annotate working copy is not supported
            self._action_annotate_mode.setEnabled(rev is not None)
            self.revChanged.emit(rev)

    @property
    def path(self):
        """Return currently selected path"""
        return self._treemodel.filePath(self._treeview.currentIndex())

    @pyqtSlot(unicode)
    def setPath(self, path):
        """Change path to show"""
        self._treeview.setCurrentIndex(self._treemodel.indexFromPath(path))

    @pyqtSlot()
    def _updatecontent(self):
        if hglib.fromunicode(self.path) not in self._repo[self._rev]:
            self._contentview.setCurrentWidget(self._nullcontent)
            return

        self._contentview.setCurrentWidget(self._fileview)
        self._fileview.setSource(self.path, self._rev)

    @pyqtSlot()
    def _emitPathChanged(self):
        self.pathChanged.emit(self.path)

# TODO: share this menu with status widget?
class _StatusFilterButton(QToolButton):
    """Button with drop-down menu for status filter"""
    statusChanged = pyqtSignal(str)

    _TYPES = 'MARC'

    def __init__(self, statustext=_TYPES, parent=None, **kwargs):
        if 'text' not in kwargs:
            kwargs['text'] = _('Status')
        super(_StatusFilterButton, self).__init__(
            parent, popupMode=QToolButton.InstantPopup,
            icon=qtlib.geticon('hg-status'),
            toolButtonStyle=Qt.ToolButtonTextBesideIcon, **kwargs)

        self._initactions(statustext)

    def _initactions(self, text):
        self._actions = {}
        menu = QMenu(self)
        for c in self._TYPES:
            st = status.statusTypes[c]
            a = menu.addAction('%s %s' % (c, st.name))
            a.setCheckable(True)
            a.setChecked(c in text)
            a.toggled.connect(self._update)
            self._actions[c] = a
        self.setMenu(menu)

    @pyqtSlot()
    def _update(self):
        self.statusChanged.emit(self.status())

    def status(self):
        """Return the text for status filter"""
        return ''.join(c for c in self._TYPES
                       if self._actions[c].isChecked())

    @pyqtSlot(str)
    def setStatus(self, text):
        """Set the status text"""
        assert util.all(c in self._TYPES for c in text)
        for c in self._TYPES:
            self._actions[c].setChecked(c in text)

class ManifestTaskWidget(ManifestWidget):
    """Manifest widget designed for task tab"""

    def __init__(self, repo, rev, parent):
        super(ManifestTaskWidget, self).__init__(repo, rev, parent)
        self.editSelected.connect(self._openInEditor)

    @util.propertycache
    def _searchbar(self):
        searchbar = qscilib.SearchToolBar(hidable=True)
        searchbar.hide()
        self.layout().addWidget(searchbar)
        connectsearchbar(self, searchbar)
        return searchbar

    @pyqtSlot(unicode, object, int)
    def _openInEditor(self, path, rev, line):
        """Open editor to show the specified file"""
        _openineditor(self._repo, path, rev, line,
                      pattern=self._searchbar.pattern(), parent=self)

def connectsearchbar(manifestwidget, searchbar):
    """Connect searchbar to manifest widget"""
    searchbar.conditionChanged.connect(manifestwidget.highlightText)
    searchbar.searchRequested.connect(manifestwidget.find)
    manifestwidget.searchRequested.connect(searchbar.search)

def _openineditor(repo, path, rev, line=None, pattern=None, parent=None):
    """Open editor to show the specified file [unicode]"""
    path = hglib.fromunicode(path)
    pattern = hglib.fromunicode(pattern)
    base = visdiff.snapshot(repo, [path], repo[rev])[0]
    files = [os.path.join(base, path)]
    wctxactions.edit(parent, repo.ui, repo, files, line, pattern)


def run(ui, *pats, **opts):
    repo = opts.get('repo') or thgrepo.repository(ui, paths.find_root())
    dlg = ManifestDialog(repo, opts.get('rev'))

    # set initial state after dialog visible
    def init():
        try:
            path = hglib.canonpaths(pats)[0]
            line = opts.get('line') and int(opts['line']) or None
            dlg.setSource(path, opts.get('rev'), line)
        except IndexError:
            pass
        dlg.setSearchPattern(hglib.tounicode(opts.get('pattern')) or '')
    QTimer.singleShot(0, init)

    return dlg

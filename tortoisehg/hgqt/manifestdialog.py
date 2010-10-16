# -*- coding: utf-8 -*-
# Copyright (c) 2003-2010 LOGILAB S.A. (Paris, FRANCE).
# http://www.logilab.fr/ -- mailto:contact@logilab.fr
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
"""
Qt4 dialogs to display hg revisions of a file
"""
import os

from mercurial import util

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.util import paths, hglib

from tortoisehg.hgqt import qtlib, qscilib, annotate, status, thgrepo, \
                            visdiff, wctxactions
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.manifestmodel import ManifestModel

class ManifestDialog(QMainWindow):
    """
    Qt4 dialog to display all files of a repo at a given revision
    """
    def __init__(self, ui, repo, rev=None, parent=None):
        QMainWindow.__init__(self, parent)
        self._repo = repo
        self.resize(400, 300)

        self._manifest_widget = ManifestWidget(ui, repo, rev)
        self._manifest_widget.revchanged.connect(self._updatewindowtitle)
        self._manifest_widget.editSelected.connect(self._openInEditor)
        self._manifest_widget.grepRequested.connect(self._openSearchWidget)
        self.setCentralWidget(self._manifest_widget)
        self.addToolBar(self._manifest_widget.toolbar)

        self._searchbar = qscilib.SearchToolBar()
        connectsearchbar(self._manifest_widget, self._searchbar)
        self.addToolBar(self._searchbar)

        self.setStatusBar(QStatusBar())
        self._manifest_widget.revisionHint.connect(self.statusBar().showMessage)

        self._readsettings()
        self._updatewindowtitle()

    @pyqtSlot()
    def _updatewindowtitle(self):
        self.setWindowTitle(_('Hg manifest viewer - %s:%s') % (
            self._repo.root, self._manifest_widget.rev))

    def closeEvent(self, event):
        self._writesettings()
        super(ManifestDialog, self).closeEvent(event)

    def _readsettings(self):
        s = QSettings()
        self.restoreGeometry(s.value('manifest/geom').toByteArray())
        # TODO: don't call deeply
        self._manifest_widget._splitter.restoreState(
            s.value('manifest/splitter').toByteArray())

    def _writesettings(self):
        s = QSettings()
        s.setValue('manifest/geom', self.saveGeometry())
        # TODO: don't call deeply
        s.setValue('manifest/splitter',
                   self._manifest_widget._splitter.saveState())

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
    revchanged = pyqtSignal(object)  # emit when curret revision changed

    revisionHint = pyqtSignal(unicode)
    """Emitted when to show revision summary as a hint"""

    searchRequested = pyqtSignal(unicode)
    """Emitted (pattern) when user request to search content"""

    editSelected = pyqtSignal(unicode, object, int)
    """Emitted (path, rev, line) when user requests to open editor"""

    grepRequested = pyqtSignal(unicode, dict)
    """Emitted (pattern, opts) when user request to search changelog"""

    def __init__(self, ui, repo, rev=None, parent=None):
        super(ManifestWidget, self).__init__(parent)
        self._ui = ui
        self._repo = repo
        self._rev = rev

        self._initwidget()
        self._initactions()
        self._setupmodel()
        self._treeview.setCurrentIndex(self._treemodel.index(0, 0))

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

    def _initactions(self):
        self._statusfilter = _StatusFilterButton(text='MAC')
        self._toolbar.addWidget(self._statusfilter)

        self._action_annotate_mode = QAction(_('Annotate'), self, checkable=True)
        self._action_annotate_mode.toggled.connect(
            self._fileview.setAnnotationEnabled)
        self._toolbar.addAction(self._action_annotate_mode)

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
                                        statusfilter=self._statusfilter.text,
                                        parent=self)
        self._treeview.setModel(self._treemodel)
        self._treeview.selectionModel().currentChanged.connect(self._updatecontent)
        self._statusfilter.textChanged.connect(self._treemodel.setStatusFilter)
        self._statusfilter.textChanged.connect(self._autoexpandtree)
        self._autoexpandtree()

    @pyqtSlot()
    def _autoexpandtree(self):
        """expand file tree if the number of the items isn't large"""
        if 'C' not in self._statusfilter.text:
            self._treeview.expandAll()

    def reload(self):
        # TODO
        pass

    @property
    def rev(self):
        """Return current revision"""
        return self._rev

    @pyqtSlot(object)
    def setrev(self, rev):
        """Change revision to show"""
        self.setSource(self.path, rev)

    @pyqtSlot(unicode, object)
    @pyqtSlot(unicode, object, int)
    def setSource(self, path, rev, line=None):
        """Change path and revision to show at once"""
        revchanged = self._rev != rev
        if revchanged:
            self._rev = rev
            self._setupmodel()
        self.setpath(path)
        if self.path in self._repo[rev]:
            self._fileview.setSource(path, rev, line)
        if revchanged:
            self.revchanged.emit(rev)

    @property
    def path(self):
        """Return currently selected path"""
        return self._treemodel.filePath(self._treeview.currentIndex())

    @pyqtSlot(unicode)
    def setpath(self, path):
        """Change path to show"""
        self._treeview.setCurrentIndex(self._treemodel.indexFromPath(path))

    @pyqtSlot()
    def _updatecontent(self):
        if hglib.fromunicode(self.path) not in self._repo[self._rev]:
            self._contentview.setCurrentWidget(self._nullcontent)
            return

        self._contentview.setCurrentWidget(self._fileview)
        self._fileview.setSource(self.path, self._rev)

# TODO: share this menu with status widget?
class _StatusFilterButton(QToolButton):
    """Button with drop-down menu for status filter"""
    textChanged = pyqtSignal(str)

    _TYPES = 'MARC'

    def __init__(self, text=_TYPES, parent=None):
        super(_StatusFilterButton, self).__init__(
            parent, popupMode=QToolButton.InstantPopup,
            icon=qtlib.geticon('status'),
            toolButtonStyle=Qt.ToolButtonTextBesideIcon)

        self._initactions(text=text)
        self._setText(self.text)

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
        self._setText(self.text)
        self.textChanged.emit(self.text)

    @property
    def text(self):
        """Return the text for status filter"""
        return ''.join(c for c in self._TYPES
                       if self._actions[c].isChecked())

    @pyqtSlot(str)
    def setText(self, text):
        """Set the status text"""
        assert util.all(c in self._TYPES for c in text)
        for c in self._TYPES:
            self._actions[c].setChecked(c in text)

    def _setText(self, text):
        super(_StatusFilterButton, self).setText(text)

class ManifestTaskWidget(ManifestWidget):
    """Manifest widget designed for task tab"""

    def __init__(self, ui, repo, rev=None, parent=None):
        super(ManifestTaskWidget, self).__init__(ui, repo, rev, parent)
        self.editSelected.connect(self._openInEditor)

    @pyqtSlot()
    def showSearchBar(self):
        self._searchbar.show()
        self._searchbar.setFocus()

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
    return ManifestDialog(ui, repo, opts.get('rev'))

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

from mercurial import util

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qsci import QsciScintilla

from tortoisehg.util import paths
from tortoisehg.util.hglib import tounicode

from tortoisehg.hgqt import qtlib, annotate, status, thgrepo
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.manifestmodel import ManifestModel
from tortoisehg.hgqt.lexers import get_lexer

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
        self.setCentralWidget(self._manifest_widget)
        self.addToolBar(self._manifest_widget.toolbar)

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

class _FileTextView(QsciScintilla):
    def __init__(self, ui, repo, parent=None):
        super(_FileTextView, self).__init__(parent)
        self._ui = ui
        self._repo = repo

        self.setMarginLineNumbers(1, True)
        self.setMarginWidth(1, '000')
        self.setReadOnly(True)
        self.setFont(qtlib.getfont('fontlog').font())
        self.setUtf8(True)
        self.SendScintilla(QsciScintilla.SCI_SETSELEOLFILLED, True)

        self.setTabWidth(repo.tabwidth)
        if repo.wsvisible == 'Visible':
            self.setWhitespaceVisibility(QsciScintilla.WsVisible)
        elif repo.wsvisible == 'VisibleAfterIndent':
            self.setWhitespaceVisibility(QsciScintilla.WsVisibleAfterIndent)
        else:
            self.setWhitespaceVisibility(QsciScintilla.WsInvisible)

    @pyqtSlot(unicode, object)
    def setsource(self, path, rev):
        fc = self._repo.changectx(rev).filectx(path)
        if fc.size() > self._repo.maxdiff:
            data = _("file too big")
        else:
            # return the whole file
            data = fc.data()
            if util.binary(data):
                data = _("binary file")
            else:
                data = tounicode(data)
                lexer = get_lexer(path, data)
                if lexer:
                    self.setLexer(lexer)
        nlines = data.count('\n')
        self.setMarginWidth(1, str(nlines)+'00')
        self.setText(data)

class _FileAnnotateView(annotate.AnnotateView):
    def __init__(self, ui, repo, parent=None):
        super(_FileAnnotateView, self).__init__(repo, parent)

    @pyqtSlot(unicode, object)
    def setsource(self, path, rev):
        self.setSource(path, rev)

class _NullView(QWidget):
    """empty widget for content view"""
    def __init__(self, parent=None):
        super(_NullView, self).__init__(parent)

    @pyqtSlot(unicode, object)
    def setsource(self, path, rev):
        pass

class ManifestWidget(QWidget):
    """Display file tree and contents at the specified revision"""
    revchanged = pyqtSignal(object)  # emit when curret revision changed

    def __init__(self, ui, repo, rev=None, parent=None):
        super(ManifestWidget, self).__init__(parent)
        self._ui = ui
        self._repo = repo
        self._rev = rev

        self._initwidget()
        self._initactions()
        self._setupmodel()
        self.setfileview('cat')
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
        self._treeview = QTreeView(headerHidden=True, dragEnabled=True)
        navlayout.addWidget(self._toolbar)
        navlayout.addWidget(self._treeview)
        navlayoutw = QWidget()
        navlayoutw.setLayout(navlayout)

        self._contentview = QStackedWidget()
        self._splitter.addWidget(navlayoutw)
        self._splitter.addWidget(self._contentview)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 3)

        self._nullcontent = _NullView()
        self._contentview.addWidget(self._nullcontent)
        self._filewidgets = {
            'cat': _FileTextView(self._ui, self._repo),
            'annotate': _FileAnnotateView(self._ui, self._repo),
            }
        for w in self._filewidgets.itervalues():
            self._contentview.addWidget(w)
        # TODO: abstract way to connect this kind of signals
        self._filewidgets['annotate'].revSelected.connect(
            lambda a: self.setsource(path=a[0], rev=a[1]))
        self._contentview.currentChanged.connect(
            lambda: self._fileselected(self._treeview.currentIndex()))

    def _initactions(self):
        self._statusfilter = _StatusFilterButton(text='MAC')
        self._toolbar.addWidget(self._statusfilter)

        self._action_annotate_mode = QAction(_('Annotate'), self, checkable=True)
        self._action_annotate_mode.toggled.connect(
            lambda checked: self.setfileview(checked and 'annotate' or 'cat'))
        self._toolbar.addAction(self._action_annotate_mode)

    @property
    def toolbar(self):
        """Return toolbar for manifest widget"""
        return self._toolbar

    def _setupmodel(self):
        self._treemodel = ManifestModel(self._repo, self._rev,
                                        statusfilter=self._statusfilter.text)
        self._treeview.setModel(self._treemodel)
        self._treeview.selectionModel().currentChanged.connect(self._fileselected)
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
        self.setsource(self.path, rev)

    @pyqtSlot(unicode, object)
    def setsource(self, path, rev):
        """Change path and revision to show at once"""
        if self._rev != rev:
            self._rev = rev
            self._setupmodel()
            self.revchanged.emit(rev)
        self.setpath(path)

    @property
    def path(self):
        """Return currently selected path"""
        return self._treemodel.filePath(self._treeview.currentIndex())

    @pyqtSlot(unicode)
    def setpath(self, path):
        """Change path to show"""
        self._treeview.setCurrentIndex(self._treemodel.indexFromPath(path))

    # disabled due to the issue of PyQt 4.7.4.
    # see http://thread.gmane.org/gmane.comp.python.pyqt-pykde/19836
    #@pyqtSlot(QModelIndex)
    def _fileselected(self, index):
        path = self._treemodel.filePath(index)
        if path not in self._repo[self._rev]:
            self._contentview.setCurrentWidget(self._nullcontent)
            return

        self._contentview.setCurrentWidget(self._curfileview)
        self._contentview.currentWidget().setsource(path, self._rev)

    @pyqtSlot(unicode)
    def setfileview(self, mode):
        """Change widget for file content view"""
        assert mode in self._filewidgets
        self._curfileview = self._filewidgets[mode]
        self._contentview.setCurrentWidget(self._curfileview)

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


def run(ui, *pats, **opts):
    repo = opts.get('repo') or thgrepo.repository(ui, paths.find_root())
    return ManifestDialog(ui, repo, opts.get('rev'))

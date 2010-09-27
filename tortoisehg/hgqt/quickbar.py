# Copyright (c) 2009-2010 LOGILAB S.A. (Paris, FRANCE).
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
Qt4 QToolBar-based class for quick bars XXX
"""

from mercurial import util

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.qtlib import geticon
from tortoisehg.hgqt import fileview

class QuickBar(QToolBar):
    def __init__(self, name, key, desc=None, parent=None):
        QToolBar.__init__(self, name, parent)
        self.original_parent = parent
        self.setIconSize(QSize(16,16))
        self.setFloatable(False)
        self.setMovable(False)
        self.setAllowedAreas(Qt.BottomToolBarArea)
        self.createActions(key, desc)
        self.createContent()
        self.setVisible(False)

    def createActions(self, openkey, desc):
        openact = QAction(desc or 'Open', self)
        openact.setCheckable(True)
        openact.setChecked(False)
        openact.setShortcut(QKeySequence(openkey))
        openact.triggered.connect(lambda: self.setVisible(True))

        closeact = QAction('Close', self)
        closeact.setIcon(geticon('close'))
        closeact.setShortcut(Qt.Key_Escape)
        closeact.triggered.connect(lambda: self.setVisible(False))

        self._actions = {'open': openact, 'close': closeact}

    def createContent(self):
        self.addAction(self._actions['close'])
        self.parent().addAction(self._actions['open'])

    def hide(self):
        self.setVisible(False)

    def cancel(self):
        self.hide()

class FindQuickBar(QuickBar):
    find = pyqtSignal(QString)
    findnext = pyqtSignal(QString)
    cancel = pyqtSignal()

    def __init__(self, parent):
        QuickBar.__init__(self, "Find", QKeySequence.Find, "Find", parent)
        self.currenttext = ''

    def createActions(self, openkey, desc):
        QuickBar.createActions(self, openkey, desc)
        self._actions['findnext'] = QAction("Find next", self)
        self._actions['findnext'].setShortcut(QKeySequence.FindNext)
        self._actions['findnext'].triggered.connect(self.findText)
        self._actions['cancel'] = QAction("Cancel", self)
        self._actions['cancel'].triggered.connect(self.on_cancel)

    def findText(self, *args):
        text = unicode(self.entry.text())
        if text == self.currenttext:
            self.findnext.emit(text)
        else:
            self.currenttext = text
            self.find.emit(text)

    def on_cancel(self):
        self.cancel.emit()

    def setCancelEnabled(self, enabled=True):
        self._actions['cancel'].setEnabled(enabled)
        self._actions['findnext'].setEnabled(not enabled)

    def createContent(self):
        QuickBar.createContent(self)
        self.compl_model = QStringListModel()
        self.completer = QCompleter(self.compl_model, self)
        self.entry = QLineEdit(self)
        self.entry.setCompleter(self.completer)
        self.addWidget(self.entry)
        self.addAction(self._actions['findnext'])
        self.addAction(self._actions['cancel'])
        self.setCancelEnabled(False)
        self.entry.returnPressed.connect(self.findText)
        self.entry.textEdited.connect(self.findText)

    def setVisible(self, visible=True):
        QuickBar.setVisible(self, visible)
        if visible:
            self.entry.setFocus()
            self.entry.selectAll()

    def text(self):
        if self.isVisible() and self.currenttext.strip():
            return self.currenttext

    def __del__(self):
        # prevent a warning in the console:
        # QObject::startTimer: QTimer can only be used with threads started with QThread
        self.entry.setCompleter(None)

class FindInGraphlogQuickBar(FindQuickBar):
    revisionSelected = pyqtSignal(int)
    fileSelected = pyqtSignal(str)
    showMessage = pyqtSignal(unicode)

    def __init__(self, parent):
        FindQuickBar.__init__(self, parent)
        self._findinfile_iter = None
        self._findinlog_iter = None
        self._fileview = None
        self._filter_files = None
        self._mode = 'diff'
        self.find.connect(self.on_find_text_changed)
        self.findnext.connect(self.on_findnext)
        self.cancel.connect(self.on_cancelsearch)

    def setFilterFiles(self, files):
        self._filter_files = files

    def setModel(self, model):
        self._model = model

    def setMode(self, mode):
        assert mode in ('diff', 'file')
        self._mode = mode

    def attachFileView(self, fileview):
        self._fileview = fileview

    def find_in_graphlog(self, fromrev, fromfile=None):
        """
        Find text in the whole repo from rev 'fromrev', from file
        'fromfile' (if given) *excluded*
        """
        text = unicode(self.entry.text())
        graph = self._model.graph
        idx = graph.index(fromrev)
        for node in graph[idx:]:
            rev = node.rev
            ctx = self._model.repo.changectx(rev)
            if text in ctx.description():
                yield rev, None
            pos = 0
            files = ctx.files()
            if self._filter_files:
                files = [x for x in files if x in self._filter_files]
            if fromfile is not None and fromfile in files:
                files = files[files.index(fromfile)+1:]
                fromfile = None
            for wfile in files:
                fd = fileview.FileData(ctx, None, wfile)
                if not fd.isValid():
                    continue
                if self._mode == 'diff' and fd.diff:
                    data = fd.diff
                else:
                    data = fd.contents
                if data and text in data:
                    yield rev, wfile
                else:
                    yield None

    def on_cancel(self):
        if self._actions['cancel'].isEnabled():
            self.cancel.emit()
        else:
            self.hide()

    def on_cancelsearch(self, *args):
        self._findinlog_iter = None
        self.setCancelEnabled(False)
        self.showMessage.emit(_('Search cancelled!'))

    def on_findnext(self):
        """
        callback called by 'Find' quicktoolbar (on findnext signal)
        """
        if self._findinfile_iter is not None:
            for pos in self._findinfile_iter:
                # just highlight next found text in descview
                return
            # no more found text in currently displayed file
            self._findinfile_iter = None

        if self._findinlog_iter is None and self._fileview:
            # start searching in the graphlog from current position
            rev = self._fileview.rev()
            filename = self._fileview.filename()
            self._findinlog_iter = self.find_in_graphlog(rev, filename)

        self.setCancelEnabled(True)
        self.find_next_in_log()

    def find_next_in_log(self, step=0):
        """
        to be called from 'on_find' callback (or recursively). Try to
        find the next occurrence of searched text (as a 'background'
        process, so the GUI is not frozen, and as a cancellable task).
        """
        if self._findinlog_iter is None:
            # search has been cancelled
            return
        for next_find in self._findinlog_iter:
            if next_find is None: # not yet found, let's animate a bit the GUI
                if (step % 20) == 0:
                    self.showMessage.emit(_('Searching')+'.'*(step/20))
                step += 1
                QTimer.singleShot(0, lambda: self.find_next_in_log(step % 80))
            else:
                self.showMessage.emit('')
                self.setCancelEnabled(False)

                rev, filename = next_find
                if rev is not None and filename is not None:
                    self.revisionSelected.emit(rev)
                    text = unicode(self.entry.text())
                    self.fileSelected.emit(filename)
                if self._fileview:
                    self._findinfile_iter = self._fileview.searchString(text)
                    self.on_findnext()
            return
        self.showMessage.emit(_('No more matches found in repository'))
        self.setCancelEnabled(False)
        self._findinlog_iter = None

    def on_find_text_changed(self, newtext):
        """
        callback called by 'Find' quicktoolbar (on find signal)
        """
        newtext = unicode(newtext)
        self._findinlog_iter = None
        self._findinfile_iter = None
        if self._fileview:
            self._findinfile_iter = self._fileview.searchString(newtext)
        if newtext.strip():
            if self._findinfile_iter is None:
                self.showMessage.emit(
                          _('Search string not found in current diff. '
                          'Hit "Find next" button to start searching '
                          'in the repository'))
            else:
                self.on_findnext()

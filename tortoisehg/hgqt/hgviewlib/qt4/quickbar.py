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

from PyQt4 import QtCore, QtGui

from hgviewlib.util import Curry
from hgviewlib.qt4 import icon as geticon

Qt = QtCore.Qt
connect = QtCore.QObject.connect
SIGNAL = QtCore.SIGNAL


class QuickBar(QtGui.QToolBar):
    def __init__(self, name, key, desc=None, parent=None):
        self.original_parent = parent
        # used to remember who had the focus before bar steel it
        self._focusw = None
        QtGui.QToolBar.__init__(self, name, parent)
        self.setIconSize(QtCore.QSize(16,16))
        self.setFloatable(False)
        self.setMovable(False)
        self.setAllowedAreas(Qt.BottomToolBarArea)
        self.createActions(key, desc)
        self.createContent()
        if parent:
            parent = parent.window()            
        if isinstance(parent, QtGui.QMainWindow):
            parent.addToolBar(Qt.BottomToolBarArea, self)
        self.setVisible(False)
        
    def createActions(self, openkey, desc):
        parent = self.parentWidget()
        self._actions = {}

        if not desc:
            desc = "Open"
        openact = QtGui.QAction(desc, parent)
        openact.setCheckable(True)        
        openact.setChecked(False)
        openact.setShortcut(QtGui.QKeySequence(openkey))
        connect(openact, SIGNAL('triggered()'),
                Curry(self.setVisible, True))

        closeact = QtGui.QAction('Close', self)
        closeact.setIcon(geticon('close'))
        connect(closeact, SIGNAL('triggered()'),
                Curry(self.setVisible, False))
                
        self._actions = {'open': openact,
                         'close': closeact,}

    def setVisible(self, visible=True):
        if visible and not self.isVisible():
            self.emit(SIGNAL('visible'))
            self._focusw = QtGui.QApplication.focusWidget()
        QtGui.QToolBar.setVisible(self, visible)
        self.emit(SIGNAL('escShortcutDisabled(bool)'), not visible)
        if not visible and self._focusw:
            self._focusw.setFocus()
            self._focusw = None

    def createContent(self):
        self.addAction(self._actions['close'])
        self.parent().addAction(self._actions['open'])

    def hide(self):
        self.setVisible(False)

    def cancel(self):
        self.hide()

    def addShortcut(self, desc, key):
        act = self._actions[desc]
        shortcuts = list(act.shortcuts())
        shortcuts.append(key)
        act.setShortcuts(shortcuts)


class FindQuickBar(QuickBar):
    def __init__(self, parent):
        QuickBar.__init__(self, "Find", "/", "Find", parent)
        self.addShortcut('open', 'Ctrl+F')
        self.currenttext = ''
        
    def createActions(self, openkey, desc):
        QuickBar.createActions(self, openkey, desc)
        self._actions['findnext'] = QtGui.QAction("Find next", self)
        self._actions['findnext'].setShortcut(QtGui.QKeySequence("Ctrl+N"))
        connect(self._actions['findnext'], SIGNAL('triggered()'), self.find)
        self._actions['cancel'] = QtGui.QAction("Cancel", self)
        connect(self._actions['cancel'], SIGNAL('triggered()'), self.cancel)

    def find(self, *args):
        text = unicode(self.entry.text())
        if text == self.currenttext:
            self.emit(SIGNAL('findnext'), text)
        else:
            self.currenttext = text
            self.emit(SIGNAL('find'), text)            

    def cancel(self):
        self.emit(SIGNAL('cancel'))

    def setCancelEnabled(self, enabled=True):
        self._actions['cancel'].setEnabled(enabled)
        self._actions['findnext'].setEnabled(not enabled)
        
    def createContent(self):
        QuickBar.createContent(self)
        self.compl_model = QtGui.QStringListModel()
        self.completer = QtGui.QCompleter(self.compl_model, self)
        self.entry = QtGui.QLineEdit(self)
        self.entry.setCompleter(self.completer)
        self.addWidget(self.entry)
        self.addAction(self._actions['findnext'])
        self.addAction(self._actions['cancel'])
        self.setCancelEnabled(False)
        
        connect(self.entry, SIGNAL('returnPressed()'),
                self.find)
        connect(self.entry, SIGNAL('textEdited(const QString &)'),
                self.find)
        
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
    def __init__(self, parent):
        FindQuickBar.__init__(self, parent)
        self._findinfile_iter = None
        self._findinlog_iter = None
        self._findindesc_iter = None
        self._fileview = None
        self._headerview = None
        self._filter_files = None
        self._mode = 'diff'
        connect(self, SIGNAL('find'),
                self.on_find_text_changed)
        connect(self, SIGNAL('findnext'),
                self.on_findnext)
        connect(self, SIGNAL('cancel'),
                self.on_cancelsearch)

    def setFilterFiles(self, files):
        self._filter_files = files
        
    def setModel(self, model):
        self._model = model

    def setMode(self, mode):
        assert mode in ('diff', 'file')
        self._mode = mode
        
    def attachFileView(self, fileview):
        self._fileview = fileview

    def attachHeaderView(self, view):
        self._headerview = view
        
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
            for filename in files:
                if self._mode == 'diff':
                    flag, data = self._model.graph.filedata(filename, rev)
                else:
                    data = ctx.filectx(filename).data()
                    if util.binary(data):
                        data = "binary file"
                if data and text in data:
                    yield rev, filename
                else:
                    yield None

    def cancel(self):
        if self._actions['cancel'].isEnabled():
            self.emit(SIGNAL('cancel'))
        else:
            self.hide()

    def on_cancelsearch(self, *args):
        self._findinlog_iter = None
        self.setCancelEnabled(False)
        self.emit(SIGNAL('showMessage'), 'Search cancelled!', 2000)

    def on_findnext(self):
        """
        callback called by 'Find' quicktoolbar (on findnext signal)
        """
        if self._findindesc_iter is not None:
            for pos in self._findindesc_iter:
                # just highlight next found text in fileview
                # (handled by _findinfile_iter)
                return
            # no more found text in currently displayed file
            self._findindesc_iter = None

        if self._findinfile_iter is not None:
            for pos in self._findinfile_iter:
                # just highlight next found text in descview
                # (handled by _findindesc_iter)
                return
            # no more found text in currently displayed file
            self._findinfile_iter = None
                
        if self._findinlog_iter is None:
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
            # when search has been cancelled
            return
        for next_find in self._findinlog_iter:
            if next_find is None: # not yet found, let's animate a bit the GUI
                if (step % 20) == 0:
                    self.emit(SIGNAL("showMessage"), 'Searching'+'.'*(step/20))
                step += 1
                QtCore.QTimer.singleShot(0, Curry(self.find_next_in_log, (step % 80)))
            else:
                self.emit(SIGNAL("showMessage"), '')
                self.setCancelEnabled(False)
                
                rev, filename = next_find
                self.emit(SIGNAL('revisionSelected'), rev)
                text = unicode(self.entry.text())
                if filename is None and self._headerview:
                    self._findindesc_iter = self._headerview.searchString(text)
                    self.on_findnext()
                else:
                    self.emit(SIGNAL('fileSelected'), filename)
                    if self._fileview:
                        self._findinfile_iter = self._fileview.searchString(text)
                        self.on_findnext()
            return
        self.emit(SIGNAL('showMessage'), 'No more matches found in repository', 2000)
        self.setCancelEnabled(False)
        self._findinlog_iter = None

    def on_find_text_changed(self, newtext):
        """
        callback called by 'Find' quicktoolbar (on find signal)
        """
        newtext = unicode(newtext)
        self._findinlog_iter = None
        self._findinfile_iter = None
        if self._headerview:
            self._findindesc_iter = self._headerview.searchString(newtext)
        if self._fileview:
            self._findinfile_iter = self._fileview.searchString(newtext)
        if newtext.strip():
            if self._findindesc_iter is None and self._findindesc_iter is None:
                self.emit(SIGNAL('showMessage'),
                          'Search string not found in current diff. '
                          'Hit "Find next" button to start searching '
                          'in the repository', 2000)
            else:
                self.on_findnext()

if __name__ == "__main__":
    import sys
    import hgviewlib.qt4 # to force importation of resource module w/ icons
    app = QtGui.QApplication(sys.argv)
    root = QtGui.QMainWindow()
    w = QtGui.QFrame()
    root.setCentralWidget(w)
    
    qbar = QuickBar("test", "Ctrl+G", "toto", w)
    root.show()
    app.exec_()
    

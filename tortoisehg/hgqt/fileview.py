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
Qt4 high level widgets for hg repo changelogs and filelogs
"""

import os
import difflib

from tortoisehg.util import hglib, patchctx
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import annotate, qscilib, qtlib, blockmatcher, lexers
from tortoisehg.hgqt import visdiff, filedata

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import Qsci

qsci = Qsci.QsciScintilla

DiffMode = 1
FileMode = 2
AnnMode = 3

class HgFileView(QFrame):
    """file diff and content viewer"""

    linkActivated = pyqtSignal(QString)
    fileDisplayed = pyqtSignal(QString, QString)
    showMessage = pyqtSignal(QString)
    revisionSelected = pyqtSignal(int)
    shelveToolExited = pyqtSignal()

    searchRequested = pyqtSignal(unicode)
    """Emitted (pattern) when user request to search content"""

    grepRequested = pyqtSignal(unicode, dict)
    """Emitted (pattern, opts) when user request to search changelog"""

    def __init__(self, repo, parent):
        QFrame.__init__(self, parent)
        framelayout = QVBoxLayout(self)
        framelayout.setContentsMargins(0,0,0,0)
        framelayout.setSpacing(0)

        l = QHBoxLayout()
        l.setContentsMargins(0,0,0,0)
        l.setSpacing(0)

        self.repo = repo
        self.topLayout = QVBoxLayout()

        self.labelhbox = hbox = QHBoxLayout()
        hbox.setContentsMargins(0,0,0,0)
        hbox.setSpacing(2)
        self.topLayout.addLayout(hbox)

        self.diffToolbar = QToolBar(_('Diff Toolbar'))
        self.diffToolbar.setIconSize(QSize(16,16))
        hbox.addWidget(self.diffToolbar)

        self.filenamelabel = w = QLabel()
        w.setWordWrap(True)
        f = w.textInteractionFlags()
        w.setTextInteractionFlags(f | Qt.TextSelectableByMouse)
        w.linkActivated.connect(self.linkActivated)
        hbox.addWidget(w, 1)

        self.extralabel = w = QLabel()
        w.setWordWrap(True)
        w.linkActivated.connect(self.linkActivated)
        self.topLayout.addWidget(w)
        w.hide()

        framelayout.addLayout(self.topLayout)
        framelayout.addLayout(l, 1)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)
        l.addLayout(hbox)

        self.blk = blockmatcher.BlockList(self)
        self.sci = annotate.AnnotateView(repo, self)
        hbox.addWidget(self.blk)
        hbox.addWidget(self.sci, 1)

        for name in ('searchRequested', 'editSelected', 'grepRequested'):
            getattr(self.sci, name).connect(getattr(self, name))
        self.sci.revisionHint.connect(self.showMessage)
        self.sci.sourceChanged.connect(self.sourceChanged)
        self.sci.setAnnotationEnabled(False)

        self.blk.linkScrollBar(self.sci.verticalScrollBar())
        self.blk.setVisible(False)

        self.sci.setFrameStyle(0)
        self.sci.setReadOnly(True)
        self.sci.setUtf8(True)
        self.sci.installEventFilter(qscilib.KeyPressInterceptor(self))
        self.sci.setCaretLineVisible(False)

        # define markers for colorize zones of diff
        self.markerplus = self.sci.markerDefine(qsci.Background)
        self.markerminus = self.sci.markerDefine(qsci.Background)
        self.markertriangle = self.sci.markerDefine(qsci.Background)
        self.sci.setMarkerBackgroundColor(QColor('#B0FFA0'), self.markerplus)
        self.sci.setMarkerBackgroundColor(QColor('#A0A0FF'), self.markerminus)
        self.sci.setMarkerBackgroundColor(QColor('#FFA0A0'), self.markertriangle)

        # hide margin 0 (markers)
        self.sci.setMarginType(0, qsci.SymbolMargin)
        self.sci.setMarginWidth(0, 0)

        self.searchbar = qscilib.SearchToolBar(hidable=True)
        self.searchbar.hide()
        self.searchbar.searchRequested.connect(self.find)
        self.searchbar.conditionChanged.connect(self.highlightText)
        self.layout().addWidget(self.searchbar)

        self._ctx = None
        self._filename = None
        self._status = None
        self._mode = None
        self._parent = 0
        self._lostMode = None
        self._lastSearch = u'', False

        self.actionDiffMode = QAction(qtlib.geticon('view-diff'),
                                      _('View change as unified diff output'),
                                      self)
        self.actionDiffMode.setCheckable(True)
        self.actionDiffMode._mode = DiffMode
        self.actionFileMode = QAction(qtlib.geticon('view-file'),
                                      _('View change in context of file'),
                                      self)
        self.actionFileMode.setCheckable(True)
        self.actionFileMode._mode = FileMode
        self.actionAnnMode = QAction(qtlib.geticon('view-annotate'),
                                     _('annotate with revision numbers'),
                                     self)
        self.actionAnnMode.setCheckable(True)
        self.actionAnnMode._mode = AnnMode

        self.modeToggleGroup = QActionGroup(self)
        self.modeToggleGroup.addAction(self.actionDiffMode)
        self.modeToggleGroup.addAction(self.actionFileMode)
        self.modeToggleGroup.addAction(self.actionAnnMode)
        self.modeToggleGroup.triggered.connect(self.setMode)

        # Next/Prev diff (in full file mode)
        self.actionNextDiff = QAction(qtlib.geticon('go-down'),
                                      'Next diff (alt+down)', self)
        self.actionNextDiff.setShortcut('Alt+Down')
        self.actionNextDiff.triggered.connect(self.nextDiff)
        self.actionPrevDiff = QAction(qtlib.geticon('go-up'),
                                      'Previous diff (alt+up)', self)
        self.actionPrevDiff.setShortcut('Alt+Up')
        self.actionPrevDiff.triggered.connect(self.prevDiff)
        self.setMode(self.actionDiffMode)

        self.actionFirstParent = QAction('1', self)
        self.actionFirstParent.setCheckable(True)
        self.actionFirstParent.setChecked(True)
        self.actionFirstParent.setShortcut('CTRL+1')
        self.actionFirstParent.setToolTip(_('Show changes from first parent'))
        self.actionSecondParent = QAction('2', self)
        self.actionSecondParent.setCheckable(True)
        self.actionSecondParent.setShortcut('CTRL+2')
        self.actionSecondParent.setToolTip(_('Show changes from second parent'))
        self.parentToggleGroup = QActionGroup(self)
        self.parentToggleGroup.addAction(self.actionFirstParent)
        self.parentToggleGroup.addAction(self.actionSecondParent)
        self.parentToggleGroup.triggered.connect(self.setParent)

        self.actionFind = self.searchbar.toggleViewAction()
        self.actionFind.setIcon(qtlib.geticon('edit-find'))
        self.actionFind.setToolTip(_('Toggle display of text search bar'))
        self.actionFind.setShortcut(QKeySequence.Find)

        self.actionShelf = QAction('Shelve', self)
        self.actionShelf.setIcon(qtlib.geticon('shelve'))
        self.actionShelf.setToolTip(_('Open shelve tool'))
        self.actionShelf.triggered.connect(self.launchShelve)

        tb = self.diffToolbar
        tb.addAction(self.actionFirstParent)
        tb.addAction(self.actionSecondParent)
        tb.addSeparator()
        tb.addAction(self.actionDiffMode)
        tb.addAction(self.actionFileMode)
        tb.addAction(self.actionAnnMode)
        tb.addSeparator()
        tb.addAction(self.actionNextDiff)
        tb.addAction(self.actionPrevDiff)
        tb.addSeparator()
        tb.addAction(self.actionFind)
        tb.addAction(self.actionShelf)

        self.timer = QTimer()
        self.timer.setSingleShot(False)
        self.timer.timeout.connect(self.timerBuildDiffMarkers)

    def launchShelve(self):
        from tortoisehg.hgqt import shelve
        # TODO: pass self._filename
        dlg = shelve.ShelveDialog(self.repo, self)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()
        self.shelveToolExited.emit()

    def setFont(self, font):
        self.sci.setFont(font)

    def loadSettings(self, qs, prefix):
        self.sci.loadSettings(qs, prefix)

    def saveSettings(self, qs, prefix):
        self.sci.saveSettings(qs, prefix)

    def setRepo(self, repo):
        self.repo = repo
        self.sci.repo = repo

    @pyqtSlot(QAction)
    def setMode(self, action):
        'One of the mode toolbar buttons has been toggled'
        mode = action._mode
        if mode != self._mode:
            self._mode = mode
            self.actionNextDiff.setEnabled(False)
            self.actionPrevDiff.setEnabled(False)
            self.blk.setVisible(mode == FileMode)
            self.sci.setAnnotationEnabled(mode == AnnMode)
            self.displayFile(self._filename, self._status)

    @pyqtSlot(QAction)
    def setParent(self, action):
        if action.text() == '1':
            parent = 0
        else:
            parent = 1
        if self._parent != parent:
            self._parent = parent
            self.displayFile(self._filename, self._status)

    def restrictModes(self, candiff, canfile, canann):
        'Disable modes based on content constraints'
        self.actionDiffMode.setEnabled(candiff)
        self.actionFileMode.setEnabled(canfile)
        self.actionAnnMode.setEnabled(canann)

        # Switch mode if necessary
        mode = self._mode
        if not candiff and mode == DiffMode and canfile:
            mode = FileMode
        if not canfile and mode != DiffMode:
            mode = DiffMode
        if self._lostMode is None:
            self._lostMode = self._mode
        if self._mode != mode:
            self.actionNextDiff.setEnabled(False)
            self.actionPrevDiff.setEnabled(False)
            self.blk.setVisible(mode == FileMode)
            self.sci.setAnnotationEnabled(mode == AnnMode)
            self._mode = mode

        if self._mode == DiffMode:
            self.actionDiffMode.setChecked(True)
        elif self._mode == FileMode:
            self.actionFileMode.setChecked(True)
        else:
            self.actionAnnMode.setChecked(True)

    def setContext(self, ctx, ctx2=None):
        self._ctx = ctx
        self._ctx2 = ctx2
        self.sci.setTabWidth(ctx._repo.tabwidth)
        self.actionAnnMode.setVisible(ctx.rev() != None)
        self.actionShelf.setVisible(ctx.rev() == None)
        self.actionFirstParent.setVisible(len(ctx.parents()) == 2)
        self.actionSecondParent.setVisible(len(ctx.parents()) == 2)
        self.actionFirstParent.setEnabled(len(ctx.parents()) == 2)
        self.actionSecondParent.setEnabled(len(ctx.parents()) == 2)

    def showLine(self, line):
        if line < self.sci.lines():
            self.sci.setCursorPosition(line, 0)

    @pyqtSlot()
    def clearDisplay(self):
        self._filename = None
        self.restrictModes(False, False, False)
        self.sci.setMarginWidth(1, 0)
        self.clearMarkup()

    def clearMarkup(self):
        self.sci.clear()
        self.blk.clear()
        # Setting the label to ' ' rather than clear() keeps the label
        # from disappearing during refresh, and tool layouts bouncing
        self.filenamelabel.setText(' ')
        self.extralabel.hide()

    def displayFile(self, filename=None, status=None):
        if isinstance(filename, (unicode, QString)):
            filename = hglib.fromunicode(filename)
            status = hglib.fromunicode(status)
        if self._filename == filename:
            # Get the last visible line to restore it after reloading the editor
            lastScrollPosition = self.sci.firstVisibleLine()
        else:
            # Reset the scroll positions when the file is changed
            lastScrollPosition = 0
        self._filename, self._status = filename, status

        self.clearMarkup()
        if filename is None:
            self.restrictModes(False, False, False)
            return

        if self._ctx2:
            ctx2 = self._ctx2
        elif self._parent == 0 or len(self._ctx.parents()) == 1:
            ctx2 = self._ctx.p1()
        else:
            ctx2 = self._ctx.p2()
        fd = filedata.FileData(self._ctx, ctx2, filename, status)

        if fd.elabel:
            self.extralabel.setText(fd.elabel)
            self.extralabel.show()
        else:
            self.extralabel.hide()
        self.filenamelabel.setText(fd.flabel)

        if not fd.isValid():
            self.sci.setText(fd.error)
            self.restrictModes(False, False, False)
            return

        candiff = bool(fd.diff)
        canfile = bool(fd.contents)
        canann = canfile and type(self._ctx.rev()) is int

        if not candiff or not canfile:
            self.restrictModes(candiff, canfile, canann)
        else:
            self.actionDiffMode.setEnabled(True)
            self.actionFileMode.setEnabled(True)
            self.actionAnnMode.setEnabled(True)
            if self._lostMode:
                self._mode = self._lostMode
                if self._lostMode == DiffMode:
                    self.actionDiffMode.trigger()
                elif self._lostMode == FileMode:
                    self.actionFileMode.trigger()
                elif self._lostMode == AnnMode:
                    self.actionAnnMode.trigger()
                self._lostMode = None
                self.blk.setVisible(self._mode == FileMode)
                self.sci.setAnnotationEnabled(self._mode == AnnMode)

        if self._mode == DiffMode:
            self.sci.setMarginWidth(1, 0)
            lexer = lexers.get_diff_lexer(self)
            self.sci.setLexer(lexer)
            if lexer is None:
                self.setFont(qtlib.getfont('fontlog').font())
            # trim first three lines, for example:
            # diff -r f6bfc41af6d7 -r c1b18806486d tortoisehg/hgqt/thgrepo.py
            # --- a/tortoisehg/hgqt/thgrepo.py
            # +++ b/tortoisehg/hgqt/thgrepo.py
            if fd.diff:
                out = fd.diff.split('\n', 3)
                if len(out) == 4:
                    self.sci.setText(hglib.tounicode(out[3]))
                else:
                    # there was an error or rename without diffs
                    self.sci.setText(hglib.tounicode(fd.diff))
        elif fd.contents is None:
            return
        elif self._mode == AnnMode:
            self.sci.setSource(filename, self._ctx.rev())
        else:
            lexer = lexers.get_lexer(filename, fd.contents, self)
            self.sci.setLexer(lexer)
            if lexer is None:
                self.setFont(qtlib.getfont('fontlog').font())
            self.sci.setText(fd.contents)
            self.sci._updatemarginwidth()

        # Recover the last scroll position
        # Make sure that lastScrollPosition never exceeds the amount of
        # lines on the editor
        lastScrollPosition = min(lastScrollPosition,  self.sci.lines() - 1)
        self.sci.verticalScrollBar().setValue(lastScrollPosition)

        self.highlightText(*self._lastSearch)
        uf = hglib.tounicode(self._filename)
        self.fileDisplayed.emit(uf, fd.contents or QString())

        if self._mode == FileMode and fd.contents and fd.olddata:
            # Update blk margin
            if self.timer.isActive():
                self.timer.stop()

            self._fd = fd
            self.actionNextDiff.setEnabled(False)
            self.actionPrevDiff.setEnabled(False)
            self.blk.syncPageStep()
            self.timer.start()

    #
    # These four functions are used by Shift+Cursor actions in revdetails
    #
    def nextLine(self):
        x, y = self.sci.getCursorPosition()
        self.sci.setCursorPosition(x+1, y)

    def prevLine(self):
        x, y = self.sci.getCursorPosition()
        self.sci.setCursorPosition(x-1, y)

    def nextCol(self):
        x, y = self.sci.getCursorPosition()
        self.sci.setCursorPosition(x, y+1)

    def prevCol(self):
        x, y = self.sci.getCursorPosition()
        self.sci.setCursorPosition(x, y-1)

    @pyqtSlot(unicode, object)
    @pyqtSlot(unicode, object, int)
    def sourceChanged(self, path, rev, line=None):
        if rev != self._ctx.rev() and type(rev) is int:
            self.revisionSelected.emit(rev)

    @pyqtSlot(unicode, object, int)
    def editSelected(self, path, rev, line):
        """Open editor to show the specified file"""
        path = hglib.fromunicode(path)
        base = visdiff.snapshot(self.repo, [path], self.repo[rev])[0]
        files = [os.path.join(base, path)]
        pattern = hglib.fromunicode(self._lastSearch[0])
        qtlib.editfiles(self.repo, files, line, pattern, self)

    @pyqtSlot(unicode, bool, bool, bool)
    def find(self, exp, icase=True, wrap=False, forward=True):
        self.sci.find(exp, icase, wrap, forward)

    @pyqtSlot(unicode, bool)
    def highlightText(self, match, icase=False):
        self._lastSearch = match, icase
        self.sci.highlightText(match, icase)

    def verticalScrollBar(self):
        return self.sci.verticalScrollBar()

    #
    # file mode diff markers
    #
    def timerBuildDiffMarkers(self):
        'show modified and added lines in the self.blk margin'
        self.sci.setUpdatesEnabled(False)
        self.blk.setUpdatesEnabled(False)

        if self._fd:
            olddata = self._fd.olddata.splitlines()
            newdata = self._fd.contents.splitlines()
            diff = difflib.SequenceMatcher(None, olddata, newdata)
            self._opcodes = diff.get_opcodes()
            self._fd = None
            self._diffs = []

        for tag, alo, ahi, blo, bhi in self._opcodes[:30]:
            if tag == 'replace':
                self._diffs.append([blo, bhi])
                self.blk.addBlock('x', blo, bhi)
                for i in range(blo, bhi):
                    self.sci.markerAdd(i, self.markertriangle)
            elif tag == 'insert':
                self._diffs.append([blo, bhi])
                self.blk.addBlock('+', blo, bhi)
                for i in range(blo, bhi):
                    self.sci.markerAdd(i, self.markerplus)
            elif tag in ('equal', 'delete'):
                pass
            else:
                raise ValueError, 'unknown tag %r' % (tag,)

        self._opcodes = self._opcodes[30:]
        if not self._opcodes:
            self.actionNextDiff.setEnabled(bool(self._diffs))
            self.actionPrevDiff.setEnabled(False)
            self.timer.stop()

        self.sci.setUpdatesEnabled(True)
        self.blk.setUpdatesEnabled(True)

    def nextDiff(self):
        if self._mode == DiffMode or not self._diffs:
            self.actionNextDiff.setEnabled(False)
            self.actionPrevDiff.setEnabled(False)
            return
        row, column = self.sci.getCursorPosition()
        for i, (lo, hi) in enumerate(self._diffs):
            if lo > row:
                last = (i == (len(self._diffs)-1))
                self.sci.setCursorPosition(lo, 0)
                self.sci.verticalScrollBar().setValue(lo)
                break
        else:
            last = True
        self.actionNextDiff.setEnabled(not last)
        self.actionPrevDiff.setEnabled(True)

    def prevDiff(self):
        if self._mode == DiffMode or not self._diffs:
            self.actionNextDiff.setEnabled(False)
            self.actionPrevDiff.setEnabled(False)
            return
        row, column = self.sci.getCursorPosition()
        for i, (lo, hi) in enumerate(reversed(self._diffs)):
            if hi < row:
                first = (i == (len(self._diffs)-1))
                self.sci.setCursorPosition(lo, 0)
                self.sci.verticalScrollBar().setValue(lo)
                break
        else:
            first = True
        self.actionNextDiff.setEnabled(True)
        self.actionPrevDiff.setEnabled(not first)

    def nDiffs(self):
        return len(self._diffs)

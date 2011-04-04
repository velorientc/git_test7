# fileview.py - File diff, content, and annotation display widget
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import difflib

from mercurial import error, util

from tortoisehg.util import hglib, patchctx, colormap, thread2
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qscilib, qtlib, blockmatcher, lexers
from tortoisehg.hgqt import visdiff, filedata

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import Qsci

qsci = Qsci.QsciScintilla

DiffMode = 1
FileMode = 2
AnnMode = 3

class HgFileView(QFrame):
    "file diff, content, and annotation viewer"

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
        self.sci = AnnotateView(repo, self)
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
            self.blk.setVisible(mode != DiffMode)
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
            self.blk.setVisible(mode != DiffMode)
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
                self.blk.setVisible(self._mode != DiffMode)
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
        else:
            lexer = lexers.get_lexer(filename, fd.contents, self)
            self.sci.setLexer(lexer)
            if lexer is None:
                self.setFont(qtlib.getfont('fontlog').font())
            self.sci.setText(fd.contents)
            self.sci._updatemarginwidth()
            if self._mode == AnnMode:
                self.sci.annfile = filename
                self.sci._rev = self._ctx.rev()
                self.sci._updateannotation()

        # Recover the last scroll position
        # Make sure that lastScrollPosition never exceeds the amount of
        # lines on the editor
        lastScrollPosition = min(lastScrollPosition,  self.sci.lines() - 1)
        self.sci.verticalScrollBar().setValue(lastScrollPosition)

        self.highlightText(*self._lastSearch)
        uf = hglib.tounicode(filename)
        self.fileDisplayed.emit(uf, fd.contents or QString())

        if self._mode != DiffMode and fd.contents and fd.olddata:
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


class AnnotateView(qscilib.Scintilla):
    'QScintilla widget capable of displaying annotations'

    revisionHint = pyqtSignal(QString)

    searchRequested = pyqtSignal(QString)
    """Emitted (pattern) when user request to search content"""

    editSelected = pyqtSignal(unicode, object, int)
    """Emitted (path, rev, line) when user requests to open editor"""

    grepRequested = pyqtSignal(QString, dict)
    """Emitted (pattern, **opts) when user request to search changelog"""

    sourceChanged = pyqtSignal(unicode, object)
    """Emitted (path, rev) when the content source changed"""

    def __init__(self, repo, parent=None, **opts):
        super(AnnotateView, self).__init__(parent)
        self.setReadOnly(True)
        self.setMarginLineNumbers(1, True)
        self.setMarginType(2, qsci.TextMarginRightJustified)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menuRequest)

        self.repo = repo
        self.repo.configChanged.connect(self.configChanged)
        self.configChanged()
        self._rev = None
        self.annfile = None
        self._annotation_enabled = bool(opts.get('annotationEnabled', False))

        self._links = []  # by line
        self._revmarkers = {}  # by rev
        self._lastrev = None

        self._thread = AnnotateThread(self)
        self._thread.finished.connect(self.fillModel)

    def configChanged(self):
        self.setIndentationWidth(self.repo.tabwidth)
        self.setTabWidth(self.repo.tabwidth)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._thread.abort()
            return
        return super(AnnotateView, self).keyPressEvent(event)

    def mouseMoveEvent(self, event):
        self._emitRevisionHintAtLine(self.lineAt(event.pos()))
        super(AnnotateView, self).mouseMoveEvent(event)

    def _emitRevisionHintAtLine(self, line):
        if line < 0:
            return
        try:
            fctx = self._links[line][0]
            if fctx.rev() != self._lastrev:
                s = hglib.get_revision_desc(fctx,
                                            hglib.fromunicode(self.annfile))
                self.revisionHint.emit(s)
                self._lastrev = fctx.rev()
        except IndexError:
            pass

    @pyqtSlot(QPoint)
    def menuRequest(self, point):
        menu = self.createStandardContextMenu()
        line = self.lineAt(point)
        point = self.mapToGlobal(point)
        if line < 0 or not self.isAnnotationEnabled():
            return menu.exec_(point)

        fctx, line = self._links[line]
        data = [hglib.tounicode(fctx.path()), fctx.rev(), line]

        if self.hasSelectedText():
            selection = self.selectedText()
            def sreq(**opts):
                return lambda: self.grepRequested.emit(selection, opts)
            def sann():
                self.searchRequested.emit(selection)
            menu.addSeparator()
            for name, func in [(_('Search in original revision'),
                                sreq(rev=fctx.rev())),
                               (_('Search in working revision'),
                                sreq(rev='.')),
                               (_('Search in current annotation'), sann),
                               (_('Search in history'), sreq(all=True))]:
                def add(name, func):
                    action = menu.addAction(name)
                    action.triggered.connect(func)
                add(name, func)

        def annorig():
            self.setSource(*data)
        def editorig():
            self.editSelected.emit(*data)
        menu.addSeparator()
        for name, func in [(_('Annotate originating revision'), annorig),
                           (_('View originating revision'), editorig)]:
            def add(name, func):
                action = menu.addAction(name)
                action.triggered.connect(func)
            add(name, func)
        for pfctx in fctx.parents():
            pdata = [hglib.tounicode(pfctx.path()), pfctx.changectx().rev(),
                     line]
            def annparent(data):
                self.setSource(*data)
            def editparent(data):
                self.editSelected.emit(*data)
            for name, func in [(_('Annotate parent revision %d') % pdata[1],
                                  annparent),
                               (_('View parent revision %d') % pdata[1],
                                  editparent)]:
                def add(name, func):
                    action = menu.addAction(name)
                    action.data = pdata
                    action.run = lambda: func(action.data)
                    action.triggered.connect(action.run)
                add(name, func)
        menu.exec_(point)

    @property
    def rev(self):
        """Returns the current revision number"""
        return self._rev

    @pyqtSlot(unicode, object, int)
    def setSource(self, wfile, rev, line=None):
        """Change the content to the specified file at rev [unicode]

        line is counted from 1.
        """
        if self.annfile == wfile and self.rev == rev:
            if line:
                self.setCursorPosition(int(line) - 1, 0)
            return

        try:
            ctx = self.repo[rev]
            fctx = ctx[hglib.fromunicode(wfile)]
        except error.LookupError:
            qtlib.ErrorMsgBox(_('Unable to annotate'),
                    _('%s is not found in revision %d') % (wfile, ctx.rev()))
            return

        try:
            if rev is None:
                size = fctx.size()
            else:
                size = fctx._filelog.rawsize(fctx.filerev())
        except (EnvironmentError, error.LookupError), e:
            self.setText(_('File or diffs not displayed: ') + \
                    hglib.tounicode(str(e)))
            self.error = p + hglib.tounicode(str(e))
            return

        if size > ctx._repo.maxdiff:
            self.setText(_('File or diffs not displayed: ') + \
                    _('File is larger than the specified max size.\n'))
        else:
            self._rev = ctx.rev()
            self.clear()
            self.annfile = wfile
            if util.binary(fctx.data()):
                self.setText(_('File is binary.\n'))
            else:
                self.setText(hglib.tounicode(fctx.data()))
            if line:
                self.setCursorPosition(int(line) - 1, 0)
            self._updatelexer(fctx)
            self._updatemarginwidth()
            self.sourceChanged.emit(wfile, self._rev)
            self._updateannotation()

    def _updateannotation(self):
        if not self.isAnnotationEnabled() or not self.annfile:
            return
        ctx = self.repo[self._rev]
        fctx = ctx[hglib.fromunicode(self.annfile)]
        if util.binary(fctx.data()):
            return
        self._thread.abort()
        self._thread.start(fctx)

    @pyqtSlot()
    def fillModel(self):
        self._thread.wait()
        if self._thread.data is None:
            return

        self._links = list(self._thread.data)

        self._updaterevmargin()
        self._updatemarkers()
        self._updatemarginwidth()

    def clear(self):
        super(AnnotateView, self).clear()
        self.clearMarginText()
        self.markerDeleteAll()
        self.annfile = None

    @pyqtSlot(bool)
    def setAnnotationEnabled(self, enabled):
        """Enable / disable annotation"""
        enabled = bool(enabled)
        if enabled == self.isAnnotationEnabled():
            return
        self._annotation_enabled = enabled
        self._updateannotation()
        self._updatemarginwidth()
        self.setMouseTracking(enabled)
        if not self.isAnnotationEnabled():
            self.annfile = None
            self.markerDeleteAll()

    def isAnnotationEnabled(self):
        """True if annotation enabled and available"""
        if self.rev is None:
            return False  # annotate working copy is not supported
        return self._annotation_enabled

    def _updatelexer(self, fctx):
        """Update the lexer according to the given file"""
        lex = lexers.get_lexer(fctx.path(), hglib.tounicode(fctx.data()), self)
        self.setLexer(lex)
        if lex is None:
            self.setFont(qtlib.getfont('fontlog').font())

    def _updaterevmargin(self):
        """Update the content of margin area showing revisions"""
        s = self._margin_style
        # Workaround to set style of the current sci widget.
        # QsciStyle sends style data only to the first sci widget.
        # See qscintilla2/Qt4/qscistyle.cpp
        self.SendScintilla(qsci.SCI_STYLESETBACK,
                           s.style(), s.paper())
        self.SendScintilla(qsci.SCI_STYLESETFONT,
                           s.style(), s.font().family().toAscii().data())
        self.SendScintilla(qsci.SCI_STYLESETSIZE,
                           s.style(), s.font().pointSize())
        for i, (fctx, _origline) in enumerate(self._links):
            self.setMarginText(i, str(fctx.rev()), s)

    def _updatemarkers(self):
        """Update markers which colorizes each line"""
        self._redefinemarkers()
        for i, (fctx, _origline) in enumerate(self._links):
            m = self._revmarkers.get(fctx.rev())
            if m is not None:
                self.markerAdd(i, m)

    def _redefinemarkers(self):
        """Redefine line markers according to the current revs"""
        curdate = self.repo[self._rev].date()[0]

        # make sure to colorize at least 1 year
        mindate = curdate - 365 * 24 * 60 * 60

        self._revmarkers.clear()
        filectxs = iter(fctx for fctx, _origline in self._links)
        palette = colormap.makeannotatepalette(filectxs, curdate,
                                               maxcolors=32, maxhues=8,
                                               maxsaturations=16,
                                               mindate=mindate)
        for i, (color, fctxs) in enumerate(palette.iteritems()):
            self.markerDefine(qsci.Background, i)
            self.setMarkerBackgroundColor(QColor(color), i)
            for fctx in fctxs:
                self._revmarkers[fctx.rev()] = i

    @util.propertycache
    def _margin_style(self):
        """Style for margin area"""
        s = Qsci.QsciStyle()
        s.setPaper(QApplication.palette().color(QPalette.Window))
        s.setFont(self.font())
        return s

    @pyqtSlot()
    def _updatemarginwidth(self):
        self.setMarginsFont(self.font())
        def lentext(s):
            return 'M' * (len(str(s)) + 2)  # 2 for margin
        self.setMarginWidth(1, lentext(self.lines()))
        if self.isAnnotationEnabled() and self._links:
            maxrev = max(fctx.rev() for fctx, _origline in self._links)
            self.setMarginWidth(2, lentext(maxrev))
        else:
            self.setMarginWidth(2, 0)

class AnnotateThread(QThread):
    'Background thread for annotating a file at a revision'
    def __init__(self, parent=None):
        super(AnnotateThread, self).__init__(parent)
        self._threadid = None

    @pyqtSlot(object)
    def start(self, fctx):
        self._fctx = fctx
        super(AnnotateThread, self).start()
        self.data = None

    @pyqtSlot()
    def abort(self):
        if self._threadid is None:
            return
        try:
            thread2._async_raise(self._threadid, KeyboardInterrupt)
            self.wait()
        except ValueError:
            pass

    def run(self):
        assert self.currentThread() != qApp.thread()
        self._threadid = self.currentThreadId()
        try:
            data = []
            for (fctx, line), _text in self._fctx.annotate(True, True):
                data.append((fctx, line))
            self.data = data
        except KeyboardInterrupt:
            pass
        finally:
            self._threadid = None
            del self._fctx

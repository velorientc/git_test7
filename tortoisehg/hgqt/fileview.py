# fileview.py - File diff, content, and annotation display widget
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import difflib
import re

from mercurial import util, patch

from tortoisehg.util import hglib, colormap, thread2
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qscilib, qtlib, blockmatcher, lexers
from tortoisehg.hgqt import visdiff, filedata

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import Qsci

qsci = qscilib.Scintilla

DiffMode = 1
FileMode = 2
AnnMode = 3

class HgFileView(QFrame):
    "file diff, content, and annotation viewer"

    diffHeaderRegExp = re.compile("^@@ -[0-9]+,[0-9]+ \+[0-9]+,[0-9]+ @@")

    linkActivated = pyqtSignal(QString)
    fileDisplayed = pyqtSignal(QString, QString)
    showMessage = pyqtSignal(QString)
    revisionSelected = pyqtSignal(int)
    shelveToolExited = pyqtSignal()
    newChunkList = pyqtSignal(QString, object)
    chunkSelectionChanged = pyqtSignal()

    grepRequested = pyqtSignal(unicode, dict)
    """Emitted (pattern, opts) when user request to search changelog"""

    def __init__(self, repoagent, parent):
        QFrame.__init__(self, parent)
        framelayout = QVBoxLayout(self)
        framelayout.setContentsMargins(0,0,0,0)

        l = QHBoxLayout()
        l.setContentsMargins(0,0,0,0)
        l.setSpacing(0)

        self._repoagent = repoagent
        repo = repoagent.rawRepo()
        # TODO: replace by repoagent if setRepo(bundlerepo) can be removed
        self.repo = repo
        self._diffs = []
        self.changes = None
        self.changeselection = False
        self.chunkatline = {}
        self.excludemsg = _(' (excluded from the next commit)')

        self.topLayout = QVBoxLayout()

        self.labelhbox = hbox = QHBoxLayout()
        hbox.setContentsMargins(0,0,0,0)
        hbox.setSpacing(2)
        self.topLayout.addLayout(hbox)

        self.diffToolbar = QToolBar(_('Diff Toolbar'))
        self.diffToolbar.setIconSize(QSize(16,16))
        self.diffToolbar.setStyleSheet(qtlib.tbstylesheet)
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
        self.blksearch = blockmatcher.BlockList(self)
        self.sci = AnnotateView(repoagent, self)
        self._forceviewindicator = None
        hbox.addWidget(self.blk)
        hbox.addWidget(self.sci, 1)
        hbox.addWidget(self.blksearch)

        self.sci.showMessage.connect(self.showMessage)
        self.sci.setAnnotationEnabled(False)
        self.sci.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sci.customContextMenuRequested.connect(self.menuRequest)
        self.annmarginclicked = False
        self.sci.marginClicked.connect(self.marginClicked)

        self.blk.linkScrollBar(self.sci.verticalScrollBar())
        self.blk.setVisible(False)
        self.blksearch.linkScrollBar(self.sci.verticalScrollBar())
        self.blksearch.setVisible(False)

        self.sci.setReadOnly(True)
        self.sci.setUtf8(True)
        keys = set((Qt.Key_Space,))
        self.sci.installEventFilter(qscilib.KeyPressInterceptor(self, keys))
        self.sci.setCaretLineVisible(False)

        # define markers for colorize zones of diff
        self.markerplus = self.sci.markerDefine(qsci.Background)
        self.markerminus = self.sci.markerDefine(qsci.Background)
        self.markertriangle = self.sci.markerDefine(qsci.Background)
        self.sci.setMarkerBackgroundColor(QColor('#B0FFA0'), self.markerplus)
        self.sci.setMarkerBackgroundColor(QColor('#A0A0FF'), self.markerminus)
        self.sci.setMarkerBackgroundColor(QColor('#FFA0A0'), self.markertriangle)

        self._checkedpix = qtlib.getcheckboxpixmap(QStyle.State_On,
                                                   QColor('#B0FFA0'), self)
        self.inclmarker = self.sci.markerDefine(self._checkedpix, -1)

        self._uncheckedpix = qtlib.getcheckboxpixmap(QStyle.State_Off,
                                                     QColor('#B0FFA0'), self)
        self.exclmarker = self.sci.markerDefine(self._uncheckedpix, -1)

        self.exclcolor = self.sci.markerDefine(qsci.Background, -1)
        self.sci.setMarkerBackgroundColor(QColor('lightgrey'), self.exclcolor)
        self.sci.setMarkerForegroundColor(QColor('darkgrey'), self.exclcolor)
        mask = (1 << self.inclmarker) | (1 << self.exclmarker) | \
               (1 << self.exclcolor)
        self.sci.setMarginType(4, qsci.SymbolMargin)
        self.sci.setMarginMarkerMask(4, mask)
        self.markexcluded = QSettings().value('changes-mark-excluded').toBool()
        self.excludeindicator = -1
        self.updateChunkIndicatorMarks()
        self.sci.setIndicatorDrawUnder(True, self.excludeindicator)
        self.sci.setIndicatorForegroundColor(QColor('gray'), self.excludeindicator)

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
        self.modeToggleGroup.triggered.connect(self._setModeByAction)

        # Next/Prev diff (in full file mode)
        self.actionNextDiff = QAction(qtlib.geticon('go-down'),
                                      _('Next diff (alt+down)'), self)
        self.actionNextDiff.setShortcut('Alt+Down')
        self.actionNextDiff.triggered.connect(self.nextDiff)
        self.actionPrevDiff = QAction(qtlib.geticon('go-up'),
                                      _('Previous diff (alt+up)'), self)
        self.actionPrevDiff.setShortcut('Alt+Up')
        self.actionPrevDiff.triggered.connect(self.prevDiff)
        self._setModeByAction(self.actionDiffMode)

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
        self.actionFind.triggered.connect(self.searchbarTriggered)
        qtlib.newshortcutsforstdkey(QKeySequence.Find, self, self.showsearchbar)

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

        self.timer = QTimer(self)
        self.timer.setSingleShot(False)
        self.timer.timeout.connect(self.timerBuildDiffMarkers)

    def launchShelve(self):
        from tortoisehg.hgqt import shelve
        # TODO: pass self._filename
        dlg = shelve.ShelveDialog(self._repoagent, self)
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

    def updateChunkIndicatorMarks(self):
        '''
        This method has some pre-requisites:
        - self.markexcluded and self.excludeindicator MUST be defined
        - self.excludeindicator MUST be set to -1 before calling this
        method for the first time
        '''
        indicatortypes = (qsci.HiddenIndicator, qsci.StrikeIndicator)
        self.excludeindicator = self.sci.indicatorDefine(
            indicatortypes[self.markexcluded],
            self.excludeindicator)

    def enableChangeSelection(self, enable):
        'Enable the use of a selection margin when a diff view is active'
        # Should only be called with True from the commit tool when it is in
        # a 'commit' mode and False for other uses
        self.changeselection = enable
        self._showChangeSelectMargin(enable)

    def updateChunk(self, chunk, exclude):
        'change chunk exclusion state, update display when necessary'
        # returns True if the chunk state was changed
        if chunk.excluded == exclude:
            return False
        if exclude:
            chunk.excluded = True
            self.changes.excludecount += 1

            self.sci.setReadOnly(False)
            llen = self.sci.text(chunk.lineno).length()
            self.sci.insertAt(self.excludemsg, chunk.lineno, llen-1)
            self.sci.setReadOnly(True)

            self.sci.markerDelete(chunk.lineno, self.inclmarker)
            self.sci.markerAdd(chunk.lineno, self.exclmarker)
            for i in xrange(chunk.linecount-1):
                self.sci.markerAdd(chunk.lineno+i+1, self.exclcolor)
            self.sci.fillIndicatorRange(chunk.lineno+1, 0,
                                        chunk.lineno+chunk.linecount, 0,
                                        self.excludeindicator)
        else:
            chunk.excluded = False
            self.changes.excludecount -= 1

            self.sci.setReadOnly(False)
            llen = self.sci.text(chunk.lineno).length()
            mlen = len(self.excludemsg)
            pos = self.sci.positionFromLineIndex(chunk.lineno, llen-mlen-1)
            self.sci.SendScintilla(qsci.SCI_SETTARGETSTART, pos)
            self.sci.SendScintilla(qsci.SCI_SETTARGETEND, pos + mlen)
            self.sci.SendScintilla(qsci.SCI_REPLACETARGET, 0, '')
            self.sci.setReadOnly(True)

            self.sci.markerDelete(chunk.lineno, self.exclmarker)
            self.sci.markerAdd(chunk.lineno, self.inclmarker)
            for i in xrange(chunk.linecount-1):
                self.sci.markerDelete(chunk.lineno+i+1, self.exclcolor)
            self.sci.clearIndicatorRange(chunk.lineno+1, 0,
                                         chunk.lineno+chunk.linecount, 0,
                                         self.excludeindicator)
        return True

    @pyqtSlot(QAction)
    def _setModeByAction(self, action):
        'One of the mode toolbar buttons has been toggled'
        mode = action._mode
        self._lostMode = mode
        if mode != self._mode:
            self._mode = mode
            self.actionNextDiff.setEnabled(False)
            self.actionPrevDiff.setEnabled(False)
            self.blk.setVisible(mode != DiffMode)
            self.sci.setAnnotationEnabled(mode == AnnMode)
            self.displayFile(self._filename, self._status)

    def setMode(self, mode):
        """Switch view to DiffMode/FileMode/AnnMode if available for the current
        content; otherwise it will be switched later"""
        actionmap = dict((a._mode, a) for a in self.modeToggleGroup.actions())
        try:
            action = actionmap[mode]
        except KeyError:
            raise ValueError('invalid mode: %r' % mode)

        if action.isEnabled():
            if not action.isChecked():
                action.trigger()  # implies _setModeByAction()
        else:
            self._lostMode = mode

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

    def setSource(self, path, rev, line):
        self.revisionSelected.emit(rev)
        self.setContext(self.repo[rev])
        self.displayFile(path, None)
        self.showLine(line)

    def showLine(self, line):
        if line < self.sci.lines():
            self.sci.setCursorPosition(line, 0)

    @pyqtSlot()
    def clearDisplay(self):
        self._filename = None
        self._diffs = []
        self.restrictModes(False, False, False)
        self.sci.setMarginWidth(1, 0)
        self.clearMarkup()

    def clearMarkup(self):
        self.sci.clear()
        self.blk.clear()
        self.blksearch.clear()
        # Setting the label to ' ' rather than clear() keeps the label
        # from disappearing during refresh, and tool layouts bouncing
        self.filenamelabel.setText(' ')
        self.extralabel.hide()
        self.actionNextDiff.setEnabled(False)
        self.actionPrevDiff.setEnabled(False)

        self.maxWidth = 0
        self.changes = None
        self.chunkatline = {}
        self._showChangeSelectMargin(False)
        self.sci.showHScrollBar(False)

    def _showChangeSelectMargin(self, show):
        'toggle the display of the diff change selection margin'
        self.sci.setMarginWidth(4, show and 15 or 0)
        self.sci.setMarginSensitivity(4, show)

    #@pyqtSlot(int, int, Qt.KeyboardModifiers)
    def marginClicked(self, margin, line, state):
        'margin clicked event'
        if margin == 2:
            if self.annmarginclicked or state == Qt.ControlModifier:
                fctx, line = self.sci._links[line]
                self.setSource(hglib.tounicode(fctx.path()), fctx.rev(), line)
            else:
                self.annmarginclicked = True
                def disableClick():
                    self.annmarginclicked = False
                QTimer.singleShot(QApplication.doubleClickInterval(), disableClick)

                # mimic the default "border selection" behavior,
                # which is disabled when you use setMarginSensitivity()
                if state == Qt.ShiftModifier:
                    sellinetop, selchartop, sellinebottom, selcharbottom = self.sci.getSelection()
                    if sellinetop <= line:
                        sline = sellinetop
                        eline = line + 1
                    else:
                        sline = line
                        eline = sellinebottom
                        if selcharbottom != 0:
                            eline += 1
                else:
                    sline = line
                    eline = line + 1
                self.sci.setSelection(sline, 0, eline, 0)
            return

        if line not in self.chunkatline:
            return
        chunk = self.chunkatline[line]
        if self.updateChunk(chunk, not chunk.excluded):
            self.chunkSelectionChanged.emit()

    def _setupForceViewIndicator(self):
        if not self._forceviewindicator:
            self._forceviewindicator = self.sci.indicatorDefine(self.sci.PlainIndicator)
            self.sci.setIndicatorDrawUnder(True, self._forceviewindicator)
            self.sci.setIndicatorForegroundColor(
                QColor('blue'), self._forceviewindicator)
            # delay until next event-loop in order to complete mouse release
            self.sci.SCN_INDICATORRELEASE.connect(self.forceDisplayFile,
                                                  Qt.QueuedConnection)

    def forceDisplayFile(self):
        if self.changes is not None:
            return
        self.sci.setText(_('Please wait while the file is opened ...'))
        # Wait a little to ensure that the "wait message" is displayed
        QTimer.singleShot(10,
            lambda: self.displayFile(self._filename, self._status, force=True))

    def displayFile(self, filename=None, status=None, force=False):
        if isinstance(filename, (unicode, QString)):
            filename = hglib.fromunicode(filename)
            status = hglib.fromunicode(status)
        if filename and self._filename == filename:
            # Get the last visible line to restore it after reloading the editor
            lastCursorPosition = self.sci.getCursorPosition()
            lastScrollPosition = self.sci.firstVisibleLine()
        else:
            lastCursorPosition = (0, 0)
            lastScrollPosition = 0
        self._filename, self._status = filename, status

        self.clearMarkup()
        self._diffs = []
        if filename is None:
            self.restrictModes(False, False, False)
            return

        if self._ctx2:
            ctx2 = self._ctx2
        elif self._parent == 0 or len(self._ctx.parents()) == 1:
            ctx2 = self._ctx.p1()
        else:
            ctx2 = self._ctx.p2()
        fd = filedata.FileData(self._ctx, ctx2, filename, status, self.changeselection, force=force)

        if fd.elabel:
            self.extralabel.setText(fd.elabel)
            self.extralabel.show()
        else:
            self.extralabel.hide()
        self.filenamelabel.setText(fd.flabel)

        uf = hglib.tounicode(filename)

        if not fd.isValid():
            self.sci.setText(fd.error)
            self.sci.setLexer(None)
            self.sci.setFont(qtlib.getfont('fontlog').font())
            self.sci.setMarginWidth(1, 0)
            self.blk.setVisible(False)
            self.restrictModes(False, False, False)
            self.newChunkList.emit(uf, None)

            forcedisplaymsg = filedata.forcedisplaymsg
            linkstart = fd.error.find(forcedisplaymsg)
            if linkstart >= 0:
                # add the link to force to view the data anyway
                self._setupForceViewIndicator()
                self.sci.fillIndicatorRange(
                    0, linkstart, 0, linkstart+len(forcedisplaymsg), self._forceviewindicator)
            return

        candiff = bool(fd.diff)
        canfile = bool(fd.contents or fd.ucontents)
        canann = bool(fd.contents) and type(self._ctx.rev()) is int

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
            lexer = lexers.difflexer(self)
            self.sci.setLexer(lexer)
            if lexer is None:
                self.sci.setFont(qtlib.getfont('fontlog').font())
            if fd.changes:
                self._showChangeSelectMargin(True)
                self.changes = fd.changes
                self.sci.setText(hglib.tounicode(fd.diff))
                for chunk in self.changes.hunks:
                    self.chunkatline[chunk.lineno] = chunk
                    self.sci.markerAdd(chunk.lineno, self.inclmarker)
            elif fd.diff:
                # trim first three lines, for example:
                # diff -r f6bfc41af6d7 -r c1b18806486d tortoisehg/hgqt/mq.py
                # --- a/tortoisehg/hgqt/mq.py
                # +++ b/tortoisehg/hgqt/mq.py
                out = fd.diff.split('\n', 3)
                if len(out) == 4:
                    self.sci.setText(hglib.tounicode(out[3]))
                else:
                    # there was an error or rename without diffs
                    self.sci.setText(hglib.tounicode(fd.diff))
            self.newChunkList.emit(uf, fd.changes)
        elif fd.ucontents:
            # subrepo summary and perhaps other data
            self.sci.setText(fd.ucontents)
            self.sci.setLexer(None)
            self.sci.setFont(qtlib.getfont('fontlog').font())
            self.sci.setMarginWidth(1, 0)
            self.blk.setVisible(False)
            self.newChunkList.emit(uf, None)
            return
        elif fd.contents:
            lexer = lexers.getlexer(self.repo.ui, filename, fd.contents, self)
            self.sci.setLexer(lexer)
            if lexer is None:
                self.sci.setFont(qtlib.getfont('fontlog').font())
            self.sci.setText(hglib.tounicode(fd.contents))
            self.blk.setVisible(True)
            self.sci._updatemarginwidth()
            if self._mode == AnnMode:
                self.sci._updateannotation(self._ctx, filename)
            self.newChunkList.emit(uf, None)
        else:
            self.newChunkList.emit(uf, None)
            return

        # Recover the last cursor/scroll position
        self.sci.setCursorPosition(*lastCursorPosition)
        # Make sure that lastScrollPosition never exceeds the amount of
        # lines on the editor
        lastScrollPosition = min(lastScrollPosition,  self.sci.lines() - 1)
        self.sci.verticalScrollBar().setValue(lastScrollPosition)

        self.highlightText(*self._lastSearch)
        uc = hglib.tounicode(fd.contents) or ''
        self.fileDisplayed.emit(uf, uc)

        if self._mode != DiffMode:
            self.blk.setVisible(True)
            self.blk.syncPageStep()
        self.blksearch.syncPageStep()

        if fd.contents and fd.olddata:
            if self.timer.isActive():
                self.timer.stop()
            self._fd = fd
            self.timer.start()
        self.actionNextDiff.setEnabled(bool(self._diffs))
        self.actionPrevDiff.setEnabled(bool(self._diffs))

        lexer = self.sci.lexer()

        if lexer:
            font = self.sci.lexer().font(0)
        else:
            font = self.sci.font()

        fm = QFontMetrics(font)
        self.maxWidth = fm.maxWidth()
        lines = unicode(self.sci.text()).splitlines()
        if lines:
            # assume that the longest line has the largest width;
            # fm.width() is too slow to apply to each line.
            try:
                longestline = max(lines, key=len)
            except TypeError:  # Python<2.5 has no key support
                longestline = max((len(l), l) for l in lines)[1]
            self.maxWidth += fm.width(longestline)
        self.updateScrollBar()

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

    @pyqtSlot(unicode, bool, bool, bool)
    def find(self, exp, icase=True, wrap=False, forward=True):
        self.sci.find(exp, icase, wrap, forward)

    @pyqtSlot(unicode, bool)
    def highlightText(self, match, icase=False):
        self._lastSearch = match, icase
        self.sci.highlightText(match, icase)
        blk = self.blksearch
        blk.clear()
        blk.setUpdatesEnabled(False)
        blk.clear()
        for l in self.sci.highlightLines:
            blk.addBlock('s', l, l + 1)
        blk.setVisible(bool(match))
        blk.setUpdatesEnabled(True)

    def loadSelectionIntoSearchbar(self):
        text = self.sci.selectedText()
        if text:
            self.searchbar.setPattern(text)

    @pyqtSlot(bool)
    def searchbarTriggered(self, checked):
        if checked:
            self.loadSelectionIntoSearchbar()

    @pyqtSlot()
    def showsearchbar(self):
        self.loadSelectionIntoSearchbar()
        self.searchbar.show()

    def verticalScrollBar(self):
        return self.sci.verticalScrollBar()

    #
    # file mode diff markers
    #
    @pyqtSlot()
    def timerBuildDiffMarkers(self):
        'show modified and added lines in the self.blk margin'
        # The way the diff markers are generated differs between the DiffMode
        # and the other modes
        # In the DiffMode case, the marker positions are found by looking for
        # lines matching a regular expression representing a diff header, while
        # in all other cases we use the difflib.SequenceMatcher, which returns
        # a set of opcodes that must be parsed
        # In any case, the markers are generated incrementally. This function is
        # run by a timer, which each time that is called processes a bunch of
        # lines (when in DiffMode) or of opcodes (in all other modes).
        # When there are no more lines or opcodes to consume the timer is
        # stopped.

        self.sci.setUpdatesEnabled(False)
        self.blk.setUpdatesEnabled(False)

        if self._mode == DiffMode:
            if self._fd:
                self._fd = None
                self._diffs = []
                self._linestoprocess = unicode(self.sci.text()).splitlines()
                self._firstlinetoprocess = 0
                self._opcodes = True
            # Process linesPerBlock lines at a time
            linesPerBlock = 100
            # Look for lines matching the "diff header"
            for n, line in enumerate(self._linestoprocess[:linesPerBlock]):
                if self.diffHeaderRegExp.match(line):
                    diffLine = self._firstlinetoprocess + n
                    self._diffs.append([diffLine, diffLine])
                    self.sci.markerAdd(diffLine, self.markerplus)
            self._linestoprocess = self._linestoprocess[linesPerBlock:]
            self._firstlinetoprocess += linesPerBlock
            if not self._linestoprocess:
                self._opcodes = False
                self._firstlinetoprocess = 0
        else:
            if self._fd:
                olddata = self._fd.olddata.splitlines()
                newdata = self._fd.contents.splitlines()
                diff = difflib.SequenceMatcher(None, olddata, newdata)
                self._opcodes = diff.get_opcodes()
                self._fd = None
                self._diffs = []
            elif isinstance(self._opcodes, bool):
                # catch self._mode changes while this thread is active
                self._opcodes = []

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
        if not self._diffs:
            self.actionNextDiff.setEnabled(False)
            self.actionPrevDiff.setEnabled(False)
            return
        else:
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
        if not self._diffs:
            self.actionNextDiff.setEnabled(False)
            self.actionPrevDiff.setEnabled(False)
            return
        else:
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

    def editSelected(self, path, rev, line):
        """Open editor to show the specified file"""
        path = hglib.fromunicode(path)
        base = visdiff.snapshot(self.repo, [path], self.repo[rev])[0]
        files = [os.path.join(base, path)]
        pattern = hglib.fromunicode(self._lastSearch[0])
        qtlib.editfiles(self.repo, files, line, pattern, self)

    @pyqtSlot(QPoint)
    def menuRequest(self, point):
        menu = self._createContextMenu(point)
        menu.exec_(self.sci.viewport().mapToGlobal(point))
        menu.setParent(None)

    def _createContextMenu(self, point):
        menu = self.sci.createStandardContextMenu()
        line = self.sci.lineNearPoint(point)

        selection = self.sci.selectedText()
        def sreq(**opts):
            return lambda: self.grepRequested.emit(selection, opts)
        def sann():
            self.searchbar.search(selection)
            self.searchbar.show()

        if self._mode != AnnMode:
            if self.changeselection:
                def toggleMarkExcluded():
                    self.markexcluded = not self.markexcluded
                    self.updateChunkIndicatorMarks()
                    QSettings().setValue('changes-mark-excluded',
                        self.markexcluded)
                actmarkexcluded = menu.addAction(_('Mark excluded changes'))
                actmarkexcluded.setCheckable(True)
                actmarkexcluded.setChecked(self.markexcluded)
                actmarkexcluded.triggered.connect(toggleMarkExcluded)
            if selection:
                menu.addSeparator()
                for name, func in [(_('&Search in Current File'), sann),
                        (_('Search in All &History'), sreq(all=True))]:
                    def add(name, func):
                        action = menu.addAction(name)
                        action.triggered.connect(func)
                    add(name, func)
            return menu

        menu.addSeparator()
        annoptsmenu = menu.addMenu(_('Annotate Op&tions'))
        annoptsmenu.addActions(self.sci.annotateOptionActions())

        if line < 0 or line >= len(self.sci._links):
            return menu

        menu.addSeparator()

        fctx, line = self.sci._links[line]
        if selection:
            def sreq(**opts):
                return lambda: self.grepRequested.emit(selection, opts)
            def sann():
                self.searchbar.search(selection)
                self.searchbar.show()
            menu.addSeparator()
            annsearchmenu = menu.addMenu(_('Search Selected Text'))
            for name, func in [(_('In Current &File'), sann),
                               (_('In &Current Revision'),
                                sreq(rev='.')),
                               (_('In &Original Revision'),
                                sreq(rev=fctx.rev())),
                               (_('In All &History'), sreq(all=True))]:
                def add(name, func):
                    action = annsearchmenu.addAction(name)
                    action.triggered.connect(func)
                add(name, func)

        data = [hglib.tounicode(fctx.path()), fctx.rev(), line]

        def annorig():
            self.setSource(*data)
        def editorig():
            self.editSelected(*data)
        menu.addSeparator()
        origrev = fctx.rev()
        anngotomenu = menu.addMenu(_('Go to'))
        annviewmenu = menu.addMenu(_('View File at'))
        for name, func, smenu in [(_('&Originating Revision'), annorig, anngotomenu),
                           (_('&Originating Revision'), editorig, annviewmenu)]:
            def add(name, func):
                action = smenu.addAction(name)
                action.triggered.connect(func)
            add(name, func)
        for pfctx in fctx.parents():
            pdata = [hglib.tounicode(pfctx.path()), pfctx.changectx().rev(),
                     line]
            def annparent(data):
                self.setSource(*data)
            def editparent(data):
                self.editSelected(*data)
            for name, func, smenu in [(_('&Parent Revision (%d)') % pdata[1],
                                  annparent, anngotomenu),
                               (_('&Parent Revision (%d)') % pdata[1],
                                  editparent, annviewmenu)]:
                def add(name, func):
                    action = smenu.addAction(name)
                    action.data = pdata
                    action.run = lambda: func(action.data)
                    action.triggered.connect(action.run)
                add(name, func)
        return menu

    def resizeEvent(self, event):
        super(HgFileView, self).resizeEvent(event)
        self.updateScrollBar()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            if self.changeselection:
                x, y = self.sci.getCursorPosition()
                chunk = self.chunkContainsLine(x)
                if self.updateChunk(chunk, not chunk.excluded):
                    self.chunkSelectionChanged.emit()
            return
        return super(HgFileView, self).keyPressEvent(event)

    def chunkContainsLine(self, line):
        chunks = self.chunkatline
        if line in chunks:
            return chunks[line]

        line = max(i for i in chunks.keys() if i < line)
        return chunks[line]

    def updateScrollBar(self):
        sbWidth = self.sci.verticalScrollBar().width()
        scrollWidth = self.maxWidth + sbWidth - self.sci.width()
        self.sci.showHScrollBar(scrollWidth > 0)
        self.sci.horizontalScrollBar().setRange(0, scrollWidth)

class AnnotateView(qscilib.Scintilla):
    'QScintilla widget capable of displaying annotations'

    showMessage = pyqtSignal(QString)

    def __init__(self, repoagent, parent=None):
        super(AnnotateView, self).__init__(parent)
        self.setReadOnly(True)
        self.setMarginLineNumbers(1, True)
        self.setMarginType(2, qsci.TextMarginRightJustified)
        self.setMouseTracking(False)

        self._repoagent = repoagent
        repo = repoagent.rawRepo()
        # TODO: replace by repoagent if sci.repo = bundlerepo can be removed
        self.repo = repo

        self._annotation_enabled = False
        self._links = []  # by line
        self._anncache = {}  # by rev
        self._revmarkers = {}  # by rev
        self._lastrev = None

        diffopts = patch.diffopts(repo.ui, section='annotate')
        self._thread = AnnotateThread(self, diffopts=diffopts)
        self._thread.finished.connect(self.fillModel)

        self._initAnnotateOptionActions()

        self._repoagent.configChanged.connect(self.configChanged)
        self.configChanged()
        self._loadAnnotateSettings()

    def _loadAnnotateSettings(self):
        s = QSettings()
        wb = "Annotate/"
        for a in self._annoptactions:
            a.setChecked(s.value(wb + a.data().toString()).toBool())
        if not util.any(a.isChecked() for a in self._annoptactions):
            self._annoptactions[-1].setChecked(True)  # 'rev' by default
        self._setupLineAnnotation()

    def _saveAnnotateSettings(self):
        s = QSettings()
        wb = "Annotate/"
        for a in self._annoptactions:
            s.setValue(wb + a.data().toString(), a.isChecked())

    def _initAnnotateOptionActions(self):
        self._annoptactions = []
        for name, field in [(_('Show &Author'), 'author'),
                            (_('Show &Date'), 'date'),
                            (_('Show &Revision'), 'rev')]:
            a = QAction(name, self, checkable=True)
            a.setData(field)
            a.triggered.connect(self._updateAnnotateOption)
            self._annoptactions.append(a)

    @pyqtSlot()
    def _updateAnnotateOption(self):
        # make sure at least one option is checked
        if not util.any(a.isChecked() for a in self._annoptactions):
            self.sender().setChecked(True)

        self._setupLineAnnotation()
        self.fillModel()
        self._saveAnnotateSettings()

    def annotateOptionActions(self):
        """List of QAction for annotate options"""
        return list(self._annoptactions)

    def _setupLineAnnotation(self):
        def getauthor(fctx):
            return hglib.tounicode(hglib.username(fctx.user()))
        def getdate(fctx):
            return util.shortdate(fctx.date())
        def getrev(fctx):
            return fctx.rev()

        aformat = [str(a.data().toString()) for a in self._annoptactions
                   if a.isChecked()]
        tiprev = self.repo['tip'].rev()
        revwidth = len(str(tiprev))
        annfields = {
            'rev': ('%%%dd' % revwidth, getrev),
            'author': ('%s', getauthor),
            'date': ('%s', getdate),
        }
        annformat = []
        annfunc = []
        for fieldname in aformat:
            fielddata = annfields.get(fieldname, ())
            if fielddata:
                annformat.append(fielddata[0])
                annfunc.append(fielddata[1])
        annformat = ' : '.join(annformat)

        self._anncache.clear()
        def lineannotation(fctx):
            rev = fctx.rev()
            ann = self._anncache.get(rev, None)
            if ann is None:
                ann = annformat % tuple([f(fctx) for f in annfunc])
                self._anncache[rev] = ann
            return ann
        self._lineannotation = lineannotation

    @pyqtSlot()
    def configChanged(self):
        self.setIndentationWidth(self.repo.tabwidth)
        self.setTabWidth(self.repo.tabwidth)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._thread.abort()
            return
        return super(AnnotateView, self).keyPressEvent(event)

    def mouseMoveEvent(self, event):
        self._emitRevisionHintAtLine(self.lineNearPoint(event.pos()))
        super(AnnotateView, self).mouseMoveEvent(event)

    def _emitRevisionHintAtLine(self, line):
        if line < 0:
            return
        try:
            fctx = self._links[line][0]
            if fctx.rev() != self._lastrev:
                s = hglib.get_revision_desc(fctx, self.annfile)
                self.showMessage.emit(s)
                self._lastrev = fctx.rev()
        except IndexError:
            pass

    def _updateannotation(self, ctx, filename):
        if ctx.rev() is None:
            return
        wsub, filename, ctx = hglib.getDeepestSubrepoContainingFile(filename, ctx)
        if wsub is None:
            # The file was not found in the repo context or its subrepos
            # This may happen for files that have been removed
            return
        self.ctx = ctx
        self.annfile = filename
        self._thread.abort()
        self._thread.start(ctx[filename])

    @pyqtSlot()
    def fillModel(self):
        self._thread.wait()
        if self._thread.data is None:
            return

        self._links = list(self._thread.data)
        self._anncache.clear()

        self._updaterevmargin()
        self._updatemarkers()
        self._updatemarginwidth()

    def clear(self):
        super(AnnotateView, self).clear()
        self.clearMarginText()
        self.markerDeleteAll()

    def setAnnotationEnabled(self, enabled):
        """Enable / disable annotation"""
        self._annotation_enabled = enabled
        self._updatemarginwidth()
        self.setMouseTracking(enabled)
        if not enabled:
            self.markerDeleteAll()

    def isAnnotationEnabled(self):
        """True if annotation enabled and available"""
        return self._annotation_enabled

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
            self.setMarginText(i, self._lineannotation(fctx), s)

    def _updatemarkers(self):
        """Update markers which colorizes each line"""
        self._redefinemarkers()
        for i, (fctx, _origline) in enumerate(self._links):
            m = self._revmarkers.get(fctx.rev())
            if m is not None:
                self.markerAdd(i, m)

    def _redefinemarkers(self):
        """Redefine line markers according to the current revs"""
        curdate = self.ctx.date()[0]

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
        showannmargin = bool(self.isAnnotationEnabled() and self._anncache)
        if showannmargin:
            # add 2 for margin
            maxwidth = 2 + max(len(s) for s in self._anncache.itervalues())
            self.setMarginWidth(2, 'M' * maxwidth)
        else:
            self.setMarginWidth(2, 0)
        self.setMarginSensitivity(2, showannmargin)

class AnnotateThread(QThread):
    'Background thread for annotating a file at a revision'
    def __init__(self, parent=None, diffopts=None):
        super(AnnotateThread, self).__init__(parent)
        self._threadid = None
        self._diffopts = diffopts

    @pyqtSlot(object)
    def start(self, fctx):
        self._fctx = fctx
        super(AnnotateThread, self).start()
        self.data = None

    @pyqtSlot()
    def abort(self):
        threadid = self._threadid
        if threadid is None:
            return
        try:
            thread2._async_raise(threadid, KeyboardInterrupt)
            self.wait()
        except ValueError:
            pass

    def run(self):
        assert self.currentThread() != qApp.thread()
        self._threadid = self.currentThreadId()
        try:
            try:
                data = []
                for (fctx, line), _text in \
                        self._fctx.annotate(True, True, self._diffopts):
                    data.append((fctx, line))
                self.data = data
            except KeyboardInterrupt:
                pass
        finally:
            self._threadid = None
            del self._fctx

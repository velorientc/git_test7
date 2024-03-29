# qscilib.py - Utility codes for QsciScintilla
#
# Copyright 2010 Steve Borho <steve@borho.org>
# Copyright 2010 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import re, os

from mercurial import util

from tortoisehg.util import hglib
from tortoisehg.hgqt import qtlib
from tortoisehg.hgqt.i18n import _

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qsci import *

class _SciImSupport(object):
    """Patch for QsciScintilla to implement improved input method support

    See http://doc.trolltech.com/4.7/qinputmethodevent.html
    """

    PREEDIT_INDIC_ID = QsciScintilla.INDIC_MAX
    """indicator for highlighting preedit text"""

    def __init__(self, sci):
        self._sci = sci
        self._preeditpos = (0, 0)  # (line, index) where preedit text starts
        self._preeditlen = 0
        self._preeditcursorpos = 0  # relative pos where preedit cursor exists
        self._undoactionbegun = False
        self._setuppreeditindic()

    def removepreedit(self):
        """Remove the previous preedit text

        original pos: preedit cursor
        final pos: target cursor
        """
        l, i = self._sci.getCursorPosition()
        i -= self._preeditcursorpos
        self._preeditcursorpos = 0
        try:
            self._sci.setSelection(
                self._preeditpos[0], self._preeditpos[1],
                self._preeditpos[0], self._preeditpos[1] + self._preeditlen)
            self._sci.removeSelectedText()
        finally:
            self._sci.setCursorPosition(l, i)

    def commitstr(self, start, repllen, commitstr):
        """Remove the repl string followed by insertion of the commit string

        original pos: target cursor
        final pos: end of committed text (= start of preedit text)
        """
        l, i = self._sci.getCursorPosition()
        i += start
        self._sci.setSelection(l, i, l, i + repllen)
        self._sci.removeSelectedText()
        self._sci.insert(commitstr)
        self._sci.setCursorPosition(l, i + len(commitstr))
        if commitstr:
            self.endundo()

    def insertpreedit(self, text):
        """Insert preedit text

        original pos: start of preedit text
        final pos: start of preedit text (unchanged)
        """
        if text and not self._preeditlen:
            self.beginundo()
        l, i = self._sci.getCursorPosition()
        self._sci.insert(text)
        self._updatepreeditpos(l, i, len(text))
        if not self._preeditlen:
            self.endundo()

    def movepreeditcursor(self, pos):
        """Move the cursor to the relative pos inside preedit text"""
        self._preeditcursorpos = min(pos, self._preeditlen)
        l, i = self._preeditpos
        self._sci.setCursorPosition(l, i + self._preeditcursorpos)

    def beginundo(self):
        if self._undoactionbegun:
            return
        self._sci.beginUndoAction()
        self._undoactionbegun = True

    def endundo(self):
        if not self._undoactionbegun:
            return
        self._sci.endUndoAction()
        self._undoactionbegun = False

    def _updatepreeditpos(self, l, i, len):
        """Update the indicator and internal state for preedit text"""
        self._sci.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT,
                                self.PREEDIT_INDIC_ID)
        self._preeditpos = (l, i)
        self._preeditlen = len
        if len <= 0:  # have problem on sci
            return
        p = self._sci.positionFromLineIndex(*self._preeditpos)
        q = self._sci.positionFromLineIndex(self._preeditpos[0],
                                            self._preeditpos[1] + len)
        self._sci.SendScintilla(QsciScintilla.SCI_INDICATORFILLRANGE,
                                p, q - p)  # q - p != len

    def _setuppreeditindic(self):
        """Configure the style of preedit text indicator"""
        self._sci.SendScintilla(QsciScintilla.SCI_INDICSETSTYLE,
                                self.PREEDIT_INDIC_ID,
                                QsciScintilla.INDIC_PLAIN)

class Scintilla(QsciScintilla):
    def __init__(self, parent=None):
        super(Scintilla, self).__init__(parent)
        self.autoUseTabs = True
        self.setUtf8(True)
        self.setWrapVisualFlags(QsciScintilla.WrapFlagByBorder)
        self.textChanged.connect(self._resetfindcond)
        self._resetfindcond()
        self.highlightLines = set()
        self._setMultipleSelectionOptions()
        unbindConflictedKeys(self)

    def _setMultipleSelectionOptions(self):
        if hasattr(QsciScintilla, 'SCI_SETMULTIPLESELECTION'):
            self.SendScintilla(QsciScintilla.SCI_SETMULTIPLESELECTION, True)
            self.SendScintilla(QsciScintilla.SCI_SETADDITIONALSELECTIONTYPING,
                               True)
            self.SendScintilla(QsciScintilla.SCI_SETMULTIPASTE,
                               QsciScintilla.SC_MULTIPASTE_EACH)
            self.SendScintilla(QsciScintilla.SCI_SETVIRTUALSPACEOPTIONS,
                               QsciScintilla.SCVS_RECTANGULARSELECTION)

    def read(self, f):
        result = super(Scintilla, self).read(f)
        self.setDefaultEolMode()
        return result

    def inputMethodQuery(self, query):
        if query == Qt.ImMicroFocus:
            return self.cursorRect()
        return super(Scintilla, self).inputMethodQuery(query)

    def inputMethodEvent(self, event):
        if self.isReadOnly():
            return

        self.removeSelectedText()
        self._imsupport.removepreedit()
        self._imsupport.commitstr(event.replacementStart(),
                                  event.replacementLength(),
                                  event.commitString())
        self._imsupport.insertpreedit(event.preeditString())
        for a in event.attributes():
            if a.type == QInputMethodEvent.Cursor:
                self._imsupport.movepreeditcursor(a.start)
            # TODO TextFormat

        event.accept()

    @util.propertycache
    def _imsupport(self):
        return _SciImSupport(self)

    def cursorRect(self):
        """Return a rectangle (in viewport coords) including the cursor"""
        l, i = self.getCursorPosition()
        p = self.positionFromLineIndex(l, i)
        x = self.SendScintilla(QsciScintilla.SCI_POINTXFROMPOSITION, 0, p)
        y = self.SendScintilla(QsciScintilla.SCI_POINTYFROMPOSITION, 0, p)
        w = self.SendScintilla(QsciScintilla.SCI_GETCARETWIDTH)
        return QRect(x, y, w, self.textHeight(l))

    def createStandardContextMenu(self):
        """Create standard context menu; ownership is transferred to caller"""
        menu = QMenu(self)
        if not self.isReadOnly():
            a = menu.addAction(_('&Undo'), self.undo)
            a.setShortcuts(QKeySequence.Undo)
            a.setEnabled(self.isUndoAvailable())
            a = menu.addAction(_('&Redo'), self.redo)
            a.setShortcuts(QKeySequence.Redo)
            a.setEnabled(self.isRedoAvailable())
            menu.addSeparator()
            a = menu.addAction(_('Cu&t'), self.cut)
            a.setShortcuts(QKeySequence.Cut)
            a.setEnabled(self.hasSelectedText())
        a = menu.addAction(_('&Copy'), self.copy)
        a.setShortcuts(QKeySequence.Copy)
        a.setEnabled(self.hasSelectedText())
        if not self.isReadOnly():
            a = menu.addAction(_('&Paste'), self.paste)
            a.setShortcuts(QKeySequence.Paste)
            a = menu.addAction(_('&Delete'), self.removeSelectedText)
            a.setShortcuts(QKeySequence.Delete)
            a.setEnabled(self.hasSelectedText())
        menu.addSeparator()
        a = menu.addAction(_('Select &All'), self.selectAll)
        a.setShortcuts(QKeySequence.SelectAll)

        menu.addSeparator()
        editoptsmenu = menu.addMenu(_('&Editor Options'))
        self._buildEditorOptionsMenu(editoptsmenu)

        return menu

    def _buildEditorOptionsMenu(self, editoptsmenu):
        qsci = QsciScintilla
        wrapmenu = QMenu(_('&Wrap'), editoptsmenu)
        wrapmenu.triggered.connect(self._setWrapModeByMenu)
        for name, mode in ((_('&None', 'wrap mode'), qsci.WrapNone),
                           (_('&Word'), qsci.WrapWord),
                           (_('&Character'), qsci.WrapCharacter)):
            a = wrapmenu.addAction(name)
            a.setCheckable(True)
            a.setChecked(self.wrapMode() == mode)
            a.setData(mode)

        wsmenu = QMenu(_('White&space'), editoptsmenu)
        wsmenu.triggered.connect(self._setWhitespaceVisibilityByMenu)
        for name, mode in ((_('&Visible'), qsci.WsVisible),
                           (_('&Invisible'), qsci.WsInvisible),
                           (_('&AfterIndent'), qsci.WsVisibleAfterIndent)):
            a = wsmenu.addAction(name)
            a.setCheckable(True)
            a.setChecked(self.whitespaceVisibility() == mode)
            a.setData(mode)

        vsmenu = QMenu(_('EOL &Visibility'), editoptsmenu)
        vsmenu.triggered.connect(self._setEolVisibilityByMenu)
        for name, mode in ((_('&Visible'), True),
                           (_('&Invisible'), False)):
            a = vsmenu.addAction(name)
            a.setCheckable(True)
            a.setChecked(self.eolVisibility() == mode)
            a.setData(mode)

        eolmodemenu = None
        tabindentsmenu = None
        acmenu = None
        if not self.isReadOnly():
            eolmodemenu = QMenu(_('EOL &Mode'), editoptsmenu)
            eolmodemenu.triggered.connect(self._setEolModeByMenu)
            for name, mode in ((_('&Windows'), qsci.EolWindows),
                               (_('&Unix'), qsci.EolUnix),
                               (_('&Mac'), qsci.EolMac)):
                a = eolmodemenu.addAction(name)
                a.setCheckable(True)
                a.setChecked(self.eolMode() == mode)
                a.setData(mode)

            tabindentsmenu = QMenu(_('&TAB Inserts'), editoptsmenu)
            tabindentsmenu.triggered.connect(self._setIndentationsUseTabsByMenu)
            for name, mode in ((_('&Auto'), -1),
                               (_('&TAB'), True),
                               (_('&Spaces'), False)):
                a = tabindentsmenu.addAction(name)
                a.setCheckable(True)
                a.setChecked(self.indentationsUseTabs() == mode
                             or (self.autoUseTabs and mode == -1))
                a.setData(mode)

            acmenu = QMenu(_('&Auto-Complete'), editoptsmenu)
            acmenu.triggered.connect(self._setAutoCompletionThresholdByMenu)
            for name, value in ((_('&Enable'), 2),
                                (_('&Disable'), -1)):
                a = acmenu.addAction(name)
                a.setCheckable(True)
                a.setChecked(self.autoCompletionThreshold() == value)
                a.setData(value)

        editoptsmenu.addMenu(wrapmenu)
        editoptsmenu.addSeparator()
        editoptsmenu.addMenu(wsmenu)
        if (tabindentsmenu): editoptsmenu.addMenu(tabindentsmenu)
        editoptsmenu.addSeparator()
        editoptsmenu.addMenu(vsmenu)
        if (eolmodemenu): editoptsmenu.addMenu(eolmodemenu)
        editoptsmenu.addSeparator()
        if (acmenu): editoptsmenu.addMenu(acmenu)

    def saveSettings(self, qs, prefix):
        qs.setValue(prefix+'/wrap', self.wrapMode())
        qs.setValue(prefix+'/whitespace', self.whitespaceVisibility())
        qs.setValue(prefix+'/eol', self.eolVisibility())
        if self.autoUseTabs:
            qs.setValue(prefix+'/usetabs', -1)
        else:
            qs.setValue(prefix+'/usetabs', self.indentationsUseTabs())
        qs.setValue(prefix+'/autocomplete', self.autoCompletionThreshold())

    def loadSettings(self, qs, prefix):
        self.setWrapMode(qs.value(prefix+'/wrap').toInt()[0])
        self.setWhitespaceVisibility(qs.value(prefix+'/whitespace').toInt()[0])
        self.setEolVisibility(qs.value(prefix+'/eol').toBool())
        self.setIndentationsUseTabs(qs.value(prefix+'/usetabs').toInt()[0])
        self.setDefaultEolMode()
        self.setAutoCompletionThreshold(qs.value(prefix+'/autocomplete').toInt()[0])


    @pyqtSlot(unicode, bool, bool, bool)
    def find(self, exp, icase=True, wrap=False, forward=True):
        """Find the next/prev occurence; returns True if found

        This method tries to imitate the behavior of QTextEdit.find(),
        unlike combo of QsciScintilla.findFirst() and findNext().
        """
        cond = (exp, True, not icase, False, wrap, forward)
        if cond == self.__findcond:
            return self.findNext()
        else:
            self.__findcond = cond
            return self.findFirst(*cond)

    @pyqtSlot()
    def _resetfindcond(self):
        self.__findcond = ()

    @pyqtSlot(unicode, bool)
    def highlightText(self, match, icase=False):
        """Highlight text matching to the given regexp pattern [unicode]

        The previous highlight is cleared automatically.
        """
        try:
            flags = 0
            if icase:
                flags |= re.IGNORECASE
            pat = re.compile(unicode(match).encode('utf-8'), flags)
        except re.error:
            return  # it could be partial pattern while user typing

        self.clearHighlightText()
        self.SendScintilla(self.SCI_SETINDICATORCURRENT,
                           self._highlightIndicator)

        if len(match) == 0:
            return

        # NOTE: pat and target text are *not* unicode because scintilla
        # requires positions in byte. For accuracy, it should do pattern
        # match in unicode, then calculating byte length of substring::
        #
        #     text = unicode(self.text())
        #     for m in pat.finditer(text):
        #         p = len(text[:m.start()].encode('utf-8'))
        #         self.SendScintilla(self.SCI_INDICATORFILLRANGE,
        #             p, len(m.group(0).encode('utf-8')))
        #
        # but it doesn't to avoid possible performance issue.
        for m in pat.finditer(unicode(self.text()).encode('utf-8')):
            self.SendScintilla(self.SCI_INDICATORFILLRANGE,
                               m.start(), m.end() - m.start())
            line = self.lineIndexFromPosition(m.start())[0]
            self.highlightLines.add(line)

    @pyqtSlot()
    def clearHighlightText(self):
        self.SendScintilla(self.SCI_SETINDICATORCURRENT,
                           self._highlightIndicator)
        self.SendScintilla(self.SCI_INDICATORCLEARRANGE, 0, self.length())
        self.highlightLines.clear()

    @util.propertycache
    def _highlightIndicator(self):
        """Return indicator number for highlight after initializing it"""
        id = self._imsupport.PREEDIT_INDIC_ID - 1
        self.SendScintilla(self.SCI_INDICSETSTYLE, id, self.INDIC_ROUNDBOX)
        self.SendScintilla(self.SCI_INDICSETUNDER, id, True)
        self.SendScintilla(self.SCI_INDICSETFORE, id, 0x00ffff) # 0xbbggrr
        # document says alpha value is 0 to 255, but it looks 0 to 100
        self.SendScintilla(self.SCI_INDICSETALPHA, id, 100)
        return id

    def showHScrollBar(self, show=True):
        self.SendScintilla(self.SCI_SETHSCROLLBAR, show)

    def setDefaultEolMode(self):
        if self.lines():
            mode = qsciEolModeFromLine(unicode(self.text(0)))
        else:
            mode = qsciEolModeFromOs()
        self.setEolMode(mode)
        return mode

    @pyqtSlot(QAction)
    def _setWrapModeByMenu(self, action):
        mode, _ok = action.data().toInt()
        self.setWrapMode(mode)

    @pyqtSlot(QAction)
    def _setWhitespaceVisibilityByMenu(self, action):
        mode, _ok = action.data().toInt()
        self.setWhitespaceVisibility(mode)

    @pyqtSlot(QAction)
    def _setEolVisibilityByMenu(self, action):
        visible = action.data().toBool()
        self.setEolVisibility(visible)

    @pyqtSlot(QAction)
    def _setEolModeByMenu(self, action):
        mode, _ok = action.data().toInt()
        self.setEolMode(mode)

    @pyqtSlot(QAction)
    def _setIndentationsUseTabsByMenu(self, action):
        mode, _ok = action.data().toInt()
        self.setIndentationsUseTabs(mode)

    def setIndentationsUseTabs(self, tabs):
        self.autoUseTabs = (tabs == -1)
        if self.autoUseTabs and self.lines():
            tabs = findTabIndentsInLines(hglib.fromunicode(self.text()))
        super(Scintilla, self).setIndentationsUseTabs(tabs)

    @pyqtSlot(QAction)
    def _setAutoCompletionThresholdByMenu(self, action):
        thresh, _ok = action.data().toInt()
        self.setAutoCompletionThreshold(thresh)

    def lineNearPoint(self, point):
        """Return the closest line to the pixel position; similar to lineAt(),
        but returns valid line number even if no character fount at point"""
        # lineAt() uses the strict request, SCI_POSITIONFROMPOINTCLOSE
        chpos = self.SendScintilla(self.SCI_POSITIONFROMPOINT,
                                   point.x(), point.y())
        return self.SendScintilla(self.SCI_LINEFROMPOSITION, chpos)

    # compability mode with QScintilla from Ubuntu 10.04
    if not hasattr(QsciScintilla, 'HiddenIndicator'):
        HiddenIndicator = QsciScintilla.INDIC_HIDDEN
    if not hasattr(QsciScintilla, 'PlainIndicator'):
        PlainIndicator = QsciScintilla.INDIC_PLAIN
    if not hasattr(QsciScintilla, 'StrikeIndicator'):
        StrikeIndicator = QsciScintilla.INDIC_STRIKE

    if not hasattr(QsciScintilla, 'indicatorDefine'):
        def indicatorDefine(self, style, indicatorNumber=-1):
            # compatibility layer allows only one indicator to be defined
            if indicatorNumber == -1:
                indicatorNumber = 1
            self.SendScintilla(self.SCI_INDICSETSTYLE, indicatorNumber, style)
            return indicatorNumber

    if not hasattr(QsciScintilla, 'setIndicatorDrawUnder'):
        def setIndicatorDrawUnder(self, under, indicatorNumber):
            self.SendScintilla(self.SCI_INDICSETUNDER, indicatorNumber, under)

    if not hasattr(QsciScintilla, 'setIndicatorForegroundColor'):
        def setIndicatorForegroundColor(self, color, indicatorNumber):
            self.SendScintilla(self.SCI_INDICSETFORE, indicatorNumber, color)
            self.SendScintilla(self.SCI_INDICSETALPHA, indicatorNumber,
                               color.alpha())

    if not hasattr(QsciScintilla, 'clearIndicatorRange'):
        def clearIndicatorRange(self, lineFrom, indexFrom, lineTo, indexTo,
                                indicatorNumber):
            start = self.positionFromLineIndex(lineFrom, indexFrom)
            finish = self.positionFromLineIndex(lineTo, indexTo)

            self.SendScintilla(self.SCI_SETINDICATORCURRENT, indicatorNumber)
            self.SendScintilla(self.SCI_INDICATORCLEARRANGE,
                               start, finish - start)

    if not hasattr(QsciScintilla, 'fillIndicatorRange'):
        def fillIndicatorRange(self, lineFrom, indexFrom, lineTo, indexTo,
                               indicatorNumber):
            start = self.positionFromLineIndex(lineFrom, indexFrom)
            finish = self.positionFromLineIndex(lineTo, indexTo)

            self.SendScintilla(self.SCI_SETINDICATORCURRENT, indicatorNumber)
            self.SendScintilla(self.SCI_INDICATORFILLRANGE,
                               start, finish - start)


class SearchToolBar(QToolBar):
    conditionChanged = pyqtSignal(unicode, bool, bool)
    """Emitted (pattern, icase, wrap) when search condition changed"""

    searchRequested = pyqtSignal(unicode, bool, bool, bool)
    """Emitted (pattern, icase, wrap, forward) when requested"""

    def __init__(self, parent=None, hidable=False):
        super(SearchToolBar, self).__init__(_('Search'), parent,
                                            objectName='search',
                                            iconSize=QSize(16, 16))
        if hidable:
            self._close_button = QToolButton(icon=qtlib.geticon('window-close'),
                                             shortcut=Qt.Key_Escape)
            self._close_button.clicked.connect(self.hide)
            self.addWidget(self._close_button)
            self.addWidget(qtlib.Spacer(2, 2))

        self._le = QLineEdit()
        if hasattr(self._le, 'setPlaceholderText'): # Qt >= 4.7
            self._le.setPlaceholderText(_('### regular expression ###'))
        else:
            self._lbl = QLabel(_('Regexp:'),
                               toolTip=_('Regular expression search pattern'))
            self.addWidget(self._lbl)
            self._lbl.setBuddy(self._le)
        self._le.returnPressed.connect(self._emitSearchRequested)
        self.addWidget(self._le)
        self.addWidget(qtlib.Spacer(4, 4))
        self._chk = QCheckBox(_('Ignore case'))
        self.addWidget(self._chk)
        self._wrapchk = QCheckBox(_('Wrap search'))
        self.addWidget(self._wrapchk)
        self._btprev = QPushButton(_('Prev'), icon=qtlib.geticon('go-up'),
                                   iconSize=QSize(16, 16))
        self._btprev.clicked.connect(
            lambda: self._emitSearchRequested(forward=False))
        self.addWidget(self._btprev)
        self._bt = QPushButton(_('Next'), icon=qtlib.geticon('go-down'),
                               iconSize=QSize(16, 16))
        self._bt.clicked.connect(self._emitSearchRequested)
        self._le.textChanged.connect(self._updateSearchButtons)
        self.addWidget(self._bt)

        self.setFocusProxy(self._le)
        self.setStyleSheet(qtlib.tbstylesheet)

        self._settings = QSettings()
        self._settings.beginGroup('searchtoolbar')
        self.searchRequested.connect(self._writesettings)
        self._readsettings()

        self._le.textChanged.connect(self._emitConditionChanged)
        self._chk.toggled.connect(self._emitConditionChanged)
        self._wrapchk.toggled.connect(self._emitConditionChanged)

        self._updateSearchButtons()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.FindNext):
            self._emitSearchRequested(forward=True)
            return
        if event.matches(QKeySequence.FindPrevious):
            self._emitSearchRequested(forward=False)
            return
        if event.key() in (Qt.Key_Enter, Qt.Key_Return):
            return  # handled by returnPressed
        super(SearchToolBar, self).keyPressEvent(event)

    def wheelEvent(self, event):
        if event.delta() > 0:
            self._emitSearchRequested(forward=False)
            return
        if event.delta() < 0:
            self._emitSearchRequested(forward=True)
            return
        super(SearchToolBar, self).wheelEvent(event)

    def setVisible(self, visible=True):
        super(SearchToolBar, self).setVisible(visible)
        if visible:
            self._le.setFocus()
            self._le.selectAll()

    def _readsettings(self):
        self.setCaseInsensitive(self._settings.value('icase', False).toBool())
        self.setWrapAround(self._settings.value('wrap', False).toBool())

    @pyqtSlot()
    def _writesettings(self):
        self._settings.setValue('icase', self.caseInsensitive())
        self._settings.setValue('wrap', self.wrapAround())

    @pyqtSlot()
    def _emitConditionChanged(self):
        self.conditionChanged.emit(self.pattern(), self.caseInsensitive(),
                                   self.wrapAround())

    @pyqtSlot()
    def _emitSearchRequested(self, forward=True):
        self.searchRequested.emit(self.pattern(), self.caseInsensitive(),
                                  self.wrapAround(), forward)

    @pyqtSlot()
    def _updateSearchButtons(self):
        enabled = bool(self._le.text())
        self._btprev.setEnabled(enabled)
        self._bt.setEnabled(enabled)

    def pattern(self):
        """Returns the current search pattern [unicode]"""
        return self._le.text()

    def setPattern(self, text):
        """Set the search pattern [unicode]"""
        self._le.setText(text)

    def caseInsensitive(self):
        """True if case-insensitive search is requested"""
        return self._chk.isChecked()

    def setCaseInsensitive(self, icase):
        self._chk.setChecked(icase)

    def wrapAround(self):
        """True if wrap search is requested"""
        return self._wrapchk.isChecked()

    def setWrapAround(self, wrap):
        self._wrapchk.setChecked(wrap)

    @pyqtSlot(unicode)
    def search(self, text):
        """Request search with the given pattern"""
        self.setPattern(text)
        self._emitSearchRequested()

class KeyPressInterceptor(QObject):
    """Grab key press events important for dialogs

    Usage::
        sci = qscilib.Scintilla(self)
        sci.installEventFilter(KeyPressInterceptor(self))
    """

    def __init__(self, parent=None, keys=None, keyseqs=None):
        super(KeyPressInterceptor, self).__init__(parent)
        self._keys = set((Qt.Key_Escape,))
        self._keyseqs = set((QKeySequence.Refresh,))
        if keys:
            self._keys.update(keys)
        if keyseqs:
            self._keyseqs.update(keyseqs)

    def eventFilter(self, watched, event):
        if event.type() != QEvent.KeyPress:
            return super(KeyPressInterceptor, self).eventFilter(
                watched, event)
        if self._isinterceptable(event):
            event.ignore()
            return True
        return False

    def _isinterceptable(self, event):
        if event.key() in self._keys:
            return True
        if util.any(event.matches(e) for e in self._keyseqs):
            return True
        return False

def unbindConflictedKeys(sci):
    cmdset = sci.standardCommands()
    try:
        cmd = cmdset.boundTo(QKeySequence('CTRL+L'))
        if cmd:
            cmd.setKey(0)
    except AttributeError:  # old QScintilla does not have boundTo()
        pass

def qsciEolModeFromOs():
    if os.name.startswith('nt'):
        return QsciScintilla.EolWindows
    else:
        return QsciScintilla.EolUnix

def qsciEolModeFromLine(line):
    if line.endswith('\r\n'):
        return QsciScintilla.EolWindows
    elif line.endswith('\r'):
        return QsciScintilla.EolMac
    elif line.endswith('\n'):
        return QsciScintilla.EolUnix
    else:
        return qsciEolModeFromOs()

def findTabIndentsInLines(lines, linestocheck=100):
    for line in lines[:linestocheck]:
        if line.startswith(' '):
            return False
        elif line.startswith('\t'):
            return True
    return False # Use spaces for indents default

def fileEditor(filename, **opts):
    'Open a simple modal file editing dialog'
    dialog = QDialog()
    dialog.setWindowFlags(dialog.windowFlags()
                          & ~Qt.WindowContextHelpButtonHint
                          | Qt.WindowMaximizeButtonHint)
    dialog.setWindowTitle(filename)
    dialog.setLayout(QVBoxLayout())
    editor = Scintilla()
    editor.setBraceMatching(QsciScintilla.SloppyBraceMatch)
    editor.installEventFilter(KeyPressInterceptor(dialog))
    editor.setMarginLineNumbers(1, True)
    editor.setMarginWidth(1, '000')
    editor.setLexer(QsciLexerProperties())
    if opts.get('foldable'):
        editor.setFolding(QsciScintilla.BoxedTreeFoldStyle)
    dialog.layout().addWidget(editor)

    searchbar = SearchToolBar(dialog, hidable=True)
    searchbar.searchRequested.connect(editor.find)
    searchbar.conditionChanged.connect(editor.highlightText)
    searchbar.hide()
    def showsearchbar():
        text = editor.selectedText()
        if text:
            searchbar.setPattern(text)
        searchbar.show()
        searchbar.setFocus(Qt.OtherFocusReason)
    qtlib.newshortcutsforstdkey(QKeySequence.Find, dialog, showsearchbar)
    dialog.layout().addWidget(searchbar)

    BB = QDialogButtonBox
    bb = QDialogButtonBox(BB.Save|BB.Cancel)
    bb.accepted.connect(dialog.accept)
    bb.rejected.connect(dialog.reject)
    dialog.layout().addWidget(bb)

    s = QSettings()
    geomname = 'editor-geom'
    desktopgeom = qApp.desktop().availableGeometry()
    dialog.resize(desktopgeom.size() * 0.5)
    dialog.restoreGeometry(s.value(geomname).toByteArray())

    ret = QDialog.Rejected
    try:
        f = QFile(filename)
        f.open(QIODevice.ReadOnly)
        editor.read(f)
        editor.setModified(False)

        ret = dialog.exec_()
        if ret == QDialog.Accepted:
            f = QFile(filename)
            f.open(QIODevice.WriteOnly)
            editor.write(f)
        s.setValue(geomname, dialog.saveGeometry())
    except EnvironmentError, e:
        qtlib.WarningMsgBox(_('Unable to read/write config file'),
                            hglib.tounicode(str(e)), parent=dialog)
    return ret

# qscilib.py - Utility codes for QsciScintilla
#
# Copyright 2010 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

from mercurial import util

from tortoisehg.hgqt import qtlib
from tortoisehg.hgqt.i18n import _

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qsci import QsciScintilla

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
        self._preeditcursorpos = pos
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

    _stdMenu = None

    def __init__(self, parent=None):
        super(Scintilla, self).__init__(parent)
        self.setUtf8(True)
        self.textChanged.connect(self._resetfindcond)
        self._resetfindcond()

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
        """Create standard context menu"""
        if not self._stdMenu:
            self._stdMenu = QMenu(self)
        else:
            self._stdMenu.clear()
        if not self.isReadOnly():
            a = self._stdMenu.addAction(_('Undo'), self.undo, QKeySequence.Undo)
            a.setEnabled(self.isUndoAvailable())
            a = self._stdMenu.addAction(_('Redo'), self.redo, QKeySequence.Redo)
            a.setEnabled(self.isRedoAvailable())
            self._stdMenu.addSeparator()
            a = self._stdMenu.addAction(_('Cut'), self.cut, QKeySequence.Cut)
            a.setEnabled(self.hasSelectedText())
        a = self._stdMenu.addAction(_('Copy'), self.copy, QKeySequence.Copy)
        a.setEnabled(self.hasSelectedText())
        if not self.isReadOnly():
            self._stdMenu.addAction(_('Paste'), self.paste, QKeySequence.Paste)
            a = self._stdMenu.addAction(_('Delete'), self.removeSelectedText,
                               QKeySequence.Delete)
            a.setEnabled(self.hasSelectedText())
        self._stdMenu.addSeparator()
        self._stdMenu.addAction(_('Select All'),
                                self.selectAll, QKeySequence.SelectAll)

        return self._stdMenu

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

class SearchToolBar(QToolBar):
    conditionChanged = pyqtSignal(unicode, bool, bool)
    """Emitted (pattern, icase, wrap) when search condition changed"""

    searchRequested = pyqtSignal(unicode, bool, bool, bool)
    """Emitted (pattern, icase, wrap, forward) when requested"""

    def __init__(self, parent=None, hidable=False, settings=None):
        super(SearchToolBar, self).__init__(_('Search'), parent,
                                            objectName='search',
                                            iconSize=QSize(16, 16))
        if hidable:
            self._close_button = QToolButton(icon=qtlib.geticon('close'),
                                             shortcut=Qt.Key_Escape)
            self._close_button.clicked.connect(self.hide)
            self.addWidget(self._close_button)

        self._lbl = QLabel(_('Regexp:'),
                           toolTip=_('Regular expression search pattern'))
        self.addWidget(self._lbl)
        self._le = QLineEdit()
        self._le.returnPressed.connect(self._emitSearchRequested)
        self._lbl.setBuddy(self._le)
        self.addWidget(self._le)
        self._chk = QCheckBox(_('Ignore case'))
        self.addWidget(self._chk)
        self._wrapchk = QCheckBox(_('Wrap search'))
        self.addWidget(self._wrapchk)
        self._bt = QPushButton(_('Search'), enabled=False)
        self._bt.clicked.connect(self._emitSearchRequested)
        self._le.textChanged.connect(lambda s: self._bt.setEnabled(bool(s)))
        self.addWidget(self._bt)

        self.setFocusProxy(self._le)

        def defaultsettings():
            s = QSettings()
            s.beginGroup('searchtoolbar')
            return s
        self._settings = settings or defaultsettings()
        self.searchRequested.connect(self._writesettings)
        self._readsettings()

        self._le.textChanged.connect(self._emitConditionChanged)
        self._chk.toggled.connect(self._emitConditionChanged)
        self._wrapchk.toggled.connect(self._emitConditionChanged)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.FindNext):
            self._emitSearchRequested(forward=True)
            return
        if event.matches(QKeySequence.FindPrevious):
            self._emitSearchRequested(forward=False)
            return
        super(SearchToolBar, self).keyPressEvent(event)

    def wheelEvent(self, event):
        if event.delta() > 0:
            self._emitSearchRequested(forward=False)
            return
        if event.delta() < 0:
            self._emitSearchRequested(forward=True)
            return
        super(SearchToolBar, self).wheelEvent(event)

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

# qscilib.py - Utility codes for QsciScintilla
#
# Copyright 2010 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

from mercurial import util

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
    def __init__(self, parent=None):
        super(Scintilla, self).__init__(parent)
        self.setUtf8(True)

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

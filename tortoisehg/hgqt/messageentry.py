# messageentry.py - TortoiseHg's commit message editng widget
#
# Copyright 2011 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qsci import QsciScintilla, QsciLexerMakefile

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, qscilib

import re

class MessageEntry(qscilib.Scintilla):

    def __init__(self, parent, getCheckedFunc=None):
        super(MessageEntry, self).__init__(parent)
        self.setEdgeColor(QColor('LightSalmon'))
        self.setEdgeMode(QsciScintilla.EdgeLine)
        self.setReadOnly(False)
        self.setMarginWidth(1, 0)
        self.setFont(qtlib.getfont('fontcomment').font())
        self.setCaretWidth(10)
        self.setCaretLineBackgroundColor(QColor("#e6fff0"))
        self.setCaretLineVisible(True)
        self.setAutoIndent(True)
        self.setAutoCompletionSource(QsciScintilla.AcsAPIs)
        self.setAutoCompletionFillupsEnabled(True)
        self.setMatchedBraceBackgroundColor(Qt.yellow)
        self.setIndentationsUseTabs(False)
        self.setBraceMatching(QsciScintilla.SloppyBraceMatch)
        # http://www.riverbankcomputing.com/pipermail/qscintilla/2009-February/000461.html
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # default message entry widgets to word wrap, user may override
        self.setWrapMode(QsciScintilla.WrapWord)

        self.getChecked = getCheckedFunc
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menuRequested)
        self.applylexer()

        self._re_boundary = re.compile('[0-9i#]+\.|\(?[0-9i#]+\)|\(@\)')

    def setText(self, text):
        result = super(MessageEntry, self).setText(text)
        self.setDefaultEolMode()
        return result

    def applylexer(self):
        font = qtlib.getfont('fontcomment').font()
        self.fontHeight = QFontMetrics(font).height()
        if QSettings().value('msgentry/lexer', True).toBool():
            self.setLexer(QsciLexerMakefile(self))
            self.lexer().setColor(QColor(Qt.red), QsciLexerMakefile.Error)
            self.lexer().setFont(font)
        else:
            self.setLexer(None)
            self.setFont(font)

    def menuRequested(self, point):
        line = self.lineAt(point)
        point = self.viewport().mapToGlobal(point)
        lexerenabled = self.lexer() is not None

        def apply():
            firstline, firstcol, lastline, lastcol = self.getSelection()
            if firstline < 0:
                line = 0
            else:
                line = firstline
            self.beginUndoAction()
            while True:
                line = self.reflowBlock(line)
                if line is None or (line > lastline > -1):
                    break
            self.endUndoAction()

        def paste():
            files = self.getChecked()
            self.insert('\n'.join(files))
        def settings():
            from tortoisehg.hgqt.settings import SettingsDialog
            dlg = SettingsDialog(True, focus='tortoisehg.summarylen')
            dlg.exec_()
        def togglelexer():
            QSettings().setValue('msgentry/lexer', not lexerenabled)
            self.applylexer()

        menu = self.createStandardContextMenu()
        menu.addSeparator()
        a = menu.addAction(_('Syntax Highlighting'))
        a.setCheckable(True)
        a.setChecked(lexerenabled)
        a.triggered.connect(togglelexer)
        menu.addSeparator()
        if self.getChecked:
            action = menu.addAction(_('Paste &Filenames'))
            action.triggered.connect(paste)
        for name, func in [(_('App&ly Format'), apply),
                           (_('C&onfigure Format'), settings)]:
            def add(name, func):
                action = menu.addAction(name)
                action.triggered.connect(func)
            add(name, func)
        return menu.exec_(point)

    def refresh(self, repo):
        self.setEdgeColumn(repo.summarylen)
        self.setIndentationWidth(repo.tabwidth)
        self.setTabWidth(repo.tabwidth)
        self.summarylen = repo.summarylen

    def reflowBlock(self, line):
        lines = self.text().split('\n', QString.KeepEmptyParts)
        if line >= len(lines):
            return None
        if not len(lines[line]) > 1:
            return line+1

        # find boundaries (empty lines or bounds)
        def istopboundary(linetext):
            # top boundary lines are those that begin with a Markdown style marker
            # or are empty
            if not linetext:
                return True
            if (linetext[0] in '#-*+'):
                return True
            if len(linetext) >= 2:
                if linetext[:2] in ('> ', '| '):
                    return True
                if self._re_boundary.match(linetext):
                    return True
            return False

        def isbottomboundary(linetext):
            # bottom boundary lines are those that end with a period
            # or are empty
            if not linetext or linetext[-1] == '.':
                return True
            return False

        def isanyboundary(linetext):
            if len(linetext) >= 3:
                if linetext[:3] in ('~~~', '```', '---', '==='):
                    return True
            return False

        b = line
        while b and len(lines[b-1]) > 1:
            linetext = unicode(lines[b].trimmed())
            if istopboundary(linetext) or isanyboundary(linetext):
                break
            if b >= 1:
                nextlinetext = unicode(lines[b - 1].trimmed())
                if isbottomboundary(nextlinetext) \
                        or isanyboundary(nextlinetext):
                    break
            b -= 1

        e = line
        while e+1 < len(lines) and len(lines[e+1]) > 1:
            linetext = unicode(lines[e].trimmed())
            if isbottomboundary(linetext) or isanyboundary(linetext):
                break
            nextlinetext =  unicode(lines[e+1].trimmed())
            if isanyboundary(nextlinetext) or istopboundary(nextlinetext):
                break
            e += 1

        if b == e == 0:
            return line + 1

        group = QStringList([lines[l].simplified() for l in xrange(b, e+1)])
        firstlinetext = unicode(lines[b])
        if firstlinetext:
            indentcount = len(firstlinetext) - len(firstlinetext.lstrip())
            firstindent = firstlinetext[:indentcount]
        else:
            indentcount = 0
            firstindent = ''
        sentence = group.join(' ')
        parts = sentence.split(' ', QString.SkipEmptyParts)

        outlines = QStringList()
        line = QStringList()
        partslen = indentcount - 1
        for part in parts:
            if partslen + len(line) + len(part) + 1 > self.summarylen:
                if line:
                    linetext = line.join(' ')
                    if len(outlines) == 0 and firstindent:
                        linetext = firstindent + linetext
                    outlines.append(linetext)
                line, partslen = QStringList(), 0
            line.append(part)
            partslen += len(part)
        if line:
            outlines.append(line.join(' '))

        self.beginUndoAction()
        self.setSelection(b, 0, e+1, 0)
        self.removeSelectedText()
        self.insertAt(outlines.join('\n')+'\n', b, 0)
        self.endUndoAction()
        self.setCursorPosition(b, 0)
        return b + len(outlines) + 1

    def moveCursorToEnd(self):
        lines = self.lines()
        if lines:
            lines -= 1
            pos = self.lineLength(lines)
            self.setCursorPosition(lines, pos)
            self.ensureLineVisible(lines)
            self.horizontalScrollBar().setSliderPosition(0)

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_E:
            line, col = self.getCursorPosition()
            self.reflowBlock(line)
        elif event.key() == Qt.Key_Backtab:
            event.accept()
            newev = QKeyEvent(event.type(), Qt.Key_Tab, Qt.ShiftModifier)
            super(MessageEntry, self).keyPressEvent(newev)
        else:
            super(MessageEntry, self).keyPressEvent(event)

    def resizeEvent(self, event):
        super(MessageEntry, self).resizeEvent(event)
        self.showHScrollBar(self.frameGeometry().height() > self.fontHeight * 3)

    def minimumSizeHint(self):
        size = super(MessageEntry, self).minimumSizeHint()
        size.setHeight(self.fontHeight * 3 / 2)
        return size

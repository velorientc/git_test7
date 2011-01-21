# rejects.py - TortoiseHg patch reject editor
#
# Copyright 2011 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

import cStringIO
import os

from mercurial import hg, util, patch, commands
from hgext import record

from tortoisehg.util import hglib
from tortoisehg.util.patchctx import patchctx
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, qscilib, lexers

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import Qsci

qsci = Qsci.QsciScintilla

# TODO
# pass ui to patchctx.longsummary() so patchctx does not need a repository

class RejectsDialog(QDialog):
    def __init__(self, path, parent):
        super(RejectsDialog, self).__init__(parent)

        self.setLayout(QVBoxLayout())
        editor = qscilib.Scintilla()
        editor.setBraceMatching(qsci.SloppyBraceMatch)
        editor.setMarginLineNumbers(1, True)
        editor.setMarginWidth(1, '000')
        editor.setFolding(qsci.BoxedTreeFoldStyle)
        editor.installEventFilter(qscilib.KeyPressInterceptor(self))
        self.baseLineColor = editor.markerDefine(qsci.Background, -1)
        editor.setMarkerBackgroundColor(QColor('lightblue'), self.baseLineColor)
        self.layout().addWidget(editor, 3)

        searchbar = qscilib.SearchToolBar(self, hidable=True)
        searchbar.searchRequested.connect(editor.find)
        searchbar.conditionChanged.connect(editor.highlightText)
        searchbar.hide()
        def showsearchbar():
            searchbar.show()
            searchbar.setFocus(Qt.OtherFocusReason)
        QShortcut(QKeySequence.Find, self, showsearchbar)
        self.layout().addWidget(searchbar)

        hbox = QHBoxLayout()
        self.layout().addLayout(hbox)
        self.chunklist = QListWidget(self)
        self.chunklist.currentRowChanged.connect(self.showChunk)
        hbox.addWidget(self.chunklist, 1)

        self.rejectbrowser = RejectBrowser(self)
        hbox.addWidget(self.rejectbrowser, 5)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Save|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.layout().addWidget(bb)

        s = QSettings()
        self.restoreGeometry(s.value('rejects/geometry').toByteArray())

        contents = hglib.tounicode(open(path, 'rb').read())
        self.setWindowTitle(_('Merge rejected patch chunks into %s') %
                            hglib.tounicode(path))
        editor.setText(contents)
        editor.setModified(False)
        lexer = lexers.get_lexer(path, contents, self)
        editor.setLexer(lexer)
        if '\r\n' in contents:
            editor.setEolMode(qsci.EolWindows)
        else:
            editor.setEolMode(qsci.EolUnix)
        self.editor = editor

        buf = cStringIO.StringIO()
        buf.write('diff -r aaaaaaaaaaaa -r bbbbbbbbbbb %s\n' % path)
        buf.write(open(path + '.rej', 'r').read())
        buf.seek(0)
        self.chunks = record.parsepatch(buf)[1:]
        for chunk in self.chunks:
            self.chunklist.addItem(str(chunk.fromline))

    @pyqtSlot(int)
    def showChunk(self, row):
        if row == -1:
            return
        buf = cStringIO.StringIO()
        chunk = self.chunks[row]
        chunk.write(buf)
        self.rejectbrowser.showChunk(buf.getvalue().splitlines()[1:])
        self.editor.setCursorPosition(chunk.fromline, 0)
        self.editor.markerDeleteAll(-1)
        self.editor.markerAdd(chunk.fromline, self.baseLineColor)

    def accept(self):
        f = util.atomictempfile(filename, 'wb', createmode=None)
        f.write(hglib.fromunicode(self.editor.text()))
        f.rename()

    def closeEvent(self, event):
        s = QSettings()
        s.setValue('rejects/geometry', self.saveGeometry())

class RejectBrowser(qscilib.Scintilla):
    'Display a rejected diff hunk in an easily copy/pasted format'
    def __init__(self, parent):
        super(RejectBrowser, self).__init__(parent)

        self.setFrameStyle(0)
        self.setReadOnly(True)
        self.setUtf8(True)

        self.installEventFilter(qscilib.KeyPressInterceptor(self))
        self.setCaretLineVisible(False)

        self.setMarginType(1, qsci.SymbolMargin)
        self.setMarginLineNumbers(1, False)
        self.setMarginWidth(1, QFontMetrics(self.font()).width('XX'))
        self.setMarginSensitivity(1, True)
        self.addedMark = self.markerDefine(qsci.Plus, -1)
        self.removedMark = self.markerDefine(qsci.Minus, -1)
        self.addedColor = self.markerDefine(qsci.Background, -1)
        self.removedColor = self.markerDefine(qsci.Background, -1)
        self.setMarkerBackgroundColor(QColor('lightgreen'), self.addedColor)
        self.setMarkerBackgroundColor(QColor('cyan'), self.removedColor)
        mask = (1 << self.addedMark) | (1 << self.removedMark) | \
               (1 << self.addedColor) | (1 << self.removedColor)
        self.setMarginMarkerMask(1, mask)
        lexer = lexers.get_diff_lexer(self)
        self.setLexer(lexer)

    def showChunk(self, lines):
        utext = []
        added = []
        removed = []
        for i, line in enumerate(lines):
            utext.append(hglib.tounicode(line[1:]))
            if line[0] == '+':
                added.append(i)
            elif line[0] == '-':
                removed.append(i)
        self.markerDeleteAll(-1)
        self.setText(u'\n'.join(utext))
        for i in added:
            self.markerAdd(i, self.addedMark)
            self.markerAdd(i, self.addedColor)
        for i in removed:
            self.markerAdd(i, self.removedMark)
            self.markerAdd(i, self.removedColor)

def run(ui, *pats, **opts):
    'for testing purposes only'
    from tortoisehg.util import paths
    from tortoisehg.hgqt import thgrepo
    repo = thgrepo.repository(ui, path=paths.find_root())
    dlg = RejectsDialog(pats[0], None)
    desktopgeom = qApp.desktop().availableGeometry()
    dlg.resize(desktopgeom.size() * 0.8)
    return dlg

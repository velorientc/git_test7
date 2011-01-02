# chunks.py - TortoiseHg patch/diff browser and editor
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

import cStringIO

from hgext import record

from tortoisehg.util import hglib
from tortoisehg.util.patchctx import patchctx
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, thgrepo, qscilib, lexers
from tortoisehg.hgqt import filelistmodel, filelistview, fileview

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import Qsci

qsci = Qsci.QsciScintilla

class ChunksWidget(QWidget):

    linkActivated = pyqtSignal(QString)
    showMessage = pyqtSignal(QString)

    def __init__(self, repo, ctx, parent):
        QWidget.__init__(self, parent)

        self.repo = repo

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setMargin(0)
        layout.setContentsMargins(2, 2, 2, 2)
        self.setLayout(layout)

        self.splitter = QSplitter(self)
        self.splitter.setOrientation(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.layout().addWidget(self.splitter)

        self.filelist = filelistview.HgFileListView(self)

        self.fileListFrame = QFrame(self.splitter)
        self.fileListFrame.setFrameShape(QFrame.NoFrame)
        vbox = QVBoxLayout()
        vbox.setSpacing(0)
        vbox.setMargin(0)
        vbox.addWidget(self.filelist)
        self.fileListFrame.setLayout(vbox)

        self.diffbrowse = DiffBrowser(self.splitter)
        self.diffbrowse.setFont(qtlib.getfont('fontlog').font())
        self.diffbrowse.showMessage.connect(self.showMessage)
        self.diffbrowse.linkActivated.connect(self.linkActivated)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 3)
        self.setContext(ctx or repo.changectx(None))

    @pyqtSlot(object, object, object)
    def displayFile(self, file, rev, status):
        self.diffbrowse.displayFile(file, status)

    def setContext(self, ctx):
        self.filelistmodel = filelistmodel.HgFileListModel(self.repo, self)
        self.filelist.setModel(self.filelistmodel)
        self.filelist.fileRevSelected.connect(self.displayFile)
        self.filelist.clearDisplay.connect(self.diffbrowse.clearDisplay)
        self.diffbrowse.setContext(ctx)
        self.filelistmodel.setContext(ctx)

    def refresh(self):
        f = self.filelist.currentFile()
        ctx = self.filelistmodel._ctx
        if isintance(ctx, patchctx):
            # if patch mtime has not changed, it could return the same ctx
            ctx = self.repo.changectx(ctx.path)
        else:
            self.repo.thginvalidate()
            ctx = self.repo.changectx(ctx.node())
        self.filelistmodel.setContext(ctx)
        if f in ctx:
            self.filelist.selectFile(f)

class DiffBrowser(QFrame):
    """diff browser"""

    linkActivated = pyqtSignal(QString)
    showMessage = pyqtSignal(QString)

    def __init__(self, parent):
        QFrame.__init__(self, parent)

        self.curchunks = []
        self.countselected = 0
        self._ctx = None

        vbox = QVBoxLayout()
        vbox.setContentsMargins(0,0,0,0)
        vbox.setSpacing(0)
        self.setLayout(vbox)

        self.labelhbox = hbox = QHBoxLayout()
        hbox.setContentsMargins(0,0,0,0)
        hbox.setSpacing(0)
        self.layout().addLayout(hbox)
        self.filenamelabel = w = QLabel()
        hbox.addWidget(w)
        w.setWordWrap(True)
        f = w.textInteractionFlags()
        w.setTextInteractionFlags(f | Qt.TextSelectableByMouse)
        w.linkActivated.connect(self.linkActivated)

        self.sumlabel = QLabel()
        hbox.addStretch(1)
        hbox.addWidget(self.sumlabel)

        self.extralabel = w = QLabel()
        w.setWordWrap(True)
        w.linkActivated.connect(self.linkActivated)
        self.layout().addWidget(w)
        w.hide()

        self.sci = qscilib.Scintilla(self)
        self.sci.setFrameStyle(0)
        self.sci.setReadOnly(True)
        self.sci.setUtf8(True)
        self.sci.setWrapMode(qsci.WrapCharacter)
        self.sci.installEventFilter(qscilib.KeyPressInterceptor(self))
        self.sci.setCaretLineVisible(False)

        self.sci.setMarginType(1, qsci.SymbolMargin)
        self.sci.setMarginLineNumbers(1, False)
        self.sci.setMarginWidth(1, QFontMetrics(self.font()).width('XX'))
        self.sci.setMarginSensitivity(1, True)
        self.sci.marginClicked.connect(self.marginClicked)
        self.selected = self.sci.markerDefine(qsci.Plus, -1)
        self.unselected = self.sci.markerDefine(qsci.Minus, -1)
        self.vertical = self.sci.markerDefine(qsci.VerticalLine, -1)
        self.selcolor = self.sci.markerDefine(qsci.Background, -1)
        self.sci.setMarkerBackgroundColor(QColor('#BBFFFF'), self.selcolor)
        mask = (1 << self.selected) | (1 << self.unselected) | \
               (1 << self.vertical) | (1 << self.selcolor)
        self.sci.setMarginMarkerMask(1, mask)

        self.layout().addWidget(self.sci, 1)

        lexer = lexers.get_diff_lexer(self)
        self.sci.setLexer(lexer)
        self.clearDisplay()

    def updateSummary(self):
        self.sumlabel.setText(_('Chunks selected: %d / %d') % (
            self.countselected, len(self.curchunks[1:])))

    @pyqtSlot(int, int, Qt.KeyboardModifiers)
    def marginClicked(self, margin, line, modifiers):
        for chunk in self.curchunks[1:]:
            if line >= chunk.lrange[0] and line < chunk.lrange[1]:
                self.sci.markerDelete(chunk.mline, -1)
                if chunk.selected:
                    self.sci.markerAdd(chunk.mline, self.unselected)
                    chunk.selected = False
                    self.countselected -= 1
                    for i in xrange(*chunk.lrange):
                        self.sci.markerDelete(i, self.selcolor)
                else:
                    self.sci.markerAdd(chunk.mline, self.selected)
                    chunk.selected = True
                    self.countselected += 1
                    for i in xrange(*chunk.lrange):
                        self.sci.markerAdd(i, self.selcolor)
                self.updateSummary()
                return

    def setContext(self, ctx):
        self._ctx = ctx
        self.sci.setTabWidth(ctx._repo.tabwidth)
        if ctx._repo.wsvisible == 'Visible':
            self.sci.setWhitespaceVisibility(qsci.WsVisible)
        elif ctx._repo.wsvisible == 'VisibleAfterIndent':
            self.sci.setWhitespaceVisibility(qsci.WsVisibleAfterIndent)
        else:
            self.sci.setWhitespaceVisibility(qsci.WsInvisible)

    def clearDisplay(self):
        self.sci.clear()
        self.filenamelabel.setText(' ')
        self.extralabel.hide()
        self.curchunks = []
        self.countselected = 0
        self.updateSummary()

    def displayFile(self, filename, status):
        self.clearDisplay()

        fd = fileview.FileData(self._ctx, None, filename, status)

        if fd.elabel:
            self.extralabel.setText(fd.elabel)
            self.extralabel.show()
        else:
            self.extralabel.hide()
        self.filenamelabel.setText(fd.flabel)

        if not fd.isValid() or not fd.diff:
            self.sci.setText(fd.error or '')
            return
        elif type(self._ctx.rev()) is str:
            chunks = self._ctx._files[filename]
        else:
            buf = cStringIO.StringIO()
            buf.write('diff -r XX %s\n' % filename)
            buf.write('\n'.join(fd.diff))
            buf.seek(0)
            chunks = record.parsepatch(buf)

        utext = []
        for chunk in chunks[1:]:
            buf = cStringIO.StringIO()
            chunk.selected = False
            chunk.write(buf)
            chunk.lines = buf.getvalue().splitlines()
            utext += [hglib.tounicode(l) for l in chunk.lines]
        self.sci.setText(u'\n'.join(utext))

        start = 0
        self.sci.markerDeleteAll(-1)
        for chunk in chunks[1:]:
            chunk.lrange = (start, start+len(chunk.lines))
            chunk.mline = start + len(chunk.lines)/2
            for i in xrange(1,len(chunk.lines)-1):
                if start + i == chunk.mline:
                    self.sci.markerAdd(chunk.mline, self.unselected)
                else:
                    self.sci.markerAdd(start+i, self.vertical)
            start += len(chunk.lines)
        self.curchunks = chunks
        self.countselected = 0
        self.updateSummary()

def run(ui, *pats, **opts):
    'for testing purposes only'
    from tortoisehg.util import paths
    repo = thgrepo.repository(ui, path=paths.find_root())
    dlg = ChunksWidget(repo, None, None)
    desktopgeom = qApp.desktop().availableGeometry()
    dlg.resize(desktopgeom.size() * 0.8)
    return dlg

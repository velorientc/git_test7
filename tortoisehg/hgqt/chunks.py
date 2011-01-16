# chunks.py - TortoiseHg patch/diff browser and editor
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

import cStringIO
import os

from mercurial import hg, util, patch
from hgext import record

from tortoisehg.util import hglib
from tortoisehg.util.patchctx import patchctx
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, thgrepo, qscilib, lexers, wctxactions
from tortoisehg.hgqt import filelistmodel, filelistview, fileview

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import Qsci

qsci = Qsci.QsciScintilla

class ChunksWidget(QWidget):

    linkActivated = pyqtSignal(QString)
    showMessage = pyqtSignal(QString)
    chunksSelected = pyqtSignal(bool)
    fileSelected = pyqtSignal(bool)
    fileModelEmpty = pyqtSignal(bool)
    fileModified = pyqtSignal()

    def __init__(self, repo, parent):
        QWidget.__init__(self, parent)

        self.repo = repo
        self.currentFile = None

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
        self.diffbrowse.setFont(qtlib.getfont('fontdiff').font())
        self.diffbrowse.showMessage.connect(self.showMessage)
        self.diffbrowse.linkActivated.connect(self.linkActivated)
        self.diffbrowse.chunksSelected.connect(self.chunksSelected)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 3)
        self.timerevent = self.startTimer(500)

    def timerEvent(self, event):
        'Periodic poll of currently displayed patch or working file'
        ctx = self.filelistmodel._ctx
        if ctx is None:
            return
        if isinstance(ctx, patchctx):
            path = ctx._path
            mtime = ctx._mtime
        elif self.currentFile:
            path = self.repo.wjoin(self.currentFile)
            mtime = self.mtime
        else:
            return
        if os.path.exists(path):
            newmtime = os.path.getmtime(path)
            if mtime != newmtime:
                self.mtime = newmtime
                self.refresh()

    def editCurrentFile(self):
        ctx = self.filelistmodel._ctx
        if isinstance(ctx, patchctx):
            path = ctx._path
        else:
            path = self.repo.wjoin(self.currentFile)
        wctxactions.edit(self, self.repo.ui, self.repo, [path])

    def deleteSelectedChunks(self):
        'delete currently selected chunks'
        repo = self.repo
        chunks = self.diffbrowse.curchunks
        dchunks = [c for c in chunks[1:] if c.selected]
        if not dchunks:
            self.showMessage.emit(_('No deletable chunks'))
            return
        kchunks = [c for c in chunks[1:] if not c.selected]
        revertall = False
        if not kchunks and qtlib.QuestionMsgBox(_('No chunks remain'),
                                                _('Remove all file changes?')):
            revertall = True
        ctx = self.filelistmodel._ctx
        if isinstance(ctx, patchctx):
            try:
                repo.thgbackup(ctx._path)
                fp = util.atomictempfile(ctx._path, 'wb')
                if ctx._ph.comments:
                    fp.write('\n'.join(ctx._ph.comments))
                    fp.write('\n\n')
                for wfile in ctx._fileorder:
                    if wfile == self.currentFile:
                        if revertall:
                            continue
                        chunks[0].write(fp)
                        for chunk in kchunks:
                            chunk.write(fp)
                        if not chunks[-1].selected:
                            fp.write('\n')
                    else:
                        for chunk in ctx._files[wfile]:
                            chunk.write(fp)
                fp.rename()
            finally:
                del fp
            self.fileModified.emit()
        else:
            path = repo.wjoin(self.currentFile)
            if not os.path.exists(path):
                self.showMessage.emit(_('file hsa been deleted, refresh'))
                return
            if self.mtime != os.path.getmtime(path):
                self.showMessage.emit(_('file hsa been modified, refresh'))
                return
            repo.thgbackup(repo.wjoin(self.currentFile))
            if revertall:
                hg.revert(repo, repo.dirstate.parents()[0],
                          lambda a: a == self.currentFile)
            else:
                repo.wopener(self.currentFile, 'wb').write(
                    self.diffbrowse.origcontents)
                fp = cStringIO.StringIO()
                chunks[0].write(fp)
                for c in kchunks:
                    c.write(fp)
                fp.seek(0)
                pfiles = {}
                patch.internalpatch(fp, repo.ui, 1, repo.root, files=pfiles,
                                    eolmode=None)
            self.fileModified.emit()

    def addFile(self, wfile, chunks):
        pass

    def removeFile(self, wfile):
        pass

    def getChunksForFile(self, wfile):
        pass

    @pyqtSlot(object, object, object)
    def displayFile(self, file, rev, status):
        if file:
            self.currentFile = file
            path = self.repo.wjoin(file)
            if os.path.exists(path):
                self.mtime = os.path.getmtime(path)
            self.diffbrowse.displayFile(file, status)
            self.fileSelected.emit(True)
        else:
            self.currentFile = None
            self.diffbrowse.clearDisplay()
            self.fileSelected.emit(False)

    def setContext(self, ctx):
        if self.filelist.model() is not None:
            f = self.filelist.currentFile()
        else:
            f = None
        self.fileSelected.emit(False)
        self.filelistmodel = filelistmodel.HgFileListModel(self.repo, self)
        self.filelist.setModel(self.filelistmodel)
        self.filelist.fileRevSelected.connect(self.displayFile)
        self.filelist.clearDisplay.connect(self.diffbrowse.clearDisplay)
        self.diffbrowse.setContext(ctx)
        self.filelistmodel.setContext(ctx)
        self.fileModelEmpty.emit(len(ctx.files()) == 0)
        if f and f in ctx:
            self.filelist.selectFile(f)

    def refresh(self):
        f = self.filelist.currentFile()
        ctx = self.filelistmodel._ctx
        if isinstance(ctx, patchctx):
            # if patch mtime has not changed, it could return the same ctx
            ctx = self.repo.changectx(ctx._path)
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
    chunksSelected = pyqtSignal(bool)

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
        hbox.setSpacing(2)
        self.layout().addLayout(hbox)
        self.filenamelabel = w = QLabel()
        hbox.addWidget(w)
        w.setWordWrap(True)
        f = w.textInteractionFlags()
        w.setTextInteractionFlags(f | Qt.TextSelectableByMouse)
        w.linkActivated.connect(self.linkActivated)

        self.sumlabel = QLabel()
        self.allbutton = QToolButton()
        self.allbutton.setText(_('All'))
        self.allbutton.setShortcut(QKeySequence.SelectAll)
        self.allbutton.clicked.connect(self.selectAll)
        self.nonebutton = QToolButton()
        self.nonebutton.setText(_('None'))
        self.nonebutton.setShortcut(QKeySequence.New)
        self.nonebutton.clicked.connect(self.selectNone)
        hbox.addStretch(1)
        hbox.addWidget(self.sumlabel)
        hbox.addWidget(self.allbutton)
        hbox.addWidget(self.nonebutton)

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

        i = qscilib.KeyPressInterceptor(self, None, [QKeySequence.SelectAll,
                                                     QKeySequence.New])
        self.sci.installEventFilter(i)
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
        self.chunksSelected.emit(self.countselected > 0)

    @pyqtSlot()
    def selectAll(self):
        for chunk in self.curchunks[1:]:
            if not chunk.selected:
                self.sci.markerDelete(chunk.mline, -1)
                self.sci.markerAdd(chunk.mline, self.selected)
                chunk.selected = True
                self.countselected += 1
                for i in xrange(*chunk.lrange):
                    self.sci.markerAdd(i, self.selcolor)
        self.updateSummary()

    @pyqtSlot()
    def selectNone(self):
        for chunk in self.curchunks[1:]:
            if chunk.selected:
                self.sci.markerDelete(chunk.mline, -1)
                self.sci.markerAdd(chunk.mline, self.unselected)
                chunk.selected = False
                self.countselected -= 1
                for i in xrange(*chunk.lrange):
                    self.sci.markerDelete(i, self.selcolor)
        self.updateSummary()

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
            buf.write('diff -r aaaaaaaaaaaa -r bbbbbbbbbbb %s\n' % filename)
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
        self.origcontents = fd.olddata
        self.curchunks = chunks
        self.countselected = 0
        self.updateSummary()

def run(ui, *pats, **opts):
    'for testing purposes only'
    from tortoisehg.util import paths
    repo = thgrepo.repository(ui, path=paths.find_root())
    dlg = ChunksWidget(repo, None)
    desktopgeom = qApp.desktop().availableGeometry()
    dlg.resize(desktopgeom.size() * 0.8)
    dlg.setContext(repo.changectx(None))
    return dlg

# chunks.py - TortoiseHg patch/diff browser and editor
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

import cStringIO
import os

from mercurial import hg, util, patch, commands, cmdutil
from mercurial import match as matchmod, ui as uimod
from hgext import record

from tortoisehg.util import hglib
from tortoisehg.util.patchctx import patchctx
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, thgrepo, qscilib, lexers, wctxactions
from tortoisehg.hgqt import filelistmodel, filelistview, fileview

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import Qsci

# TODO
# Add support for tools like TortoiseMerge that help resolve rejected chunks

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
        self.filelistmodel = filelistmodel.HgFileListModel(self.repo, self)
        self.filelist.setModel(self.filelistmodel)

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

        self.filelist.fileRevSelected.connect(self.displayFile)
        self.filelist.clearDisplay.connect(self.diffbrowse.clearDisplay)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 3)
        self.timerevent = self.startTimer(500)

    def timerEvent(self, event):
        'Periodic poll of currently displayed patch or working file'
        if not hasattr(self, 'filelistmodel'):
            return
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

    def runPatcher(self, fp, wfile, updatestate):
        ui = self.repo.ui.copy()
        class warncapt(ui.__class__):
            def warn(self, msg, *args, **opts):
                self.write(msg)
        ui.__class__ = warncapt

        ok = True
        repo = self.repo
        ui.pushbuffer()
        pfiles = {}
        curdir = os.getcwd()
        try:
            os.chdir(repo.root)
            if patch.applydiff(ui, fp, pfiles) < 0:
                ok = False
                self.showMessage.emit(_('Patch failed to apply'))
        except patch.PatchError, err:
            ok = False
            self.showMessage.emit(hglib.tounicode(str(err)))
        os.chdir(curdir)
        for line in ui.popbuffer().splitlines():
            if line.endswith(wfile + '.rej'):
                if qtlib.QuestionMsgBox(_('Manually resolve rejected chunks?'),
                                        hglib.tounicode(line) + u'<br><br>' +
                                        _('Edit patched file and rejects?'),
                                       parent=self):
                    from tortoisehg.hgqt import rejects
                    dlg = rejects.RejectsDialog(repo.wjoin(wfile), self)
                    if dlg.exec_() == QDialog.Accepted:
                        ok = True
                    break
        if updatestate and ok:
            # Apply operations specified in git diff headers
            cmdutil.updatedir(repo.ui, repo, pfiles)
        return ok

    def editCurrentFile(self):
        ctx = self.filelistmodel._ctx
        if isinstance(ctx, patchctx):
            path = ctx._path
        else:
            path = self.repo.wjoin(self.currentFile)
        wctxactions.edit(self, self.repo.ui, self.repo, [path])

    def getSelectedFileAndChunks(self):
        chunks = self.diffbrowse.curchunks
        if chunks:
            dchunks = [c for c in chunks[1:] if c.selected]
            return self.currentFile, [chunks[0]] + dchunks
        else:
            return self.currentFile, []

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
            repo.thgbackup(ctx._path)
            fp = util.atomictempfile(ctx._path, 'wb')
            try:
                if ctx._ph.comments:
                    fp.write('\n'.join(ctx._ph.comments))
                    fp.write('\n\n')
                needsnewline = False
                for wfile in ctx._fileorder:
                    if wfile == self.currentFile:
                        if revertall:
                            continue
                        chunks[0].write(fp)
                        for chunk in kchunks:
                            chunk.write(fp)
                        if not chunks[-1].selected:
                            needsnewline = True
                    else:
                        if needsnewline:
                            fp.write('\n')
                            needsnewline = False
                        for chunk in ctx._files[wfile]:
                            chunk.write(fp)
                fp.rename()
            finally:
                del fp
            ctx.invalidate()
            self.fileModified.emit()
        else:
            path = repo.wjoin(self.currentFile)
            if not os.path.exists(path):
                self.showMessage.emit(_('file has been deleted, refresh'))
                return
            if self.mtime != os.path.getmtime(path):
                self.showMessage.emit(_('file has been modified, refresh'))
                return
            repo.thgbackup(path)
            if revertall:
                commands.revert(repo.ui, repo, path, no_backup=True)
            else:
                wlock = repo.wlock()
                try:
                    repo.wopener(self.currentFile, 'wb').write(
                        self.diffbrowse.origcontents)
                    fp = cStringIO.StringIO()
                    chunks[0].write(fp)
                    for c in kchunks:
                        c.write(fp)
                    fp.seek(0)
                    self.runPatcher(fp, self.currentFile, False)
                finally:
                    wlock.release()
            self.fileModified.emit()

    def mergeChunks(self, wfile, chunks):
        def isAorR(header):
            for line in header:
                if line.startswith('--- /dev/null'):
                    return True
                if line.startswith('+++ /dev/null'):
                    return True
            return False
        repo = self.repo
        ctx = self.filelistmodel._ctx
        if isinstance(ctx, patchctx):
            if wfile in ctx._files:
                patchchunks = ctx._files[wfile]
                if isAorR(chunks[0].header) or isAorR(patchchunks[0].header):
                    qtlib.InfoMsgBox(_('Unable to merge chunks'),
                                    _('Add or remove patches must be merged '
                                      'in the working directory'))
                    return False
                # merge new chunks into existing chunks, sorting on start line
                newchunks = [chunks[0]]
                pidx = nidx = 1
                while pidx < len(patchchunks) or nidx < len(chunks):
                    if pidx == len(patchchunks):
                        newchunks.append(chunks[nidx])
                        nidx += 1
                    elif nidx == len(chunks):
                        newchunks.append(patchchunks[pidx])
                        pidx += 1
                    elif chunks[nidx].fromline < patchchunks[pidx].fromline:
                        newchunks.append(chunks[nidx])
                        nidx += 1
                    else:
                        newchunks.append(patchchunks[pidx])
                        pidx += 1
                ctx._files[wfile] = newchunks
            else:
                # add file to patch
                ctx._files[wfile] = chunks
                ctx._fileorder.append(wfile)
            repo.thgbackup(ctx._path)
            fp = util.atomictempfile(ctx._path, 'wb')
            try:
                if ctx._ph.comments:
                    fp.write('\n'.join(ctx._ph.comments))
                    fp.write('\n\n')
                for file in ctx._fileorder:
                    for chunk in ctx._files[file]:
                        chunk.write(fp)
                fp.rename()
                ctx.invalidate()
                self.fileModified.emit()
                return True
            finally:
                del fp
            return False
        else:
            # Apply chunks to wfile
            repo.thgbackup(repo.wjoin(wfile))
            fp = cStringIO.StringIO()
            for c in chunks:
                c.write(fp)
            fp.seek(0)
            wlock = repo.wlock()
            try:
                return self.runPatcher(fp, wfile, True)
            finally:
                wlock.release()
            return False

    def getFileList(self):
        return self.filelistmodel._ctx.files()

    def removeFile(self, wfile):
        repo = self.repo
        ctx = self.filelistmodel._ctx
        if isinstance(ctx, patchctx):
            repo.thgbackup(ctx._path)
            fp = util.atomictempfile(ctx._path, 'wb')
            try:
                if ctx._ph.comments:
                    fp.write('\n'.join(ctx._ph.comments))
                    fp.write('\n\n')
                for file in ctx._fileorder:
                    if file == wfile:
                        continue
                    for chunk in ctx._files[file]:
                        chunk.write(fp)
                fp.rename()
            finally:
                del fp
            ctx.invalidate()
        else:
            repo.thgbackup(repo.wjoin(wfile))
            wasadded = wfile in repo[None].added()
            commands.revert(repo.ui, repo, repo.wjoin(wfile), no_backup=True)
            if wasadded:
                os.unlink(repo.wjoin(wfile))
        self.fileModified.emit()

    def getChunksForFile(self, wfile):
        repo = self.repo
        ctx = self.filelistmodel._ctx
        if isinstance(ctx, patchctx):
            if wfile in ctx._files:
                return ctx._files[wfile]
            else:
                return []
        else:
            buf = cStringIO.StringIO()
            diffopts = patch.diffopts(repo.ui, {'git':True})
            m = matchmod.exact(repo.root, repo.root, [wfile])
            for p in patch.diff(repo, ctx.p1().node(), None, match=m,
                                opts=diffopts):
                buf.write(p)
            buf.seek(0)
            header =  record.parsepatch(buf)[0]
            return [header] + header.hunks

    @pyqtSlot(object, object, object)
    def displayFile(self, file, rev, status):
        if file:
            self.currentFile = file
            path = self.repo.wjoin(file)
            if os.path.exists(path):
                self.mtime = os.path.getmtime(path)
            else:
                self.mtime = None
            self.diffbrowse.displayFile(file, status)
            self.fileSelected.emit(True)
        else:
            self.currentFile = None
            self.diffbrowse.clearDisplay()
            self.diffbrowse.clearChunks()
            self.fileSelected.emit(False)

    def setContext(self, ctx):
        self.diffbrowse.setContext(ctx)
        self.filelistmodel.setContext(ctx)
        empty = len(ctx.files()) == 0
        self.fileModelEmpty.emit(empty)
        self.fileSelected.emit(not empty)
        self.diffbrowse.updateSummary()

    def refresh(self):
        ctx = self.filelistmodel._ctx
        if isinstance(ctx, patchctx):
            # if patch mtime has not changed, it could return the same ctx
            ctx = self.repo.changectx(ctx._path)
        else:
            self.repo.thginvalidate()
            ctx = self.repo.changectx(ctx.node())
        self.setContext(ctx)
        if self.currentFile:
            self.filelist.selectFile(self.currentFile)

    def loadSettings(self, qs, prefix):
        self.diffbrowse.loadSettings(qs, prefix)

    def saveSettings(self, qs, prefix):
        self.diffbrowse.saveSettings(qs, prefix)


# DO NOT USE.  Sadly, this does not work.
class ElideLabel(QLabel):
    def __init__(self, text='', parent=None):
        QLabel.__init__(self, text, parent)

    def sizeHint(self):
        return super(ElideLabel, self).sizeHint()

    def paintEvent(self, event):
        p = QPainter()
        fm = QFontMetrics(self.font())
        if fm.width(self.text()): # > self.contentsRect().width():
            elided = fm.elidedText(self.text(), Qt.ElideLeft,
                                   self.rect().width(), 0)
            p.drawText(self.rect(), Qt.AlignTop | Qt.AlignRight |
                       Qt.TextSingleLine, elided)
        else:
            super(ElideLabel, self).paintEvent(event)

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
        self._lastfile = None

        vbox = QVBoxLayout()
        vbox.setContentsMargins(0,0,0,0)
        vbox.setSpacing(0)
        self.setLayout(vbox)

        self.labelhbox = hbox = QHBoxLayout()
        hbox.setContentsMargins(0,0,0,0)
        hbox.setSpacing(2)
        self.layout().addLayout(hbox)
        self.filenamelabel = w = QLabel()
        self.filenamelabel.hide()
        hbox.addWidget(w)
        w.setWordWrap(True)
        f = w.textInteractionFlags()
        w.setTextInteractionFlags(f | Qt.TextSelectableByMouse)
        w.linkActivated.connect(self.linkActivated)

        self.sumlabel = QLabel()
        self.allbutton = QToolButton()
        self.allbutton.setText(_('All', 'files'))
        self.allbutton.setShortcut(QKeySequence.SelectAll)
        self.allbutton.clicked.connect(self.selectAll)
        self.nonebutton = QToolButton()
        self.nonebutton.setText(_('None', 'files'))
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
        self.sci.installEventFilter(qscilib.KeyPressInterceptor(self))
        self.sci.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sci.customContextMenuRequested.connect(self.menuRequested)
        self.sci.setCaretLineVisible(False)

        self.sci.setMarginType(1, qsci.SymbolMargin)
        self.sci.setMarginLineNumbers(1, False)
        self.sci.setMarginWidth(1, QFontMetrics(self.font()).width('XX'))
        self.sci.setMarginSensitivity(1, True)
        self.sci.marginClicked.connect(self.marginClicked)
        self.selected = self.sci.markerDefine(qsci.Plus, -1)
        self.unselected = self.sci.markerDefine(qsci.Minus, -1)
        self.vertical = self.sci.markerDefine(qsci.VerticalLine, -1)
        self.divider = self.sci.markerDefine(qsci.Background, -1)
        self.selcolor = self.sci.markerDefine(qsci.Background, -1)
        self.sci.setMarkerBackgroundColor(QColor('#BBFFFF'), self.selcolor)
        self.sci.setMarkerBackgroundColor(QColor('#AAAAAA'), self.divider)
        mask = (1 << self.selected) | (1 << self.unselected) | \
               (1 << self.vertical) | (1 << self.selcolor) | (1 << self.divider)
        self.sci.setMarginMarkerMask(1, mask)

        self.layout().addWidget(self.sci, 1)

        lexer = lexers.get_diff_lexer(self)
        self.sci.setLexer(lexer)
        self.clearDisplay()

    def menuRequested(self, point):
        point = self.sci.mapToGlobal(point)
        return self.sci.createStandardContextMenu().exec_(point)

    def loadSettings(self, qs, prefix):
        self.sci.loadSettings(qs, prefix)

    def saveSettings(self, qs, prefix):
        self.sci.saveSettings(qs, prefix)

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
                self.toggleChunk(chunk)
                self.updateSummary()
                return

    def toggleChunk(self, chunk):
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

    def setContext(self, ctx):
        self._ctx = ctx
        self.sci.setTabWidth(ctx._repo.tabwidth)

    def clearDisplay(self):
        self.sci.clear()
        self.filenamelabel.setText(' ')
        self.extralabel.hide()

    def clearChunks(self):
        self.curchunks = []
        self.countselected = 0
        self.updateSummary()

    def displayFile(self, filename, status):
        self.clearDisplay()
        if filename == self._lastfile:
            reenable = [c.fromline for c in self.curchunks[1:] if c.selected]
        else:
            reenable = []
        self._lastfile = filename
        self.clearChunks()

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
            header = record.parsepatch(cStringIO.StringIO(fd.diff))[0]
            chunks = [header] + header.hunks

        utext = []
        for chunk in chunks[1:]:
            buf = cStringIO.StringIO()
            chunk.selected = False
            chunk.write(buf)
            chunk.lines = buf.getvalue().splitlines()
            utext += [hglib.tounicode(l) for l in chunk.lines]
            utext.append('')
        self.sci.setText(u'\n'.join(utext))

        start = 0
        self.sci.markerDeleteAll(-1)
        for chunk in chunks[1:]:
            chunk.lrange = (start, start+len(chunk.lines))
            chunk.mline = start + len(chunk.lines)/2
            if start:
                self.sci.markerAdd(start-1, self.divider)
            for i in xrange(1,len(chunk.lines)-1):
                if start + i == chunk.mline:
                    self.sci.markerAdd(chunk.mline, self.unselected)
                else:
                    self.sci.markerAdd(start+i, self.vertical)
            start += len(chunk.lines) + 1
        self.origcontents = fd.olddata
        self.countselected = 0
        self.curchunks = chunks
        for c in chunks[1:]:
            if c.fromline in reenable:
                self.toggleChunk(c)
        self.updateSummary()

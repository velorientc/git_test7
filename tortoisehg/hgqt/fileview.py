# Copyright (c) 2009-2010 LOGILAB S.A. (Paris, FRANCE).
# http://www.logilab.fr/ -- mailto:contact@logilab.fr
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
"""
Qt4 high level widgets for hg repo changelogs and filelogs
"""

import os
import difflib
import re

from mercurial import hg, error, match, patch, util
from mercurial import ui as uimod, mdiff

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import Qsci

from tortoisehg.util import hglib, patchctx
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import annotate, qscilib, qtlib, blockmatcher, lexers
from tortoisehg.hgqt import visdiff, wctxactions

qsci = Qsci.QsciScintilla

class HgFileView(QFrame):
    """file diff and content viewer"""

    linkActivated = pyqtSignal(QString)
    fileDisplayed = pyqtSignal(QString, QString)
    showMessage = pyqtSignal(QString)
    revForDiffChanged = pyqtSignal(int)
    filled = pyqtSignal()

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
        hbox.addWidget(self.blk)
        self.blk.setVisible(False)

        self._stacked = QStackedWidget()
        hbox.addWidget(self._stacked, 1)

        self.sci = qscilib.Scintilla(self)
        self.blk.linkScrollBar(self.sci.verticalScrollBar())
        self._stacked.addWidget(self.sci)

        self.sci.setFrameStyle(0)
        self.sci.setReadOnly(True)
        self.sci.setUtf8(True)
        self.sci.installEventFilter(qscilib.KeyPressInterceptor(self))
        self.sci.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sci.customContextMenuRequested.connect(self.menuRequested)
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

        if hasattr(self.sci, 'indicatorDefine'):
            self.sci.indicatorDefine(qsci.RoundBoxIndicator, 8)
            self.sci.setIndicatorDrawUnder(8)
            self.sci.setIndicatorForegroundColor(QColor('#BBFFFF'), 8)
            self.sci.indicatorDefine(qsci.RoundBoxIndicator, 9)
            self.sci.setIndicatorDrawUnder(9)
            self.sci.setIndicatorForegroundColor(QColor('#58A8FF'), 9)
        else:
            self.sci.SendScintilla(qsci.SCI_INDICSETSTYLE, 8, qsci.INDIC_ROUNDBOX)
            self.sci.SendScintilla(qsci.SCI_INDICSETUNDER, 8, True)
            self.sci.SendScintilla(qsci.SCI_INDICSETFORE, 8, 0xBBFFFF)
            self.sci.SendScintilla(qsci.SCI_INDICSETSTYLE, 9, qsci.INDIC_ROUNDBOX)
            self.sci.SendScintilla(qsci.SCI_INDICSETUNDER, 9, True)
            self.sci.SendScintilla(qsci.SCI_INDICSETFORE, 9, 0x58A8FF)

        self._annotate = annotate.AnnotateView(repo, self)
        for name in ('searchRequested', 'editSelected', 'grepRequested'):
            getattr(self._annotate, name).connect(getattr(self, name))
        self._annotate.revisionHint.connect(self.showMessage)
        self._annotate.sourceChanged.connect(self.sourceChanged)
        self._annotate.setAnnotationEnabled(True)
        self._stacked.addWidget(self._annotate)

        self._ctx = None
        self._filename = None
        self._status = None
        self._find_text = None
        self._mode = None
        self._lostMode = None

        self.actionDiffMode = QAction('Diff', self)
        self.actionDiffMode.setCheckable(True)
        self.actionFileMode = QAction('File', self)
        self.actionFileMode.setCheckable(True)
        self.actionAnnMode = QAction('Ann', self)
        self.actionAnnMode.setCheckable(True)

        self.modeToggleGroup = QActionGroup(self)
        self.modeToggleGroup.addAction(self.actionDiffMode)
        self.modeToggleGroup.addAction(self.actionFileMode)
        self.modeToggleGroup.addAction(self.actionAnnMode)
        self.modeToggleGroup.triggered.connect(self.setMode)

        # Next/Prev diff (in full file mode)
        self.actionNextDiff = QAction(qtlib.geticon('down'), 'Next diff', self)
        self.actionNextDiff.setShortcut('Alt+Down')
        self.actionNextDiff.triggered.connect(self.nextDiff)
        self.actionPrevDiff = QAction(qtlib.geticon('up'), 'Previous diff', self)
        self.actionPrevDiff.setShortcut('Alt+Up')
        self.actionPrevDiff.triggered.connect(self.prevDiff)

        self.forceMode('diff')

        tb = self.diffToolbar
        tb.addAction(self.actionDiffMode)
        tb.addAction(self.actionFileMode)
        tb.addAction(self.actionAnnMode)
        tb.addSeparator()
        tb.addAction(self.actionNextDiff)
        tb.addAction(self.actionPrevDiff)

        self.actionNextLine = QAction('Next line', self)
        self.actionNextLine.setShortcut(Qt.SHIFT + Qt.Key_Down)
        self.actionNextLine.triggered.connect(self.nextLine)
        self.addAction(self.actionNextLine)
        self.actionPrevLine = QAction('Prev line', self)
        self.actionPrevLine.setShortcut(Qt.SHIFT + Qt.Key_Up)
        self.actionPrevLine.triggered.connect(self.prevLine)
        self.addAction(self.actionPrevLine)
        self.actionNextCol = QAction('Next column', self)
        self.actionNextCol.setShortcut(Qt.SHIFT + Qt.Key_Right)
        self.actionNextCol.triggered.connect(self.nextCol)
        self.addAction(self.actionNextCol)
        self.actionPrevCol = QAction('Prev column', self)
        self.actionPrevCol.setShortcut(Qt.SHIFT + Qt.Key_Left)
        self.actionPrevCol.triggered.connect(self.prevCol)
        self.addAction(self.actionPrevCol)

        self.timer = QTimer()
        self.timer.setSingleShot(False)
        self.timer.timeout.connect(self.idle_fill_files)

    def menuRequested(self, point):
        point = self.sci.mapToGlobal(point)
        return self.sci.createStandardContextMenu().exec_(point)

    def loadSettings(self, qs, prefix):
        self.sci.loadSettings(qs, prefix)

    def saveSettings(self, qs, prefix):
        self.sci.saveSettings(qs, prefix)

    @pyqtSlot(QAction)
    def setMode(self, action):
        'One of the mode toolbar buttons has been toggled'
        mode = {'Diff':'diff', 'File':'file', 'Ann':'ann'}[str(action.text())]
        self.actionNextDiff.setEnabled(mode == 'file')
        self.actionPrevDiff.setEnabled(False)
        self.blk.setVisible(mode == 'file')
        if mode == 'ann':
            self._stacked.setCurrentWidget(self._annotate)
        else:
            self._stacked.setCurrentWidget(self.sci)
        if mode != self._mode:
            self._mode = mode
            if not self._lostMode:
                self.displayFile()

    def forceMode(self, mode):
        'Force into file or diff mode, based on content constaints'
        assert mode in ('diff', 'file')
        if self._lostMode is None:
            self._lostMode = self._mode
        self._mode = mode
        if mode == 'diff':
            self.actionDiffMode.setChecked(True)
        else:
            self.actionFileMode.setChecked(True)
        self.actionDiffMode.setEnabled(False)
        self.actionFileMode.setEnabled(False)
        self.actionAnnMode.setEnabled(False)
        self.actionNextDiff.setEnabled(False)
        self.actionPrevDiff.setEnabled(False)
        self.blk.setVisible(mode == 'file')
        self._stacked.setCurrentWidget(self.sci)

    def setContext(self, ctx):
        self._ctx = ctx
        self._p_rev = None
        self.sci.setTabWidth(ctx._repo.tabwidth)
        self.actionAnnMode.setVisible(ctx.rev() != None)

    def displayDiff(self, rev):
        if rev != self._p_rev:
            self.displayFile(rev=rev)

    def clearDisplay(self):
        self.sci.clear()
        self.blk.clear()
        # Setting the label to ' ' rather than clear() keeps the label
        # from disappearing during refresh, and tool layouts bouncing
        self.filenamelabel.setText(' ')
        self.extralabel.hide()
        self.sci.setMarginLineNumbers(1, False)
        self.sci.setMarginWidth(1, '')
        self._diffs = []

    def displayFile(self, filename=None, rev=None, status=None):
        if filename is None:
            filename, status = self._filename, self._status
        else:
            self._filename, self._status = filename, status

        if rev is not None:
            self._p_rev = rev
            self.revForDiffChanged.emit(rev)

        self.clearDisplay()
        if filename is None:
            self.forceMode('file')
            return

        ctx = self._ctx
        repo = ctx._repo
        if self._p_rev is not None:
            ctx2 = repo[self._p_rev]
        else:
            ctx2 = None

        fd = FileData(ctx, ctx2, filename, status)

        if fd.elabel:
            self.extralabel.setText(fd.elabel)
            self.extralabel.show()
        else:
            self.extralabel.hide()
        self.filenamelabel.setText(fd.flabel)

        if not fd.isValid():
            self.sci.setText(fd.error)
            self.forceMode('file')
            return

        if fd.diff and not fd.contents:
            self.forceMode('diff')
        elif fd.contents and not fd.diff:
            self.forceMode('file')
        else:
            self.actionDiffMode.setEnabled(True)
            self.actionFileMode.setEnabled(True)
            self.actionAnnMode.setEnabled(True)
            if self._lostMode:
                if self._lostMode == 'diff':
                    self.actionDiffMode.trigger()
                elif self._lostMode == 'file':
                    self.actionFileMode.trigger()
                elif self._lostMode == 'ann':
                    self.actionAnnMode.trigger()
                self._lostMode = None

        if self._mode == 'ann':
            self._annotate.setSource(filename, ctx.rev())
        elif self._mode == 'diff':
            lexer = lexers.get_diff_lexer(self)
            self.sci.setLexer(lexer)
            # trim first three lines, for example:
            # diff -r f6bfc41af6d7 -r c1b18806486d tortoisehg/hgqt/thgrepo.py
            # --- a/tortoisehg/hgqt/thgrepo.py
            # +++ b/tortoisehg/hgqt/thgrepo.py
            noheader = fd.diff.split('\n', 3)[3]
            self.sci.setText(hglib.tounicode(noheader))
        elif fd.contents is None:
            return
        else:
            lexer = lexers.get_lexer(filename, fd.contents, self)
            self.sci.setLexer(lexer)
            nlines = fd.contents.count('\n')
            # margin 1 is used for line numbers
            self.sci.setMarginLineNumbers(1, True)
            self.sci.setMarginWidth(1, str(nlines)+'0')
            self.sci.setText(fd.contents)

        if self._find_text:
            self.highlightSearchString(self._find_text)

        uf = hglib.tounicode(self._filename)
        self.fileDisplayed.emit(uf, fd.contents or QString())

        if self._mode == 'file' and fd.contents and fd.olddata:
            # Update diff margin
            if self.timer.isActive():
                self.timer.stop()

            olddata = fd.olddata.splitlines()
            newdata = fd.contents.splitlines()
            self._diff = difflib.SequenceMatcher(None, olddata, newdata)
            self.blk.syncPageStep()
            self.timer.start()

    def nextDiff(self):
        if self._mode == 'diff' or not self._diffs:
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
        if self._mode == 'diff' or not self._diffs:
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

    def nDiffs(self):
        return len(self._diffs)

    @pyqtSlot(unicode, object)
    @pyqtSlot(unicode, object, int)
    def sourceChanged(self, path, rev, line=None):
        self.revForDiffChanged.emit(rev)

    @pyqtSlot(unicode, object, int)
    def editSelected(self, path, rev, line):
        """Open editor to show the specified file"""
        repo = self._ctx._repo
        path = hglib.fromunicode(path)
        base = visdiff.snapshot(repo, [path], repo[rev])[0]
        files = [os.path.join(base, path)]
        wctxactions.edit(self, repo.ui, repo, files, line, self._find_text)

    def searchString(self, text):
        self._find_text = text
        self.clearHighlights()
        findpos = self.highlightSearchString(self._find_text)
        if findpos:
            def finditer(self, findpos):
                if self._find_text:
                    for pos in findpos:
                        self.highlightCurrentSearchString(pos, self._find_text)
                        yield self._ctx.rev(), self._filename, pos
            return finditer(self, findpos)

    def clearHighlights(self):
        n = self.sci.length()
        # highlight
        self.sci.SendScintilla(qsci.SCI_SETINDICATORCURRENT, 8)
        self.sci.SendScintilla(qsci.SCI_INDICATORCLEARRANGE, 0, n)
        # current found occurrence
        self.sci.SendScintilla(qsci.SCI_SETINDICATORCURRENT, 9)
        self.sci.SendScintilla(qsci.SCI_INDICATORCLEARRANGE, 0, n)

    def highlightSearchString(self, text):
        data = unicode(self.sci.text())
        self.sci.SendScintilla(qsci.SCI_SETINDICATORCURRENT, 8)
        pos = [data.find(text)]
        n = len(text)
        while pos[-1] > -1:
            self.sci.SendScintilla(qsci.SCI_INDICATORFILLRANGE, pos[-1], n)
            pos.append(data.find(text, pos[-1]+1))
        pos = [x for x in pos if x > -1]
        self.showMessage.emit(
             _("Found %d occurrences of '%s' in current file or diff") % (
                 len(pos), text))
        return pos

    def highlightCurrentSearchString(self, pos, text):
        line = self.sci.SendScintilla(qsci.SCI_LINEFROMPOSITION, pos)
        #line, idx = w.lineIndexFromPosition(nextpos)
        self.sci.ensureLineVisible(line)
        self.sci.SendScintilla(qsci.SCI_SETINDICATORCURRENT, 9)
        self.sci.SendScintilla(qsci.SCI_INDICATORCLEARRANGE, 0, pos)
        self.sci.SendScintilla(qsci.SCI_INDICATORFILLRANGE, pos, len(text))

    @pyqtSlot(unicode, bool, bool, bool)
    def find(self, exp, icase=True, wrap=False, forward=True):
        self.sci.find(exp, icase, wrap, forward)

    @pyqtSlot(unicode, bool)
    def highlightText(self, match, icase=False):
        self.sci.highlightText(match, icase)

    def verticalScrollBar(self):
        return self.sci.verticalScrollBar()

    def idle_fill_files(self):
        # we make a burst of diff-lines computed at once, but we
        # disable GUI updates for efficiency reasons, then only
        # refresh GUI at the end of the burst
        self.sci.setUpdatesEnabled(False)
        self.blk.setUpdatesEnabled(False)
        for n in range(30): # burst pool
            if self._diff is None or not self._diff.get_opcodes():
                self.actionNextDiff.setEnabled(bool(self._diffs))
                self.actionPrevDiff.setEnabled(False)
                self._diff = None
                self.timer.stop()
                self.filled.emit()
                break

            tag, alo, ahi, blo, bhi = self._diff.get_opcodes().pop(0)
            if tag == 'replace':
                self._diffs.append([blo, bhi])
                self.blk.addBlock('x', blo, bhi)
                for i in range(blo, bhi):
                    self.sci.markerAdd(i, self.markertriangle)

            elif tag == 'delete':
                # You cannot effectively show deleted lines in a single
                # pane display.  They do not exist.
                pass
                # self._diffs.append([blo, bhi])
                # self.blk.addBlock('-', blo, bhi)
                # for i in range(alo, ahi):
                #      self.sci.markerAdd(i, self.markerminus)

            elif tag == 'insert':
                self._diffs.append([blo, bhi])
                self.blk.addBlock('+', blo, bhi)
                for i in range(blo, bhi):
                    self.sci.markerAdd(i, self.markerplus)

            elif tag == 'equal':
                pass

            else:
                raise ValueError, 'unknown tag %r' % (tag,)

        # ok, enable GUI refresh for code viewers and diff-block displayers
        self.sci.setUpdatesEnabled(True)
        self.blk.setUpdatesEnabled(True)


class FileData(object):
    def __init__(self, ctx, ctx2, wfile, status=None):
        self.contents = None
        self.error = None
        self.olddata = None
        self.diff = None
        self.flabel = u''
        self.elabel = u''
        self.readStatus(ctx, ctx2, wfile, status)

    def checkMaxDiff(self, ctx, wfile):
        p = _('File or diffs not displayed: ')
        try:
            fctx = ctx.filectx(wfile)
            if ctx.rev() is None:
                size = fctx.size()
            else:
                # fctx.size() can read all data into memory in rename cases so
                # we read the size directly from the filelog, this is deeper
                # under the API than I prefer to go, but seems necessary
                size = fctx._filelog.rawsize(fctx.filerev())
        except (EnvironmentError, error.LookupError), e:
            self.error = p + hglib.tounicode(str(e))
            return None
        if size > ctx._repo.maxdiff:
            self.error = p + _('File is larger than the specified max size.\n')
            return None
        try:
            data = fctx.data()
            if '\0' in data:
                self.error = p + _('File is binary.\n')
                return None
        except EnvironmentError, e:
            self.error = p + hglib.tounicode(str(e))
            return None
        return fctx, data

    def isValid(self):
        return self.error is None

    def readStatus(self, ctx, ctx2, wfile, status):
        def getstatus(repo, n1, n2, wfile):
            m = match.exact(repo.root, repo.getcwd(), [wfile])
            modified, added, removed = repo.status(n1, n2, match=m)[:3]
            if wfile in modified:
                return 'M'
            if wfile in added:
                return 'A'
            if wfile in removed:
                return 'R'
            return None

        repo = ctx._repo
        self.flabel += u'<b>%s</b>' % hglib.tounicode(wfile)

        if isinstance(ctx, patchctx.patchctx):
            self.diff = ctx.thgmqpatchdata(wfile)
            flags = ctx.flags(wfile)
            if flags in ('x', '-'):
                lbl = _("exec mode has been <font color='red'>%s</font>")
                change = (flags == 'x') and _('set') or _('unset')
                self.elabel = lbl % change
            elif flags == 'l':
                self.flabel += _(' <i>(is a symlink)</i>')
            return

        absfile = repo.wjoin(wfile)
        if (wfile in ctx and 'l' in ctx.flags(wfile)) or \
           os.path.islink(absfile):
            if wfile in ctx:
                data = ctx[wfile].data()
            else:
                data = os.readlink(absfile)
            self.contents = hglib.tounicode(data)
            self.flabel += _(' <i>(is a symlink)</i>')
            return

        if status is None:
            status = getstatus(repo, ctx.p1().node(), ctx.node(), wfile)
        if ctx2 is None:
            ctx2 = ctx.p1()

        if status == 'S':
            try:
                from mercurial import subrepo, commands
                assert(ctx.rev() is None)
                out = []
                _ui = uimod.ui()
                sroot = repo.wjoin(wfile)
                srepo = hg.repository(_ui, path=sroot)
                srev = ctx.substate.get(wfile, subrepo.nullstate)[1]
                sactual = srepo['.'].hex()
                _ui.pushbuffer()
                commands.status(_ui, srepo)
                data = _ui.popbuffer()
                if data:
                    out.append(_('File Status:\n'))
                    out.append(data)
                    out.append('\n')
                if srev == '':
                    out.append(_('New subrepository\n\n'))
                elif srev != sactual:
                    out.append(_('Revision has changed from:\n\n'))
                    opts = {'date':None, 'user':None, 'rev':[srev]}
                    _ui.pushbuffer()
                    commands.log(_ui, srepo, **opts)
                    out.append(hglib.tounicode(_ui.popbuffer()))
                    out.append(_('To:\n'))
                    opts['rev'] = [sactual]
                    _ui.pushbuffer()
                    commands.log(_ui, srepo, **opts)
                    out.append(hglib.tounicode(_ui.popbuffer()))
                self.contents = u''.join(out)
                self.flabel += _(' <i>(is a dirty sub-repository)</i>')
                lbl = u' <a href="subrepo:%s">%s...</a>'
                self.flabel += lbl % (hglib.tounicode(sroot), _('open'))
            except (error.RepoError, util.Abort), e:
                self.error = _('Not a Mercurial subrepo, not previewable')
            return

        # TODO: elif check if a subdirectory (for manifest tool)

        if status in ('R', '!'):
            if wfile in ctx.p1():
                newdata = ctx.p1()[wfile].data()
                self.contents = hglib.tounicode(newdata)
                self.flabel += _(' <i>(was deleted)</i>')
            else:
                self.flabel += _(' <i>(was added, now missing)</i>')
            return

        if status in ('I', '?'):
            try:
                data = open(repo.wjoin(wfile), 'r').read()
                if '\0' in data:
                    self.error = 'binary file'
                else:
                    self.contents = hglib.tounicode(data)
                    self.flabel += _(' <i>(is unversioned)</i>')
            except EnvironmentError, e:
                self.error = hglib.tounicode(str(e))
            return

        if status in ('M', 'A'):
            res = self.checkMaxDiff(ctx, wfile)
            if res is None:
                return
            fctx, newdata = res
            self.contents = hglib.tounicode(newdata)
            change = None
            for pfctx in fctx.parents():
                if 'x' in fctx.flags() and 'x' not in pfctx.flags():
                    change = _('set')
                elif 'x' not in fctx.flags() and 'x' in pfctx.flags():
                    change = _('unset')
            if change:
                lbl = _("exec mode has been <font color='red'>%s</font>")
                self.elabel = lbl % change

        if status == 'A':
            renamed = fctx.renamed()
            if not renamed:
                self.flabel += _(' <i>(was added)</i>')
                return

            oldname, node = renamed
            fr = hglib.tounicode(oldname)
            self.flabel += _(' <i>(renamed from %s)</i>') % fr
            olddata = repo.filectx(oldname, fileid=node).data()
        elif status == 'M':
            if wfile not in ctx2:
                # merge situation where file was added in other branch
                self.flabel += _(' <i>(was added)</i>')
                return
            oldname = wfile
            olddata = ctx2[wfile].data()
        else:
            return

        self.olddata = olddata
        newdate = util.datestr(ctx.date())
        olddate = util.datestr(ctx2.date())
        revs = [str(ctx), str(ctx2)]
        diffopts = patch.diffopts(repo.ui, {})
        diffopts.git = False
        self.diff = mdiff.unidiff(olddata, olddate, newdata, newdate,
                                  oldname, wfile, revs, diffopts)

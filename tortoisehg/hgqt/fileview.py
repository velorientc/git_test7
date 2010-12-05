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

from mercurial import hg, error, match, patch, subrepo, commands
from mercurial import ui as uimod

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import Qsci

from tortoisehg.util import hglib

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.lexers import get_lexer, get_diff_lexer
from tortoisehg.hgqt.blockmatcher import BlockList
from tortoisehg.hgqt import qscilib

qsci = Qsci.QsciScintilla
chunkhdrre = re.compile('^@@ -(\d+).*@@$')

class Annotator(qsci):
    # we use a QScintilla for the annotater cause it makes
    # it much easier to keep the text area and the annotater sync
    # (same font rendering etc). However, it have the drawback of making much
    # more difficult to implement things like QTextBrowser.anchorClicked, which
    # would have been nice to directly go to the annotated revision...
    def __init__(self, textarea, parent=None):
        qsci.__init__(self, parent)

        self.setFrameStyle(0)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setReadOnly(True)
        self.sizePolicy().setControlType(QSizePolicy.Slider)
        self.setMinimumWidth(20)
        self.setMaximumWidth(40) # XXX TODO make this computed
        self.setFont(textarea.font())
        self.setMarginWidth(0, '')
        self.setMarginWidth(1, '')

        self.SendScintilla(qsci.SCI_SETCURSOR, 2)
        self.SendScintilla(qsci.SCI_SETCARETSTYLE, 0)

        # used to set a background color for every annotating rev
        N = 32
        self.markers = []
        for i in range(N):
            marker = self.markerDefine(qsci.Background)
            color = 0x7FFF00 + (i-N/2)*256/N*256*256 - i*256/N*256 + i*256/N
            self.SendScintilla(qsci.SCI_MARKERSETBACK, marker, color)
            self.markers.append(marker)

        textarea.verticalScrollBar().valueChanged.connect(
                self.verticalScrollBar().setValue)

    def setFilectx(self, fctx):
        self.fctx = fctx
        if fctx.rev() is None:
            # the working context does not support annotate yet.  I need to
            # add that to Mercurial at some point.
            self.setText('')
            self.fctxann = []
            return
        self.fctxann = [f for f, line in fctx.annotate(follow=True)]
        revlist = [str(f.rev()) for f in self.fctxann]
        self.setText('\n'.join(revlist))
        uniqrevs = list(sorted(set(revlist)))
        for i, rev in enumerate(revlist):
            idx = uniqrevs.index(rev)
            self.markerAdd(i, self.markers[idx % len(self.markers)])

class HgFileView(QFrame):
    """file diff and content viewer"""

    showDescSignal = pyqtSignal(QString)
    linkActivated = pyqtSignal(QString)
    fileDisplayed = pyqtSignal(QString, QString)
    showMessage = pyqtSignal(unicode)
    revForDiffChanged = pyqtSignal(int)
    filled = pyqtSignal()

    def __init__(self, parent=None):
        QFrame.__init__(self, parent)
        framelayout = QVBoxLayout(self)
        framelayout.setContentsMargins(0,0,0,0)
        framelayout.setSpacing(0)

        l = QHBoxLayout()
        l.setContentsMargins(0,0,0,0)
        l.setSpacing(0)

        self.topLayout = QVBoxLayout()

        self.filenamelabel = w = QLabel()
        w.setWordWrap(True)
        f = w.textInteractionFlags()
        w.setTextInteractionFlags(f | Qt.TextSelectableByMouse)
        w.linkActivated.connect(self.linkActivated)
        self.topLayout.addWidget(w)

        self.extralabel = w = QLabel()
        w.setWordWrap(True)
        w.linkActivated.connect(self.linkActivated)
        self.topLayout.addWidget(w)
        w.hide()

        framelayout.addLayout(self.topLayout)
        framelayout.addLayout(l, 1)

        self.sci = qscilib.Scintilla(self)
        self.sci.setFrameStyle(0)
        l.addWidget(self.sci, 1)
        #self.sci.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.sci.setReadOnly(True)
        self.sci.setUtf8(True)
        self.sci.setWrapMode(qsci.WrapCharacter)
        self.sci.installEventFilter(qscilib.KeyPressInterceptor(self))

        self.sci.SendScintilla(qsci.SCI_SETCARETSTYLE, 0)

        self.sci.SendScintilla(qsci.SCI_INDICSETSTYLE, 8, qsci.INDIC_ROUNDBOX)
        self.sci.SendScintilla(qsci.SCI_INDICSETUNDER, 8, True)
        self.sci.SendScintilla(qsci.SCI_INDICSETFORE, 8, 0xBBFFFF)
        self.sci.SendScintilla(qsci.SCI_INDICSETSTYLE, 9, qsci.INDIC_ROUNDBOX)
        self.sci.SendScintilla(qsci.SCI_INDICSETUNDER, 9, True)
        self.sci.SendScintilla(qsci.SCI_INDICSETFORE, 9, 0x58A8FF)

        # hide margin 0 (markers)
        self.sci.SendScintilla(qsci.SCI_SETMARGINTYPEN, 0, 0)
        self.sci.SendScintilla(qsci.SCI_SETMARGINWIDTHN, 0, 0)

        # define markers for colorize zones of diff
        self.markerplus = self.sci.markerDefine(qsci.Background)
        self.sci.SendScintilla(qsci.SCI_MARKERSETBACK, self.markerplus,
                               0xB0FFA0)
        self.markerminus = self.sci.markerDefine(qsci.Background)
        self.sci.SendScintilla(qsci.SCI_MARKERSETBACK, self.markerminus,
                               0xA0A0FF)
        self.markertriangle = self.sci.markerDefine(qsci.Background)
        self.sci.SendScintilla(qsci.SCI_MARKERSETBACK, self.markertriangle,
                               0xFFA0A0)
        self.lastrev = None
        self.sci.mouseMoveEvent = self.mouseMoveEvent

        ll = QVBoxLayout()
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        l.insertLayout(0, ll)

        ll2 = QHBoxLayout()
        ll2.setContentsMargins(0, 0, 0, 0)
        ll2.setSpacing(0)
        ll.addLayout(ll2)

        # used to fill height of the horizontal scroll bar
        w = QWidget(self)
        ll.addWidget(w)
        self._spacer = w

        self.blk = BlockList(self)
        self.blk.linkScrollBar(self.sci.verticalScrollBar())
        ll2.addWidget(self.blk)
        self.blk.setVisible(False)

        self.ann = Annotator(self.sci, self)
        ll2.addWidget(self.ann)
        self.ann.setVisible(False)

        self._ctx = None
        self._filename = None
        self._status = None
        self._annotate = False
        self._find_text = None
        self._mode = "diff" # can be 'diff' or 'file'

        self.timer = QTimer()
        self.timer.setSingleShot(False)
        self.timer.timeout.connect(self.idle_fill_files)

    def resizeEvent(self, event):
        QFrame.resizeEvent(self, event)
        h = self.sci.horizontalScrollBar().height()
        self._spacer.setMinimumHeight(h)
        self._spacer.setMaximumHeight(h)

    def setMode(self, mode):
        if isinstance(mode, bool):
            mode = ['file', 'diff'][mode]
        assert mode in ('diff', 'file')
        if mode != self._mode:
            self._mode = mode
            self.blk.setVisible(self._mode == 'file')
            self.ann.setVisible(self._mode == 'file' and self._annotate)
            self.displayFile()

    def getMode(self):
        return self._mode

    def setAnnotate(self, ann):
        self._annotate = ann
        self.blk.setVisible(self._mode == 'file')
        self.ann.setVisible(self._mode == 'file' and self._annotate)
        self.displayFile()

    def getAnnotate(self):
        return self._annotate

    def setContext(self, ctx):
        self._ctx = ctx
        self._p_rev = None
        self.sci.setTabWidth(ctx._repo.tabwidth)
        if ctx._repo.wsvisible == 'Visible':
            self.sci.setWhitespaceVisibility(qsci.WsVisible)
        elif ctx._repo.wsvisible == 'VisibleAfterIndent':
            self.sci.setWhitespaceVisibility(qsci.WsVisibleAfterIndent)
        else:
            self.sci.setWhitespaceVisibility(qsci.WsInvisible)

    def rev(self):
        return self._ctx.rev()

    def filename(self):
        return self._filename

    def displayDiff(self, rev):
        if rev != self._p_rev:
            self.displayFile(rev=rev)

    def mouseMoveEvent(self, event):
        if self._mode == 'file' and self._annotate and self.ann.fctxann:
            # Calculate row index from the scroll offset and mouse position
            scroll_offset = self.sci.verticalScrollBar().value()
            idx = scroll_offset + event.pos().y() / self.sci.textHeight(0)
            # It's possible to scroll below the bottom line
            if idx >= len(self.ann.fctxann):
                idx = len(self.ann.fctxann) - 1
            ctx = self.ann.fctxann[idx]
            rev = ctx.rev()
            desc = hglib.get_revision_desc(ctx, self.filename())
            if rev != self.lastrev:
                self.showDescSignal.emit(desc)
                self.lastrev = rev
        qsci.mouseMoveEvent(self.sci, event)

    def leaveEvent(self, event):
        self.lastrev = None
        self.showDescSignal.emit('')

    def clearDisplay(self):
        self.sci.clear()
        self.ann.clear()
        self.blk.clear()
        # Setting the label to ' ' rather than clear() keeps the label
        # from disappearing during refresh, and tool layouts bouncing
        self.filenamelabel.setText(' ')
        self.extralabel.hide()

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
            self.sci.setMarginLineNumbers(1, False)
            self.sci.setMarginWidth(1, '')
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
            self.ann.setVisible(False)
            self.sci.setText(fd.error)
            self.sci.setMarginLineNumbers(1, False)
            self.sci.setMarginWidth(1, '')
            return

        if self._mode == 'diff' and fd.diff:
            lexer = get_diff_lexer(self)
            self.sci.setLexer(lexer)
            self.sci.setText(fd.diff)
            self.sci.setMarginLineNumbers(1, False)
            self.sci.setMarginWidth(1, '')
        elif fd.contents is None:
            self.sci.setMarginLineNumbers(1, False)
            self.sci.setMarginWidth(1, '')
            return
        else:
            lexer = get_lexer(filename, fd.contents, self)
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
        if self._mode != 'file':
            return

        if self._annotate:
            self.ann.setVisible(self._annotate)
            if lexer is not None:
                self.ann.setFont(lexer.font(0))
            else:
                self.ann.setFont(self.sci.font())
            self.ann.setFilectx(self._ctx[filename])

        # Update diff margin
        if fd.contents and fd.olddata:
            if self.timer.isActive():
                self.timer.stop()

            olddata = fd.olddata.splitlines()
            newdata = fd.contents.splitlines()
            self._diff = difflib.SequenceMatcher(None, olddata, newdata)
            self._diffs = []
            self.blk.syncPageStep()
            self.timer.start()

    def nextDiff(self):
        if self._mode == 'file':
            row, column = self.sci.getCursorPosition()
            for i, (lo, hi) in enumerate(self._diffs):
                if lo > row:
                    last = (i == (len(self._diffs)-1))
                    break
            else:
                return False
            self.sci.setCursorPosition(lo, 0)
            self.sci.verticalScrollBar().setValue(lo)
            return not last

    def prevDiff(self):
        if self._mode == 'file':
            row, column = self.sci.getCursorPosition()
            for i, (lo, hi) in enumerate(reversed(self._diffs)):
                if hi < row:
                    first = (i == (len(self._diffs)-1))
                    break
            else:
                return False
            self.sci.setCursorPosition(lo, 0)
            self.sci.verticalScrollBar().setValue(lo)
            return not first

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

    def diffMode(self):
        return self._mode == 'diff'
    def fileMode(self):
        return self._mode == 'file'

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

        if type(ctx.rev()) == str:  # unapplied patch
            chunks = ctx.thgmqpatchchunks(wfile)
            self.diff = '\n'.join(chunks)
            return

        if status is None:
            status = getstatus(repo, ctx.p1().node(), ctx.node(), wfile)
        if ctx2 is None:
            ctx2 = ctx.p1()

        if status == 'S':
            try:
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
            except error.RepoError:
                self.error = _('Not an hg subrepo, not previewable')
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
                    change = 'set'
                elif 'x' not in fctx.flags() and 'x' in pfctx.flags():
                    change = 'unset'
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
        olddata = olddata.splitlines()
        newdata = newdata.splitlines()
        gen = difflib.unified_diff(olddata, newdata, oldname, wfile,
                                   lineterm='')
        data = []
        if repo.ui.config('diff', 'showfunc'):
            for chunkline in gen:
                chunkhdr = chunkhdrre.match(chunkline)
                if chunkhdr:
                    func = hglib.getchunkfunction(olddata, chunkhdr.group(1))
                    if func:
                        chunkline += func
                data.append(chunkline)
        else:
            for chunkline in gen:
                data.append(chunkline)
        data = [hglib.tounicode(l) for l in data]
        self.diff = u'\n'.join(data[2:])

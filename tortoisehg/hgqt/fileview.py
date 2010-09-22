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

import difflib

from mercurial import hg, error, match, patch, subrepo, commands
from mercurial import ui as uimod
    
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import Qsci

from tortoisehg.util import hglib
from tortoisehg.hgqt import chunkselect
from tortoisehg.util.util import exec_flag_changed, isbfile, bfilepath

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.lexers import get_lexer, get_diff_lexer
from tortoisehg.hgqt.blockmatcher import BlockList

qsci = Qsci.QsciScintilla

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
    fileDisplayed = pyqtSignal(str)
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

        self.sci = qsci(self)
        self.sci.setFrameStyle(0)
        l.addWidget(self.sci, 1)
        #self.sci.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.sci.setReadOnly(True)
        self.sci.setUtf8(True)

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

        self._model = None
        self._ctx = None
        self._filename = None
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

    def setModel(self, model):
        # XXX we really need only the "Graph" instance
        self._model = model
        self.sci.clear()

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
        if self._mode == 'file' and self._annotate:
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
        self.filenamelabel.clear()
        self.extralabel.hide()

    def displayFile(self, filename=None, rev=None, status=None):
        if self._mode == 'diff':
            self.sci.setMarginLineNumbers(1, False)
            self.sci.setMarginWidth(1, '')
        else:
            # margin 1 is used for line numbers
            self.sci.setMarginLineNumbers(1, True)
            self.sci.setMarginWidth(1, '000')

        if filename is None:
            filename = self._filename
            
        self._realfilename = filename
        if isbfile(filename):
            self._filename = bfilepath(filename)
        else:
            self._filename = filename
            
        if rev is not None:
            self._p_rev = rev
            self.revForDiffChanged.emit(rev)

        self.clearDisplay()
        if filename is None:
            return

        ctx = self._ctx
        repo = ctx._repo
        if self._p_rev is not None:
            ctx2 = repo[self._p_rev]
        else:
            ctx2 = None
        fd = filedata(ctx, ctx2, filename, status)

        if 'elabel' in fd:
            self.extralabel.setText(fd['elabel'])
            self.extralabel.show()
        else:
            self.extralabel.hide()
        self.filenamelabel.setText(fd['flabel'])

        if 'error' in fd:
            self.sci.setText(fd['error'])
            return
        diff = fd['diff']
        if self._mode == 'diff' and diff:
            lexer = get_diff_lexer(repo.ui)
            self._cur_lexer = lexer # SJB - holding refcount?
            self.sci.setLexer(lexer)
            self.sci.setText(diff)
        else:
            contents = fd['contents']
            lexer = get_lexer(filename, contents, repo.ui)
            self._cur_lexer = lexer # SJB - holding refcount?
            self.sci.setLexer(lexer)
            nlines = contents.count('\n')
            self.sci.setMarginWidth(1, str(nlines)+'0')
            self.sci.setText(contents)

        if self._find_text:
            self.highlightSearchString(self._find_text)

        self.fileDisplayed.emit(self._filename)
        if self._mode != 'file':
            return

        if self._annotate:
            if 'error' in fd:
                self.ann.setVisible(False)
            else:
                self.ann.setVisible(self._annotate)
                if lexer is not None:
                    self.ann.setFont(lexer.font(0))
                else:
                    self.ann.setFont(self.sci.font())
                self.ann.setFilectx(self._ctx[filename])

        # Update diff margin
        if 'contents' in fd and 'olddata' in fd:
            if self.timer.isActive():
                self.timer.stop()

            olddata = fd['olddata'].splitlines()
            newdata = fd['contents'].splitlines()
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
                pass
                # self.block['left'].addBlock('-', alo, ahi)
                # self.diffblock.addBlock('-', alo, ahi, blo, bhi)
                # w = self.viewers['left']
                # for i in range(alo, ahi):
                #     w.markerAdd(i, self.markerminus)

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


def filedata(ctx, ctx2, wfile, status=None):
    '''Returns a dictionary describing the specified file at the given
       revision context. If status is provided, it bypasses the
       repo.status() calls.

       The returned dictionary has several mandatory keys:
          status   - file status
          p2status - file status in ctx2
          flabel   - file label

       And several optional keys:
          contents - file contents or descriptive text
          olddata  - parent data used to generate diff
          diff     - requested diff contents
          error    - an error that prevented content retrieval
          elabel   - exec flag change label

       If the 'error' key is returned, the 'contents' and 'diff'
       keys should be ignored.  All returned text values are in
       unicode.
    '''
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

    # TODO: Teach this function about patch contexts

    labeltxt = u''
    if isbfile(wfile):
        labeltxt += u'[bfile tracked] '
    labeltxt += u'<b>%s</b>' % hglib.tounicode(wfile)

    repo = ctx._repo
    p2status = None
    if status is None:
        status = getstatus(repo, ctx.p1().node(), ctx.node(), wfile)
    if ctx2 is not None:
        p2status = getstatus(repo, ctx2.node(), ctx.node(), wfile)
    else:
        ctx2 = ctx.p1()

    fd = dict(contents=None, diff=None, status=status, flabel=labeltxt,
              p2status=p2status)

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
            fd['contents'] = u''.join(out)
            labeltxt += _(' <i>(is a dirty sub-repository)</i>')
            labeltxt += u' <a href="subrepo:%s">%s...</a>'
            fd['flabel'] = labeltxt % (hglib.tounicode(sroot), _('open'))
        except error.RepoError:
            fd['error'] = _('Not an hg subrepo, not previewable')
        return fd

    if wfile in ctx:
        warnings = chunkselect.check_max_diff(ctx, wfile)
        if warnings:
            fd['error'] = _('File or diffs not displayed: %s') % warnings[1]
            return fd

        if status != '!':
            fctx = ctx[wfile]
            newdata = fctx.data()
            fd['contents'] = hglib.tounicode(newdata)
            change = exec_flag_changed(fctx)
            if change:
                lbl = _("<b>exec mode has been <font color='red'>%s</font></b>")
                fd['elabel'] = lbl % change

    if status in ('R', '!'):
        newdata = ctx.p1()[wfile].data()
        fd['contents'] = hglib.tounicode(newdata)
        labeltxt += _(' <i>(was deleted)</i>')
        fd['flabel'] = labeltxt
        return fd
    elif status in ('I', '?'):
        try:
            data = open(repo.wjoin(wfile), 'r').read()
            if '\0' in data:
                fd['error'] = 'binary file'
            else:
                fd['contents'] = hglib.tounicode(data)
                labeltxt += _(' <i>(is unversioned)</i>')
                fd['flabel'] = labeltxt
        except EnvironmentError, e:
            fd['error'] = hglib.tounicode(str(e))
        return fd

    # TODO: elif check if a subdirectory (for manifest tool)

    if status == 'A':
        renamed = fctx.renamed()
        if not renamed:
            labeltxt += _(' <i>(was added)</i>')
            fd['flabel'] = labeltxt
            return fd

        oldname, node = renamed
        fr = hglib.tounicode(bfilepath(oldname))
        labeltxt += _(' <i>(renamed from %s)</i>') % fr
        fd['flabel'] = labeltxt
        olddata = repo.filectx(oldname, fileid=node).data()
    elif status == 'M':
        oldname = wfile
        olddata = ctx2[wfile].data()
    else:
        return fd

    fd['olddata'] = olddata
    olddata = olddata.splitlines()
    newdata = newdata.splitlines()
    gen = difflib.unified_diff(olddata, newdata, oldname, wfile)
    data = []
    for chunk in gen:
        data.extend(chunk.splitlines())
    data = [hglib.tounicode(l) for l in data]
    fd['diff'] = u'\n'.join(data[2:])
    return fd


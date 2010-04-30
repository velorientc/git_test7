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
import sys
import difflib

from mercurial.node import hex, short as short_hex, bin as short_bin
from mercurial import util
try:
    from mercurial.error import LookupError
except ImportError:
    from mercurial.revlog import LookupError
    
from PyQt4 import QtCore, QtGui, Qsci
Qt = QtCore.Qt
connect = QtCore.QObject.connect
SIGNAL = QtCore.SIGNAL
nullvariant = QtCore.QVariant()

from hgviewlib.decorators import timeit
from hgviewlib.util import exec_flag_changed, isbfile, bfilepath
from hgviewlib.config import HgConfig

from hgviewlib.qt4 import icon as geticon
from hgviewlib.qt4.hgfiledialog import FileViewer, FileDiffViewer 
from hgviewlib.qt4.hgmanifestdialog import ManifestViewer
from hgviewlib.qt4.quickbar import QuickBar
from hgviewlib.qt4.lexers import get_lexer
from hgviewlib.qt4.blockmatcher import BlockList

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
        self.sizePolicy().setControlType(QtGui.QSizePolicy.Slider)
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

        connect(textarea.verticalScrollBar(),
                SIGNAL('valueChanged(int)'),
                self.verticalScrollBar().setValue)
        
    def setFilectx(self, fctx):
        self.fctx = fctx
        ann = [f.rev() for f, line in fctx.annotate(follow=True)]
        self.setText('\n'.join(map(str, ann)))
        allrevs = list(sorted(set(ann)))
        for i, rev in enumerate(ann):
            idx = allrevs.index(rev)
            self.markerAdd(i, self.markers[idx % len(self.markers)])
        
        
        
class HgFileView(QtGui.QFrame):
    def __init__(self, parent=None):
        QtGui.QFrame.__init__(self, parent)
        framelayout = QtGui.QVBoxLayout(self)
        framelayout.setContentsMargins(0,0,0,0)
        framelayout.setSpacing(0)

        l = QtGui.QHBoxLayout()
        l.setContentsMargins(0,0,0,0)
        l.setSpacing(0)
        
        self.topLayout = QtGui.QVBoxLayout()
        self.filenamelabel = QtGui.QLabel()
        self.filenamelabel.setWordWrap(True)
        self.execflaglabel = QtGui.QLabel()
        self.execflaglabel.setWordWrap(True)
        self.topLayout.addWidget(self.filenamelabel)
        self.topLayout.addWidget(self.execflaglabel)
        self.execflaglabel.hide()
        framelayout.addLayout(self.topLayout)
        framelayout.addLayout(l, 1)

        self.sci = qsci(self)
        self.sci.setFrameStyle(0)
        l.addWidget(self.sci, 1)
        self.sci.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.sci.setReadOnly(True)

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
        self.sci.SendScintilla(qsci.SCI_MARKERSETBACK, self.markerplus, 0xB0FFA0)
        self.markerminus = self.sci.markerDefine(qsci.Background)
        self.sci.SendScintilla(qsci.SCI_MARKERSETBACK, self.markerminus, 0xA0A0FF)
        self.markertriangle = self.sci.markerDefine(qsci.Background)
        self.sci.SendScintilla(qsci.SCI_MARKERSETBACK, self.markertriangle, 0xFFA0A0)

        ll = QtGui.QVBoxLayout()
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        l.insertLayout(0, ll)

        ll2 = QtGui.QHBoxLayout()
        ll2.setContentsMargins(0, 0, 0, 0)
        ll2.setSpacing(0)
        ll.addLayout(ll2)

        # used to fill height of the horizontal scroll bar
        w = QtGui.QWidget(self)
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
        self.filedata = None

        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(False)
        self.connect(self.timer, QtCore.SIGNAL("timeout()"),
                     self.idle_fill_files)

    def resizeEvent(self, event):
        QtGui.QFrame.resizeEvent(self, event)
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

    def setAnnotate(self, ann):
        self._annotate = ann
        if ann:
            self.displayFile()
        
    def setModel(self, model):
        # XXX we really need only the "Graph" instance
        self._model = model
        self.sci.clear()

    def setContext(self, ctx):
        self._ctx = ctx
        self._p_rev = None
        self.sci.clear()

    def rev(self):
        return self._ctx.rev()

    def filename(self):
        return self._filename

    def displayDiff(self, rev):
        if rev != self._p_rev:
            self.displayFile(rev=rev)
        
    def displayFile(self, filename=None, rev=None):
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
            self.emit(SIGNAL('revForDiffChanged'), rev)
        self.sci.clear()
        self.ann.clear()
        self.filenamelabel.setText(" ")
        self.execflaglabel.clear()
        if filename is None:
            return
        try:
            filectx = self._ctx.filectx(self._realfilename)
            
        except LookupError: # occur on deleted files
            return
        if self._mode == 'diff' and self._p_rev is not None:
            mode = self._p_rev
        else:
            mode = self._mode
        flag, data = self._model.graph.filedata(filename, self._ctx.rev(), mode)
        if flag == '-':
            return
        if flag == '':
            return
        
        cfg = HgConfig(self._model.repo.ui)
        lexer = get_lexer(filename, data, flag, cfg)
        if flag == "+":
            nlines = data.count('\n')
            self.sci.setMarginWidth(1, str(nlines)+'0')
        self.sci.setLexer(lexer)
        self._cur_lexer = lexer
        if data not in ('file too big', 'binary file'):
            self.filedata = data
        else:
            self.filedata = None

        flag = exec_flag_changed(filectx)
        if flag:
            self.execflaglabel.setText("<b>exec mode has been <font color='red'>%s</font></b>" % flag)
            self.execflaglabel.show()
        else:
            self.execflaglabel.hide()

        labeltxt = ''
        if isbfile(self._realfilename):
            labeltxt += '[bfile tracked] '
        labeltxt += "<b>%s</b>" % self._filename
            
        if self._p_rev is not None:
            labeltxt += ' (diff from rev %s)' % self._p_rev
        renamed = filectx.renamed()
        if renamed:
            labeltxt += ' <i>(renamed from %s)</i>' % bfilepath(renamed[0])
        self.filenamelabel.setText(labeltxt)

        self.sci.setText(data)
        if self._find_text:
            self.highlightSearchString(self._find_text)
        self.emit(SIGNAL('fileDisplayed'), self._filename)
        self.updateDiffDecorations()
        if self._mode == 'file' and self._annotate:
            if filectx.rev() is None: # XXX hide also for binary files
                self.ann.setVisible(False)
            else:                
                self.ann.setVisible(self._annotate)
                if lexer is not None:
                    self.ann.setFont(lexer.font(0))
                else:
                    self.ann.setFont(self.sci.font())
                self.ann.setFilectx(filectx)
        return True

    def updateDiffDecorations(self):
        """
        Recompute the diff and starts the timer
        responsible for filling diff decoration markers
        """
        self.blk.clear()
        if self._mode == 'file' and self.filedata is not None:
            if self.timer.isActive():
                self.timer.stop()

            parent = self._model.graph.fileparent(self._filename, self._ctx.rev())
            if parent is None:
                return
            m = self._ctx.filectx(self._filename).renamed()
            if m:
                pfilename, pnode = m
            else:
                pfilename = self._filename
            _, parentdata = self._model.graph.filedata(pfilename,
                                                       parent, 'file')
            if parentdata is not None:
                filedata = self.filedata.splitlines()
                parentdata = parentdata.splitlines()
                self._diff = difflib.SequenceMatcher(None,
                                                     parentdata,
                                                     filedata,)
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
        self.sci.SendScintilla(qsci.SCI_SETINDICATORCURRENT, 8) # highlight
        self.sci.SendScintilla(qsci.SCI_INDICATORCLEARRANGE, 0, n)
        self.sci.SendScintilla(qsci.SCI_SETINDICATORCURRENT, 9) # current found occurrence
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
        self.emit(SIGNAL('showMessage'),
                  "Found %d occurrences of '%s' in current file or diff" % (len(pos), text),
                  2000)
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
                self.emit(SIGNAL('filled'))
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

        # ok, let's enable GUI refresh for code viewers and diff-block displayers
        self.sci.setUpdatesEnabled(True)
        self.blk.setUpdatesEnabled(True)


class HgFileListView(QtGui.QTableView):
    """
    A QTableView for displaying a HgFileListModel
    """
    def __init__(self, parent=None):
        QtGui.QTableView.__init__(self, parent)
        self.setShowGrid(False)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(20)
        self.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.setAlternatingRowColors(True)
        self.setTextElideMode(Qt.ElideLeft)

        self.horizontalHeader().setToolTip('Double click to toggle merge mode')

        self.createActions()

        connect(self.horizontalHeader(), SIGNAL('sectionDoubleClicked(int)'),
                self.toggleFullFileList)
        connect(self,
                SIGNAL('doubleClicked (const QModelIndex &)'),
                self.fileActivated)

        connect(self.horizontalHeader(),
                SIGNAL('sectionResized(int, int, int)'),
                self.sectionResized)
        self._diff_dialogs = {}
        self._nav_dialogs = {}
        
    def setModel(self, model):
        QtGui.QTableView.setModel(self, model)
        connect(model, SIGNAL('layoutChanged()'),
                self.fileSelected)
        connect(self.selectionModel(),
                SIGNAL('currentRowChanged (const QModelIndex & , const QModelIndex & )'),
                self.fileSelected)
        self.horizontalHeader().setResizeMode(1, QtGui.QHeaderView.Stretch)

    def currentFile(self):
        index = self.currentIndex()
        return self.model().fileFromIndex(index)

    def fileSelected(self, index=None, *args):
        if index is None:
            index = self.currentIndex()
        sel_file = self.model().fileFromIndex(index)
        from_rev = self.model().revFromIndex(index)
        self.emit(SIGNAL('fileSelected'), sel_file, from_rev)

    def selectFile(self, filename):
        self.setCurrentIndex(self.model().indexFromFile(filename))

    def fileActivated(self, index, alternate=False):
        sel_file = self.model().fileFromIndex(index)
        if alternate:
            self.navigate(sel_file)
        else:
            self.diffNavigate(sel_file)

    def toggleFullFileList(self, *args):
        self.model().toggleFullFileList()

    def navigate(self, filename=None):
        self._navigate(filename, FileViewer, self._nav_dialogs)

    def diffNavigate(self, filename=None):
        self._navigate(filename, FileDiffViewer, self._diff_dialogs)

    def _navigate(self, filename, dlgclass, dlgdict):
        if filename is None:
            filename = self.currentFile()
        model = self.model()
        if filename is not None and len(model.repo.file(filename))>0:
            if filename not in dlgdict:
                dlg = dlgclass(model.repo, filename,
                               repoviewer=self.window())
                dlgdict[filename] = dlg
                
                dlg.setWindowTitle('Hg file log viewer')
            dlg = dlgdict[filename] 
            dlg.goto(model.current_ctx.rev())
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

    def _action_defs(self):
        a = [("navigate", self.tr("Navigate"), None ,
              self.tr('Navigate the revision tree of this file'), None, self.navigate),
             ("diffnavigate", self.tr("Diff-mode navigate"), None,
              self.tr('Navigate the revision tree of this file in diff mode'), None, self.diffNavigate),
             ]
        return a

    def createActions(self):
        self._actions = {}
        for name, desc, icon, tip, key, cb in self._action_defs():
            act = QtGui.QAction(desc, self)
            if icon:
                act.setIcon(geticon(icon))
            if tip:
                act.setStatusTip(tip)
            if key:
                act.setShortcut(key)
            if cb:
                connect(act, SIGNAL('triggered()'), cb)
            self._actions[name] = act
            self.addAction(act)

    def contextMenuEvent(self, event):
        menu = QtGui.QMenu(self)
        for act in ['navigate', 'diffnavigate']:
            if act:
                menu.addAction(self._actions[act])
            else:
                menu.addSeparator()
        menu.exec_(event.globalPos())

    def resizeEvent(self, event):
        vp_width = self.viewport().width()
        col_widths = [self.columnWidth(i) \
                      for i in range(1, self.model().columnCount())]
        col_width = vp_width - sum(col_widths)
        col_width = max(col_width, 50)
        self.setColumnWidth(0, col_width)
        QtGui.QTableView.resizeEvent(self, event)

    def sectionResized(self, idx, oldsize, newsize):
        if idx == 1:
            self.model().setDiffWidth(newsize)

    def nextFile(self):
        row = self.currentIndex().row()
        self.setCurrentIndex(self.model().index(min(row+1,
                             self.model().rowCount() - 1), 0))
    def prevFile(self):
        row = self.currentIndex().row()
        self.setCurrentIndex(self.model().index(max(row - 1, 0), 0))

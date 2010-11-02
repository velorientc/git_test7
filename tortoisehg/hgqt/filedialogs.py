# -*- coding: utf-8 -*-
# Copyright (c) 2003-2010 LOGILAB S.A. (Paris, FRANCE).
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
Qt4 dialogs to display hg revisions of a file
"""

import difflib

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qsci import QsciScintilla

from mercurial import hg
from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.qtlib import geticon, getfont
from tortoisehg.hgqt.filerevmodel import FileRevModel
from tortoisehg.hgqt.blockmatcher import BlockList, BlockMatch
from tortoisehg.hgqt.lexers import get_lexer
from tortoisehg.hgqt.quickbar import FindInGraphlogQuickBar
from tortoisehg.hgqt.fileview import HgFileView
from tortoisehg.hgqt.repoview import HgRepoView

sides = ('left', 'right')
otherside = {'left': 'right', 'right': 'left'}

class _AbstractFileDialog(QMainWindow):
    def __init__(self, repo, filename, repoviewer=None):
        QMainWindow.__init__(self)
        self.repo = repo

        self._font = getfont('fontlog').font()
        self.setupUi(self)
        self.setRepoViewer(repoviewer)
        self._show_rev = None

        self.filename = filename
        self.findLexer()

        self.createActions()
        self.setupToolbars()

        self.setupViews()
        self.setupModels()

    def attachQuickBar(self, qbar):
        qbar.setParent(self)
        self.addToolBar(Qt.BottomToolBarArea, qbar)

    def setRepoViewer(self, repoviewer=None):
        self.repoviewer = repoviewer
        if repoviewer:
            repoviewer.finished.connect(lambda x: self.setRepoViewer(None))

    def reload(self):
        'Reload toolbar action handler'
        self.repo.thginvalidate()
        self.setupModels()

    def findLexer(self):
        # try to find a lexer for our file.
        f = self.repo.file(self.filename)
        head = f.heads()[0]
        if f.size(f.rev(head)) < 1e6:
            data = f.read(head)
        else:
            data = '' # too big
        lexer = get_lexer(self.filename, data, self)
        if lexer:
            lexer.setDefaultFont(self._font)
            lexer.setFont(self._font)
        self.lexer = lexer

    def revisionActivated(self, rev):
        """
        Callback called when a revision is double-clicked in the revisions table
        """
        if self.repoviewer is None:
            # prevent recursive import
            from workbench import Workbench
            self.repoviewer = Workbench()
        self.repoviewer.show()
        self.repoviewer.activateWindow()
        self.repoviewer.raise_()
        self.repoviewer.showRepo(hglib.tounicode(self.repo.root))
        self.repoviewer.goto(self.repo.root, rev)

class FileLogDialog(_AbstractFileDialog):
    """
    A dialog showing a revision graph for a file.
    """
    def __init__(self, repo, filename, repoviewer=None):
        super(FileLogDialog, self).__init__(repo, filename, repoviewer)
        self._readSettings()

    def closeEvent(self, event):
        self._writeSettings()
        super(FileLogDialog, self).closeEvent(event)

    def _readSettings(self):
        s = QSettings()
        s.beginGroup('filelog')
        try:
            self.restoreGeometry(s.value('geom').toByteArray())
            self.splitter.restoreState(s.value('splitter').toByteArray())
        finally:
            s.endGroup()

    def _writeSettings(self):
        s = QSettings()
        s.beginGroup('filelog')
        try:
            s.setValue('geom', self.saveGeometry())
            s.setValue('splitter', self.splitter.saveState())
        finally:
            s.endGroup()

    def setupUi(self, o):
        self.editToolbar = QToolBar(self)
        self.addToolBar(Qt.ToolBarArea(Qt.TopToolBarArea), self.editToolbar)
        self.actionClose = QAction(self, shortcut=QKeySequence.Close)
        self.actionReload = QAction(self, shortcut=QKeySequence.Refresh)
        self.editToolbar.addAction(self.actionReload)
        self.addAction(self.actionClose)

        # TODO: workaround for HgRepoView
        self.actionBack = QAction(_('Back'), self, enabled=False,
                                  icon=geticon('back'))
        self.actionForward = QAction(_('Forward'), self, enabled=False,
                                     icon=geticon('forward'))

        self.splitter = QSplitter(Qt.Vertical)
        self.setCentralWidget(self.splitter)
        self.repoview = HgRepoView(self, self.repo)
        self.textView = HgFileView(self)
        self.splitter.addWidget(self.repoview)
        self.splitter.addWidget(self.textView)

    def setupViews(self):
        self.textView.setFont(self._font)
        self.textView.showMessage.connect(self.statusBar().showMessage)

    def setupToolbars(self):
        self.findToolbar = FindInGraphlogQuickBar(self)
        self.findToolbar.attachFileView(self.textView)
        self.findToolbar.revisionSelected.connect(self.repoview.goto)
        self.findToolbar.showMessage.connect(self.statusBar().showMessage)
        self.attachQuickBar(self.findToolbar)

        self.editToolbar.addSeparator()
        self.editToolbar.addAction(self.repoview._actions['back'])
        self.editToolbar.addAction(self.repoview._actions['forward'])
        self.editToolbar.addSeparator()
        self.editToolbar.addAction(self.actionDiffMode)
        self.editToolbar.addAction(self.actionAnnMode)
        self.editToolbar.addAction(self.actionNextDiff)
        self.editToolbar.addAction(self.actionPrevDiff)

    def setupModels(self):
        self.filerevmodel = FileRevModel(self.repo)
        self.repoview.setModel(self.filerevmodel)
        self.repoview.revisionSelected.connect(self.revisionSelected)
        self.repoview.revisionActivated.connect(self.revisionActivated)
        self.filerevmodel.showMessage.connect(self.statusBar().showMessage)
        self.filerevmodel.filled.connect(self.modelFilled)
        self.textView.setMode('file')
        self.findToolbar.setModel(self.filerevmodel)
        self.findToolbar.setFilterFiles([self.filename])
        self.findToolbar.setMode('file')
        self.filerevmodel.setFilename(self.filename)

    def createActions(self):
        self.actionClose.triggered.connect(self.close)
        self.actionReload.triggered.connect(self.reload)
        self.actionReload.setIcon(geticon('reload'))

        self.actionDiffMode = QAction('Diff mode', self)
        self.actionDiffMode.setCheckable(True)
        self.actionDiffMode.toggled.connect(self.setMode)

        self.actionAnnMode = QAction('Annotate', self)
        self.actionAnnMode.setCheckable(True)
        self.actionAnnMode.toggled.connect(self.textView.setAnnotate)

        self.actionNextDiff = QAction(geticon('down'), 'Next diff', self)
        self.actionNextDiff.setShortcut('Alt+Down')
        self.actionNextDiff.triggered.connect(self.nextDiff)
        self.actionPrevDiff = QAction(geticon('up'), 'Previous diff', self)
        self.actionPrevDiff.setShortcut('Alt+Up')
        self.actionPrevDiff.triggered.connect(self.prevDiff)

        self.actionBack.triggered.connect(self.repoview.back)
        self.actionForward.triggered.connect(self.repoview.forward)

    def modelFilled(self):
        self.repoview.resizeColumns()
        if self._show_rev is not None:
            index = self.filerevmodel.indexFromRev(self._show_rev)
            self._show_rev = None
        else:
            index = self.filerevmodel.index(0,0)
        if index is not None:
            self.repoview.setCurrentIndex(index)

    def revisionSelected(self, rev):
        pos = self.textView.verticalScrollBar().value()
        ctx = self.filerevmodel.repo.changectx(rev)
        self.textView.setContext(ctx)
        self.textView.displayFile(self.filerevmodel.graph.filename(rev))
        self.textView.verticalScrollBar().setValue(pos)
        self.actionPrevDiff.setEnabled(False)
        def textfilled():
            enabled = self.textView.fileMode() and self.textView.nDiffs()
            self.actionNextDiff.setEnabled(enabled)
        self.textView.filled.connect(textfilled)

    def goto(self, rev):
        index = self.filerevmodel.indexFromRev(rev)
        if index is not None:
            self.repoview.setCurrentIndex(index)
        else:
            self._show_rev = rev

    def setMode(self, mode):
        self.textView.setMode(mode)
        self.actionAnnMode.setEnabled(not mode)
        self.actionNextDiff.setEnabled(not mode)
        self.actionPrevDiff.setEnabled(not mode)

    def nextDiff(self):
        notlast = self.textView.nextDiff()
        mode = self.textView.fileMode()
        ndiffs = self.textView.nDiffs()
        self.actionNextDiff.setEnabled(mode and notlast and ndiffs)
        self.actionPrevDiff.setEnabled(mode and ndiffs)

    def prevDiff(self):
        notfirst = self.textView.prevDiff()
        mode = self.textView.fileMode()
        ndiffs = self.textView.nDiffs()
        self.actionPrevDiff.setEnabled(mode and notfirst and ndiffs)
        self.actionNextDiff.setEnabled(mode and ndiffs)


class FileDiffDialog(_AbstractFileDialog):
    """
    Qt4 dialog to display diffs between different mercurial revisions of a file.
    """
    def __init__(self, repo, filename, repoviewer=None):
        super(FileDiffDialog, self).__init__(repo, filename, repoviewer)
        self._readSettings()

    def closeEvent(self, event):
        self._writeSettings()
        super(FileDiffDialog, self).closeEvent(event)

    def _readSettings(self):
        s = QSettings()
        s.beginGroup('filediff')
        try:
            self.restoreGeometry(s.value('geom').toByteArray())
            self.splitter.restoreState(s.value('splitter').toByteArray())
        finally:
            s.endGroup()

    def _writeSettings(self):
        s = QSettings()
        s.beginGroup('filediff')
        try:
            s.setValue('geom', self.saveGeometry())
            s.setValue('splitter', self.splitter.saveState())
        finally:
            s.endGroup()

    def setupUi(self, o):
        self.editToolbar = QToolBar(self)
        self.addToolBar(Qt.ToolBarArea(Qt.TopToolBarArea), self.editToolbar)
        self.actionClose = QAction(self, shortcut=QKeySequence.Close)
        self.actionReload = QAction(self, shortcut=QKeySequence.Refresh)
        self.editToolbar.addAction(self.actionReload)
        self.addAction(self.actionClose)

        # TODO: workaround for HgRepoView
        self.actionBack = QAction(self)
        self.actionForward = QAction(self)
        self.actionDiffMode = QAction(self)

        def layouttowidget(layout):
            w = QWidget()
            w.setLayout(layout)
            return w

        self.splitter = QSplitter(Qt.Vertical)
        self.setCentralWidget(self.splitter)
        self.horizontalLayout = QHBoxLayout()
        self.tableView_revisions_left = HgRepoView(self, self.repo)
        self.tableView_revisions_right = HgRepoView(self, self.repo)
        self.horizontalLayout.addWidget(self.tableView_revisions_left)
        self.horizontalLayout.addWidget(self.tableView_revisions_right)
        self.frame = QFrame()
        self.splitter.addWidget(layouttowidget(self.horizontalLayout))
        self.splitter.addWidget(self.frame)

    def setupViews(self):
        self.repoview = self.tableView_revisions_left
        self.tableViews = {'left': self.tableView_revisions_left,
                           'right': self.tableView_revisions_right}
        # viewers are Scintilla editors
        self.viewers = {}
        # block are diff-block displayers
        self.block = {}
        self.diffblock = BlockMatch(self.frame)
        lay = QHBoxLayout(self.frame)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)
        for side, idx  in (('left', 0), ('right', 3)):
            sci = QsciScintilla(self.frame)
            sci.setFont(self._font)
            sci.verticalScrollBar().setFocusPolicy(Qt.StrongFocus)
            sci.setFocusProxy(sci.verticalScrollBar())
            sci.verticalScrollBar().installEventFilter(self)
            sci.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            sci.setFrameShape(QFrame.NoFrame)
            sci.setMarginLineNumbers(1, True)
            sci.SendScintilla(sci.SCI_SETSELEOLFILLED, True)
            if self.lexer:
                sci.setLexer(self.lexer)

            sci.setReadOnly(True)
            lay.addWidget(sci)

            # hide margin 0 (markers)
            sci.SendScintilla(sci.SCI_SETMARGINTYPEN, 0, 0)
            sci.SendScintilla(sci.SCI_SETMARGINWIDTHN, 0, 0)
            # setup margin 1 for line numbers only
            sci.SendScintilla(sci.SCI_SETMARGINTYPEN, 1, 1)
            sci.SendScintilla(sci.SCI_SETMARGINWIDTHN, 1, 20)
            sci.SendScintilla(sci.SCI_SETMARGINMASKN, 1, 0)

            # define markers for colorize zones of diff
            self.markerplus = sci.markerDefine(QsciScintilla.Background)
            sci.SendScintilla(sci.SCI_MARKERSETBACK, self.markerplus, 0xB0FFA0)
            self.markerminus = sci.markerDefine(QsciScintilla.Background)
            sci.SendScintilla(sci.SCI_MARKERSETBACK, self.markerminus, 0xA0A0FF)
            self.markertriangle = sci.markerDefine(QsciScintilla.Background)
            sci.SendScintilla(sci.SCI_MARKERSETBACK, self.markertriangle, 0xFFA0A0)

            self.viewers[side] = sci
            blk = BlockList(self.frame)
            blk.linkScrollBar(sci.verticalScrollBar())
            self.diffblock.linkScrollBar(sci.verticalScrollBar(), side)
            lay.insertWidget(idx, blk)
            self.block[side] = blk
        lay.insertWidget(2, self.diffblock)

        for side in sides:
            table = getattr(self, 'tableView_revisions_%s' % side)
            table.setTabKeyNavigation(False)
            #table.installEventFilter(self)
            table.revisionSelected.connect(self.revisionSelected)
            table.revisionActivated.connect(self.revisionActivated)

            self.viewers[side].verticalScrollBar().valueChanged.connect(
                    lambda value, side=side: self.vbar_changed(value, side))

        self.setTabOrder(table, self.viewers['left'])
        self.setTabOrder(self.viewers['left'], self.viewers['right'])

        # timer used to fill viewers with diff block markers during GUI idle time
        self.timer = QTimer()
        self.timer.setSingleShot(False)
        self.timer.timeout.connect(self.idle_fill_files)

    def setupModels(self):
        self.filedata = {'left': None, 'right': None}
        self._invbarchanged = False
        self.filerevmodel = FileRevModel(self.repo, self.filename)
        self.filerevmodel.filled.connect(self.modelFilled)
        self.tableView_revisions_left.setModel(self.filerevmodel)
        self.tableView_revisions_right.setModel(self.filerevmodel)

    def createActions(self):
        self.actionClose.triggered.connect(self.close)
        self.actionReload.triggered.connect(self.reload)
        self.actionReload.setIcon(geticon('reload'))

        self.actionNextDiff = QAction(geticon('down'), 'Next diff', self)
        self.actionNextDiff.setShortcut('Alt+Down')
        self.actionNextDiff.triggered.connect(self.nextDiff)

        self.actionPrevDiff = QAction(geticon('up'), 'Previous diff', self)
        self.actionPrevDiff.setShortcut('Alt+Up')
        self.actionPrevDiff.triggered.connect(self.prevDiff)

        self.actionNextDiff.setEnabled(False)
        self.actionPrevDiff.setEnabled(False)

    def setupToolbars(self):
        self.editToolbar.addSeparator()
        self.editToolbar.addAction(self.actionNextDiff)
        self.editToolbar.addAction(self.actionPrevDiff)

    def modelFilled(self):
        self.tableView_revisions_left.resizeColumns()
        self.tableView_revisions_right.resizeColumns()
        if self._show_rev is not None:
            rev = self._show_rev
            self._show_rev = None
        else:
            rev = self.filerevmodel.graph[0].rev
        self.goto(rev)

    def revisionSelected(self, rev):
        if self.sender() is self.tableView_revisions_right:
            side = 'right'
        else:
            side = 'left'
        path = self.filerevmodel.graph.nodesdict[rev].extra[0]
        fc = self.repo.changectx(rev).filectx(path)
        self.filedata[side] = fc.data().splitlines()
        self.update_diff(keeppos=otherside[side])

    def goto(self, rev):
        index = self.filerevmodel.indexFromRev(rev)
        if index is not None:
            if index.row() == 0:
                index = self.filerevmodel.index(1, 0)                
            self.tableView_revisions_left.setCurrentIndex(index)
            index = self.filerevmodel.index(0, 0)                
            self.tableView_revisions_right.setCurrentIndex(index)            
        else:
            self._show_rev = rev

    def setDiffNavActions(self, pos=0):
        hasdiff = (self.diffblock.nDiffs() > 0)
        self.actionNextDiff.setEnabled(hasdiff and pos != 1)
        self.actionPrevDiff.setEnabled(hasdiff and pos != -1)

    def nextDiff(self):
        self.setDiffNavActions(self.diffblock.nextDiff())

    def prevDiff(self):
        self.setDiffNavActions(self.diffblock.prevDiff())

    def update_page_steps(self, keeppos=None):
        for side in sides:
            self.block[side].syncPageStep()
        self.diffblock.syncPageStep()
        if keeppos:
            side, pos = keeppos
            self.viewers[side].verticalScrollBar().setValue(pos)

    def idle_fill_files(self):
        # we make a burst of diff-lines computed at once, but we
        # disable GUI updates for efficiency reasons, then only
        # refresh GUI at the end of the burst
        for side in sides:
            self.viewers[side].setUpdatesEnabled(False)
            self.block[side].setUpdatesEnabled(False)
        self.diffblock.setUpdatesEnabled(False)

        for n in range(30): # burst pool
            if self._diff is None or not self._diff.get_opcodes():
                self._diff = None
                self.timer.stop()
                self.setDiffNavActions(-1)
                break

            tag, alo, ahi, blo, bhi = self._diff.get_opcodes().pop(0)

            w = self.viewers['left']
            cposl = w.SendScintilla(w.SCI_GETENDSTYLED)
            w = self.viewers['right']
            cposr = w.SendScintilla(w.SCI_GETENDSTYLED)
            if tag == 'replace':
                self.block['left'].addBlock('x', alo, ahi)
                self.block['right'].addBlock('x', blo, bhi)
                self.diffblock.addBlock('x', alo, ahi, blo, bhi)

                w = self.viewers['left']
                for i in range(alo, ahi):
                    w.markerAdd(i, self.markertriangle)

                w = self.viewers['right']
                for i in range(blo, bhi):
                    w.markerAdd(i, self.markertriangle)

            elif tag == 'delete':
                self.block['left'].addBlock('-', alo, ahi)
                self.diffblock.addBlock('-', alo, ahi, blo, bhi)

                w = self.viewers['left']
                for i in range(alo, ahi):
                    w.markerAdd(i, self.markerminus)

            elif tag == 'insert':
                self.block['right'].addBlock('+', blo, bhi)
                self.diffblock.addBlock('+', alo, ahi, blo, bhi)

                w = self.viewers['right']
                for i in range(blo, bhi):
                    w.markerAdd(i, self.markerplus)

            elif tag == 'equal':
                pass

            else:
                raise ValueError, 'unknown tag %r' % (tag,)

        # ok, let's enable GUI refresh for code viewers and diff-block displayers
        for side in sides:
            self.viewers[side].setUpdatesEnabled(True)
            self.block[side].setUpdatesEnabled(True)
        self.diffblock.setUpdatesEnabled(True)

    def update_diff(self, keeppos=None):
        """
        Recompute the diff, display files and starts the timer
        responsible for filling diff markers
        """
        if keeppos:
            pos = self.viewers[keeppos].verticalScrollBar().value()
            keeppos = (keeppos, pos)

        for side in sides:
            self.viewers[side].clear()
            self.block[side].clear()
        self.diffblock.clear()

        if None not in self.filedata.values():
            if self.timer.isActive():
                self.timer.stop()
            for side in sides:
                self.viewers[side].setMarginWidth(1, "00%s" % len(self.filedata[side]))

            self._diff = difflib.SequenceMatcher(None, self.filedata['left'],
                                                 self.filedata['right'])
            blocks = self._diff.get_opcodes()[:]

            self._diffmatch = {'left': [x[1:3] for x in blocks],
                               'right': [x[3:5] for x in blocks]}
            for side in sides:
                self.viewers[side].setText('\n'.join(self.filedata[side]))
            self.update_page_steps(keeppos)
            self.timer.start()

    def vbar_changed(self, value, side):
        """
        Callback called when the vertical scrollbar of a file viewer
        is changed, so we can update the position of the other file
        viewer.
        """
        if self._invbarchanged:
            # prevent loops in changes (left -> right -> left ...)
            return
        self._invbarchanged = True
        oside = otherside[side]

        for i, (lo, hi) in enumerate(self._diffmatch[side]):
            if lo <= value < hi:
                break
        dv = value - lo

        blo, bhi = self._diffmatch[oside][i]
        vbar = self.viewers[oside].verticalScrollBar()
        if (dv) < (bhi - blo):
            bvalue = blo + dv
        else:
            bvalue = bhi
        vbar.setValue(bvalue)
        self._invbarchanged = False

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

import sys, os
import os.path as osp

import difflib

from mercurial import ui, hg, util

from PyQt4 import QtGui, QtCore, Qsci
from PyQt4.QtCore import Qt

from tortoisehg.util.hglib import tounicode

from tortoisehg.hgqt.qtlib import geticon
from tortoisehg.hgqt.dialogmixin import HgDialogMixin
from tortoisehg.hgqt.filerevmodel import FileRevModel
from tortoisehg.hgqt.blockmatcher import BlockList, BlockMatch
from tortoisehg.hgqt.lexers import get_lexer
from tortoisehg.hgqt.quickbar import FindInGraphlogQuickBar

connect = QtCore.QObject.connect
disconnect = QtCore.QObject.disconnect
SIGNAL = QtCore.SIGNAL
nullvariant = QtCore.QVariant()

sides = ('left', 'right')
otherside = {'left': 'right', 'right': 'left'}


class AbstractFileDialog(QtGui.QMainWindow, HgDialogMixin):
    def __init__(self, repo, filename, repoviewer=None):
        self.repo = repo
        QtGui.QMainWindow.__init__(self)
        HgDialogMixin.__init__(self, self.repo.ui)

        self.setRepoViewer(repoviewer)
        self._show_rev = None

        self.filename = filename
        self.findLexer()

        self.createActions()
        self.setupToolbars()

        self.setupViews()
        self.setupModels()

    def setRepoViewer(self, repoviewer=None):
        self.repoviewer = repoviewer
        if repoviewer:
            connect(repoviewer, SIGNAL('finished(int)'),
                    lambda x: self.setRepoViewer())

    def reload(self):
        self.repo = hg.repository(self.repo.ui, self.repo.root)
        self.setupModels()

    def findLexer(self):
        # try to find a lexer for our file.
        f = self.repo.file(self.filename)
        head = f.heads()[0]
        if f.size(f.rev(head)) < 1e6:
            data = f.read(head)
        else:
            data = '' # too big
        lexer = get_lexer(self.filename, data, self.repo.ui)
        if lexer:
            lexer.setDefaultFont(self._font)
            lexer.setFont(self._font)
        self.lexer = lexer

    def modelFilled(self):
        disconnect(self.filerevmodel, SIGNAL('filled'),
                   self.modelFilled)
        if self._show_rev is not None:
            index = self.filerevmodel.indexFromRev(self._show_rev)
            self._show_rev = None
        else:
            index = self.filerevmodel.index(0,0)
        self.repoview.setCurrentIndex(index)

    def revisionActivated(self, rev):
        """
        Callback called when a revision is double-clicked in the revisions table
        """
        if self.repoviewer is None:
            # prevent recursive import
            from workbench import Workbench
            self.repoviewer = Workbench(self.repo)
        self.repoviewer.goto(rev)
        self.repoviewer.show()
        self.repoviewer.activateWindow()
        self.repoviewer.raise_()

class FileLogDialog(AbstractFileDialog):
    """
    A dialog showing a revision graph for a file.
    """
    _uifile = 'FileLogDialog.ui'

    def setupViews(self):
        self.textView.setFont(self._font)
        connect(self.textView, SIGNAL('showMessage'),
                self.statusBar().showMessage)

    def setupToolbars(self):
        self.find_toolbar = FindInGraphlogQuickBar(self)
        self.find_toolbar.attachFileView(self.textView)
        connect(self.find_toolbar, SIGNAL('revisionSelected'),
                self.repoview.goto)
        connect(self.find_toolbar, SIGNAL('showMessage'),
                self.statusBar().showMessage)
        self.attachQuickBar(self.find_toolbar)

        self.toolBar_edit.addSeparator()
        self.toolBar_edit.addAction(self.repoview._actions['back'])
        self.toolBar_edit.addAction(self.repoview._actions['forward'])
        self.toolBar_edit.addSeparator()
        self.toolBar_edit.addAction(self.actionDiffMode)
        self.toolBar_edit.addAction(self.actionAnnMode)
        self.toolBar_edit.addAction(self.actionNextDiff)
        self.toolBar_edit.addAction(self.actionPrevDiff)

        self.attachQuickBar(self.repoview.goto_toolbar)

    def setupModels(self):
        self.filerevmodel = FileRevModel(self.repo)
        self.repoview.setModel(self.filerevmodel)
        connect(self.repoview,
                SIGNAL('revisionSelected'),
                self.revisionSelected)
        connect(self.repoview,
                SIGNAL('revisionActivated'),
                self.revisionActivated)
        connect(self.filerevmodel, SIGNAL('showMessage'),
                self.statusBar().showMessage,
                Qt.QueuedConnection)
        connect(self.filerevmodel, QtCore.SIGNAL('filled'),
                self.modelFilled)
        self.textView.setMode('file')
        self.textView.setModel(self.filerevmodel)
        self.find_toolbar.setModel(self.filerevmodel)
        self.find_toolbar.setFilterFiles([self.filename])
        self.find_toolbar.setMode('file')
        self.filerevmodel.setFilename(self.filename)

    def createActions(self):
        connect(self.actionClose, SIGNAL('triggered()'),
                self.close)
        connect(self.actionReload, SIGNAL('triggered()'),
                self.reload)
        self.actionClose.setIcon(geticon('quit'))
        self.actionReload.setIcon(geticon('reload'))

        self.actionDiffMode = QtGui.QAction('Diff mode', self)
        self.actionDiffMode.setCheckable(True)
        connect(self.actionDiffMode, SIGNAL('toggled(bool)'),
                self.setMode)

        self.actionAnnMode = QtGui.QAction('Annotate', self)
        self.actionAnnMode.setCheckable(True)
        connect(self.actionAnnMode, SIGNAL('toggled(bool)'),
                self.textView.setAnnotate)

        self.actionNextDiff = QtGui.QAction(geticon('down'), 'Next diff', self)
        self.actionNextDiff.setShortcut('Alt+Down')
        self.actionPrevDiff = QtGui.QAction(geticon('up'), 'Previous diff', self)
        self.actionPrevDiff.setShortcut('Alt+Up')
        connect(self.actionNextDiff, SIGNAL('triggered()'),
                self.nextDiff)
        connect(self.actionPrevDiff, SIGNAL('triggered()'),
                self.prevDiff)

    def revisionSelected(self, rev):
        pos = self.textView.verticalScrollBar().value()
        ctx = self.filerevmodel.repo.changectx(rev)
        self.textView.setContext(ctx)
        self.textView.displayFile(self.filerevmodel.graph.filename(rev))
        self.textView.verticalScrollBar().setValue(pos)
        self.actionPrevDiff.setEnabled(False)
        connect(self.textView, SIGNAL('filled'),
                lambda self=self: self.actionNextDiff.setEnabled(self.textView.fileMode() and self.textView.nDiffs()))

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
        self.actionNextDiff.setEnabled(self.textView.fileMode() and notlast and self.textView.nDiffs())
        self.actionPrevDiff.setEnabled(self.textView.fileMode() and self.textView.nDiffs())

    def prevDiff(self):
        notfirst = self.textView.prevDiff()
        self.actionPrevDiff.setEnabled(self.textView.fileMode() and notfirst and self.textView.nDiffs())
        self.actionNextDiff.setEnabled(self.textView.fileMode() and self.textView.nDiffs())


class FileDiffDialog(AbstractFileDialog):
    """
    Qt4 dialog to display diffs between different mercurial revisions of a file.
    """
    _uifile = 'FileDiffDialog.ui'

    def setupViews(self):
        self.repoview = self.tableView_revisions_left
        self.tableViews = {'left': self.tableView_revisions_left,
                           'right': self.tableView_revisions_right}
        # viewers are Scintilla editors
        self.viewers = {}
        # block are diff-block displayers
        self.block = {}
        self.diffblock = BlockMatch(self.frame)
        lay = QtGui.QHBoxLayout(self.frame)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)
        for side, idx  in (('left', 0), ('right', 3)):
            sci = Qsci.QsciScintilla(self.frame)
            sci.setFont(self._font)
            sci.verticalScrollBar().setFocusPolicy(Qt.StrongFocus)
            sci.setFocusProxy(sci.verticalScrollBar())
            sci.verticalScrollBar().installEventFilter(self)
            sci.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            sci.setFrameShape(QtGui.QFrame.NoFrame)
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
            self.markerplus = sci.markerDefine(Qsci.QsciScintilla.Background)
            sci.SendScintilla(sci.SCI_MARKERSETBACK, self.markerplus, 0xB0FFA0)
            self.markerminus = sci.markerDefine(Qsci.QsciScintilla.Background)
            sci.SendScintilla(sci.SCI_MARKERSETBACK, self.markerminus, 0xA0A0FF)
            self.markertriangle = sci.markerDefine(Qsci.QsciScintilla.Background)
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
            connect(table, SIGNAL('revisionSelected'), self.revisionSelected)
            connect(table, SIGNAL('revisionActivated'), self.revisionActivated)

            connect(self.viewers[side].verticalScrollBar(),
                    QtCore.SIGNAL('valueChanged(int)'),
                    lambda value, side=side: self.vbar_changed(value, side))
            self.attachQuickBar(table.goto_toolbar)

        self.setTabOrder(table, self.viewers['left'])
        self.setTabOrder(self.viewers['left'], self.viewers['right'])

        # timer used to fill viewers with diff block markers during GUI idle time
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(False)
        connect(self.timer, SIGNAL("timeout()"),
                self.idle_fill_files)

    def setupModels(self):
        self.filedata = {'left': None, 'right': None}
        self._invbarchanged = False
        self.filerevmodel = FileRevModel(self.repo, self.filename)
        connect(self.filerevmodel, QtCore.SIGNAL('filled'),
                self.modelFilled)
        self.tableView_revisions_left.setModel(self.filerevmodel)
        self.tableView_revisions_right.setModel(self.filerevmodel)

    def createActions(self):
        connect(self.actionClose, SIGNAL('triggered()'),
                self.close)
        connect(self.actionReload, SIGNAL('triggered()'),
                self.reload)
        self.actionClose.setIcon(geticon('quit'))
        self.actionReload.setIcon(geticon('reload'))

        self.actionNextDiff = QtGui.QAction(geticon('down'), 'Next diff', self)
        self.actionNextDiff.setShortcut('Alt+Down')
        self.actionPrevDiff = QtGui.QAction(geticon('up'), 'Previous diff', self)
        self.actionPrevDiff.setShortcut('Alt+Up')
        connect(self.actionNextDiff, SIGNAL('triggered()'),
                self.nextDiff)
        connect(self.actionPrevDiff, SIGNAL('triggered()'),
                self.prevDiff)
        self.actionNextDiff.setEnabled(False)
        self.actionPrevDiff.setEnabled(False)

    def setupToolbars(self):
        self.toolBar_edit.addSeparator()
        self.toolBar_edit.addAction(self.actionNextDiff)
        self.toolBar_edit.addAction(self.actionPrevDiff)

    def modelFilled(self):
        disconnect(self.filerevmodel, SIGNAL('filled'),
                   self.modelFilled)
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
                self.emit(SIGNAL('diffFilled'))
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

def rootpath(repo, rev, path):
    """return the path name of 'path' relative to repo's root at
    revision rev;
    path is relative to cwd
    """  
    ctx = repo[rev]        
    filenames = list(ctx.walk(cmdutil.match(repo, [path], {})))
    if len(filenames) != 1 or filenames[0] not in ctx.manifest():
        return None
    else:
        return filenames[0]

if __name__ == '__main__':
    from mercurial import ui, hg
    from optparse import OptionParser
    opt = OptionParser()
    opt.add_option('-R', '--repo',
                   dest='repo',
                   default='.',
                   help='Hg repository')
    opt.add_option('-d', '--diff',
                   dest='diff',
                   default=False,
                   action='store_true',
                   help='Run in diff mode')

    options, args = opt.parse_args()
    if len(args)!=1:
        opt.error('provide a filename please')
        
    filename = rootpath(repo, options.rev, args[0])
    if filename is None:
        parser.error("%s is not a tracked file" % args[0])

    u = ui.ui()
    repo = hg.repository(u, options.repo)
    app = QtGui.QApplication([])

    if options.diff:
        view = FileDiffDialog(repo, filename)
    else:
        view = FileLogDialog(repo, filename)
    view.show()
    sys.exit(app.exec_())


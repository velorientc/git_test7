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
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""
Qt4 dialogs to display hg revisions of a file
"""

import os
import difflib

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, visdiff, filerevmodel, blockmatcher, lexers
from tortoisehg.hgqt import fileview, repoview, revpanel, revert
from tortoisehg.hgqt.qscilib import Scintilla

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qsci import QsciScintilla

sides = ('left', 'right')
otherside = {'left': 'right', 'right': 'left'}

class _AbstractFileDialog(QMainWindow):
    finished = pyqtSignal(int)

    def __init__(self, repo, filename):
        QMainWindow.__init__(self)
        self.repo = repo

        self.setupUi(self)
        self._show_rev = None

        assert not isinstance(filename, (unicode, QString))
        self.filename = filename

        self.setWindowTitle(_('Hg file log viewer [%s] - %s')
                            % (repo.displayname, hglib.tounicode(filename)))
        self.setWindowIcon(qtlib.geticon('hg-log'))

        self.createActions()
        self.setupToolbars()

        self.setupViews()
        self.setupModels()

    def closeEvent(self, event):
        super(_AbstractFileDialog, self).closeEvent(event)
        self.finished.emit(0)  # mimic QDialog exit

    def reload(self):
        'Reload toolbar action handler'
        self.repo.thginvalidate()
        self.setupModels()

    def onRevisionActivated(self, rev):
        """
        Callback called when a revision is double-clicked in the revisions table
        """
        # TODO: implement by using signal-slot if possible
        from tortoisehg.hgqt import run
        run.qtrun.showRepoInWorkbench(hglib.tounicode(self.repo.root), rev)

class FileLogDialog(_AbstractFileDialog):
    """
    A dialog showing a revision graph for a file.
    """
    def __init__(self, repo, filename):
        super(FileLogDialog, self).__init__(repo, filename)
        self._readSettings()
        self.menu = None
        self.dualmenu = None
        self.revdetails = None

    def closeEvent(self, event):
        self._writeSettings()
        super(FileLogDialog, self).closeEvent(event)

    def _readSettings(self):
        s = QSettings()
        s.beginGroup('filelog')
        try:
            self.textView.loadSettings(s, 'fileview')
            self.restoreGeometry(s.value('geom').toByteArray())
            self.splitter.restoreState(s.value('splitter').toByteArray())
            self.revpanel.set_expanded(s.value('revpanel.expanded').toBool())
        finally:
            s.endGroup()

    def _writeSettings(self):
        s = QSettings()
        s.beginGroup('filelog')
        try:
            self.textView.saveSettings(s, 'fileview')
            s.setValue('revpanel.expanded', self.revpanel.is_expanded())
            s.setValue('geom', self.saveGeometry())
            s.setValue('splitter', self.splitter.saveState())
        finally:
            s.endGroup()

    def setupUi(self, o):
        self.editToolbar = QToolBar(self)
        self.editToolbar.setContextMenuPolicy(Qt.PreventContextMenu)
        self.addToolBar(Qt.ToolBarArea(Qt.TopToolBarArea), self.editToolbar)
        self.actionClose = QAction(self)
        self.actionClose.setShortcuts(QKeySequence.Close)
        self.actionReload = QAction(self)
        self.actionReload.setShortcuts(QKeySequence.Refresh)
        self.editToolbar.addAction(self.actionReload)
        self.addAction(self.actionClose)

        self.splitter = QSplitter(Qt.Vertical)
        self.setCentralWidget(self.splitter)
        cs = ('fileLogDialog', _('File History Log Columns'))
        self.repoview = repoview.HgRepoView(self.repo, cs[0], cs, self.splitter)
        self.repoview.revisionSelectionChanged.connect(
            self._checkValidSelection)

        self.contentframe = QFrame(self.splitter)

        vbox = QVBoxLayout()
        vbox.setSpacing(0)
        vbox.setMargin(0)
        self.contentframe.setLayout(vbox)

        self.revpanel = revpanel.RevPanelWidget(self.repo)
        self.revpanel.linkActivated.connect(self.onLinkActivated)
        vbox.addWidget(self.revpanel, 0)

        self.textView = fileview.HgFileView(self.repo, self)
        self.textView.revisionSelected.connect(self.goto)
        vbox.addWidget(self.textView, 1)

    def setupViews(self):
        self.textView.showMessage.connect(self.statusBar().showMessage)

    def setupToolbars(self):
        self.editToolbar.addSeparator()
        self.editToolbar.addAction(self.actionBack)
        self.editToolbar.addAction(self.actionForward)

    def setupModels(self):
        self.filerevmodel = filerevmodel.FileRevModel(self.repo,
                                         self.repoview.colselect[0],
                                         parent=self)
        self.repoview.setModel(self.filerevmodel)
        self.repoview.revisionSelected.connect(self.onRevisionSelected)
        self.repoview.revisionActivated.connect(self.onRevisionActivated)
        self.repoview.menuRequested.connect(self.viewMenuRequest)
        self.filerevmodel.showMessage.connect(self.statusBar().showMessage)
        self.filerevmodel.filled.connect(self.modelFilled)
        self.filerevmodel.setFilename(self.filename)

    def createActions(self):
        self.actionClose.triggered.connect(self.close)
        self.actionReload.triggered.connect(self.reload)
        self.actionReload.setIcon(qtlib.geticon('view-refresh'))

        self.actionBack = QAction(_('Back'), self, enabled=False,
                                  icon=qtlib.geticon('go-previous'))
        self.actionForward = QAction(_('Forward'), self, enabled=False,
                                     icon=qtlib.geticon('go-next'))
        self.repoview.revisionSelected.connect(self._updateHistoryActions)
        self.actionBack.triggered.connect(self.repoview.back)
        self.actionForward.triggered.connect(self.repoview.forward)

    @pyqtSlot()
    def _updateHistoryActions(self):
        self.actionBack.setEnabled(self.repoview.canGoBack())
        self.actionForward.setEnabled(self.repoview.canGoForward())

    def modelFilled(self):
        self.repoview.resizeColumns()
        if self._show_rev is not None:
            index = self.filerevmodel.indexLinkedFromRev(self._show_rev)
            self._show_rev = None
        elif self.repoview.currentIndex().isValid():
            return  # already set by goto()
        else:
            index = self.filerevmodel.index(0,0)
        if index is not None:
            self.repoview.setCurrentIndex(index)

    @pyqtSlot(QPoint, object)
    def viewMenuRequest(self, point, selection):
        'User requested a context menu in repo view widget'
        if not selection or len(selection) > 2:
            return
        if len(selection) == 2:
            if self.dualmenu is None:
                self.dualmenu = menu = QMenu(self)
                a = menu.addAction(_('&Diff Selected Changesets'))
                a.triggered.connect(self.onVisualDiffRevs)
                a = menu.addAction(_('Diff Selected &File Revisions'))
                a.setIcon(qtlib.geticon('visualdiff'))
                a.triggered.connect(self.onVisualDiffFileRevs)
            else:
                menu = self.dualmenu
        elif self.menu is None:
            self.menu = menu = QMenu(self)
            a = menu.addAction(_('&Diff Changeset to Parent'))
            a.setIcon(qtlib.geticon('visualdiff'))
            a.triggered.connect(self.onVisualDiff)
            a = menu.addAction(_('Diff Changeset to &Local'))
            a.setIcon(qtlib.geticon('ldiff'))
            a.triggered.connect(self.onVisualDiffToLocal)
            menu.addSeparator()
            a = menu.addAction(_('Diff &File to Parent'))
            a.setIcon(qtlib.geticon('visualdiff'))
            a.triggered.connect(self.onVisualDiffFile)
            a = menu.addAction(_('Diff File to Lo&cal'))
            a.setIcon(qtlib.geticon('ldiff'))
            a.triggered.connect(self.onVisualDiffFileToLocal)
            menu.addSeparator()
            a = menu.addAction(_('&View at Revision'))
            a.setIcon(qtlib.geticon('view-at-revision'))
            a.triggered.connect(self.onViewFileAtRevision)
            a = menu.addAction(_('&Save at Revision...'))
            a.triggered.connect(self.onSaveFileAtRevision)
            a = menu.addAction(_('&Edit Local'))
            a.setIcon(qtlib.geticon('edit-file'))
            a.triggered.connect(self.onEditLocal)
            a = menu.addAction(_('&Revert to Revision...'))
            a.setIcon(qtlib.geticon('hg-revert'))
            a.triggered.connect(self.onRevertFileToRevision)
            menu.addSeparator()
            a = menu.addAction(_('Show Revision &Details'))
            a.setIcon(qtlib.geticon('hg-log'))
            a.triggered.connect(self.onShowRevisionDetails)
        else:
            menu = self.menu
        self.selection = selection
        menu.exec_(point)

    def onVisualDiff(self):
        opts = dict(change=self.selection[0])
        dlg = visdiff.visualdiff(self.repo.ui, self.repo, [], opts)
        if dlg:
            dlg.exec_()

    def onVisualDiffToLocal(self):
        opts = dict(rev=['rev(%d)' % self.selection[0]])
        dlg = visdiff.visualdiff(self.repo.ui, self.repo, [], opts)
        if dlg:
            dlg.exec_()

    def onVisualDiffRevs(self):
        revs = self.selection
        if len(revs) != 2:
            self.textView.showMessage.emit(_('You must select two revisions to diff'))
            return
        opts = dict(rev=revs)
        dlg = visdiff.visualdiff(self.repo.ui, self.repo, [], opts)
        if dlg:
            dlg.exec_()

    def onVisualDiffFile(self):
        rev = self.selection[0]
        paths = [self.filerevmodel.graph.filename(rev)]
        opts = dict(change=self.selection[0])
        dlg = visdiff.visualdiff(self.repo.ui, self.repo, paths, opts)
        if dlg:
            dlg.exec_()

    def onVisualDiffFileToLocal(self):
        rev = self.selection[0]
        paths = [self.filerevmodel.graph.filename(rev)]
        opts = dict(rev=['rev(%d)' % rev])
        dlg = visdiff.visualdiff(self.repo.ui, self.repo, paths, opts)
        if dlg:
            dlg.exec_()

    def onVisualDiffFileRevs(self):
        revs = self.selection
        if len(revs) != 2:
            self.textView.showMessage.emit(_('You must select two revisions to diff'))
            return
        paths = [self.filerevmodel.graph.filename(revs[0])]
        opts = dict(rev=['rev(%d)' % rev for rev in revs])
        dlg = visdiff.visualdiff(self.repo.ui, self.repo, paths, opts)
        if dlg:
            dlg.exec_()

    def onEditLocal(self):
        filenames = [self.filename]
        if not filenames:
            return
        qtlib.editfiles(self.repo, filenames, parent=self)

    def onRevertFileToRevision(self):
        rev = self.selection[0]
        if rev is None:
            rev = self.repo['.'].rev()
        fileSelection = [self.filerevmodel.graph.filename(rev)]
        if len(fileSelection) == 0:
            return
        dlg = revert.RevertDialog(self.repo, fileSelection, rev, self)
        if dlg:
            dlg.exec_()
            dlg.deleteLater()

    def onViewFileAtRevision(self):
        rev = self.selection[0]
        filenames = [self.filerevmodel.graph.filename(rev)]
        if not filenames:
            return
        if rev is None:
            qtlib.editfiles(self.repo, filenames, parent=self)
        else:
            base, _ = visdiff.snapshot(self.repo, filenames, self.repo[rev])
            files = [os.path.join(base, filename)
                     for filename in filenames]
            qtlib.editfiles(self.repo, files, parent=self)

    def onSaveFileAtRevision(self, rev):
        rev = self.selection[0]
        files = [self.filerevmodel.graph.filename(rev)]
        if not files or rev is None:
            return
        else:
            qtlib.savefiles(self.repo, files, rev, parent=self)

    def onShowRevisionDetails(self):
        rev = self.selection[0]
        if not self.revdetails:
            from tortoisehg.hgqt.revdetails import RevDetailsDialog
            self.revdetails = RevDetailsDialog(self.repo, rev=rev)
        else:
            self.revdetails.setRev(rev)
        self.revdetails.show()
        self.revdetails.raise_()

    @pyqtSlot(QString)
    def onLinkActivated(self, link):
        link = unicode(link)
        if ':' in link:
            scheme, param = link.split(':', 1)
            if scheme == 'cset':
                rev = self.repo[hglib.fromunicode(param)].rev()
                return self.goto(rev)
        QDesktopServices.openUrl(QUrl(link))

    def onRevisionSelected(self, rev):
        pos = self.textView.verticalScrollBar().value()
        ctx = self.filerevmodel.repo.changectx(rev)
        self.textView.setContext(ctx)
        self.textView.displayFile(self.filerevmodel.graph.filename(rev), None)
        self.textView.verticalScrollBar().setValue(pos)
        self.revpanel.set_revision(rev)
        self.revpanel.update(repo = self.repo)

    # It does not make sense to select more than two revisions at a time.
    # Rather than enforcing a max selection size we simply let the user
    # know when it has selected too many revisions by using the status bar
    @pyqtSlot()
    def _checkValidSelection(self):
        selection = self.repoview.selectedRevisions()
        if len(selection) > 2:
            msg = _('Too many rows selected for menu')
        else:
            msg = ''
        self.textView.showMessage.emit(msg)

    def goto(self, rev):
        index = self.filerevmodel.indexLinkedFromRev(rev)
        if index is not None:
            self.repoview.setCurrentIndex(index)
        else:
            self._show_rev = rev

    def showLine(self, line):
        self.textView.showLine(line - 1)  # fileview should do -1 instead?

    def setFileViewMode(self, mode):
        self.textView.setMode(mode)

    def setSearchPattern(self, text):
        self.textView.searchbar.setPattern(text)

    def setSearchCaseInsensitive(self, ignorecase):
        self.textView.searchbar.setCaseInsensitive(ignorecase)

    def reload(self):
        self.repoview.saveSettings()
        super(FileLogDialog, self).reload()

class FileDiffDialog(_AbstractFileDialog):
    """
    Qt4 dialog to display diffs between different mercurial revisions of a file.
    """
    def __init__(self, repo, filename):
        super(FileDiffDialog, self).__init__(repo, filename)
        self._readSettings()
        self.menu = None

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
        self.editToolbar.setContextMenuPolicy(Qt.PreventContextMenu)
        self.addToolBar(Qt.ToolBarArea(Qt.TopToolBarArea), self.editToolbar)
        self.actionClose = QAction(self)
        self.actionClose.setShortcuts(QKeySequence.Close)
        self.actionReload = QAction(self)
        self.actionReload.setShortcuts(QKeySequence.Refresh)
        self.editToolbar.addAction(self.actionReload)
        self.addAction(self.actionClose)

        def layouttowidget(layout):
            w = QWidget()
            w.setLayout(layout)
            return w

        self.splitter = QSplitter(Qt.Vertical)
        self.setCentralWidget(self.splitter)
        self.horizontalLayout = QHBoxLayout()
        cs = ('fileDiffDialogLeft', _('File Differences Log Columns'))
        self.tableView_revisions_left = repoview.HgRepoView(self.repo, cs[0],
                                                            cs, self)
        self.tableView_revisions_right = repoview.HgRepoView(self.repo,
                                                             'fileDiffDialogRight',
                                                             cs, self)
        self.horizontalLayout.addWidget(self.tableView_revisions_left)
        self.horizontalLayout.addWidget(self.tableView_revisions_right)
        self.tableView_revisions_right.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tableView_revisions_left.setSelectionMode(QAbstractItemView.SingleSelection)
        self.frame = QFrame()
        self.splitter.addWidget(layouttowidget(self.horizontalLayout))
        self.splitter.addWidget(self.frame)

    #@pyqtSlot(QPoint)
    def fileViewMenuRequest(self, point):
        sci = self.sender()
        menu = sci.createStandardContextMenu()
        point = sci.viewport().mapToGlobal(point)
        menu.exec_(point)

    def setupViews(self):
        self.tableViews = {'left': self.tableView_revisions_left,
                           'right': self.tableView_revisions_right}
        # viewers are Scintilla editors
        self.viewers = {}
        # block are diff-block displayers
        self.block = {}
        self.diffblock = blockmatcher.BlockMatch(self.frame)
        lay = QHBoxLayout(self.frame)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)

        try:
            contents = open(self.repo.wjoin(self.filename), "rb").read(1024)
            lexer = lexers.getlexer(self.repo.ui, self.filename, contents, self)
        except Exception:
            lexer = None

        for side, idx  in (('left', 0), ('right', 3)):
            sci = Scintilla(self.frame)
            sci.verticalScrollBar().setFocusPolicy(Qt.StrongFocus)
            sci.setFocusProxy(sci.verticalScrollBar())
            sci.verticalScrollBar().installEventFilter(self)

            sci.setContextMenuPolicy(Qt.CustomContextMenu)
            sci.customContextMenuRequested.connect(self.fileViewMenuRequest)

            sci.setFrameShape(QFrame.NoFrame)
            sci.setMarginLineNumbers(1, True)
            sci.SendScintilla(sci.SCI_SETSELEOLFILLED, True)

            sci.setLexer(lexer)
            if lexer is None:
                sci.setFont(qtlib.getfont('fontdiff').font())

            sci.setReadOnly(True)
            sci.setUtf8(True)
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
            blk = blockmatcher.BlockList(self.frame)
            blk.linkScrollBar(sci.verticalScrollBar())
            self.diffblock.linkScrollBar(sci.verticalScrollBar(), side)
            lay.insertWidget(idx, blk)
            self.block[side] = blk
        lay.insertWidget(2, self.diffblock)

        for side in sides:
            table = getattr(self, 'tableView_revisions_%s' % side)
            table.setTabKeyNavigation(False)
            #table.installEventFilter(self)
            table.revisionSelected.connect(self.onRevisionSelected)
            table.revisionActivated.connect(self.onRevisionActivated)

        l, r = (self.viewers[k].verticalScrollBar() for k in sides)
        l.valueChanged.connect(self.sbar_changed_left)
        r.valueChanged.connect(self.sbar_changed_right)

        l, r = (self.viewers[k].horizontalScrollBar() for k in sides)
        l.valueChanged.connect(r.setValue)
        r.valueChanged.connect(l.setValue)

        self.setTabOrder(table, self.viewers['left'])
        self.setTabOrder(self.viewers['left'], self.viewers['right'])

        # timer used to fill viewers with diff block markers during GUI idle time
        self.timer = QTimer()
        self.timer.setSingleShot(False)
        self.timer.timeout.connect(self.idle_fill_files)

    def setupModels(self):
        self.filedata = {'left': None, 'right': None}
        self._invbarchanged = False
        self.filerevmodel = filerevmodel.FileRevModel(self.repo,
                                         self.tableView_revisions_left.colselect[0],
                                         self.filename, parent=self)
        self.filerevmodel.filled.connect(self.modelFilled)
        self.tableView_revisions_left.setModel(self.filerevmodel)
        self.tableView_revisions_right.setModel(self.filerevmodel)
        self.tableView_revisions_left.menuRequested.connect(self.viewMenuRequest)
        self.tableView_revisions_right.menuRequested.connect(self.viewMenuRequest)

    def createActions(self):
        self.actionClose.triggered.connect(self.close)
        self.actionReload.triggered.connect(self.reload)
        self.actionReload.setIcon(qtlib.geticon('view-refresh'))

        self.actionNextDiff = QAction(qtlib.geticon('go-down'),
                                      _('Next diff'), self)
        self.actionNextDiff.setShortcut('Alt+Down')
        self.actionNextDiff.triggered.connect(self.nextDiff)

        self.actionPrevDiff = QAction(qtlib.geticon('go-up'),
                                      _('Previous diff'), self)
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
            self.goto(self._show_rev)
            self._show_rev = None
        elif self.tableView_revisions_left.currentIndex().isValid():
            return  # already set by goto()
        elif len(self.filerevmodel.graph):
            self.goto(self.filerevmodel.graph[0].rev)

    def onRevisionSelected(self, rev):
        if rev is None or rev not in self.filerevmodel.graph.nodesdict:
            return
        if self.sender() is self.tableView_revisions_right:
            side = 'right'
        else:
            side = 'left'
        path = self.filerevmodel.graph.nodesdict[rev].extra[0]
        fc = self.repo.changectx(rev).filectx(path)
        data = hglib.tounicode(fc.data())
        self.filedata[side] = data.splitlines()
        self.update_diff(keeppos=otherside[side])

    def goto(self, rev):
        index = self.filerevmodel.indexLinkedFromRev(rev)
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
                self.viewers[side].setText(u'\n'.join(self.filedata[side]))
            self.update_page_steps(keeppos)
            self.timer.start()

    @pyqtSlot(int)
    def sbar_changed_left(self, value):
        self.sbar_changed(value, 'left')

    @pyqtSlot(int)
    def sbar_changed_right(self, value):
        self.sbar_changed(value, 'right')

    def sbar_changed(self, value, side):
        """
        Callback called when a scrollbar of a file viewer
        is changed, so we can update the position of the other file
        viewer.
        """
        if self._invbarchanged or not hasattr(self, '_diffmatch'):
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

    def reload(self):
        self.tableView_revisions_left.saveSettings()
        self.tableView_revisions_right.saveSettings()
        super(FileDiffDialog, self).reload()

    @pyqtSlot(QPoint, object)
    def viewMenuRequest(self, point, selection):
        'User requested a context menu in repo view widget'
        if not selection:
            return
        if self.menu is None:
            self.menu = menu = QMenu(self)
            a = menu.addAction(_('&Diff to Parent'))
            a.setIcon(qtlib.geticon('visualdiff'))
            a.triggered.connect(self.onVisualDiff)
            a = menu.addAction(_('Diff to &Local'))
            a.setIcon(qtlib.geticon('ldiff'))
            a.triggered.connect(self.onVisualDiffToLocal)
            menu.addSeparator()
            a = menu.addAction(_('Diff &File to Parent'))
            a.setIcon(qtlib.geticon('visualdiff'))
            a.triggered.connect(self.onVisualDiffFile)
            a = menu.addAction(_('Diff File to Lo&cal'))
            a.setIcon(qtlib.geticon('ldiff'))
            a.triggered.connect(self.onVisualDiffFileToLocal)
            menu.addSeparator()
            a = menu.addAction(_('&View at Revision'))
            a.setIcon(qtlib.geticon('view-at-revision'))
            a.triggered.connect(self.onViewFileAtRevision)
            a = menu.addAction(_('&Save at Revision...'))
            a.triggered.connect(self.onSaveFileAtRevision)
            a = menu.addAction(_('&Edit Local'))
            a.setIcon(qtlib.geticon('edit-file'))
            a.triggered.connect(self.onEditLocal)
            a = menu.addAction(_('&Revert to Revision...'))
            a.setIcon(qtlib.geticon('hg-revert'))
            a.triggered.connect(self.onRevertFileToRevision)
        self.selection = selection
        self.menu.exec_(point)

    def onVisualDiff(self):
        opts = dict(change=self.selection[0])
        dlg = visdiff.visualdiff(self.repo.ui, self.repo, [], opts)
        if dlg:
            dlg.exec_()

    def onVisualDiffToLocal(self):
        opts = dict(rev=['rev(%d)' % self.selection[0]])
        dlg = visdiff.visualdiff(self.repo.ui, self.repo, [], opts)
        if dlg:
            dlg.exec_()

    def onVisualDiffFile(self):
        rev = self.selection[0]
        paths = [self.filerevmodel.graph.filename(rev)]
        opts = dict(change=self.selection[0])
        dlg = visdiff.visualdiff(self.repo.ui, self.repo, paths, opts)
        if dlg:
            dlg.exec_()

    def onVisualDiffFileToLocal(self):
        rev = self.selection[0]
        paths = [self.filerevmodel.graph.filename(rev)]
        opts = dict(rev=['rev(%d)' % rev])
        dlg = visdiff.visualdiff(self.repo.ui, self.repo, paths, opts)
        if dlg:
            dlg.exec_()

    def onEditLocal(self):
        filenames = [self.filename]
        if not filenames:
            return
        qtlib.editfiles(self.repo, filenames, parent=self)

    def onRevertFileToRevision(self):
        rev = self.selection[0]
        if rev is None:
            rev = self.repo['.'].rev()
        fileSelection = [self.filerevmodel.graph.filename(rev)]
        if len(fileSelection) == 0:
            return
        dlg = revert.RevertDialog(self.repo, fileSelection, rev, self)
        if dlg:
            dlg.exec_()
            dlg.deleteLater()

    def onViewFileAtRevision(self):
        rev = self.selection[0]
        filenames = [self.filerevmodel.graph.filename(rev)]
        if not filenames:
            return
        if rev is None:
            qtlib.editfiles(self.repo, filenames, parent=self)
        else:
            base, _ = visdiff.snapshot(self.repo, filenames, self.repo[rev])
            files = [os.path.join(base, filename)
                     for filename in filenames]
            qtlib.editfiles(self.repo, files, parent=self)

    def onSaveFileAtRevision(self, rev):
        rev = self.selection[0]
        files = [self.filerevmodel.graph.filename(rev)]
        if not files or rev is None:
            return
        else:
            qtlib.savefiles(self.repo, files, rev, parent=self)

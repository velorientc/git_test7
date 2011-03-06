# annotate.py - File annotation widget
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import ui, error, util

from tortoisehg.hgqt import visdiff, qtlib, qscilib, wctxactions, thgrepo, lexers
from tortoisehg.util import paths, hglib, colormap, thread2
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.grep import SearchWidget

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qsci import QsciScintilla, QsciStyle

# Technical Debt
#  Pass search parameters to grep
#  forward/backward history buttons
#  menu options for viewing appropriate changesets

class AnnotateView(qscilib.Scintilla):
    revisionHint = pyqtSignal(QString)

    searchRequested = pyqtSignal(QString)
    """Emitted (pattern) when user request to search content"""

    editSelected = pyqtSignal(unicode, object, int)
    """Emitted (path, rev, line) when user requests to open editor"""

    grepRequested = pyqtSignal(QString, dict)
    """Emitted (pattern, **opts) when user request to search changelog"""

    sourceChanged = pyqtSignal(unicode, object)
    """Emitted (path, rev) when the content source changed"""

    def __init__(self, repo, parent=None, **opts):
        super(AnnotateView, self).__init__(parent)
        self.setReadOnly(True)
        self.setMarginLineNumbers(1, True)
        self.setMarginType(2, QsciScintilla.TextMarginRightJustified)
        self.setMouseTracking(True)
        self.setFont(qtlib.getfont('fontdiff').font())
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menuRequest)

        self.repo = repo
        self.repo.configChanged.connect(self.configChanged)
        self.configChanged()
        self._rev = None
        self.annfile = None
        self._annotation_enabled = bool(opts.get('annotationEnabled', False))

        self._links = []  # by line
        self._revmarkers = {}  # by rev
        self._lastrev = None

        self._thread = _AnnotateThread(self)
        self._thread.finished.connect(self.fillModel)

    def configChanged(self):
        self.setIndentationWidth(self.repo.tabwidth)
        self.setTabWidth(self.repo.tabwidth)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._thread.abort()
            return
        return super(AnnotateView, self).keyPressEvent(event)

    def mouseMoveEvent(self, event):
        self._emitRevisionHintAtLine(self.lineAt(event.pos()))
        super(AnnotateView, self).mouseMoveEvent(event)

    def _emitRevisionHintAtLine(self, line):
        if line < 0:
            return
        try:
            fctx = self._links[line][0]
            if fctx.rev() != self._lastrev:
                s = hglib.get_revision_desc(fctx,
                                            hglib.fromunicode(self.annfile))
                self.revisionHint.emit(s)
                self._lastrev = fctx.rev()
        except IndexError:
            pass

    @pyqtSlot(QPoint)
    def menuRequest(self, point):
        menu = self.createStandardContextMenu()
        line = self.lineAt(point)
        point = self.mapToGlobal(point)
        if line < 0 or not self.isAnnotationEnabled():
            return menu.exec_(point)

        fctx, line = self._links[line]
        data = [hglib.tounicode(fctx.path()), fctx.rev(), line]

        if self.hasSelectedText():
            selection = self.selectedText()
            def sreq(**opts):
                return lambda: self.grepRequested.emit(selection, opts)
            def sann():
                self.searchRequested.emit(selection)
            menu.addSeparator()
            for name, func in [(_('Search in original revision'),
                                sreq(rev=fctx.rev())),
                               (_('Search in working revision'),
                                sreq(rev='.')),
                               (_('Search in current annotation'), sann),
                               (_('Search in history'), sreq(all=True))]:
                def add(name, func):
                    action = menu.addAction(name)
                    action.triggered.connect(func)
                add(name, func)

        def annorig():
            self.setSource(*data)
        def editorig():
            self.editSelected.emit(*data)
        menu.addSeparator()
        for name, func in [(_('Annotate originating revision'), annorig),
                           (_('View originating revision'), editorig)]:
            def add(name, func):
                action = menu.addAction(name)
                action.triggered.connect(func)
            add(name, func)
        for pfctx in fctx.parents():
            pdata = [hglib.tounicode(pfctx.path()), pfctx.changectx().rev(),
                     line]
            def annparent(data):
                self.setSource(*data)
            def editparent(data):
                self.editSelected.emit(*data)
            for name, func in [(_('Annotate parent revision %d') % pdata[1],
                                  annparent),
                               (_('View parent revision %d') % pdata[1],
                                  editparent)]:
                def add(name, func):
                    action = menu.addAction(name)
                    action.data = pdata
                    action.run = lambda: func(action.data)
                    action.triggered.connect(action.run)
                add(name, func)
        menu.exec_(point)

    @property
    def rev(self):
        """Returns the current revision number"""
        return self._rev

    @pyqtSlot(unicode, object, int)
    def setSource(self, wfile, rev, line=None):
        """Change the content to the specified file at rev [unicode]

        line is counted from 1.
        """
        if self.annfile == wfile and self.rev == rev:
            if line:
                self.setCursorPosition(int(line) - 1, 0)
            return

        try:
            ctx = self.repo[rev]
            fctx = ctx[hglib.fromunicode(wfile)]
        except error.LookupError:
            qtlib.ErrorMsgBox(_('Unable to annotate'),
                    _('%s is not found in revision %d') % (wfile, ctx.rev()))
            return
        self._rev = ctx.rev()
        self.clear()
        self.annfile = wfile
        if util.binary(fctx.data()):
            self.setText(_('File is binary.\n'))
        else:
            self.setText(hglib.tounicode(fctx.data()))
        if line:
            self.setCursorPosition(int(line) - 1, 0)
        self._updatelexer(fctx)
        self._updatemarginwidth()
        self.sourceChanged.emit(wfile, self._rev)
        self._updateannotation()

    def _updateannotation(self):
        if not self.isAnnotationEnabled() or not self.annfile:
            return
        ctx = self.repo[self._rev]
        fctx = ctx[hglib.fromunicode(self.annfile)]
        if util.binary(fctx.data()):
            return
        self._thread.abort()
        self._thread.start(fctx)

    @pyqtSlot()
    def fillModel(self):
        self._thread.wait()
        if self._thread.data is None:
            return

        self._links = list(self._thread.data)

        self._updaterevmargin()
        self._updatemarkers()
        self._updatemarginwidth()

    def clear(self):
        super(AnnotateView, self).clear()
        self.clearMarginText()
        self.markerDeleteAll()
        self.annfile = None

    @pyqtSlot(bool)
    def setAnnotationEnabled(self, enabled):
        """Enable / disable annotation"""
        enabled = bool(enabled)
        if enabled == self.isAnnotationEnabled():
            return
        self._annotation_enabled = enabled
        self._updateannotation()
        self._updatemarginwidth()
        self.setMouseTracking(enabled)
        if not self.isAnnotationEnabled():
            self.annfile = None
            self.markerDeleteAll()

    def isAnnotationEnabled(self):
        """True if annotation enabled and available"""
        if self.rev is None:
            return False  # annotate working copy is not supported
        return self._annotation_enabled

    def _updatelexer(self, fctx):
        """Update the lexer according to the given file"""
        lex = lexers.get_lexer(fctx.path(), hglib.tounicode(fctx.data()), self)
        self.setLexer(lex)

    def _updaterevmargin(self):
        """Update the content of margin area showing revisions"""
        s = self._margin_style
        # Workaround to set style of the current sci widget.
        # QsciStyle sends style data only to the first sci widget.
        # See qscintilla2/Qt4/qscistyle.cpp
        self.SendScintilla(QsciScintilla.SCI_STYLESETBACK,
                           s.style(), s.paper())
        self.SendScintilla(QsciScintilla.SCI_STYLESETFONT,
                           s.style(), s.font().family().toAscii().data())
        self.SendScintilla(QsciScintilla.SCI_STYLESETSIZE,
                           s.style(), s.font().pointSize())
        for i, (fctx, _origline) in enumerate(self._links):
            self.setMarginText(i, str(fctx.rev()), s)

    def _updatemarkers(self):
        """Update markers which colorizes each line"""
        self._redefinemarkers()
        for i, (fctx, _origline) in enumerate(self._links):
            m = self._revmarkers.get(fctx.rev())
            if m is not None:
                self.markerAdd(i, m)

    def _redefinemarkers(self):
        """Redefine line markers according to the current revs"""
        curdate = self.repo[self._rev].date()[0]

        # make sure to colorize at least 1 year
        mindate = curdate - 365 * 24 * 60 * 60

        self._revmarkers.clear()
        filectxs = iter(fctx for fctx, _origline in self._links)
        palette = colormap.makeannotatepalette(filectxs, curdate,
                                               maxcolors=32, maxhues=8,
                                               maxsaturations=16,
                                               mindate=mindate)
        for i, (color, fctxs) in enumerate(palette.iteritems()):
            self.markerDefine(QsciScintilla.Background, i)
            self.setMarkerBackgroundColor(QColor(color), i)
            for fctx in fctxs:
                self._revmarkers[fctx.rev()] = i

    @util.propertycache
    def _margin_style(self):
        """Style for margin area"""
        s = QsciStyle()
        s.setPaper(QApplication.palette().color(QPalette.Window))
        s.setFont(self.font())
        return s

    @pyqtSlot()
    def _updatemarginwidth(self):
        self.setMarginsFont(self.font())
        def lentext(s):
            return 'M' * (len(str(s)) + 2)  # 2 for margin
        self.setMarginWidth(1, lentext(self.lines()))
        if self.isAnnotationEnabled() and self._links:
            maxrev = max(fctx.rev() for fctx, _origline in self._links)
            self.setMarginWidth(2, lentext(maxrev))
        else:
            self.setMarginWidth(2, 0)

class _AnnotateThread(QThread):
    'Background thread for annotating a file at a revision'
    def __init__(self, parent=None):
        super(_AnnotateThread, self).__init__(parent)
        self._threadid = None

    @pyqtSlot(object)
    def start(self, fctx):
        self._fctx = fctx
        super(_AnnotateThread, self).start()
        self.data = None

    @pyqtSlot()
    def abort(self):
        if self._threadid is None:
            return
        try:
            thread2._async_raise(self._threadid, KeyboardInterrupt)
            self.wait()
        except ValueError:
            pass

    def run(self):
        assert self.currentThread() != qApp.thread()
        self._threadid = self.currentThreadId()
        try:
            data = []
            for (fctx, line), _text in self._fctx.annotate(True, True):
                data.append((fctx, line))
            self.data = data
        except KeyboardInterrupt:
            pass
        finally:
            self._threadid = None
            del self._fctx

class AnnotateDialog(QMainWindow):
    def __init__(self, *pats, **opts):
        super(AnnotateDialog,self).__init__(opts.get('parent'), Qt.Window)

        root = opts.get('root') or paths.find_root()
        repo = thgrepo.repository(ui.ui(), path=root)
        # TODO: handle repo not found

        av = AnnotateView(repo, self, annotationEnabled=True)
        self.setCentralWidget(av)
        self.av = av

        status = QStatusBar()
        self.setStatusBar(status)
        av.revisionHint.connect(status.showMessage)
        av.editSelected.connect(self.editSelected)
        av.grepRequested.connect(self._openSearchWidget)

        self._searchbar = qscilib.SearchToolBar()
        self.addToolBar(self._searchbar)
        self._searchbar.setPattern(hglib.tounicode(opts.get('pattern', '')))
        self._searchbar.searchRequested.connect(self.av.find)
        self._searchbar.conditionChanged.connect(self.av.highlightText)
        av.searchRequested.connect(self._searchbar.search)
        QShortcut(QKeySequence.Find, self,
            lambda: self._searchbar.setFocus(Qt.OtherFocusReason))

        self.av.sourceChanged.connect(
            lambda *args: self.setWindowTitle(_('Annotate %s@%d') % args))

        self.searchwidget = opts.get('searchwidget')

        self.opts = opts
        line = opts.get('line')
        if line and isinstance(line, str):
            line = int(line)

        self.repo = repo

        self.restoreSettings()

        # run heavy operation after the dialog visible
        path = hglib.tounicode(pats[0])
        rev = opts.get('rev') or '.'
        QTimer.singleShot(0, lambda: av.setSource(path, rev, line))

    def closeEvent(self, event):
        self.storeSettings()
        super(AnnotateDialog, self).closeEvent(event)

    def editSelected(self, wfile, rev, line):
        pattern = hglib.fromunicode(self._searchbar._le.text()) or None
        wfile = hglib.fromunicode(wfile)
        repo = self.repo
        try:
            ctx = repo[rev]
            fctx = ctx[wfile]
        except Exception, e:
            self.statusBar().showMessage(hglib.tounicode(str(e)))

        base, _ = visdiff.snapshot(repo, [wfile], repo[rev])
        files = [os.path.join(base, wfile)]
        wctxactions.edit(self, repo.ui, repo, files, line, pattern)

    @pyqtSlot(unicode, dict)
    def _openSearchWidget(self, pattern, opts):
        opts = dict((str(k), str(v)) for k, v in opts.iteritems())
        if self.searchwidget is None:
            self.searchwidget = SearchWidget([pattern], repo=self.repo,
                                             **opts)
            self.searchwidget.show()
        else:
            self.searchwidget.setSearch(pattern, **opts)
            self.searchwidget.show()
            self.searchwidget.raise_()

    def storeSettings(self):
        s = QSettings()
        s.setValue('annotate/geom', self.saveGeometry())
        self.av.saveSettings(s, 'annotate/av')

    def restoreSettings(self):
        s = QSettings()
        self.restoreGeometry(s.value('annotate/geom').toByteArray())
        self.av.loadSettings(s, 'annotate/av')

def run(ui, *pats, **opts):
    pats = hglib.canonpaths(pats)
    return AnnotateDialog(*pats, **opts)

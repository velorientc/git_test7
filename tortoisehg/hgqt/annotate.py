# annotate.py - File annotation widget
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os, re

from mercurial import ui, error, util

from tortoisehg.hgqt import visdiff, qtlib, qscilib, wctxactions, thgrepo, lexers
from tortoisehg.util import paths, hglib, colormap
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

    revSelected = pyqtSignal(object)
    editSelected = pyqtSignal(object)

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
        self.setFont(qtlib.getfont('fontlog').font())
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menuRequest)

        self.repo = repo
        self._rev = None
        self.annfile = None
        self._annotation_enabled = bool(opts.get('annotationEnabled', False))

        self._revs = []  # by line
        self._links = []  # by line
        self._revmarkers = {}  # by rev
        self._summaries = {}  # by rev
        self._lastrev = None

        self._thread = _AnnotateThread(self)
        self._thread.done.connect(self.fillModel)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._thread.terminate()
            return
        if event.matches(QKeySequence.FindNext):
            self.nextMatch()
            return
        if event.matches(QKeySequence.FindPrevious):
            self.prevMatch()
            return
        return super(AnnotateView, self).keyPressEvent(event)

    def mouseMoveEvent(self, event):
        line = self.lineAt(event.pos())
        if line < 0:
            return
        try:
            rev = self._revs[line]
            if rev != self._lastrev:
                self.revisionHint.emit(self._summaries[rev])
                self._lastrev = rev
        except IndexError:
            pass
        QsciScintilla.mouseMoveEvent(self, event)

    @pyqtSlot(QPoint)
    def menuRequest(self, point):
        menu = self.createStandardContextMenu()
        line = self.lineAt(point)
        point = self.mapToGlobal(point)
        if line < 0 or not self.isAnnotationEnabled():
            return menu.exec_(point)

        fctx, line = self._links[line]
        data = [fctx.path(), fctx.linkrev(), line]

        if self.hasSelectedText():
            selection = self.selectedText()
            def sreq(**opts):
                return lambda: self.grepRequested.emit(selection, opts)
            def sann():
                self.searchRequested.emit(selection)
            menu.addSeparator()
            for name, func in [(_('Search in original revision'),
                                sreq(rev=fctx.linkrev())),
                               (_('Search in working revision'),
                                sreq(rev='.')),
                               (_('Search in current annotation'), sann),
                               (_('Search in history'), sreq(all=True))]:
                def add(name, func):
                    action = menu.addAction(name)
                    action.triggered.connect(func)
                add(name, func)

        def annorig():
            self.revSelected.emit(data)
        def editorig():
            self.editSelected.emit(data)
        menu.addSeparator()
        for name, func in [(_('Annotate originating revision'), annorig),
                           (_('View originating revision'), editorig)]:
            def add(name, func):
                action = menu.addAction(name)
                action.triggered.connect(func)
            add(name, func)
        for pfctx in fctx.parents():
            pdata = [pfctx.path(), pfctx.changectx().rev(), line]
            def annparent(data):
                self.revSelected.emit(data)
            def editparent(data):
                self.editSelected.emit(data)
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
        if self._thread.isRunning():
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
        self.setText(hglib.tounicode(fctx.data()))
        if line:
            self.setCursorPosition(line - 1, 0)
        self._updatelexer(fctx)
        self._updatemarginwidth()
        self.sourceChanged.emit(wfile, self._rev)
        self._updateannotation()

    def _updateannotation(self):
        if not self.isAnnotationEnabled() or not self.annfile:
            return
        ctx = self.repo[self._rev]
        fctx = ctx[hglib.fromunicode(self.annfile)]
        curdate = fctx.date()[0]
        agedays = (curdate - fctx.date()[0]) / (24 * 60 * 60)
        self.cm = colormap.AnnotateColorSaturation(agedays)
        self.curdate = curdate
        self._thread.start(fctx)

    @pyqtSlot(object)
    def fillModel(self, data):
        revs, links = [], []
        sums = {}
        for fctx, origline in data:
            rev = fctx.linkrev()
            revs.append(rev)
            links.append([fctx, origline])
            if rev not in sums:
                sums[rev] = hglib.get_revision_desc(
                    fctx, hglib.fromunicode(self.annfile))

        self._revs = revs
        self._summaries = sums
        self._links = links

        self._updaterevmargin()
        self._updatemarkers()
        self._updatemarginwidth()

    def clear(self):
        super(AnnotateView, self).clear()
        self.clearMarginText()
        self.markerDeleteAll()

    @pyqtSlot(bool)
    def setAnnotationEnabled(self, enabled):
        """Enable / disable annotation"""
        if bool(enabled) == self.isAnnotationEnabled():
            return
        self._annotation_enabled = bool(enabled)
        self._updateannotation()
        self._updatemarginwidth()
        if not self.isAnnotationEnabled():
            self.markerDeleteAll()

    def isAnnotationEnabled(self):
        """True if annotation enabled"""
        return self._annotation_enabled

    def _updatelexer(self, fctx):
        """Update the lexer according to the given file"""
        lex = lexers.get_lexer(fctx.path(), hglib.tounicode(fctx.data()))
        if lex:
            self.setLexer(lex)

    def _updaterevmargin(self):
        """Update the content of margin area showing revisions"""
        for i, e in enumerate(self._revs):
            self.setMarginText(i, str(e), self._margin_style)

    def _updatemarkers(self):
        """Update markers which colorizes each line"""
        self._redefinemarkers()
        for i, rev in enumerate(self._revs):
            m = self._revmarkers.get(rev)
            if m is not None:
                self.markerAdd(i, m)

    def _redefinemarkers(self):
        """Redefine line markers according to the current revs"""
        self._revmarkers.clear()
        # assign from the latest rev for maximum discrimination
        for i, rev in enumerate(reversed(sorted(set(self._revs)))):
            if i >= 32:
                return  # no marker left
            color = self.cm.get_color(self.repo[rev], self.curdate)
            self.markerDefine(QsciScintilla.Background, i)
            self.setMarkerBackgroundColor(QColor(color), i)
            self._revmarkers[rev] = i

    @util.propertycache
    def _margin_style(self):
        """Style for margin area"""
        s = QsciStyle()
        s.setPaper(QApplication.palette().color(QPalette.Window))
        s.setFont(self.font())

        # Workaround to set style of the current sci widget.
        # QsciStyle sends style data only to the first sci widget.
        # See qscintilla2/Qt4/qscistyle.cpp
        self.SendScintilla(QsciScintilla.SCI_STYLESETBACK,
                           s.style(), s.paper())
        self.SendScintilla(QsciScintilla.SCI_STYLESETFONT,
                           s.style(), s.font().family().toAscii().data())
        self.SendScintilla(QsciScintilla.SCI_STYLESETSIZE,
                           s.style(), s.font().pointSize())
        return s

    @pyqtSlot()
    def _updatemarginwidth(self):
        def lentext(s):
            return 'M' * (len(str(s)) + 2)  # 2 for margin
        self.setMarginWidth(1, lentext(self.lines()))
        if self.isAnnotationEnabled() and self._revs:
            self.setMarginWidth(2, lentext(max(self._revs)))
        else:
            self.setMarginWidth(2, 0)

    def nextMatch(self):
        self.findNext()

    def prevMatch(self):
        pass # XXX

    @pyqtSlot(unicode, bool, bool)
    def searchText(self, match, icase=False, wrap=False):
        """Search text matching to the givne regexp pattern [unicode]"""
        self.findFirst(match, True, not icase, False, wrap)

    @pyqtSlot(unicode, bool)
    def highlightText(self, match, icase=False):
        """Highlight text matching to the given regexp pattern [unicode]

        The previous highlight is cleared automatically.
        """
        try:
            flags = 0
            if icase:
                flags |= re.IGNORECASE
            pat = re.compile(unicode(match).encode('utf-8'), flags)
        except re.error:
            return  # it could be partial pattern while user typing

        self.clearHighlightText()
        self.SendScintilla(self.SCI_SETINDICATORCURRENT,
                           self._highlightIndicator)

        # NOTE: pat and target text are *not* unicode because scintilla
        # requires positions in byte. For accuracy, it should do pattern
        # match in unicode, then calculating byte length of substring::
        #
        #     text = unicode(self.text())
        #     for m in pat.finditer(text):
        #         p = len(text[:m.start()].encode('utf-8'))
        #         self.SendScintilla(self.SCI_INDICATORFILLRANGE,
        #             p, len(m.group(0).encode('utf-8')))
        #
        # but it doesn't to avoid possible performance issue.
        for m in pat.finditer(unicode(self.text()).encode('utf-8')):
            self.SendScintilla(self.SCI_INDICATORFILLRANGE,
                               m.start(), m.end() - m.start())

    @pyqtSlot()
    def clearHighlightText(self):
        self.SendScintilla(self.SCI_SETINDICATORCURRENT,
                           self._highlightIndicator)
        self.SendScintilla(self.SCI_INDICATORCLEARRANGE, 0, self.length())

    @util.propertycache
    def _highlightIndicator(self):
        """Return indicator number for highlight after initializing it"""
        id = self.INDIC_CONTAINER
        self.SendScintilla(self.SCI_INDICSETSTYLE, id, self.INDIC_ROUNDBOX)
        self.SendScintilla(self.SCI_INDICSETUNDER, id, True)
        self.SendScintilla(self.SCI_INDICSETFORE, id, 0x00ffff) # 0xbbggrr
        # document says alpha value is 0 to 255, but it looks 0 to 100
        self.SendScintilla(self.SCI_INDICSETALPHA, id, 100)
        return id

class _AnnotateThread(QThread):
    'Background thread for annotating a file at a revision'
    done = pyqtSignal(object)

    def __init__(self, parent=None):
        super(_AnnotateThread, self).__init__(parent)

    @pyqtSlot(object)
    def start(self, fctx):
        self._fctx = fctx
        super(_AnnotateThread, self).start()

    def run(self):
        assert self.currentThread() != qApp.thread()
        data = []
        for (fctx, line), _text in self._fctx.annotate(True, True):
            data.append((fctx, line))
        self.done.emit(data)
        del self._fctx

class SearchToolBar(QToolBar):
    conditionChanged = pyqtSignal(unicode, bool, bool)
    """Emitted (pattern, icase, wrap) when search condition changed"""

    searchRequested = pyqtSignal(unicode, bool, bool)
    """Emitted (pattern, icase, wrap) when search button pressed"""

    def __init__(self, parent=None, hidable=False):
        super(SearchToolBar, self).__init__(_('Search'), parent,
                                            objectName='search',
                                            iconSize=QSize(16, 16))
        if hidable:
            self._close_button = QToolButton(icon=qtlib.geticon('close'),
                                             shortcut=Qt.Key_Escape)
            self._close_button.clicked.connect(self.hide)
            self.addWidget(self._close_button)

        self._lbl = QLabel(_('Regexp:'),
                           toolTip=_('Regular expression search pattern'))
        self.addWidget(self._lbl)
        self._le = QLineEdit()
        self._le.textChanged.connect(self._emitConditionChanged)
        self._le.returnPressed.connect(self._emitSearchRequested)
        self._lbl.setBuddy(self._le)
        self.addWidget(self._le)
        self._chk = QCheckBox(_('Ignore case'))
        self._chk.toggled.connect(self._emitConditionChanged)
        self.addWidget(self._chk)
        self._wrapchk = QCheckBox(_('Wrap search'))
        self._wrapchk.toggled.connect(self._emitConditionChanged)
        self.addWidget(self._wrapchk)
        self._bt = QPushButton(_('Search'), enabled=False)
        self._bt.clicked.connect(self._emitSearchRequested)
        self._le.textChanged.connect(lambda s: self._bt.setEnabled(bool(s)))
        self.addWidget(self._bt)

        self.setFocusProxy(self._le)

    @pyqtSlot()
    def _emitConditionChanged(self):
        self.conditionChanged.emit(self.pattern(), self.caseInsensitive(),
                                   self.wrapAround())

    @pyqtSlot()
    def _emitSearchRequested(self):
        self.searchRequested.emit(self.pattern(), self.caseInsensitive(),
                                  self.wrapAround())

    def pattern(self):
        """Returns the current search pattern [unicode]"""
        return self._le.text()

    def setPattern(self, text):
        """Set the search pattern [unicode]"""
        self._le.setText(text)

    def caseInsensitive(self):
        """True if case-insensitive search is requested"""
        return self._chk.isChecked()

    def setCaseInsensitive(self, icase):
        self._chk.setChecked(icase)

    def wrapAround(self):
        """True if wrap search is requested"""
        return self._wrapchk.isChecked()

    def setWrapAround(self, wrap):
        self._wrapchk.setChecked(wrap)

    @pyqtSlot(unicode)
    def search(self, text):
        """Request search with the given pattern"""
        self.setPattern(text)
        self._emitSearchRequested()

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
        av.revSelected.connect(lambda data: self.av.setSource(*data))
        av.editSelected.connect(self.editSelected)
        av.grepRequested.connect(self._openSearchWidget)

        self._searchbar = SearchToolBar()
        self.addToolBar(self._searchbar)
        self._searchbar.setPattern(hglib.tounicode(opts.get('pattern', '')))
        self._searchbar.searchRequested.connect(self.av.searchText)
        self._searchbar.conditionChanged.connect(self.av.highlightText)
        av.searchRequested.connect(self._searchbar.search)

        self.av.sourceChanged.connect(
            lambda *args: self.setWindowTitle(_('Annotate %s@%d') % args))

        self.searchwidget = opts.get('searchwidget')

        self.opts = opts
        line = opts.get('line')
        if line and isinstance(line, str):
            line = int(line)

        av.setSource(hglib.tounicode(pats[0]), opts.get('rev') or '.', line)
        self.repo = repo

        self.restoreSettings()

    def closeEvent(self, event):
        self.storeSettings()
        super(AnnotateDialog, self).closeEvent(event)

    def editSelected(self, args):
        pattern = hglib.fromunicode(self._searchbar._le.text()) or None
        repo = self.repo
        wfile, rev, line = args
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

    def wheelEvent(self, event):
        if self.childAt(event.pos()) != self._searchbar._le:
            event.ignore()
            return
        if event.delta() > 0:
            self.av.prevMatch()
        elif event.delta() < 0:
            self.av.nextMatch()

    def storeSettings(self):
        s = QSettings()
        s.setValue('annotate/geom', self.saveGeometry())
        s.setValue('annotate/wrap', self._searchbar.wrapAround())

    def restoreSettings(self):
        s = QSettings()
        self.restoreGeometry(s.value('annotate/geom').toByteArray())
        wrap = s.value('annotate/wrap', False).toBool()
        self._searchbar.setWrapAround(wrap)

def run(ui, *pats, **opts):
    pats = hglib.canonpaths(pats)
    return AnnotateDialog(*pats, **opts)

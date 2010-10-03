# annotate.py - File annotation widget
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os, re

from mercurial import ui, error, util

from tortoisehg.hgqt import visdiff, qtlib, wctxactions, thgrepo, lexers
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

class AnnotateView(QsciScintilla):
    loadBegin = pyqtSignal()
    loadComplete = pyqtSignal()
    closeSelf = pyqtSignal()

    revisionHint = pyqtSignal(QString)
    searchAtParent = pyqtSignal(QString)
    searchAll = pyqtSignal(QString)
    searchAnnotation = pyqtSignal(QString)
    searchAtRev = pyqtSignal(object)
    revSelected = pyqtSignal(object)
    editSelected = pyqtSignal(object)

    sourceChanged = pyqtSignal(unicode, object)
    """Emitted (path, rev) when the content source changed"""

    def __init__(self, repo, parent=None, **opts):
        super(AnnotateView, self).__init__(parent)
        self.setReadOnly(True)
        self.setUtf8(True)
        self.setMarginLineNumbers(1, True)
        self.setMarginType(2, QsciScintilla.TextMarginRightJustified)
        self.setMouseTracking(True)
        self.setFont(qtlib.getfont('fontlog').font())
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menuRequest)

        self.repo = repo
        self._rev = None
        self._annotation_enabled = bool(opts.get('annotationEnabled', False))

        self._revs = []  # by line
        self._links = []  # by line
        self._revmarkers = {}  # by rev
        self._summaries = {}  # by rev
        self._lastrev = None

        self.thread = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.thread and self.thread.isRunning():
                self.thread.terminate()
                self.finished()
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
        menu = qtlib.createStandardContextMenuForScintilla(self)
        line = self.lineAt(point)
        point = self.mapToGlobal(point)
        if line < 0 or not self.isAnnotationEnabled():
            return menu.exec_(point)

        fctx, line = self._links[line]
        data = [fctx.path(), fctx.linkrev(), line]

        if self.hasSelectedText():
            selection = self.selectedText()
            def sorig():
                sdata = [selection, str(fctx.linkrev())]
                self.searchAtRev.emit(sdata)
            def sctx():
                self.searchAtParent.emit(selection)
            def searchall():
                self.searchAll.emit(selection)
            def sann():
                self.searchAnnotation.emit(selection)
            menu.addSeparator()
            for name, func in [(_('Search in original revision'), sorig),
                               (_('Search in working revision'), sctx),
                               (_('Search in current annotation'), sann),
                               (_('Search in history'), searchall)]:
                def add(name, func):
                    action = menu.addAction(name)
                    action.triggered.connect(func)
                add(name, func)
            return menu.exec_(point)

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
        """Change the content to the specified file at rev [unicode]"""
        if self.thread is not None:
            return
        try:
            ctx = self.repo[rev]
            fctx = ctx[hglib.fromunicode(wfile)]
        except error.LookupError:
            qtlib.ErrorMsgBox(_('Unable to annotate'),
                    _('%s is not found in revision %d') % (wfile, ctx.rev()))
            self.closeSelf.emit()
            return
        self._rev = ctx.rev()
        self.clear()
        self.resumeline = line
        self.annfile = wfile
        self.setText(hglib.tounicode(fctx.data()))
        self._updatelexer(fctx)
        self._updatemarginwidth()
        self.sourceChanged.emit(wfile, self._rev)
        self._updateannotation()

    def _updateannotation(self):
        if not self.isAnnotationEnabled():
            return
        ctx = self.repo[self._rev]
        fctx = ctx[hglib.fromunicode(self.annfile)]
        curdate = fctx.date()[0]
        agedays = (curdate - fctx.date()[0]) / (24 * 60 * 60)
        self.cm = colormap.AnnotateColorSaturation(agedays)
        self.curdate = curdate
        self.loadBegin.emit()
        self.thread = AnnotateThread(fctx)
        self.thread.done.connect(self.finished)
        self.thread.start()

    def finished(self):
        self.thread.wait()
        self.loadComplete.emit()
        if hasattr(self.thread, 'data'):
            self.fillModel(self.thread.data)
        self.thread = None

    def fillModel(self, data):
        revs, links = [], []
        sums = {}
        for fctx, origline, text in data:
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

        # Workaround to set style of the current sci widget.
        # QsciStyle sends style data only to the first sci widget.
        # See qscintilla2/Qt4/qscistyle.cpp
        self.SendScintilla(QsciScintilla.SCI_STYLESETBACK,
                           s.style(), s.paper())
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
        """Highlight text matching to the given regexp pattern [unicode]"""
        try:
            flags = 0
            if icase:
                flags |= re.IGNORECASE
            pat = re.compile(unicode(match), flags)
        except re.error:
            return  # it could be partial pattern while user typing

        self.clearHighlightText()
        self.SendScintilla(self.SCI_SETINDICATORCURRENT,
                           self._highlightIndicator)

        for m in pat.finditer(unicode(self.text())):
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
        self.SendScintilla(self.SCI_INDICSETFORE, id, 0x00ffff) # 0xbbggrr
        # document says alpha value is 0 to 255, but it looks 0 to 100
        self.SendScintilla(self.SCI_INDICSETALPHA, id, 100)
        return id

class AnnotateThread(QThread):
    'Background thread for annotating a file at a revision'
    done = pyqtSignal()
    def __init__(self, fctx):
        super(AnnotateThread, self).__init__()
        self.fctx = fctx

    def run(self):
        data = []
        for (fctx, line), text in self.fctx.annotate(True, True):
            data.append([fctx, line, text])
        self.data = data
        self.done.emit()

class AnnotateDialog(QDialog):
    def __init__(self, *pats, **opts):
        super(AnnotateDialog,self).__init__(opts.get('parent'), Qt.Window)

        mainvbox = QVBoxLayout()
        self.setLayout(mainvbox)

        hbox = QHBoxLayout()
        hbox.setMargin(0)
        lbl = QLabel(_('Regexp:'))
        le = QLineEdit()
        le.setText(hglib.tounicode(opts.get('pattern', '')))
        lbl.setBuddy(le)
        lbl.setToolTip(_('Regular expression search pattern'))
        bt = QPushButton(_('Search'), enabled=False, default=True,
                         shortcut=QKeySequence.Find)
        bt.clicked.connect(self.searchText)
        chk = QCheckBox(_('Ignore case'))
        wrapchk = QCheckBox(_('Wrap search'))
        hbox.addWidget(lbl)
        hbox.addWidget(le, 1)
        hbox.addWidget(chk)
        hbox.addWidget(wrapchk)
        hbox.addWidget(bt)
        mainvbox.addLayout(hbox)
        self.le, self.chk, self.wrapchk = le, chk, wrapchk

        root = opts.get('root') or paths.find_root()
        repo = thgrepo.repository(ui.ui(), path=root)
        # TODO: handle repo not found

        av = AnnotateView(repo, self, annotationEnabled=True)
        mainvbox.addWidget(av)
        self.av = av

        status = QLabel()
        mainvbox.addWidget(status)
        av.revisionHint.connect(status.setText)
        av.revSelected.connect(lambda data: self.av.setSource(*data))
        av.editSelected.connect(self.editSelected)
        av.searchAtRev.connect(self.searchAtRev)
        av.searchAtParent.connect(self.searchAtParent)
        av.searchAll.connect(self.searchAll)
        av.searchAnnotation.connect(self.searchAnnotation)
        av.closeSelf.connect(self.closeSelf)

        self.le.textChanged.connect(self.highlightText)
        self.chk.toggled.connect(self.highlightText)
        self.le.textChanged.connect(lambda s: bt.setEnabled(bool(s)))
        self.av.sourceChanged.connect(
            lambda *args: self.setWindowTitle(_('Annotate %s@%d') % args))

        self.status = status
        self.searchwidget = opts.get('searchwidget')

        self.opts = opts
        line = opts.get('line')
        if line and isinstance(line, str):
            line = int(line)

        av.setSource(hglib.tounicode(pats[0]), opts.get('rev') or '.', line)
        self.repo = repo

        self.restoreSettings()

    def closeSelf(self):
        self.close()
        QTimer.singleShot(0, self.reject)

    def editSelected(self, args):
        pattern = hglib.fromunicode(self.le.text()) or None
        repo = self.repo
        wfile, rev, line = args
        try:
            ctx = repo[rev]
            fctx = ctx[wfile]
        except Exception, e:
            self.status.setText(hglib.tounicode(str(e)))

        base, _ = visdiff.snapshot(repo, [wfile], repo[rev])
        files = [os.path.join(base, wfile)]
        wctxactions.edit(self, repo.ui, repo, files, line, pattern)

    def searchAtRev(self, args):
        if self.searchwidget is None:
            self.searchwidget = SearchWidget([args[0]], repo=self.repo,
                                             rev=args[1])
            self.searchwidget.show()
        else:
            self.searchwidget.setSearch(args[0], rev=args[1])
            self.searchwidget.show()
            self.searchwidget.raise_()

    def searchAtParent(self, pattern):
        if self.searchwidget is None:
            self.searchwidget = SearchWidget([pattern], repo=self.repo,
                                             rev='.')
            self.searchwidget.show()
        else:
            self.searchwidget.setSearch(pattern, rev='.')
            self.searchwidget.show()
            self.searchwidget.raise_()

    def searchAll(self, pattern):
        if self.searchwidget is None:
            self.searchwidget = SearchWidget([pattern], repo=self.repo,
                                             all=True)
            self.searchwidget.show()
        else:
            self.searchwidget.setSearch(pattern, all=True)
            self.searchwidget.show()
            self.searchwidget.raise_()

    def searchAnnotation(self, pattern):
        self.le.setText(QRegExp.escape(pattern))
        self.av.searchText(pattern, False, wrap=self.wrapchk.isChecked())

    @pyqtSlot()
    def searchText(self):
        self.av.searchText(self.le.text(), icase=self.chk.isChecked(),
                           wrap=self.wrapchk.isChecked())

    @pyqtSlot()
    def highlightText(self):
        self.av.clearHighlightText()
        self.av.highlightText(self.le.text(), icase=self.chk.isChecked())

    def wheelEvent(self, event):
        if self.childAt(event.pos()) != self.le:
            event.ignore()
            return
        if event.delta() > 0:
            self.av.prevMatch()
        elif event.delta() < 0:
            self.av.nextMatch()

    def accept(self):
        self.storeSettings()
        super(AnnotateDialog, self).accept()

    def reject(self):
        self.storeSettings()
        super(AnnotateDialog, self).reject()

    def storeSettings(self):
        s = QSettings()
        s.setValue('annotate/geom', self.saveGeometry())
        s.setValue('annotate/wrap', self.wrapchk.isChecked())

    def restoreSettings(self):
        s = QSettings()
        self.restoreGeometry(s.value('annotate/geom').toByteArray())
        wrap = s.value('annotate/wrap', False).toBool()
        self.wrapchk.setChecked(wrap)

def run(ui, *pats, **opts):
    pats = hglib.canonpaths(pats)
    return AnnotateDialog(*pats, **opts)

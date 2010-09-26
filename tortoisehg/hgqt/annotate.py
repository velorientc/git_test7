# annotate.py - File annotation widget
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import re

from mercurial import ui, hg, error, commands, cmdutil, util

from tortoisehg.hgqt import visdiff, qtlib, wctxactions, thgrepo
from tortoisehg.util import paths, hglib, colormap
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.grep import SearchWidget

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qsci import QsciScintilla, QsciStyle

# Technical Debt
#  Syntax Highlighting?
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

    def __init__(self, parent=None):
        super(AnnotateView, self).__init__(parent)
        self.setReadOnly(True)
        self.setUtf8(True)
        self.setMarginLineNumbers(1, True)
        self.setMarginType(2, QsciScintilla.TextMarginRightJustified)
        self.setMouseTracking(True)
        self.linesChanged.connect(self._updatemargin)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menuRequest)
        self._revs = []  # by line
        self._links = []  # by line
        self._revmarkers = {}  # by color
        self._summaries = {}  # by rev
        self._lastrev = None

        self.thread = None
        self.wrap = False

    def mouseMoveEvent(self, event):
        line = self.lineAt(event.pos())
        if line < 0:
            return
        rev = self._revs[line]
        if rev != self._lastrev:
            self.revisionHint.emit(self._summaries[rev])
            self._lastrev = rev

    @pyqtSlot(QPoint)
    def menuRequest(self, point):
        line = self.lineAt(point)
        point = self.mapToGlobal(point)
        if line < 0:
            return

        fctx, line = self._links[line]
        data = [fctx.path(), fctx.linkrev(), line]

        """ XXX context menu for selected text
        c = self.textCursor()
        selection = c.selection().toPlainText()
        if selection and cursor.position() >= c.selectionStart() and \
                cursor.position() <= c.selectionEnd():
            selection = c.selection().toPlainText()
            def sorig():
                sdata = [selection, str(fctx.linkrev())]
                self.searchAtRev.emit(sdata)
            def sctx():
                self.searchAtParent.emit(selection)
            def searchall():
                self.searchAll.emit(selection)
            def sann():
                self.searchAnnotation.emit(selection)
            menu = QMenu(self)
            for name, func in [(_('Search in original revision'), sorig),
                               (_('Search in working revision'), sctx),
                               (_('Search in current annotation'), sann),
                               (_('Search in history'), searchall)]:
                def add(name, func):
                    action = menu.addAction(name)
                    action.triggered.connect(func)
                add(name, func)
            return menu.exec_(point)
        """

        def annorig():
            self.revSelected.emit(data)
        def editorig():
            self.editSelected.emit(data)
        menu = QMenu(self)
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

    @pyqtSlot()
    def _updatemargin(self):
        self.setMarginWidth(1, 'M' * (len(str(self.lines()))))
        self.setMarginWidth(2, 'M' * 4) # XXX

    def setLineBackground(self, line, color):
        # TODO: assign markers from the latest
        if color not in self._revmarkers and len(self._revmarkers) < 32:
            m = len(self._revmarkers)
            self.markerDefine(QsciScintilla.Background, m)
            self.setMarkerBackgroundColor(QColor(color), m)
            self._revmarkers[color] = m
        if color in self._revmarkers:
            self.markerAdd(line, self._revmarkers[color])

    def setContent(self, text, revs, summaries, links):
        self.setText(text)
        self._revs = list(revs)
        self._revmarkers.clear()
        self._summaries = summaries.copy()
        self._links = list(links)

        for i, e in enumerate(self._revs):
            self.setMarginText(i, str(e), self._margin_style)

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

    def annotateFileAtRev(self, repo, ctx, wfile, line=None):
        if self.thread is not None:
            return
        try:
            fctx = ctx[wfile]
        except error.LookupError:
            qtlib.ErrorMsgBox(_('Unable to annotate'),
                    _('%s is not found in revision %d') % (wfile, ctx.rev()))
            self.closeSelf.emit()
            return
        curdate = fctx.date()[0]
        basedate = repo.filectx(wfile, fileid=0).date()[0]
        agedays = (curdate - fctx.date()[0]) / (24 * 60 * 60)
        self.cm = colormap.AnnotateColorSaturation(agedays)
        self.curdate = curdate
        self.repo = repo
        self.resumeline = line
        self.annfile = wfile
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

    def fillModel(self, data):
        revs, lines, lpos, sels, links = [], [], [], [], []
        sums = {}
        pos = 0
        for fctx, origline, text in data:
            rev = fctx.linkrev()
            lines.append(text)
            lpos.append(pos)
            revs.append(rev)
            links.append([fctx, origline])
            pos += len(hglib.tounicode(text))
            if rev not in sums:
                sums[rev] = hglib.get_revision_desc(fctx, self.annfile)

        self.setContent(hglib.tounicode(''.join(lines)),
                        revs, sums, links)

        for i, rev in enumerate(revs):
            ctx = self.repo[rev]
            rgb = self.cm.get_color(ctx, self.curdate)
            self.setLineBackground(i, rgb)

    def nextMatch(self):
        self.findNext()

    def prevMatch(self):
        pass # XXX

    def searchText(self, match, icase):
        self.findFirst(match.pattern(), True, icase, False, self.wrap)

    def setWrap(self, wrap):
        self.wrap = wrap

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
        bt = QPushButton(_('Search'))
        bt.setDefault(True)
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

        av = AnnotateView(self)
        wrapchk.stateChanged.connect(av.setWrap)
        mainvbox.addWidget(av)
        self.av = av

        status = QLabel()
        mainvbox.addWidget(status)
        av.revisionHint.connect(status.setText)
        av.revSelected.connect(self.revSelected)
        av.editSelected.connect(self.editSelected)
        av.searchAtRev.connect(self.searchAtRev)
        av.searchAtParent.connect(self.searchAtParent)
        av.searchAll.connect(self.searchAll)
        av.searchAnnotation.connect(self.searchAnnotation)
        av.closeSelf.connect(self.closeSelf)

        self.status = status
        self.searchwidget = opts.get('searchwidget')

        self.opts = opts
        line = opts.get('line')
        if line and isinstance(line, str):
            line = int(line)
        try:
            root = opts.get('root') or paths.find_root()
            repo = thgrepo.repository(ui.ui(), path=root)
            ctx = repo[opts.get('rev') or '.']
            fctx = ctx[pats[0]] # just for validation
        except Exception, e:
            self.status.setText(hglib.tounicode(str(e)))
            self.close()
            return

        av.annotateFileAtRev(repo, ctx, pats[0], line)
        self.setWindowTitle(_('Annotate %s@%d') % (pats[0], ctx.rev()))
        self.repo = repo

        self.restoreSettings()

    def closeSelf(self):
        self.close()
        QTimer.singleShot(0, self.reject)

    def revSelected(self, args):
        repo = self.repo
        wfile, rev, line = args
        try:
            ctx = repo[rev]
            fctx = ctx[wfile]
        except Exception, e:
            self.status.setText(hglib.tounicode(str(e)))
        self.av.annotateFileAtRev(repo, ctx, wfile, line)
        self.setWindowTitle(_('Annotate %s@%d') % (wfile, ctx.rev()))

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
            self.searchwidget = SearchWidget([args[0]], rev=args[1])
            self.searchwidget.show()
        else:
            self.searchwidget.setSearch(args[0], rev=args[1])
            self.searchwidget.raise_()

    def searchAtParent(self, pattern):
        if self.searchwidget is None:
            self.searchwidget = SearchWidget([pattern], rev='.')
            self.searchwidget.show()
        else:
            self.searchwidget.setSearch(pattern, rev='.')
            self.searchwidget.raise_()

    def searchAll(self, pattern):
        if self.searchwidget is None:
            self.searchwidget = SearchWidget([pattern], all=True)
            self.searchwidget.show()
        else:
            self.searchwidget.setSearch(pattern, all=True)
            self.searchwidget.raise_()

    def searchAnnotation(self, pattern):
        self.le.setText(QRegExp.escape(pattern))
        self.av.searchText(pattern, False)

    def searchText(self):
        pattern = hglib.fromunicode(self.le.text())
        if not pattern:
            return
        try:
            regexp = re.compile(pattern)
        except Exception, inst:
            msg = _('grep: invalid match pattern: %s\n') % inst
            self.status.setText(hglib.tounicode(msg))
        if self.chk.isChecked():
            regexp = QRegExp(pattern, Qt.CaseInsensitive)
            icase = True
        else:
            icase = False
            regexp = QRegExp(pattern, Qt.CaseSensitive)
        self.av.searchText(regexp, icase)

    def wheelEvent(self, event):
        if self.childAt(event.pos()) != self.le:
            event.ignore()
            return
        if event.delta() > 0:
            self.av.prevMatch()
        elif event.delta() < 0:
            self.av.nextMatch()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Find):
            self.searchText()
            return
        return super(AnnotateDialog, self).keyPressEvent(event)

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

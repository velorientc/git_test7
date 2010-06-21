# annotate.py - File annotation widget
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import re

from mercurial import ui, hg, error, commands, cmdutil, util

from tortoisehg.hgqt import visdiff, qtlib, wctxactions
from tortoisehg.util import paths, hglib, colormap
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.grep import SearchWidget

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# Technical Debt
#  Syntax Highlighting?
#  Pass search parameters to grep
#  forward/backward history buttons
#  menu options for viewing appropriate changesets

class AnnotateView(QFrame):
    loadBegin = pyqtSignal()
    loadComplete = pyqtSignal()
    revisionHint = pyqtSignal(QString)

    class RevArea(QWidget):
        'Display user@rev in front of each line'
        def __init__(self, edit, parent=None):
            QWidget.__init__(self, parent)
            self.edit = edit
            self.width = 0
        def sizeHint(self):
            return QSize(self.width, 0)
        def updateContents(self, rect, scroll):
            if scroll:
                self.scroll(0, scroll)
            else:
                self.update(0, rect.y(), self.width, rect.height())
        def paintEvent(self, event):
            self.edit.paintRevArea(self, event)
            QWidget.paintEvent(self, event)

    class TextArea(QPlainTextEdit):
        'Display lines of annotation text'

        revisionHint = pyqtSignal(QString)

        def __init__(self, parent=None):
            QPlainTextEdit.__init__(self, parent)
            self.document().setDefaultStyleSheet(qtlib.thgstylesheet)
            self.setReadOnly(True)
            self.setFont(QFont('Monospace'))
            self.setContextMenuPolicy(Qt.CustomContextMenu)
            self.connect(self,
                    SIGNAL('customContextMenuRequested(const QPoint &)'),
                    self.customContextMenuRequested)
            self.setTextInteractionFlags(Qt.TextSelectableByMouse |
                                         Qt.TextSelectableByKeyboard)
            tm = QFontMetrics(self.font())
            self.charwidth = tm.width('9')
            self.charheight = tm.height()
            self.revs = []
            self.summaries = []
            self.setMouseTracking(True)
            self.lastrev = None

        def paintRevArea(self, revarea, event):
            painter = QPainter(revarea)
            painter.fillRect(event.rect(), Qt.lightGray)

            block = self.firstVisibleBlock()
            line = block.blockNumber()

            offs = self.contentOffset()
            top = self.blockBoundingGeometry(block).translated(offs).top()
            while block.isValid() and line < len(self.revs):
                if not block.isVisible() or top >= event.rect().bottom():
                    break
                painter.setPen(Qt.black)
                rect = QRect(0, top, revarea.width, self.charheight)
                painter.drawText(rect, Qt.AlignRight, str(self.revs[line]))
                block = block.next()
                top += self.blockBoundingGeometry(block).height()
                line += 1

        def mouseMoveEvent(self, event):
            cursor = self.cursorForPosition(event.pos())
            line = cursor.block()
            if not line.isValid() or line.blockNumber() >= len(self.revs):
                return
            rev = self.revs[line.blockNumber()]
            if rev != self.lastrev:
                self.revisionHint.emit(self.summaries[rev])
                self.lastrev = rev

        def customContextMenuRequested(self, point):
            cursor = self.cursorForPosition(point)
            point = self.mapToGlobal(point)

            line = cursor.block()
            if not line.isValid() or line.blockNumber() >= len(self.revs):
                return
            fctx, line = self.links[line.blockNumber()]
            data = [fctx.path(), fctx.linkrev(), line]

            # check if the user has opened a menu on a text selection
            c = self.textCursor()
            selection = c.selection().toPlainText()
            if selection and cursor.position() >= c.selectionStart() and \
                    cursor.position() <= c.selectionEnd():
                selection = c.selection().toPlainText()
                def sorig():
                    sdata = [selection, str(fctx.linkrev())]
                    self.emit(SIGNAL('searchAtRev'), sdata)
                def sctx():
                    self.emit(SIGNAL('searchAtParent'), selection)
                def searchall():
                    self.emit(SIGNAL('searchAll'), selection)
                def sann():
                    self.emit(SIGNAL('searchAnnotation'), selection)
                menu = QMenu(self)
                for name, func in [(_('Search in original revision'), sorig),
                                   (_('Search in working revision'), sctx),
                                   (_('Search in current annotation'), sann),
                                   (_('Search in history'), searchall)]:
                    action = menu.addAction(name)
                    action.wrapper = lambda f=func: f()
                    self.connect(action, SIGNAL('triggered()'), action.wrapper)
                return menu.exec_(point)

            def annorig():
                self.emit(SIGNAL('revSelected'), data)
            def editorig():
                self.emit(SIGNAL('editSelected'), data)
            menu = QMenu(self)
            for name, func in [(_('Annotate originating revision'), annorig),
                               (_('View originating revision'), editorig)]:
                action = menu.addAction(name)
                action.wrapper = lambda f=func: f()
                self.connect(action, SIGNAL('triggered()'), action.wrapper)
            for pfctx in fctx.parents():
                pdata = [pfctx.path(), pfctx.changectx().rev(), line]
                def annparent(data):
                    self.emit(SIGNAL('revSelected'), data)
                def editparent():
                    self.emit(SIGNAL('editSelected'), data)
                for name, func in [(_('Annotate parent revision %d') % pdata[1],
                                      annparent),
                                   (_('View parent revision %d') % pdata[1],
                                      editparent)]:
                    action = menu.addAction(name)
                    action.wrapper = lambda f=func,d=pdata: f(d)
                    self.connect(action, SIGNAL('triggered()'), action.wrapper)
            menu.exec_(point)

    def __init__(self, parent=None):
        super(AnnotateView, self).__init__(parent)

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        self.edit = self.TextArea(self)
        self.revarea = self.RevArea(self.edit)
        self.edit.updateRequest.connect(self.revarea.updateContents)
        self.edit.revisionHint.connect(lambda h: self.revisionHint.emit(h))
        self.connect(self.edit, SIGNAL('revSelected'),
                lambda data: self.emit(SIGNAL('revSelected'), data))
        self.connect(self.edit, SIGNAL('editSelected'),
                lambda data: self.emit(SIGNAL('editSelected'), data))
        self.connect(self.edit, SIGNAL('searchAtRev'),
                lambda data: self.emit(SIGNAL('searchAtRev'), data))
        self.connect(self.edit, SIGNAL('searchAtParent'),
                lambda pattern: self.emit(SIGNAL('searchAtParent'), pattern))
        self.connect(self.edit, SIGNAL('searchAll'),
                lambda pattern: self.emit(SIGNAL('searchAll'), pattern))
        self.connect(self.edit, SIGNAL('searchAnnotation'),
                lambda pattern: self.emit(SIGNAL('searchAnnotation'), pattern))

        hbox = QHBoxLayout(self)
        hbox.setSpacing(10)
        hbox.setMargin(0)
        hbox.addWidget(self.revarea)
        hbox.addWidget(self.edit)

        self.thread = None
        self.matches = []
        self.wrap = False

    def annotateFileAtRev(self, repo, ctx, wfile, line=None):
        if self.thread is not None:
            return
        fctx = ctx[wfile]
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
        lines = len(self.edit.revs) * 1.0
        if self.resumeline and lines > self.resumeline:
            cursor = self.edit.textCursor()
            cursor.movePosition(QTextCursor.NextBlock,
                                QTextCursor.MoveAnchor,
                                self.resumeline-1)
            cursor.select(QTextCursor.LineUnderCursor)
            self.edit.setTextCursor(cursor)
            sb = self.edit.verticalScrollBar()
            val = int(sb.maximum() * self.resumeline / lines)
            sb.setValue(val)
            self.edit.ensureCursorVisible()
        else:
            self.edit.verticalScrollBar().setValue(0)
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
            pos += len(text)
            if rev not in sums:
                author = hglib.username(fctx.user())
                author = hglib.tounicode(author)
                date = hglib.age(fctx.date())
                l = hglib.tounicode(fctx.description()).replace('\0', '').splitlines()
                summary = l and l[0] or ''
                if fctx.path() == self.annfile:
                    source = ''
                else:
                    source = '(%s)' % fctx.path()
                desc = '%s@%s%s:%s "%s"' % (author, rev, source, date, summary)
                sums[rev] = desc

        self.edit.summaries = sums
        self.edit.links = links
        self.edit.setPlainText(hglib.tounicode(''.join(lines)))
        self.edit.revs = revs
        width = max([len(str(r)) for r in revs]) * self.edit.charwidth + 3
        self.revarea.width = width
        self.revarea.setFixedWidth(width)

        for i, rev in enumerate(revs):
            ctx = self.repo[rev]
            rgb = self.cm.get_color(ctx, self.curdate)
            sel = QTextEdit.ExtraSelection()
            sel.bgcolor = QColor(rgb) # save a reference
            sel.format.setBackground(sel.bgcolor)
            sel.format.setProperty(QTextFormat.FullWidthSelection, True)
            sel.cursor = QTextCursor(self.edit.document())
            sel.cursor.setPosition(lpos[i])
            sel.cursor.clearSelection()
            sels.append(sel)
        self.colorsels = sels

        self.edit.setExtraSelections(self.colorsels)

    def nextMatch(self):
        if not self.matches:
            return
        if self.curmatch < len(self.matches)-1:
            self.curmatch += 1
        elif self.wrap:
            self.curmatch = 0
        self.edit.setTextCursor(self.matches[self.curmatch].cursor)

    def prevMatch(self):
        if not self.matches:
            return
        if self.curmatch > 0:
            self.curmatch -= 1
        elif self.wrap:
            self.curmatch = len(self.matches)-1
        self.edit.setTextCursor(self.matches[self.curmatch].cursor)

    def searchText(self, match, icase):
        matches = []
        color = QColor(Qt.yellow)
        flags = QTextDocument.FindFlags()
        if not icase:
            flags |= QTextDocument.FindCaseSensitively
        doc = self.edit.document()
        cursor = doc.find(match, 0, flags)
        while not cursor.isNull():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(color)
            selection.cursor = cursor
            matches.append(selection)
            cursor = doc.find(match, cursor)
        self.matches = matches
        self.curmatch = 0
        if matches:
            self.edit.setTextCursor(matches[0].cursor)
        self.edit.setExtraSelections(self.colorsels + self.matches)
        self.edit.setFocus()

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
        self.connect(av, SIGNAL('revSelected'), self.revSelected)
        self.connect(av, SIGNAL('editSelected'), self.editSelected)
        self.connect(av, SIGNAL('searchAtRev'), self.searchAtRev)
        self.connect(av, SIGNAL('searchAtParent'), self.searchAtParent)
        self.connect(av, SIGNAL('searchAll'), self.searchAll)
        self.connect(av, SIGNAL('searchAnnotation'), self.searchAnnotation)

        self.status = status
        self.searchwidget = opts.get('searchwidget')

        self.opts = opts
        line = opts.get('line')
        if line and isinstance(line, str):
            line = int(line)
        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
            ctx = repo[opts.get('rev') or '.']
            fctx = ctx[pats[0]] # just for validation
        except Exception, e:
            self.status.setText(hglib.tounicode(str(e)))
        av.annotateFileAtRev(repo, ctx, pats[0], line)
        self.setWindowTitle(_('Annotate %s@%d') % (pats[0], ctx.rev()))
        self.repo = repo

        s = QSettings()
        self.restoreGeometry(s.value('annotate/geom').toByteArray())
        wrap = s.value('annotate/wrap', False).toBool()
        wrapchk.setChecked(wrap)

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
        s = QSettings()
        s.setValue('annotate/geom', self.saveGeometry())
        s.setValue('annotate/wrap', self.wrapchk.isChecked())
        super(AnnotateDialog, self).accept()

    def reject(self):
        s = QSettings()
        s.setValue('annotate/geom', self.saveGeometry())
        s.setValue('annotate/wrap', self.wrapchk.isChecked())
        super(AnnotateDialog, self).reject()

def run(ui, *pats, **opts):
    pats = hglib.canonpaths(pats)
    return AnnotateDialog(*pats, **opts)

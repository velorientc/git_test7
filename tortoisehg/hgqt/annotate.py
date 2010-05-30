# annotate.py - File annotation widget
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import re

from mercurial import ui, hg, error, commands, cmdutil, util

from tortoisehg.hgqt import htmlui, visdiff, qtlib, htmllistview
from tortoisehg.util import paths, hglib, colormap
from tortoisehg.hgqt.i18n import _

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class AnnotateView(QFrame):
    loadBegin = pyqtSignal()
    loadComplete = pyqtSignal()
    errorMessage = pyqtSignal(QString)
    revSelected = pyqtSignal(int)
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
            if not line.isValid():
                return
            rev = self.revs[line.blockNumber()]
            if rev != self.lastrev:
                self.revisionHint.emit(self.summaries[rev])
                self.lastrev = rev

    def __init__(self, parent=None):
        super(AnnotateView, self).__init__(parent)

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        self.edit = self.TextArea(self)
        self.revarea = self.RevArea(self.edit)
        self.edit.updateRequest.connect(self.revarea.updateContents)
        self.edit.revisionHint.connect(lambda h: self.revisionHint.emit(h))

        hbox = QHBoxLayout(self)
        hbox.setSpacing(10)
        hbox.setMargin(0)
        hbox.addWidget(self.revarea)
        hbox.addWidget(self.edit)

        self.thread = None
        self.matches = []

    def annotateFileAtRev(self, repo, ctx, wfile):
        if self.thread is not None:
            return
        fctx = ctx[wfile]
        curdate = fctx.date()[0]
        basedate = repo.filectx(wfile, fileid=0).date()[0]
        agedays = (curdate - fctx.date()[0]) / (24 * 60 * 60)
        self.cm = colormap.AnnotateColorSaturation(agedays)
        self.curdate = curdate
        self.repo = repo
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
        return super(AnnotateView, self).keyPressEvent(event)

    def fillModel(self, data):
        revs, lines, lpos, sels = [], [], [], []
        sums = {}
        pos = 0
        for fctx, origline, text in data:
            rev = fctx.linkrev()
            lines.append(text)
            lpos.append(pos)
            revs.append(rev)
            pos += len(text)
            if rev in sums:
                continue

            author = hglib.username(fctx.user())
            date = hglib.age(fctx.date())
            l = fctx.description().replace(u'\0', '').splitlines()
            summary = l and l[0] or ''
            if fctx.path() == self.annfile:
                source = ''
            else:
                source = '(%s)' % fctx.path()
            desc = '%s@%s%s:%s "%s"' % (author, rev, source, date, summary)
            sums[rev] = desc

        self.edit.summaries = sums
        self.edit.setPlainText(''.join(lines))
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
        self.edit.verticalScrollBar().setValue(0)

    def nextMatch(self):
        if not self.matches:
            return
        if self.curmatch < len(self.matches)-1:
            self.curmatch += 1
        self.edit.setTextCursor(self.matches[self.curmatch].cursor)

    def prevMatch(self):
        if not self.matches:
            return
        if self.curmatch > 0:
            self.curmatch -= 1
        self.edit.setTextCursor(self.matches[self.curmatch].cursor)

    def searchText(self, regexp, icase):
        matches = []
        color = QColor(Qt.yellow)
        flags = QTextDocument.FindFlags()
        if not icase:
            flags |= QTextDocument.FindCaseSensitively
        doc = self.edit.document()
        cursor = doc.find(regexp, 0, flags)
        while not cursor.isNull():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(color)
            selection.cursor = cursor
            matches.append(selection)
            cursor = doc.find(regexp, cursor)
        self.matches = matches
        self.curmatch = 0
        if matches:
            self.edit.setTextCursor(matches[0].cursor)
        self.edit.setExtraSelections(self.colorsels + self.matches)

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
        super(AnnotateDialog,self).__init__(parent = None)

        mainvbox = QVBoxLayout()
        self.setLayout(mainvbox)

        hbox = QHBoxLayout()
        hbox.setMargin(0)
        lbl = QLabel(_('Regexp:'))
        le = QLineEdit()
        lbl.setBuddy(le)
        lbl.setToolTip(_('Regular expression search pattern'))
        bt = QPushButton(_('Search'))
        bt.setDefault(True)
        bt.clicked.connect(self.searchText)
        chk = QCheckBox(_('Ignore case'))
        hbox.addWidget(lbl)
        hbox.addWidget(le, 1)
        hbox.addWidget(chk)
        hbox.addWidget(bt)
        mainvbox.addLayout(hbox)
        self.le, self.chk = le, chk

        av = AnnotateView(self)
        mainvbox.addWidget(av)
        self.av = av

        status = QLabel()
        mainvbox.addWidget(status)
        av.revisionHint.connect(status.setText)
        self.status = status

        self.opts = opts
        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
            ctx = repo[opts.get('rev', '.')]
            fctx = ctx[pats[0]] # just for validation
        except Exception, e:
            self.status.setText(hglib.tounicode(str(e)))
        av.annotateFileAtRev(repo, ctx, pats[0])

        s = QSettings()
        self.restoreGeometry(s.value('annotate/geom').toByteArray())

    def searchText(self):
        pattern = hglib.fromunicode(self.le.text())
        if not pattern:
            return
        try:
            icase = self.chk.isChecked()
            regexp = re.compile(pattern, icase and re.I or 0)
        except Exception, inst:
            msg = _('grep: invalid match pattern: %s\n') % inst
            self.status.setText(hglib.tounicode(msg))
        self.av.searchText(QRegExp(pattern), icase)

    def wheelEvent(self, event):
        if self.childAt(event.pos()) != self.le:
            event.ignore()
            return
        if event.delta() > 0:
            self.av.prevMatch()
        elif event.delta() < 0:
            self.av.nextMatch()

    def accept(self):
        s = QSettings()
        s.setValue('annotate/geom', self.saveGeometry())
        super(AnnotateDialog, self).accept()

    def reject(self):
        s = QSettings()
        s.setValue('annotate/geom', self.saveGeometry())
        super(AnnotateDialog, self).reject()

def run(ui, *pats, **opts):
    return AnnotateDialog(*pats)

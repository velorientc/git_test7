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
from tortoisehg.util import paths, hglib
from tortoisehg.hgqt.i18n import _

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class AnnotateView(QFrame):
    loadBegin = pyqtSignal()
    loadComplete = pyqtSignal()
    errorMessage = pyqtSignal(QString)
    revSelected = pyqtSignal(int)

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
        def __init__(self, parent=None):
            QPlainTextEdit.__init__(self, parent)
            self.document().setDefaultStyleSheet(qtlib.thgstylesheet)
            self.setReadOnly(True)
            tm = QFontMetrics(self.font())
            self.charwidth = tm.width('9')
            self.charheight = tm.height()
            self.revs = []

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
                painter.drawText(rect, Qt.AlignRight, self.revs[line])
                block = block.next()
                top += self.blockBoundingGeometry(block).height()
                line += 1

    def __init__(self, parent=None):
        super(AnnotateView, self).__init__(parent)

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        self.edit = self.TextArea(self)
        self.revarea = self.RevArea(self.edit)
        self.edit.updateRequest.connect(self.revarea.updateContents)

        hbox = QHBoxLayout(self)
        hbox.setSpacing(10)
        hbox.setMargin(0)
        hbox.addWidget(self.revarea)
        hbox.addWidget(self.edit)

        self.thread = None

    def annotateFileAtRev(self, fctx):
        if self.thread is not None:
            return
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
        lines = []
        revs = []
        for fctx, origline, text in data:
            revs.append(str(fctx.linkrev()))
            lines.append(text)
        width = max([len(r) for r in revs]) * self.edit.charwidth + 3
        self.revarea.width = width
        self.revarea.setFixedWidth(width)
        self.edit.setPlainText(''.join(lines))
        self.edit.revs = revs

    def searchText(self, regexp, icase):
        extraSelections = []
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
            extraSelections.append(selection)
            cursor = doc.find(regexp, cursor)
        self.edit.setExtraSelections(extraSelections)

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
        self.status = status

        self.opts = opts
        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
            ctx = repo[opts.get('rev', '.')]
            fctx = ctx[pats[0]]
            av.annotateFileAtRev(fctx)
        except Exception, e:
            self.status.setText(hglib.tounicode(str(e)))

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

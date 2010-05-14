# grep.py - Working copy and history search
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import re

from mercurial import ui, hg, error

from tortoisehg.hgqt import htmlui, visdiff, qtlib
from tortoisehg.util import paths, hglib
from tortoisehg.util.i18n import _

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# This widget can be embedded in any application that would like to
# prove search features

# Technical Debt
#  uhm, do some searching
#  draggable matches from history
#  tortoisehg.editor with line number
#  smart visual diffs
#  context menu for matches
#  emit errors to parent's status bar
#  emit to parent's progress bar

class SearchWidget(QWidget):
    def __init__(self, root=None, parent=None):
        QWidget.__init__(self, parent)

        root = paths.find_root(root)
        repo = hg.repository(ui.ui(), path=root)
        assert(repo)

        layout = QVBoxLayout()
        layout.setMargin(0)
        self.setLayout(layout)

        hbox = QHBoxLayout()
        hbox.setMargin(0)
        lbl = QLabel(_('Regexp:'))
        le = QLineEdit()
        lbl.setBuddy(le)
        cb = QComboBox()
        cb.addItems([_('Working Copy'),
                     _('Parent Revision'),
                     _('All History')])
        chk = QCheckBox(_('Ignore case'))

        hbox.addWidget(lbl)
        hbox.addWidget(le, 1)
        hbox.addWidget(cb)
        hbox.addWidget(chk)
        layout.addLayout(hbox)

        tv = MatchTree(repo, self)
        tv.setItemsExpandable(False)
        tv.setRootIsDecorated(False)
        tm = MatchModel()
        tv.setModel(tm)
        tv.setColumnHidden(COL_REVISION, True)
        tv.setColumnHidden(COL_USER, True)
        layout.addWidget(tv)
        le.returnPressed.connect(self.searchActivated)
        self.repo = repo
        self.tv, self.le, self.cb, self.chk = tv, le, cb, chk

        if not parent:
            self.setWindowTitle(_('TortoiseHg Search'))
            self.resize(800, 500)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            return super(SearchWidget, self).keyPressEvent(event)

    def searchActivated(self):
        'User pressed [Return] in QLineEdit'
        model = self.tv.model()
        model.reset()
        regexp = hglib.fromunicode(self.le.text())
        icase = self.chk.isChecked()
        if not regexp:
            return
        self.le.selectAll()
        searchre = re.compile(regexp, icase and re.I or 0)

        mode = self.cb.currentIndex()
        if mode == 0:
            ctx = self.repo[None]
        elif mode == 1:
            ctx = self.repo['.']
        else:
            self.tv.setColumnHidden(COL_REVISION, False)
            self.tv.setColumnHidden(COL_USER, False)
            # Full blown 'hg grep' call
            # show revision, user columns
            # hg grep [-i] -afn regexp
            return

        self.tv.setColumnHidden(COL_REVISION, True)
        self.tv.setColumnHidden(COL_USER, True)
        hu = htmlui.htmlui()
        # searching len(ctx.manifest()) files
        for wfile in ctx:                     # walk manifest
            data = ctx[wfile].data()          # load file data
            if '\0' in data:
                continue
            for i, line in enumerate(data.splitlines()):
                pos = 0
                for m in searchre.finditer(line): # perform regexp
                    hu.write(line[pos:m.start()])
                    hu.write(line[m.start():m.end()], label='grep.match')
                    pos = m.end()
                if pos:
                    hu.write(line[pos:])
                    model.appendRow(wfile, i, None, None, hu.getdata()[0])

COL_PATH     = 0
COL_LINE     = 1
COL_REVISION = 2  # Hidden if ctx
COL_USER     = 3  # Hidden if ctx
COL_TEXT     = 4

class MatchTree(QTreeView):
    def __init__(self, repo, parent=None):
        QTreeView.__init__(self, parent)
        self.repo = repo
        self.setItemDelegate(HTMLDelegate(self))
        self.setSelectionMode(QTreeView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.connect(self, SIGNAL('customContextMenuRequested(const QPoint &)'),
                     self.customContextMenuRequested)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_D and event.modifiers() == Qt.ControlModifier:
            selfiles = []
            for index in self.selectedRows():
                # TODO: record rev, prune dups
                selfiles.append(self.model().getRow(index)[COL_PATH])
            visdiff.visualdiff(self.repo.ui, self.repo, selfiles, {})
        else:
            return super(MatchTree, self).keyPressEvent(event)

    def dragObject(self):
        urls = []
        for index in self.selectedRows():
            path = self.model().getRow(index)[COL_PATH]
            u = QUrl()
            u.setPath('file://' + os.path.join(self.repo.root, path))
            urls.append(u)
        if urls:
            d = QDrag(self)
            m = QMimeData()
            m.setUrls(urls)
            d.setMimeData(m)
            d.start(Qt.CopyAction)

    def mouseMoveEvent(self, event):
        self.dragObject()

    def customContextMenuRequested(self, point):
        selrows = []
        for index in self.selectedRows():
            path, line, rev, user, text = self.model().getRow(index)
            selrows.append((rev, path, line))
        point = self.mapToGlobal(point)
        #action = wctxactions.wctxactions(self, point, self.repo, selrows)
        #if action:
        #    self.emit(SIGNAL('menuAction()'))

    def selectedRows(self):
        return self.selectionModel().selectedRows()



class MatchModel(QAbstractTableModel):
    def __init__(self, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.rows = []
        self.headers = (_('File'), _('Line'), _('Revision'), _('User'),
                        _('Match Text'))

    def rowCount(self, parent):
        return len(self.rows)

    def columnCount(self, parent):
        return len(self.headers)

    def data(self, index, role):
        if not index.isValid():
            return QVariant()
        if role == Qt.DisplayRole:
            return QVariant(self.rows[index.row()][index.column()])
        return QVariant()

    def headerData(self, col, orientation, role):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return QVariant()
        else:
            return QVariant(self.headers[col])

    def flags(self, index):
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled
        return flags

    def sort(self, col, order):
        self.emit(SIGNAL("layoutAboutToBeChanged()"))
        self.rows.sort(lambda x, y: cmp(x[col], y[col]))
        if order == Qt.DescendingOrder:
            self.rows.reverse()
        self.emit(SIGNAL("layoutChanged()"))

    ## Custom methods

    def appendRow(self, *args):
        self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows))
        self.rows.append(args)
        self.endInsertRows()
        self.emit(SIGNAL("dataChanged()"))

    def reset(self):
        self.beginRemoveRows(QModelIndex(), 0, len(self.rows)-1)
        self.rows = []
        self.endRemoveRows()

class HTMLDelegate(QStyledItemDelegate):
    def __init__(self, parent=0):
        QStyledItemDelegate.__init__(self, parent)

    def paint(self, painter, option, index):
        if index.column() != COL_TEXT:
            return QStyledItemDelegate.paint(self, painter, option, index)
        text = index.model().data(index, Qt.DisplayRole).toString()
        palette = QApplication.palette()
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setDefaultStyleSheet(qtlib.thgstylesheet)
        painter.save()
        if option.state & QStyle.State_Selected:
            doc.setHtml('<font color=%s>%s</font>' % (
                palette.highlightedText().color().name(), text))
            bgcolor = palette.highlight().color()
            painter.fillRect(option.rect, bgcolor)
        else:
            doc.setHtml(text)
        painter.translate(option.rect.left(), option.rect.top())
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        text = index.model().data(index, Qt.DisplayRole).toString()
        doc = QTextDocument()
        doc.setDefaultStyleSheet(qtlib.thgstylesheet)
        doc.setDefaultFont(option.font)
        doc.setHtml(text)
        doc.setTextWidth(option.rect.width())
        return QSize(doc.idealWidth() + 5, doc.size().height())

def run(ui, *pats, **opts):
    return SearchWidget()

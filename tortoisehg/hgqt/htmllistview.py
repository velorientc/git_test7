# htmllistview.py - QListView based widget for selectable read-only HTML
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import sys

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.hgqt import qtlib

class HtmlListView(QListView):
    def __init__(self, model):
        QListView.__init__(self)
        self.setWindowTitle('HtmlListView')
        self.setModel(model)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setSelectionMode(QAbstractItemView.MultiSelection)
        self.resize(600, 200)
        self.setItemDelegate(HTMLDelegate(self))
        self._supportsSelection = QApplication.clipboard().supportsSelection()

    def selectionChanged(self, selected, deselected):
        QListView.selectionChanged(self, selected, deselected)
        self.copySelection( QClipboard.Selection )

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Cut) or event.matches(QKeySequence.Copy):
            self.copySelection(QClipboard.Clipboard)
        else:
            QListView.keyPressEvent(self, event)

    def copySelection(self, mode):
        if mode == QClipboard.Selection and not self._supportsSelection:
            return
        
        maxCol = 0
        sel = []
        for index in self.selectionModel().selectedIndexes():
            if maxCol < index.column():
                maxCol = index.column()
            sel.append((index.row(), index.column(), index))
        sel.sort()

        selectionText = ''
        for item in sel:
            data = self.model().data(item[2], Qt.DisplayRole).toString()
            data.replace('\n', '\\n')
            selectionText += data
            if item[1] == maxCol:
                selectionText += '\n'
            else:
                selectionText += '\t'

        QApplication.clipboard().setText(selectionText, mode)


class HtmlModel(QAbstractListModel):
    def __init__(self, strings):
        QAbstractTableModel.__init__(self)
        self.strings = strings

    def rowCount(self, parent):
        if not parent.isValid():
            return len(self.strings)
        return 0

    def data(self, index, role):
        if not index.isValid() or role != Qt.DisplayRole:
            return QVariant()
        if index.row() < 0 or index.row() >= len(self.strings):
            return QVariant()
        return QVariant(self.strings[index.row()])

    def headerData(self, col, orientation, role):
        if col != 0 or role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return QVariant()
        else:
            return QVariant("Multiline Rich-Text List")

    def flags(self, index):
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled


class HTMLDelegate(QStyledItemDelegate):
    def __init__(self, parent=0, cols=None):
        QStyledItemDelegate.__init__(self, parent)
        self.cols = cols

    def paint(self, painter, option, index):
        if self.cols and index.column() not in self.cols:
            return QStyledItemDelegate.paint(self, painter, option, index)
        text = index.model().data(index, Qt.DisplayRole).toString()

        # draw selection
        option = QStyleOptionViewItemV4(option)
        self.parent().style().drawControl(QStyle.CE_ItemViewItem, option, painter)

        # draw text
        doc = QTextDocument()
        painter.save()
        doc.setHtml(text)
        painter.setClipRect(option.rect)
        painter.translate(QPointF(
            option.rect.left(),
            option.rect.top() + (option.rect.height() - doc.size().height()) / 2))
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


if __name__ == "__main__":
    items = [ 'item0',
              '<pre style="color: green">just this text from this item</pre>',
              'what does a multi<br>line cell look like?',
              'what <b>does</b> a multi<br>line cell<br>look<br>like?',
              'item2' ]
    app = QApplication(sys.argv)
    tm = HtmlModel(items)
    tv1 = HtmlListView( tm )
    tv1.show()
    app.connect(app, SIGNAL('lastWindowClosed()'), app, SLOT('quit()'))
    sys.exit(app.exec_())

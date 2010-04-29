# htmllistview.py - QListView based widget for selectable read-only HTML
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import sys

from PyQt4.QtCore import *
from PyQt4.QtGui import *

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

class HtmlListView(QListView):
    def __init__(self, model):
        QListView.__init__(self)
        self.setWindowTitle('HtmlListView')
        self.setModel(model)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
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


class HTMLDelegate(QStyledItemDelegate):
    def __init__(self, parent=0):
        QItemDelegate.__init__(self, parent)

    def paint(self, painter, option, index):
        options = QStyleOptionViewItemV4(option)
        doc = QTextDocument()
        doc.setHtml(index.data().toString())

        painter.save()
        options.widget.style().drawControl(QStyle.CE_ItemViewItem,
                options, painter)
        painter.translate(options.rect.left(), options.rect.top())
        clip = QRectF(0, 0, options.rect.width(), options.rect.height())
        doc.drawContents(painter, clip)
        painter.restore()

    def sizeHint(self, option, index):
        options = QStyleOptionViewItemV4(option)
        doc = QTextDocument()
        doc.setHtml(index.data().toString())
        doc.setTextWidth(options.rect.width())
        return QSize(doc.idealWidth(), doc.size().height())


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

# docklog.py - Log dock widget for the TortoiseHg Workbench
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os
import time

from mercurial import ui

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, thread
from tortoisehg.util import hglib

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class LogDockWidget(QDockWidget):
    visibilityChanged = pyqtSignal(bool)

    def __init__(self, parent=None):
        super(LogDockWidget, self).__init__(parent)

        self.setFeatures(QDockWidget.DockWidgetClosable |
                         QDockWidget.DockWidgetMovable  |
                         QDockWidget.DockWidgetFloatable)
        self.setWindowTitle(_('Output Log'))

        mainframe = QFrame()
        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        mainframe.setLayout(vbox)
        self.setWidget(mainframe)

        self.logte = QPlainTextEdit()
        self.logte.setReadOnly(True)
        self.logte.setMaximumBlockCount(1024)
        self.logte.setWordWrapMode(QTextOption.NoWrap)
        vbox.addWidget(self.logte, 1)

    @pyqtSlot(thread.DataWrapper)
    def output(self, wrapper):
        msg, label = wrapper.data
        msg = hglib.tounicode(msg)
        msg = Qt.escape(msg)
        style = qtlib.geteffect(label)
        self.logMessage(msg, style)

    @pyqtSlot()
    def clear(self):
        self.logte.clear()

    def logMessage(self, msg, style=''):
        msg = msg.replace('\n', '<br/>')
        cursor = self.logte.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml('<font style="%s">%s</font>' % (style, msg))
        max = self.logte.verticalScrollBar().maximum()
        self.logte.verticalScrollBar().setSliderPosition(max)

    def showEvent(self, event):
        self.visibilityChanged.emit(True)

    def hideEvent(self, event):
        self.visibilityChanged.emit(False)

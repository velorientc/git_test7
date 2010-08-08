# docklog.py - Log / progress widget for the TortoiseHg Workbench
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os
import time

from mercurial import ui

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib
from tortoisehg.util import hglib

from PyQt4.QtCore import *
from PyQt4.QtGui import *

BEGINTAG = '\033' + str(time.time())
ENDTAG = '\032' + str(time.time())

class LogDockWidget(QDockWidget):
    visibilityChanged = pyqtSignal(bool)

    def __init__(self, parent=None):
        super(LogDockWidget, self).__init__(parent)

        self.setFeatures(QDockWidget.DockWidgetClosable |
                         QDockWidget.DockWidgetMovable  |
                         QDockWidget.DockWidgetFloatable)
        self.setWindowTitle(_('Progress Log'))

        mainframe = QFrame()
        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        mainframe.setLayout(vbox)
        self.setWidget(mainframe)

        self.logte = QPlainTextEdit()
        vbox.addWidget(self.logte, 1)

        hbox = QHBoxLayout()
        vbox.addLayout(hbox)
        self.phbox = hbox
        self.topics = {}

    def progress(self, topic, pos, item='', unit='', total=None):
        # topic is current operation
        # pos is the current numeric position (revision, bytes)
        # item is a non-numeric marker of current position (current file)
        # unit is a string label
        # total is the highest expected pos
        # All topics should be marked closed by setting pos to None
        if pos is None:
            if topic in self.topics:
                pm = self.topics[topic]
                self.phbox.removeWidget(pm)
                del self.topics[pm]
            return
        if topic not in self.topics:
            pm = ProgressMonitor(topic)
            self.topics[topic] = pm
            self.phbox.addWidget(pm)
        else:
            pm = self.topics[topic]
        if item:
            pm.status.setText(hglib.tounicode(item))
        elif unit:
            pm.status.setText(hglib.tounicode(unit))
        if total:
            pm.pbar.setValue(pos)
            pm.pbar.setMaximum(total)
        else:
            pm.pbar.unknown()

    def logMessage(self, msg):
        self.logte.appendPlainText(hglib.tounicode(msg))

    def logErrorMessage(self, msg):
        self.logte.appendPlainText(hglib.tounicode(msg))

    def showEvent(self, event):
        self.visibilityChanged.emit(True)

    def hideEvent(self, event):
        self.visibilityChanged.emit(False)


class ProgressMonitor(QWidget):
    def __init__(self, topic):
        super(ProgressMonitor, self).__init__()

        hbox = QHBoxLayout()
        hbox.setContentsMargins(*(0,)*4)
        self.setLayout(hbox)

        self.status = QLabel()
        hbox.addWidget(self.status, 0)

        self.topic = QLabel(topic)
        hbox.addWidget(self.topic, 0)

        self.pbar = QProgressBar()
        self.pbar.setTextVisible(False)
        self.pbar.setMinimum(0)
        hbox.addWidget(self.pbar)

        self.pbar.setMaximum(100)
        self.pbar.reset()
        self.status.setText('')

    def unknown(self):
        self.pbar.setMinimum(0)
        self.pbar.setMaximum(0)

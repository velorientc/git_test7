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
        self.logte.setReadOnly(True)
        self.logte.setCenterOnScroll(True)
        self.logte.setMaximumBlockCount(1024)
        self.logte.setWordWrapMode(QTextOption.NoWrap)
        vbox.addWidget(self.logte, 1)

        hbox = QVBoxLayout()
        hbox.addWidget(QLabel(_('Progress:')))
        vbox.addLayout(hbox)
        self.pvbox = hbox
        self.pbars = []
        self.topics = {}

    def progress(self, wrapper):
        # topic is current operation
        # pos is the current numeric position (revision, bytes)
        # item is a non-numeric marker of current position (current file)
        # unit is a string label
        # total is the highest expected pos
        # All topics should be marked closed by setting pos to None
        topic, item, pos, total, unit = wrapper.data
        if pos is None or (not pos and not total):
            if topic in self.topics:
                pm = self.topics[topic]
                pm.clear()
                del self.topics[topic]
                self.pvbox.update()
            return
        if topic not in self.topics:
            for pm in self.pbars:
                if pm.idle:
                    pm.reuse(topic)
                    break
            else:
                pm = ProgressMonitor(topic)
                self.pvbox.addWidget(pm)
                self.pbars.append(pm)
                self.pvbox.update()
            self.topics[topic] = pm
        else:
            pm = self.topics[topic]
        if total:
            fmt = '%s / %s ' % (str(pos), str(total))
            if unit:
                fmt += unit
            pm.status.setText(fmt)
            pm.setcounts(pos, total)
        else:
            if item:
                item = hglib.tounicode(item)[-30:]
            pm.status.setText('%s %s' % (str(pos), item))
            pm.unknown()

    def logMessage(self, msg, style=''):
        if msg.endsWith('\n'):
            msg.chop(1)
        msg = msg.replace('\n', '<br/>')
        self.logte.appendHtml('<font style="%s">%s</font>' % (style, msg))

    def clear(self):
        self.logte.clear()

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
        self.idle = False

        self.pbar = QProgressBar()
        self.pbar.setTextVisible(False)
        self.pbar.setMinimum(0)
        hbox.addWidget(self.pbar)

        self.topic = QLabel(topic)
        hbox.addWidget(self.topic, 0)

        self.status = QLabel()
        hbox.addWidget(self.status, 1)

        self.pbar.setMaximum(100)
        self.pbar.reset()
        self.status.setText('')

    def reuse(self, topic):
        self.topic.setText(topic)
        self.status.setText('')
        self.idle = False

    def clear(self):
        self.pbar.setMinimum(0)
        self.pbar.setMaximum(100)
        self.pbar.setValue(100)
        self.status.setText('')
        self.idle = True

    def setcounts(self, cur, max):
        self.pbar.setMaximum(max)
        self.pbar.setValue(cur)

    def unknown(self):
        self.pbar.setMinimum(0)
        self.pbar.setMaximum(0)

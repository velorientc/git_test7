# Copyright (c) 2009-2010 LOGILAB S.A. (Paris, FRANCE).
# http://www.logilab.fr/ -- mailto:contact@logilab.fr
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
"""
Qt4 QToolBar-based class for quick bars XXX
"""

from mercurial import util

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.qtlib import geticon

class QuickBar(QToolBar):
    def __init__(self, name, key, desc=None, parent=None):
        QToolBar.__init__(self, name, parent)
        self.setIconSize(QSize(16,16))
        self.setFloatable(False)
        self.setMovable(False)
        self.setAllowedAreas(Qt.BottomToolBarArea)
        self.createActions(key, desc)
        self.createContent()
        self.setVisible(False)

    def createActions(self, openkey, desc):
        openact = QAction(desc or 'Open', self)
        openact.setCheckable(True)
        openact.setChecked(False)
        openact.setShortcut(QKeySequence(openkey))
        openact.triggered.connect(self.show)

        self._actions = {'open': openact}

    def createContent(self):
        self.parent().addAction(self._actions['open'])

    def hide(self):
        self.setVisible(False)

    def cancel(self):
        self.hide()

class GotoQuickBar(QuickBar):
    gotoSignal = pyqtSignal(unicode)

    def __init__(self, parent):
        QuickBar.__init__(self, 'Goto', None, 'Goto', parent)

    def createActions(self, openkey, desc):
        QuickBar.createActions(self, openkey, desc)
        self._actions['go'] = QAction(geticon('go-jump'), _('Go'), self)
        self._actions['go'].triggered.connect(self.goto)

    def goto(self):
        self.gotoSignal.emit(unicode(self.entry.text()))

    def createContent(self):
        QuickBar.createContent(self)
        self.entry = QLineEdit(self)
        self.addWidget(self.entry)
        self.addAction(self._actions['go'])
        self.entry.returnPressed.connect(self._actions['go'].trigger)

    def setVisible(self, visible=True):
        QuickBar.setVisible(self, visible)
        if visible:
            self.entry.setFocus()
            self.entry.selectAll()

    def setCompletionKeys(self, keys):
        self.entry.setCompleter(QCompleter(keys))



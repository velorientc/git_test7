# sync.py - TortoiseHg's sync widget
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class SyncWidget(QWidget):

    def __init__(self, root, parent=None):
        QWidget.__init__(self, parent)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        la = QLabel("Sync widget %s for repo '%s' "
              "(widget is under construction)" % (id(self), root))
        layout.addWidget(la)

# -*- coding: utf-8 -*-
# Copyright (c) 2003-2010 LOGILAB S.A. (Paris, FRANCE).
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

from PyQt4.QtCore import *

from tortoisehg.hgqt import qtlib

class HgDialogMixin(object):
    """
    Mixin for QDialogs defined from a .ui file, wich automates the
    setup of the UI from the ui file, and the loading of user
    preferences.
    The main class must define a '_ui_file' class attribute.
    """
    def __init__(self, ui):
        self.load_config(ui)
        self.setupUi(self)

    def attachQuickBar(self, qbar):
        qbar.setParent(self)
        self.addToolBar(Qt.BottomToolBarArea, qbar)

    def load_config(self, ui):
        # TODO: connect to font changed signal
        self._font = qtlib.getfont('fontlog').font()
        self.rowheight = 8
        self.users, self.aliases = [], []

    def accept(self):
        self.close()
    def reject(self):
        self.close()
      

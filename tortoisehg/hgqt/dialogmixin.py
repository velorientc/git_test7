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

#
# make sur the Qt rc files are converted into python modules, then load them
# this must be done BEFORE other hgview qt4 modules are loaded.
import os
import os.path as osp
import sys

from PyQt4 import QtCore
from PyQt4 import QtGui, uic
connect = QtCore.QObject.connect
SIGNAL = QtCore.SIGNAL
Qt = QtCore.Qt

from tortoisehg.hgqt import should_rebuild
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

        _path = osp.dirname(__file__)
        uifile = osp.join(_path, self._uifile)
        pyfile = uifile.replace(".ui", "_ui.py")
        if should_rebuild(uifile, pyfile):
            os.system('pyuic4 %s -o %s' % (uifile, pyfile))
        try:
            modname = osp.splitext(osp.basename(uifile))[0] + "_ui"
            modname = "tortoisehg.hgqt.%s" % modname
            mod = __import__(modname, fromlist=['*'])
            classnames = [x for x in dir(mod) if x.startswith('Ui_')]
            if len(classnames) == 1:
                ui_class = getattr(mod, classnames[0])
            elif 'Ui_MainWindow' in classnames:
                ui_class = getattr(mod, 'Ui_MainWindow')
            else:
                raise ValueError("Can't determine which main class to use in %s" % modname)
        except ImportError:
            ui_class, base_class = uic.loadUiType(uifile)

        if ui_class not in self.__class__.__bases__:
            # hacking by adding the form class from ui file or pyuic4
            # generated module because we cannot use metaclass here,
            # due to "QObject" not being a subclass of "object"
            self.__class__.__bases__ = self.__class__.__bases__ + (ui_class,)
        self.setupUi(self)
        self._quickbars = []
        self.disab_shortcuts = []

    def attachQuickBar(self, qbar):
        qbar.setParent(self)
        self._quickbars.append(qbar)
        connect(qbar, SIGNAL('escShortcutDisabled(bool)'),
                self.setShortcutsEnabled)
        self.addToolBar(Qt.BottomToolBarArea, qbar)
        connect(qbar, SIGNAL('visible'),
                self.ensureOneQuickBar)

    def setShortcutsEnabled(self, enabled=True):
        for sh in self.disab_shortcuts:
            sh.setEnabled(enabled)
        
    def ensureOneQuickBar(self):
        tb = self.sender()
        for w in self._quickbars:
            if w is not tb:
                w.hide()
        
    def load_config(self, ui):
        # TODO: connect to font changed signal
        self._font = qtlib.getfont(ui, 'fontlog').font()
        self.rowheight = 8
        self.users, self.aliases = [], []
        self.max_file_size = 100000

    def accept(self):
        self.close()
    def reject(self):
        self.close()
      

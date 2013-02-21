# core.py - top-level menus and hooks
#
# Copyright 2013 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gc

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import extensions
from tortoisehg.hgqt import run, workbench

import dbgutil, infobar, widgets

class DebugMenuActions(dbgutil.BaseMenuActions):
    """Set up top-level debug menu"""

    def _setupMenu(self, menu):
        if self._workbench():
            m = menu.addMenu('&InfoBar')
            infobar.InfoBarMenuActions(m, parent=self)
            self._infoBarMenu = m
            menu.aboutToShow.connect(self._updateInfoBarMenu)

        m = menu.addMenu('&Widgets')
        widgets.WidgetsMenuActions(m, parent=self)

        menu.addSeparator()

        a = menu.addAction('Run Full &Garbage Collection')
        a.triggered.connect(self.runGc)

        a = menu.addAction('')  # placeholder to show gc status
        a.setEnabled(False)
        self._gcStatusAction = a

        a = menu.addAction('&Enable Garbage Collector')
        a.setCheckable(True)
        a.triggered.connect(self.setGcEnabled)
        self._gcEnabledAction = a
        menu.aboutToShow.connect(self._updateGcAction)

    @pyqtSlot()
    def _updateInfoBarMenu(self):
        self._infoBarMenu.setEnabled(bool(self._repoWidget()))

    @pyqtSlot()
    def runGc(self):
        found = gc.collect()
        self._information('GC Result', 'Found %d unreachable objects' % found)

    @property
    def _gcTimer(self):
        return run.qtrun._gc.timer

    def isGcEnabled(self):
        return self._gcTimer.isActive()

    @pyqtSlot(bool)
    def setGcEnabled(self, enabled):
        if enabled:
            self._gcTimer.start()
        else:
            self._gcTimer.stop()

    @pyqtSlot()
    def _updateGcAction(self):
        self._gcStatusAction.setText('  count = %s'
                                     % ', '.join(map(str, gc.get_count())))
        self._gcEnabledAction.setChecked(self.isGcEnabled())

def _workbenchrun(orig, ui, *pats, **opts):
    dlg = orig(ui, *pats, **opts)
    m = dlg.menuBar().addMenu('&Debug')
    DebugMenuActions(m, parent=dlg)
    return dlg

def extsetup(ui):
    extensions.wrapfunction(workbench, 'run', _workbenchrun)

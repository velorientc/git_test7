# infobar.py - menu to show/hide infobar manually
#
# Copyright 2013 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import extensions, util
from tortoisehg.hgqt import qtlib

import dbgutil

class InfoBarMenuActions(dbgutil.BaseMenuActions):
    """Set up debug menu for RepoWidget's InfoBar"""

    def _setupMenu(self, menu):
        menu.triggered.connect(self._setInfoBarByAction)
        clsnames = ['&StatusInfoBar', 'Command&ErrorInfoBar',
                    '&ConfirmInfoBar']
        for e in clsnames:
            menu.addAction(e).setData(e.replace('&', ''))

        menu.addSeparator()
        a = menu.addAction('Cl&ear')
        a.triggered.connect(self.clearInfoBar)
        a = menu.addAction('Setup &Trace')
        a.triggered.connect(self.setupInfoBarTrace)

    @pyqtSlot(QAction)
    def _setInfoBarByAction(self, action):
        clsname = str(action.data().toString())
        if not clsname:
            return
        self.setInfoBar(clsname)

    def setInfoBar(self, clsname):
        cls = getattr(qtlib, clsname)
        msg = self._getText('Set InfoBar', 'Message',
                            'The quick fox jumps over the lazy dog.')
        if msg:
            self._findRepoWidget().setInfoBar(cls, msg)

    @pyqtSlot()
    def clearInfoBar(self):
        self._findRepoWidget().clearInfoBar()

    @pyqtSlot()
    def setupInfoBarTrace(self):
        rw = self._findRepoWidget()
        def setInfoBarWithTrace(orig, cls, *args, **kwargs):
            w = orig(cls, *args, **kwargs)
            if not w:
                return
            self._log('InfoBar %r created\n' % w)
            if util.safehasattr(w, 'finished'):
                w.finished.connect(self._logInfoBarFinished)
            return w
        extensions.wrapfunction(rw, 'setInfoBar', setInfoBarWithTrace)

    @pyqtSlot(int)
    def _logInfoBarFinished(self, result):
        self._log('InfoBar %r finished with %d\n' % (self.sender(), result))

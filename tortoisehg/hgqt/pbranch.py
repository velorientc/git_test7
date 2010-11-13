# pbranch.py - TortoiseHg's patch branch widget
#
# Copyright 2010 Peer Sommerlund <peso@users.sourceforge.net>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os
import time

from mercurial import ui

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, cmdui
from tortoisehg.util import hglib

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class PatchBranchWidget(QWidget):
    '''
    A widget that show the patch graph and provide actions 
    for the pbranch extension
    '''
    visibilityChanged = pyqtSignal(bool)

    def __init__(self, repo, parent=None, logwidget=None):
        QWidget.__init__(self, parent)

        # Set up variables and connect signals

        self.repo = repo
        self.runner = cmdui.Runner(_('Patch Branch'), self, logwidget)
        self.runner.commandStarted.connect(repo.incrementBusyCount)
        self.runner.commandFinished.connect(self.commandFinished)

        repo.configChanged.connect(self.configChanged)
        repo.repositoryChanged.connect(self.repositoryChanged)
        repo.workingBranchChanged.connect(self.workingBranchChanged)

        # Build child widgets
        
        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        self.setLayout(vbox)

        # Toolbar
        self.toolBar_patchbranch = tb = QToolBar(_("Patch Branch Toolbar"), self)
        tb.setEnabled(True)
        tb.setObjectName("toolBar_patchbranch")
        tb.setFloatable(False)

        self.actionPMerge = a = QWidgetAction(self)
        a.setIcon(QIcon(QPixmap(":/icons/merge.svg")))
        a.setToolTip(_('Merge all pending dependencies'))
        tb.addAction(self.actionPMerge)
        #self.actionPMerge.triggered.connect(self.pmerge_clicked)

        self.actionBackport = a = QWidgetAction(self)
        a.setIcon(QIcon(QPixmap(":/icons/back.svg")))
        a.setToolTip(_('Backout current patch branch'))
        tb.addAction(self.actionBackport)
        #self.actionBackport.triggered.connect(self.pbackout_clicked)

        self.actionReapply = a = QWidgetAction(self)
        a.setIcon(QIcon(QPixmap(":/icons/forward.svg")))
        a.setToolTip(_('Backport part of a changeset to a dependency'))
        tb.addAction(self.actionReapply)
        #self.actionReapply.triggered.connect(self.reapply_clicked)

       	self.actionPNew = a = QWidgetAction(self)
        a.setIcon(QIcon(QPixmap(":/icons/fileadd.ico"))) #STOCK_NEW
        a.setToolTip(_('Start a new patch branch'))
        tb.addAction(self.actionPNew)
        #self.actionPNew.triggered.connect(self.pbackout_clicked)

        self.actionEditPGraph = a = QWidgetAction(self)
        a.setIcon(QIcon(QPixmap(":/icons/log.svg"))) #STOCK_EDIT
        a.setToolTip(_('Edit patch dependency graph'))
        tb.addAction(self.actionEditPGraph)
        #self.actionEditPGraph.triggered.connect(self.pbackout_clicked)

        vbox.addWidget(self.toolBar_patchbranch, 1)
        
        # Patch list
        self.logte = QPlainTextEdit()
        self.logte.setReadOnly(True)
        self.logte.setCenterOnScroll(True)
        self.logte.setMaximumBlockCount(1024)
        self.logte.setWordWrapMode(QTextOption.NoWrap)
        vbox.addWidget(self.logte, 1)
        
        # Command output
        self.logte = QPlainTextEdit()
        self.logte.setReadOnly(True)
        self.logte.setCenterOnScroll(True)
        self.logte.setMaximumBlockCount(1024)
        self.logte.setWordWrapMode(QTextOption.NoWrap)
        vbox.addWidget(self.logte, 1)
        
    # Signal handlers
    
    def commandFinished(self, wrapper):
        pass
    def configChanged(self, wrapper):
        pass
    def repositoryChanged(self):
        pass
    def workingBranchChanged(self, wrapper):
        pass


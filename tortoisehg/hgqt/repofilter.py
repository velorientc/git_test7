# repofilter.py - TortoiseHg toolbar for filtering changesets
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
# Copyright (C) 2010 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class RepoFilterBar(QToolBar):
    """Toolbar for RepoWidget to filter changesets"""

    branchChanged = pyqtSignal(unicode, bool)
    """Emitted (branch, allparents) when branch selection changed"""

    def __init__(self, repo, parent=None):
        super(RepoFilterBar, self).__init__(parent)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self._repo = repo

        self.addWidget(QLineEdit(text='### placeholder for revsets ###',
                                 enabled=False))

        self._initbranchfilter()
        self.refresh()

    def _initbranchfilter(self):
        self.branchLabel = QToolButton()
        self.branchLabel.setText("Branch")
        self.branchLabel.setStatusTip("Display graph the named branch only")
        self.branchLabel.setPopupMode(QToolButton.InstantPopup)
        self.branch_menu = QMenu()
        cbranch_action = self.branch_menu.addAction("Display closed branches")
        cbranch_action.setCheckable(True)
        self.cbranch_action = cbranch_action
        allpar_action = self.branch_menu.addAction("Include all ancestors")
        allpar_action.setCheckable(True)
        self.allpar_action = allpar_action
        self.branchLabel.setMenu(self.branch_menu)
        self.branchCombo = QComboBox()
        self.branchCombo.activated.connect(self._emitBranchChanged)
        cbranch_action.toggled.connect(self.refresh)
        allpar_action.toggled.connect(self._emitBranchChanged)

        self.branchLabelAction = self.addWidget(self.branchLabel)
        self.branchComboAction = self.addWidget(self.branchCombo)

    def _updatebranchfilter(self):
        """Update the list of branches"""
        curbranch = self.branch()

        allbranches = sorted(self._repo.branchtags().items())

        openbr = []
        for branch, brnode in allbranches:
            openbr.extend(self._repo.branchheads(branch, closed=False))
        clbranches = [br for br, node in allbranches if node not in openbr]
        branches = [br for br, node in allbranches if node in openbr]
        if self.cbranch_action.isChecked():
            branches = branches + clbranches

        if len(branches) == 1:
            self.branchLabelAction.setEnabled(False)
            self.branchComboAction.setEnabled(False)
            self.branchCombo.clear()
        else:
            branches = [''] + branches
            self.branchesmodel = QStringListModel(branches)
            self.branchCombo.setModel(self.branchesmodel)
            self.branchLabelAction.setEnabled(True)
            self.branchComboAction.setEnabled(True)

        self.setBranch(curbranch)

    @pyqtSlot(unicode)
    def setBranch(self, branch):
        """Change the current branch by name [unicode]"""
        self.branchCombo.setCurrentIndex(self.branchCombo.findText(branch))

    def branch(self):
        """Return the current branch name [unicode]"""
        return unicode(self.branchCombo.currentText())

    @pyqtSlot()
    def _emitBranchChanged(self):
        self.branchChanged.emit(self.branch(),
                                self.allpar_action.isChecked())

    @pyqtSlot()
    def refresh(self):
        self._updatebranchfilter()

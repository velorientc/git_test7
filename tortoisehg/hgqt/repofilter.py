# repofilter.py - TortoiseHg toolbar for filtering changesets
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
# Copyright (C) 2010 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.hgqt.i18n import _

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
        self.branchLabel = QToolButton(
            text=_('Branch'), popupMode=QToolButton.InstantPopup,
            statusTip=_('Display graph the named branch only'))
        self.branch_menu = QMenu(self.branchLabel)
        self.cbranch_action = self.branch_menu.addAction(
            _('Display closed branches'), self.refresh)
        self.cbranch_action.setCheckable(True)
        self.allpar_action = self.branch_menu.addAction(
            _('Include all ancestors'), self._emitBranchChanged)
        self.allpar_action.setCheckable(True)
        self.branchLabel.setMenu(self.branch_menu)

        self.branchCombo = QComboBox()
        self.branchCombo.currentIndexChanged.connect(self._emitBranchChanged)

        self.addWidget(self.branchLabel)
        self.addWidget(self.branchCombo)

    def _updatebranchfilter(self):
        """Update the list of branches"""
        curbranch = self.branch()

        def iterbranches(all=False):
            allbranches = self._repo.branchtags()
            if all:
                return sorted(allbranches.keys())

            openbrnodes = []
            for br in allbranches.iterkeys():
                openbrnodes.extend(self._repo.branchheads(br, closed=False))
            return sorted(br for br, n in allbranches.iteritems()
                          if n in openbrnodes)

        branches = list(iterbranches(all=self.cbranch_action.isChecked()))
        self.branchCombo.clear()
        self.branchCombo.addItems([''] + branches)
        self.branchLabel.setEnabled(len(branches) > 1)
        self.branchCombo.setEnabled(len(branches) > 1)

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

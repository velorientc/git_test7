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
from tortoisehg.hgqt import revset, qtlib

class RepoFilterBar(QToolBar):
    """Toolbar for RepoWidget to filter changesets"""

    revisionSet = pyqtSignal(object)
    clearSet = pyqtSignal()
    filterToggled = pyqtSignal(bool)

    showMessage = pyqtSignal(QString)
    progress = pyqtSignal(QString, object, QString, QString, object)

    branchChanged = pyqtSignal(unicode, bool)
    """Emitted (branch, allparents) when branch selection changed"""

    def __init__(self, repo, parent):
        super(RepoFilterBar, self).__init__(parent)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.setIconSize(QSize(16,16))
        self.setFloatable(False)
        self.setMovable(False)
        self._repo = repo

        self.entrydlg = revset.RevisionSetQuery(repo, self)
        self.entrydlg.progress.connect(self.progress)
        self.entrydlg.showMessage.connect(self.showMessage)
        self.entrydlg.queryIssued.connect(self.dialogQuery)
        self.entrydlg.hide()

        self.clear = QPushButton(_('clear'))
        self.addWidget(self.clear)

        self.editor = QPushButton(_('editor'))
        self.editor.clicked.connect(self.openEditor)
        self.addWidget(self.editor)

        s = QSettings()
        self.entrydlg.restoreGeometry(s.value('revset/geom').toByteArray())
        self.revsethist = list(s.value('revset-queries').toStringList())
        self.revsetle = le = QLineEdit()
        le.setCompleter(QCompleter(self.revsethist))
        le.returnPressed.connect(self.returnPressed)
        if hasattr(self.revsetle, 'setPlaceholderText'): # Qt >= 4.7 
            self.revsetle.setPlaceholderText('### revision set query ###')
        self.addWidget(le)

        self.clear.clicked.connect(le.clear)
        self.clear.clicked.connect(self.clearSet)

        self.filtercb = f = QCheckBox(_('filter'))
        f.setChecked(s.value('revset-filter').toBool())
        f.toggled.connect(self.filterToggled)
        self.addWidget(f)

        self.store = store = QPushButton(_('store'))
        store.clicked.connect(self.saveQuery)
        le.textChanged.connect(lambda t: store.setEnabled(False))
        store.setEnabled(False)
        self.addWidget(store)

        self._initbranchfilter()
        self.refresh()

    def showEvent(self, event):
        self.revsetle.setFocus()

    def openEditor(self):
        query = self.revsetle.text().simplified()
        self.entrydlg.entry.setText(query)
        self.entrydlg.entry.setCursorPosition(0, len(query))
        self.entrydlg.entry.setFocus()
        self.entrydlg.setShown(True)

    def dialogQuery(self, query, revset):
        self.revsetle.setText(query)
        self.store.setEnabled(True)
        self.revisionSet.emit(revset)

    def returnPressed(self):
        'Return pressed on revset line entry, forward to dialog'
        query = self.revsetle.text().simplified()
        if query:
            self.entrydlg.entry.setText(query)
            self.entrydlg.runQuery()

    def saveQuery(self):
        query = self.revsetle.text()
        if query in self.revsethist:
            self.revsethist.remove(query)
        self.revsethist.insert(0, query)
        self.revsetle.setCompleter(QCompleter(self.revsethist))
        self.store.setEnabled(False)
        self.showMessage.emit(_('Revision set query saved'))

    def storeConfigs(self, s):
        s.setValue('revset/geom', self.entrydlg.saveGeometry())
        s.setValue('revset-queries', self.revsethist)
        s.setValue('revset-filter', self.filtercb.isChecked())

    def _initbranchfilter(self):
        self._branchLabel = QToolButton(
            text=_('Branch'), popupMode=QToolButton.InstantPopup,
            statusTip=_('Display graph the named branch only'))
        self._branchMenu = QMenu(self._branchLabel)
        self._cbranchAction = self._branchMenu.addAction(
            _('Display closed branches'), self.refresh)
        self._cbranchAction.setCheckable(True)
        self._allparAction = self._branchMenu.addAction(
            _('Include all ancestors'), self._emitBranchChanged)
        self._allparAction.setCheckable(True)
        self._branchLabel.setMenu(self._branchMenu)

        self._branchCombo = QComboBox()
        self._branchCombo.currentIndexChanged.connect(self._emitBranchChanged)
        self._branchReloading = False

        self.addWidget(self._branchLabel)
        self.addWidget(self._branchCombo)

    def _updatebranchfilter(self):
        """Update the list of branches"""
        curbranch = self.branch()

        if self._cbranchAction.isChecked():
            branches = sorted(self._repo.branchtags().keys())
        else:
            branches = self._repo.namedbranches

        self._branchReloading = True
        self._branchCombo.clear()
        self._branchCombo.addItems([''] + branches)
        self._branchLabel.setEnabled(len(branches) > 1)
        self._branchCombo.setEnabled(len(branches) > 1)
        self._branchReloading = False

        self.setBranch(curbranch)

    @pyqtSlot(unicode)
    def setBranch(self, branch):
        """Change the current branch by name [unicode]"""
        self._branchCombo.setCurrentIndex(self._branchCombo.findText(branch))

    def branch(self):
        """Return the current branch name [unicode]"""
        return unicode(self._branchCombo.currentText())

    @pyqtSlot()
    def _emitBranchChanged(self):
        if not self._branchReloading:
            self.branchChanged.emit(self.branch(),
                                    self._allparAction.isChecked())

    @pyqtSlot()
    def refresh(self):
        self._updatebranchfilter()

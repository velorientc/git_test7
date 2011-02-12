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

_permanent_queries = ('head()', 'merge()', 'tagged()', 'file(".hgsubstate")')

class RepoFilterBar(QToolBar):
    """Toolbar for RepoWidget to filter changesets"""

    setRevisionSet = pyqtSignal(object)
    clearRevisionSet = pyqtSignal()
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
        self.filterEnabled = True

        self.entrydlg = revset.RevisionSetQuery(repo, self)
        self.entrydlg.progress.connect(self.progress)
        self.entrydlg.showMessage.connect(self.showMessage)
        self.entrydlg.queryIssued.connect(self.queryIssued)
        self.entrydlg.hide()

        self.revsetcombo = combo = QComboBox()
        combo.setEditable(True)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        le = combo.lineEdit()
        le.returnPressed.connect(self.returnPressed)
        le.selectionChanged.connect(self.selectionChanged)
        if hasattr(le, 'setPlaceholderText'): # Qt >= 4.7 
            le.setPlaceholderText(_('### revision set query ###'))
        combo.activated.connect(self.comboSelectionActivated)
        self.revsetle = le

        self.clearBtn = QToolButton(self)
        self.clearBtn.setIcon(qtlib.geticon('filedelete'))
        self.clearBtn.setToolTip(_('Clear current query and query text'))
        self.clearBtn.clicked.connect(le.clear)
        self.clearBtn.clicked.connect(self.clearRevisionSet)
        self.addWidget(self.clearBtn)
        self.addWidget(combo)

        self.searchBtn = QToolButton(self)
        self.searchBtn.setIcon(qtlib.geticon('find'))
        self.searchBtn.setToolTip(_('Trigger revision set query'))
        self.searchBtn.clicked.connect(self.returnPressed)
        self.addWidget(self.searchBtn)

        self.editorBtn = QToolButton()
        self.editorBtn.setText('...')
        self.editorBtn.setToolTip(_('Open advanced query editor'))
        self.editorBtn.clicked.connect(self.openEditor)
        self.addWidget(self.editorBtn)

        icon = QIcon()
        icon.addPixmap(QApplication.style().standardPixmap(QStyle.SP_TrashIcon))
        self.deleteBtn = QToolButton()
        self.deleteBtn.setIcon(icon)
        self.deleteBtn.setToolTip(_('Delete selected query from history'))
        self.deleteBtn.clicked.connect(self.deleteFromHistory)
        self.deleteBtn.setEnabled(False)
        self.addWidget(self.deleteBtn)
        self.addSeparator()

        self.filtercb = f = QCheckBox(_('filter'))
        f.toggled.connect(self.filterToggled)
        f.setToolTip(_('Toggle filtering of non-matched changesets'))
        self.addWidget(f)
        self.addSeparator()

        self._initbranchfilter()
        self.refresh()

    def setEnableFilter(self, enabled):
        'Enable/disable the changing of the current filter'
        self.revsetcombo.setEnabled(enabled)
        self.clearBtn.setEnabled(enabled)
        self.searchBtn.setEnabled(enabled)
        self.editorBtn.setEnabled(enabled)
        self.deleteBtn.setEnabled(enabled)
        self._branchCombo.setEnabled(enabled)
        self._branchLabel.setEnabled(enabled)
        self.filterEnabled = enabled

    def selectionChanged(self):
        selection = self.revsetcombo.lineEdit().selectedText()
        self.deleteBtn.setEnabled(selection in self.revsethist)

    def deleteFromHistory(self):
        selection = self.revsetcombo.lineEdit().selectedText()
        if selection not in self.revsethist:
            return
        self.revsethist.remove(selection)
        full = self.revsethist + list(_permanent_queries)
        self.revsetcombo.clear()
        self.revsetcombo.addItems(full)
        self.revsetcombo.setCurrentIndex(-1)

    def showEvent(self, event):
        self.revsetcombo.lineEdit().setFocus()

    def openEditor(self):
        query = self.revsetcombo.lineEdit().text().simplified()
        self.entrydlg.entry.setText(query)
        self.entrydlg.entry.setCursorPosition(0, len(query))
        self.entrydlg.entry.setFocus()
        self.entrydlg.setShown(True)

    @pyqtSlot(int)
    def comboSelectionActivated(self, row):
        text = self.revsetcombo.itemText(row)
        self.revsetcombo.lineEdit().setText(text)
        self.entrydlg.entry.setText(text)
        self.entrydlg.runQuery()

    def queryIssued(self, query, revset):
        self.revsetcombo.lineEdit().setText(query)
        if revset:
            self.setRevisionSet.emit(revset)
        else:
            self.clearRevisionSet.emit()
        self.saveQuery()
        self.revsetcombo.lineEdit().selectAll()

    def returnPressed(self):
        'Return pressed on revset line entry, forward to dialog'
        query = self.revsetcombo.lineEdit().text().simplified()
        if query:
            self.entrydlg.entry.setText(query)
            self.entrydlg.runQuery()
        else:
            self.clearRevisionSet.emit()

    def saveQuery(self):
        query = self.revsetcombo.lineEdit().text()
        if query in self.revsethist:
            self.revsethist.remove(query)
        if query not in _permanent_queries:
            self.revsethist.insert(0, query)
            self.revsethist = self.revsethist[:20]
        full = self.revsethist + list(_permanent_queries)
        self.revsetcombo.clear()
        self.revsetcombo.addItems(full)
        self.revsetcombo.lineEdit().setText(query)

    def loadSettings(self, s):
        self.entrydlg.restoreGeometry(s.value('revset/geom').toByteArray())
        self.revsethist = list(s.value('revset-queries').toStringList())
        self.filtercb.setChecked(s.value('revset-filter', True).toBool())
        full = self.revsethist + list(_permanent_queries)
        self.revsetcombo.clear()
        self.revsetcombo.addItems(full)
        self.revsetcombo.setCurrentIndex(-1)

    def saveSettings(self, s):
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
        self._branchCombo.addItem('')
        for branch in branches:
            self._branchCombo.addItem(branch)
        self._branchLabel.setEnabled(self.filterEnabled and len(branches) > 1)
        self._branchCombo.setEnabled(self.filterEnabled and len(branches) > 1)
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

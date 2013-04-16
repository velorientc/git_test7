# repofilter.py - TortoiseHg toolbar for filtering changesets
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
# Copyright (C) 2010 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

import os
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import error, revset as hgrevset
from mercurial import repoview

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import revset, qtlib

_permanent_queries = ('head()', 'merge()',
                      'tagged()', 'bookmark()',
                      'file(".hgsubstate") or file(".hgsub")')

def _firstword(query):
    try:
        for token, value, _pos in hgrevset.tokenize(hglib.fromunicode(query)):
            if token == 'symbol' or token == 'string':
                return value  # localstr
    except error.ParseError:
        pass

def _querytype(repo, query):
    """
    >>> repo = set('0 1 2 3 . stable'.split())
    >>> _querytype(repo, u'') is None
    True
    >>> _querytype(repo, u'quick fox')
    'keyword'
    >>> _querytype(repo, u'0')
    'revset'
    >>> _querytype(repo, u'stable')
    'revset'
    >>> _querytype(repo, u'0::2')  # symbol
    'revset'
    >>> _querytype(repo, u'::"stable"')  # string
    'revset'
    >>> _querytype(repo, u'"')  # unterminated string
    'keyword'
    >>> _querytype(repo, u'tagged()')
    'revset'
    """
    if not query:
        return
    if '(' in query:
        return 'revset'
    changeid = _firstword(query)
    if not changeid:
        return 'keyword'
    try:
        if changeid in repo:
            return 'revset'
    except error.LookupError:  # ambiguous changeid
        pass
    return 'keyword'

class RepoFilterBar(QToolBar):
    """Toolbar for RepoWidget to filter changesets"""

    setRevisionSet = pyqtSignal(object)
    clearRevisionSet = pyqtSignal()
    filterToggled = pyqtSignal(bool)

    showMessage = pyqtSignal(QString)
    progress = pyqtSignal(QString, object, QString, QString, object)

    branchChanged = pyqtSignal(unicode, bool)
    """Emitted (branch, allparents) when branch selection changed"""

    showHiddenChanged = pyqtSignal(bool)

    _allBranchesLabel = u'\u2605 ' + _('Show all') + u' \u2605'

    def __init__(self, repo, parent=None):
        super(RepoFilterBar, self).__init__(parent)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.setIconSize(QSize(16,16))
        self.setFloatable(False)
        self.setMovable(False)
        self._repo = repo
        self._permanent_queries = list(_permanent_queries)
        username = repo.ui.config('ui', 'username')
        if username:
            self._permanent_queries.insert(0,
                hgrevset.formatspec('author(%s)', os.path.expandvars(username)))
        self.filterEnabled = True

        #Check if the font contains the glyph needed by the branch combo
        if not QFontMetrics(self.font()).inFont(QString(u'\u2605').at(0)):
            self._allBranchesLabel = u'*** %s ***' % _('Show all')

        self.entrydlg = revset.RevisionSetQuery(repo, self)
        self.entrydlg.progress.connect(self.progress)
        self.entrydlg.showMessage.connect(self.showMessage)
        self.entrydlg.queryIssued.connect(self.queryIssued)
        self.entrydlg.hide()

        self.revsetcombo = combo = QComboBox()
        combo.setEditable(True)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.setMinimumContentsLength(10)
        qtlib.allowCaseChangingInput(combo)
        le = combo.lineEdit()
        le.returnPressed.connect(self.runQuery)
        le.selectionChanged.connect(self.selectionChanged)
        if hasattr(le, 'setPlaceholderText'): # Qt >= 4.7
            le.setPlaceholderText(_('### revision set query ###'))
        combo.activated.connect(self.runQuery)

        self._revsettypelabel = QLabel(le)
        self._revsettypetimer = QTimer(self, interval=200, singleShot=True)
        self._revsettypetimer.timeout.connect(self._updateQueryType)
        combo.editTextChanged.connect(self._revsettypetimer.start)
        self._updateQueryType()
        le.installEventFilter(self)

        self.clearBtn = QToolButton(self)
        self.clearBtn.setIcon(qtlib.geticon('filedelete'))
        self.clearBtn.setToolTip(_('Clear current query and query text'))
        self.clearBtn.clicked.connect(self.onClearButtonClicked)
        self.addWidget(self.clearBtn)
        self.addWidget(qtlib.Spacer(2, 2))
        self.addWidget(combo)
        self.addWidget(qtlib.Spacer(2, 2))

        self.searchBtn = QToolButton(self)
        self.searchBtn.setIcon(qtlib.geticon('view-filter'))
        self.searchBtn.setToolTip(_('Trigger revision set query'))
        self.searchBtn.clicked.connect(self.runQuery)
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

        self.showHiddenBtn = QToolButton()
        self.showHiddenBtn.setIcon(qtlib.geticon('view-hidden'))
        self.showHiddenBtn.setCheckable(True)
        self.showHiddenBtn.setToolTip(_('Show/Hide hidden changesets'))
        self.showHiddenBtn.clicked.connect(self.showHiddenChanged)
        self.addWidget(self.showHiddenBtn)
        self.addSeparator()

        self._initBranchFilter()
        self.refresh()

    def onClearButtonClicked(self):
        if self.revsetcombo.currentText():
            self.revsetcombo.clearEditText()
        else:
            self.hide()
        self.clearRevisionSet.emit()

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
        self.showHiddenBtn.setEnabled(enabled)

    def selectionChanged(self):
        selection = self.revsetcombo.lineEdit().selectedText()
        self.deleteBtn.setEnabled(selection in self.revsethist)

    def deleteFromHistory(self):
        selection = self.revsetcombo.lineEdit().selectedText()
        if selection not in self.revsethist:
            return
        self.revsethist.remove(selection)
        full = self.revsethist + self._permanent_queries
        self.revsetcombo.clear()
        self.revsetcombo.addItems(full)
        self.revsetcombo.setCurrentIndex(-1)

    def showEvent(self, event):
        super(RepoFilterBar, self).showEvent(event)
        self.revsetcombo.setFocus()

    def eventFilter(self, watched, event):
        if watched is self.revsetcombo.lineEdit():
            if event.type() == QEvent.Resize:
                self._updateQueryTypeGeometry()
            return False
        return super(RepoFilterBar, self).eventFilter(watched, event)

    def openEditor(self):
        query = self._prepareQuery()
        self.entrydlg.entry.setText(query)
        self.entrydlg.entry.setCursorPosition(0, len(query))
        self.entrydlg.entry.setFocus()
        self.entrydlg.setShown(True)

    def queryIssued(self, query, revset):
        if self._prepareQuery() != unicode(query):  # keep keyword query as-is
            self.revsetcombo.setEditText(query)
        if revset:
            self.setRevisionSet.emit(revset)
        else:
            self.clearRevisionSet.emit()
        self.saveQuery()
        self.revsetcombo.lineEdit().selectAll()

    def _prepareQuery(self):
        query = unicode(self.revsetcombo.currentText()).strip()
        if _querytype(self._repo, query) == 'keyword':
            s = hglib.fromunicode(query)
            return hglib.tounicode(hgrevset.formatspec('keyword(%s)', s))
        else:
            return query

    @pyqtSlot()
    def _updateQueryType(self):
        query = unicode(self.revsetcombo.currentText()).strip()
        qtype = _querytype(self._repo, query)
        if not qtype:
            self._revsettypelabel.hide()
            self._updateQueryTypeGeometry()
            return

        name, bordercolor, bgcolor = {
            'keyword': (_('Keyword Search'), '#cccccc', '#eeeeee'),
            'revset':  (_('Revision Set'),   '#f6dd82', '#fcf1ca'),
            }[qtype]
        label = self._revsettypelabel
        label.setText(name)
        label.setStyleSheet('border: 1px solid %s; background-color: %s; '
                            'color: black;' % (bordercolor, bgcolor))
        label.show()
        self._updateQueryTypeGeometry()

    def _updateQueryTypeGeometry(self):
        le = self.revsetcombo.lineEdit()
        label = self._revsettypelabel
        # show label in right corner
        w = label.minimumSizeHint().width()
        label.setGeometry(le.width() - w - 1, 1, w, le.height() - 2)
        # right margin for label
        margins = list(le.getContentsMargins())
        if label.isHidden():
            margins[2] = 0
        else:
            margins[2] = w + 1
        le.setContentsMargins(*margins)

    def setQuery(self, query):
        self.revsetcombo.setEditText(query)

    @pyqtSlot()
    def runQuery(self):
        'Run the current revset query or request to clear the previous result'
        query = self._prepareQuery()
        if query:
            self.entrydlg.entry.setText(query)
            self.entrydlg.runQuery()
        else:
            self.clearRevisionSet.emit()

    def saveQuery(self):
        query = self.revsetcombo.currentText()
        if query in self.revsethist:
            self.revsethist.remove(query)
        if query not in self._permanent_queries:
            self.revsethist.insert(0, query)
            self.revsethist = self.revsethist[:20]
        full = self.revsethist + self._permanent_queries
        self.revsetcombo.clear()
        self.revsetcombo.addItems(full)
        self.revsetcombo.setCurrentIndex(self.revsetcombo.findText(query))

    def loadSettings(self, s):
        repoid = str(self._repo[0])
        s.beginGroup('revset/' + repoid)
        self.entrydlg.restoreGeometry(s.value('geom').toByteArray())
        self.revsethist = list(s.value('queries').toStringList())
        self.filtercb.setChecked(s.value('filter', True).toBool())
        full = self.revsethist + self._permanent_queries
        self.revsetcombo.clear()
        self.revsetcombo.addItems(full)
        self.revsetcombo.setCurrentIndex(-1)
        self.setVisible(s.value('showrepofilterbar').toBool())
        self.showHiddenBtn.setChecked(s.value('showhidden').toBool())
        self._loadBranchFilterSettings(s)
        s.endGroup()

    def saveSettings(self, s):
        try:
            repoid = str(self._repo[0])
        except EnvironmentError:
            return
        s.beginGroup('revset/' + repoid)
        s.setValue('geom', self.entrydlg.saveGeometry())
        s.setValue('queries', self.revsethist)
        s.setValue('filter', self.filtercb.isChecked())
        s.setValue('showrepofilterbar', not self.isHidden())
        self._saveBranchFilterSettings(s)
        s.setValue('showhidden', self.showHiddenBtn.isChecked())
        s.endGroup()

    def _initBranchFilter(self):
        self._branchLabel = QToolButton(
            text=_('Branch'), popupMode=QToolButton.MenuButtonPopup,
            statusTip=_('Display graph the named branch only'))
        self._branchLabel.clicked.connect(self._branchLabel.showMenu)
        self._branchMenu = QMenu(self._branchLabel)
        self._abranchAction = self._branchMenu.addAction(
            _('Display only active branches'), self.refresh)
        self._abranchAction.setCheckable(True)
        self._cbranchAction = self._branchMenu.addAction(
            _('Display closed branches'), self.refresh)
        self._cbranchAction.setCheckable(True)
        self._allparAction = self._branchMenu.addAction(
            _('Include all ancestors'), self._emitBranchChanged)
        self._allparAction.setCheckable(True)
        self._branchLabel.setMenu(self._branchMenu)

        self._branchCombo = QComboBox()
        self._branchCombo.setMinimumContentsLength(10)
        self._branchCombo.setMaxVisibleItems(30)
        self._branchCombo.currentIndexChanged.connect(self._emitBranchChanged)

        self.addWidget(self._branchLabel)
        self.addWidget(qtlib.Spacer(2, 2))
        self.addWidget(self._branchCombo)

    def _loadBranchFilterSettings(self, s):
        branch = unicode(s.value('branch').toString())
        if branch == '.':
            branch = hglib.tounicode(self._repo.dirstate.branch())
        self._branchCombo.blockSignals(True)
        self.setBranch(branch)
        self._branchCombo.blockSignals(False)

    def _saveBranchFilterSettings(self, s):
        branch = self.branch()
        if branch == hglib.tounicode(self._repo.dirstate.branch()):
            # special case for working branch: it's common to have multiple
            # clones which are updated to particular branches.
            branch = '.'
        s.setValue('branch', branch)

    def _updateBranchFilter(self):
        """Update the list of branches"""
        curbranch = self.branch()

        if self._abranchAction.isChecked():
            branches = sorted(set([self._repo[n].branch()
                for n in self._repo.heads()
                if not self._repo[n].extra().get('close')]))
        elif self._cbranchAction.isChecked():
            branches = sorted(self._repo.branchtags().keys())
        else:
            branches = self._repo.namedbranches

        # easy access to common branches (Python sorted() is stable)
        priomap = {self._repo.dirstate.branch(): -2, 'default': -1}
        branches = sorted(branches, key=lambda e: priomap.get(e, 0))

        self._branchCombo.blockSignals(True)
        self._branchCombo.clear()
        self._branchCombo.addItem(self._allBranchesLabel)
        for branch in branches:
            self._branchCombo.addItem(hglib.tounicode(branch))
            self._branchCombo.setItemData(self._branchCombo.count() - 1,
                                          hglib.tounicode(branch),
                                          Qt.ToolTipRole)
        self._branchCombo.setEnabled(self.filterEnabled and bool(branches))
        self._branchCombo.blockSignals(False)

        if curbranch and curbranch not in branches:
            self._emitBranchChanged()  # falls back to "show all"
        else:
            self.setBranch(curbranch)

    @pyqtSlot(unicode)
    def setBranch(self, branch):
        """Change the current branch by name [unicode]"""
        if not branch:
            index = 0
        else:
            index = self._branchCombo.findText(branch)
        if index >= 0:
            self._branchCombo.setCurrentIndex(index)

    def branch(self):
        """Return the current branch name [unicode]"""
        if self._branchCombo.currentIndex() == 0:
            return ''
        else:
            return unicode(self._branchCombo.currentText())

    def getShowHidden(self):
        return self.showHiddenBtn.isChecked()

    @pyqtSlot()
    def _emitBranchChanged(self):
        self.branchChanged.emit(self.branch(),
                                self._allparAction.isChecked())

    @pyqtSlot()
    def refresh(self):
        self._updateBranchFilter()
        self._updateShowHiddenBtnState()

    def _updateShowHiddenBtnState(self):
        hashidden = bool(repoview.filterrevs(self._repo, 'visible'))
        self.showHiddenBtn.setEnabled(hashidden)

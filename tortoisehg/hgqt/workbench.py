
# -*- coding: iso-8859-1 -*-
#!/usr/bin/env python
# workbench.py - main TortoiseHg Window
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.
"""
Main Qt4 application for TortoiseHg
"""

import os

from mercurial import hg
from mercurial.error import RepoError

from tortoisehg.util.hglib import tounicode
from tortoisehg.hgqt import repomodel
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.decorators import timeit
from tortoisehg.hgqt.qtlib import geticon, getfont, configstyles
from tortoisehg.hgqt.quickbar import FindInGraphlogQuickBar
from tortoisehg.hgqt.repowidget import RepoWidget
from tortoisehg.hgqt.commit import CommitWidget
from tortoisehg.hgqt.reporegistry import RepoRegistryView
from tortoisehg.hgqt.logcolumns import ColumnSelectDialog

from tortoisehg.util import paths

from PyQt4.QtCore import *
from PyQt4.QtGui import *

connect = QObject.connect


class Workbench(QMainWindow):
    """hg repository viewer/browser application"""

    def __init__(self, ui, repo=None):
        self.ui = ui

        self._reload_rev = None
        self._reload_file = None

        self._loading = True
        self._scanForRepoChanges = True
        self._searchWidgets = []

        self.commitwidgets = {} # key: reporoot

        QMainWindow.__init__(self)

        self.load_config(ui)
        self.setupUi()
        self._quickbars = []
        self.disab_shortcuts = []

        self.repotabs_splitter.setCollapsible(0, False)

        self.dummywidget = QWidget()
        self.revDetailsStackedWidget.addWidget(self.dummywidget)
        self.revDetailsStackedWidget.setCurrentWidget(self.dummywidget)
        self.currentRepoRoot = ''

        self.setWindowTitle('TortoiseHg Workbench')

        self.reporegistry = rr = RepoRegistryView(ui, self)
        rr.setObjectName('RepoRegistryView')
        self.addDockWidget(Qt.LeftDockWidgetArea, rr)

        rr.openRepoSignal.connect(self.openRepo)

        if repo:
            self.addRepoTab(repo)

        tw = self.repoTabsWidget
        connect(tw, SIGNAL('tabCloseRequested(int)'), self.repoTabCloseRequested)
        connect(tw, SIGNAL('currentChanged(int)'), self.repoTabChanged)

        tw = self.taskTabsWidget
        tw.currentChanged.connect(self.taskTabChanged)

        self.createActions()
        self.createToolbars()

        self.repoTabChanged()
        self.setupBranchCombo()
        self.restoreSettings()
        self.setAcceptDrops(True)

        def gotVisible(state):
            self.actionShowRepoRegistry.setChecked(self.reporegistry.isVisible())
        self.reporegistry.visibilityChanged.connect(gotVisible)

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
        configstyles(ui)
        # TODO: connect to font changed signal
        font = getfont(ui, 'fontlog').font()
        self._font = font
        self.rowheight = 8
        self.users, self.aliases = [], []

    def accept(self):
        self.close()

    def reject(self):
        self.close()

    def setupUi(self):
        self.resize(627, 721)

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icons/log.svg"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        self.centralwidget = QWidget(self)

        self.verticalLayout = vl = QVBoxLayout(self.centralwidget)
        vl.setSpacing(0)
        vl.setMargin(0)

        self.repotabs_splitter = sp = QSplitter(self.centralwidget)
        sp.hide()
        sp.setOrientation(Qt.Vertical)
        self.verticalLayout.addWidget(sp)

        self.repoTabsWidget = tw = QTabWidget(self.repotabs_splitter)
        tw.setDocumentMode(True)
        tw.setTabsClosable(True)
        tw.setMovable(True)
        sp = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sp.setHorizontalStretch(1)
        sp.setVerticalStretch(1)
        sp.setHeightForWidth(tw.sizePolicy().hasHeightForWidth())
        tw.setSizePolicy(sp)

        self.taskTabsWidget = tt = QTabWidget(self.repotabs_splitter)
        tt.setDocumentMode(True)
        tt.setTabPosition(QTabWidget.East)
        self.revDetailsStackedWidget = sw = QStackedWidget()
        sw.minimumSizeHint = lambda: QSize(0, 0)
        index = tt.addTab(sw, geticon('log'), '')
        tt.setTabToolTip(index, _("Revision details"))
        self.commitStackedWidget = sw = QStackedWidget()
        sw.minimumSizeHint = lambda: QSize(0, 0)
        index = tt.addTab(sw, geticon('commit'), '')
        tt.setTabToolTip(index, _("Commit"))
        sw = QStackedWidget()
        sw.minimumSizeHint = lambda: QSize(0, 0)
        index = tt.addTab(sw, geticon('sync'), '')
        tt.setTabToolTip(index, _("Synchronize"))

        self.setCentralWidget(self.centralwidget)

        self.statusbar = QStatusBar(self)
        self.setStatusBar(self.statusbar)

        self.toolBar_treefilters = tb = QToolBar(_("Filter Toolbar"), self)
        tb.setEnabled(True)
        tb.setObjectName("toolBar_treefilters")
        self.addToolBar(Qt.ToolBarArea(Qt.TopToolBarArea), tb)

        self.toolBar_diff = tb = QToolBar(_("Diff Toolbar"), self)
        tb.setObjectName("toolBar_diff")
        self.addToolBar(Qt.ToolBarArea(Qt.TopToolBarArea), tb)

        self.actionOpen_repository = a = QAction(_("&Open Repository"), self)
        a.setShortcut("Ctrl+O")

        self.actionRefresh = a = QAction(_("&Refresh"), self)
        a.setShortcut("Ctrl+R")

        self.actionQuit = a = QAction(_("E&xit"), self)
        a.setShortcut("None")
        a.setIconText(_("Exit"))
        a.setToolTip(_("Exit"))

        self.actionAbout = QAction(_("About"), self)
        self.actionDisplayAllBranches = QAction("displayAllBranches", self)
        self.actionHelp = QAction(_("Help"), self)

        self.actionBack = a = QAction(_("Back"), self)
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icons/back.svg"), QIcon.Normal, QIcon.Off)
        a.setIcon(icon)

        self.actionForward = a = QAction(_("Forward"), self)
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icons/forward.svg"), QIcon.Normal, QIcon.Off)
        a.setIcon(icon)

        self.actionShowPaths = a = QAction(_("Show Paths"), self)
        a.setCheckable(True)

        self.actionSelectColumns = QAction(_("Choose Log Columns..."), self)

        a = QAction(_("Show Repository Registry"), self)
        a.setCheckable(True)
        self.actionShowRepoRegistry = a

        self.menubar = QMenuBar(self)
        self.setMenuBar(self.menubar)

        self.menuFile = m = QMenu(_("&File"), self.menubar)
        m.addAction(self.actionOpen_repository)
        m.addAction(self.actionRefresh)
        m.addSeparator()
        m.addAction(self.actionQuit)

        self.menuHelp = m = QMenu(_("&Help"), self.menubar)
        m.addAction(self.actionHelp)
        m.addAction(self.actionAbout)

        self.menuView = m = QMenu(_("View"), self.menubar)
        m.addAction(self.actionShowRepoRegistry)
        m.addAction(self.actionShowPaths)
        m.addSeparator()
        m.addAction(self.actionSelectColumns)

        self.menubar.addAction(self.menuFile.menuAction())
        self.menubar.addAction(self.menuView.menuAction())
        self.menubar.addAction(self.menuHelp.menuAction())

        self.toolBar_edit = tb = QToolBar(_("Edit Toolbar"), self)
        tb.setEnabled(True)
        tb.setObjectName("toolBar_edit")
        tb.addAction(self.actionRefresh)
        tb.addSeparator()
        tb.addAction(self.actionBack)
        tb.addAction(self.actionForward)
        tb.addSeparator()
        self.addToolBar(Qt.ToolBarArea(Qt.TopToolBarArea), tb)

    def workingCopySelected(self):
        cw = self.createCommitWidget(self.currentRepoRoot)
        self.commitStackedWidget.setCurrentWidget(cw)
        self.taskTabsWidget.setCurrentIndex(1)

    def revisionSelected(self):
        self.taskTabsWidget.setCurrentIndex(0)

    def showRepoRegistry(self, show):
        self.reporegistry.setVisible(show)

    def openRepo(self, repopath):
        repo = hg.repository(self.ui, path=str(repopath))
        self.addRepoTab(repo)

    def find_root(self, url):
        p = str(url.toLocalFile())
        return paths.find_root(p)

    def dragEnterEvent(self, event):                
        d = event.mimeData()
        for u in d.urls():
            root = self.find_root(u)
            if root:
                event.acceptProposedAction()
                break

    def dropEvent(self, event):
        accept = False
        d = event.mimeData()
        for u in d.urls():            
            root = self.find_root(u)
            if root:
                repo = hg.repository(self.ui, path=root)
                self.addRepoTab(repo)
                accept = True
        if accept:
            event.acceptProposedAction()

    def repoTabCloseRequested(self, index):
        tw = self.repoTabsWidget
        w = tw.widget(index)
        if w.closeRepoWidget():
            tw.removeTab(index)

    def repoTabChanged(self, index=0):
        self.setupBranchCombo()

        w = self.repoTabsWidget.currentWidget()
        mode = 'diff'
        ann = False
        tags = []
        if w:
            mode = w.getMode()
            ann = w.getAnnotate()
            tags = w.repo.tags().keys()
            self.currentRepoRoot = root = w.repo.root
            if self.taskTabsWidget.currentIndex() == 1:
                cw = self.getCommitWidget(root)
                if cw:
                    self.commitStackedWidget.setCurrentWidget(cw)
                else:
                    self.taskTabsWidget.setCurrentIndex(0)
            w.switchedTo()
            self.repotabs_splitter.show()
        else:
            self.revDetailsStackedWidget.setCurrentWidget(self.dummywidget)
            self.currentRepoRoot = ''
            self.repotabs_splitter.hide()

        self.actionDiffMode.setEnabled(w is not None)
        self.actionDiffMode.setChecked(mode == 'diff')
        self.actionAnnMode.setChecked(ann)

    def taskTabChanged(self, index=0):
        if index == 1:
            self.workingCopySelected()

    def getCurentRepoRoot(self):
        return self.currentRepoRoot

    def addRepoTab(self, repo):
        '''opens the given repo in a new tab'''
        reponame = os.path.basename(repo.root)
        rw = RepoWidget(repo, self)
        rw.showMessageSignal.connect(self.showMessage)
        rw.switchToSignal.connect(self.switchTo)
        tw = self.repoTabsWidget
        index = self.repoTabsWidget.addTab(rw, reponame)
        tw.setCurrentIndex(index)
        self.reporegistry.addRepo(repo.root)

    def createCommitWidget(self, root):
        cw = self.getCommitWidget(root)
        if cw is None:
            pats = {}
            opts = {}
            print "creating commit widget for %s" % root
            cw = CommitWidget(pats, opts, root=root)
            self.commitwidgets[root] = cw
            self.commitStackedWidget.addWidget(cw)
            s = QSettings()
            cw.loadConfigs(s)
        return cw

    def getCommitWidget(self, root):
        '''returns None if no commit widget for that repo has been created yet'''
        return self.commitwidgets.get(root)

    def switchTo(self, widget):
        self.repoTabsWidget.setCurrentWidget(widget)

    def showMessage(self, msg):
        self.statusBar().showMessage(msg)

    def setupBranchCombo(self, *args):
        w = self.repoTabsWidget.currentWidget()
        if not w:
            self.branch_label_action.setEnabled(False)
            self.branch_comboBox_action.setEnabled(False)
            self.branch_comboBox.clear()
            return

        repo = w.repo
        allbranches = sorted(repo.branchtags().items())

        openbr = []
        for branch, brnode in allbranches:
            openbr.extend(repo.branchheads(branch, closed=False))
        clbranches = [br for br, node in allbranches if node not in openbr]
        branches = [br for br, node in allbranches if node in openbr]
        if self.branch_checkBox_action.isChecked():
            branches = branches + clbranches

        if len(branches) == 1:
            self.branch_label_action.setEnabled(False)
            self.branch_comboBox_action.setEnabled(False)
            self.branch_comboBox.clear()
        else:
            branches = [''] + branches
            self.branchesmodel = QStringListModel(branches)
            self.branch_comboBox.setModel(self.branchesmodel)
            self.branch_label_action.setEnabled(True)
            self.branch_comboBox_action.setEnabled(True)

            branch = w.filterbranch()
            index = -1
            for i, b in enumerate(branches):
                if b == branch:
                    index = i
                    break
            self.branch_comboBox.setCurrentIndex(index)

    def createToolbars(self):
        # find quickbar
        self.find_toolbar = tb = FindInGraphlogQuickBar(self)
        tb.setObjectName("find_toolbar")
        #tb.attachFileView(self.fileview)
        #tb.attachHeaderView(self.revdisplay)
        #connect(tb, SIGNAL('revisionSelected'), self.repoview.goto)
        #connect(tb, SIGNAL('fileSelected'), self.tableView_filelist.selectFile)
        connect(tb, SIGNAL('showMessage'), self.statusBar().showMessage,
                Qt.QueuedConnection)

        self.attachQuickBar(tb)

        findaction = self.find_toolbar.toggleViewAction()
        findaction.setIcon(geticon('find'))
        self.toolBar_edit.addAction(findaction)

        # tree filters toolbar
        self.branch_label = QToolButton()
        self.branch_label.setText("Branch")
        self.branch_label.setStatusTip("Display graph the named branch only")
        self.branch_label.setPopupMode(QToolButton.InstantPopup)
        self.branch_menu = QMenu()
        cbranch_action = self.branch_menu.addAction("Display closed branches")
        cbranch_action.setCheckable(True)
        self.branch_checkBox_action = cbranch_action
        self.branch_label.setMenu(self.branch_menu)
        self.branch_comboBox = QComboBox()
        connect(self.branch_comboBox, SIGNAL('activated(const QString &)'),
                self.refreshRevisionTable)
        connect(cbranch_action, SIGNAL('toggled(bool)'),
                self.setupBranchCombo)

        self.toolBar_treefilters.layout().setSpacing(3)

        self.branch_label_action = self.toolBar_treefilters.addWidget(self.branch_label)
        self.branch_comboBox_action = self.toolBar_treefilters.addWidget(self.branch_comboBox)
        self.toolBar_treefilters.addSeparator()
        self.toolBar_treefilters.addAction(self.actionSearch)
        self.toolBar_treefilters.addSeparator()

        # diff mode toolbar
        self.toolBar_diff.addAction(self.actionDiffMode)
        self.toolBar_diff.addAction(self.actionAnnMode)
        self.toolBar_diff.addAction(self.actionNextDiff)
        self.toolBar_diff.addAction(self.actionPrevDiff)

    def createActions(self):
        # main window actions (from .ui file)
        self.actionRefresh.triggered.connect(self.reload)
        self.actionAbout.triggered.connect(self.on_about)
        self.actionQuit.triggered.connect(self.close)
        self.actionBack.triggered.connect(self.back)
        self.actionForward.triggered.connect(self.forward)
        self.actionSelectColumns.triggered.connect(self.setHistoryColumns)
        self.actionShowPaths.toggled.connect(self.actionShowPathsToggled)
        self.actionShowRepoRegistry.toggled.connect(self.showRepoRegistry)

        self.actionQuit.setIcon(geticon('quit'))
        self.actionRefresh.setIcon(geticon('reload'))

        self.actionDiffMode = QAction('Diff mode', self)
        self.actionDiffMode.setCheckable(True)
        connect(self.actionDiffMode, SIGNAL('toggled(bool)'),
                self.setMode)

        self.actionAnnMode = QAction('Annotate', self)
        self.actionAnnMode.setCheckable(True)
        connect(self.actionAnnMode, SIGNAL('toggled(bool)'), self.setAnnotate)

        self.actionSearch = QAction('Search', self)
        self.actionSearch.setShortcut(Qt.Key_F3)
        connect(self.actionSearch, SIGNAL('triggered()'), self.on_search)

        self.actionHelp.setShortcut(Qt.Key_F1)
        self.actionHelp.setIcon(geticon('help'))
        connect(self.actionHelp, SIGNAL('triggered()'), self.on_help)

        # Next/Prev diff (in full file mode)
        self.actionNextDiff = QAction(geticon('down'), 'Next diff', self)
        self.actionNextDiff.setShortcut('Alt+Down')
        def filled():
            self.actionNextDiff.setEnabled(
                self.fileview.fileMode() and self.fileview.nDiffs())
        #connect(self.fileview, SIGNAL('filled'), filled)
        self.actionPrevDiff = QAction(geticon('up'), 'Previous diff', self)
        self.actionPrevDiff.setShortcut('Alt+Up')
        connect(self.actionNextDiff, SIGNAL('triggered()'),
                self.nextDiff)
        connect(self.actionPrevDiff, SIGNAL('triggered()'),
                self.prevDiff)
        self.actionDiffMode.setChecked(True)

        # Next/Prev file
        self.actionNextFile = QAction('Next file', self)
        self.actionNextFile.setShortcut('Right')
        #connect(self.actionNextFile, SIGNAL('triggered()'),
        #        self.tableView_filelist.nextFile)
        self.actionPrevFile = QAction('Prev file', self)
        self.actionPrevFile.setShortcut('Left')
        #connect(self.actionPrevFile, SIGNAL('triggered()'),
        #        self.tableView_filelist.prevFile)
        self.addAction(self.actionNextFile)
        self.addAction(self.actionPrevFile)
        self.disab_shortcuts.append(self.actionNextFile)
        self.disab_shortcuts.append(self.actionPrevFile)

        # navigate in file viewer
        self.actionNextLine = QAction('Next line', self)
        self.actionNextLine.setShortcut(Qt.SHIFT + Qt.Key_Down)
        #connect(self.actionNextLine, SIGNAL('triggered()'),
        #        self.fileview.nextLine)
        self.addAction(self.actionNextLine)
        self.actionPrevLine = QAction('Prev line', self)
        self.actionPrevLine.setShortcut(Qt.SHIFT + Qt.Key_Up)
        #connect(self.actionPrevLine, SIGNAL('triggered()'),
        #        self.fileview.prevLine)
        self.addAction(self.actionPrevLine)
        self.actionNextCol = QAction('Next column', self)
        self.actionNextCol.setShortcut(Qt.SHIFT + Qt.Key_Right)
        #connect(self.actionNextCol, SIGNAL('triggered()'),
        #        self.fileview.nextCol)
        self.addAction(self.actionNextCol)
        self.actionPrevCol = QAction('Prev column', self)
        self.actionPrevCol.setShortcut(Qt.SHIFT + Qt.Key_Left)
        #connect(self.actionPrevCol, SIGNAL('triggered()'),
        #        self.fileview.prevCol)
        self.addAction(self.actionPrevCol)

        connect(self.actionOpen_repository, SIGNAL('triggered()'),
                self.openRepository)

    def actionShowPathsToggled(self, show):
        self.reporegistry.showPaths(show)

    def setHistoryColumns(self, *args):
        """Display the column selection dialog"""
        dlg = ColumnSelectDialog(repomodel.ALLCOLUMNS)
        if dlg.exec_() == QDialog.Accepted:
            w = self.repoTabsWidget.currentWidget()
            if w:
                w.repoview.model().updateColumns()
                w.repoview.resizeColumns()

    def back(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.back()

    def forward(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.forward()

    def openRepository(self):
        caption = _('Select repository directory to open')
        FD = QFileDialog
        path = FD.getExistingDirectory(parent=self, caption=caption,
            options=FD.ShowDirsOnly | FD.ReadOnly)
        path = str(path)
        try:
            repo = hg.repository(self.ui, path=path)
            self.addRepoTab(repo)
        except RepoError:
            QMessageBox.warning(self, _('Failed to open repository'), 
                _('%s is not a valid repository') % path)

    def setMode(self, mode):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.setMode(mode)
        self.actionAnnMode.setEnabled(not mode)
        self.actionNextDiff.setEnabled(not mode)
        self.actionPrevDiff.setEnabled(not mode)

    def setAnnotate(self, ann):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.setAnnotate(ann)

    def nextDiff(self):
        pass

    def prevDiff(self):
        pass

    def file_displayed(self, filename):
        # self.actionPrevDiff.setEnabled(False)
        pass

    def reload(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.reload()
            self.setupBranchCombo()

    def reloadRepository(self, root):
        tw = self.repoTabsWidget
        for idx in range(tw.count()):
            rw = tw.widget(idx)
            if rw.repo.root == root:
                rw.reload()
        self.setupBranchCombo()

    #@timeit
    def refreshRevisionTable(self, *args, **kw):
        """Starts the process of filling the HgModel"""
        branch = self.branch_comboBox.currentText()
        branch = str(branch)
        tw = self.repoTabsWidget
        w = tw.currentWidget()
        if w:
            w.setRepomodel(branch)
            if branch:
                tabtext = '%s [%s]' % (w.reponame(), branch)
            else:
                tabtext = w.reponame()
            tw.setTabText(tw.currentIndex(), tabtext)

    def on_about(self, *args):
        """ Display about dialog """
        from tortoisehg.hgqt.about import AboutDialog
        ad = AboutDialog()
        ad.exec_()

    def on_help(self, *args):
        pass

    def on_search(self, *args):
        from tortoisehg.hgqt.grep import SearchWidget
        w = self.repoTabsWidget.currentWidget()
        if w is None:
            return
        s = SearchWidget('', w.repo.root, self)
        s.setAllowedAreas(Qt.TopDockWidgetArea | Qt.BottomDockWidgetArea)
        s.setObjectName("searchWidget%d" % len(self._searchWidgets))
        self.addDockWidget(Qt.BottomDockWidgetArea, s)
        self._searchWidgets.append(s)

    def storeSettings(self):
        s = QSettings()
        wb = "Workbench/"
        s.setValue(wb + 'geometry', self.saveGeometry())
        s.setValue(wb + 'windowState', self.saveState())

        for n in self.splitternames:
            s.setValue(wb + n, getattr(self, n).saveState())

    def restoreSettings(self):
        s = QSettings()
        wb = "Workbench/"
        self.restoreGeometry(s.value(wb + 'geometry').toByteArray())
        self.restoreState(s.value(wb + 'windowState').toByteArray())

        self.splitternames = []
        sn = ('repotabs', )
        for n in sn:
            n += '_splitter'
            self.splitternames.append(n)
            getattr(self, n).restoreState(s.value(wb + n).toByteArray())

    def closeEvent(self, event):
        if not self.closeRepoTabs():
            event.ignore()
        else:
           self.storeSettings()
           self.reporegistry.close()

    def closeRepoTabs(self):
        '''returns False if close should be aborted'''
        tw = self.repoTabsWidget
        for idx in range(tw.count()):
            rw = tw.widget(idx)
            if not rw.closeRepoWidget():
                return False
        return True

def run(ui, *pats, **opts):
    repo = None
    root = paths.find_root()
    if root:
        repo = hg.repository(ui, path=root)
    return Workbench(ui, repo)

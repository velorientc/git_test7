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
import subprocess

from mercurial.error import RepoError

from tortoisehg.util.hglib import tounicode
from tortoisehg.util import paths, thgrepo

#from tortoisehg.hgqt.decorators import timeit

from tortoisehg.hgqt import repomodel
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.qtlib import geticon, getfont, configstyles
from tortoisehg.hgqt.quickbar import FindInGraphlogQuickBar
from tortoisehg.hgqt.repowidget import RepoWidget
from tortoisehg.hgqt.reporegistry import RepoRegistryView
from tortoisehg.hgqt.logcolumns import ColumnSelectDialog
from tortoisehg.hgqt.docklog import LogDockWidget

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

        QMainWindow.__init__(self)

        self.load_config(ui)
        self.setupUi()
        self._quickbars = []
        self.disab_shortcuts = []

        self.setWindowTitle('TortoiseHg Workbench')

        self.reporegistry = rr = RepoRegistryView(ui, self)
        rr.setObjectName('RepoRegistryView')
        self.addDockWidget(Qt.LeftDockWidgetArea, rr)

        self.log = LogDockWidget(self)
        self.log.setObjectName('Log')
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log)

        rr.openRepoSignal.connect(self.openRepo)

        if repo:
            self.addRepoTab(repo)

        tw = self.repoTabsWidget
        connect(tw, SIGNAL('tabCloseRequested(int)'), self.repoTabCloseRequested)
        connect(tw, SIGNAL('currentChanged(int)'), self.repoTabChanged)

        self.createActions()
        self.createToolbars()

        self.repoTabChanged()
        self.setupBranchCombo()
        self.restoreSettings()
        self.setAcceptDrops(True)

        def gotVisible(state):
            self.actionShowRepoRegistry.setChecked(self.reporegistry.isVisible())
        def logVisible(state):
            self.actionShowLog.setChecked(self.log.isVisible())

        self.reporegistry.visibilityChanged.connect(gotVisible)
        self.log.visibilityChanged.connect(logVisible)

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

        self.repoTabsWidget = tw = QTabWidget()
        tw.setDocumentMode(True)
        tw.setTabsClosable(True)
        tw.setMovable(True)
        sp = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sp.setHorizontalStretch(1)
        sp.setVerticalStretch(1)
        sp.setHeightForWidth(tw.sizePolicy().hasHeightForWidth())
        tw.setSizePolicy(sp)
        vl.addWidget(tw)

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

        self.actionNew_repository = a = QAction(_("&New Repository..."), self)
        a.setShortcut(QKeySequence.New)

        self.actionOpen_repository = a = QAction(_("&Open Repository..."), self)
        a.setShortcut(QKeySequence.Open)

        self.actionClose_repository = a = QAction(_("&Close Repository"), self)
        a.setShortcut(QKeySequence.Close)

        self.actionRefresh = a = QAction(_("&Refresh"), self)
        a.setShortcut(QKeySequence.Refresh)

        self.actionQuit = a = QAction(_("E&xit"), self)
        a.setShortcut(QKeySequence.Quit)
        a.setIconText(_("Exit"))
        a.setToolTip(_("Exit"))

        self.actionAbout = QAction(_("About"), self)
        self.actionDisplayAllBranches = QAction("displayAllBranches", self)
        self.actionHelp = QAction(_("Help"), self)

        self.actionBack = a = QAction(_("Back"), self)
        a.setEnabled(False)
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icons/back.svg"), QIcon.Normal, QIcon.Off)
        a.setIcon(icon)

        self.actionForward = a = QAction(_("Forward"), self)
        a.setEnabled(False)
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icons/forward.svg"), QIcon.Normal, QIcon.Off)
        a.setIcon(icon)

        self.actionLoadAll = a = QAction(_("Load all"), self)
        a.setEnabled(True)
#        icon = QIcon()
#        icon.addPixmap(QPixmap(":/icons/loadall.svg"), QIcon.Normal, QIcon.Off)
#        a.setIcon(icon)

        self.actionShowPaths = a = QAction(_("Show Paths"), self)
        a.setCheckable(True)

        self.actionSelectColumns = QAction(_("Choose Log Columns..."), self)

        a = QAction(_("Show Repository Registry"), self)
        a.setCheckable(True)
        self.actionShowRepoRegistry = a

        a = QAction(_("Show Output Log"), self)
        a.setCheckable(True)
        self.actionShowLog = a

        self.actionServe = QAction(_("Web Server"), self)
        self.actionImport = QAction(_("Import"), self)
        self.actionVerify = QAction(_("Verify"), self)
        self.actionRecover = QAction(_("Recover"), self)
        self.actionRollback = QAction(_("Rollback/Undo"), self)
        self.actionPurge = QAction(_("Purge"), self)
        self.actionExplore = QAction(_("Explore"), self)

        self.menubar = QMenuBar(self)
        self.setMenuBar(self.menubar)

        self.menuFile = m = QMenu(_("&File"), self.menubar)
        m.addAction(self.actionNew_repository)
        m.addAction(self.actionOpen_repository)
        m.addAction(self.actionClose_repository)
        m.addSeparator()
        m.addAction(self.actionQuit)

        self.menuHelp = m = QMenu(_("&Help"), self.menubar)
        m.addAction(self.actionHelp)
        m.addAction(self.actionAbout)

        self.menuView = m = QMenu(_("&View"), self.menubar)
        m.addAction(self.actionShowRepoRegistry)
        m.addAction(self.actionShowPaths)
        m.addAction(self.actionShowLog)
        m.addSeparator()
        m.addAction(self.actionSelectColumns)
        m.addSeparator()
        m.addAction(self.actionRefresh)

        self.menuRepository = m = QMenu(_("&Repository"), self.menubar)
        m.addAction(self.actionServe)
        m.addSeparator()
        m.addAction(self.actionImport)
        m.addSeparator()
        m.addAction(self.actionVerify)
        m.addAction(self.actionRecover)
        m.addSeparator()
        m.addAction(self.actionRollback)
        m.addAction(self.actionPurge)
        m.addSeparator()
        m.addAction(self.actionExplore)

        self.menubar.addAction(self.menuFile.menuAction())
        self.menubar.addAction(self.menuView.menuAction())
        self.menubar.addAction(self.menuRepository.menuAction())
        self.menubar.addAction(self.menuHelp.menuAction())

        self.toolBar_edit = tb = QToolBar(_("Edit Toolbar"), self)
        tb.setEnabled(True)
        tb.setObjectName("toolBar_edit")
        tb.addAction(self.actionRefresh)
        tb.addSeparator()
        tb.addAction(self.actionBack)
        tb.addAction(self.actionForward)
        tb.addSeparator()
        tb.addAction(self.actionLoadAll)
        tb.addSeparator()
        self.addToolBar(Qt.ToolBarArea(Qt.TopToolBarArea), tb)

    def showRepoRegistry(self, show):
        self.reporegistry.setVisible(show)

    def showLog(self, show):
        self.log.setVisible(show)

    def openRepo(self, repopath):
        repo = thgrepo.repository(self.ui, path=str(repopath))
        self.addRepoTab(repo)

    def find_root(self, url):
        p = str(url.toLocalFile())
        return paths.find_root(p)

    def outgoing_for_root(self, root, outgoing):
        repo = thgrepo.repository(self.ui, path=root)
        repo._outgoing = outgoing
        self.refreshRepository(root)
        # TODO: draw out arrows

    def dragEnterEvent(self, event):
        d = event.mimeData()
        for u in d.urls():
            root = self.find_root(u)
            if root:
                event.setDropAction(Qt.LinkAction)
                event.accept()
                break

    def dropEvent(self, event):
        accept = False
        d = event.mimeData()
        for u in d.urls():
            root = self.find_root(u)
            if root:
                self.openRepo(root)
                accept = True
        if accept:
            event.setDropAction(Qt.LinkAction)
            event.accept()

    def repoTabCloseRequested(self, index):
        tw = self.repoTabsWidget
        w = tw.widget(index)
        if w and w.closeRepoWidget():
            tw.removeTab(index)

    def repoTabChanged(self, index=0):
        self.setupBranchCombo()

        w = self.repoTabsWidget.currentWidget()
        if w:
            w.switchedTo()
        else:

            self.actionDiffMode.setEnabled(False)
            self.actionAnnMode.setEnabled(False)
            self.actionNextDiff.setEnabled(False)
            self.actionPrevDiff.setEnabled(False)

    def addRepoTab(self, repo):
        '''opens the given repo in a new tab'''
        reponame = os.path.basename(repo.root)
        rw = RepoWidget(repo, self)
        rw.showMessageSignal.connect(self.showMessage)
        rw.revDetailsWidget.fileview.showDescSignal.connect(self.showMessage)
        rw.switchToSignal.connect(self.switchTo)
        tw = self.repoTabsWidget
        index = self.repoTabsWidget.addTab(rw, reponame)
        tw.setCurrentIndex(index)
        self.reporegistry.addRepo(repo.root)

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
        if self.cbranch_action.isChecked():
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
        self.cbranch_action = cbranch_action
        allpar_action = self.branch_menu.addAction("Include all ancestors")
        allpar_action.setCheckable(True)
        self.allpar_action = allpar_action
        self.branch_label.setMenu(self.branch_menu)
        self.branch_comboBox = QComboBox()
        connect(self.branch_comboBox, SIGNAL('activated(const QString &)'),
                self.refreshRevisionTable)
        connect(cbranch_action, SIGNAL('toggled(bool)'),
                self.setupBranchCombo)
        connect(allpar_action, SIGNAL('toggled(bool)'),
                self.refreshRevisionTable)

        self.toolBar_treefilters.layout().setSpacing(3)

        self.branch_label_action = self.toolBar_treefilters.addWidget(self.branch_label)
        self.branch_comboBox_action = self.toolBar_treefilters.addWidget(self.branch_comboBox)
        self.toolBar_treefilters.addSeparator()

        # diff mode toolbar
        self.toolBar_diff.addAction(self.actionDiffMode)
        self.toolBar_diff.addAction(self.actionNextDiff)
        self.toolBar_diff.addAction(self.actionPrevDiff)
        self.toolBar_diff.addSeparator()
        self.toolBar_diff.addAction(self.actionAnnMode)

    def createActions(self):
        # main window actions (from .ui file)
        self.actionRefresh.triggered.connect(self.reload)
        self.actionAbout.triggered.connect(self.on_about)
        self.actionQuit.triggered.connect(self.close)
        self.actionBack.triggered.connect(self.back)
        self.actionForward.triggered.connect(self.forward)
        self.actionImport.triggered.connect(self.thgimport)
        self.actionLoadAll.triggered.connect(self.loadall)
        self.actionSelectColumns.triggered.connect(self.setHistoryColumns)
        self.actionShowPaths.toggled.connect(self.actionShowPathsToggled)
        self.actionShowRepoRegistry.toggled.connect(self.showRepoRegistry)
        self.actionShowLog.toggled.connect(self.showLog)

        self.actionServe.triggered.connect(self.serve)
        self.actionVerify.triggered.connect(self.verify)
        self.actionRecover.triggered.connect(self.recover)
        self.actionRollback.triggered.connect(self.rollback)
        self.actionPurge.triggered.connect(self.purge)
        self.actionExplore.triggered.connect(self.explore)

        self.actionQuit.setIcon(geticon('quit'))
        self.actionRefresh.setIcon(geticon('reload'))

        self.actionDiffMode = QAction('Diff mode', self)
        self.actionDiffMode.setCheckable(True)
        connect(self.actionDiffMode, SIGNAL('toggled(bool)'),
                self.setMode)

        self.actionAnnMode = QAction('Annotate', self)
        self.actionAnnMode.setCheckable(True)
        connect(self.actionAnnMode, SIGNAL('toggled(bool)'), self.setAnnotate)

        self.actionHelp.setShortcut(QKeySequence.HelpContents)
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

        connect(self.actionNew_repository, SIGNAL('triggered()'),
                self.newRepository)
        connect(self.actionOpen_repository, SIGNAL('triggered()'),
                self.openRepository)
        connect(self.actionClose_repository, SIGNAL('triggered()'),
                self.closeRepository)

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

    def serve(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            from tortoisehg.hgqt import run
            run.serve(self.ui, root=w.repo.root)

    def thgimport(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.thgimport()

    def verify(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.verify()

    def recover(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.recover()

    def rollback(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.rollback()

    def purge(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.purge()

    def back(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.back()

    def forward(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.forward()

    def loadall(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.repoview.model().loadall()

    def newRepository(self):
        """ Run init dialog """
        from tortoisehg.hgqt.hginit import InitDialog
        initdlg = InitDialog(caller='workbench')
        def cmdfinished(res):
            if res == 0:
                path = initdlg.getPath()
                self.openRepo(path)
        initdlg.cmdfinished.connect(cmdfinished)
        initdlg.show()

    def openRepository(self):
        caption = _('Select repository directory to open')
        FD = QFileDialog
        path = FD.getExistingDirectory(parent=self, caption=caption,
            options=FD.ShowDirsOnly | FD.ReadOnly)
        path = str(path)
        if path:
            try:
                repo = thgrepo.repository(self.ui, path=path)
                self.addRepoTab(repo)
            except RepoError:
                QMessageBox.warning(self, _('Failed to open repository'),
                    _('%s is not a valid repository') % path)

    def setMode(self, mode):
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.setMode(mode)

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

    def refreshRepository(self, root):
        for rw in self._findrepowidget(root):
            rw.refresh()

    def reloadRepository(self, root):
        for rw in self._findrepowidget(root):
            rw.reload()
        self.setupBranchCombo()

    def _findrepowidget(self, root):
        """Iterates RepoWidget for the specified root"""
        tw = self.repoTabsWidget
        for idx in range(tw.count()):
            rw = tw.widget(idx)
            if rw.repo.root == root:
                yield rw

    #@timeit
    def refreshRevisionTable(self, *args, **kw):
        """Starts the process of filling the HgModel"""
        branch = self.branch_comboBox.currentText()
        branch = str(branch)
        allparents = self.allpar_action.isChecked()
        tw = self.repoTabsWidget
        w = tw.currentWidget()
        if w:
            w.setRepomodel(branch, allparents)
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

    def storeSettings(self):
        s = QSettings()
        wb = "Workbench/"
        s.setValue(wb + 'geometry', self.saveGeometry())
        s.setValue(wb + 'windowState', self.saveState())

    def restoreSettings(self):
        s = QSettings()
        wb = "Workbench/"
        self.restoreGeometry(s.value(wb + 'geometry').toByteArray())
        self.restoreState(s.value(wb + 'windowState').toByteArray())

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

    def closeRepository(self):
        """close the current repo tab"""
        self.repoTabCloseRequested(self.repoTabsWidget.currentIndex())

    def explore(self):
        w = self.repoTabsWidget.currentWidget()
        if w:
            self.launchExplorer(w.repo.root)

    def launchExplorer(self, root):
        """open Windows Explorer at the repo root"""
        if os.name == 'nt':
            subprocess.call(['explorer.exe', root])
        elif os.name == 'posix':
            subprocess.call(['nautilus', root])


def run(ui, *pats, **opts):
    repo = None
    root = paths.find_root()
    if root:
        repo = thgrepo.repository(ui, path=root)
    return Workbench(ui, repo)

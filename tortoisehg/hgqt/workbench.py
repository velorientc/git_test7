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
import sys, os
import re

from PyQt4 import QtCore, QtGui, Qsci

from mercurial import ui, hg, util
from mercurial.error import RepoError

from tortoisehg.util.util import tounicode
from tortoisehg.util.util import rootpath, find_repository

from tortoisehg.hgqt.i18n import _

from tortoisehg.hgqt.decorators import timeit

from tortoisehg.hgqt.config import HgConfig
from tortoisehg.hgqt.qtlib import geticon
from tortoisehg.hgqt.quickbar import FindInGraphlogQuickBar
from tortoisehg.hgqt.repowidget import RepoWidget
from tortoisehg.hgqt.commit import CommitWidget
from tortoisehg.hgqt.reporegistry import RepoRegistryView

from tortoisehg.util import paths

from mercurial.error import RepoError

Qt = QtCore.Qt
bold = QtGui.QFont.Bold
connect = QtCore.QObject.connect
SIGNAL = QtCore.SIGNAL


class Workbench(QtGui.QMainWindow):
    """hg repository viewer/browser application"""

    def __init__(self, ui, repo=None):
        self.ui = ui

        self._reload_rev = None
        self._reload_file = None

        self._loading = True
        self._scanForRepoChanges = True
        self._searchWidgets = []

        self.commitwidgets = {} # key: reporoot

        QtGui.QMainWindow.__init__(self)

        self.load_config(ui)
        self.setupUi()
        self._quickbars = []
        self.disab_shortcuts = []

        self.repotabs_splitter.setCollapsible(0, False)

        self.dummywidget = QtGui.QWidget()
        self.stackedWidget.addWidget(self.dummywidget)
        self.stackedWidget.setCurrentWidget(self.dummywidget)

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
        cfg = HgConfig(ui)
        fontstr = cfg.getFont()
        font = QtGui.QFont()
        try:
            if not font.fromString(fontstr):
                raise Exception
        except:
            print "bad font name '%s'" % fontstr
            font.setFamily("Monospace")
            font.setFixedPitch(True)
            font.setPointSize(10)
        self._font = font

        self.rowheight = cfg.getRowHeight()
        self.users, self.aliases = cfg.getUsers()
        return cfg

    def accept(self):
        self.close()

    def reject(self):
        self.close()

    def setupUi(self):
        self.resize(627, 721)

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icons/log.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.setWindowIcon(icon)

        self.centralwidget = QtGui.QWidget(self)

        self.verticalLayout = QtGui.QVBoxLayout(self.centralwidget)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setMargin(0)

        self.repotabs_splitter = QtGui.QSplitter(self.centralwidget)
        self.repotabs_splitter.setOrientation(QtCore.Qt.Vertical)
        self.repotabs_splitter.setObjectName("repotabs_splitter")

        self.repoTabsWidget = tw = QtGui.QTabWidget(self.repotabs_splitter)
        tw.setDocumentMode(True)
        tw.setTabsClosable(True)
        tw.setMovable(True)
        sp = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sp.setHorizontalStretch(1)
        sp.setVerticalStretch(1)
        sp.setHeightForWidth(tw.sizePolicy().hasHeightForWidth())
        tw.setSizePolicy(sp)

        self.stackedWidget = QtGui.QStackedWidget(self.repotabs_splitter)

        self.verticalLayout.addWidget(self.repotabs_splitter)

        self.setCentralWidget(self.centralwidget)

        self.menubar = QtGui.QMenuBar(self)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 627, 19))

        self.menuFile = QtGui.QMenu(self.menubar)
        self.menuHelp = QtGui.QMenu(self.menubar)
        self.menuView = QtGui.QMenu(self.menubar)

        self.setMenuBar(self.menubar)

        self.statusbar = QtGui.QStatusBar(self)
        self.setStatusBar(self.statusbar)

        self.toolBar_edit = QtGui.QToolBar(self)
        self.toolBar_edit.setEnabled(True)
        self.toolBar_edit.setObjectName("toolBar_edit")
        self.addToolBar(QtCore.Qt.ToolBarArea(QtCore.Qt.TopToolBarArea), self.toolBar_edit)

        self.toolBar_treefilters = QtGui.QToolBar(self)
        self.toolBar_treefilters.setEnabled(True)
        self.toolBar_treefilters.setObjectName("toolBar_treefilters")
        self.addToolBar(QtCore.Qt.ToolBarArea(QtCore.Qt.TopToolBarArea), self.toolBar_treefilters)

        self.toolBar_diff = QtGui.QToolBar(self)
        self.toolBar_diff.setObjectName("toolBar_diff")
        self.addToolBar(QtCore.Qt.ToolBarArea(QtCore.Qt.TopToolBarArea), self.toolBar_diff)

        self.toolBar_help = QtGui.QToolBar(self)
        self.toolBar_help.setObjectName("toolBar_help")
        self.addToolBar(QtCore.Qt.ToolBarArea(QtCore.Qt.TopToolBarArea), self.toolBar_help)

        self.actionOpen_repository = QtGui.QAction(self)
        self.actionRefresh = QtGui.QAction(self)
        self.actionQuit = QtGui.QAction(self)
        self.actionQuit.setShortcut("None")
        self.actionAbout = QtGui.QAction(self)
        self.actionDisplayAllBranches = QtGui.QAction(self)
        self.actionHelp = QtGui.QAction(self)

        self.actionBack = QtGui.QAction(self)
        icon1 = QtGui.QIcon()
        icon1.addPixmap(QtGui.QPixmap(":/icons/back.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.actionBack.setIcon(icon1)

        self.actionForward = QtGui.QAction(self)
        icon2 = QtGui.QIcon()
        icon2.addPixmap(QtGui.QPixmap(":/icons/forward.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.actionForward.setIcon(icon2)

        self.actionShowPaths = QtGui.QAction(self)
        self.actionShowPaths.setCheckable(True)

        self.actionShowRepoRegistry = QtGui.QAction(self)
        self.actionShowRepoRegistry.setCheckable(True)

        self.menuFile.addAction(self.actionOpen_repository)
        self.menuFile.addAction(self.actionRefresh)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionQuit)

        self.menuHelp.addAction(self.actionAbout)
        self.menuHelp.addAction(self.actionHelp)

        self.menuView.addAction(self.actionShowRepoRegistry)
        self.menuView.addAction(self.actionShowPaths)

        self.menubar.addAction(self.menuFile.menuAction())
        self.menubar.addAction(self.menuView.menuAction())
        self.menubar.addAction(self.menuHelp.menuAction())

        self.toolBar_edit.addAction(self.actionRefresh)
        self.toolBar_edit.addSeparator()
        self.toolBar_edit.addAction(self.actionBack)
        self.toolBar_edit.addAction(self.actionForward)
        self.toolBar_edit.addSeparator()

        self.toolBar_help.addAction(self.actionHelp)

        self.menuFile.setTitle(_("&File"))
        self.menuHelp.setTitle(_("&Help"))
        self.menuView.setTitle(_("View"))
        self.toolBar_edit.setWindowTitle(_("Edit Toolbar"))
        self.toolBar_treefilters.setWindowTitle(_("Filter Toolbar"))
        self.toolBar_diff.setWindowTitle(_("Diff toolbar"))
        self.toolBar_help.setWindowTitle(_("Help toolbar"))
        self.actionOpen_repository.setText(_("&Open Repository"))
        self.actionOpen_repository.setShortcut("Ctrl+O")
        self.actionRefresh.setText(_("&Refresh"))
        self.actionRefresh.setShortcut("Ctrl+R")
        self.actionQuit.setText(_("E&xit"))
        self.actionQuit.setIconText(_("Exit"))
        self.actionQuit.setToolTip(_("Exit"))
        self.actionAbout.setText(_("About"))
        self.actionDisplayAllBranches.setText("displayAllBranches")
        self.actionHelp.setText(_("Help"))
        self.actionBack.setText(_("Back"))
        self.actionForward.setText(_("Forward"))
        self.actionShowPaths.setText(_("Show Paths"))
        self.actionShowRepoRegistry.setText(_("Show Repository Registry"))

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
            w.switchedTo()
        else:
            self.actionDiffMode.setEnabled(False)
            self.stackedWidget.setCurrentWidget(self.dummywidget)

        self.actionDiffMode.setChecked(mode == 'diff')
        self.actionAnnMode.setChecked(ann)

    def addRepoTab(self, repo):
        '''opens the given repo in a new tab'''
        reponame = os.path.basename(repo.root)

        if repo.root in self.commitwidgets:
            cw = self.commitwidgets[repo.root]
        else:
            pats = {}
            opts = {}
            cw = CommitWidget(pats, opts, root=repo.root)
            self.commitwidgets[repo.root] = cw
            self.stackedWidget.addWidget(cw)
            s = QtCore.QSettings()
            cw.loadConfigs(s)

        rw = RepoWidget(repo, self.stackedWidget, cw)
        rw.showMessageSignal.connect(self.showMessage)
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
        if self.branch_checkBox_action.isChecked():
            branches = branches + clbranches

        if len(branches) == 1:
            self.branch_label_action.setEnabled(False)
            self.branch_comboBox_action.setEnabled(False)
            self.branch_comboBox.clear()
        else:
            branches = [''] + branches
            self.branchesmodel = QtGui.QStringListModel(branches)
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
        self.branch_label = QtGui.QToolButton()
        self.branch_label.setText("Branch")
        self.branch_label.setStatusTip("Display graph the named branch only")
        self.branch_label.setPopupMode(QtGui.QToolButton.InstantPopup)
        self.branch_menu = QtGui.QMenu()
        cbranch_action = self.branch_menu.addAction("Display closed branches")
        cbranch_action.setCheckable(True)
        self.branch_checkBox_action = cbranch_action
        self.branch_label.setMenu(self.branch_menu)
        self.branch_comboBox = QtGui.QComboBox()
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
        self.actionShowPaths.toggled.connect(self.actionShowPathsToggled)
        self.actionShowRepoRegistry.toggled.connect(self.showRepoRegistry)

        self.actionQuit.setIcon(geticon('quit'))
        self.actionRefresh.setIcon(geticon('reload'))

        self.actionDiffMode = QtGui.QAction('Diff mode', self)
        self.actionDiffMode.setCheckable(True)
        connect(self.actionDiffMode, SIGNAL('toggled(bool)'),
                self.setMode)

        self.actionAnnMode = QtGui.QAction('Annotate', self)
        self.actionAnnMode.setCheckable(True)
        connect(self.actionAnnMode, SIGNAL('toggled(bool)'), self.setAnnotate)

        self.actionSearch = QtGui.QAction('Search', self)
        self.actionSearch.setShortcut(Qt.Key_F3)
        connect(self.actionSearch, SIGNAL('triggered()'), self.on_search)

        self.actionHelp.setShortcut(Qt.Key_F1)
        self.actionHelp.setIcon(geticon('help'))
        connect(self.actionHelp, SIGNAL('triggered()'), self.on_help)

        # Next/Prev diff (in full file mode)
        self.actionNextDiff = QtGui.QAction(geticon('down'), 'Next diff', self)
        self.actionNextDiff.setShortcut('Alt+Down')
        def filled():
            self.actionNextDiff.setEnabled(
                self.fileview.fileMode() and self.fileview.nDiffs())
        #connect(self.fileview, SIGNAL('filled'), filled)
        self.actionPrevDiff = QtGui.QAction(geticon('up'), 'Previous diff', self)
        self.actionPrevDiff.setShortcut('Alt+Up')
        connect(self.actionNextDiff, SIGNAL('triggered()'),
                self.nextDiff)
        connect(self.actionPrevDiff, SIGNAL('triggered()'),
                self.prevDiff)
        self.actionDiffMode.setChecked(True)

        # Next/Prev file
        self.actionNextFile = QtGui.QAction('Next file', self)
        self.actionNextFile.setShortcut('Right')
        #connect(self.actionNextFile, SIGNAL('triggered()'),
        #        self.tableView_filelist.nextFile)
        self.actionPrevFile = QtGui.QAction('Prev file', self)
        self.actionPrevFile.setShortcut('Left')
        #connect(self.actionPrevFile, SIGNAL('triggered()'),
        #        self.tableView_filelist.prevFile)
        self.addAction(self.actionNextFile)
        self.addAction(self.actionPrevFile)
        self.disab_shortcuts.append(self.actionNextFile)
        self.disab_shortcuts.append(self.actionPrevFile)

        # Next/Prev rev
        self.actionNextRev = QtGui.QAction('Next revision', self)
        self.actionNextRev.setShortcut('Down')
        #connect(self.actionNextRev, SIGNAL('triggered()'),
        #        self.repoview.nextRev)
        self.actionPrevRev = QtGui.QAction('Prev revision', self)
        self.actionPrevRev.setShortcut('Up')
        #connect(self.actionPrevRev, SIGNAL('triggered()'),
        #        self.repoview.prevRev)
        self.addAction(self.actionNextRev)
        self.addAction(self.actionPrevRev)
        self.disab_shortcuts.append(self.actionNextRev)
        self.disab_shortcuts.append(self.actionPrevRev)

        # navigate in file viewer
        self.actionNextLine = QtGui.QAction('Next line', self)
        self.actionNextLine.setShortcut(Qt.SHIFT + Qt.Key_Down)
        #connect(self.actionNextLine, SIGNAL('triggered()'),
        #        self.fileview.nextLine)
        self.addAction(self.actionNextLine)
        self.actionPrevLine = QtGui.QAction('Prev line', self)
        self.actionPrevLine.setShortcut(Qt.SHIFT + Qt.Key_Up)
        #connect(self.actionPrevLine, SIGNAL('triggered()'),
        #        self.fileview.prevLine)
        self.addAction(self.actionPrevLine)
        self.actionNextCol = QtGui.QAction('Next column', self)
        self.actionNextCol.setShortcut(Qt.SHIFT + Qt.Key_Right)
        #connect(self.actionNextCol, SIGNAL('triggered()'),
        #        self.fileview.nextCol)
        self.addAction(self.actionNextCol)
        self.actionPrevCol = QtGui.QAction('Prev column', self)
        self.actionPrevCol.setShortcut(Qt.SHIFT + Qt.Key_Left)
        #connect(self.actionPrevCol, SIGNAL('triggered()'),
        #        self.fileview.prevCol)
        self.addAction(self.actionPrevCol)

        connect(self.actionOpen_repository, SIGNAL('triggered()'),
                self.openRepository)

    def actionShowPathsToggled(self, show):
        self.reporegistry.showPaths(show)

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
        FD = QtGui.QFileDialog
        path = FD.getExistingDirectory(parent=self, caption=caption,
            options=FD.ShowDirsOnly | FD.ReadOnly)
        path = str(path)
        try:
            repo = hg.repository(self.ui, path=path)
            self.addRepoTab(repo)
        except RepoError:
            QtGui.QMessageBox.warning(self, _('Failed to open repository'), 
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
        from __pkginfo__ import modname, version, short_desc, long_desc
        try:
            from mercurial.version import get_version
            hgversion = get_version()
        except:
            from mercurial.__version__ import version as hgversion

        msg = "<h2>About %(appname)s %(version)s</h2> (using hg %(hgversion)s)" % \
              {"appname": modname, "version": version, "hgversion": hgversion}
        msg += "<p><i>%s</i></p>" % short_desc.capitalize()
        msg += "<p>%s</p>" % long_desc
        QtGui.QMessageBox.about(self, "About %s" % modname, msg)

    def on_help(self, *args):
        pass

    def on_search(self, *args):
        from tortoisehg.hgqt.grep import SearchWidget
        # todo: get root of current repo, pass to search widget
        root = None
        s = SearchWidget('', root, self)
        s.setAllowedAreas(QtCore.Qt.TopDockWidgetArea|
                          QtCore.Qt.BottomDockWidgetArea)
        s.setObjectName("searchWidget%d" % len(self._searchWidgets))
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, s)
        self._searchWidgets.append(s)

    def okToContinue(self):
        '''
        returns False if there is unsaved data
        
        If there is unsaved data, present a dialog asking the user if it is ok to
        discard the changes made.
        '''
        return True

    def storeSettings(self):
        s = QtCore.QSettings()
        wb = "Workbench/"
        s.setValue(wb + 'geometry', self.saveGeometry())
        s.setValue(wb + 'windowState', self.saveState())

        for n in self.splitternames:
            s.setValue(wb + n, getattr(self, n).saveState())

    def restoreSettings(self):
        s = QtCore.QSettings()
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
        if not self.okToContinue() or not self.closeRepoTabs():
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

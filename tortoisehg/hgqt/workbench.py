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

from tortoisehg.util.i18n import _

from tortoisehg.hgqt.decorators import timeit

from tortoisehg.hgqt import icon as geticon
from tortoisehg.hgqt.dialogmixin import HgDialogMixin
from tortoisehg.hgqt.quickbar import FindInGraphlogQuickBar
from tortoisehg.hgqt.repowidget import RepoWidget

from tortoisehg.util import paths

from mercurial.error import RepoError

Qt = QtCore.Qt
bold = QtGui.QFont.Bold
connect = QtCore.QObject.connect
SIGNAL = QtCore.SIGNAL


class Workbench(QtGui.QMainWindow, HgDialogMixin):
    """hg repository viewer/browser application"""
    _uifile = 'workbench.ui'
    def __init__(self, ui, repo, fromhead=None):
        self.ui = ui

        # these are used to know where to go after a reload
        self._reload_rev = None
        self._reload_file = None
        self._loading = True
        self._scanForRepoChanges = True

        QtGui.QMainWindow.__init__(self)
        HgDialogMixin.__init__(self, ui)

        self.setWindowTitle('TortoiseHg Workbench')

        self.createActions()
        self.createToolbars()

        #self.textview_status.setFont(self._font)
        #connect(self.textview_status, SIGNAL('showMessage'),
        #        self.statusBar().showMessage)
        #connect(self.tableView_revisions, SIGNAL('showMessage'),
        #        self.statusBar().showMessage)

        #self.textview_header.setMessageWidget(self.message)

        #self.textview_header.commitsignal.connect(self.commit)

        self.addRepoTab(repo, fromhead)
        tw = self.repoTabsWidget
        tw.removeTab(0)
        self.repoTabChanged()
        connect(tw, SIGNAL('tabCloseRequested(int)'), self.repoTabCloseRequested)
        connect(tw, SIGNAL('currentChanged(int)'), self.repoTabChanged)

        # setup tables and views
        #self.setupHeaderTextview()
        #connect(self.textview_status, SIGNAL('fileDisplayed'),
        #        self.file_displayed)
        self.setupBranchCombo()
        # self.setupModels(fromhead)
        if fromhead:
            self.startrev_entry.setText(str(fromhead))
        #self.setupRevisionTable()

        # restore settings
        s = QtCore.QSettings()
        wb = "Workbench/"
        self.restoreGeometry(s.value(wb + 'geometry').toByteArray())
        self.restoreState(s.value(wb + 'windowState').toByteArray())
        '''
        self.splitternames = []
        sn = ('revisions', 'filelist', 'message')
        for n in sn:
            n += '_splitter'
            self.splitternames.append(n)
            getattr(self, n).restoreState(s.value(wb + n).toByteArray())
        '''

    def repoTabCloseRequested(self, index):
        tw = self.repoTabsWidget
        if (tw.count() == 1):
            return # ignore request to close the last tab
        tw.removeTab(index)

    def repoTabChanged(self, index=0):
        print "repoTabChanged(%i)" % index
        self.setupBranchCombo()

    def addRepoTab(self, repo, fromhead=None):
        '''opens the given repo in a new tab'''
        reponame = os.path.basename(repo.root)
        rw = RepoWidget(repo, fromhead)
        tw = self.repoTabsWidget
        index = self.repoTabsWidget.addTab(rw, reponame)
        tw.setCurrentIndex(index)

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
            self.branchesmodel = QtGui.QStringListModel([''] + branches)
            self.branch_comboBox.setModel(self.branchesmodel)
            self.branch_label_action.setEnabled(True)
            self.branch_comboBox_action.setEnabled(True)

    def createToolbars(self):
        # find quickbar
        self.find_toolbar = tb = FindInGraphlogQuickBar(self)
        tb.setObjectName("find_toolbar")
        #tb.attachFileView(self.textview_status)
        #tb.attachHeaderView(self.textview_header)
        #connect(tb, SIGNAL('revisionSelected'), self.tableView_revisions.goto)
        #connect(tb, SIGNAL('fileSelected'), self.tableView_filelist.selectFile)
        connect(tb, SIGNAL('showMessage'), self.statusBar().showMessage,
                Qt.QueuedConnection)

        self.attachQuickBar(tb)

        # navigation toolbar
        #self.toolBar_edit.addAction(self.tableView_revisions._actions['back'])
        #self.toolBar_edit.addAction(self.tableView_revisions._actions['forward'])

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

        self.startrev_label = QtGui.QToolButton()
        self.startrev_label.setText("Start rev.")
        self.startrev_label.setStatusTip("Display graph from this revision")
        self.startrev_label.setPopupMode(QtGui.QToolButton.InstantPopup)
        self.startrev_entry = QtGui.QLineEdit()
        self.startrev_entry.setStatusTip("Display graph from this revision")
        self.startrev_menu = QtGui.QMenu()
        follow_action = self.startrev_menu.addAction("Follow mode")
        follow_action.setCheckable(True)
        follow_action.setStatusTip("Follow changeset history from start revision")
        self.startrev_follow_action = follow_action
        self.startrev_label.setMenu(self.startrev_menu)

        self.revscompl_model = QtGui.QStringListModel(['tip'])
        self.revcompleter = QtGui.QCompleter(self.revscompl_model, self)
        self.startrev_entry.setCompleter(self.revcompleter)

        connect(self.startrev_entry, SIGNAL('editingFinished()'),
                self.refreshRevisionTable)
        connect(self.startrev_follow_action, SIGNAL('toggled(bool)'),
                self.refreshRevisionTable)
        self.startrev_label_action = self.toolBar_treefilters.addWidget(self.startrev_label)
        self.startrev_entry_action = self.toolBar_treefilters.addWidget(self.startrev_entry)

        # diff mode toolbar
        self.toolBar_diff.addAction(self.actionDiffMode)
        self.toolBar_diff.addAction(self.actionAnnMode)
        self.toolBar_diff.addAction(self.actionNextDiff)
        self.toolBar_diff.addAction(self.actionPrevDiff)

    def createActions(self):
        # main window actions (from .ui file)
        connect(self.actionRefresh, SIGNAL('triggered()'),
                self.reload)
        connect(self.actionAbout, SIGNAL('triggered()'),
                self.on_about)
        connect(self.actionQuit, SIGNAL('triggered()'),
                self.close)
        self.actionQuit.setIcon(geticon('quit'))
        self.actionRefresh.setIcon(geticon('reload'))

        self.actionDiffMode = QtGui.QAction('Diff mode', self)
        self.actionDiffMode.setCheckable(True)
        connect(self.actionDiffMode, SIGNAL('toggled(bool)'),
                self.setMode)

        self.actionAnnMode = QtGui.QAction('Annotate', self)
        self.actionAnnMode.setCheckable(True)
        #connect(self.actionAnnMode, SIGNAL('toggled(bool)'),
        #        self.textview_status.setAnnotate)

        self.actionHelp.setShortcut(Qt.Key_F1)
        self.actionHelp.setIcon(geticon('help'))
        connect(self.actionHelp, SIGNAL('triggered()'),
                self.on_help)
        
        # Next/Prev diff (in full file mode)
        self.actionNextDiff = QtGui.QAction(geticon('down'), 'Next diff', self)
        self.actionNextDiff.setShortcut('Alt+Down')
        def filled():
            self.actionNextDiff.setEnabled(
                self.textview_status.fileMode() and self.textview_status.nDiffs())
        #connect(self.textview_status, SIGNAL('filled'), filled)
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
        #        self.tableView_revisions.nextRev)
        self.actionPrevRev = QtGui.QAction('Prev revision', self)
        self.actionPrevRev.setShortcut('Up')
        #connect(self.actionPrevRev, SIGNAL('triggered()'),
        #        self.tableView_revisions.prevRev)
        self.addAction(self.actionNextRev)
        self.addAction(self.actionPrevRev)
        self.disab_shortcuts.append(self.actionNextRev)
        self.disab_shortcuts.append(self.actionPrevRev)

        # navigate in file viewer
        self.actionNextLine = QtGui.QAction('Next line', self)
        self.actionNextLine.setShortcut(Qt.SHIFT + Qt.Key_Down)
        #connect(self.actionNextLine, SIGNAL('triggered()'),
        #        self.textview_status.nextLine)
        self.addAction(self.actionNextLine)
        self.actionPrevLine = QtGui.QAction('Prev line', self)
        self.actionPrevLine.setShortcut(Qt.SHIFT + Qt.Key_Up)
        #connect(self.actionPrevLine, SIGNAL('triggered()'),
        #        self.textview_status.prevLine)
        self.addAction(self.actionPrevLine)
        self.actionNextCol = QtGui.QAction('Next column', self)
        self.actionNextCol.setShortcut(Qt.SHIFT + Qt.Key_Right)
        #connect(self.actionNextCol, SIGNAL('triggered()'),
        #        self.textview_status.nextCol)
        self.addAction(self.actionNextCol)
        self.actionPrevCol = QtGui.QAction('Prev column', self)
        self.actionPrevCol.setShortcut(Qt.SHIFT + Qt.Key_Left)
        #connect(self.actionPrevCol, SIGNAL('triggered()'),
        #        self.textview_status.prevCol)
        self.addAction(self.actionPrevCol)

        self.actionStartAtRev = QtGui.QAction('Start at rev.', self)
        self.actionStartAtRev.setShortcuts([Qt.Key_Backspace,])
        connect(self.actionStartAtRev, SIGNAL('triggered()'),
                self.startAtCurrentRev)
        self.addAction(self.actionStartAtRev)

        self.actionClearStartAtRev = QtGui.QAction('Clear start at rev.', self)
        self.actionClearStartAtRev.setShortcuts([Qt.SHIFT + Qt.Key_Backspace,])
        connect(self.actionClearStartAtRev, SIGNAL('triggered()'),
                self.clearStartAtRev)
        self.addAction(self.actionClearStartAtRev)

        connect(self.actionOpen_repository, SIGNAL('triggered()'),
                self.openRepository)

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

    def startAtCurrentRev(self):
        pass

    def clearStartAtRev(self):
        pass

    def setMode(self, mode):
        pass

    def nextDiff(self):
        pass

    def prevDiff(self):
        pass

    def load_config(self, ui):
        cfg = HgDialogMixin.load_config(self, ui)
        self.hidefinddelay = cfg.getHideFindDelay()

    def file_displayed(self, filename):
        # self.actionPrevDiff.setEnabled(False)
        pass

    def reload(self):
        """Reload the repository"""
        print "reload() called"
        w = self.repoTabsWidget.currentWidget()
        if w:
            w.reload()

    #@timeit
    def refreshRevisionTable(self, *args, **kw):
        pass

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

    def okToContinue(self):
        '''
        returns False if there is unsaved data
        
        If there is unsaved data, present a dialog asking the user if it is ok to
        discard the changes made.
        '''
        return True # we currently have no data to loose

    def closeEvent(self, event):
        if not self.okToContinue():
            event.ignore()
        s = QtCore.QSettings()
        wb = "Workbench/"
        s.setValue(wb + 'geometry', self.saveGeometry())
        s.setValue(wb + 'windowState', self.saveState())
        '''
        for n in self.splitternames:
            s.setValue(wb + n, getattr(self, n).saveState())
        '''

def run(ui, *pats, **opts):
    repo = None
    root = paths.find_root()
    if root:
        repo = hg.repository(ui, path=root)
    return Workbench(ui, repo)

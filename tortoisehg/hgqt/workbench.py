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

from mercurial import ui, hg
from mercurial import util

from tortoisehg.util.util import tounicode, has_closed_branch_support
from tortoisehg.util.util import rootpath, find_repository

from tortoisehg.hgqt.graph import diff as revdiff
from tortoisehg.hgqt.decorators import timeit

from tortoisehg.hgqt import icon as geticon
from tortoisehg.hgqt.repomodel import HgRepoListModel, HgFileListModel
from tortoisehg.hgqt.filedialogs import FileLogDialog, FileDiffDialog
from tortoisehg.hgqt.manifestdialog import ManifestDialog
from tortoisehg.hgqt.dialogmixin import HgDialogMixin
from tortoisehg.hgqt.update import UpdateDialog
from tortoisehg.hgqt.quickbar import FindInGraphlogQuickBar
from tortoisehg.hgqt.helpdialog import HelpDialog
from tortoisehg.hgqt import cmdui

from tortoisehg.util import paths

try:
    from mercurial.error import RepoError
except ImportError: # old API
    from mercurial.repo import RepoError

Qt = QtCore.Qt
bold = QtGui.QFont.Bold
connect = QtCore.QObject.connect
SIGNAL = QtCore.SIGNAL


class Workbench(QtGui.QMainWindow, HgDialogMixin):
    """hg repository viewer/browser application"""
    _uifile = 'workbench.ui'
    def __init__(self, repo, fromhead=None):
        self.repo = repo
        self._closed_branch_supp = has_closed_branch_support(self.repo)

        # these are used to know where to go after a reload
        self._reload_rev = None
        self._reload_file = None

        QtGui.QMainWindow.__init__(self)
        HgDialogMixin.__init__(self)

        self.setWindowTitle('TortoiseHg Workbench: %s' % os.path.abspath(self.repo.root))
        self.menubar.hide()

        self.createActions()
        self.createToolbars()

        self.textview_status.setFont(self._font)
        connect(self.textview_status, SIGNAL('showMessage'),
                self.statusBar().showMessage)
        connect(self.tableView_revisions, SIGNAL('showMessage'),
                self.statusBar().showMessage)

        self.textview_header.setMessageWidget(self.message)

        # setup tables and views
        self.setupHeaderTextview()
        connect(self.textview_status, SIGNAL('fileDisplayed'),
                self.file_displayed)
        self.setupBranchCombo()
        self.setupModels(fromhead)
        if fromhead:
            self.startrev_entry.setText(str(fromhead))
        self.setupRevisionTable()

        # restore settings
        s = QtCore.QSettings()
        wb = "Workbench/"
        self.restoreGeometry(s.value(wb + 'geometry').toByteArray())
        self.restoreState(s.value(wb + 'windowState').toByteArray())
        self.splitternames = []
        sn = ('revisions', 'filelist', 'message')
        for n in sn:
            n += '_splitter'
            self.splitternames.append(n)
            getattr(self, n).restoreState(s.value(wb + n).toByteArray())

        self._repodate = self._getrepomtime()
        self._watchrepotimer = self.startTimer(500)

    def timerEvent(self, event):
        if event.timerId() == self._watchrepotimer:
            mtime = self._getrepomtime()
            if mtime > self._repodate:
                self.statusBar().showMessage("Repository has been modified, "
                                             "reloading...", 2000)

                self.reload()

    def setupBranchCombo(self, *args):
        allbranches = sorted(self.repo.branchtags().items())
        if self._closed_branch_supp:
            openbr = []
            for branch, brnode in allbranches:
                openbr.extend(self.repo.branchheads(branch, closed=False))
            clbranches = [br for br, node in allbranches if node not in openbr]
            branches = [br for br, node in allbranches if node in openbr]
            if self.branch_checkBox_action.isChecked():
                branches = branches + clbranches
        else:
            branches = [br for br, node in allbranches] # open branches

        if len(branches) == 1:
            self.branch_label_action.setEnabled(False)
            self.branch_comboBox_action.setEnabled(False)
        else:
            self.branchesmodel = QtGui.QStringListModel([''] + branches)
            self.branch_comboBox.setModel(self.branchesmodel)
            self.branch_label_action.setEnabled(True)
            self.branch_comboBox_action.setEnabled(True)

    def createToolbars(self):
        # find quickbar
        self.find_toolbar = tb = FindInGraphlogQuickBar(self)
        tb.setObjectName("find_toolbar")
        tb.attachFileView(self.textview_status)
        tb.attachHeaderView(self.textview_header)
        connect(tb, SIGNAL('revisionSelected'), self.tableView_revisions.goto)
        connect(tb, SIGNAL('fileSelected'), self.tableView_filelist.selectFile)
        connect(tb, SIGNAL('showMessage'), self.statusBar().showMessage,
                Qt.QueuedConnection)

        self.attachQuickBar(tb)

        # navigation toolbar
        self.toolBar_edit.addAction(self.tableView_revisions._actions['back'])
        self.toolBar_edit.addAction(self.tableView_revisions._actions['forward'])

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
        connect(self.actionAnnMode, SIGNAL('toggled(bool)'),
                self.textview_status.setAnnotate)

        self.actionHelp.setShortcut(Qt.Key_F1)
        self.actionHelp.setIcon(geticon('help'))
        connect(self.actionHelp, SIGNAL('triggered()'),
                self.on_help)
        
        # Next/Prev diff (in full file mode)
        self.actionNextDiff = QtGui.QAction(geticon('down'), 'Next diff', self)
        self.actionNextDiff.setShortcut('Alt+Down')
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
        connect(self.actionNextFile, SIGNAL('triggered()'),
                self.tableView_filelist.nextFile)
        self.actionPrevFile = QtGui.QAction('Prev file', self)
        self.actionPrevFile.setShortcut('Left')
        connect(self.actionPrevFile, SIGNAL('triggered()'),
                self.tableView_filelist.prevFile)
        self.addAction(self.actionNextFile)
        self.addAction(self.actionPrevFile)
        self.disab_shortcuts.append(self.actionNextFile)
        self.disab_shortcuts.append(self.actionPrevFile)

        # Next/Prev rev
        self.actionNextRev = QtGui.QAction('Next revision', self)
        self.actionNextRev.setShortcut('Down')
        connect(self.actionNextRev, SIGNAL('triggered()'),
                self.tableView_revisions.nextRev)
        self.actionPrevRev = QtGui.QAction('Prev revision', self)
        self.actionPrevRev.setShortcut('Up')
        connect(self.actionPrevRev, SIGNAL('triggered()'),
                self.tableView_revisions.prevRev)
        self.addAction(self.actionNextRev)
        self.addAction(self.actionPrevRev)
        self.disab_shortcuts.append(self.actionNextRev)
        self.disab_shortcuts.append(self.actionPrevRev)

        # navigate in file viewer
        self.actionNextLine = QtGui.QAction('Next line', self)
        self.actionNextLine.setShortcut(Qt.SHIFT + Qt.Key_Down)
        connect(self.actionNextLine, SIGNAL('triggered()'),
                self.textview_status.nextLine)
        self.addAction(self.actionNextLine)
        self.actionPrevLine = QtGui.QAction('Prev line', self)
        self.actionPrevLine.setShortcut(Qt.SHIFT + Qt.Key_Up)
        connect(self.actionPrevLine, SIGNAL('triggered()'),
                self.textview_status.prevLine)
        self.addAction(self.actionPrevLine)
        self.actionNextCol = QtGui.QAction('Next column', self)
        self.actionNextCol.setShortcut(Qt.SHIFT + Qt.Key_Right)
        connect(self.actionNextCol, SIGNAL('triggered()'),
                self.textview_status.nextCol)
        self.addAction(self.actionNextCol)
        self.actionPrevCol = QtGui.QAction('Prev column', self)
        self.actionPrevCol.setShortcut(Qt.SHIFT + Qt.Key_Left)
        connect(self.actionPrevCol, SIGNAL('triggered()'),
                self.textview_status.prevCol)
        self.addAction(self.actionPrevCol)

        # Activate file (file diff navigator)
        self.actionActivateFile = QtGui.QAction('Activate file', self)
        self.actionActivateFile.setShortcuts([Qt.Key_Return, Qt.Key_Enter])
        def enterkeypressed():
            w = QtGui.QApplication.focusWidget()
            if not isinstance(w, QtGui.QLineEdit):
                self.tableView_filelist.fileActivated(self.tableView_filelist.currentIndex(),)
            else:
                w.emit(SIGNAL('editingFinished()'))
        connect(self.actionActivateFile, SIGNAL('triggered()'),
                enterkeypressed)

        self.actionActivateFileAlt = QtGui.QAction('Activate alt. file', self)
        self.actionActivateFileAlt.setShortcuts([Qt.ALT+Qt.Key_Return, Qt.ALT+Qt.Key_Enter])
        connect(self.actionActivateFileAlt, SIGNAL('triggered()'),
                lambda self=self:
                self.tableView_filelist.fileActivated(self.tableView_filelist.currentIndex(),
                                                      alternate=True))
        self.actionActivateRev = QtGui.QAction('Activate rev.', self)
        self.actionActivateRev.setShortcuts([Qt.SHIFT+Qt.Key_Return, Qt.SHIFT+Qt.Key_Enter])
        connect(self.actionActivateRev, SIGNAL('triggered()'),
                self.revision_activated)
        self.addAction(self.actionActivateFile)
        self.addAction(self.actionActivateFileAlt)
        self.addAction(self.actionActivateRev)
        self.disab_shortcuts.append(self.actionActivateFile)
        self.disab_shortcuts.append(self.actionActivateRev)

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

    def startAtCurrentRev(self):
        crev = self.tableView_revisions.current_rev
        if crev:
            self.startrev_entry.setText(str(crev))
            # XXX workaround: see refreshRevisionTable method 
            self.refreshRevisionTable(sender=self)

    def clearStartAtRev(self):
        self.startrev_entry.setText("")
        self._reload_rev = self.tableView_revisions.current_rev
        self._reload_file = self.tableView_filelist.currentFile()
        # XXX workaround: see refreshRevisionTable method 
        self.refreshRevisionTable(sender=self)

    def setMode(self, mode):
        self.textview_status.setMode(mode)
        self.actionAnnMode.setEnabled(not mode)
        self.actionNextDiff.setEnabled(not mode)
        self.actionPrevDiff.setEnabled(not mode)

    def nextDiff(self):
        notlast = self.textview_status.nextDiff()
        self.actionNextDiff.setEnabled(self.textview_status.fileMode() and notlast and self.textview_status.nDiffs())
        self.actionPrevDiff.setEnabled(self.textview_status.fileMode() and self.textview_status.nDiffs())

    def prevDiff(self):
        notfirst = self.textview_status.prevDiff()
        self.actionPrevDiff.setEnabled(self.textview_status.fileMode() and notfirst and self.textview_status.nDiffs())
        self.actionNextDiff.setEnabled(self.textview_status.fileMode() and self.textview_status.nDiffs())

    def load_config(self):
        cfg = HgDialogMixin.load_config(self)
        self.hidefinddelay = cfg.getHideFindDelay()

    def create_models(self, fromhead=None):
        self.repomodel = HgRepoListModel(self.repo, fromhead=fromhead)
        connect(self.repomodel, SIGNAL('filled'),
                self.on_filled)
        connect(self.repomodel, SIGNAL('showMessage'),
                self.statusBar().showMessage,
                Qt.QueuedConnection)

        self.filelistmodel = HgFileListModel(self.repo)

    def setupModels(self, fromhead=None):
        self.create_models(fromhead)
        self.tableView_revisions.setModel(self.repomodel)
        self.tableView_filelist.setModel(self.filelistmodel)
        self.textview_status.setModel(self.repomodel)
        self.find_toolbar.setModel(self.repomodel)

        filetable = self.tableView_filelist
        connect(filetable, SIGNAL('fileSelected'),
                self.textview_status.displayFile)
        connect(self.textview_status, SIGNAL('revForDiffChanged'),
                self.textview_header.setDiffRevision)

    def setupRevisionTable(self):
        view = self.tableView_revisions
        view.installEventFilter(self)
        connect(view, SIGNAL('revisionSelected'), self.revision_selected)
        connect(view, SIGNAL('revisionActivated'), self.revision_activated)
        connect(view, SIGNAL('updateToRevision'), self.updateToRevision)
        connect(self.textview_header, SIGNAL('revisionSelected'), view.goto)
        connect(self.textview_header, SIGNAL('parentRevisionSelected'), self.textview_status.displayDiff)
        self.attachQuickBar(view.goto_toolbar)
        gotoaction = view.goto_toolbar.toggleViewAction()
        gotoaction.setIcon(geticon('goto'))
        self.toolBar_edit.addAction(gotoaction)
        
    def _setup_table(self, table):
        table.setTabKeyNavigation(False)
        table.verticalHeader().setDefaultSectionSize(self.rowheight)
        table.setShowGrid(False)
        table.verticalHeader().hide()
        table.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        table.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)

    def setupHeaderTextview(self):
        self.header_diff_format = QtGui.QTextCharFormat()
        self.header_diff_format.setFont(self._font)
        self.header_diff_format.setFontWeight(bold)
        self.header_diff_format.setForeground(Qt.black)
        self.header_diff_format.setBackground(Qt.gray)

    def on_filled(self):
        # called the first time the model is filled, so we select
        # the first available revision
        tv = self.tableView_revisions
        if self._reload_rev is not None:
            torev = self._reload_rev
            self._reload_rev = None
            try:
                tv.goto(torev)
                self.tableView_filelist.selectFile(self._reload_file)
                self._reload_file = None
                return
            except IndexError:
                pass
        tv.setCurrentIndex(tv.model().index(0, 0))

    def revision_activated(self, rev=None):
        """
        Callback called when a revision is double-clicked in the revisions table
        """
        if rev is None:
            rev = self.tableView_revisions.current_rev
        self._manifestdlg = ManifestDialog(self.repo, rev)
        self._manifestdlg.show()

    def updateToRevision(self, rev):
        opts = {}
        dlg = UpdateDialog(rev, self.repo, opts=opts)
        dlg.show()
        self._updatedlg = dlg

    def file_displayed(self, filename):
        self.actionPrevDiff.setEnabled(False)
        connect(self.textview_status, SIGNAL('filled'),
                lambda self=self: self.actionNextDiff.setEnabled(self.textview_status.fileMode() \
                                                                 and self.textview_status.nDiffs()))

    def revision_selected(self, rev):
        """
        Callback called when a revision is selected in the revisions table
        """
        if self.repomodel.graph:
            ctx = self.repomodel.repo.changectx(rev)
            self.textview_status.setContext(ctx)
            self.textview_header.displayRevision(ctx)
            self.filelistmodel.setSelectedRev(ctx)
            if len(self.filelistmodel):
                self.tableView_filelist.selectRow(0)

    def goto(self, rev):
        if len(self.tableView_revisions.model().graph):
            self.tableView_revisions.goto(rev)
        else:
            # store rev to show once it's available (when graph
            # filling is still running)
            self._reload_rev = rev
            
    def _getrepomtime(self):
        """Return the last modification time for the repo"""
        watchedfiles = [(self.repo.root, ".hg", "store", "00changelog.i"),
                        (self.repo.root, ".hg", "dirstate")]
        watchedfiles = [os.path.join(*wf) for wf in watchedfiles]
        mtime = [os.path.getmtime(wf) for wf in watchedfiles \
                 if os.path.isfile(wf)]
        if mtime:
            return max(mtime)
        # humm, directory has probably been deleted, exiting...
        self.close()

    def reload(self):
        """Reload the repository"""
        self._reload_rev = self.tableView_revisions.current_rev
        self._reload_file = self.tableView_filelist.currentFile()
        self.repo = hg.repository(self.repo.ui, self.repo.root)
        self._repodate = self._getrepomtime()
        self.setupBranchCombo()
        self.setupModels()
        # XXX workaround: see refreshRevisionTable method 
        self.refreshRevisionTable(sender=self)

    #@timeit
    def refreshRevisionTable(self, *args, **kw):
        """Starts the process of filling the HgModel"""
        branch = self.branch_comboBox.currentText()
        branch = str(branch)
        startrev = str(self.startrev_entry.text()).strip()
        if not startrev:
            startrev = None
        # XXX workaround: self.sender() may provoque a core dump if
        # this method is called directly (not via a connected signal);
        # the 'sender' keyword is a way to discrimimne that the method
        # has been called directly (thus caller MUST set this kw arg)
        sender = kw.get('sender') or self.sender()
        if sender is self.startrev_follow_action and startrev is None:
            return
        startrev = self.repo.changectx(startrev).rev()
        follow = self.startrev_follow_action.isChecked()
        self.revscompl_model.setStringList(self.repo.tags().keys())

        self.repomodel.setRepo(self.repo, branch=branch, fromhead=startrev,
                               follow=follow)

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
        w = HelpDialog(self.repo, self)
        w.show()
        w.raise_()
        w.activateWindow()

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
        for n in self.splitternames:
            s.setValue(wb + n, getattr(self, n).saveState())

def run(ui, *pats, **opts):
    from tortoisehg.hgqt import setup_font_substitutions
    setup_font_substitutions()

    repo = None
    root = paths.find_root()
    if root:
        repo = hg.repository(ui, path=root)
    return Workbench(repo)

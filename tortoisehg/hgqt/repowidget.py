# -*- coding: iso-8859-1 -*-
#!/usr/bin/env python
# repowidget.py - TortoiseHg repository widget
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
# Copyright (C) 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

import os

from PyQt4 import QtCore, QtGui

from mercurial import hg

from tortoisehg.util.util import has_closed_branch_support

from tortoisehg.hgqt.i18n import _

from tortoisehg.hgqt import icon as geticon
from tortoisehg.hgqt.repomodel import HgRepoListModel
from tortoisehg.hgqt.update import UpdateDialog
from tortoisehg.hgqt import cmdui
from tortoisehg.hgqt.config import HgConfig
from tortoisehg.hgqt.manifestdialog import ManifestDialog

from repoview import HgRepoView
from commit import CommitWidget
from revdetailswidget import RevDetailsWidget


Qt = QtCore.Qt
connect = QtCore.QObject.connect
SIGNAL = QtCore.SIGNAL


class RepoWidget(QtGui.QWidget):

    showMessageSignal = QtCore.pyqtSignal(str)
    switchToSignal = QtCore.pyqtSignal(QtGui.QWidget)

    def __init__(self, repo):
        self.repo = repo
        self._closed_branch_supp = has_closed_branch_support(self.repo)

        # these are used to know where to go after a reload
        self._reload_rev = '.'

        self._loading = True
        self._scanForRepoChanges = True

        self.splitternames = []

        QtGui.QWidget.__init__(self)
        
        self.load_config()

        self.setupUi()
        self.disab_shortcuts = []

        self.currentMessage = ''

        self.createActions()

        connect(self.repoview, SIGNAL('showMessage'), self.showMessage)

#        self.revdisplay.commitsignal.connect(self.commit)

        self.setupModels()
        self.setupRevisionTable()

        self._repodate = self._getrepomtime()
        self._watchrepotimer = self.startTimer(500)

        self.restoreSettings()

    def setupUi(self):
        SP = QtGui.QSizePolicy

        self.hbox = QtGui.QHBoxLayout(self)
        self.hbox.setSpacing(0)
        self.hbox.setMargin(0)

        self.revisions_splitter = QtGui.QSplitter(self)
        self.splitternames.append('revisions_splitter')
        self.revisions_splitter.setOrientation(Qt.Vertical)

        self.repoview = HgRepoView(self.revisions_splitter)
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(1)
        sp.setHeightForWidth(self.repoview.sizePolicy().hasHeightForWidth())
        self.repoview.setSizePolicy(sp)
        self.repoview.setFrameShape(QtGui.QFrame.StyledPanel)

        self.stackedWidget = QtGui.QStackedWidget(self.revisions_splitter)

        self.revDetailsWidget = RevDetailsWidget(self.repo, self.repoview)
        self.stackedWidget.addWidget(self.revDetailsWidget)

        pats = {}
        opts = {}
        self.commitWidget = CommitWidget(pats, opts, root=self.repo.root)
        self.stackedWidget.addWidget(self.commitWidget)

        self.hbox.addWidget(self.revisions_splitter)

    def load_config(self):
        cfg = HgConfig(self.repo.ui)
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
        self.hidefinddelay = cfg.getHideFindDelay()
        return cfg

    def reponame(self):
        return os.path.basename(self.repo.root)

    def showMessage(self, msg):
        self.currentMessage = msg
        if self.isVisible():
            self.showMessageSignal.emit(msg)

    def showEvent(self, event):
        QtGui.QWidget.showEvent(self, event)
        self.showMessageSignal.emit(self.currentMessage)

    def commit(self, action='commit'):
        pass

    def timerEvent(self, event):
        if event.timerId() == self._watchrepotimer:
            if not self._scanForRepoChanges or self.loading():
                return
            mtime = self._getrepomtime()
            if mtime > self._repodate:
                self.showMessage(_("Repository has been modified "
                                   "(reloading is recommended)"))

    def loading(self):
        return self._loading

    def loaded(self):
        reponame = os.path.basename(self.repo.root)
        self._repodate = self._getrepomtime()
        self._loading = False

    def createActions(self):
        self.actionActivateRev = QtGui.QAction('Activate rev.', self)
        self.actionActivateRev.setShortcuts([Qt.SHIFT+Qt.Key_Return, Qt.SHIFT+Qt.Key_Enter])
        connect(self.actionActivateRev, SIGNAL('triggered()'),
                self.revision_activated)
        self.addAction(self.actionActivateRev)
        self.disab_shortcuts.append(self.actionActivateRev)

    def back(self):
        self.repoview.back()

    def forward(self):
        self.repoview.forward()

    def setMode(self, mode):
        self.revDetailsWidget.setMode(mode)

    def getMode(self):
        return self.revDetailsWidget.getMode()

    def setAnnotate(self, ann):
        self.revDetailsWidget.setAnnotate(ann)

    def getAnnotate(self):
        return self.revDetailsWidget.getAnnotate()

    def nextDiff(self):
        self.revDetailsWidget.nextDiff()

    def prevDiff(self):
        self.revDetailsWidget.prevDiff()

    def create_models(self):
        self.repomodel = HgRepoListModel(self.repo)
        connect(self.repomodel, SIGNAL('filled'), self.on_filled)
        connect(self.repomodel, SIGNAL('loaded'), self.loaded)
        connect(self.repomodel, SIGNAL('showMessage'),
                self.showMessage, Qt.QueuedConnection)

    def setupModels(self):
        self.create_models()
        self.repoview.setModel(self.repomodel)
        self.revDetailsWidget.setupModels(self.repomodel)

    def setupRevisionTable(self):
        view = self.repoview
        view.installEventFilter(self)
        connect(view, SIGNAL('revisionSelected'), self.revision_selected)
        connect(view, SIGNAL('revisionActivated'), self.revision_activated)
        connect(view, SIGNAL('updateToRevision'), self.updateToRevision)
        #self.attachQuickBar(view.goto_toolbar)
        gotoaction = view.goto_toolbar.toggleViewAction()
        gotoaction.setIcon(geticon('goto'))
        #self.toolBar_edit.addAction(gotoaction)

    def on_filled(self):
        tv = self.repoview
        if self._reload_rev is not None:
            try:
                tv.goto(self._reload_rev)
                self.revDetailsWidget.on_filled()
                return
            except IndexError:
                pass
        else:
            tv.setCurrentIndex(tv.model().index(0, 0))

    def revision_activated(self, rev=None):
        """
        Callback called when a revision is double-clicked in the revisions table
        """
        if rev is None:
            rev = self.repoview.current_rev
        self._manifestdlg = ManifestDialog(self.repo, rev)
        self._manifestdlg.show()

    def setScanForRepoChanges(self, enable):
        saved = self._scanForRepoChanges
        self._scanForRepoChanges = enable
        return saved

    def updateToRevision(self, rev):
        saved = self.setScanForRepoChanges(False)
        opts = { 'clean':False }
        dlg = UpdateDialog(rev, self.repo, self, opts=opts)
        self._updatedlg = dlg
        def quit(status):
            if status == 0:
                self.reload()  # TODO: implement something less drastic than a full reload
            self.setScanForRepoChanges(saved)
        dlg.quitsignal.connect(quit)
        dlg.show()

    def revision_selected(self, rev):
        """
        Callback called when a revision is selected in the revisions table
        """
        if self.repomodel.graph:
            ctx = self.repomodel.repo.changectx(rev)
            if ctx.rev() is None:
                # working copy
                curridx = 1
            else:
                self.revDetailsWidget.revision_selected(rev)
                curridx = 0
            self.stackedWidget.setCurrentIndex(curridx)

    def goto(self, rev):
        if len(self.repoview.model().graph):
            self.repoview.goto(rev)
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

    def reload(self, rev=None):
        """Reload the repository"""
        if rev == None:
            self._reload_rev = self.repoview.current_rev
        else:
            self._reload_rev = rev
        self._loading = True
        self.repo = hg.repository(self.repo.ui, self.repo.root)
        self._repodate = self._getrepomtime()
        self.setupModels()
        self.commitWidget.stwidget.refreshWctx()
        self.revDetailsWidget.reload(rev)

    def setRepomodel(self, branch):
        self.repomodel.setRepo(self.repo, branch=branch)

    def filterbranch(self):
        return self.repomodel.branch()

    def okToContinue(self):
        return True

    def switchTo(self):
        self.switchToSignal.emit(self)

    def storeSettings(self):
        s = QtCore.QSettings()
        wb = "RepoWidget/"
        for n in self.splitternames:
            s.setValue(wb + n, getattr(self, n).saveState())
        self.revDetailsWidget.storeSettings()

    def restoreSettings(self):
        s = QtCore.QSettings()
        wb = "RepoWidget/"
        for n in self.splitternames:
            getattr(self, n).restoreState(s.value(wb + n).toByteArray())
        expanded = s.value(wb + 'revpanel.expanded', True).toBool()
        self.revDetailsWidget.restoreSettings()

    def closeRepoWidget(self):
        '''returns False if close should be aborted'''
        if not self.okToContinue():
            return False
        if self.isVisible():
            # assuming here that there is at most one RepoWidget visible
            self.storeSettings()
        return True

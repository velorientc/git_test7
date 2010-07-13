# -*- coding: iso-8859-1 -*-
#!/usr/bin/env python
# repowidget.py - TortoiseHg repository widget
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
# Copyright (C) 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

import binascii
import os

from mercurial import hg

from tortoisehg.hgqt.i18n import _

from tortoisehg.hgqt.qtlib import geticon, getfont
from tortoisehg.hgqt.repomodel import HgRepoListModel
from tortoisehg.hgqt import cmdui, update, tag, manifestdialog, backout, merge
from tortoisehg.hgqt import hgemail

from repoview import HgRepoView
from revdetailswidget import RevDetailsWidget

from PyQt4.QtCore import *
from PyQt4.QtGui import *

connect = QObject.connect


class RepoWidget(QWidget):

    showMessageSignal = pyqtSignal(str)
    switchToSignal = pyqtSignal(QWidget)

    def __init__(self, repo, workbench):
        self.repo = repo
        self.workbench = workbench
        self.revDetailsStackedWidget = workbench.revDetailsStackedWidget
        self._reload_rev = '.' # select working parent at startup
        self._scanForRepoChanges = True
        self.disab_shortcuts = []
        self.currentMessage = ''

        QWidget.__init__(self)
        
        self.load_config()
        self.setupUi()
        self.createActions()

        connect(self.repoview, SIGNAL('showMessage'), self.showMessage)

        self.setupModels()
        self.setupRevisionTable()

        self._repodate = self._getrepomtime()
        self._watchrepotimer = self.startTimer(500)

        self.restoreSettings()

    def setupUi(self):
        SP = QSizePolicy

        self.hbox = QHBoxLayout(self)
        self.hbox.setSpacing(0)
        self.hbox.setMargin(0)

        self.repoview = HgRepoView(self.workbench)
        self.hbox.addWidget(self.repoview)
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(1)
        sp.setHeightForWidth(self.repoview.sizePolicy().hasHeightForWidth())
        self.repoview.setSizePolicy(sp)
        self.repoview.setFrameShape(QFrame.StyledPanel)

        w = RevDetailsWidget(self.repo, self.repoview)
        self.revDetailsStackedWidget.addWidget(w)
        w.revisionLinkClicked.connect(self.goto)
        self.revDetailsWidget = w

    def load_config(self):
        self._font = getfont(self.repo.ui, 'fontlog')
        self.rowheight = 8
        self.users, self.aliases = [], []
        self.hidefinddelay = False

    def reponame(self):
        return os.path.basename(self.repo.root)

    def showMessage(self, msg):
        self.currentMessage = msg
        if self.isVisible():
            self.showMessageSignal.emit(msg)

    def showEvent(self, event):
        QWidget.showEvent(self, event)
        self.showMessageSignal.emit(self.currentMessage)

    def timerEvent(self, event):
        if event.timerId() == self._watchrepotimer:
            if not self._scanForRepoChanges:
                return
            mtime = self._getrepomtime()
            if mtime > self._repodate:
                self.showMessage(_("Repository has been modified "
                                   "(reloading is recommended)"))

    def createActions(self):
        self.actionActivateRev = QAction('Activate rev.', self)
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
        self.updateActions()

    def setAnnotate(self, ann):
        self.revDetailsWidget.setAnnotate(ann)

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
        connect(view, SIGNAL('mergeWithRevision'), self.mergeWithRevision)
        connect(view, SIGNAL('tagToRevision'), self.tagToRevision)
        connect(view, SIGNAL('backoutToRevision'), self.backoutToRevision)
        connect(view, SIGNAL('emailRevision'), self.emailRevision)
        connect(view, SIGNAL('copyHash'), self.copyHash)
        #self.attachQuickBar(view.goto_toolbar)
        gotoaction = view.goto_toolbar.toggleViewAction()
        gotoaction.setIcon(geticon('goto'))
        #self.toolBar_edit.addAction(gotoaction)

    def on_filled(self):
        'initial batch of revisions loaded'
        self.repoview.resizeColumns()
        self.loaded()

    def loaded(self):
        'all revisions loaded (graph generator completed)'
        self._repodate = self._getrepomtime()
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
        if rev is None:
            rev = self.repoview.current_rev
        self._manifestdlg = manifestdialog.ManifestDialog(self.repo, rev)
        self._manifestdlg.show()

    def setScanForRepoChanges(self, enable):
        saved = self._scanForRepoChanges
        self._scanForRepoChanges = enable
        return saved

    def updateToRevision(self, rev):
        saved = self.setScanForRepoChanges(False)
        dlg = update.UpdateDialog(rev, self.repo, self)
        self._updatedlg = dlg
        def cmdfinished(status):
            if status == 0:
                self.reload()  # TODO: implement something less drastic than a full reload
            self.setScanForRepoChanges(saved)
        dlg.cmdfinished.connect(cmdfinished)
        dlg.show()

    def mergeWithRevision(self, rev):
        saved = self.setScanForRepoChanges(False)
        dlg = merge.MergeDialog(rev, self.repo, self)
        def finished(ret):
            self.setScanForRepoChanges(saved)
        dlg.finished.connect(finished)
        def invalidated():
            self.reload() # TODO: implement something less drastic than a full reload
        dlg.repoInvalidated.connect(invalidated)
        dlg.show()

    def tagToRevision(self, rev):
        saved = self.setScanForRepoChanges(False)
        dlg = tag.TagDialog(self.repo, rev=str(rev), parent=self)
        def finished(ret):
            self.setScanForRepoChanges(saved)
        dlg.finished.connect(finished)
        def invalidated():
            self.reload() # TODO: implement something less drastic than a full reload
        dlg.repoInvalidated.connect(invalidated)
        dlg.show()

    def backoutToRevision(self, rev):
        saved = self.setScanForRepoChanges(False)
        dlg = backout.BackoutDialog(self.repo, str(rev), self)
        def finished(ret):
            self.setScanForRepoChanges(saved)
        dlg.finished.connect(finished)
        def invalidated():
            self.reload() # TODO: implement something less drastic than a full reload
        dlg.repoInvalidated.connect(invalidated)
        dlg.show()

    def emailRevision(self, rev):
        dlg = hgemail.EmailDialog(self.repo.ui, self.repo, [str(rev)], self)
        dlg.show()

    def copyHash(self, rev):
        clip = QApplication.clipboard()
        clip.setText(binascii.hexlify(self.repo[rev].node()))

    def revision_selected(self, rev):
        if self.workbench.getCurentRepoRoot() != self.repo.root:
            return
        if self.repomodel.graph is None:
            return
        ctx = self.repomodel.repo.changectx(rev)
        if ctx.rev() is None:
            self.workbench.workingCopySelected()
        else:
            self.revDetailsWidget.revision_selected(rev)
            self.workbench.revisionSelected()
        self.revDetailsStackedWidget.setCurrentWidget(self.revDetailsWidget)
        self.updateActions()

    def goto(self, rev):
        rev = str(rev)
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
        'Initiate a refresh of the repo model'
        if rev == None:
            self._reload_rev = self.repoview.current_rev
        else:
            self._reload_rev = rev
        self.repo = hg.repository(self.repo.ui, self.repo.root)
        self._repodate = self._getrepomtime()
        self.setupModels()
        cw = self.getCommitWidget()
        if cw:
            cw.stwidget.refreshWctx()
        self.revDetailsWidget.reload(rev)

    def getCommitWidget(self):
        return self.workbench.getCommitWidget(self.repo.root)

    def setRepomodel(self, branch):
        self.repomodel.setRepo(self.repo, branch=branch)

    def filterbranch(self):
        return self.repomodel.branch()

    def okToContinue(self):
        cw = self.getCommitWidget()
        if cw:
            return cw.canExit()
        return True

    def switchTo(self):
        self.switchToSignal.emit(self)

    def switchedTo(self):
        self.revDetailsStackedWidget.setCurrentWidget(self.revDetailsWidget)
        self.updateActions()

    def updateActions(self):
        mode = self.revDetailsWidget.getMode()
        wb = self.workbench
        enable = self.repoview.current_rev is not None
        wb.actionDiffMode.setEnabled(enable)
        wb.actionDiffMode.setChecked(mode == 'diff')
        ann = self.revDetailsWidget.getAnnotate()
        wb.actionAnnMode.setChecked(ann)
        wb.actionAnnMode.setEnabled(enable and mode != 'diff')
        wb.actionNextDiff.setEnabled(enable and mode != 'diff')
        wb.actionPrevDiff.setEnabled(enable and mode != 'diff')
        self.repoview.updateActions()

    def storeSettings(self):
        self.revDetailsWidget.storeSettings()

    def restoreSettings(self):
        self.revDetailsWidget.restoreSettings()

    def closeRepoWidget(self):
        '''returns False if close should be aborted'''
        if not self.okToContinue():
            return False
        if self.isVisible():
            # assuming here that there is at most one RepoWidget visible
            self.storeSettings()
        self.revDetailsStackedWidget.removeWidget(self.revDetailsWidget)
        s = QSettings()
        cw = self.getCommitWidget()
        if cw:
            cw.storeConfigs(s)
        return True

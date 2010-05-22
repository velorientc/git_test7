# -*- coding: iso-8859-1 -*-
#!/usr/bin/env python
# repowidget.py - TortoiseHg repository widget
#
# Copyright (C) 2007-2010 Logilab. All rights reserved.
# Copyright (C) 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

import sys, os
import re

from PyQt4 import QtCore, QtGui, Qsci

from mercurial import ui, hg
from mercurial import util

from tortoisehg.util.util import tounicode, has_closed_branch_support
from tortoisehg.util.util import rootpath, find_repository

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.graph import diff as revdiff
from tortoisehg.hgqt.decorators import timeit

from tortoisehg.hgqt import icon as geticon
from tortoisehg.hgqt.repomodel import HgRepoListModel
from tortoisehg.hgqt.filelistmodel import HgFileListModel
from tortoisehg.hgqt.filedialogs import FileLogDialog, FileDiffDialog
from tortoisehg.hgqt.manifestdialog import ManifestDialog
from tortoisehg.hgqt.update import UpdateDialog
from tortoisehg.hgqt import cmdui, csinfo, qtlib
from tortoisehg.hgqt.config import HgConfig

from revdisplay import RevMessage
from filelistview import HgFileListView
from fileview import HgFileView
from repoview import HgRepoView

from tortoisehg.util import paths, hglib

from mercurial.error import RepoError


Qt = QtCore.Qt
bold = QtGui.QFont.Bold
connect = QtCore.QObject.connect
SIGNAL = QtCore.SIGNAL


class RepoWidget(QtGui.QWidget):

    showMessageSignal = QtCore.pyqtSignal(str)
    switchToSignal = QtCore.pyqtSignal(QtGui.QWidget)

    def __init__(self, repo):
        self.repo = repo
        self._closed_branch_supp = has_closed_branch_support(self.repo)

        # these are used to know where to go after a reload
        self._reload_rev = None
        self._reload_file = None
        self._loading = True
        self._scanForRepoChanges = True

        QtGui.QWidget.__init__(self)
        
        self.load_config()

        self.setupUi()
        self.disab_shortcuts = []

        self.currentMessage = ''

        self.createActions()

        def label_func(widget, item):
            if item == 'cset':
                return _('Changeset:')
            elif item == 'parents':
                return _('Parent:')
            elif item == 'children':
                return _('Child:')
            elif item == 'patch':
                return _('Patch:')
            raise csinfo.UnknownItem(item)
        def revid_markup(revid, **kargs):
            opts = dict(family='monospace', size='9pt')
            opts.update(kargs)
            return qtlib.markup(revid, **opts)
        def data_func(widget, item, ctx):
            def summary_line(desc):
                desc = desc.replace('\0', '').split('\n')[0]
                return hglib.tounicode(desc[:80])
            def revline_data(ctx, hl=False, branch=None):
                if isinstance(ctx, basestring):
                    return ctx
                desc = ctx.description()
                return (str(ctx.rev()), str(ctx), summary_line(desc), hl, branch)
            if item == 'cset':
                return revline_data(ctx)
            elif item == 'branch':
                value = hglib.tounicode(ctx.branch())
                return value != 'default' and value or None
            elif item == 'parents':
                # TODO: need to put 'diff to other' checkbox
                #pindex = self.diff_other_parent() and 1 or 0
                pindex = 0 # always show diff with first parent
                pctxs = ctx.parents()
                parents = []
                for pctx in pctxs:
                    highlight = len(pctxs) == 2 and pctx == pctxs[pindex]
                    branch = None
                    if hasattr(pctx, 'branch') and pctx.branch() != ctx.branch():
                        branch = pctx.branch()
                    parents.append(revline_data(pctx, highlight, branch))
                return parents
            elif item == 'children':
                children = []
                for cctx in ctx.children():
                    branch = None
                    if hasattr(cctx, 'branch') and cctx.branch() != ctx.branch():
                        branch = cctx.branch()
                    children.append(revline_data(cctx, branch=branch))
                return children
            elif item in ('transplant', 'p4', 'svn'):
                ts = widget.get_data(item, usepreset=True)
                if not ts:
                    return None
                try:
                    tctx = self.repo[ts]
                    return revline_data(tctx)
                except (error.LookupError, error.RepoLookupError, error.RepoError):
                    return ts
            elif item == 'patch':
                if hasattr(ctx, '_patchname'):
                    desc = ctx.description()
                    return (ctx._patchname, str(ctx), summary_line(desc))
                return None
            raise csinfo.UnknownItem(item)
        def markup_func(widget, item, value):
            def link_markup(revnum, revid, enable=True):
                mrevid = revid_markup(revid)
                if not enable:
                    return '%s (%s)' % (revnum, mrevid)
                link = 'cset://%s:%s' % (revnum, revid)
                return '<a href="%s">%s (%s)</a>' % (link, revnum, mrevid)
            def revline_markup(revnum, revid, summary, highlight=None,
                               branch=None, link=True):
                def branch_markup(branch):
                    opts = dict(fg='black', bg='#aaffaa')
                    return qtlib.markup(' %s ' % branch, **opts)
                summary = qtlib.markup(summary)
                if branch:
                    branch = branch_markup(branch)
                if revid:
                    rev = link_markup(revnum, revid, link)
                    if branch:
                        return '%s %s %s' % (rev, branch, summary)
                    return '%s %s' % (rev, summary)
                else:
                    revnum = qtlib.markup(revnum)
                    if branch:
                        return '%s - %s %s' % (revnum, branch, summary)
                    return '%s - %s' % (revnum, summary)
            if item in ('cset', 'transplant', 'patch', 'p4', 'svn'):
                link = item != 'cset'
                if isinstance(value, basestring):
                    return revid_markup(value)
                return revline_markup(link=link, *value)
            elif item in ('parents', 'children'):
                csets = []
                for cset in value:
                    if isinstance(cset, basestring):
                        csets.append(revid_markup(cset))
                    else:
                        csets.append(revline_markup(*cset))
                return csets
            raise csinfo.UnknownItem(item)

        custom = csinfo.custom(data=data_func, label=label_func,
                               markup=markup_func)
        style = csinfo.panelstyle(contents=('cset', 'branch', 'user',
                       'dateage', 'parents', 'children', 'tags', 'transplant',
                       'p4', 'svn'), selectable=True, expandable=True)
        self.revpanel = csinfo.create(self.repo, style=style, custom=custom)
        def activated(url):
            if url.startsWith('cset://'):
                rev = url[7:].split(':')[0]
                self.repoview.goto(rev)
        self.revpanel.linkActivated.connect(activated)
        self.cset_and_file_details_layout.insertWidget(0, self.revpanel)

        self.fileview.setFont(self._font)
        connect(self.fileview, SIGNAL('showMessage'), self.showMessage)
        connect(self.repoview, SIGNAL('showMessage'), self.showMessage)

#        self.revdisplay.commitsignal.connect(self.commit)

        connect(self.message, SIGNAL('revisionSelected'), self.repoview.goto)

        # setup tables and views
        connect(self.fileview, SIGNAL('fileDisplayed'),
                self.file_displayed)
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
        self.revisions_splitter.setOrientation(QtCore.Qt.Vertical)

        self.repoview = HgRepoView(self.revisions_splitter)
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(1)
        sp.setHeightForWidth(self.repoview.sizePolicy().hasHeightForWidth())
        self.repoview.setSizePolicy(sp)
        self.repoview.setFrameShape(QtGui.QFrame.StyledPanel)

        self.revisionDetailsWidget = QtGui.QFrame(self.revisions_splitter)
        sp = SP(SP.Preferred, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.revisionDetailsWidget.sizePolicy().hasHeightForWidth())
        self.revisionDetailsWidget.setSizePolicy(sp)
        self.revisionDetailsWidget.setFrameShape(QtGui.QFrame.NoFrame)
        self.revisionDetailsWidget.setFrameShadow(QtGui.QFrame.Plain)

        self.revisiondetails_layout = QtGui.QVBoxLayout(self.revisionDetailsWidget)
        self.revisiondetails_layout.setSpacing(0)
        self.revisiondetails_layout.setMargin(0)

        self.filelist_splitter = QtGui.QSplitter(self.revisionDetailsWidget)
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.filelist_splitter.sizePolicy().hasHeightForWidth())
        self.filelist_splitter.setSizePolicy(sp)
        self.filelist_splitter.setOrientation(QtCore.Qt.Horizontal)
        self.filelist_splitter.setChildrenCollapsible(False)

        self.tableView_filelist = HgFileListView(self.filelist_splitter)

        self.cset_and_file_details_frame = QtGui.QFrame(self.filelist_splitter)
        sp = SP(SP.Preferred, SP.Preferred)
        sp.setHorizontalStretch(1)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(
            self.cset_and_file_details_frame.sizePolicy().hasHeightForWidth())
        self.cset_and_file_details_frame.setSizePolicy(sp)
        self.cset_and_file_details_frame.setFrameShape(QtGui.QFrame.NoFrame)

        vbox = QtGui.QVBoxLayout(self.cset_and_file_details_frame)
        vbox.setSpacing(0)
        vbox.setSizeConstraint(QtGui.QLayout.SetDefaultConstraint)
        vbox.setMargin(0)
        self.cset_and_file_details_layout = vbox

        self.message_splitter = QtGui.QSplitter(self.cset_and_file_details_frame)
        sp = SP(SP.Preferred, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.message_splitter.sizePolicy().hasHeightForWidth())
        self.message_splitter.setSizePolicy(sp)
        self.message_splitter.setMinimumSize(QtCore.QSize(50, 50))
        self.message_splitter.setFrameShape(QtGui.QFrame.NoFrame)
        self.message_splitter.setLineWidth(0)
        self.message_splitter.setMidLineWidth(0)
        self.message_splitter.setOrientation(QtCore.Qt.Vertical)
        self.message_splitter.setOpaqueResize(True)
        self.message = RevMessage(self.message_splitter)

        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.message.sizePolicy().hasHeightForWidth())
        self.message.setSizePolicy(sp)
        self.message.setMinimumSize(QtCore.QSize(0, 0))
        font = QtGui.QFont()
        font.setFamily("Courier")
        font.setPointSize(9)
        self.message.setFont(font)

        self.fileview = HgFileView(self.message_splitter)
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(1)
        sp.setHeightForWidth(self.fileview.sizePolicy().hasHeightForWidth())
        self.fileview.setSizePolicy(sp)
        self.fileview.setMinimumSize(QtCore.QSize(0, 0))

        self.cset_and_file_details_layout.addWidget(self.message_splitter)
        self.revisiondetails_layout.addWidget(self.filelist_splitter)
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
        args = [str(action)]
        args += ['-v', '-m', self.message.text()]
        dlg = cmdui.Dialog(args)
        if action == 'commit':
            dlg.setWindowTitle(_('Commit'))
        elif action == 'qrefresh':
            dlg.setWindowTitle(_('QRefresh'))
        if dlg.exec_():
            self.message.setSaved()
            self.message.clear()
            self.reload('tip')

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
        # navigate in file viewer
        self.actionNextLine = QtGui.QAction('Next line', self)
        self.actionNextLine.setShortcut(Qt.SHIFT + Qt.Key_Down)
        connect(self.actionNextLine, SIGNAL('triggered()'),
                self.fileview.nextLine)
        self.addAction(self.actionNextLine)
        self.actionPrevLine = QtGui.QAction('Prev line', self)
        self.actionPrevLine.setShortcut(Qt.SHIFT + Qt.Key_Up)
        connect(self.actionPrevLine, SIGNAL('triggered()'),
                self.fileview.prevLine)
        self.addAction(self.actionPrevLine)
        self.actionNextCol = QtGui.QAction('Next column', self)
        self.actionNextCol.setShortcut(Qt.SHIFT + Qt.Key_Right)
        connect(self.actionNextCol, SIGNAL('triggered()'),
                self.fileview.nextCol)
        self.addAction(self.actionNextCol)
        self.actionPrevCol = QtGui.QAction('Prev column', self)
        self.actionPrevCol.setShortcut(Qt.SHIFT + Qt.Key_Left)
        connect(self.actionPrevCol, SIGNAL('triggered()'),
                self.fileview.prevCol)
        self.addAction(self.actionPrevCol)

        # Activate file (file diff navigator)
        self.actionActivateFile = QtGui.QAction('Activate file', self)

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

    def back(self):
        self.repoview.back()

    def forward(self):
        self.repoview.forward()

    def setMode(self, mode):
        self.fileview.setMode(mode)

    def getMode(self):
        return self.fileview.getMode()

    def setAnnotate(self, ann):
        self.fileview.setAnnotate(ann)

    def getAnnotate(self):
        return self.fileview.getAnnotate()

    def nextDiff(self):
        notlast = self.fileview.nextDiff()
        self.actionNextDiff.setEnabled(self.fileview.fileMode() and notlast and self.fileview.nDiffs())
        self.actionPrevDiff.setEnabled(self.fileview.fileMode() and self.fileview.nDiffs())

    def prevDiff(self):
        notfirst = self.fileview.prevDiff()
        self.actionPrevDiff.setEnabled(self.fileview.fileMode() and notfirst and self.fileview.nDiffs())
        self.actionNextDiff.setEnabled(self.fileview.fileMode() and self.fileview.nDiffs())

    def create_models(self):
        self.repomodel = HgRepoListModel(self.repo)
        connect(self.repomodel, SIGNAL('filled'),
                self.on_filled)
        connect(self.repomodel, SIGNAL('loaded'),
                self.loaded)
        connect(self.repomodel, SIGNAL('showMessage'),
                self.showMessage, Qt.QueuedConnection)

        self.filelistmodel = HgFileListModel(self.repo)

    def setupModels(self):
        self.create_models()
        self.repoview.setModel(self.repomodel)
        self.tableView_filelist.setModel(self.filelistmodel)
        self.fileview.setModel(self.repomodel)
        #self.find_toolbar.setModel(self.repomodel)

        filetable = self.tableView_filelist
        connect(filetable, SIGNAL('fileSelected'),
                self.fileview.displayFile)
#        connect(self.fileview, SIGNAL('revForDiffChanged'),
#                self.revdisplay.setDiffRevision)

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

    def _setup_table(self, table):
        table.setTabKeyNavigation(False)
        table.verticalHeader().setDefaultSectionSize(self.rowheight)
        table.setShowGrid(False)
        table.verticalHeader().hide()
        table.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        table.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)

    def on_filled(self):
        tv = self.repoview
        if self._reload_rev is not None:
            try:
                tv.goto(self._reload_rev)
                self.tableView_filelist.selectFile(self._reload_file)
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

    def file_displayed(self, filename):
        #self.actionPrevDiff.setEnabled(False)
        pass

    def revision_selected(self, rev):
        """
        Callback called when a revision is selected in the revisions table
        """
        if self.repomodel.graph:
            ctx = self.repomodel.repo.changectx(rev)
            self.fileview.setContext(ctx)
            self.revpanel.update(ctx.rev())
            self.message.displayRevision(ctx, None)
            self.filelistmodel.setSelectedRev(ctx)
            if len(self.filelistmodel):
                self.tableView_filelist.selectRow(0)

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
        self._reload_file = self.tableView_filelist.currentFile()
        self.repo = hg.repository(self.repo.ui, self.repo.root)
        self._repodate = self._getrepomtime()
        self.setupModels()

    def setRepomodel(self, branch):
        self.repomodel.setRepo(self.repo, branch=branch)

    def filterbranch(self):
        return self.repomodel.branch()

    def okToContinue(self):
        if self.message.isSaved():
            res = True
        else:
            self.switchTo()
            MB = QtGui.QMessageBox
            prompt = _("The message text for '%s' has not been saved.")
            mb = MB(MB.Warning, _("Unsaved Change Message"),
                    prompt % self.reponame(), MB.Discard | MB.Cancel, self)
            mb.setInformativeText(_("Discard changes and close anyway?"))
            mb.setDefaultButton(MB.Cancel)
            ret = mb.exec_()
            if ret == MB.Cancel:
                res = False
            else:
                res = True
        return res

    def switchTo(self):
        self.switchToSignal.emit(self)

    def storeSettings(self):
        s = QtCore.QSettings()
        wb = "RepoWidget/"
        for n in self.splitternames:
            s.setValue(wb + n, getattr(self, n).saveState())
        s.setValue(wb + 'revpanel.expanded', self.revpanel.is_expanded())

    def restoreSettings(self):
        s = QtCore.QSettings()
        wb = "RepoWidget/"
        self.splitternames = []
        sn = ('revisions', 'filelist', 'message')
        for n in sn:
            n += '_splitter'
            self.splitternames.append(n)
            getattr(self, n).restoreState(s.value(wb + n).toByteArray())
        expanded = s.value(wb + 'revpanel.expanded', True).toBool()
        self.revpanel.set_expanded(expanded)

    def closeRepoWidget(self):
        '''returns False if close should be aborted'''
        if not self.okToContinue():
            return False
        if self.isVisible():
            # assuming here that there is at most one RepoWidget visible
            self.storeSettings()
        return True

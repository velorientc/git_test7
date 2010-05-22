# commit.py - TortoiseHg's commit widget and standalone dialog
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import hg, ui, cmdutil, util, dispatch

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.hgqt.i18n import _
from tortoisehg.util import hglib, shlib, paths

from tortoisehg.hgqt import qtlib, status, cmdui, branchop

# Technical Debt for CommitWidget
#  qrefresh support
#  threaded / wrapped commit (need a CmdRunner equivalent)
#  qctlib decode failure dialog (ask for retry locale, suggest HGENCODING)
#  Need a unicode-to-UTF8 function
#  +1 / -1 head indication (not as important with workbench integration)
#  recent committers history
#  pushafterci, autoincludes list
#  use date option
#  qnew/shelve-patch creation dialog (in another file)
#  reflow / auto-wrap / message format checks / paste filenames
#  spell check / tab completion
#  in-memory patching / committing chunk selected files

class CommitWidget(QWidget):
    'A widget that encompasses a StatusWidget and commit extras'
    loadBegin = pyqtSignal()
    loadComplete = pyqtSignal()
    errorMessage = pyqtSignal(QString)
    commitComplete = pyqtSignal()

    def __init__(self, pats, opts, root=None, parent=None):
        QWidget.__init__(self, parent)

        self.opts = opts # user, date
        self.stwidget = status.StatusWidget(pats, opts, root, self)
        self.connect(self.stwidget, SIGNAL('errorMessage'),
                     lambda m: self.emit(SIGNAL('errorMessage'), m))
        self.connect(self.stwidget, SIGNAL('loadBegin'),
                     lambda: self.emit(SIGNAL('loadBegin')))
        self.connect(self.stwidget, SIGNAL('loadComplete'),
                     lambda: self.emit(SIGNAL('loadComplete')))
        self.msghistory = []

        SP = QSizePolicy

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stwidget)
        self.setLayout(layout)
        form = QFormLayout()
        form.setContentsMargins(3, 9, 9, 0)
        repo = self.stwidget.repo
        wctx = repo[None]

        usercombo = QComboBox()
        try:
            if opts.get('user'):
                usercombo.addItem(hglib.tounicode(opts['user']))
            usercombo.addItem(hglib.tounicode(wctx.user()))
        except util.Abort:
            import socket
            user = '%s@%s' % (util.getuser(), socket.getfqdn())
            usercombo.addItem(hglib.tounicode(user))

        usercombo.setEditable(True)
        form.addRow(_('Changeset:'), QLabel(_('Working Copy')))
        form.addRow(_('User:'), usercombo)
        form.addRow(_('Parent:'), QLabel('Description of ' + str(repo['.'])))
        frame = QFrame()
        frame.setLayout(form)
        frame.setFrameStyle(QFrame.NoFrame)

        vbox = QVBoxLayout()
        vbox.addWidget(frame, 0)
        vbox.setMargin(0)
        hbox = QHBoxLayout()

        branchbutton = QPushButton(_('Branch: ') +
                                   hglib.tounicode(wctx.branch()))
        branchbutton.pressed.connect(self.branchOp)
        self.branchbutton = branchbutton
        self.branchop = None
        hbox.addWidget(branchbutton)

        msgcombo = MessageHistoryCombo()
        self.connect(msgcombo, SIGNAL('activated(int)'), self.msgSelected)
        hbox.addWidget(msgcombo, 1)
        hbox.addSpacing(9)
        vbox.addLayout(hbox, 0)
        msgte = QTextEdit()
        msgte.setAcceptRichText(False)
        vbox.addWidget(msgte, 1)
        upperframe = QFrame()
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(1)
        upperframe.setSizePolicy(sp)
        upperframe.setLayout(vbox)

        self.split = QSplitter(Qt.Vertical)
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(1)
        sp.setVerticalStretch(0)
        self.split.setSizePolicy(sp)
        # Add our widgets to the top of our splitter
        self.split.addWidget(upperframe)
        # Add status widget document frame below our splitter
        # this reparents the docf from the status splitter
        self.split.addWidget(self.stwidget.docf)

        # add our splitter where the docf used to be
        self.stwidget.split.addWidget(self.split)
        msgte.setFocus()
        # Yuki's Mockup: http://bitbucket.org/kuy/thg-qt/wiki/Home
        self.usercombo = usercombo
        self.msgte = msgte
        self.msgcombo = msgcombo

    def restoreState(self, data):
        return self.stwidget.restoreState(data)

    def saveState(self):
        return self.stwidget.saveState()

    def branchOp(self):
        d = branchop.BranchOpDialog(self.stwidget.repo, self.branchop)
        if d.exec_() == QDialog.Accepted:
            self.branchop = d.branchop
            wctx = self.stwidget.repo[None]
            cur = hglib.tounicode(wctx.branch())
            if self.branchop is None:
                title = _('Branch: ') + cur
            elif self.branchop == False:
                title = _('Close Branch: ') + cur
            else:
                title = _('New Branch: ') + self.branchop
            self.branchbutton.setText(title)

    def canUndo(self):
        'Returns undo description or None if not valid'
        repo = self.stwidget.repo
        if os.path.exists(self.repo.sjoin('undo')):
            try:
                args = self.repo.opener('undo.desc', 'r').read().splitlines()
                if args[1] != 'commit':
                    return None
                return _('Rollback commit to revision %d') % (int(args[0]) - 1)
            except (IOError, IndexError, ValueError):
                pass
        return None

    def rollback(self):
        msg = self.canUndo()
        if not msg:
            return
        d = QMessageBox.question(self, _('Confirm Undo'), msg,
                                 QMessageBox.Ok | QMessageBox.Cancel)
        if d != QMessageBox.Ok:
            return
        repo = self.stwidget.repo
        repo.rollback()
        self.stwidget.refreshWctx()
        QTimer.singleShot(500, lambda: shlib.shell_notify([repo.root]))

    def getMessage(self):
        text = self.msgte.toPlainText()
        try:
            text = hglib.fromunicode(text, 'strict')
        except UnicodeEncodeError:
            pass # TODO
        return text

    def msgSelected(self, index):
        doc = self.msgte.document()
        if not doc.isEmpty() and doc.isModified():
            d = QMessageBox.question(self, _('Confirm Discard Message'),
                        _('Discard current commit message?'),
                        QMessageBox.Ok | QMessageBox.Cancel)
            if d != QMessageBox.Ok:
                return
        self.msgte.setPlainText(self.msghistory[index])
        self.msgte.document().setModified(False)
        self.msgte.moveCursor(QTextCursor.End)
        self.msgte.setFocus()

    def canExit(self):
        # Usually safe to exit, since we're saving messages implicitly
        # We'll ask the user for confirmation later, if they have any
        # files partially selected.
        return True
    
    def loadConfigs(self, s):
        'Load history, etc, from QSettings instance'
        repo = self.stwidget.repo
        repoid = str(repo[0])
        # message history is stored in unicode
        self.split.restoreState(s.value('commit/split').toByteArray())
        self.msghistory = list(s.value('commit/history-'+repoid).toStringList())
        self.msghistory = [s for s in self.msghistory if s]
        self.msgcombo.reset(self.msghistory)
        try:
            curmsg = repo.opener('cur-message.txt').read()
            self.msgte.setPlainText(hglib.fromunicode(curmsg))
            self.msgte.document().setModified(False)
            self.msgte.moveCursor(QTextCursor.End)
        except EnvironmentError:
            pass

    def storeConfigs(self, s):
        'Save history, etc, in QSettings instance'
        repo = self.stwidget.repo
        repoid = str(repo[0])
        s.setValue('commit/history-'+repoid, self.msghistory)
        s.setValue('commit/split', self.split.saveState())
        try:
            # current message is stored in local encoding
            repo.opener('cur-message.txt', 'w').write(self.getMessage())
        except EnvironmentError:
            pass

    def addMessageToHistory(self):
        umsg = self.msgte.toPlainText()
        if not umsg:
            return
        if umsg in self.msghistory:
            self.msghistory.remove(umsg)
        self.msghistory.insert(0, umsg)
        self.msghistory = self.msghistory[:10]
        self.msgcombo.reset(self.msghistory)

    def commit(self):
        repo = self.stwidget.repo
        ui = repo.ui
        cwd = os.getcwd()
        try:
            os.chdir(repo.root)
            return self._commit(repo, ui)
        finally:
            os.chdir(cwd)

    def _commit(self, repo, ui):
        msg = self.getMessage()
        if not msg:
            qtlib.WarningMsgBox(_('Nothing Commited'),
                                _('Please enter commit message'),
                                parent=self)
            self.msgte.setFocus()
            return
        repo = self.stwidget.repo
        if self.branchop is None:
            brcmd = []
        elif self.branchop == False:
            brcmd = ['--close-branch']
        else:
            brcmd = []
            # TODO: Need a unicode-to-UTF8 function
            newbranch = hglib.fromunicode(self.branchop)
            if newbranch in repo.branchtags():
                # response: 0=Yes, 1=No, 2=Cancel
                pb = [p.branch() for p in repo.parents()]
                if self.nextbranch in pb:
                    resp = 0
                else:
                    rev = repo[newbranch].rev()
                    resp = qtlib.CustomPrompt(_('Confirm Branch Change'),
                        _('Named branch "%s" already exists, '
                          'last used in revision %d\n'
                          'Yes\t- Make commit restarting this named branch\n'
                          'No\t- Make commit without changing branch\n'
                          'Cancel\t- Cancel this commit') % (newbranch, rev),
                          self, (_('&Yes'), _('&No'), _('&Cancel')), 2, 2).run()
            else:
                resp = qtlib.CustomPrompt(_('Confirm New Branch'),
                    _('Create new named branch "%s" with this commit?\n'
                      'Yes\t- Start new branch with this commit\n'
                      'No\t- Make commit without branch change\n'
                      'Cancel\t- Cancel this commit') % newbranch,
                    self, (_('&Yes'), _('&No'), _('&Cancel')), 2, 2).run()
            if resp == 0:
                repo.dirstate.setbranch(newbranch)
            elif resp == 2:
                return
        files = self.stwidget.getChecked('MAR?!S')
        if not (files or brcmd or repo[None].branch() != repo['.'].branch()):
            qtlib.WarningMsgBox(_('No files checked'),
                                _('No modified files checkmarked for commit'),
                                parent=self)
            self.stwidget.tv.setFocus()
            return
        user = self.usercombo.currentText()
        try:
            user = hglib.fromunicode(user, 'strict')
        except UnicodeEncodeError:
            pass # TODO
        if not user:
            qtlib.WarningMsgBox(_('Username required'),
                                _('Please enter a username'),
                                parent=self)
            self.usercombo.setFocus()
            return
        checkedUnknowns = self.stwidget.getChecked('?I')
        if checkedUnknowns:
            res = qtlib.CustomPrompt(
                    _('Confirm Add'),
                    _('Add checked untracked files?'), self,
                    (_('&Ok'), ('&Cancel')), 0, 1,
                    checkedUnknowns).run()
            if res == 0:
                dispatch._dispatch(ui, ['add'] + checkedUnknowns)
            else:
                return
        checkedMissing = self.stwidget.getChecked('!')
        if checkedMissing:
            res = qtlib.CustomPrompt(
                    _('Confirm Remove'),
                    _('Remove checked deleted files?'), self,
                    (_('&Ok'), ('&Cancel')), 0, 1,
                    checkedMissing).run()
            if res == 0:
                dispatch._dispatch(ui, ['remove'] + checkedMissing)
            else:
                return
        cmdline = ['commit', '--user', user, '--message', msg]
        cmdline += brcmd + files
        ret = dispatch._dispatch(ui, cmdline)
        if not ret:
            self.addMessageToHistory()
            self.msgte.clear()
            self.msgte.document().setModified(False)
            self.emit(SIGNAL('commitComplete'))
            return True
        else:
            return False

class MessageHistoryCombo(QComboBox):
    def __init__(self, parent=None):
        QComboBox.__init__(self, parent)
        self.reset([])

    def reset(self, msgs):
        self.clear()
        self.addItem(_('Recent commit messages...'))
        self.loaded = False
        self.msgs = msgs

    def showPopup(self):
        if not self.loaded:
            self.clear()
            for s in self.msgs:
                self.addItem(s.split('\n', 1)[0][:70])
            self.loaded = True
        QComboBox.showPopup(self)

# Technical Debt for standalone tool
#   add a toolbar for refresh, undo, etc
#   add a statusbar and simple progressbar

class CommitDialog(QDialog):
    'Standalone commit tool, a wrapper for CommitWidget'
    def __init__(self, pats, opts, parent=None):
        QDialog.__init__(self, parent)
        self.pats = pats
        self.opts = opts

        layout = QVBoxLayout()
        self.setLayout(layout)

        commit = CommitWidget(pats, opts, None, self)
        layout.addWidget(commit, 1)
        layout.setContentsMargins(0, 0, 0, 0)

        bbl = QHBoxLayout()
        layout.addLayout(bbl)
        layout.addSpacing(9)
        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        self.connect(bb, SIGNAL("accepted()"), self, SLOT("accept()"))
        self.connect(bb, SIGNAL("rejected()"), self, SLOT("reject()"))
        bb.button(BB.Ok).setDefault(True)
        bb.button(BB.Ok).setText('Commit')
        bbl.addWidget(bb, alignment=Qt.AlignRight)
        bbl.addSpacing(9)
        self.bb = bb

        s = QSettings()
        commit.restoreState(s.value('commit/state').toByteArray())
        self.restoreGeometry(s.value('commit/geom').toByteArray())
        commit.loadConfigs(s)
        commit.errorMessage.connect(self.errorMessage)

        name = hglib.get_reponame(commit.stwidget.repo)
        self.setWindowTitle('%s - commit' % name)
        self.commit = commit

    def errorMessage(self, msg):
        print msg

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() == Qt.ControlModifier:
                self.accept()  # Ctrl+Enter
            return
        elif event.key() == Qt.Key_Escape:
            self.reject()
            return
        return super(QDialog, self).keyPressEvent(event)

    def accept(self):
        if self.commit.commit():
            self.reject()
        else:
            self.commit.stwidget.refreshWctx()

    def reject(self):
        if self.commit.canExit():
            s = QSettings()
            s.setValue('commit/state', self.commit.saveState())
            s.setValue('commit/geom', self.saveGeometry())
            self.commit.storeConfigs(s)
            QDialog.reject(self)

def run(ui, *pats, **opts):
    return CommitDialog(hglib.canonpaths(pats), opts)

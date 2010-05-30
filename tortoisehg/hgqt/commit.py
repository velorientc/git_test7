# commit.py - TortoiseHg's commit widget and standalone dialog
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import hg, ui, cmdutil, util, dispatch, error
from mercurial.node import short as short_hex

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.hgqt.i18n import _
from tortoisehg.util import hglib, shlib, paths
from tortoisehg.util.util import format_desc

from tortoisehg.hgqt import qtlib, status, cmdui, branchop

# Technical Debt for CommitWidget
#  auto-wrap / paste filenames
#  qrefresh support
#  refresh parent changeset descriptions after refresh
#  threaded / wrapped commit (need a CmdRunner equivalent)
#  qtlib decode failure dialog (ask for retry locale, suggest HGENCODING)
#  Need a unicode-to-UTF8 function
#  +1 / -1 head indication (not as important with workbench integration)
#  recent committers history
#  pushafterci, autoincludes list
#  qnew/shelve-patch creation dialog (in another file)
#  spell check / tab completion
#  in-memory patching / committing chunk selected files

class CommitWidget(QWidget):
    'A widget that encompasses a StatusWidget and commit extras'
    loadBegin = pyqtSignal()
    loadComplete = pyqtSignal()
    errorMessage = pyqtSignal(QString)
    commitComplete = pyqtSignal()

    def __init__(self, pats, opts, root=None, parent=None, hidebutton=False):
        QWidget.__init__(self, parent)

        self.opts = opts # user, date
        self.stwidget = status.StatusWidget(pats, opts, root, self)
        self.connect(self.stwidget, SIGNAL('errorMessage'),
                     lambda m: self.emit(SIGNAL('errorMessage'), m))
        self.stwidget.loadBegin.connect(lambda: self.loadBegin.emit())
        self.stwidget.loadComplete.connect(lambda: self.loadComplete.emit())
        self.msghistory = []

        SP = QSizePolicy

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stwidget)
        self.setLayout(layout)
        form = QFormLayout()
        form.setVerticalSpacing(3)
        form.setContentsMargins(3, 0, 9, 0)
        repo = self.stwidget.repo
        wctx = repo[None]

        usercombo = QComboBox()
        usercombo.setEditable(True)
        try:
            if opts.get('user'):
                usercombo.addItem(hglib.tounicode(opts['user']))
            usercombo.addItem(hglib.tounicode(wctx.user()))
        except util.Abort:
            pass

        self.commitButton = b = QPushButton(_('Commit'))
        if hidebutton:
            b.hide()
        w = QWidget()
        l = QHBoxLayout()
        l.setMargin(0)
        w.setLayout(l)
        l.addWidget(QLabel(_('Working Copy')))
        l.addStretch(1)
        l.addWidget(b)
        b.clicked.connect(self.commit)

        def addrow(s, w):
            form.addRow("<b>%s</b>" % s, w)
        addrow(('Changeset:'), w)
        for ctx in repo.parents():
            desc = format_desc(ctx.description(), 80)
            fmt =  "<span style='font-family:Courier'>%s(%s)</span> %s"
            ptext = fmt % (ctx.rev(), short_hex(ctx.node()), desc)
            addrow(_('Parent:'), QLabel(ptext))
        addrow(_('User:'), usercombo)
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
        msgte = QPlainTextEdit()
        msgte.textChanged.connect(self.msgChanged)
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

    def msgChanged(self):
        text = self.msgte.toPlainText()
        self.commitButton.setEnabled(not text.isEmpty())
        sumlen, maxlen = self.getLengths()
        if not sumlen and not maxlen:
            self.msgte.setExtraSelections([])
            return
        pos, nextpos = 0, 0
        sels = []
        for i, line in enumerate(text.split('\n')):
            pos = nextpos
            length = len(line)
            nextpos += length + 1 # include \n
            if i == 0 and (length < sumlen or not sumlen):
                continue
            elif i == 1 and (length == 0 or not sumlen):
                continue
            elif i > 1 and (length < maxlen or not maxlen):
                continue
            sel = QTextEdit.ExtraSelection()
            sel.bgcolor = QColor('red')
            sel.format.setBackground(sel.bgcolor)
            sel.format.setProperty(QTextFormat.FullWidthSelection, True)
            sel.cursor = QTextCursor(self.msgte.document())
            sel.cursor.setPosition(pos)
            sel.cursor.clearSelection()
            sels.append(sel)
        self.msgte.setExtraSelections(sels)

    def msgReflow(self):
        'User pressed Alt-Q'
        if QApplication.focusWidget() != self.msgte:
            return

        sumlen, maxlen = self.getLengths()
        if not maxlen:
            return

        # In QtTextDocument land, a block is a sequence of text ending
        # in (and including) a carriage return.  Aka, a line of text.
        block = self.msgte.textCursor().block()
        while block.length() and block.previous().length() > 1:
            block = block.previous()
        begin = block.position()

        while block.length() and block.next().length() > 1:
            block = block.next()
        end = block.position() + block.length() - 1

        # select the contiguous lines of text under the cursor
        cursor = self.msgte.textCursor()
        cursor.setPosition(begin, QTextCursor.MoveAnchor)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        sentence = cursor.selection().toPlainText().simplified()

        parts = sentence.split(' ', QString.SkipEmptyParts)
        lines = QStringList()
        line = QStringList()
        partslen = 0
        for part in parts:
            if partslen + len(line) + len(part) + 1 > maxlen:
                if line:
                    lines.append(line.join(' '))
                line, partslen = QStringList(), 0
            line.append(part)
            partslen += len(part)
        if line:
            lines.append(line.join(' '))
        reflow = lines.join('\n')

        # Replace selection with new sentence
        cursor.insertText(reflow)

    def getLengths(self):
        repo = self.stwidget.repo
        try:
            sumlen = int(repo.ui.config('tortoisehg', 'summarylen', 0))
            maxlen = int(repo.ui.config('tortoisehg', 'messagewrap', 0))
        except (TypeError, ValueError):
            sumlen, maxlen = 0, 0
        return sumlen, maxlen

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
        if os.path.exists(repo.sjoin('undo')):
            try:
                args = repo.opener('undo.desc', 'r').read().splitlines()
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

    def _commit(self, repo, _ui):
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
            try:
                QMessageBox.information(self, _('Please enter a username'),
                        _('You must identify yourself to Mercurial'),
                        QMessageBox.Ok)
                from tortoisehg.hgqt.settings import SettingsDialog
                dlg = SettingsDialog(False, focus='ui.username')
                dlg.exec_()
                user = ui.ui().username()
                if user:
                    self.usercombo.addItem(hglib.tounicode(user))
            except util.Abort:
                pass
            if not user:
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
                dispatch._dispatch(_ui, ['add'] + checkedUnknowns)
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
                dispatch._dispatch(_ui, ['remove'] + checkedMissing)
            else:
                return
        try:
            date = self.opts.get('date')
            if date:
                util.parsedate(date)
                dcmd = ['--date', date]
            else:
                dcmd = []
        except error.Abort, e:
            self.emit(SIGNAL('errorMessage'), hglib.tounicode(str(e)))
            dcmd = []

        cmdline = ['commit', '--user', user, '--message', msg]
        cmdline += dcmd + brcmd + files
        ret = dispatch._dispatch(_ui, cmdline)
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
#   add a toolbar for refresh
#   add a statusbar and simple progressbar

class CommitDialog(QDialog):
    'Standalone commit tool, a wrapper for CommitWidget'
    def __init__(self, pats, opts, parent=None):
        QDialog.__init__(self, parent)
        self.pats = pats
        self.opts = opts

        layout = QVBoxLayout()
        self.setLayout(layout)

        commit = CommitWidget(pats, opts, None, self, hidebutton=True)
        layout.addWidget(commit, 1)
        layout.setContentsMargins(0, 6, 0, 0)

        bbl = QHBoxLayout()
        layout.addLayout(bbl)
        layout.addSpacing(9)
        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel|BB.Discard)
        self.connect(bb, SIGNAL("accepted()"), self, SLOT("accept()"))
        self.connect(bb, SIGNAL("rejected()"), self, SLOT("reject()"))
        bb.button(BB.Cancel).setDefault(False)
        bb.button(BB.Discard).setDefault(False)
        bb.button(BB.Discard).setText('Undo')
        bb.button(BB.Discard).clicked.connect(commit.rollback)
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
        commit.loadComplete.connect(self.updateUndo)

    def updateUndo(self):
        BB = QDialogButtonBox
        undomsg = self.commit.canUndo()
        if undomsg:
            self.bb.button(BB.Discard).setEnabled(True)
            self.bb.button(BB.Discard).setToolTip(undomsg)
        else:
            self.bb.button(BB.Discard).setEnabled(False)
            self.bb.button(BB.Discard).setToolTip('')

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
        elif event.modifiers() == Qt.AltModifier and event.key() == Qt.Key_Q:
            self.commit.msgReflow()
        elif event.modifiers() == Qt.MetaModifier and event.key() == Qt.Key_R:
            # On a Mac, CTRL-R will also reflow (until someone fixes this)
            self.commit.msgReflow()
        return super(QDialog, self).keyPressEvent(event)

    def accept(self):
        if self.commit.commit():
            repo = self.commit.stwidget.repo
            if repo.ui.configbool('tortoisehg', 'closeci'):
                self.reject()
                return
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

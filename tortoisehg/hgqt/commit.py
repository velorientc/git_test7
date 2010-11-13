# commit.py - TortoiseHg's commit widget and standalone dialog
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import ui, util, error

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qsci import QsciScintilla, QsciAPIs, QsciLexerMakefile

from tortoisehg.hgqt.i18n import _
from tortoisehg.util import hglib, shlib, wconfig

from tortoisehg.hgqt import qtlib, qscilib, status, cmdui, branchop, revpanel
from tortoisehg.hgqt.sync import loadIniFile

# Technical Debt for CommitWidget
#  qtlib decode failure dialog (ask for retry locale, suggest HGENCODING)
#  Need a unicode-to-UTF8 function
#  spell check / tab completion
#  in-memory patching / committing chunk selected files

class MessageEntry(qscilib.Scintilla):
    reflowPressed = pyqtSignal()

    def __init__(self, parent=None):
        super(MessageEntry, self).__init__(parent)
        self.setEdgeColor(QColor('LightSalmon'))
        self.setEdgeMode(QsciScintilla.EdgeLine)
        self.setWrapMode(QsciScintilla.WrapNone)
        self.setReadOnly(False)
        self.setMarginWidth(1, 0)
        self.setFont(qtlib.getfont('fontcomment').font())
        self.setCaretWidth(10)
        self.setCaretLineBackgroundColor(QColor("#e6fff0"))
        self.setCaretLineVisible(True)
        self.setAutoIndent(True)
        self.setAutoCompletionThreshold(2)
        self.setAutoCompletionSource(QsciScintilla.AcsAPIs)
        self.setAutoCompletionFillupsEnabled(True)
        self.setLexer(QsciLexerMakefile(self))
        self.lexer().setFont(qtlib.getfont('fontcomment').font())
        self.setMatchedBraceBackgroundColor(Qt.yellow)
        self.setIndentationsUseTabs(False)
        self.setBraceMatching(QsciScintilla.SloppyBraceMatch)
        #self.setIndentationGuidesBackgroundColor(QColor("#e6e6de"))
        #self.setFolding(QsciScintilla.BoxedFoldStyle)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setWrapMode(QsciScintilla.WrapCharacter)

    def refresh(self, repo):
        self.setEdgeColumn(repo.summarylen)
        self.setIndentationWidth(repo.tabwidth)
        self.setTabWidth(repo.tabwidth)
        if repo.wsvisible == 'Visible':
            self.setWhitespaceVisibility(QsciScintilla.WsVisible)
        elif repo.wsvisible == 'VisibleAfterIndent':
            self.setWhitespaceVisibility(QsciScintilla.WsVisibleAfterIndent)
        else:
            self.setWhitespaceVisibility(QsciScintilla.WsInvisible)

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_E:
            self.reflowPressed.emit()
        super(MessageEntry, self).keyPressEvent(event)

class CommitWidget(QWidget):
    'A widget that encompasses a StatusWidget and commit extras'
    commitButtonName = pyqtSignal(QString)
    linkActivated = pyqtSignal(QString)
    showMessage = pyqtSignal(unicode)
    commitComplete = pyqtSignal()

    progress = pyqtSignal(QString, object, QString, QString, object)
    output = pyqtSignal(QString, QString)
    makeLogVisible = pyqtSignal(bool)

    def __init__(self, pats, opts, root=None, embedded=False, parent=None):
        QWidget.__init__(self, parent=parent)

        self.opts = opts # user, date
        self.stwidget = status.StatusWidget(pats, opts, root, self)
        self.stwidget.showMessage.connect(self.showMessage)
        self.stwidget.progress.connect(self.progress)
        self.stwidget.linkActivated.connect(self.linkActivated)
        self.stwidget.fileDisplayed.connect(self.fileDisplayed)
        self.msghistory = []
        self.qref = False

        self.repo = repo = self.stwidget.repo
        self.runner = cmdui.Runner(_('Commit'), not embedded, self)
        self.runner.output.connect(self.output)
        self.runner.progress.connect(self.progress)
        self.runner.makeLogVisible.connect(self.makeLogVisible)
        self.runner.commandFinished.connect(self.commandFinished)

        repo.configChanged.connect(self.configChanged)
        repo.repositoryChanged.connect(self.repositoryChanged)
        repo.workingBranchChanged.connect(self.workingBranchChanged)

        self.opts['pushafter'] = repo.ui.config('tortoisehg', 'cipushafter', '')
        self.opts['autoinc'] = repo.ui.config('tortoisehg', 'autoinc', '')

        layout = QVBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        layout.addWidget(self.stwidget)
        self.setLayout(layout)

        vbox = QVBoxLayout()
        vbox.setMargin(0)
        vbox.setSpacing(0)
        vbox.setContentsMargins(*(0,)*4)

        hbox = QHBoxLayout()
        hbox.setMargin(0)
        hbox.setContentsMargins(*(0,)*4)
        branchbutton = QPushButton(_('Branch: '))
        branchbutton.pressed.connect(self.branchOp)
        self.branchbutton = branchbutton
        self.branchop = None
        hbox.addWidget(branchbutton)

        self.detailsbutton = QPushButton(_('Details'))
        self.detailsbutton.pressed.connect(self.details)
        hbox.addWidget(self.detailsbutton)

        msgcombo = MessageHistoryCombo()
        msgcombo.activated.connect(self.msgSelected)
        hbox.addWidget(msgcombo, 1)
        hbox.addSpacing(2)
        vbox.addLayout(hbox, 0)
        self.buttonHBox = hbox

        self.pcsinfo = revpanel.ParentWidget(repo)
        vbox.addWidget(self.pcsinfo, 0)

        msgte = MessageEntry(self)
        msgte.reflowPressed.connect(self.reflowPressed)
        msgte.setContextMenuPolicy(Qt.CustomContextMenu)
        msgte.customContextMenuRequested.connect(self.menuRequested)
        msgte.installEventFilter(qscilib.KeyPressInterceptor(self))
        vbox.addWidget(msgte, 1)
        upperframe = QFrame()

        SP = QSizePolicy
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
        self.msgte = msgte
        self.msgcombo = msgcombo

    @pyqtSlot(QString, QString)
    def fileDisplayed(self, wfile, contents):
        'Status widget is displaying a new file'
        if not (wfile and contents):
            return
        wfile = unicode(wfile)
        self._apis = QsciAPIs(self.msgte.lexer())
        tokens = set()
        for e in self.stwidget.getChecked():
            tokens.add(e)
            tokens.add(os.path.basename(e))
        try:
            from pygments.lexers import guess_lexer_for_filename
            from pygments.token import Token
            from pygments.util import ClassNotFound
            try:
                contents = unicode(contents)
                lexer = guess_lexer_for_filename(wfile, contents)
                for tokentype, value in lexer.get_tokens(contents):
                    if tokentype in Token.Name and len(value) > 4:
                        tokens.add(value)
            except ClassNotFound:
                pass
        except ImportError:
            pass
        for n in sorted(list(tokens)):
            self._apis.add(n)
        self._apis.apiPreparationFinished.connect(self.apiPrepFinished)
        self._apis.prepare()

    def apiPrepFinished(self):
        'QsciAPIs has finished parsing displayed file'
        self.msgte.lexer().setAPIs(self._apis)

    def details(self):
        dlg = DetailsDialog(self.opts, self.userhist, self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        if dlg.exec_() == QDialog.Accepted:
            self.opts.update(dlg.outopts)

    def workingBranchChanged(self):
        'Repository has detected a change in .hg/branch'
        self.refresh()

    def repositoryChanged(self):
        'Repository has detected a changelog / dirstate change'
        self.refresh()

    def configChanged(self):
        'Repository is reporting its config files have changed'
        self.refresh()

    def reload(self):
        'User has requested a reload'
        self.repo.thginvalidate()
        self.refresh()
        self.stwidget.refreshWctx() # Trigger reload of working context

    def refresh(self):
        # Update qrefresh mode
        if self.repo.changectx('.').thgmqappliedpatch():
            self.commitButtonName.emit(_('QRefresh'))
            if not self.qref:
                self.initQRefreshMode()
        else:
            self.commitButtonName.emit(_('Commit'))
            if self.qref:
                self.endQRefreshMode()

        self.msgte.refresh(self.repo)

        # Update message list
        self.msgcombo.reset(self.msghistory)

        # Update branch operation button
        cur = hglib.tounicode(self.repo[None].branch())
        if self.branchop is None:
            title = _('Branch: ') + cur
        elif self.branchop == False:
            title = _('Close Branch: ') + cur
        else:
            title = _('New Branch: ') + self.branchop
        self.branchbutton.setText(title)

        # Update parent csinfo widget
        self.pcsinfo.set_revision(None)
        self.pcsinfo.update()

    def initQRefreshMode(self):
        'Working parent is a patch.  Is it refreshable?'
        qtip = self.repo['qtip']
        if qtip != self.repo['.']:
            self.showMessage.emit(_('Cannot refresh non-tip patch'))
            self.commitButtonName.emit(_('N/A'))
            return
        self.opts['user'] = qtip.user()
        self.opts['date'] = hglib.displaytime(qtip.date())
        self.setMessage(hglib.tounicode(qtip.description()))
        self.qref = True

    def endQRefreshMode(self):
        self.setMessage('')
        self.opts['user'] = ''
        self.opts['date'] = ''
        self.qref = False

    def reflowPressed(self):
        'User pressed Control-E, reflow current paragraph'
        line, col = self.msgte.getCursorPosition()
        self.reflowBlock(line)

    def reflowBlock(self, line):
        lines = self.msgte.text().split('\n', QString.KeepEmptyParts)
        if line >= len(lines):
            return None
        if not len(lines[line]) > 1:
            return line+1

        # find boundaries (empty lines or bounds)
        b = line
        while b and len(lines[b-1]) > 1:
            b = b - 1
        e = line
        while e+1 < len(lines) and len(lines[e+1]) > 1:
            e = e + 1
        group = QStringList([lines[l].simplified() for l in xrange(b, e+1)])
        sentence = group.join(' ')
        parts = sentence.split(' ', QString.SkipEmptyParts)

        outlines = QStringList()
        line = QStringList()
        partslen = 0
        for part in parts:
            if partslen + len(line) + len(part) + 1 > self.repo.summarylen:
                if line:
                    outlines.append(line.join(' '))
                line, partslen = QStringList(), 0
            line.append(part)
            partslen += len(part)
        if line:
            outlines.append(line.join(' '))

        self.msgte.beginUndoAction()
        self.msgte.setSelection(b, 0, e+1, 0)
        self.msgte.removeSelectedText()
        self.msgte.insertAt(outlines.join('\n')+'\n', b, 0)
        self.msgte.endUndoAction()
        self.msgte.setCursorPosition(b, 0)
        return b + len(outlines) + 1

    def menuRequested(self, point):
        line = self.msgte.lineAt(point)
        point = self.msgte.mapToGlobal(point)

        def apply():
            line = 0
            while True:
                line = self.reflowBlock(line)
                if line is None:
                    break;
        def paste():
            files = self.stwidget.getChecked()
            self.msgte.insert(', '.join(files))
        def settings():
            from tortoisehg.hgqt.settings import SettingsDialog
            dlg = SettingsDialog(True, focus='tortoisehg.summarylen')
            dlg.exec_()

        menu = self.msgte.createStandardContextMenu()
        menu.addSeparator()
        for name, func in [(_('Paste &Filenames'), paste),
                           (_('App&ly Format'), apply),
                           (_('C&onfigure Format'), settings)]:
            def add(name, func):
                action = menu.addAction(name)
                action.triggered.connect(lambda: func())
            add(name, func)
        return menu.exec_(point)

    def restoreState(self, data):
        return self.stwidget.restoreState(data)

    def saveState(self):
        return self.stwidget.saveState()

    def branchOp(self):
        d = branchop.BranchOpDialog(self.repo, self.branchop, self)
        d.setWindowFlags(Qt.Sheet)
        d.setWindowModality(Qt.WindowModal)
        if d.exec_() == QDialog.Accepted:
            self.branchop = d.branchop
            self.refresh()

    def canUndo(self):
        'Returns undo description or None if not valid'
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
        self.repo.incrementBusyCount()
        self.repo.rollback()
        self.repo.decrementBusyCount()
        self.reload()
        QTimer.singleShot(500, lambda: shlib.shell_notify([self.repo.root]))

    def getMessage(self):
        text = self.msgte.text()
        try:
            text = hglib.fromunicode(text, 'strict')
        except UnicodeEncodeError:
            pass # TODO
        return text

    def msgSelected(self, index):
        if self.msgte.text() and self.msgte.isModified():
            d = QMessageBox.question(self, _('Confirm Discard Message'),
                        _('Discard current commit message?'),
                        QMessageBox.Ok | QMessageBox.Cancel)
            if d != QMessageBox.Ok:
                return
        self.setMessage(self.msghistory[index])
        self.msgte.setFocus()

    def setMessage(self, msg):
        self.msgte.setText(msg)
        lines = self.msgte.lines()
        if lines:
            lines -= 1
            pos = self.msgte.lineLength(lines)
            self.msgte.setCursorPosition(lines, pos)
            self.msgte.ensureLineVisible(lines)
            hs = self.msgte.horizontalScrollBar()
            hs.setSliderPosition(0)
        self.msgte.setModified(False)

    def canExit(self):
        # Usually safe to exit, since we're saving messages implicitly
        # We'll ask the user for confirmation later, if they have any
        # files partially selected.
        return True

    def loadConfigs(self, s):
        'Load history, etc, from QSettings instance'
        repoid = str(self.repo[0])
        # message history is stored in unicode
        self.split.restoreState(s.value('commit/split').toByteArray())
        self.msghistory = list(s.value('commit/history-'+repoid).toStringList())
        self.msghistory = [m for m in self.msghistory if m]
        self.msgcombo.reset(self.msghistory)
        self.userhist = s.value('commit/userhist').toStringList()
        self.userhist = [u for u in self.userhist if u]
        try:
            curmsg = self.repo.opener('last-message.txt').read()
            self.setMessage(hglib.tounicode(curmsg))
        except EnvironmentError:
            pass

    def storeConfigs(self, s):
        'Save history, etc, in QSettings instance'
        repoid = str(self.repo[0])
        s.setValue('commit/history-'+repoid, self.msghistory)
        s.setValue('commit/split', self.split.saveState())
        s.setValue('commit/userhist', self.userhist)
        try:
            if self.qref:
                # don't store patch summary as current working comment
                msg = ''
            else:
                # current message is stored in local encoding
                msg = self.getMessage()
            self.repo.opener('last-message.txt', 'w').write(msg)
        except EnvironmentError:
            pass

    def addMessageToHistory(self):
        umsg = self.msgte.text()
        if not umsg:
            return
        if umsg in self.msghistory:
            self.msghistory.remove(umsg)
        self.msghistory.insert(0, umsg)
        self.msghistory = self.msghistory[:10]

    def addUsernameToHistory(self, user):
        if user in self.userhist:
            self.userhist.remove(user)
        self.userhist.insert(0, user)
        self.userhist = self.userhist[:10]

    def getCurrentUsername(self):
        # 1. Override has highest priority
        user = self.opts.get('user')
        if user:
            return user

        # 2. Read from repository
        try:
            return self.repo.ui.username()
        except error.Abort:
            pass

        # 3. Get a username from the user
        QMessageBox.information(self, _('Please enter a username'),
                    _('You must identify yourself to Mercurial'),
                    QMessageBox.Ok)
        from tortoisehg.hgqt.settings import SettingsDialog
        dlg = SettingsDialog(False, focus='ui.username')
        dlg.exec_()
        self.repo.invalidateui()
        try:
            return self.repo.ui.username()
        except error.Abort:
            return None

    def commit(self):
        repo = self.repo
        msg = self.getMessage()
        if not msg:
            qtlib.WarningMsgBox(_('Nothing Commited'),
                                _('Please enter commit message'),
                                parent=self)
            self.msgte.setFocus()
            return
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
                if newbranch in [p.branch() for p in repo.parents()]:
                    resp = 0
                else:
                    rev = repo[newbranch].rev()
                    resp = qtlib.CustomPrompt(_('Confirm Branch Change'),
                        _('Named branch "%s" already exists, '
                          'last used in revision %d\n'
                          'Yes\t- Make commit restarting this named branch\n'
                          'No\t- Make commit without changing branch\n'
                          'Cancel\t- Cancel this commit') % (newbranch, rev),
                          self, (_('&Yes'), _('&No'), _('Cancel')), 2, 2).run()
            else:
                resp = qtlib.CustomPrompt(_('Confirm New Branch'),
                    _('Create new named branch "%s" with this commit?\n'
                      'Yes\t- Start new branch with this commit\n'
                      'No\t- Make commit without branch change\n'
                      'Cancel\t- Cancel this commit') % newbranch,
                    self, (_('&Yes'), _('&No'), _('Cancel')), 2, 2).run()
            if resp == 0:
                repo.dirstate.setbranch(newbranch)
            elif resp == 2:
                return
        files = self.stwidget.getChecked('MAR?!S')
        if not (files or brcmd or repo[None].branch() != repo['.'].branch() \
                or self.qref):
            qtlib.WarningMsgBox(_('No files checked'),
                                _('No modified files checkmarked for commit'),
                                parent=self)
            self.stwidget.tv.setFocus()
            return
        if len(repo.parents()) > 1:
            files = []

        user = self.getCurrentUsername()
        if not user:
            return
        self.addUsernameToHistory(user)

        commandlines = []

        checkedUnknowns = self.stwidget.getChecked('?I')
        if checkedUnknowns:
            res = qtlib.CustomPrompt(
                    _('Confirm Add'),
                    _('Add checked untracked files?'), self,
                    (_('&OK'), _('Cancel')), 0, 1,
                    checkedUnknowns).run()
            if res == 0:
                cmd = ['add', '--repository', repo.root] + \
                      [repo.wjoin(f) for f in checkedUnknowns]
                commandlines.append(cmd)
            else:
                return
        checkedMissing = self.stwidget.getChecked('!')
        if checkedMissing:
            res = qtlib.CustomPrompt(
                    _('Confirm Remove'),
                    _('Remove checked deleted files?'), self,
                    (_('&OK'), _('Cancel')), 0, 1,
                    checkedMissing).run()
            if res == 0:
                cmd = ['remove', '--repository', repo.root] + \
                      [repo.wjoin(f) for f in checkedMissing]
                commandlines.append(cmd)
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
            self.showMessage.emit(hglib.tounicode(str(e)))
            dcmd = []

        cmdline = ['commit', '--repository', repo.root,
                   '--verbose', '--user', user, '--message', msg]
        if self.qref:
            cmdline[0] = 'qrefresh'
            files = []
        cmdline += dcmd + brcmd + [repo.wjoin(f) for f in files]
        for fname in self.opts.get('autoinc', '').split(','):
            fname = fname.strip()
            if fname:
                cmdline.extend(['--include', fname])

        commandlines.append(cmdline)

        if self.opts.get('pushafter'):
            cmd = ['push', '--repository', repo.root, self.opts['pushafter']]
            commandlines.append(cmd)

        repo.incrementBusyCount()
        self.runner.run(*commandlines)

    def commandFinished(self, ret):
        self.repo.decrementBusyCount()
        if ret == 0:
            self.addMessageToHistory()
            if not self.qref:
                self.msgte.clear()
            self.msgte.setModified(False)
            self.commitComplete.emit()
        self.stwidget.refreshWctx()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() == Qt.ControlModifier:
                self.commit()
            return
        return super(CommitWidget, self).keyPressEvent(event)

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


class DetailsDialog(QDialog):
    'Utility dialog for configuring uncommon settings'
    def __init__(self, opts, userhistory, parent):
        QDialog.__init__(self, parent)
        self.repo = parent.repo

        layout = QVBoxLayout()
        self.setLayout(layout)

        hbox = QHBoxLayout()
        self.usercb = QCheckBox(_('Set username:'))

        usercombo = QComboBox()
        usercombo.setEditable(True)
        usercombo.setEnabled(False)
        self.usercb.toggled.connect(usercombo.setEnabled)

        l = []
        if opts.get('user'):
            val = hglib.tounicode(opts['user'])
            self.usercb.setChecked(True)
            l.append(val)
        try:
            val = hglib.tounicode(self.repo.ui.username())
            l.append(val)
        except util.Abort:
            pass
        for name in userhistory:
            if name not in l:
                l.append(name)
        for name in l:
            usercombo.addItem(name)
        self.usercombo = usercombo

        usersaverepo = QPushButton(_('Save in Repo'))
        usersaverepo.clicked.connect(self.saveInRepo)
        usersaverepo.setEnabled(False)
        self.usercb.toggled.connect(usersaverepo.setEnabled)

        usersaveglobal = QPushButton(_('Save Global'))
        usersaveglobal.clicked.connect(self.saveGlobal)
        usersaveglobal.setEnabled(False)
        self.usercb.toggled.connect(usersaveglobal.setEnabled)

        hbox.addWidget(self.usercb)
        hbox.addWidget(self.usercombo)
        hbox.addWidget(usersaverepo)
        hbox.addWidget(usersaveglobal)
        layout.addLayout(hbox)

        hbox = QHBoxLayout()
        self.datecb = QCheckBox(_('Set Date:'))
        self.datele = QLineEdit()
        self.datele.setEnabled(False)
        self.datecb.toggled.connect(self.datele.setEnabled)
        curdate = QPushButton(_('Update'))
        curdate.setEnabled(False)
        self.datecb.toggled.connect(curdate.setEnabled)
        curdate.clicked.connect( lambda: self.datele.setText(
                hglib.tounicode(hglib.displaytime(util.makedate()))))
        if opts.get('date'):
            self.datele.setText(opts['date'])
            self.datecb.setChecked(True)
        else:
            self.datecb.setChecked(False)
            curdate.clicked.emit(True)

        hbox.addWidget(self.datecb)
        hbox.addWidget(self.datele)
        hbox.addWidget(curdate)
        layout.addLayout(hbox)

        hbox = QHBoxLayout()
        self.pushaftercb = QCheckBox(_('Push After Commit:'))
        self.pushafterle = QLineEdit()
        self.pushafterle.setEnabled(False)
        self.pushaftercb.toggled.connect(self.pushafterle.setEnabled)

        pushaftersave = QPushButton(_('Save in Repo'))
        pushaftersave.clicked.connect(self.savePushAfter)
        pushaftersave.setEnabled(False)
        self.pushaftercb.toggled.connect(pushaftersave.setEnabled)

        if opts.get('pushafter'):
            val = hglib.tounicode(opts['pushafter'])
            self.pushafterle.setText(val)
            self.pushaftercb.setChecked(True)

        hbox.addWidget(self.pushaftercb)
        hbox.addWidget(self.pushafterle)
        hbox.addWidget(pushaftersave)
        layout.addLayout(hbox)

        hbox = QHBoxLayout()
        self.autoinccb = QCheckBox(_('Auto Includes:'))
        self.autoincle = QLineEdit()
        self.autoincle.setEnabled(False)
        self.autoinccb.toggled.connect(self.autoincle.setEnabled)

        autoincsave = QPushButton(_('Save in Repo'))
        autoincsave.clicked.connect(self.saveAutoInc)
        autoincsave.setEnabled(False)
        self.autoinccb.toggled.connect(autoincsave.setEnabled)

        if opts.get('autoinc'):
            val = hglib.tounicode(opts['autoinc'])
            self.autoincle.setText(val)
            self.autoinccb.setChecked(True)

        hbox.addWidget(self.autoinccb)
        hbox.addWidget(self.autoincle)
        hbox.addWidget(autoincsave)
        layout.addLayout(hbox)

        hbox = QHBoxLayout()
        #  qnew/shelve-patch creation dialog (in another file)
        lbl = QLabel(_('New patch (QNew)'))
        self.patchle = QLineEdit()
        self.patchle.returnPressed.connect(self.newPatch)
        createpatch = QPushButton(_('Create'))
        createpatch.clicked.connect(self.newPatch)
        def changed(text):
            createpatch.setEnabled(bool(text))
        self.patchle.textChanged.connect(changed)
        createpatch.setEnabled(False)
        hbox.addWidget(lbl)
        hbox.addWidget(self.patchle)
        hbox.addWidget(createpatch)
        layout.addStretch(10)
        layout.addLayout(hbox)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.bb = bb
        layout.addWidget(bb)

        self.setWindowTitle('%s - commit details' % self.repo.displayname)

    def newPatch(self):
        name = hglib.fromunicode(self.patchle.text())
        # TODO

    def saveInRepo(self):
        fn = os.path.join(self.repo.root, '.hg', 'hgrc')
        self.saveToPath([fn])

    def saveGlobal(self):
        self.saveToPath(util.user_rcpath())

    def saveToPath(self, path):
        fn, cfg = loadIniFile(path, self)
        if not hasattr(cfg, 'write'):
            qtlib.WarningMsgBox(_('Unable to save username'),
                   _('Iniparse must be installed.'), parent=self)
            return
        if fn is None:
            return
        try:
            user = hglib.fromunicode(self.usercombo.currentText())
            if user:
                cfg.set('ui', 'username', user)
            else:
                try:
                    del cfg['ui']['username']
                except KeyError:
                    pass
            wconfig.writefile(cfg, fn)
        except IOError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                hglib.tounicode(e), parent=self)

    def savePushAfter(self):
        path = os.path.join(self.repo.root, '.hg', 'hgrc')
        fn, cfg = loadIniFile([path], self)
        if not hasattr(cfg, 'write'):
            qtlib.WarningMsgBox(_('Unable to save after commit push'),
                   _('Iniparse must be installed.'), parent=self)
            return
        if fn is None:
            return
        try:
            remote = hglib.fromunicode(self.pushafterle.text())
            if remote:
                cfg.set('tortoisehg', 'cipushafter', remote)
            else:
                try:
                    del cfg['tortoisehg']['cipushafter']
                except KeyError:
                    pass
            wconfig.writefile(cfg, fn)
        except IOError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                hglib.tounicode(e), parent=self)

    def saveAutoInc(self):
        path = os.path.join(self.repo.root, '.hg', 'hgrc')
        fn, cfg = loadIniFile([path], self)
        if not hasattr(cfg, 'write'):
            qtlib.WarningMsgBox(_('Unable to save auto include list'),
                   _('Iniparse must be installed.'), parent=self)
            return
        if fn is None:
            return
        try:
            list = hglib.fromunicode(self.autoincle.text())
            if list:
                cfg.set('tortoisehg', 'autoinc', list)
            else:
                try:
                    del cfg['tortoisehg']['autoinc']
                except KeyError:
                    pass
            wconfig.writefile(cfg, fn)
        except IOError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                hglib.tounicode(e), parent=self)

    def accept(self):
        outopts = {}
        if self.datecb.isChecked():
            date = hglib.fromunicode(self.datele.text())
            try:
                util.parsedate(date)
            except error.Abort, e:
                qtlib.WarningMsgBox(_('Invalid date format'),
                                    hglib.tounicode(e), parent=self)
                return
            outopts['date'] = date
        else:
            outopts['date'] = ''

        if self.usercb.isChecked():
            user = hglib.fromunicode(self.usercombo.currentText())
        else:
            user = ''
        outopts['user'] = user
        if not user:
            try:
                self.repo.ui.username()
            except util.Abort, e:
                qtlib.WarningMsgBox(_('No username configured'),
                                    hglib.tounicode(e), parent=self)
                return

        if self.pushaftercb.isChecked():
            remote = hglib.fromunicode(self.pushafterle.text())
            outopts['pushafter'] = remote
        else:
            outopts['pushafter'] = ''

        self.outopts = outopts
        QDialog.accept(self)


class CommitDialog(QDialog):
    'Standalone commit tool, a wrapper for CommitWidget'

    def __init__(self, pats, opts, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowFlags(Qt.Window)
        self.pats = pats
        self.opts = opts

        layout = QVBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setMargin(0)
        self.setLayout(layout)

        commit = CommitWidget(pats, opts, opts.get('root'), False, self)
        layout.addWidget(commit, 1)

        self.statusbar = cmdui.ThgStatusBar(self)
        self.statusbar.setSizeGripEnabled(False)
        commit.showMessage.connect(self.statusbar.showMessage)
        commit.progress.connect(self.statusbar.progress)
        commit.linkActivated.connect(self.linkActivated)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel|BB.Discard)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(BB.Discard).setText('Undo')
        bb.button(BB.Discard).clicked.connect(commit.rollback)
        bb.button(BB.Cancel).setDefault(False)
        bb.button(BB.Discard).setDefault(False)
        bb.button(BB.Ok).setDefault(True)
        self.bb = bb

        hbox = QHBoxLayout()
        hbox.setMargin(0)
        hbox.setContentsMargins(*(0,)*4)
        hbox.addWidget(self.statusbar)
        hbox.addWidget(self.bb)
        layout.addLayout(hbox)

        s = QSettings()
        commit.restoreState(s.value('commit/state').toByteArray())
        self.restoreGeometry(s.value('commit/geom').toByteArray())
        commit.loadConfigs(s)
        commit.repo.repositoryChanged.connect(self.updateUndo)
        commit.commitComplete.connect(self.postcommit)
        commit.commitButtonName.connect(self.setButtonName)

        self.setWindowTitle('%s - commit' % commit.repo.displayname)
        self.commit = commit
        self.commit.reload()
        self.updateUndo()
        self.commit.msgte.setFocus()

    def linkActivated(self, link):
        link = hglib.fromunicode(link)
        if link.startswith('subrepo:'):
            from tortoisehg.hgqt.run import qtrun
            qtrun(run, ui.ui(), root=link[8:])

    def setButtonName(self, name):
        self.bb.button(QDialogButtonBox.Ok).setText(name)

    def updateUndo(self):
        BB = QDialogButtonBox
        undomsg = self.commit.canUndo()
        if undomsg:
            self.bb.button(BB.Discard).setEnabled(True)
            self.bb.button(BB.Discard).setToolTip(undomsg)
        else:
            self.bb.button(BB.Discard).setEnabled(False)
            self.bb.button(BB.Discard).setToolTip('')

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        elif event.matches(QKeySequence.Refresh):
            self.refresh()
        return super(CommitDialog, self).keyPressEvent(event)

    def refresh(self):
        self.updateUndo()
        self.commit.reload()

    def postcommit(self):
        repo = self.commit.stwidget.repo
        if repo.ui.configbool('tortoisehg', 'closeci'):
            self.reject()
            return

    def accept(self):
        self.commit.commit()

    def reject(self):
        if self.commit.canExit():
            s = QSettings()
            s.setValue('commit/state', self.commit.saveState())
            s.setValue('commit/geom', self.saveGeometry())
            self.commit.storeConfigs(s)
            QDialog.reject(self)

def run(ui, *pats, **opts):
    return CommitDialog(hglib.canonpaths(pats), opts)

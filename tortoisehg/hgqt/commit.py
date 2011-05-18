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

# Technical Debt for CommitWidget
#  disable commit button while no message is entered or no files are selected
#  qtlib decode failure dialog (ask for retry locale, suggest HGENCODING)
#  spell check / tab completion
#  in-memory patching / committing chunk selected files

class MessageEntry(qscilib.Scintilla):

    def __init__(self, parent, getCheckedFunc=None):
        super(MessageEntry, self).__init__(parent)
        self.setEdgeColor(QColor('LightSalmon'))
        self.setEdgeMode(QsciScintilla.EdgeLine)
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
        self.lexer().setColor(QColor(Qt.red), QsciLexerMakefile.Error)
        self.setMatchedBraceBackgroundColor(Qt.yellow)
        self.setIndentationsUseTabs(False)
        self.setBraceMatching(QsciScintilla.SloppyBraceMatch)
        #self.setIndentationGuidesBackgroundColor(QColor("#e6e6de"))
        #self.setFolding(QsciScintilla.BoxedFoldStyle)
        # http://www.riverbankcomputing.com/pipermail/qscintilla/2009-February/000461.html
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # default message entry widgets to word wrap, user may override
        self.setWrapMode(QsciScintilla.WrapWord)

        self.getChecked = getCheckedFunc
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menuRequested)

    def menuRequested(self, point):
        line = self.lineAt(point)
        point = self.mapToGlobal(point)

        def apply():
            line = 0
            while True:
                line = self.reflowBlock(line)
                if line is None:
                    break;
        def paste():
            files = self.getChecked()
            self.insert(', '.join(files))
        def settings():
            from tortoisehg.hgqt.settings import SettingsDialog
            dlg = SettingsDialog(True, focus='tortoisehg.summarylen')
            dlg.exec_()

        menu = self.createStandardContextMenu()
        menu.addSeparator()
        if self.getChecked:
            action = menu.addAction(_('Paste &Filenames'))
            action.triggered.connect(paste)
        for name, func in [(_('App&ly Format'), apply),
                           (_('C&onfigure Format'), settings)]:
            def add(name, func):
                action = menu.addAction(name)
                action.triggered.connect(func)
            add(name, func)
        return menu.exec_(point)

    def refresh(self, repo):
        self.setEdgeColumn(repo.summarylen)
        self.setIndentationWidth(repo.tabwidth)
        self.setTabWidth(repo.tabwidth)
        self.summarylen = repo.summarylen

    def reflowBlock(self, line):
        lines = self.text().split('\n', QString.KeepEmptyParts)
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
            if partslen + len(line) + len(part) + 1 > self.summarylen:
                if line:
                    outlines.append(line.join(' '))
                line, partslen = QStringList(), 0
            line.append(part)
            partslen += len(part)
        if line:
            outlines.append(line.join(' '))

        self.beginUndoAction()
        self.setSelection(b, 0, e+1, 0)
        self.removeSelectedText()
        self.insertAt(outlines.join('\n')+'\n', b, 0)
        self.endUndoAction()
        self.setCursorPosition(b, 0)
        return b + len(outlines) + 1

    def moveCursorToEnd(self):
        lines = self.lines()
        if lines:
            lines -= 1
            pos = self.lineLength(lines)
            self.setCursorPosition(lines, pos)
            self.ensureLineVisible(lines)
            self.horizontalScrollBar().setSliderPosition(0)

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_E:
            line, col = self.getCursorPosition()
            self.reflowBlock(line)
        elif event.key() == Qt.Key_Backtab:
            event.accept()
            newev = QKeyEvent(event.type(), Qt.Key_Tab, Qt.ShiftModifier)
            super(MessageEntry, self).keyPressEvent(newev)
        else:
            super(MessageEntry, self).keyPressEvent(event)

class CommitWidget(QWidget):
    'A widget that encompasses a StatusWidget and commit extras'
    commitButtonEnable = pyqtSignal(bool)
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
        self.repo = repo = self.stwidget.repo
        self.runner = cmdui.Runner(not embedded, self)
        self.runner.setTitle(_('Commit', 'window title'))
        self.runner.output.connect(self.output)
        self.runner.progress.connect(self.progress)
        self.runner.makeLogVisible.connect(self.makeLogVisible)
        self.runner.commandFinished.connect(self.commandFinished)

        repo.configChanged.connect(self.configChanged)
        repo.repositoryChanged.connect(self.repositoryChanged)
        repo.workingBranchChanged.connect(self.workingBranchChanged)

        self.opts['pushafter'] = repo.ui.config('tortoisehg', 'cipushafter', '')
        self.opts['autoinc'] = repo.ui.config('tortoisehg', 'autoinc', '')
        self.stwidget.opts['ciexclude'] = repo.ui.config('tortoisehg', 'ciexclude', '')

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
        tbar = QToolBar(_("Commit Dialog Toolbar"), self)
        hbox.addWidget(tbar)

        self.recentMessagesButton = QToolButton(
            text=_('Copy message'),
            popupMode=QToolButton.InstantPopup,
            toolTip=_('Copy one of the recent commit messages'))
        tbar.addWidget(self.recentMessagesButton)
        self.updateRecentMessages()

        self.branchbutton = tbar.addAction(_('Branch: '))
        self.branchbutton.triggered.connect(self.branchOp)
        self.branchop = None

        tbar.addAction(_('Options')).triggered.connect(self.details)
        tbar.setIconSize(QSize(16,16))
        self.stopAction = tbar.addAction(_('Stop'))
        self.stopAction.triggered.connect(self.stop)
        self.stopAction.setIcon(qtlib.geticon('process-stop'))
        self.stopAction.setEnabled(False)

        hbox.addStretch(1)

        vbox.addLayout(hbox, 0)
        self.buttonHBox = hbox

        self.pcsinfo = revpanel.ParentWidget(repo)
        vbox.addWidget(self.pcsinfo, 0)

        msgte = MessageEntry(self, self.stwidget.getChecked)
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
        self.split.setCollapsible(0, False)
        # Add status widget document frame below our splitter
        # this reparents the docf from the status splitter
        self.split.addWidget(self.stwidget.docf)

        # add our splitter where the docf used to be
        self.stwidget.split.addWidget(self.split)
        self.msgte = msgte
        QShortcut(QKeySequence('Ctrl+Return'), self, self.commit).setContext(
                  Qt.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence('Ctrl+Enter'), self, self.commit).setContext(
                  Qt.WidgetWithChildrenShortcut)

    @pyqtSlot(QString, QString)
    def fileDisplayed(self, wfile, contents):
        'Status widget is displaying a new file'
        if not (wfile and contents):
            return
        wfile = unicode(wfile)
        self._apis = QsciAPIs(self.msgte.lexer())
        tokens = set()
        for e in self.stwidget.getChecked():
            e = hglib.tounicode(e)
            tokens.add(e)
            tokens.add(os.path.basename(e))
        tokens.add(wfile)
        tokens.add(os.path.basename(wfile))
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
        dlg.finished.connect(dlg.deleteLater)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        if dlg.exec_() == QDialog.Accepted:
            self.opts.update(dlg.outopts)
            self.refresh()

    def workingBranchChanged(self):
        'Repository has detected a change in .hg/branch'
        self.refresh()

    def repositoryChanged(self):
        'Repository has detected a changelog / dirstate change'
        self.refresh()
        self.stwidget.refreshWctx() # Trigger reload of working context

    def configChanged(self):
        'Repository is reporting its config files have changed'
        self.refresh()

    @pyqtSlot()
    def reload(self):
        'User has requested a reload'
        self.repo.thginvalidate()
        self.refresh()
        self.stwidget.refreshWctx() # Trigger reload of working context

    def refresh(self):
        ispatch = self.repo.changectx('.').thgmqappliedpatch()
        self.commitButtonEnable.emit(not ispatch)
        self.msgte.refresh(self.repo)

        # Update branch operation button
        branchu = hglib.tounicode(self.repo[None].branch())
        if self.branchop is None:
            title = _('Branch: ') + branchu
        elif self.branchop == False:
            title = _('Close Branch: ') + branchu
        else:
            title = _('New Branch: ') + self.branchop
        self.branchbutton.setText(title)

        # Update parent csinfo widget
        self.pcsinfo.set_revision(None)
        self.pcsinfo.update()

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

    def updateRecentMessages(self):
        # Define a menu that lists recent messages
        m = QMenu()
        for s in self.msghistory:
            title = s.split('\n', 1)[0][:70]
            def overwriteMsg(newMsg): return lambda: self.msgSelected(newMsg)
            m.addAction(title).triggered.connect(overwriteMsg(s))
        self.recentMessagesButton.setMenu(m)

    def getMessage(self):
        text = self.msgte.text()
        try:
            text = hglib.fromunicode(text, 'strict')
        except UnicodeEncodeError:
            pass # TODO
        return text

    def msgSelected(self, message):
        if self.msgte.text() and self.msgte.isModified():
            d = QMessageBox.question(self, _('Confirm Discard Message'),
                        _('Discard current commit message?'),
                        QMessageBox.Ok | QMessageBox.Cancel)
            if d != QMessageBox.Ok:
                return
        self.setMessage(message)
        self.msgte.setFocus()

    def setMessage(self, msg):
        self.msgte.setText(msg)
        self.msgte.moveCursorToEnd()
        self.msgte.setModified(False)

    def canExit(self):
        if not self.stwidget.canExit():
            return False
        return not self.runner.core.running()

    def loadSettings(self, s, prefix):
        'Load history, etc, from QSettings instance'
        repoid = str(self.repo[0])
        lpref = prefix + '/commit/' # local settings (splitter, etc)
        gpref = 'commit/'           # global settings (history, etc)
        # message history is stored in unicode
        self.split.restoreState(s.value(lpref+'split').toByteArray())
        self.msgte.loadSettings(s, lpref+'msgte')
        self.stwidget.loadSettings(s, lpref+'status')
        self.msghistory = list(s.value(gpref+'history-'+repoid).toStringList())
        self.msghistory = [unicode(m) for m in self.msghistory if m]
        self.updateRecentMessages()
        self.userhist = s.value(gpref+'userhist').toStringList()
        self.userhist = [u for u in self.userhist if u]
        try:
            curmsg = self.repo.opener('cur-message.txt').read()
            self.setMessage(hglib.tounicode(curmsg))
        except EnvironmentError:
            pass
        try:
            curmsg = self.repo.opener('last-message.txt').read()
            if curmsg:
                self.addMessageToHistory(hglib.tounicode(curmsg))
        except EnvironmentError:
            pass

    def saveSettings(self, s, prefix):
        'Save history, etc, in QSettings instance'
        repoid = str(self.repo[0])
        lpref = prefix + '/commit/'
        gpref = 'commit/'
        s.setValue(lpref+'split', self.split.saveState())
        self.msgte.saveSettings(s, lpref+'msgte')
        self.stwidget.saveSettings(s, lpref+'status')
        s.setValue(gpref+'history-'+repoid, self.msghistory)
        s.setValue(gpref+'userhist', self.userhist)
        try:
            msg = self.getMessage()
            self.repo.opener('cur-message.txt', 'w').write(msg)
        except EnvironmentError:
            pass

    def addMessageToHistory(self, umsg):
        umsg = unicode(umsg)
        if umsg in self.msghistory:
            self.msghistory.remove(umsg)
        self.msghistory.insert(0, umsg)
        self.msghistory = self.msghistory[:10]
        self.updateRecentMessages()

    def addUsernameToHistory(self, user):
        user = hglib.tounicode(user)
        if user in self.userhist:
            self.userhist.remove(user)
        self.userhist.insert(0, user)
        self.userhist = self.userhist[:10]

    def commit(self):
        repo = self.repo
        msg = self.getMessage()
        if not msg:
            qtlib.WarningMsgBox(_('Nothing Commited'),
                                _('Please enter commit message'),
                                parent=self)
            self.msgte.setFocus()
            return

        commandlines = []

        brcmd = []
        newbranch = False
        if self.branchop is None:
            newbranch = repo[None].branch() != repo['.'].branch()
        elif self.branchop == False:
            brcmd = ['--close-branch']
        else:
            branch = hglib.fromunicode(self.branchop)
            if branch in repo.branchtags():
                # response: 0=Yes, 1=No, 2=Cancel
                if branch in [p.branch() for p in repo.parents()]:
                    resp = 0
                else:
                    rev = repo[branch].rev()
                    resp = qtlib.CustomPrompt(_('Confirm Branch Change'),
                        _('Named branch "%s" already exists, '
                          'last used in revision %d\n'
                          ) % (self.branchop, rev),
                        self,
                        (_('Restart &Branch'),
                         _('&Commit to current branch'),
                         _('Cancel')), 2, 2).run()
            else:
                resp = qtlib.CustomPrompt(_('Confirm New Branch'),
                    _('Create new named branch "%s" with this commit?\n'
                      ) % self.branchop,
                    self,
                    (_('Create &Branch'),
                     _('&Commit to current branch'),
                     _('Cancel')), 2, 2).run()
            if resp == 0:
                newbranch = True
                commandlines.append(['branch', '--repository', repo.root,
                                     '--force', branch])
            elif resp == 2:
                return
        files = self.stwidget.getChecked('MAR?!S')
        if not (files or brcmd or newbranch):
            qtlib.WarningMsgBox(_('No files checked'),
                                _('No modified files checkmarked for commit'),
                                parent=self)
            self.stwidget.tv.setFocus()
            return
        if len(repo.parents()) > 1:
            files = []

        user = qtlib.getCurrentUsername(self, self.repo, self.opts)
        if not user:
            return
        self.addUsernameToHistory(user)

        checkedUnknowns = self.stwidget.getChecked('?I')
        if checkedUnknowns:
            res = qtlib.CustomPrompt(
                    _('Confirm Add'),
                    _('Add selected untracked files?'), self,
                    (_('&Add'), _('Cancel')), 0, 1,
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
                    _('Remove selected deleted files?'), self,
                    (_('&Remove'), _('Cancel')), 0, 1,
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
            if e.hint:
                err = _('%s (hint: %s)') % (hglib.tounicode(str(e)),
                                            hglib.tounicode(e.hint))
            else:
                err = hglib.tounicode(str(e))
            self.showMessage.emit(err)
            dcmd = []
        cmdline = ['commit', '--repository', repo.root, '--verbose',
                   '--user', user, '--message='+msg]
        cmdline += dcmd + brcmd + [repo.wjoin(f) for f in files]
        if len(repo.parents()) == 1:
            for fname in self.opts.get('autoinc', '').split(','):
                fname = fname.strip()
                if fname:
                    cmdline.extend(['--include', fname])

        commandlines.append(cmdline)

        if self.opts.get('pushafter'):
            cmd = ['push', '--repository', repo.root, self.opts['pushafter']]
            commandlines.append(cmd)

        repo.incrementBusyCount()
        self.commitButtonEnable.emit(False)
        self.runner.run(*commandlines)
        self.stopAction.setEnabled(True)
        self.progress.emit(*cmdui.startProgress(_('Commit', 'start progress'), ''))

    def stop(self):
        self.runner.cancel()

    def commandFinished(self, ret):
        self.progress.emit(*cmdui.stopProgress(_('Commit', 'stop progress')))
        self.stopAction.setEnabled(False)
        self.commitButtonEnable.emit(True)
        self.repo.decrementBusyCount()
        if ret == 0:
            self.branchop = None
            umsg = self.msgte.text()
            if umsg:
                self.addMessageToHistory(umsg)
            self.msgte.clear()
            self.msgte.setModified(False)
            self.commitComplete.emit()

class DetailsDialog(QDialog):
    'Utility dialog for configuring uncommon settings'
    def __init__(self, opts, userhistory, parent):
        QDialog.__init__(self, parent)
        self.setWindowTitle(_('%s - commit options') % parent.repo.displayname)
        self.repo = parent.repo

        layout = QVBoxLayout()
        self.setLayout(layout)

        hbox = QHBoxLayout()
        self.usercb = QCheckBox(_('Set username:'))

        usercombo = QComboBox()
        usercombo.setEditable(True)
        usercombo.setEnabled(False)
        SP = QSizePolicy
        usercombo.setSizePolicy(SP(SP.Expanding, SP.Minimum))
        self.usercb.toggled.connect(usercombo.setEnabled)
        self.usercb.toggled.connect(lambda s: s and usercombo.setFocus())

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
        self.datecb.toggled.connect(lambda s: s and curdate.setFocus())
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
        self.pushaftercb.toggled.connect(lambda s:
                s and self.pushafterle.setFocus())

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
        self.autoinccb.toggled.connect(lambda s:
                s and self.autoincle.setFocus())

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

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.bb = bb
        layout.addWidget(bb)

    def saveInRepo(self):
        fn = os.path.join(self.repo.root, '.hg', 'hgrc')
        self.saveToPath([fn])

    def saveGlobal(self):
        self.saveToPath(util.user_rcpath())

    def saveToPath(self, path):
        fn, cfg = qtlib.loadIniFile(path, self)
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
        fn, cfg = qtlib.loadIniFile([path], self)
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
        fn, cfg = qtlib.loadIniFile([path], self)
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
                if e.hint:
                    err = _('%s (hint: %s)') % (hglib.tounicode(str(e)),
                                                hglib.tounicode(e.hint))
                else:
                    err = hglib.tounicode(str(e))
                qtlib.WarningMsgBox(_('Invalid date format'), err, parent=self)
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
                if e.hint:
                    err = _('%s (hint: %s)') % (hglib.tounicode(str(e)),
                                                hglib.tounicode(e.hint))
                else:
                    err = hglib.tounicode(str(e))
                qtlib.WarningMsgBox(_('No username configured'),
                                    err, parent=self)
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
        self.setWindowIcon(qtlib.geticon('hg-commit'))
        self.pats = pats
        self.opts = opts

        layout = QVBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setMargin(0)
        layout.setSpacing(0)
        self.setLayout(layout)

        commit = CommitWidget(pats, opts, opts.get('root'), False, self)
        layout.addWidget(commit, 1)

        self.statusbar = cmdui.ThgStatusBar(self)
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
        self.commitButton = bb.button(BB.Ok)
        self.commitButton.setText(_('Commit', 'action button'))
        self.bb = bb

        layout.addWidget(self.bb)
        layout.addWidget(self.statusbar)

        s = QSettings()
        self.restoreGeometry(s.value('commit/geom').toByteArray())
        commit.loadSettings(s, 'committool')
        commit.repo.repositoryChanged.connect(self.updateUndo)
        commit.commitComplete.connect(self.postcommit)
        commit.commitButtonEnable.connect(self.commitButton.setEnabled)

        self.setWindowTitle(_('%s - commit') % commit.repo.displayname)
        self.commit = commit
        self.commit.reload()
        self.updateUndo()
        self.commit.msgte.setFocus()
        QShortcut(QKeySequence.Refresh, self, self.refresh)

    def done(self, ret):
        self.commit.repo.configChanged.disconnect(self.commit.configChanged)
        self.commit.repo.repositoryChanged.disconnect(self.commit.repositoryChanged)
        self.commit.repo.workingBranchChanged.disconnect(self.commit.workingBranchChanged)
        self.commit.repo.repositoryChanged.disconnect(self.updateUndo)
        super(CommitDialog, self).done(ret)

    def linkActivated(self, link):
        link = hglib.fromunicode(link)
        if link.startswith('subrepo:'):
            from tortoisehg.hgqt.run import qtrun
            qtrun(run, ui.ui(), root=link[8:])
        if link.startswith('shelve:'):
            repo = self.commit.repo
            from tortoisehg.hgqt import shelve
            dlg = shelve.ShelveDialog(repo, self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.exec_()
            self.refresh()

    def updateUndo(self):
        BB = QDialogButtonBox
        undomsg = self.commit.canUndo()
        if undomsg:
            self.bb.button(BB.Discard).setEnabled(True)
            self.bb.button(BB.Discard).setToolTip(undomsg)
        else:
            self.bb.button(BB.Discard).setEnabled(False)
            self.bb.button(BB.Discard).setToolTip('')

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
            s.setValue('commit/geom', self.saveGeometry())
            self.commit.saveSettings(s, 'committool')
            QDialog.reject(self)

def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    from tortoisehg.hgqt import thgrepo
    repo = thgrepo.repository(ui, path=paths.find_root())
    pats = hglib.canonpaths(pats)
    os.chdir(repo.root)
    return CommitDialog(pats, opts)

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
from tortoisehg.util import hglib, shlib, paths, wconfig
from tortoisehg.util.util import format_desc

from tortoisehg.hgqt import qtlib, status, cmdui, branchop
from tortoisehg.hgqt.sync import loadIniFile

# Technical Debt for CommitWidget
#  qtlib decode failure dialog (ask for retry locale, suggest HGENCODING)
#  Need a unicode-to-UTF8 function
#  +1 / -1 head indication (not as important with workbench integration)
#  spell check / tab completion
#  in-memory patching / committing chunk selected files

class CommitWidget(QWidget):
    'A widget that encompasses a StatusWidget and commit extras'
    loadBegin = pyqtSignal()
    loadComplete = pyqtSignal()
    commitButtonName = pyqtSignal(str)
    showMessage = pyqtSignal(str)
    commitComplete = pyqtSignal()

    def __init__(self, pats, opts, root=None, parent=None, logwidget=None):
        QWidget.__init__(self, parent)

        self.opts = opts # user, date
        self.stwidget = status.StatusWidget(pats, opts, root, self)
        self.stwidget.showMessage.connect(self.showMessage)
        self.stwidget.loadBegin.connect(lambda: self.loadBegin.emit())
        self.stwidget.loadComplete.connect(lambda: self.loadComplete.emit())
        self.msghistory = []
        self.qref = False

        self.repo = repo = self.stwidget.repo
        self.runner = cmdui.Runner(_('Commit'), self, logwidget)
        self.runner.commandStarted.connect(repo.incrementBusyCount)
        self.runner.commandFinished.connect(self.commandFinished)

        repo.configChanged.connect(self.configChanged)
        repo.repositoryChanged.connect(self.repositoryChanged)

        self.opts['pushafter'] = repo.ui.config('tortoisehg', 'cipushafter', '')
        self.opts['autoinc'] = repo.ui.config('tortoisehg', 'autoinc', '')

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stwidget)
        self.setLayout(layout)

        vbox = QVBoxLayout()
        vbox.setMargin(0)
        vbox.setContentsMargins(*(0,)*4)

        hbox = QHBoxLayout()
        hbox.setMargin(0)
        hbox.setContentsMargins(*(0,)*4)
        branchbutton = QPushButton(_('Branch: '))
        branchbutton.pressed.connect(self.branchOp)
        self.branchbutton = branchbutton
        self.branchop = None
        hbox.addWidget(branchbutton)
        self.buttonHBox = hbox

        msgcombo = MessageHistoryCombo()
        msgcombo.activated.connect(self.msgSelected)
        hbox.addWidget(msgcombo, 1)
        hbox.addSpacing(2)
        vbox.addLayout(hbox, 0)

        self.detailsbutton = QPushButton(_('Details'))
        self.detailsbutton.pressed.connect(self.details)
        self.buttonHBox.addWidget(self.detailsbutton)

        self.parentvbox = QVBoxLayout()
        self.parentlabels = [QLabel('<b>Parent:</b>')]
        self.parentvbox.addWidget(self.parentlabels[0])
        vbox.addLayout(self.parentvbox, 0)

        msgte = QPlainTextEdit()
        msgte.setLineWrapMode(QPlainTextEdit.NoWrap)
        msgfont = qtlib.getfont(self.repo.ui, 'fontcomment')
        msgte.setFont(msgfont.font())
        msgfont.changed.connect(lambda fnt: msgte.setFont(fnt))
        msgte.textChanged.connect(self.msgChanged)
        msgte.setContextMenuPolicy(Qt.CustomContextMenu)
        msgte.customContextMenuRequested.connect(self.menuRequested)
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
        msgte.setFocus()
        # Yuki's Mockup: http://bitbucket.org/kuy/thg-qt/wiki/Home
        self.msgte = msgte
        self.msgcombo = msgcombo

    def details(self):
        dlg = DetailsDialog(self.opts, self.userhist, self)
        if dlg.exec_() == QDialog.Accepted:
            self.opts.update(dlg.outopts)

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
        wctx = self.repo[None]

        # Update qrefresh mode
        if self.repo.changectx('.').thgmqappliedpatch():
            self.commitButtonName.emit(_('QRefresh'))
            if not self.qref:
                self.initQRefreshMode()
        else:
            self.commitButtonName.emit(_('Commit'))
            if self.qref:
                self.endQRefreshMode()

        # Update message list
        self.msgcombo.reset(self.msghistory)

        # Update branch operation button
        cur = hglib.tounicode(wctx.branch())
        if self.branchop is None:
            title = _('Branch: ') + cur
        elif self.branchop == False:
            title = _('Close Branch: ') + cur
        else:
            title = _('New Branch: ') + self.branchop
        self.branchbutton.setText(title)

        # Update parent revision(s)
        for i, ctx in enumerate(self.repo.parents()):
            desc = format_desc(ctx.description(), 80)
            fmt = "<span style='font-family:Courier'>%s(%s)</span> %s"
            ptext = fmt % (ctx.rev(), short_hex(ctx.node()), desc)
            ptext = _('<b>Parent: </b>') + ptext
            if i >= len(self.parentlabels):
                lbl = QLabel(ptext)
                self.parentvbox.addWidget(lbl)
                self.parentlabels.append(lbl)
            else:
                self.parentlabels[i].setText(ptext)
        while len(self.repo.parents()) > len(self.parentlabels):
            w = self.parentlabels.pop()
            self.parentvbox.removeWidget(w)

    def initQRefreshMode(self):
        'Working parent is a patch.  Is it refreshable?'
        qtip = self.repo['qtip']
        if qtip != self.repo['.']:
            self.showMessage.emit(_('Cannot refresh non-tip patch'))
            self.commitButtonName.emit(_('N/A'))
            return
        self.opts['user'] = qtip.user()
        self.opts['date'] = hglib.displaytime(qtip.date())
        self.msgte.setPlainText(hglib.tounicode(qtip.description()))
        self.msgte.document().setModified(False)
        self.msgte.moveCursor(QTextCursor.End)
        self.qref = True

    def endQRefreshMode(self):
        self.msgte.clear()
        self.opts['user'] = ''
        self.opts['date'] = ''
        self.qref = False

    def msgChanged(self):
        text = self.msgte.toPlainText()
        self.buttonHBox.setEnabled(not text.isEmpty())
        sumlen, maxlen = self.getLengths()
        if not sumlen and not maxlen:
            self.msgte.setExtraSelections([])
            return
        pos, nextpos = 0, 0
        sels = []
        for i, line in enumerate(text.split('\n')):
            length = len(line)
            pos = nextpos
            nextpos += length + 1 # include \n
            if i == 0:
                if length < sumlen or not sumlen:
                    continue
                pos += sumlen
            elif i == 1:
                if length == 0 or not sumlen:
                    continue
            else:
                if length < maxlen or not maxlen:
                    continue
                pos += maxlen
            sel = QTextEdit.ExtraSelection()
            sel._bgcolor = QColor('LightSalmon')
            sel._fgcolor = QColor('Black')
            sel.format.setBackground(sel._bgcolor)
            sel.format.setForeground(sel._fgcolor)
            sel.cursor = QTextCursor(self.msgte.document())
            sel.cursor.setPosition(pos)
            sel.cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
            sels.append(sel)
        self.msgte.setExtraSelections(sels)

    def msgReflow(self):
        'User pressed Control-E, reflow current paragraph'
        if QApplication.focusWidget() != self.msgte:
            return
        self.reflowBlock(self.msgte.textCursor().block())

    def reflowBlock(self, block):
        sumlen, maxlen = self.getLengths()
        if not maxlen:
            return
        # In QtTextDocument land, a block is a sequence of text ending
        # in (and including) a carriage return.  Aka, a line of text.
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
        return cursor.block()

    def menuRequested(self, point):
        cursor = self.msgte.cursorForPosition(point)
        point = self.msgte.mapToGlobal(point)

        def apply():
            sumlen, maxlen = self.getLengths()
            if not maxlen:
                return
            block = self.msgte.document().firstBlock()
            while block != self.msgte.document().end():
                if block.length() > maxlen:
                    block = self.reflowBlock(block)
                block = block.next()
        def paste():
            files = self.stwidget.getChecked()
            cursor.insertText(', '.join(files))
        def settings():
            from tortoisehg.hgqt.settings import SettingsDialog
            dlg = SettingsDialog(True, focus='tortoisehg.summarylen')
            self.repo.incrementBusyCount()
            ret = dlg.exec_()
            self.repo.decrementBusyCount()
            if ret == QDialog.Accepted:
                self.msgChanged()

        menu = self.msgte.createStandardContextMenu()
        for name, func in [(_('Paste &Filenames'), paste),
                           (_('App&ly Format'), apply),
                           (_('C&onfigure Format'), settings)]:
            def add(name, func):
                action = menu.addAction(name)
                action.triggered.connect(lambda: func())
            add(name, func)
        return menu.exec_(point)

    def getLengths(self):
        try:
            sumlen = int(self.repo.ui.config('tortoisehg', 'summarylen', 0))
            maxlen = int(self.repo.ui.config('tortoisehg', 'messagewrap', 0))
        except (TypeError, ValueError):
            sumlen, maxlen = 0, 0
        return sumlen, maxlen

    def restoreState(self, data):
        return self.stwidget.restoreState(data)

    def saveState(self):
        return self.stwidget.saveState()

    def branchOp(self):
        d = branchop.BranchOpDialog(self.repo, self.branchop)
        self.repo.incrementBusyCount()
        if d.exec_() == QDialog.Accepted:
            self.branchop = d.branchop
        self.repo.decrementBusyCount()

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
        repoid = str(self.repo[0])
        # message history is stored in unicode
        self.split.restoreState(s.value('commit/split').toByteArray())
        self.msghistory = list(s.value('commit/history-'+repoid).toStringList())
        self.msghistory = [m for m in self.msghistory if m]
        self.msgcombo.reset(self.msghistory)
        self.userhist = s.value('commit/userhist').toStringList()
        self.userhist = [u for u in self.userhist if u]
        try:
            curmsg = self.repo.opener('cur-message.txt').read()
            self.msgte.setPlainText(hglib.tounicode(curmsg))
            self.msgte.document().setModified(False)
            self.msgte.moveCursor(QTextCursor.End)
        except EnvironmentError:
            pass

    def storeConfigs(self, s):
        'Save history, etc, in QSettings instance'
        repoid = str(self.repo[0])
        s.setValue('commit/history-'+repoid, self.msghistory)
        s.setValue('commit/split', self.split.saveState())
        s.setValue('commit/userhist', self.userhist)
        try:
            # current message is stored in local encoding
            self.repo.opener('cur-message.txt', 'w').write(self.getMessage())
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
        self.repo.ui.invalidateui()
        try:
            return self.repo.ui.username()
        except error.Abort:
            return None

    def commit(self):
        cwd = os.getcwd()
        try:
            os.chdir(self.repo.root)
            return self._commit(self.repo)
        finally:
            os.chdir(cwd)

    def _commit(self, repo):
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

        checkedUnknowns = self.stwidget.getChecked('?I')
        if checkedUnknowns:
            res = qtlib.CustomPrompt(
                    _('Confirm Add'),
                    _('Add checked untracked files?'), self,
                    (_('&OK'), _('Cancel')), 0, 1,
                    checkedUnknowns).run()
            if res == 0:
                dispatch._dispatch(repo.ui, ['add'] + checkedUnknowns)
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
                dispatch._dispatch(repo.ui, ['remove'] + checkedMissing)
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

        cmdline = ['commit', '--verbose', '--user', user, '--message', msg]
        cmdline += dcmd + brcmd + files
        if self.qref:
            cmdline[0] = 'qrefresh'

        for fname in self.opts.get('autoinc', '').split(','):
            fname = fname.strip()
            if fname:
                cmdline.extend(['--include', fname])

        if self.opts.get('pushafter'):
            pushcmd = ['push', self.opts['pushafter']]
            display = ' '.join(['hg'] + cmdline + ['&&'] + pushcmd)
            self.runner.run(cmdline, pushcmd, display=display)
        else:
            display = ' '.join(['hg'] + cmdline)
            self.runner.run(cmdline, display=display)

    def commandFinished(self, wrapper):
        if not wrapper.data:
            self.addMessageToHistory()
            if not self.qref:
                self.msgte.clear()
            self.msgte.document().setModified(False)
            self.commitComplete.emit()
        self.repo.decrementBusyCount()
        self.stwidget.refreshWctx()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() == Qt.ControlModifier:
                self.commit()
            return
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_E:
            self.msgReflow()
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

        name = hglib.get_reponame(self.repo)
        self.setWindowTitle('%s - commit details' % name)

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

        commit = CommitWidget(pats, opts, None, self)
        layout.addWidget(commit, 1)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel|BB.Discard)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(BB.Discard).setText('Undo')
        bb.button(BB.Discard).clicked.connect(commit.rollback)
        bb.button(BB.Cancel).setDefault(False)
        bb.button(BB.Discard).setDefault(False)
        bb.button(BB.Ok).setDefault(True)
        layout.addWidget(bb)
        self.bb = bb

        s = QSettings()
        commit.restoreState(s.value('commit/state').toByteArray())
        self.restoreGeometry(s.value('commit/geom').toByteArray())
        commit.loadConfigs(s)
        commit.showMessage.connect(self.showMessage)
        commit.loadComplete.connect(self.updateUndo)
        commit.commitComplete.connect(self.postcommit)
        commit.commitButtonName.connect(self.setButtonName)

        name = hglib.get_reponame(commit.repo)
        self.setWindowTitle('%s - commit' % name)
        self.commit = commit
        self.commit.reload()

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

    def showMessage(self, msg):
        print msg

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        elif event.matches(QKeySequence.Refresh):
            self.commit.reload()
        return super(CommitDialog, self).keyPressEvent(event)

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

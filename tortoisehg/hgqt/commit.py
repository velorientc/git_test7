# commit.py - TortoiseHg's commit widget and standalone dialog
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import hg, ui, cmdutil, util

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.hgqt.i18n import _
from tortoisehg.util import hglib, shlib, paths

from tortoisehg.hgqt import qtlib, status, cmdui

class CommitWidget(QWidget):
    'A widget that encompasses a StatusWidget and commit extras'
    loadBegin = pyqtSignal()
    loadComplete = pyqtSignal()
    errorMessage = pyqtSignal(QString)
    commitComplete = pyqtSignal()
    commit = pyqtSlot()

    def __init__(self, pats, opts, root=None, parent=None):
        QWidget.__init__(self, parent)

        self.opts = opts # user, date
        self.stwidget = status.StatusWidget(pats, opts, root, self)
        self.msghistory = []

        layout = QVBoxLayout()
        layout.addWidget(self.stwidget)
        self.setLayout(layout)
        form = QFormLayout()
        usercombo = QComboBox()
        usercombo.addItem(self.stwidget.repo[None].user())
        usercombo.setEditable(True)
        form.addRow(_('Changeset:'), QLabel(_('Working Copy')))
        form.addRow(_('User:'), usercombo)
        form.addRow(_('Parent:'), QLabel('Description of ' +
                                         str(self.stwidget.repo['.'])))
        frame = QFrame()
        frame.setLayout(form)
        frame.setFrameStyle(QFrame.StyledPanel)

        vbox = QVBoxLayout()
        vbox.addWidget(frame, 0)
        vbox.setMargin(0)
        hbox = QHBoxLayout()
        branchop = QPushButton('Branch: default')
        hbox.addWidget(branchop)
        msgcombo = QComboBox()
        msgcombo.addItem('Recent commit messages...')
        hbox.addWidget(msgcombo, 1)
        vbox.addLayout(hbox, 0)
        msgte = QTextEdit()
        msgte.setAcceptRichText(False)
        vbox.addWidget(msgte, 1)
        upperframe = QFrame()
        upperframe.setLayout(vbox)

        self.split = QSplitter(Qt.Vertical)
        # Add our widgets to the top of our splitter
        self.split.addWidget(upperframe)
        # Add status widget document frame below our splitter
        # this reparents the docf from the status splitter
        self.split.addWidget(self.stwidget.docf)
        h = self.split.sizeHint().height()
        mh = upperframe.minimumSizeHint().height()
        self.split.setSizes([mh, h-mh])

        # add our splitter where the docf used to be
        self.stwidget.split.addWidget(self.split)
        msgte.setFocus()
        # Yuki's Mockup: http://bitbucket.org/kuy/thg-qt/wiki/Home
        self.usercombo = usercombo
        self.msgte = msgte

    def restoreState(self, data):
        return self.stwidget.restoreState(data)

    def saveState(self):
        return self.stwidget.saveState()

    def getMessage(self):
        text = self.msgte.toPlainText()
        try:
            text = hglib.fromunicode(text, 'strict')
        except UnicodeEncodeError:
            pass # Handle decoding errors
        return text

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
        self.msghistory = s.value('commit/history-'+repoid).toStringList()
        try:
            lastmsg = repo.opener('last-message.txt').read()
            self.msgte.setPlainText(hglib.fromunicode(lastmsg))
            self.msgte.document().setModified(False)
            self.msgte.moveCursor(QTextCursor.End)
        except EnvironmentError:
            pass

    def storeConfigs(self, s):
        'Save history, etc, in QSettings instance'
        repo = self.stwidget.repo
        repoid = str(repo[0])
        s.setValue('commit/history-'+repoid, self.msghistory)
        try:
            # last message is stored in local encoding
            repo.opener('last-message.txt', 'w').write(self.getMessage())
        except EnvironmentError:
            pass

    def commit(self):
        msg = self.getMessage()
        cmdline = ['commit', '--message', msg]
        files = self.stwidget.getChecked()
        if files:
            cmdline.extend(files)
        else:
            qtlib.WarningMsgBox(_('No files selected'),
                                _('No operation to perform'),
                                parent=self)
            return
        print cmdline
        umsg = self.msgte.toPlainText()
        if umsg not in self.msghistory:
            self.msghistory.insert(0, umsg)
            self.msghistory = self.msghistory[:10]
        self.msgte.clear()
        self.msgte.document().setModified(False)
        return True

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
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        self.connect(bb, SIGNAL("accepted()"), self, SLOT("accept()"))
        self.connect(bb, SIGNAL("rejected()"), self, SLOT("reject()"))
        bb.button(BB.Ok).setDefault(True)
        bb.button(BB.Ok).setText('Commit')
        layout.addWidget(bb)
        self.bb = bb

        s = QSettings()
        commit.restoreState(s.value('commit/state').toByteArray())
        self.restoreGeometry(s.value('commit/geom').toByteArray())
        commit.loadConfigs(s)
        self.commit = commit

        self.connect(self.commit, SIGNAL('errorMessage'),
                     self.errorMessage)

    def errorMessage(self, msg):
        # TODO - add a status bar
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
            s = QSettings()
            s.setValue('commit/state', self.commit.saveState())
            s.setValue('commit/geom', self.saveGeometry())
            self.commit.storeConfigs(s)
            QDialog.accept(self)

    def reject(self):
        if self.commit.canExit():
            s = QSettings()
            s.setValue('commit/state', self.commit.saveState())
            s.setValue('commit/geom', self.saveGeometry())
            self.commit.storeConfigs(s)
            QDialog.reject(self)

def run(ui, *pats, **opts):
    return CommitDialog(hglib.canonpaths(pats), opts)

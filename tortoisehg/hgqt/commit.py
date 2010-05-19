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
    '''A widget that encompasses a StatusWidget and commit extras
       SIGNALS:
       loadBegin()                  - for progress bar
       loadComplete()               - for progress bar
       errorMessage(QString)        - for status bar
       titleTextChanged(QString)    - for window title
       commitComplete(QString)      - refresh notification
    '''
    def __init__(self, pats, opts, root=None, parent=None):
        QWidget.__init__(self, parent)
        self.opts = opts # user, date
        self.stwidget = status.StatusWidget(pats, opts, root, self)
        layout = QVBoxLayout()
        layout.addWidget(self.stwidget)
        self.setLayout(layout)
        vbox = self.stwidget.diffvbox
        form = QFormLayout()
        userle = QLineEdit()
        form.addRow(_('Changeset:'), QLabel(_('Working Copy')))
        form.addRow(_('User:'), userle)
        form.addRow(_('Parent:'), QLabel('Description of ' +
                                         str(self.stwidget.repo['.'])))
        frame = QFrame()
        frame.setLayout(form)
        frame.setFrameStyle(QFrame.StyledPanel)
        vbox.insertWidget(0, frame, 0)
        msgcombo = QComboBox()
        msgcombo.addItem('Recent commit messages...')
        vbox.insertWidget(1, msgcombo, 0)
        msgte = QTextEdit()
        msgte.setAcceptRichText(False)
        # TODO
        # http://www.qtcentre.org/threads/9840-QTextEdit-auto-resize
        vbox.insertWidget(2, msgte, 0)
        vbox.setStretchFactor(msgte, 0)
        # TODO add commit widgets
        # branchop dialog
        # Yuki's Mockup: http://bitbucket.org/kuy/thg-qt/wiki/Home

    def restoreState(self, data):
        return self.stwidget.restoreState(data)

    def saveState(self):
        return self.stwidget.saveState()

    def getChecked(self):
        return self.stwidget.getChecked()

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
        self.connect(bb, SIGNAL("accepted()"),
                     self, SLOT("accept()"))
        self.connect(bb, SIGNAL("rejected()"),
                     self, SLOT("reject()"))
        bb.button(BB.Ok).setDefault(True)
        bb.button(BB.Ok).setText('Commit')
        layout.addWidget(bb)
        self.bb = bb

        cmd = cmdui.Widget()
        cmd.commandStarted.connect(self.commandStarted)
        cmd.commandFinished.connect(self.commandFinished)
        cmd.commandCanceling.connect(self.commandCanceled)
        layout.addWidget(cmd)
        cmd.setHidden(True)
        self.cmd = cmd

        s = QSettings()
        commit.restoreState(s.value('commit/state').toByteArray())
        self.restoreGeometry(s.value('commit/geom').toByteArray())
        self.commit = commit

        self.connect(self.commit, SIGNAL('errorMessage'),
                     self.errorMessage)

    def errorMessage(self, msg):
        # TODO: Does not appear to work
        self.cmd.pmon.set_text(msg)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() == Qt.ControlModifier:
                self.accept()  # Ctrl+Enter
            return
        elif event.key() == Qt.Key_Escape:
            self.reject()
            return
        return super(QDialog, self).keyPressEvent(event)

    def commandStarted(self):
        self.cmd.setShown(True)
        self.bb.button(QDialogButtonBox.Ok).setEnabled(False)

    def commandFinished(self, wrapper):
        self.bb.button(QDialogButtonBox.Ok).setEnabled(True)
        if wrapper.data is not 0:
            self.cmd.show_output(True)
        else:
            self.reject()

    def commandCanceled(self):
        self.bb.button(QDialogButtonBox.Ok).setEnabled(True)

    def accept(self):
        cmdline = ['commit']
        files = self.stwidget.getChecked()
        if files:
            cmdline.extend(files)
        else:
            qtlib.WarningMsgBox(_('No files selected'),
                                _('No operation to perform'),
                                parent=self)
            return
        print cmdline
        #self.cmd.run(cmdline)

    def reject(self):
        if self.cmd.core.is_running():
            self.cmd.core.cancel()
        else:
            s = QSettings()
            s.setValue('commit/state', self.commit.saveState())
            s.setValue('commit/geom', self.saveGeometry())
            QDialog.reject(self)

def run(ui, *pats, **opts):
    return CommitDialog(hglib.canonpaths(pats), opts)

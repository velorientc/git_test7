# mq.py - TortoiseHg MQ widget
#
# Copyright 2011 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os
import re

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import hg, ui, url, util, error
from mercurial import merge as mergemod

from tortoisehg.util import hglib, patchctx
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, cmdui, rejects, commit, shelve

class MQWidget(QWidget):
    showMessage = pyqtSignal(unicode)
    output = pyqtSignal(QString, QString)
    progress = pyqtSignal(QString, object, QString, QString, object)
    makeLogVisible = pyqtSignal(bool)

    def __init__(self, repo, parent, **opts):
        QWidget.__init__(self, parent)

        self.repo = repo
        self.opts = opts
        self.refreshing = False

        layout = QVBoxLayout()
        layout.setSpacing(0)
        self.setLayout(layout)

        # top toolbar
        tbarhbox = QHBoxLayout()
        tbarhbox.setSpacing(5)
        self.layout().addLayout(tbarhbox, 0)
        self.queueCombo = QComboBox()
        self.optionsBtn = QPushButton(_('Options'))
        self.msgHistoryCombo = QComboBox()
        tbarhbox.addWidget(self.queueCombo)
        tbarhbox.addWidget(self.optionsBtn)
        tbarhbox.addWidget(self.msgHistoryCombo, 1)

        # main area consists of a three-way horizontal splitter
        splitter = QSplitter()
        self.layout().addWidget(splitter, 1)
        splitter.setOrientation(Qt.Horizontal)
        splitter.setChildrenCollapsible(True)
        splitter.setObjectName('splitter')

        self.queueFrame = QFrame(splitter)
        self.fileListFrame = QFrame(splitter)
        self.messageFrame = QFrame(splitter)

        # Patch Queue Frame
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.queueFrame.setLayout(layout)

        qtbarhbox = QHBoxLayout()
        qtbarhbox.setSpacing(2)
        layout.addLayout(qtbarhbox, 0)
        qtbarhbox.setContentsMargins(0, 0, 0, 0)
        self.qpushAllBtn = QToolButton()
        self.qpushBtn = QToolButton()
        self.qpushMoveBtn = QToolButton()
        self.qdeleteBtn = QToolButton()
        self.qpopBtn = QToolButton()
        self.qpopAllBtn = QToolButton()
        qtbarhbox.addWidget(self.qpushAllBtn)
        qtbarhbox.addWidget(self.qpushBtn)
        qtbarhbox.addStretch(1)
        qtbarhbox.addWidget(self.qpushMoveBtn)
        qtbarhbox.addWidget(self.qdeleteBtn)
        qtbarhbox.addStretch(1)
        qtbarhbox.addWidget(self.qpopBtn)
        qtbarhbox.addWidget(self.qpopAllBtn)

        self.queueListWidget = QListWidget(self)
        layout.addWidget(self.queueListWidget, 1)

        self.guardSelBtn = QPushButton(_('Guards: 0/0'))
        layout.addWidget(self.guardSelBtn, 0)

        self.revisionOrCommitBtn = QPushButton(_('Revision Queue'))
        layout.addWidget(self.revisionOrCommitBtn, 0)

        # File List Frame
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.fileListFrame.setLayout(layout)

        self.fileListWidget = QListWidget(self)
        layout.addWidget(self.fileListWidget, 0)

        # Message Frame
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.messageFrame.setLayout(layout)

        mtbarhbox = QHBoxLayout()
        mtbarhbox.setSpacing(5)
        layout.addLayout(mtbarhbox, 0)
        mtbarhbox.setContentsMargins(0, 0, 0, 0)
        self.newCheckBox = QCheckBox(_('New Patch'))
        self.patchNameLE = QLineEdit()
        mtbarhbox.addWidget(self.newCheckBox)
        mtbarhbox.addWidget(self.patchNameLE, 1)

        self.messageEditor = commit.MessageEntry(self)
        layout.addWidget(self.messageEditor, 1)

        qrefhbox = QHBoxLayout()
        layout.addLayout(qrefhbox, 0)
        qrefhbox.setContentsMargins(0, 0, 0, 0)
        self.shelveBtn = QPushButton(_('Shelve'))
        self.qnewOrRefreshBtn = QPushButton(_('QRefresh'))
        qrefhbox.addStretch(1)
        qrefhbox.addWidget(self.shelveBtn)
        qrefhbox.addWidget(self.qnewOrRefreshBtn)

        self.cmd = cmdui.Runner(_('Patch Queue'), parent != None, self)
        self.cmd.output.connect(self.output)
        self.cmd.makeLogVisible.connect(self.makeLogVisible)
        self.cmd.progress.connect(self.progress)

        self.shelveBtn.pressed.connect(self.launchShelveTool)

        self.repo.configChanged.connect(self.onConfigChanged)
        self.repo.repositoryChanged.connect(self.onRepositoryChanged)
        self.setAcceptDrops(True)

        if hasattr(self.patchNameLE, 'setPlaceholderText'): # Qt >= 4.7 
            self.patchNameLE.setPlaceholderText('### patch name ###')

        if parent:
            layout.setContentsMargins(2, 2, 2, 2)
        else:
            layout.setContentsMargins(0, 0, 0, 0)
            self.setWindowTitle(_('TortoiseHg Patch Queue'))
            self.resize(850, 550)

    def onConfigChanged(self):
        'Repository is reporting its config files have changed'
        self.reload()

    def onRepositoryChanged(self):
        'Repository is reporting its changelog has changed'
        self.reload()

    def launchShelveTool(self):
        dlg = shelve.ShelveDialog(self.repo, self)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()
        self.reload()

    def reload(self):
        self.refreshing = True
        # refresh self.queueCombo
        # refresh self.msgHistoryCombo
        # set self.patchNameLE to qtip patch name
        # update enabled states of qtbarhbox buttons
        # refresh self.queueListWidget
        # refresh self.guardSelBtn
        # refresh self.revisionOrCommitBtn
        # refresh self.messageEditor with qtip description, if not in new mode
        # refresh self.qnewOrRefreshBtn
        # refresh self.fileListWidget
        self.refreshing = False

    def details(self):
        dlg = OptionsDialog(self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        if dlg.exec_() == QDialog.Accepted:
            self.opts.update(dlg.outopts)

    # Capture drop events, try to import into current patch queue

    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [unicode(u.toLocalFile()) for u in event.mimeData().urls()]
        filepaths = [p for p in paths if os.path.isfile(p)]
        if filepaths:
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            super(MQWidget, self).dropEvent(event)
            return
        dlg = thgimport.ImportDialog(repo=self.repo, parent=self)
        # TODO: send flag to dialog indicating this is a qimport (alias?)
        dlg.finished.connect(dlg.deleteLater)
        dlg.setfilepaths(filepaths)
        dlg.exec_()

    # End drop events

    def canExit(self):
        return not self.cmd.core.running()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Refresh):
            self.reload()
        elif event.key() == Qt.Key_Escape:
            if self.cmd.core.running():
                self.cmd.cancel()
            elif not self.parent():
                self.close()
        else:
            return super(MQWidget, self).keyPressEvent(event)

class OptionsDialog(QDialog):
    'Utility dialog for configuring uncommon options'
    def __init__(self, parent):
        QDialog.__init__(self, parent)
        self.setWindowTitle('MQ options')

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.gitcb = QCheckBox(_('Use git extended diff format'))
        self.gitcb.setChecked(parent.opts.get('git', False))
        layout.addRow(self.gitcb, None)

        self.forcecb = QCheckBox(_('Force push or pop'))
        self.forcecb.setChecked(parent.opts.get('force', False))
        layout.addRow(self.forcecb, None)

        self.exactcb = QCheckBox(_('Apply patch to its recorded parent'))
        self.exactcb.setChecked(parent.opts.get('exact', False))
        layout.addRow(self.exactcb, None)

        self.currentdatecb = QCheckBox(_('Update date field with current date'))
        self.currentdatecb.setChecked(parent.opts.get('currentdate', False))
        layout.addRow(self.currentdatecb, None)

        self.currentusercb = QCheckBox(_('Update author field with current user'))
        self.currentusercb.setChecked(parent.opts.get('currentuser', False))
        layout.addRow(self.currentusercb, None)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def accept(self):
        outopts = {}
        outopts['git'] = self.gitcb.isChecked()
        outopts['force'] = self.forcecb.isChecked()
        outopts['exact'] = self.exactcb.isChecked()
        outopts['currentdate'] = self.currentdatecb.isChecked()
        outopts['currentuser'] = self.currentusercb.isChecked()
        self.outopts = outopts
        QDialog.accept(self)


def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    from tortoisehg.hgqt import thgrepo
    repo = thgrepo.repository(ui, path=paths.find_root())
    return MQWidget(repo, None, **opts)

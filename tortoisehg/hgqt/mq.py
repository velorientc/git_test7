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
        self.messageFrame = QFrame(splitter)
        self.fileListFrame = QFrame(splitter)

        # Patch Queue Frame
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.queueFrame.setLayout(layout)

        qtbarhbox = QHBoxLayout()
        qtbarhbox.setSpacing(2)
        layout.addLayout(qtbarhbox, 0)
        qtbarhbox.setContentsMargins(0, 0, 0, 0)
        self.qpushAllBtn = tb = QToolButton()
        #tb.setIcon(qtlib.geticon('qpush'))
        tb.setToolTip(_('Apply all patches'))
        self.qpushBtn = tb = QToolButton()
        tb.setIcon(qtlib.geticon('qpush'))
        tb.setToolTip(_('Apply one patch'))
        self.qpushMoveBtn = tb = QToolButton()
        #tb.setIcon(qtlib.geticon('qpush'))
        tb.setToolTip(_('Apply selected patch next (change queue order)'))
        self.qdeleteBtn = tb = QToolButton()
        tb.setIcon(qtlib.geticon('filedelete'))
        tb.setToolTip(_('Delete selected patches'))
        self.qpopBtn = tb = QToolButton()
        tb.setIcon(qtlib.geticon('qpop'))
        tb.setToolTip(_('Unapply one patch'))
        self.qpopAllBtn = tb = QToolButton()
        #tb.setIcon(qtlib.geticon('qpop'))
        tb.setToolTip(_('Unapply all patches'))
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
        self.messageEditor.refresh(repo)
        layout.addWidget(self.messageEditor, 1)

        qrefhbox = QHBoxLayout()
        layout.addLayout(qrefhbox, 0)
        qrefhbox.setContentsMargins(0, 0, 0, 0)
        self.shelveBtn = QPushButton(_('Shelve'))
        self.qnewOrRefreshBtn = QPushButton(_('QRefresh'))
        qrefhbox.addStretch(1)
        qrefhbox.addWidget(self.shelveBtn)
        qrefhbox.addWidget(self.qnewOrRefreshBtn)

        # File List Frame
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.fileListFrame.setLayout(layout)

        self.fileListWidget = QListWidget(self)
        layout.addWidget(self.fileListWidget, 0)

        # Command runner and connections...
        self.cmd = cmdui.Runner(_('Patch Queue'), parent != None, self)
        self.cmd.output.connect(self.output)
        self.cmd.makeLogVisible.connect(self.makeLogVisible)
        self.cmd.progress.connect(self.progress)

        self.shelveBtn.pressed.connect(self.launchShelveTool)
        self.optionsBtn.pressed.connect(self.launchOptionsDialog)

        self.repo.configChanged.connect(self.onConfigChanged)
        self.repo.repositoryChanged.connect(self.onRepositoryChanged)
        self.setAcceptDrops(True)

        if hasattr(self.patchNameLE, 'setPlaceholderText'): # Qt >= 4.7 
            self.patchNameLE.setPlaceholderText('### patch name ###')

        if parent:
            self.layout().setContentsMargins(2, 2, 2, 2)
        else:
            self.layout().setContentsMargins(0, 0, 0, 0)
            self.setWindowTitle(_('TortoiseHg Patch Queue'))
            self.statusbar = cmdui.ThgStatusBar(self)
            self.layout().addWidget(self.statusbar)
            self.progress.connect(self.statusbar.progress)
            self.showMessage.connect(self.statusbar.showMessage)
            self.resize(850, 550)

        QTimer.singleShot(0, self.reload)

    def onConfigChanged(self):
        'Repository is reporting its config files have changed'
        self.messageEditor.refresh(self.repo)

    def onRepositoryChanged(self):
        'Repository is reporting its changelog has changed'
        self.reload()

    def launchShelveTool(self):
        dlg = shelve.ShelveDialog(self.repo, self)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()
        self.reload()

    def launchOptionsDialog(self):
        dlg = OptionsDialog(self)
        dlg.finished.connect(dlg.deleteLater)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        if dlg.exec_() == QDialog.Accepted:
            self.opts.update(dlg.outopts)

    def reload(self):
        self.refreshing = True
        try:
            pass
            # refresh self.queueCombo
            # refresh self.msgHistoryCombo
            # set self.patchNameLE to qtip patch name
            # update enabled states of qtbarhbox buttons
            # refresh self.queueListWidget
            # refresh self.guardSelBtn
            # refresh self.revisionOrCommitBtn
            # refresh self.messageEditor with qtip description, if not new
            # refresh self.qnewOrRefreshBtn
            # refresh self.fileListWidget
        except Exception, e:
            self.showMessage.emit(hglib.tounicode(str(e)))
        self.refreshing = False

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

        layout = QFormLayout()
        self.setLayout(layout)

        self.gitcb = QCheckBox(_('Use git extended diff format'))
        layout.addRow(self.gitcb, None)

        self.forcecb = QCheckBox(_('Force push or pop'))
        layout.addRow(self.forcecb, None)

        self.exactcb = QCheckBox(_('Apply patch to its recorded parent'))
        layout.addRow(self.exactcb, None)

        self.currentdatecb = QCheckBox(_('Update date field with current date'))
        layout.addRow(self.currentdatecb, None)

        self.datele = QLineEdit()
        layout.addRow(QLabel(_('Specify an explicit date:')), self.datele)

        self.currentusercb = QCheckBox(_('Update author field with current user'))
        layout.addRow(self.currentusercb, None)

        self.userle = QLineEdit()
        layout.addRow(QLabel(_('Specify an explicit author:')), self.userle)

        self.currentdatecb.toggled.connect(self.datele.setDisabled)
        self.currentusercb.toggled.connect(self.userle.setDisabled)

        self.gitcb.setChecked(parent.opts.get('git', False))
        self.forcecb.setChecked(parent.opts.get('force', False))
        self.exactcb.setChecked(parent.opts.get('exact', False))
        self.currentdatecb.setChecked(parent.opts.get('currentdate', False))
        self.currentusercb.setChecked(parent.opts.get('currentuser', False))
        self.datele.setText(hglib.tounicode(parent.opts.get('date', '')))
        self.userle.setText(hglib.tounicode(parent.opts.get('user', '')))

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.bb = bb
        layout.addWidget(bb)

    def accept(self):
        outopts = {}
        outopts['git'] = self.gitcb.isChecked()
        outopts['force'] = self.forcecb.isChecked()
        outopts['exact'] = self.exactcb.isChecked()
        outopts['currentdate'] = self.currentdatecb.isChecked()
        outopts['currentuser'] = self.currentusercb.isChecked()
        if self.currentdatecb.isChecked():
            outopts['date'] = ''
        else:
            outopts['date'] = hglib.fromunicode(self.datele.text())
        if self.currentusercb.isChecked():
            outopts['user'] = ''
        else:
            outopts['user'] = hglib.fromunicode(self.userle.text())

        self.outopts = outopts
        QDialog.accept(self)

def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    from tortoisehg.hgqt import thgrepo
    repo = thgrepo.repository(ui, path=paths.find_root())
    return MQWidget(repo, None, **opts)

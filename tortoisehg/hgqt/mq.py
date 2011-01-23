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
from hgext import mq as mqmod

from tortoisehg.util import hglib, patchctx
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, cmdui, rejects, commit, shelve, qscilib

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
        self.msgHistoryCombo = PatchMessageCombo(self)
        tbarhbox.addWidget(self.queueCombo)
        tbarhbox.addWidget(self.optionsBtn)
        tbarhbox.addWidget(self.msgHistoryCombo, 1)

        # main area consists of a three-way horizontal splitter
        self.splitter = splitter = QSplitter()
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
        self.setGuardsBtn = tb = QToolButton()
        #tb.setIcon(qtlib.geticon('qpush'))
        tb.setToolTip(_('Configure guards for selected patch'))
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
        qtbarhbox.addWidget(self.setGuardsBtn)
        qtbarhbox.addWidget(self.qpushMoveBtn)
        qtbarhbox.addWidget(self.qdeleteBtn)
        qtbarhbox.addStretch(1)
        qtbarhbox.addWidget(self.qpopBtn)
        qtbarhbox.addWidget(self.qpopAllBtn)

        self.queueListWidget = QListWidget(self)
        layout.addWidget(self.queueListWidget, 1)

        self.guardSelBtn = QPushButton()
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
        self.messageEditor.installEventFilter(qscilib.KeyPressInterceptor(self))
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
        self.msgHistoryCombo.activated.connect(self.onMessageSelected)

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
            QShortcut(QKeySequence.Refresh, self, self.reload)
            self.resize(850, 550)

        self.loadConfigs()
        QTimer.singleShot(0, self.reload)

    @pyqtSlot()
    def onConfigChanged(self):
        'Repository is reporting its config files have changed'
        self.messageEditor.refresh(self.repo)

    @pyqtSlot()
    def onRepositoryChanged(self):
        'Repository is reporting its changelog has changed'
        self.reload()

    @pyqtSlot(int)
    def onMessageSelected(self, row):
        if self.messageEditor.text() and self.messageEditor.isModified():
            d = QMessageBox.question(self, _('Confirm Discard Message'),
                        _('Discard current commit message?'),
                        QMessageBox.Ok | QMessageBox.Cancel)
            if d != QMessageBox.Ok:
                return
        self.messageEditor.setText(self.messages[row][1])
        lines = self.messageEditor.lines()
        if lines:
            lines -= 1
            pos = self.messageEditor.lineLength(lines)
            self.messageEditor.setCursorPosition(lines, pos)
            self.messageEditor.ensureLineVisible(lines)
            hs = self.messageEditor.horizontalScrollBar()
            hs.setSliderPosition(0)
        self.messageEditor.setModified(False)
        self.messageEditor.setFocus()

    @pyqtSlot()
    def launchShelveTool(self):
        dlg = shelve.ShelveDialog(self.repo, self)
        dlg.finished.connect(dlg.deleteLater)
        dlg.exec_()
        self.reload()

    @pyqtSlot()
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
            try:
                self._reload()
            except Exception, e:
                self.showMessage.emit(hglib.tounicode(str(e)))
        finally:
            self.refreshing = False

    def _reload(self):
        ui, repo = self.repo.ui, self.repo

        self.queueCombo.clear()
        self.queueListWidget.clear()
        self.fileListWidget.clear()

        ui.pushbuffer()
        mqmod.qqueue(ui, repo, list=True)
        out = ui.popbuffer()
        activestr = ' (active)' # TODO: not locale safe
        for i, qname in enumerate(out.splitlines()):
            if qname.endswith(activestr):
                current = i
                qname = qname[:-len(activestr)]
            self.queueCombo.addItem(hglib.tounicode(qname))
        self.queueCombo.setCurrentIndex(current)

        # TODO: maintain current selection
        applied = set([p.name for p in repo.mq.applied])
        items = []
        for idx, patch in enumerate(repo.mq.series):
            item = QListWidgetItem(hglib.tounicode(patch))
            if patch in applied:
                f = item.font()
                f.setWeight(QFont.Bold)
                item.setFont(f)
            patchguards = repo.mq.series_guards[idx]
            if patchguards:
                uguards = hglib.tounicode(patchguards)
            else:
                uguards = _('no guards')
            uname = hglib.tounicode(patch)
            item.setToolTip(u'%s: %s' % (uname, uguards))
            items.append(item)
        for item in reversed(items):
            self.queueListWidget.addItem(item)

        self.messages = []
        for patch in repo.mq.series:
            ctx = repo.changectx(patch)
            msg = ctx.description()
            if msg:
                self.messages.append((patch, msg))
        self.msgHistoryCombo.reset(self.messages)

        # update enabled states of qtbarhbox buttons
        # refresh self.revisionOrCommitBtn

        # refresh self.messageEditor with qtip description, if not new
        # set self.patchNameLE to qtip patch name, if not new
        # refresh self.qnewOrRefreshBtn
        # refresh self.fileListWidget
        self.refreshSelectedGuards()

    def refreshSelectedGuards(self):
        count, total = 0, 0
        self.guardSelBtn.setText(_('Guards: %d/%d') % (count, total))

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

    def loadConfigs(self):
        'Load history, etc, from QSettings instance'
        s = QSettings()
        self.splitter.restoreState(s.value('mq/splitter').toByteArray())
        userhist = s.value('commit/userhist').toStringList()
        self.opts['userhist'] = [hglib.fromunicode(u) for u in userhist if u]
        if not self.parent():
            self.restoreGeometry(s.value('mq/geom').toByteArray())

    def storeConfigs(self):
        'Save history, etc, in QSettings instance'
        s = QSettings()
        s.setValue('mq/splitter', self.splitter.saveState())
        if not self.parent():
            s.setValue('mq/geom', self.saveGeometry())

    def canExit(self):
        self.storeConfigs()
        return not self.cmd.core.running()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.cmd.core.running():
                self.cmd.cancel()
            elif not self.parent() and self.canExit():
                self.close()
        else:
            return super(MQWidget, self).keyPressEvent(event)



class PatchMessageCombo(QComboBox):
    def __init__(self, parent):
        super(PatchMessageCombo, self).__init__(parent)
        self.reset([])

    def reset(self, msglist):
        self.clear()
        self.addItem(_('Patch commit messages...'))
        self.loaded = False
        self.msglist = msglist

    def showPopup(self):
        if not self.loaded and self.msglist:
            self.clear()
            for patch, message in self.msglist:
                sum = message.split('\n', 1)[0][:70]
                self.addItem(hglib.tounicode('%s: %s' % (patch, sum)))
            self.loaded = True
        if self.loaded:
            super(PatchMessageCombo, self).showPopup()



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

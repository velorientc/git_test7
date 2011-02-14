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
from tortoisehg.hgqt import qtlib, cmdui, rejects, commit, qscilib
from tortoisehg.hgqt import qqueue, fileview

# TODO: Disable MQ toolbar while cmdui.Runner is busy

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
        layout.setSpacing(4)
        self.setLayout(layout)

        # top toolbar
        tbarhbox = QHBoxLayout()
        tbarhbox.setSpacing(5)
        self.layout().addLayout(tbarhbox, 0)
        self.queueCombo = QComboBox()
        self.optionsBtn = QPushButton(_('Options'))
        self.msgSelectCombo = PatchMessageCombo(self)
        tbarhbox.addWidget(self.queueCombo)
        tbarhbox.addWidget(self.optionsBtn)
        tbarhbox.addWidget(self.msgSelectCombo, 1)

        # main area consists of a three-way horizontal splitter
        self.splitter = splitter = QSplitter()
        self.layout().addWidget(splitter, 1)
        splitter.setOrientation(Qt.Horizontal)
        splitter.setChildrenCollapsible(True)
        splitter.setObjectName('splitter')

        self.queueFrame = QFrame(splitter)
        self.messageFrame = QFrame(splitter)
        self.fileview = fileview.HgFileView(repo, splitter)

        self.fileview.showMessage.connect(self.showMessage)
        self.fileview.setContext(repo[None])
        self.fileview.shelveToolExited.connect(self.reload)

        # Patch Queue Frame
        layout = QVBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)
        self.queueFrame.setLayout(layout)

        qtbarhbox = QHBoxLayout()
        qtbarhbox.setSpacing(5)
        layout.addLayout(qtbarhbox, 0)
        qtbarhbox.setContentsMargins(0, 0, 0, 0)
        self.qpushAllBtn = tb = QToolButton()
        tb.setIcon(qtlib.geticon('hg-qpush-all'))
        tb.setToolTip(_('Apply all patches'))
        self.qpushBtn = tb = QToolButton()
        tb.setIcon(qtlib.geticon('hg-qpush'))
        tb.setToolTip(_('Apply one patch'))
        self.setGuardsBtn = tb = QToolButton()
        tb.setIcon(qtlib.geticon('hg-qguard'))
        tb.setToolTip(_('Configure guards for selected patch'))
        self.qpushMoveBtn = tb = QToolButton()
        tb.setIcon(qtlib.geticon('thg-qreorder'))
        tb.setToolTip(_('Apply selected patch next (change queue order)'))
        self.qdeleteBtn = tb = QToolButton()
        tb.setIcon(qtlib.geticon('filedelete'))
        tb.setToolTip(_('Delete selected patches'))
        self.qpopBtn = tb = QToolButton()
        tb.setIcon(qtlib.geticon('hg-qpop'))
        tb.setToolTip(_('Unapply one patch'))
        self.qpopAllBtn = tb = QToolButton()
        tb.setIcon(qtlib.geticon('hg-qpop-all'))
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

        self.revisionOrCommitBtn = QPushButton()
        layout.addWidget(self.revisionOrCommitBtn, 0)

        # Message Frame
        layout = QVBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)
        self.messageFrame.setLayout(layout)

        mtbarhbox = QHBoxLayout()
        mtbarhbox.setSpacing(8)
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

        self.fileListWidget = QListWidget(self)
        self.fileListWidget.currentRowChanged.connect(self.onFileSelected)
        layout.addWidget(self.fileListWidget, 2)

        qrefhbox = QHBoxLayout()
        layout.addLayout(qrefhbox, 0)
        qrefhbox.setContentsMargins(0, 0, 0, 0)
        self.qqueueBtn = QPushButton(_('Manage queues'))
        self.qqueueBtn.setMinimumWidth(150)
        self.qnewOrRefreshBtn = QPushButton(_('QRefresh'))
        qrefhbox.addWidget(self.qqueueBtn)
        qrefhbox.addStretch(1)
        qrefhbox.addWidget(self.qnewOrRefreshBtn)

        # Command runner and connections...
        self.cmd = cmdui.Runner(_('Patch Queue'), parent == None, self)
        self.cmd.output.connect(self.output)
        self.cmd.makeLogVisible.connect(self.makeLogVisible)
        self.cmd.progress.connect(self.progress)
        self.cmd.commandFinished.connect(self.onCommandFinished)

        self.qqueueBtn.clicked.connect(self.launchQQueueTool)
        self.optionsBtn.clicked.connect(self.launchOptionsDialog)
        self.revisionOrCommitBtn.clicked.connect(self.qinitOrCommit)
        self.msgSelectCombo.activated.connect(self.onMessageSelected)
        self.queueListWidget.currentRowChanged.connect(self.onPatchSelected)
        self.queueListWidget.itemActivated.connect(self.onGotoPatch)
        self.queueListWidget.itemChanged.connect(self.onRenamePatch)
        self.qpushAllBtn.clicked.connect(self.onPushAll)
        self.qpushBtn.clicked.connect(self.onPush)
        self.qpushMoveBtn.clicked.connect(self.onPushMove)
        self.qpopAllBtn.clicked.connect(self.onPopAll)
        self.qpopBtn.clicked.connect(self.onPop)
        self.setGuardsBtn.clicked.connect(self.onGuardConfigure)
        self.qdeleteBtn.clicked.connect(self.onDelete)
        self.newCheckBox.toggled.connect(self.onNewModeToggled)
        self.qnewOrRefreshBtn.clicked.connect(self.onQNewOrQRefresh)

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

    def getUserOptions(self, *optionlist):
        out = []
        for opt in optionlist:
            if opt not in self.opts:
                continue
            val = self.opts[opt]
            if val is False:
                continue
            elif val is True:
                out.append('--' + opt)
            else:
                out.append('--' + opt)
                out.append(val)
        return out

    @pyqtSlot()
    def onConfigChanged(self):
        'Repository is reporting its config files have changed'
        self.messageEditor.refresh(self.repo)
        self.fileview.setContext(self.repo[None])

    @pyqtSlot()
    def onRepositoryChanged(self):
        'Repository is reporting its changelog has changed'
        self.reload()

    @pyqtSlot(int)
    def onCommandFinished(self, ret):
        self.repo.decrementBusyCount()
        if ret is not 0:
            pass # TODO: look for reject notifications

    @pyqtSlot()
    def onPushAll(self):
        if self.cmd.running():
            return
        self.repo.incrementBusyCount()
        cmdline = ['qpush', '-R', self.repo.root, '--all']
        cmdline += self.getUserOptions('force', 'exact')
        self.cmd.run(cmdline)

    @pyqtSlot()
    def onPush(self):
        if self.cmd.running():
            return
        self.repo.incrementBusyCount()
        cmdline = ['qpush', '-R', self.repo.root]
        cmdline += self.getUserOptions('force', 'exact')
        self.cmd.run(cmdline)

    @pyqtSlot()
    def onPopAll(self):
        if self.cmd.running():
            return
        self.repo.incrementBusyCount()
        cmdline = ['qpop', '-R', self.repo.root, '--all']
        cmdline += self.getUserOptions('force')
        self.cmd.run(cmdline)

    @pyqtSlot()
    def onPop(self):
        if self.cmd.running():
            return
        self.repo.incrementBusyCount()
        cmdline = ['qpop', '-R', self.repo.root]
        cmdline += self.getUserOptions('force')
        self.cmd.run(cmdline)

    @pyqtSlot()
    def onPushMove(self):
        if self.cmd.running():
            return
        patch = self.queueListWidget.currentItem()._thgpatch
        cmdline = ['qpush', '-R', self.repo.root]
        cmdline += self.getUserOptions('force')
        cmdline += ['--move', '--', patch]
        self.repo.incrementBusyCount()
        self.cmd.run(cmdline)

    @pyqtSlot()
    def onGuardConfigure(self):
        item = self.queueListWidget.currentItem()
        patch = item._thgpatch
        if item._thgguards:
            uguards = hglib.tounicode(' '.join(item._thgguards))
        else:
            uguards = ''
        new, ok = QInputDialog.getText(self,
                      _('Configure guards'),
                      _('Input new guards for %s:') % hglib.tounicode(patch),
                      text=uguards, flags=Qt.Sheet)
        if not ok or new == uguards:
            return
        guards = []
        for guard in hglib.fromunicode(new).split(' '):
            guard = guard.strip()
            if not guard:
                continue
            if not (guard[0] == '+' or guard[0] == '-'):
                self.showMessage.emit(_('Guards must begin with "+" or "-"'))
                continue
            guards.append(guard)
        cmdline = ['qguard', '-R', self.repo.root, '--', patch]
        if guards:
            cmdline += guards
        else:
            cmdline.insert(3, '--none')
        if self.cmd.running():
            return
        self.repo.incrementBusyCount()
        self.cmd.run(cmdline)

    @pyqtSlot()
    def onDelete(self):
        from tortoisehg.hgqt import qdelete
        patch = self.queueListWidget.currentItem()._thgpatch
        dlg = qdelete.QDeleteDialog(self.repo, [patch], self)
        dlg.finished.connect(dlg.deleteLater)
        if dlg.exec_() == QDialog.Accepted:
            self.reload()

    #@pyqtSlot(QListWidgetItem)
    def onGotoPatch(self, item):
        'Patch has been activated (return), issue qgoto'
        if self.cmd.running():
            return
        cmdline = ['qgoto', '-R', self.repo.root]
        cmdline += self.getUserOptions('force')
        cmdline += ['--', item._thgpatch]
        self.repo.incrementBusyCount()
        self.cmd.run(cmdline)

    #@pyqtSlot(QListWidgetItem)
    def onRenamePatch(self, item):
        'Patch has been renamed, issue qrename'
        if self.cmd.running():
            return
        self.repo.incrementBusyCount()
        self.cmd.run(['qrename', '-R', self.repo.root, '--',
                      item._thgpatch, hglib.fromunicode(item.text())])

    @pyqtSlot(int)
    def onPatchSelected(self, row):
        'Patch has been selected, update buttons'
        if self.refreshing:
            return
        if row >= 0:
            patch = self.queueListWidget.item(row)._thgpatch
            applied = set([p.name for p in self.repo.mq.applied])
            self.qdeleteBtn.setEnabled(patch not in applied)
            self.qpushMoveBtn.setEnabled(patch not in applied)
            self.setGuardsBtn.setEnabled(True)
        else:
            self.qdeleteBtn.setEnabled(False)
            self.qpushMoveBtn.setEnabled(False)
            self.setGuardsBtn.setEnabled(False)

    @pyqtSlot(int)
    def onFileSelected(self, row):
        if self.refreshing or row == -1:
            return
        text = hglib.fromunicode(self.fileListWidget.item(row).text())
        status = text[0]
        filename = text[2:]
        if self.newCheckBox.isChecked():
            rev = self.repo['.'].rev()
        else:
            rev = self.repo['qtip'].p1().rev()
        self.fileview.displayFile(filename, rev, status)

    @pyqtSlot(int)
    def onMessageSelected(self, row):
        if self.messageEditor.text() and self.messageEditor.isModified():
            d = QMessageBox.question(self, _('Confirm Discard Message'),
                        _('Discard current commit message?'),
                        QMessageBox.Ok | QMessageBox.Cancel)
            if d != QMessageBox.Ok:
                return
        self.setMessage(self.messages[row][1])
        self.messageEditor.setFocus()

    def setMessage(self, message):
        self.messageEditor.setText(message)
        lines = self.messageEditor.lines()
        if lines:
            lines -= 1
            pos = self.messageEditor.lineLength(lines)
            self.messageEditor.setCursorPosition(lines, pos)
            self.messageEditor.ensureLineVisible(lines)
            hs = self.messageEditor.horizontalScrollBar()
            hs.setSliderPosition(0)
        self.messageEditor.setModified(False)

    @pyqtSlot()
    def onQNewOrQRefresh(self):
        if self.newCheckBox.isChecked():
            name = hglib.fromunicode(self.patchNameLE.text())
            if not name:
                qtlib.ErrorMsgBox(_('Patch Name Required'),
                                  _('You must enter a patch name'))
                self.patchNameLE.setFocus()
                return
            cmdline = ['qnew', '--repository', self.repo.root, name]
        else:
            cmdline = ['qrefresh', '--repository', self.repo.root]
        message = self.messageEditor.text()
        if message:
            cmdline += ['--message=' + hglib.fromunicode(message)]
        cmdline += self.getUserOptions('user', 'currentuser', 'git',
                                       'date', 'currentdate')
        files = ['--']
        for row in xrange(self.fileListWidget.count()):
            item = self.fileListWidget.item(row)
            if item.checkState() == Qt.Checked:
                wfile = hglib.fromunicode(item.text()[2:])
                files.append(self.repo.wjoin(wfile))
        if len(files) > 1:
            cmdline += files
        else:
            cmdline += ['--exclude', self.repo.root]
        self.repo.incrementBusyCount()
        self.cmd.run(cmdline)

    @pyqtSlot()
    def qinitOrCommit(self):
        if os.path.isdir(self.repo.mq.join('.hg')):
            dlg = commit.CommitDialog([], dict(root=self.repo.mq.path), self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.exec_()
            self.reload()
        else:
            self.repo.incrementBusyCount()
            self.cmd.run(['qinit', '-c', '-R', self.repo.root])

    @pyqtSlot()
    def launchQQueueTool(self):
        dlg = qqueue.QQueueDialog(self.repo, self)
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
                if 'THGDEBUG' in os.environ:
                    import traceback
                    traceback.print_exc()
        finally:
            self.refreshing = False

    def _reload(self):
        ui, repo = self.repo.ui, self.repo

        self.queueCombo.clear()
        self.queueListWidget.clear()

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
        self.queueCombo.setEnabled(self.queueCombo.count() > 1)

        # TODO: maintain current selection
        applied = set([p.name for p in repo.mq.applied])
        self.allguards = set()
        items = []
        for idx, patch in enumerate(repo.mq.series):
            item = QListWidgetItem(hglib.tounicode(patch))
            if patch in applied: # applied
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            elif not repo.mq.pushable(idx)[0]: # guarded
                f = item.font()
                f.setItalic(True)
                item.setFont(f)
            patchguards = repo.mq.series_guards[idx]
            if patchguards:
                for guard in patchguards:
                    self.allguards.add(guard[1:])
                uguards = hglib.tounicode(', '.join(patchguards))
            else:
                uguards = _('no guards')
            uname = hglib.tounicode(patch)
            item._thgpatch = patch
            item._thgguards = patchguards
            item.setToolTip(u'%s: %s' % (uname, uguards))
            item.setFlags(Qt.ItemIsSelectable |
                          Qt.ItemIsEditable |
                          Qt.ItemIsEnabled)
            items.append(item)
        for item in reversed(items):
            self.queueListWidget.addItem(item)

        for guard in repo.mq.active():
            self.allguards.add(guard)
        self.refreshSelectedGuards()

        self.messages = []
        for patch in repo.mq.series:
            ctx = repo.changectx(patch)
            msg = ctx.description()
            if msg:
                self.messages.append((patch, msg))
        self.msgSelectCombo.reset(self.messages)

        if os.path.isdir(repo.mq.join('.hg')):
            self.revisionOrCommitBtn.setText(_('QCommit'))
        else:
            self.revisionOrCommitBtn.setText(_('Revision Queue'))

        self.qpushAllBtn.setEnabled(bool(repo.thgmqunappliedpatches))
        self.qpushBtn.setEnabled(bool(repo.thgmqunappliedpatches))
        self.qpushMoveBtn.setEnabled(False)
        self.qdeleteBtn.setEnabled(False)
        self.setGuardsBtn.setEnabled(False)
        self.qpopBtn.setEnabled(bool(applied))
        self.qpopAllBtn.setEnabled(bool(applied))

        pctx = repo.changectx('.')
        newmode = self.newCheckBox.isChecked()
        if 'qtip' in pctx.tags():
            self.fileListWidget.setEnabled(True)
            self.messageEditor.setEnabled(True)
            self.msgSelectCombo.setEnabled(True)
            self.qnewOrRefreshBtn.setEnabled(True)
            if not newmode:
                self.setMessage(pctx.description())
                name = repo.mq.applied[-1].name
                self.patchNameLE.setText(hglib.tounicode(name))
        else:
            self.fileListWidget.setEnabled(newmode)
            self.messageEditor.setEnabled(newmode)
            self.msgSelectCombo.setEnabled(newmode)
            self.qnewOrRefreshBtn.setEnabled(newmode)
            if not newmode:
                self.setMessage('')
                self.patchNameLE.setText('')
        self.patchNameLE.setEnabled(newmode)
        self.refreshFileListWidget()

    def onNewModeToggled(self, isChecked):
        if isChecked:
            self.fileListWidget.setEnabled(True)
            self.qnewOrRefreshBtn.setText(_('QNew'))
            self.qnewOrRefreshBtn.setEnabled(True)
            self.messageEditor.setEnabled(True)
            self.patchNameLE.setEnabled(True)
            self.patchNameLE.selectAll()
            self.patchNameLE.setFocus()
            self.setMessage('')
        else:
            self.qnewOrRefreshBtn.setText(_('QRefresh'))
            pctx = self.repo.changectx('.')
            if 'qtip' in pctx.tags():
                self.messageEditor.setEnabled(True)
                self.setMessage(pctx.description())
                name = self.repo.mq.applied[-1].name
                self.patchNameLE.setText(hglib.tounicode(name))
                self.qnewOrRefreshBtn.setEnabled(True)
                self.fileListWidget.setEnabled(True)
            else:
                self.messageEditor.setEnabled(False)
                self.qnewOrRefreshBtn.setEnabled(False)
                self.fileListWidget.setEnabled(False)
                self.patchNameLE.setText('')
                self.setMessage('')
            self.patchNameLE.setEnabled(False)
        self.refreshing = True
        try:
            try:
                self.refreshFileListWidget()
            except Exception, e:
                self.showMessage.emit(hglib.tounicode(str(e)))
                import traceback
                traceback.print_exc()
        finally:
            self.refreshing = False

    def refreshFileListWidget(self):
        # TODO: maintain selection, check state
        def addfiles(mode, files):
            for file in files:
                item = QListWidgetItem(u'%s %s' % (mode, hglib.tounicode(file)))
                item.setFlags(flags)
                item.setCheckState(Qt.Checked)
                self.fileListWidget.addItem(item)
        self.fileListWidget.clear()
        self.fileview.clearDisplay()
        pctx = self.repo.changectx('.')
        newmode = self.newCheckBox.isChecked()
        if not newmode and 'qtip' in pctx.tags():
            # Show qrefresh (qdiff) diffs
            M, A, R = self.repo.status(pctx.p1().node(), None)[:3]
        elif newmode:
            # Show qnew (working) diffs
            M, A, R = self.repo[None].status()[:3]
        else:
            return
        flags = Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
        addfiles(u'A', A)
        addfiles(u'M', M)
        addfiles(u'R', R)

    def refreshSelectedGuards(self):
        total = len(self.allguards)
        count = len(self.repo.mq.active())
        oldmenu = self.guardSelBtn.menu()
        if oldmenu:
            oldmenu.setParent(None)
        menu = QMenu(self)
        for guard in self.allguards:
            a = menu.addAction(hglib.tounicode(guard))
            a.setCheckable(True)
            a.setChecked(guard in self.repo.mq.active())
            a.triggered.connect(self.onGuardSelectionChange)
        self.guardSelBtn.setMenu(menu)
        self.guardSelBtn.setText(_('Guards: %d/%d') % (count, total))

    def onGuardSelectionChange(self, isChecked):
        guard = hglib.fromunicode(self.sender().text())
        newguards = self.repo.mq.active()[:]
        if isChecked:
            newguards.append(guard)
        elif guard in newguards:
            newguards.remove(guard)
        cmdline = ['qselect', '-R', self.repo.root]
        cmdline += newguards or ['--none']
        self.repo.incrementBusyCount()
        self.cmd.run(cmdline)

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
        self.messageEditor.loadSettings(s, 'mq/editor')
        self.fileview.loadSettings(s, 'mq/fileview')
        if not self.parent():
            self.restoreGeometry(s.value('mq/geom').toByteArray())

    def storeConfigs(self):
        'Save history, etc, in QSettings instance'
        s = QSettings()
        s.setValue('mq/splitter', self.splitter.saveState())
        self.messageEditor.saveSettings(s, 'mq/editor')
        self.fileview.saveSettings(s, 'mq/fileview')
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

        self.gitcb = QCheckBox(
            _('Force use of git extended diff format (--git)'))
        layout.addRow(self.gitcb, None)

        self.forcecb = QCheckBox(
            _('Force push or pop (--force)'))
        layout.addRow(self.forcecb, None)

        self.exactcb = QCheckBox(
            _('Apply patch to its recorded parent (--exact)'))
        layout.addRow(self.exactcb, None)

        self.currentdatecb = QCheckBox(
            _('Update date field with current date (--currentdate)'))
        layout.addRow(self.currentdatecb, None)

        self.datele = QLineEdit()
        layout.addRow(QLabel(_('Specify an explicit date:')), self.datele)

        self.currentusercb = QCheckBox(
            _('Update author field with current user (--currentuser)'))
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
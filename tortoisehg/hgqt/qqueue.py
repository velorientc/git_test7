# qqueue.py - TortoiseHg dialog for managing multiple MQ patch queues
#
# Copyright 2011 Johan Samyn <johan.samyn@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import ui as uimod
from mercurial import util
from hgext import mq

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import thgrepo, qtlib, cmdui
from tortoisehg.util import paths, hglib

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# TODO:
# - Renaming a non-active queue ? (Why is it hg doesn't allow this ?)

class QQueueDialog(QDialog):
    """Dialog for managing multiple MQ patch queues"""

    output = pyqtSignal(QString, QString)
    makeLogVisible = pyqtSignal(bool)

    def __init__(self, repo, parent=None):
        super(QQueueDialog, self).__init__(parent)

        self.setWindowIcon(qtlib.geticon('thg_logo'))
        self.setWindowTitle(_('Manage MQ patch queues'))
        self.setWindowFlags(self.windowFlags()
                            & ~Qt.WindowContextHelpButtonHint)

        self.activequeue = ''
        self.repo = repo
        repo.repositoryChanged.connect(self.reload)

        layout = QVBoxLayout()
        layout.setMargin(4)
        self.setLayout(layout)

        hbr = QHBoxLayout()
        hbr.setMargin(2)
        layout.addLayout(hbr)
        rlbl = QLabel(_('Repository:'))
        hbr.addWidget(rlbl)
        rle = QLineEdit()
        hbr.addWidget(rle)
        rle.setFont(qtlib.getfont('fontlist').font())
        rle.setText(repo.displayname)
        rle.setReadOnly(True)
        rle.setFocusPolicy(Qt.NoFocus)

        topsep = qtlib.LabeledSeparator('')
        layout.addWidget(topsep)

        hbl = QHBoxLayout()
        hbl.setMargin(2)
        layout.addLayout(hbl)

        qvb = QVBoxLayout()
        hbl.addLayout(qvb)

        qlbl = QLabel(_('Patch queues:'))
        qvb.addWidget(qlbl)
        ql = QListWidget(self)
        qvb.addWidget(ql)
        ql.currentRowChanged.connect(self.updateUI)

        vbb = QVBoxLayout()
        vbb.setMargin(2)
        qvb.addLayout(vbb)

        hqbtntop = QHBoxLayout()
        vbb.addLayout(hqbtntop)
        hqbtnmid = QHBoxLayout()
        vbb.addLayout(hqbtnmid)
        hqbtnbot = QHBoxLayout()
        vbb.addLayout(hqbtnbot)

        btrel = QPushButton(_('Reload'))
        btrel.clicked.connect(self.reload)
        hqbtntop.addWidget(btrel)
        btact = QPushButton(_('Activate'))
        btact.clicked.connect(self.qqueueActivate)
        hqbtntop.addWidget(btact)
        btadd = QPushButton(_('Add'))
        btadd.clicked.connect(self.qqueueAdd)
        hqbtnmid.addWidget(btadd)
        btren = QPushButton(_('Rename'))
        btren.clicked.connect(self.qqueueRename)
        hqbtnmid.addWidget(btren)
        btdel = QPushButton(_('Delete'))
        btdel.clicked.connect(self.qqueueDelete)
        hqbtnbot.addWidget(btdel)
        btpur = QPushButton(_('Purge'))
        btpur.clicked.connect(self.qqueuePurge)
        hqbtnbot.addWidget(btpur)

        pvb = QVBoxLayout()
        hbl.addLayout(pvb)

        plbl = QLabel(_('Patches:'))
        pvb.addWidget(plbl)
        pl = QListWidget(self)
        pvb.addWidget(pl)

        botsep = qtlib.LabeledSeparator('')
        layout.addWidget(botsep)

        cmdlist = cmdui.Runner()
        cmdlist.output.connect(self.output)
        cmdlist.makeLogVisible.connect(self.makeLogVisible)
        cmd = cmdui.Runner()
        cmd.output.connect(self.output)
        cmd.makeLogVisible.connect(self.makeLogVisible)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Close)
        bb.button(BB.Close).clicked.connect(self.close)
        layout.addWidget(bb)

        self.setLayout(layout)
        self.ql = ql
        self.pl = pl
        self.btrel = btrel
        self.btact = btact
        self.btadd = btadd
        self.btren = btren
        self.btdel = btdel
        self.btpur = btpur
        self.bb = bb
        self.cmdlist = cmdlist
        self.cmd = cmd

        self.itemfont = None
        self.itemfontbold = None
        self._readsettings()
        self.reload()
        self.ql.setFocus()

    def setButtonState(self, state):
        if state:
            if self.ql.currentRow() != -1:
                q = hglib.fromunicode(self.ql.item(self.ql.currentRow()).text())
                self.btact.setEnabled(q != self.activequeue)
                self.btren.setEnabled(q == self.activequeue and q != 'patches')
                self.btdel.setEnabled(q != 'patches')
                self.btpur.setEnabled(q != 'patches')
            else:
                self.btact.setEnabled(False)
                self.btren.setEnabled(False)
                self.btdel.setEnabled(False)
                self.btpur.setEnabled(False)
            self.btrel.setEnabled(True)
            self.btadd.setEnabled(True)
            self.bb.setEnabled(True)
        else:
            self.btrel.setEnabled(False)
            self.btact.setEnabled(False)
            self.btadd.setEnabled(False)
            self.btren.setEnabled(False)
            self.btdel.setEnabled(False)
            self.btpur.setEnabled(False)
            self.bb.setEnabled(False)

    @pyqtSlot()
    def updateUI(self):
        if self.ql.currentRow() != -1:
            self.showPatchesForQueue()
        self.setButtonState(True)
        self.bb.setEnabled(True)

    @pyqtSlot()
    def reload(self):
        def reloadFinished():
            self.repo.decrementBusyCount()
            output = self.cmdlist.core.rawoutput()
            self.showQueues(output)
            self.updateUI()
        cmdline = ['qqueue', '--repository', self.repo.root, '--list']
        self.cmdlist.commandFinished.connect(reloadFinished)
        self.repo.incrementBusyCount()
        self.cmdlist.run(cmdline)

    # This seems to return the cached data as it was just before the last
    # issued command. So I used the threaded method again.
    # def reload(self):
        # _ui = uimod.ui()
        # _ui.pushbuffer()
        # try:
            # opts = {'list': True}
            # mq.qqueue(_ui, self.repo, None, **opts)
        # except (util.Abort, EnvironmentError), e:
            # print e
        # output = _ui.popbuffer()
        # qtlib.InfoMsgBox('test', '<p>reload - output = %s</p>' % output)
        # self.showQueues(output)

    def showQueues(self, output):
        queues = output.rstrip('\n').split('\n')
        self.ql.clear()
        self.pl.clear()
        row_activeq = 0
        for i, q in enumerate(queues):
            item = QListWidgetItem(q)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled
                          | Qt.ItemIsDragEnabled)
            self.ql.addItem(item)
            if self.itemfont == None:
                self.itemfont = item.font()
                self.itemfontbold = self.itemfont
                self.itemfontbold.setBold(True)
            if 'active' in q:
                row_activeq = i
                self.activequeue = q[:-9]
                item.setText(self.activequeue)
                item.setFont(self.itemfontbold)
        self.ql.setCurrentRow(row_activeq)

    def showPatchesForQueue(self):
        currow = self.ql.currentRow()
        if currow == -1:
            return
        while currow > self.ql.count() - 1:
            currow -= 1
        q = hglib.fromunicode(self.ql.item(currow).text())
        self.pl.clear()
        patches = []
        if q == self.activequeue:
            patches = self.repo.mq.full_series
        else:
            if q == 'patches':
                sf = '/.hg/patches/series'
            else:
                sf = '/.hg/patches-%s/series' % q
            sf = self.repo.root + sf
            if os.path.exists(sf):
                with open(sf, 'r') as f:
                    patches = f.read().splitlines()
        for p in patches:
            item = QListWidgetItem(hglib.tounicode(p))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.pl.addItem(item)
        self.ql.setFocus()

    @pyqtSlot()
    def qqueueActivate(self):
        q = hglib.fromunicode(self.ql.item(self.ql.currentRow()).text())
        if q == self.activequeue:
            return
        if qtlib.QuestionMsgBox(_('Confirm patch queue switch'),
                _('Do you really want to activate patch queue \'%s\' ?' % q),
                parent=self, defaultbutton=QMessageBox.No):
            opts = [q]
            self.qqueueCommand(opts)

    @pyqtSlot()
    def qqueueAdd(self):
        title = _('TortoiseHg Prompt')
        # this is the only way I found to make that dialog wide enough :(
        label = QString(_('New patch queue name') + (' ' * 30))
        # WindowContextHelpButton still there :( after this ?
        dlg = QInputDialog(self, Qt.WindowFlags()
                              & ~Qt.WindowContextHelpButtonHint)
        qname, ok = dlg.getText(self, title, label)
        if qname and ok:
            opts = ['--create', hglib.fromunicode(qname)]
            self.qqueueCommand(opts)

    @pyqtSlot()
    def qqueueRename(self):
        q = hglib.fromunicode(self.ql.item(self.ql.currentRow()).text())
        if q == 'patches':
            return
        title = _('TortoiseHg Prompt')
        # this is the only way I found to make that dialog wide enough :(
        label = QString(_('Rename patch queue \'%s\' to' % q) + (' ' * 30))
        # WindowContextHelpButton still there :( after this ?
        dlg = QInputDialog(self, Qt.WindowFlags()
                              & ~Qt.WindowContextHelpButtonHint)
        newqname, ok = dlg.getText(self, title, label)
        if newqname:
            newqname = hglib.fromunicode(newqname)
        if newqname and ok:
            opts = ['--rename', newqname]
            self.qqueueCommand(opts)

    @pyqtSlot()
    def qqueueDelete(self):
        q = hglib.fromunicode(self.ql.item(self.ql.currentRow()).text())
        if q == 'patches':
            return
        if qtlib.QuestionMsgBox(_('Confirm patch queue delete'),
              _('Do you really want to delete patch queue \'%s\' ?'
              % q), parent=self, defaultbutton=QMessageBox.No):
            opts = ['--delete', q]
            self.qqueueCommand(opts)

    @pyqtSlot()
    def qqueuePurge(self):
        q = hglib.fromunicode(self.ql.item(self.ql.currentRow()).text())
        if q == 'patches':
            return
        if qtlib.QuestionMsgBox(_('Confirm patch queue purge'),
              _('<p>This will also erase de patchfiles on disk!</p>'
                '<p>Do you really want to purge patch queue \'%s\' ?</p>'
                % q), parent=self, defaultbutton=QMessageBox.No):
            opts = ['--purge', q]
            self.qqueueCommand(opts)

    def qqueueCommand(self, opts):
        self.setButtonState(False)
        def qqcmdFinished():
            self.repo.decrementBusyCount()
            # This seems to cause excessive refreshes ?!
            # See when using 'thgdbg qqueue' from the commandline.
            # But when not used, the data are not reshown after a command.
            # Is it ok to have 2 cmd threads in the same dialog ?
            self.reload()
            # self.updateUI()
        self.cmd.commandFinished.connect(qqcmdFinished)
        cmdline = ['qqueue', '--repository', self.repo.root] + opts
        self.repo.incrementBusyCount()
        self.cmd.run(cmdline)

    def accept(self):
        self._writesettings()
        QDialog.accept(self)

    def close(self, event):
        self._writesettings()
        QDialog.close(self)

    def _readsettings(self):
        s = QSettings()
        self.restoreGeometry(s.value('qqueue/geom').toByteArray())

    def _writesettings(self):
        s = QSettings()
        s.setValue('qqueue/geom', self.saveGeometry())

def run(ui, *pats, **opts):
    repo = thgrepo.repository(None, paths.find_root())
    if hasattr(repo, 'mq'):
        return QQueueDialog(repo)
    else:
        qtlib.ErrorMsgBox(_('TortoiseHg Error'),
            _('Please enable the MQ extension first.'))

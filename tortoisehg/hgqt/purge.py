# purge.py - working copy purge dialog, based on Mercurial purge extension
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import stat
import shutil

from mercurial import cmdutil

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, cmdui

from PyQt4.QtCore import *
from PyQt4.QtGui import *

class PurgeDialog(QDialog):

    progress = pyqtSignal(QString, object, QString, QString, object)
    showMessage = pyqtSignal(QString)

    def __init__(self, repo, parent):
        QDialog.__init__(self, parent)
        f = self.windowFlags()
        self.setWindowFlags(f & ~Qt.WindowContextHelpButtonHint)
        self.setLayout(QVBoxLayout())

        cb = QCheckBox(_('No unknown files found'))
        cb.setChecked(False)
        cb.setEnabled(False)
        self.layout().addWidget(cb)
        self.ucb = cb

        cb = QCheckBox(_('No ignored files found'))
        cb.setChecked(False)
        cb.setEnabled(False)
        self.layout().addWidget(cb)
        self.icb = cb

        cb = QCheckBox(_('No trash files found'))
        cb.setChecked(False)
        cb.setEnabled(False)
        self.layout().addWidget(cb)
        self.tcb = cb

        self.foldercb = QCheckBox(_('Delete empty folders'))
        self.foldercb.setChecked(True)
        self.layout().addWidget(self.foldercb)
        self.hgfilecb = QCheckBox(_('Preserve files beginning with .hg'))
        self.hgfilecb.setChecked(True)
        self.layout().addWidget(self.hgfilecb)

        self.stbar = cmdui.ThgStatusBar(self)
        self.stbar.setSizeGripEnabled(False)
        self.progress.connect(self.stbar.progress)
        self.showMessage.connect(self.stbar.showMessage)
        self.layout().addWidget(self.stbar)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.bb = bb
        self.layout().addWidget(bb)

        self.setWindowTitle('%s - purge' % repo.displayname)
        self.setWindowIcon(qtlib.geticon('hg-purge'))
        self.repo = repo

        self.bb.setEnabled(False)
        self.progress.emit(*cmdui.startProgress(_('Checking'), '...'))
        s = QSettings()
        desktopgeom = qApp.desktop().availableGeometry()
        self.resize(desktopgeom.size() * 0.25)
        self.restoreGeometry(s.value('purge/geom').toByteArray())
        QTimer.singleShot(0, self.checkStatus)

    def checkStatus(self):
        repo = self.repo
        class CheckThread(QThread):
            def __init__(self, parent):
                QThread.__init__(self, parent)
                self.files = (None, None)
                self.error = None

            def run(self):
                try:
                    wctx = repo[None]
                    wctx.status(ignored=True, unknown=True)
                    trashcan = repo.join('Trashcan')
                    if os.path.isdir(trashcan):
                        trash = os.listdir(trashcan)
                    else:
                        trash = []
                    self.files = wctx.unknown(), wctx.ignored(), trash
                except Exception, e:
                    self.error = str(e)

        def completed():
            self.th.wait()
            self.files = self.th.files
            self.bb.setEnabled(True)
            self.progress.emit(*cmdui.stopProgress(_('Checking')))
            if self.th.error:
                self.showMessage.emit(hglib.tounicode(self.th.error))
            else:
                self.showMessage.emit(_('Ready to purge.'))
                U, I, T = self.files
                if U:
                    self.ucb.setText(_('Delete %d unknown files') % len(U))
                    self.ucb.setChecked(True)
                    self.ucb.setEnabled(True)
                if I:
                    self.icb.setText(_('Delete %d ignored files') % len(I))
                    self.icb.setChecked(True)
                    self.icb.setEnabled(True)
                if T:
                    self.tcb.setText(_('Delete %d files in .hg/Trashcan') %
                                     len(T))
                    self.tcb.setChecked(True)
                    self.tcb.setEnabled(True)

        self.th = CheckThread(self)
        self.th.finished.connect(completed)
        self.th.start()

    def reject(self):
        s = QSettings()
        s.setValue('purge/geom', self.saveGeometry())
        super(PurgeDialog, self).reject()

    def accept(self):
        unknown = self.ucb.isChecked()
        ignored = self.icb.isChecked()
        trash = self.tcb.isChecked()
        delf = self.foldercb.isChecked()
        keep = self.hgfilecb.isChecked()

        if not (unknown or ignored or trash or delf):
            QDialog.accept(self)
            return
        if not qtlib.QuestionMsgBox(_('Confirm file deletions'),
            _('Are you sure you want to delete these files and/or folders?')):
            return

        def completed():
            self.th.wait()
            if self.th.failures:
                qtlib.InfoMsgBox(_('Deletion failures'),
                    _('Unable to delete %d files or folders') %
                                 len(self.th.failures), parent=self)
            self.reject()

        self.th = PurgeThread(self.repo, ignored, unknown, trash, delf, keep, self)
        self.th.progress.connect(self.progress)
        self.th.showMessage.connect(self.showMessage)
        self.th.finished.connect(completed)
        self.th.start()

class PurgeThread(QThread):
    progress = pyqtSignal(QString, object, QString, QString, object)
    showMessage = pyqtSignal(QString)

    def __init__(self, repo, ignored, unknown, trash, delf, keephg, parent):
        super(PurgeThread, self).__init__(parent)
        self.failures = 0
        self.repo = repo
        self.ignored = ignored
        self.unknown = unknown
        self.trash = trash
        self.delfolders = delf
        self.keephg = keephg

    def run(self):
        self.failures = self.purge(self.repo, self.ignored, self.unknown,
                                   self.trash, self.delfolders, self.keephg)

    def purge(self, repo, ignored, unknown, trash, delfolders, keephg):
        directories = []
        failures = []

        if trash:
            self.showMessage.emit(_('Deleting trash folder...'))
            trashcan = self.repo.join('Trashcan')
            try:
                shutil.rmtree(trashcan)
            except EnvironmentError:
                failures.append(trashcan)

        self.showMessage.emit('')
        match = cmdutil.match(repo, [], {})
        match.dir = directories.append
        status = repo.status(match=match, ignored=ignored, unknown=unknown)
        files = status[4] + status[5]

        def remove(remove_func, name):
            try:
                if keephg and name.startswith('.hg'):
                    return
                remove_func(repo.wjoin(name))
            except EnvironmentError:
                failures.append(name)

        def removefile(path):
            try:
                os.remove(path)
            except OSError:
                # read-only files cannot be unlinked under Windows
                s = os.stat(path)
                if (s.st_mode & stat.S_IWRITE) != 0:
                    raise
                os.chmod(path, stat.S_IMODE(s.st_mode) | stat.S_IWRITE)
                os.remove(path)

        for i, f in enumerate(sorted(files)):
            data = ('deleting', i, f, '', len(files))
            self.progress.emit(*data)
            remove(removefile, f)
        data = ('deleting', None, '', '', len(files))
        self.progress.emit(*data)
        self.showMessage.emit(_('Deleted %d files') % len(files))

        if delfolders:
            for i, f in enumerate(sorted(directories, reverse=True)):
                if not os.listdir(repo.wjoin(f)):
                    data = ('rmdir', i, f, '', len(directories))
                    self.progress.emit(*data)
                    remove(os.rmdir, f)
            data = ('rmdir', None, f, '', len(directories))
            self.progress.emit(*data)
            self.showMessage.emit(_('Deleted %d files and %d folders') % (
                                  len(files), len(directories)))
        return failures

def run(ui, *pats, **opts):
    from tortoisehg.hgqt import thgrepo
    from tortoisehg.util import paths
    repo = thgrepo.repository(ui, path=paths.find_root())
    return PurgeDialog(repo, None)

# status.py - working copy browser
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import stat

from mercurial import cmdutil

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib

from PyQt4.QtCore import *
from PyQt4.QtGui import *

def purge(repo, ignored, unknown, delfolders, keephg):
    directories = []
    failures = []

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

    match = cmdutil.match(repo, [], {})
    match.dir = directories.append
    status = repo.status(match=match, ignored=ignored, unknown=unknown)

    for f in sorted(status[4] + status[5]):
        remove(removefile, f)

    if delfolders:
        for f in sorted(directories, reverse=True):
            if not os.listdir(repo.wjoin(f)):
                remove(os.rmdir, f)
    return failures


class PurgeDialog(QDialog):
    def __init__(self, repo, unknown, ignored, parent):
        QDialog.__init__(self, parent)
        self.setLayout(QVBoxLayout())
        if unknown:
            cb = QCheckBox(_('Delete %d unknown files') % len(unknown))
            cb.setChecked(True)
            self.layout().addWidget(cb)
            self.ucb = cb
        if ignored:
            cb = QCheckBox(_('Delete %d ignored files') % len(ignored))
            cb.setChecked(True)
            self.layout().addWidget(cb)
            self.icb = cb
        self.foldercb = QCheckBox(_('Delete empty folders'))
        self.foldercb.setChecked(True)
        self.layout().addWidget(self.foldercb)
        self.hgfilecb = QCheckBox(_('Preserve files beginning with .hg'))
        self.hgfilecb.setChecked(True)
        self.layout().addWidget(self.hgfilecb)
        self.files = (unknown, ignored)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.bb = bb
        self.layout().addWidget(bb)

        self.setWindowTitle('%s - purge' % repo.displayname)
        self.repo = repo

    def accept(self):
        U, I = self.files
        unknown = len(U) and self.ucb.isChecked()
        ignored = len(I) and self.icb.isChecked()
        delf = self.foldercb.isChecked()
        keep = self.hgfilecb.isChecked()

        if not (unknown or ignored or delf):
            QDialog.accept(self)
            return
        if not qtlib.QuestionMsgBox(_('Confirm file deletions'),
            _('Are you sure you want to delete these files and/or folders?')):
            return

        failures = purge(self.repo, ignored, unknown, delf, keep)
        if failures:
            qtlib.InfoMsgBox(_('Deletion failures'),
                _('Unable to delete %d files or folders') % len(failures), self)
        QDialog.accept(self)

def run(ui, *pats, **opts):
    from tortoisehg.hgqt import thgrepo
    from tortoisehg.util import paths
    try:
        repo = thgrepo.repository(ui, path=paths.find_root())
        wctx = repo[None]
        wctx.status(ignored=True, unknown=True)
    except Exception, e:
        qtlib.InfoMsgBox(_('Repository Error'),
                         _('Unable to query unrevisioned files\n') +
                         hglib.tounicode(str(e)))
        return None
    U, I = wctx.unknown(), wctx.ignored()
    if not U and not I:
        qtlib.InfoMsgBox(_('No unrevisioned files'),
                         _('There are no purgable unrevisioned files'))
        return None
    return PurgeDialog(repo, U, I, None)

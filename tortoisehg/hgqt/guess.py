# guess.py - TortoiseHg's dialogs for detecting copies and renames
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import hg, ui, mdiff, cmdutil, util, error, similar

from tortoisehg.util import hglib, shlib, paths

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# Technical Debt
#  Give simularity routines a repo.ui that catches progress reports

class DetectRenameDialog(QDialog):
    'Detect renames after they occur'

    matchAccepted = pyqtSignal()

    def __init__(self, root=None, parent=None):
        QDialog.__init__(self, parent)

        repo = hg.repository(ui.ui(), path=paths.find_root(root))
        self.repo = repo

        reponame = hglib.get_reponame(repo)
        self.setWindowTitle(_('Detect Copies/Renames in %s') % reponame)
        s = QSettings()
        self.restoreGeometry(s.value('guess/geom').toByteArray())

        layout = QVBoxLayout()
        self.setLayout(layout)

        tophbox = QHBoxLayout()
        layout.addLayout(tophbox)

        lbl = QLabel(_('Minimum Simularity Percentage'))
        tophbox.addWidget(lbl)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setTickInterval(10)
        slider.setTickPosition(QSlider.TicksBelow)
        tophbox.addWidget(slider)
        lbl.setBuddy(slider)

        # vsplit for top & diff
        vsplit = QSplitter(Qt.Horizontal)
        vsplit.restoreState(s.value('guess/vsplit-state').toByteArray())
        utframe = QFrame(vsplit)
        matchframe = QFrame(vsplit)

        utvbox = QVBoxLayout()
        utframe.setLayout(utvbox)
        matchvbox = QVBoxLayout()
        matchframe.setLayout(matchvbox)

        hsplit = QSplitter(Qt.Vertical)
        hsplit.restoreState(s.value('guess/hsplit-state').toByteArray())
        layout.addWidget(hsplit)
        hsplit.addWidget(vsplit)

        utlbl = QLabel(_('<b>Unrevisioned Files</b>'))
        utvbox.addWidget(utlbl)
        self.unrevlist = QListWidget()
        self.unrevlist.setSelectionMode(QAbstractItemView.MultiSelection)
        utvbox.addWidget(self.unrevlist)

        matchlbl = QLabel(_('<b>Candidate Matches</b>'))
        matchvbox.addWidget(matchlbl)
        token = QListWidget()
        matchvbox.addWidget(token)

        diffframe = QFrame(hsplit)
        diffvbox = QVBoxLayout()
        diffframe.setLayout(diffvbox)

        difflabel = QLabel(_('<b>Differences from Source to Dest</b>'))
        diffvbox.addWidget(difflabel)
        difftb = QTextBrowser()
        diffvbox.addWidget(difftb)
        self.difftb = difftb

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Close)
        self.connect(bb, SIGNAL("accepted()"), self, SLOT("accept()"))
        self.connect(bb, SIGNAL("rejected()"), self, SLOT("reject()"))
        layout.addWidget(bb)
        self.bb = bb

        self.vsplit, self.hsplit = vsplit, hsplit
        QTimer.singleShot(0, self.refresh)

    def refresh(self):
        hglib.invalidaterepo(self.repo)
        wctx = self.repo[None]
        wctx.status(unknown=True)
        self.unrevlist.clear()
        self.unrevlcl = []
        for u in wctx.unknown():
            self.unrevlcl.append(u)
        for a in wctx.added():
            if not wctx[a].renamed():
                self.unrevlcl.append(a)
        for x in self.unrevlcl:
            self.unrevlist.addItem(hglib.tounicode(x))

    def findRenames(self, copy=False):
        'User pressed "find renames" button'
        # get selected rows from self.unrevlist
        # pass to search thread

    def findCopies(self):
        'User pressed "find copies" button'
        # call rename function with simularity = 100%
        self.findRenames(copy=True)

    def acceptMatch(self):
        'User pressed "accept match" button'
        hglib.invalidaterepo(self.repo)
        canmodel, upaths = self.cantree.get_selection().get_selected_rows()
        for path in upaths:
            row = canmodel[path]
            src, usrc, dest, udest, percent, sensitive = row
            if not sensitive:
                continue
            if not os.path.exists(self.repo.wjoin(src)):
                # Mark missing rename source as removed
                self.repo.remove([src])
            self.repo.copy(src, dest)
            shlib.shell_notify([self.repo.wjoin(src), self.repo.wjoin(dest)])
            # Mark all rows with this target file as non-sensitive
            for row in canmodel:
                if row[2] == dest:
                    row[5] = False
        # emit matchAccepted()
        self.refresh()

    def showDiff(self):
        'User selected a row in the candidate tree'
        hglib.invalidaterepo(self.repo)
        src, usrc, dest, udest, percent, sensitive = row
        ctx = self.repo['.']
        aa = self.repo.wread(dest)
        rr = ctx.filectx(src).data()
        opts = mdiff.defaultopts
        difftext = mdiff.unidiff(rr, '', aa, '', src, dest, None, opts=opts)
        if not difftext:
            l = _('== %s and %s have identical contents ==\n\n') % (src, dest)
        # pass through qtlib.difflabel and htmlui

    def accept(self):
        s = QSettings()
        s.setValue('guess/geom', self.saveGeometry())
        s.setValue('guess/vsplit-state', self.vsplit.saveState())
        s.setValue('guess/hsplit-state', self.hsplit.saveState())
        QDialog.accept(self)

    def reject(self):
        # cancel active thread
        s = QSettings()
        s.setValue('guess/geom', self.saveGeometry())
        s.setValue('guess/vsplit-state', self.vsplit.saveState())
        s.setValue('guess/hsplit-state', self.hsplit.saveState())
        QDialog.reject(self)


class RenameSearchThread(QThread):
    '''Background thread for searching repository history'''
    match = pyqtSignal()
    error = pyqtSignal()
    searchComplete = pyqtSignal()

    def __init__(self, repo, ufiles, minpct, copies):
        super(RenameSearchThread, self).__init__()
        self.repo = repo
        self.ufiles = ufiles
        self.minpct = minpct
        self.copies = copies

    def run(self):
        try:
            self.search(self.repo)
        except Exception, e:
            self.error.emit(hglib.tounicode(str(e)))
            print e
        self.searchComplete.emit()

    def search(repo):
        hglib.invalidaterepo(repo)
        wctx = repo[None]
        pctx = repo['.']
        if self.copies:
            wctx.status(clean=True)
            srcs = wctx.removed() + wctx.deleted()
            srcs += wctx.modified() + wctx.clean()
        else:
            srcs = wctx.removed() + wctx.deleted()
        added = [wctx[a] for a in self.ufiles]
        removed = [pctx[a] for a in srcs if a in pctx]
        # do not consider files of zero length
        added = sorted([fctx for fctx in added if fctx.size() > 0])
        removed = sorted([fctx for fctx in removed if fctx.size() > 0])
        for o, n in similar._findexactmatches(repo, added, removed):
            old, new = o.path(), n.path()
            self.match.emit( [old, new, '100%'] )
        if self.minpct < 1.0:
            for o, n, s in similar._findsimilarmatches(repo, added, removed,
                                                       self.minpct):
                old, new = o.path(), n.path()
                self.match.emit( [old, new, '%d%%' % (s*100)] )

def run(ui, *pats, **opts):
    return DetectRenameDialog()

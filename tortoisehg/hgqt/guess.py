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
from tortoisehg.hgqt import qtlib, htmlui

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# Technical Debt
#  Add a progress/status bar, connect to thread errors
#  Give simularity routines a repo.ui that catches progress reports
#  Disable buttons when lists are empty

class DetectRenameDialog(QDialog):
    'Detect renames after they occur'

    matchAccepted = pyqtSignal()

    def __init__(self, parent=None, root=None, *pats):
        QDialog.__init__(self, parent)

        repo = hg.repository(ui.ui(), path=paths.find_root(root))
        self.repo = repo
        self.pats = pats
        self.thread = None

        reponame = hglib.get_reponame(repo)
        self.setWindowTitle(_('Detect Copies/Renames in %s') % reponame)
        s = QSettings()
        self.restoreGeometry(s.value('guess/geom').toByteArray())

        layout = QVBoxLayout()
        self.setLayout(layout)

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
        self.unrevlist.setSelectionMode(QAbstractItemView.ExtendedSelection)
        utvbox.addWidget(self.unrevlist)

        simhbox = QHBoxLayout()
        utvbox.addLayout(simhbox)
        lbl = QLabel()
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setTickInterval(10)
        slider.setPageStep(10)
        slider.setTickPosition(QSlider.TicksBelow)
        slider.changefunc = lambda v: lbl.setText(
                            _('Min Simularity: %d%%') % v)
        slider.valueChanged.connect(slider.changefunc)
        slider.setValue(s.value('guess/simslider').toInt()[0])
        self.simslider = slider
        lbl.setBuddy(slider)
        simhbox.addWidget(lbl)
        simhbox.addWidget(slider, 1)

        buthbox = QHBoxLayout()
        utvbox.addLayout(buthbox)
        copycheck = QCheckBox(_('Only consider deleted files'))
        copycheck.setToolTip(_('Uncheck to consider all revisioned files'
                               ' for copy sources'))
        copycheck.setChecked(True)
        findrenames = QPushButton(_('Find Rename'))
        findrenames.setToolTip(_('Find copy and/or rename sources'))
        findrenames.clicked.connect(self.findRenames)
        buthbox.addWidget(copycheck)
        buthbox.addStretch(1)
        buthbox.addWidget(findrenames)
        self.findbtn, self.copycheck = findrenames, copycheck

        matchlbl = QLabel(_('<b>Candidate Matches</b>'))
        matchvbox.addWidget(matchlbl)
        self.matchlv = QTreeView()
        self.matchlv.setItemsExpandable(False)
        self.matchlv.setRootIsDecorated(False)
        self.matchlv.setModel(MatchModel())
        self.matchlv.clicked.connect(self.showDiff)
        buthbox = QHBoxLayout()
        matchbtn = QPushButton(_('Accept Selected Matches'))
        matchbtn.clicked.connect(self.acceptMatch)
        matchbtn.setEnabled(False)
        self.matchbtn = matchbtn
        buthbox.addStretch(1)
        buthbox.addWidget(matchbtn)
        matchvbox.addWidget(self.matchlv)
        matchvbox.addLayout(buthbox)

        diffframe = QFrame(hsplit)
        diffvbox = QVBoxLayout()
        diffframe.setLayout(diffvbox)

        difflabel = QLabel(_('<b>Differences from Source to Dest</b>'))
        diffvbox.addWidget(difflabel)
        difftb = QTextBrowser()
        difftb.document().setDefaultStyleSheet(qtlib.thgstylesheet)
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
        dests = []
        for u in wctx.unknown():
            dests.append(u)
        for a in wctx.added():
            if not wctx[a].renamed():
                dests.append(a)
        for x in dests:
            item = QListWidgetItem(hglib.tounicode(x))
            item.orig = x
            self.unrevlist.addItem(item)
            self.unrevlist.setItemSelected(item, x in self.pats)
        self.difftb.clear()
        self.pats = []

    def findRenames(self):
        'User pressed "find renames" button'
        if self.thread and self.thread.isRunning():
            QMessageBox.information(self, _('Search already in progress'),
                                    _('Cannot start a new search'))
            return
        ulist = []
        for item in self.unrevlist.selectedItems():
            ulist.append(item.orig)
        if not ulist:
            QMessageBox.information(self, _('No rows selected'),
                                    _('Select one or more rows for search'))
            return

        def done():
            for col in xrange(3):
                self.matchlv.resizeColumnToContents(col)
            self.findbtn.setEnabled(True)
            self.matchbtn.setDisabled(model.isEmpty())

        pct = self.simslider.value() / 100
        copies = not self.copycheck.isChecked()
        model = self.matchlv.model()
        model.clear()
        self.findbtn.setEnabled(False)
        self.matchbtn.setEnabled(False)

        self.thread = RenameSearchThread(self.repo, ulist, pct, copies)
        self.thread.match.connect(model.appendRow)
        #self.thread.error.connect(print)
        #self.thread.progress.connect(print)
        self.thread.searchComplete.connect(done)
        self.thread.start()

    def acceptMatch(self):
        'User pressed "accept match" button'
        hglib.invalidaterepo(self.repo)
        sel = self.matchlv.selectionModel()
        for index in sel.selectedIndexes():
            src, dest, percent = self.matchlv.model().getRow(index)
            if not os.path.exists(self.repo.wjoin(src)):
                # Mark missing rename source as removed
                self.repo.remove([src])
            self.repo.copy(src, dest)
            shlib.shell_notify([self.repo.wjoin(src), self.repo.wjoin(dest)])
            # Mark all rows with this target file as non-sensitive
            #for row in self.matchlv.model().getRows():
            #    if row[1] == dest:
            #        row[5] = False
        self.matchAccepted.emit()
        self.refresh()

    def showDiff(self, index):
        'User selected a row in the candidate tree'
        hglib.invalidaterepo(self.repo)
        ctx = self.repo['.']
        hu = htmlui.htmlui()
        row = self.matchlv.model().getRow(index)
        src, dest, percent = self.matchlv.model().getRow(index)
        aa = self.repo.wread(dest)
        rr = ctx.filectx(src).data()
        opts = mdiff.defaultopts
        difftext = mdiff.unidiff(rr, '', aa, '', src,
                                 dest, None, opts=opts)
        if not difftext:
            t = _('%s and %s have identical contents\n\n') % (src, dest)
            hu.write(t, label='ui.error')
        else:
            for t, l in qtlib.difflabel(difftext.splitlines, True):
                hu.write(t, label=l)
        self.difftb.setHtml(hu.getdata()[0])

    def accept(self):
        s = QSettings()
        s.setValue('guess/geom', self.saveGeometry())
        s.setValue('guess/vsplit-state', self.vsplit.saveState())
        s.setValue('guess/hsplit-state', self.hsplit.saveState())
        s.setValue('guess/simslider', self.simslider.value())
        QDialog.accept(self)

    def reject(self):
        if self.thread and self.thread.isRunning():
            self.thread.terminate()
            # This can lockup, so stop waiting after 2sec
            self.thread.wait( 2000 )
            self.finished()
            self.thread = None
        else:
            s = QSettings()
            s.setValue('guess/geom', self.saveGeometry())
            s.setValue('guess/vsplit-state', self.vsplit.saveState())
            s.setValue('guess/hsplit-state', self.hsplit.saveState())
            s.setValue('guess/simslider', self.simslider.value())
            QDialog.reject(self)


class MatchModel(QAbstractTableModel):
    def __init__(self, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.rows = []
        self.headers = (_('Source'), _('Dest'), _('% Match'))

    def rowCount(self, parent):
        return len(self.rows)

    def columnCount(self, parent):
        return len(self.headers)

    def data(self, index, role):
        if not index.isValid():
            return QVariant()
        if role == Qt.DisplayRole:
            s = self.rows[index.row()][index.column()]
            return QVariant(hglib.tounicode(s))
        '''
        elif role == Qt.TextColorRole:
            src, dst, pct = self.rows[index.row()]
            if pct == 1.0:
                return QColor('green')
            else:
                return QColor('black')
        elif role == Qt.ToolTipRole:
            # explain what row means?
        '''
        return QVariant()

    def headerData(self, col, orientation, role):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return QVariant()
        else:
            return QVariant(self.headers[col])

    def flags(self, index):
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled

    # Custom methods

    def getRow(self, index):
        assert index.isValid()
        return self.rows[index.row()]

    def appendRow(self, *args):
        self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows))
        vals = [str(a) for a in args] # PyQt is upgrading to QString
        self.rows.append(vals)
        self.endInsertRows()
        self.emit(SIGNAL("dataChanged()"))

    def clear(self):
        self.beginRemoveRows(QModelIndex(), 0, len(self.rows)-1)
        self.rows = []
        self.endRemoveRows()
        self.emit(SIGNAL("dataChanged()"))

    def sort(self, col, order):
        self.emit(SIGNAL("layoutAboutToBeChanged()"))
        if col == COL_PATH:
            c = self.checked
            self.rows.sort(lambda x, y: cmp(c[x[col]], c[y[col]]))
        else:
            self.rows.sort(lambda x, y: cmp(x[col], y[col]))
        if order == Qt.DescendingOrder:
            self.rows.reverse()
        self.emit(SIGNAL("layoutChanged()"))
        self.reset()

    def isEmpty(self):
        return not bool(self.rows)

class RenameSearchThread(QThread):
    '''Background thread for searching repository history'''
    match = pyqtSignal(str, str, str)
    error = pyqtSignal(QString)
    progress = pyqtSignal()
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

    def search(self, repo):
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
            self.match.emit(old, new, '100%')
        if self.minpct < 1.0:
            for o, n, s in similar._findsimilarmatches(repo, added, removed,
                                                       self.minpct):
                old, new = o.path(), n.path()
                self.match.emit(old, new, '%d%%' % (s*100))

def run(ui, *pats, **opts):
    return DetectRenameDialog(None, None, *pats)

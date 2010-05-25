# guess.py - TortoiseHg's dialogs for detecting copies and renames
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import hg, ui, mdiff, similar

from tortoisehg.util import hglib, shlib, paths

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, htmlui, cmdui

from PyQt4.QtCore import *
from PyQt4.QtGui import *

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

        layout = QVBoxLayout()
        self.setLayout(layout)

        # vsplit for top & diff
        vsplit = QSplitter(Qt.Horizontal)
        utframe = QFrame(vsplit)
        matchframe = QFrame(vsplit)

        utvbox = QVBoxLayout()
        utframe.setLayout(utvbox)
        matchvbox = QVBoxLayout()
        matchframe.setLayout(matchvbox)

        hsplit = QSplitter(Qt.Vertical)
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
        findrenames.setEnabled(False)
        findrenames.clicked.connect(self.findRenames)
        buthbox.addWidget(copycheck)
        buthbox.addStretch(1)
        buthbox.addWidget(findrenames)
        self.findbtn, self.copycheck = findrenames, copycheck
        def itemselect():
            self.findbtn.setEnabled(len(self.unrevlist.selectedItems()))
        self.unrevlist.itemSelectionChanged.connect(itemselect)

        matchlbl = QLabel(_('<b>Candidate Matches</b>'))
        matchvbox.addWidget(matchlbl)
        matchtv = QTreeView()
        matchtv.setSelectionMode(QTreeView.ExtendedSelection)
        matchtv.setItemsExpandable(False)
        matchtv.setRootIsDecorated(False)
        matchtv.setModel(MatchModel())
        matchtv.clicked.connect(self.showDiff)
        buthbox = QHBoxLayout()
        matchbtn = QPushButton(_('Accept Selected Matches'))
        matchbtn.clicked.connect(self.acceptMatch)
        matchbtn.setEnabled(False)
        buthbox.addStretch(1)
        buthbox.addWidget(matchbtn)
        matchvbox.addWidget(matchtv)
        matchvbox.addLayout(buthbox)
        self.matchtv, self.matchbtn = matchtv, matchbtn
        def matchselect(s, d):
            count = len(matchtv.selectedIndexes())
            self.matchbtn.setEnabled(count > 0)
        selmodel = matchtv.selectionModel()
        selmodel.selectionChanged.connect(matchselect)

        diffframe = QFrame(hsplit)
        diffvbox = QVBoxLayout()
        diffframe.setLayout(diffvbox)

        difflabel = QLabel(_('<b>Differences from Source to Dest</b>'))
        diffvbox.addWidget(difflabel)
        difftb = QTextBrowser()
        difftb.document().setDefaultStyleSheet(qtlib.thgstylesheet)
        diffvbox.addWidget(difftb)
        self.difftb = difftb

        self.pmon = cmdui.ProgressMonitor()
        self.pmon.hide()
        layout.addWidget(self.pmon)

        s = QSettings()
        self.restoreGeometry(s.value('guess/geom').toByteArray())
        hsplit.restoreState(s.value('guess/hsplit-state').toByteArray())
        vsplit.restoreState(s.value('guess/vsplit-state').toByteArray())
        slider.setValue(s.value('guess/simslider').toInt()[0])
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
        self.pmon.clear_progress()

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

        pct = self.simslider.value() / 100.0
        copies = not self.copycheck.isChecked()
        self.findbtn.setEnabled(False)
        self.errorstr = None

        self.matchtv.model().clear()
        self.thread = RenameSearchThread(self.repo, ulist, pct, copies)
        self.connect(self.thread, SIGNAL('match'), self.rowReceived)
        self.connect(self.thread, SIGNAL('progress'), self.progressReceived)
        self.connect(self.thread, SIGNAL('error'), self.errorReceived)
        self.thread.searchComplete.connect(self.finished)
        self.thread.start()

    def finished(self):
        self.pmon.fillup_progress()
        if self.errorstr:
            self.pmon.set_text(self.errorstr)
        else:
            self.pmon.hide()
        for col in xrange(3):
            self.matchtv.resizeColumnToContents(col)
        self.findbtn.setEnabled(len(self.unrevlist.selectedItems()))

    def rowReceived(self, args):
        self.matchtv.model().appendRow(*args)

    def errorReceived(self, qstr):
        self.errorstr = qstr
        self.pmon.set_text(qstr)

    def progressReceived(self, data):
        if self.thread.isFinished():
            return
        self.pmon.show()
        counting = False
        topic, item, pos, total, unit = data
        if pos is None:
            self.pmon.clear_progress()
            return
        if total is None:
            count = '%d' % pos
            counting = True
        else:
            self.pmon.pbar.setMaximum(total)
            self.pmon.pbar.setValue(pos)
            count = '%d / %d' % (pos, total)
        if unit:
            count += ' ' + unit
        self.pmon.prog_label.setText(hglib.tounicode(count))
        if item:
            status = '%s: %s' % (topic, item)
        else:
            status = _('Status: %s') % topic
        self.pmon.status_label.setText(hglib.tounicode(status))
        self.pmon.inprogress = True

        if not self.pmon.inprogress or counting:
            # use indeterminate mode
            self.pmon.pbar.setMinimum(0)

    def acceptMatch(self):
        'User pressed "accept match" button'
        remdests = {}
        for index in self.matchtv.selectionModel().selectedRows():
            src, dest, percent = self.matchtv.model().getRow(index)
            if dest in remdests:
                QMessageBox.warning(self, _('Multiple sources chosen'),
                    _('You have multiple renames selected for '
                      'destination file:\n%s. Aborting!') % dest)
                return
            remdests[dest] = src
        for dest, src in remdests.iteritems():
            if not os.path.exists(self.repo.wjoin(src)):
                self.repo.remove([src]) # !->R
            self.repo.copy(src, dest)
            shlib.shell_notify([self.repo.wjoin(src), self.repo.wjoin(dest)])
            self.matchtv.model().remove(dest)
        self.matchAccepted.emit()
        self.refresh()

    def showDiff(self, index):
        'User selected a row in the candidate tree'
        hglib.invalidaterepo(self.repo)
        ctx = self.repo['.']
        hu = htmlui.htmlui()
        row = self.matchtv.model().getRow(index)
        src, dest, percent = self.matchtv.model().getRow(index)
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
        self.rows.append(args)
        self.endInsertRows()
        self.emit(SIGNAL("dataChanged()"))

    def clear(self):
        self.beginRemoveRows(QModelIndex(), 0, len(self.rows)-1)
        self.rows = []
        self.endRemoveRows()
        self.emit(SIGNAL("dataChanged()"))

    def remove(self, dest):
        i = 0
        while i < len(self.rows):
            if self.rows[i][1] == dest:
                self.beginRemoveRows(QModelIndex(), i, i)
                self.rows.pop(i)
                self.endRemoveRows()
            else:
                i += 1
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
    searchComplete = pyqtSignal()

    def __init__(self, repo, ufiles, minpct, copies):
        super(RenameSearchThread, self).__init__()
        self.repo = repo
        self.ufiles = ufiles
        self.minpct = minpct
        self.copies = copies

    def run(self):
        class ProgUi(ui.ui):
            def __init__(self, src=None):
                super(ProgUi, self).__init__(src)
                self.setconfig('ui', 'interactive', 'off')
                self.setconfig('progress', 'disable', 'True')
                os.environ['TERM'] = 'dumb'
                if src:
                    self.sig = src.sig
                else:
                    self.sig = QObject() # dummy object to emit signals
            def progress(self, topic, pos, item='', unit='', total=None):
                self.sig.emit(SIGNAL('progress'),
                             [topic, item, pos, total, unit])
        progui = ProgUi()
        self.connect(progui.sig, SIGNAL('progress'), self.progress)
        storeui = self.repo.ui
        self.progui = progui
        self.repo.ui = progui
        try:
            self.search(self.repo)
        except Exception, e:
            self.emit(SIGNAL('error'), hglib.tounicode(str(e)))
        self.repo.ui = storeui
        self.searchComplete.emit()

    def progress(self, wr):
        self.emit(SIGNAL('progress'), wr)

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
        exacts = []
        gen = similar._findexactmatches(repo, added, removed)
        for o, n in gen:
            old, new = o.path(), n.path()
            exacts.append(old)
            self.emit(SIGNAL('match'), [old, new, '100%'])
        if self.minpct == 1.0:
            return
        removed = [r for r in removed if r.path() not in exacts]
        gen = similar._findsimilarmatches(repo, added, removed, self.minpct)
        for o, n, s in gen:
            old, new, sim = o.path(), n.path(), '%d%%' % (s*100)
            self.emit(SIGNAL('match'), [old, new, sim])

def run(ui, *pats, **opts):
    return DetectRenameDialog(None, None, *pats)

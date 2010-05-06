# status.py - working copy browser
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import ui, hg, util, patch, cmdutil, error, mdiff, context, merge
from tortoisehg.hgqt import qtlib, htmlui, chunkselect
from tortoisehg.util import paths, hglib
from tortoisehg.util.i18n import _

from PyQt4.QtCore import Qt, QVariant, SIGNAL, QAbstractTableModel
from PyQt4.QtCore import QObject, QEvent, QMimeData, QUrl
from PyQt4.QtGui import QWidget, QVBoxLayout, QSplitter, QTreeView
from PyQt4.QtGui import QTextEdit, QFont, QColor, QDrag

# This widget can be used as the basis of the commit tool or any other
# working copy browser.

# Technical Debt
#  Thread refreshWctx, connect to an external progress bar
#  Thread rowSelected, connect to an external progress bar
#  Need mechanisms to clear pats and toggle visibility options
#  Need mechanism to override file size/binary check
#  Show subrepos better
#  Save splitter position to parent's QSetting
#  Context menu, toolbar
#  Sorting, filtering of working files
#  Chunk selection
#  tri-state checkboxes for commit
#  Investigate Qt.DecorationRole and possible use of overlay icons
#  Investigate folding/nesting of files

class StatusWidget(QWidget):
    def __init__(self, pats, opts, parent=None):
        QWidget.__init__(self, parent)

        root = paths.find_root()
        assert(root)
        self.repo = hg.repository(ui.ui(), path=root)
        self.wctx = self.repo[None]
        self.opts = dict(unknown=True, clean=False, ignored=False)
        self.opts.update(opts)
        self.pats = pats
        self.ms = {}

        # determine the user configured status colors
        # (in the future, we could support full rich-text tags)
        qtlib.configstyles(self.repo.ui)
        for stat in color_labels.keys():
            effect = qtlib.geteffect(color_labels[stat])
            for e in effect.split(';'):
                if e.startswith('color:'):
                    colors[stat] = QColor(e[7:])
                    break

        split = QSplitter(Qt.Horizontal)
        layout = QVBoxLayout()
        layout.addWidget(split)
        self.setLayout(layout)

        self.tv = WctxFileTree(root, split)
        self.connect(self.tv, SIGNAL('clicked(QModelIndex)'), self.rowSelected)

        self.te = QTextEdit(split)
        self.te.document().setDefaultStyleSheet(qtlib.thgstylesheet)
        self.te.setReadOnly(True)
        self.te.setLineWrapMode(QTextEdit.NoWrap)
        # it is not clear why I had to set this QFont to get monospace
        f = QFont("Monospace")
        f.setStyleHint(QFont.TypeWriter)
        f.setPointSize(9)
        self.te.setFont(f)

        if not parent:
            self.setWindowTitle(_('TortoiseHg Status'))
            self.resize(800, 500)
            # 75% for diff pane
            split.setStretchFactor(0, 1)
            split.setStretchFactor(1, 2)

        self.refreshWctx()
        self.updateModel()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F5:
            self.te.clear()
            self.refreshWctx()
            self.updateModel()
        else:
            return super(StatusWidget, self).keyPressEvent(event)

    def refreshWctx(self):
        hglib.invalidaterepo(self.repo)
        self.ms = merge.mergestate(self.repo)
        extract = lambda x, y: dict(zip(x, map(y.get, x)))
        stopts = extract(('unknown', 'ignored', 'clean'), self.opts)
        if self.pats:
            m = cmdutil.match(self.repo, self.pats)
            status = self.repo.status(match=m, **stopts)
            self.wctx = context.workingctx(self.repo, changes=status)
            return
        wctx = self.repo[None]
        try:
            wctx.status(**stopts)
        except AttributeError:
            # your mercurial source is not new enough, falling back
            # to triggering implicit status() call.
            wctx.modified()
        except (OSError, IOError, util.Abort), e:
            self.status_error = str(e)
        self.wctx = wctx

    def isMerge(self):
        return bool(self.wctx.p2())

    def updateModel(self):
        tm = WctxModel(self.wctx, self.ms, self.opts)
        self.tv.setModel(tm)
        self.tv.setItemsExpandable(False)
        self.tv.setRootIsDecorated(False)
        self.tv.setSortingEnabled(True)
        self.tv.sortByColumn(COL_PATH_DISPLAY)
        for col in xrange(COL_PATH):
            self.tv.resizeColumnToContents(col)
        self.tv.setColumnHidden(COL_MERGE_STATE, not tm.anyMerge())
        self.connect(self.tv, SIGNAL('activated(QModelIndex)'), tm.toggleRow)
        self.connect(self.tv, SIGNAL('pressed(QModelIndex)'), tm.pressedRow)

    def rowSelected(self, index):
        'Connected to treeview "clicked" signal'
        pfile = index.model().getPath(index)
        wfile = util.pconvert(pfile)

        warnings = chunkselect.check_max_diff(self.wctx, wfile)
        if warnings:
            text = '<b>Diffs not displayed: %s</b>' % warnings[1]
            self.te.setHtml(text)
            return

        if self.isMerge():
            header = _('===== Diff to first parent %d:%s =====\n') % (
                    self.wctx.p1().rev(), str(self.wctx.p1()))
            header = '<h3>' + header + '</h3></br>'
        else:
            header = ''

        hu = htmlui.htmlui()
        m = cmdutil.matchfiles(self.repo, [wfile])
        try:
            try:
                for s, l in patch.difflabel(self.wctx.diff, match=m):
                    hu.write(s, label=l)
            except AttributeError:
                # your mercurial source is not new enough, falling back
                # to manual patch.diff() call
                opts = mdiff.diffopts(git=True, nodates=True)
                n2, n1 = None, self.wctx.p1().node()
                for s, l in patch.difflabel(patch.diff, self.repo, n1, n2,
                                            match=m, opts=opts):
                    hu.write(s, label=l)
        except (IOError, error.RepoError, error.LookupError, util.Abort), e:
            self.status_error = str(e)
            return
        o, e = hu.getdata()
        diff = o or _('<em>No change</em>')
        if self.isMerge():
            text = header + diff
        else:
            self.te.setHtml(header + diff)
            return

        try:
            for s, l in patch.difflabel(self.wctx.diff, self.wctx.p2(), match=m):
                hu.write(s, label=l)
        except (IOError, error.RepoError, error.LookupError, util.Abort), e:
            self.status_error = str(e)
            return
        text += '</br><h3>'
        text += _('===== Diff to second parent %d:%s =====\n') % (
                self.wctx.p2().rev(), str(self.wctx.p2()))
        text += '</h3></br>'
        o, e = hu.getdata()
        diff = o or _('<em>No change</em>')
        self.te.setHtml(text + diff)


class WctxFileTree(QTreeView):
    def __init__(self, root, parent=None):
        QTreeView.__init__(self, parent)
        self.root = root

    def keyPressEvent(self, event):
        if event.key() == 32:
            for index in self.selectedIndexes():
                self.model().toggleRow(index)
        else:
            return super(WctxFileTree, self).keyPressEvent(event)

    def dragObject(self):
        rows = set()
        urls = []
        for index in self.selectedIndexes():
            if index.row() not in rows:
                rows.add(index.row())
                path = self.model().getPath(index)
                u = QUrl()
                u.setPath('file://' + os.path.join(self.root, path))
                urls.append(u)
        if rows:
            d = QDrag(self)
            m = QMimeData()
            m.setUrls(urls)
            d.setMimeData(m)
            d.start(Qt.CopyAction)

    def mouseMoveEvent(self, event):
        self.dragObject()


COL_CHECK = 0
COL_STATUS = 1
COL_MERGE_STATE = 2
COL_PATH_DISPLAY = 3
COL_PATH = 4

tips = {
   'M': _('%s is modified'),
   'A': _('%s is added'),
   'R': _('%s is removed'),
   '?': _('%s is not tracked (unknown)'),
   '!': _('%s is missing!'),
   'I': _('%s is ignored'),
   'C': _('%s is not modified (clean)'),
   'S': _('%s is a dirty subrepo'),
}

color_labels = {
   'M': 'status.modified',
   'A': 'status.added',
   'R': 'status.removed',
   '?': 'status.unknown',
   '!': 'status.deleted',
   'I': 'status.ignored',
   'C': 'status.clean',
   'S': 'status.subrepo',
   'r': 'resolve.resolved',
   'u': 'resolve.unresolved',
}

colors = {}

class WctxModel(QAbstractTableModel):
    def __init__(self, wctx, ms, opts, parent=None):
        QAbstractTableModel.__init__(self, parent)
        rows = []
        for m in wctx.modified():
            mst = m in ms and ms[m].upper() or ""
            rows.append([True, 'M', mst, hglib.tounicode(m), m])
        for a in wctx.added():
            mst = a in ms and ms[a].upper() or ""
            rows.append([True, 'A', mst, hglib.tounicode(a), a])
        for r in wctx.removed():
            mst = r in ms and ms[r].upper() or ""
            rows.append([True, 'R', mst, hglib.tounicode(r), r])
        for d in wctx.deleted():
            mst = d in ms and ms[d].upper() or ""
            rows.append([False, '!', mst, hglib.tounicode(d), d])
        if opts['unknown']:
            for u in wctx.unknown():
            	rows.append([False, '?', '', hglib.tounicode(u), u])
        if opts['ignored']:
            for i in wctx.ignored():
            	rows.append([False, 'I', '', hglib.tounicode(i), i])
        if opts['clean']:
            for c in wctx.clean():
            	rows.append([False, 'C', '', hglib.tounicode(c), c])
        try:
            for s in wctx.substate:
                if wctx.sub(s).dirty():
                    rows.append([False, 'S', '', hglib.tounicode(s), s])
        except (OSError, IOError, error.ConfigError), e:
            self.status_error = str(e)
        self.headers = ('*', _('Stat'), _('M'), _('Filename'))
        self.rows = rows

    def rowCount(self, parent):
        return len(self.rows)

    def columnCount(self, parent):
        return len(self.headers)

    def data(self, index, role):
        if not index.isValid():
            return QVariant()
        if index.column() == COL_CHECK:
            if role == Qt.CheckStateRole:
                # also Qt.PartiallyChecked
                if self.rows[index.row()][COL_CHECK]:
                    return Qt.Checked
                else:
                    return Qt.Unchecked
        elif role == Qt.DisplayRole:
            return QVariant(self.rows[index.row()][index.column()])

        checked, status, mst, upath, path = self.rows[index.row()]
        if role == Qt.TextColorRole:
            if mst:
                return colors.get(mst.lower(), QColor('black'))
            else:
                return colors.get(status, QColor('black'))
        elif role == Qt.ToolTipRole:
            if status in tips:
                tip = tips[status] % upath
                if mst == 'R':
                    tip += _(', resolved merge')
                elif mst == 'U':
                    tip += _(', unresolved merge')
                return QVariant(tip)
        return QVariant()

    def headerData(self, col, orientation, role):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return QVariant()
        else:
            return QVariant(self.headers[col])

    def flags(self, index):
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled
        if index.column() == COL_CHECK:
            flags |= Qt.ItemIsUserCheckable
        return flags

    # Custom methods

    def anyMerge(self):
        for r in self.rows:
            if r[COL_MERGE_STATE]:
                return True
        return False

    def getPath(self, index):
        assert index.isValid()
        return self.rows[index.row()][COL_PATH]

    def toggleRow(self, index):
        'Connected to "activated" signal, emitted by dbl-click or enter'
        assert index.isValid()
        row = index.row()
        self.rows[row][COL_CHECK] = not self.rows[row][COL_CHECK]
        self.emit(SIGNAL("layoutChanged()"))

    def pressedRow(self, index):
        'Connected to "pressed" signal, emitted by mouse clicks'
        assert index.isValid()
        if index.column() == COL_CHECK:
            self.toggleRow(index)


def run(ui, *pats, **opts):
    return StatusWidget(pats, opts)

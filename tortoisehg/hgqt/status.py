# status.py - working copy browser
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from mercurial import ui, hg, util, patch, cmdutil, error, mdiff
from tortoisehg.hgqt import qtlib, htmlui
from tortoisehg.util import paths, hglib
from tortoisehg.util.i18n import _

from PyQt4.QtCore import Qt, QVariant, SIGNAL, QAbstractTableModel
from PyQt4.QtCore import QObject, QEvent
from PyQt4.QtGui import QWidget, QVBoxLayout, QSplitter, QTreeView
from PyQt4.QtGui import QTextEdit, QFont, QColor

# This widget can be used as the basis of the commit tool or any other
# working copy browser.

# A QuickOp style dialog will need to create the workingctx instance by
# hand, not using repo[None], in order to pass in the results from its
# own call to localrepo.status(), else it will not be able to see clean
# or ignored files.

# Technical Debt
#  filter using pats
#  show example of wctx manual creation
#  wctx.ignored() does not exist, need a back-door
#  Handle large files, binary files, subrepos better
#  Thread refreshWctx, connect to an external progress bar
#  Thread rowSelected, connect to an external progress bar
#  Need a mechanism to clear pats
#  Save splitter position, use parent's QSetting
#  Show merge status column, when appropriate
#  Context menu, toolbar
#  Sorting, filtering of working files
#  Chunk selection
#  tri-state checkboxes for commit
#  File type (unknown/deleted) toggles
#  Investigate Qt.DecorationRole and possible use of overlay icons
#  Investigate folding/nesting of files

class StatusWidget(QWidget):
    def __init__(self, pats, parent=None):
        QWidget.__init__(self, parent)

        root = paths.find_root()
        assert(root)
        self.repo = hg.repository(ui.ui(), path=root)
        self.wctx = self.repo[None]

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

        self.tv = QTreeView(split)
        self.connect(self.tv, SIGNAL('clicked(QModelIndex)'), self.rowSelected)
        self.tv.installEventFilter(TvEventFilter(self))

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
            self.resize(650, 400)
            # 60% for diff pane
            split.setStretchFactor(0, 2)
            split.setStretchFactor(1, 5)

        self.refreshWctx()
        self.updateModel()

    def refreshWctx(self):
        hglib.invalidaterepo(self.repo)
        wctx = self.repo[None]
        try:
            # Force wctx to load _status property
            wctx.unknown()
        except (OSError, IOError, util.Abort), e:
            self.status_error = str(e)
        self.wctx = wctx

    def isMerge(self):
        return bool(self.wctx.p2())

    def updateModel(self):
        tm = WctxModel(self.wctx)
        self.tv.setModel(tm)
        self.tv.setItemsExpandable(False)
        self.tv.setRootIsDecorated(False)
        self.tv.setSortingEnabled(True)
        self.tv.sortByColumn(COL_PATH_DISPLAY)
        self.tv.resizeColumnToContents(COL_CHECK)
        self.tv.resizeColumnToContents(COL_STATUS)
        self.tv.resizeColumnToContents(COL_PATH_DISPLAY)
        self.connect(self.tv, SIGNAL('activated(QModelIndex)'), tm.toggleRow)
        self.connect(self.tv, SIGNAL('pressed(QModelIndex)'), tm.pressedRow)

    def rowSelected(self, index):
        'Connected to treeview "clicked" signal'
        pfile = index.model().getPath(index)
        wfile = util.pconvert(pfile)
        hu = htmlui.htmlui()
        try:
            m = cmdutil.matchfiles(self.repo, [wfile])
            opts = mdiff.diffopts(git=True, nodates=True)
            n2, n1 = None, self.wctx.p1().node()
            for s, l in patch.difflabel(patch.diff, self.repo, n1, n2,
                                        match=m, opts=opts):
                hu.write(s, label=l)
        except (IOError, error.RepoError, error.LookupError, util.Abort), e:
            self.status_error = str(e)
        o, e = hu.getdata()
        self.te.setHtml(o)


class TvEventFilter(QObject):
    '''Event filter for our QTreeView'''
    def __init__(self, parent):
        QObject.__init__(self, parent)
    def eventFilter(self, treeview, event):
        if event.type() == QEvent.KeyPress and event.key() == 32:
            for index in treeview.selectedIndexes():
                treeview.model().toggleRow(index)
            return True
        return treeview.eventFilter(treeview, event)


COL_CHECK = 0
COL_STATUS = 1
COL_PATH_DISPLAY = 2
COL_PATH = 3

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
}

colors = {}

class WctxModel(QAbstractTableModel):
    def __init__(self, wctx, parent=None):
        QAbstractTableModel.__init__(self, parent)
        rows = []
        for m in wctx.modified():
            rows.append([True, 'M', hglib.tounicode(m), m])
        for a in wctx.added():
            rows.append([True, 'A', hglib.tounicode(a), a])
        for r in wctx.removed():
            rows.append([True, 'R', hglib.tounicode(r), r])
        for d in wctx.deleted():
            rows.append([False, '!', hglib.tounicode(d), d])
        for u in wctx.unknown():
            rows.append([False, '?', hglib.tounicode(u), u])
        # TODO: wctx.ignored() does not exist
        #for i in wctx.ignored():
        #    rows.append([False, 'I', hglib.tounicode(i), i])
        for c in wctx.clean():
            rows.append([False, 'C', hglib.tounicode(c), c])
        try:
            for s in wctx.substate:
                if wctx.sub(s).dirty():
                    rows.append([False, 'S', hglib.tounicode(s), s])
        except (OSError, IOError, error.ConfigError), e:
            self.status_error = str(e)
        self.rows = rows
        self.headers = ('*', _('Stat'), _('Filename'))

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

        checked, status, upath, path = self.rows[index.row()]
        if role == Qt.TextColorRole:
            return colors.get(status, QColor('black'))
        elif role == Qt.ToolTipRole:
            if status in tips:
                return QVariant(tips[status] % upath)
        return QVariant()

    def headerData(self, col, orientation, role):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return QVariant()
        else:
            return QVariant(self.headers[col])

    def flags(self, index):
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if index.column() == COL_CHECK:
            flags |= Qt.ItemIsUserCheckable
        return flags

    # Custom methods

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
    return StatusWidget(pats, None)

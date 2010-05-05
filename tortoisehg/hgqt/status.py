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
from PyQt4.QtGui import QWidget, QVBoxLayout, QSplitter, QTreeView
from PyQt4.QtGui import QTextEdit, QFont

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
#  Select entire table row when clicked
#  File type (unknown/deleted) toggles

class StatusWidget(QWidget):
    def __init__(self, pats, parent=None):
        QWidget.__init__(self, parent)

        root = paths.find_root()
        assert(root)
        self.repo = hg.repository(ui.ui(), path=root)
        self.wctx = self.repo[None]

        split = QSplitter(Qt.Horizontal)
        layout = QVBoxLayout()
        layout.addWidget(split)
        self.setLayout(layout)

        self.tv = QTreeView(split)
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
        self.tv.setItemsExpandable(False)
        self.tv.setRootIsDecorated(False)
        self.tv.setSortingEnabled(True)
        self.tv.sortByColumn(1)
        self.tv.setModel(tm)
        self.tv.resizeColumnToContents(0)
        self.tv.resizeColumnToContents(1)

    def rowSelected(self, index):
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


COL_STATUS = 0
COL_PATH_DISPLAY = 1
COL_PATH = 2

class WctxModel(QAbstractTableModel):
    def __init__(self, wctx, parent=None):
        QAbstractTableModel.__init__(self, parent)
        rows = []
        for m in wctx.modified():
            rows.append(('M', hglib.tounicode(m), m))
        for a in wctx.added():
            rows.append(('A', hglib.tounicode(a), a))
        for r in wctx.removed():
            rows.append(('R', hglib.tounicode(r), r))
        for d in wctx.deleted():
            rows.append(('!', hglib.tounicode(d), d))
        for u in wctx.unknown():
            rows.append(('?', hglib.tounicode(u), u))
        # TODO: wctx.ignored() does not exist
        #for i in wctx.ignored():
        #    rows.append(('I', hglib.tounicode(i), i))
        for c in wctx.clean():
            rows.append(('C', hglib.tounicode(c), c))
        try:
            for s in wctx.substate:
                if wctx.sub(s).dirty():
                    rows.append(('S', hglib.tounicode(s), s))
        except (OSError, IOError, error.ConfigError), e:
            self.status_error = str(e)
        self.rows = rows
        self.headers = (_('Stat'), _('Filename'))

    def rowCount(self, parent):
        return len(self.rows)

    def columnCount(self, parent):
        return len(self.headers)

    def data(self, index, role):
        if not index.isValid() or role != Qt.DisplayRole:
            return QVariant()
        return QVariant(self.rows[index.row()][index.column()])

    def getPath(self, index):
        assert index.isValid()
        return self.rows[index.row()][COL_PATH]

    def headerData(self, col, orientation, role):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return QVariant()
        else:
            return QVariant(self.headers[col])

    def flags(self, index):
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled


def run(ui, *pats, **opts):
    return StatusWidget(pats, None)

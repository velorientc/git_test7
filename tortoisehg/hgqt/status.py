# status.py - working copy browser
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import ui, hg, util, patch, cmdutil, error, mdiff, context, merge
from tortoisehg.hgqt import qtlib, htmlui, chunkselect, wctxactions, visdiff
from tortoisehg.util import paths, hglib
from tortoisehg.util.i18n import _

from PyQt4.QtCore import Qt, QVariant, SIGNAL, SLOT, QAbstractTableModel
from PyQt4.QtCore import QObject, QEvent, QMimeData, QUrl, QString
from PyQt4.QtGui import QWidget, QVBoxLayout, QSplitter, QTreeView, QLineEdit
from PyQt4.QtGui import QTextEdit, QFont, QColor, QDrag, QSortFilterProxyModel
from PyQt4.QtGui import QFrame, QHBoxLayout, QLabel, QPushButton, QMenu
from PyQt4.QtGui import QIcon, QPixmap

# This widget can be used as the basis of the commit tool or any other
# working copy browser.

# Technical Debt
#  Selections are not surviving refresh
#  We need a real icon set for file status types
#  Refresh can be too expensive; probably need to disable some signals
#  Add some initial drag distance before starting QDrag
#   (it interferes with selection the way it is now)
#  Thread refreshWctx, connect to an external progress bar
#  Thread rowSelected, connect to an external progress bar
#  Need mechanism to override file size/binary check
#  Show subrepos better
#  Save splitter position to parent's QSetting
#  Chunk selection
#  tri-state checkboxes for commit
#  Investigate folding/nesting of files
# Maybe, Maybe Not
#  Toolbar
#  double-click visual diffs

class StatusType(object):
    preferredOrder = 'MAR?!ICS'
    def __init__(self, name, icon, desc, uilabel):
        self.name = name
        self.icon = icon
        self.desc = desc
        self.uilabel = uilabel

statusTypes = {
    'M' : StatusType('modified', 'menucommit.ico', _('%s is modified'),
                     'status.modified'),
    'A' : StatusType('added', 'fileadd.ico', _('%s is added'),
                     'status.added'),
    'R' : StatusType('removed', 'filedelete.ico', _('%s is removed'),
                     'status.removed'),
    '?' : StatusType('unknown', 'shelve.ico', _('%s is not tracked (unknown)'),
                     'status.unknown'),
    '!' : StatusType('deleted', 'menudelete.ico', _('%s is missing!'),
                     'status.deleted'),
    'I' : StatusType('ignored', 'ignore.ico', _('%s is ignored'),
                     'status.ignored'),
    'C' : StatusType('clean', '', _('%s is not modified (clean)'),
                     'status.clean'),
    'S' : StatusType('subrepo', 'hg.ico', _('%s is a dirty subrepo'),
                     'status.subrepo'),
}

class StatusWidget(QWidget):
    def __init__(self, pats, opts, parent=None):
        QWidget.__init__(self, parent)

        root = paths.find_root()
        assert(root)
        self.repo = hg.repository(ui.ui(), path=root)
        self.wctx = self.repo[None]
        self.opts = dict(modified=True, added=True, removed=True, deleted=True,
                         unknown=True, clean=False, ignored=False, subrepo=True)
        self.opts.update(opts)
        self.pats = pats
        self.ms = {}

        # determine the user configured status colors
        # (in the future, we could support full rich-text tags)
        qtlib.configstyles(self.repo.ui)
        labels = [(stat, val.uilabel) for stat, val in statusTypes.items()]
        labels.extend([('r', 'resolve.resolved'), ('u', 'resolve.unresolved')])
        for stat, label in labels:
            effect = qtlib.geteffect(label)
            for e in effect.split(';'):
                if e.startswith('color:'):
                    colors[stat] = QColor(e[7:])
                    break

        split = QSplitter(Qt.Horizontal)
        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.addWidget(split)
        self.setLayout(layout)

        vbox = QVBoxLayout()
        vbox.setMargin(0)
        frame = QFrame(split)
        frame.setLayout(vbox)
        hbox = QHBoxLayout()
        hbox.setContentsMargins (5, 7, 0, 0)
        lbl = QLabel(_('Filter:'))
        le = QLineEdit()
        pb = QPushButton(_('MAR!?IC')) # needs a better label
        hbox.addWidget(lbl)
        hbox.addWidget(le)
        hbox.addWidget(pb)
        tv = WctxFileTree(self.repo)
        vbox.addLayout(hbox)
        vbox.addWidget(tv)
        split.addWidget(frame)

        if self.pats:
            def clearPattern():
                self.pats = []
                self.refreshWctx()
                cpb.setVisible(False)
            cpb = QPushButton(_('Remove filter, show root'))
            vbox.addWidget(cpb)
            cpb.clicked.connect(clearPattern)

        self.connect(tv, SIGNAL('clicked(QModelIndex)'), self.rowSelected)
        self.connect(tv, SIGNAL('menuAction()'), self.refreshWctx)
        tv.setItemsExpandable(False)
        tv.setRootIsDecorated(False)
        tv.setSortingEnabled(True)

        def setButtonText():
            text = ''
            for stat in StatusType.preferredOrder:
                name = statusTypes[stat].name
                if self.opts[name]:
                    text += stat
            pb.setText(text)
        def statusTypeTrigger(isChecked):
            txt = hglib.fromunicode(self.sender().text())
            self.opts[txt[2:]] = isChecked
            self.refreshWctx()
            setButtonText()
        menu = QMenu()
        for stat in StatusType.preferredOrder:
            val = statusTypes[stat]
            a = menu.addAction('%s %s' % (stat, val.name))
            a.setCheckable(True)
            a.setChecked(self.opts[val.name])
            a.triggered.connect(statusTypeTrigger)
        pb.setMenu(menu)
        setButtonText()
        pb.storeref = menu

        self.proxy = WctxProxyModel()
        self.proxy.setFilterKeyColumn(COL_PATH_DISPLAY)
        self.connect(le, SIGNAL('textEdited(QString)'), self.proxy,
                     SLOT('setFilterWildcard(QString)'))
        tv.setModel(self.proxy)
        self.tv = tv

        self.te = QTextEdit(split)
        self.te.document().setDefaultStyleSheet(qtlib.thgstylesheet)
        self.te.setReadOnly(True)
        self.te.setLineWrapMode(QTextEdit.NoWrap)

        if not parent:
            self.setWindowTitle(_('TortoiseHg Status'))
            self.resize(800, 500)
            # 75% for diff pane
            split.setStretchFactor(0, 1)
            split.setStretchFactor(1, 2)

        self.refreshWctx()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F5:
            self.te.clear()
            self.refreshWctx()
        else:
            return super(StatusWidget, self).keyPressEvent(event)

    def refreshWctx(self):
        self.te.clear()
        hglib.invalidaterepo(self.repo)
        self.ms = merge.mergestate(self.repo)
        extract = lambda x, y: dict(zip(x, map(y.get, x)))
        stopts = extract(('unknown', 'ignored', 'clean'), self.opts)
        if self.pats:
            m = cmdutil.match(self.repo, self.pats)
            status = self.repo.status(match=m, **stopts)
            self.wctx = context.workingctx(self.repo, changes=status)
            self.updateModel()
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
        self.updateModel()

    def updateModel(self):
        tm = WctxModel(self.wctx, self.ms, self.opts)
        self.rawmodel = tm
        self.proxy.setSourceModel(tm)
        self.tv.sortByColumn(COL_PATH_DISPLAY)
        self.tv.setColumnHidden(COL_CHECK, self.isMerge())
        self.tv.setColumnHidden(COL_MERGE_STATE, not tm.anyMerge())
        for col in xrange(COL_PATH):
            self.tv.resizeColumnToContents(col)
        self.connect(self.tv, SIGNAL('activated(QModelIndex)'), tm.toggleRow)
        self.connect(self.tv, SIGNAL('pressed(QModelIndex)'), tm.pressedRow)

    def isMerge(self):
        return bool(self.wctx.p2())

    def rowSelected(self, index):
        'Connected to treeview "clicked" signal'
        checked, status, mst, upath, path = index.model().getRow(index)
        wfile = util.pconvert(path)

        if status in '?IC':
            # TODO: Display file contents if a button clicked,
            # add to a toolbar above the diff panel
            text = '<b>File is not tracked</b>'
            self.te.setHtml(text)
            return
        elif status in '!':
            text = '<b>File is missing!</b>'
            self.te.setHtml(text)
            return

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
                for s, l in patch.difflabel(self.wctx.diff, match=m, git=True):
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
        diff = o or _('<em>No displayable differences</em>')
        if self.isMerge():
            text = header + diff
        else:
            self.te.setHtml(header + diff)
            return

        try:
            for s, l in patch.difflabel(self.wctx.diff, self.wctx.p2(),
                                        match=m, git=True):
                hu.write(s, label=l)
        except (IOError, error.RepoError, error.LookupError, util.Abort), e:
            self.status_error = str(e)
            return
        text += '</br><h3>'
        text += _('===== Diff to second parent %d:%s =====\n') % (
                self.wctx.p2().rev(), str(self.wctx.p2()))
        text += '</h3></br>'
        o, e = hu.getdata()
        diff = o or _('<em>No displayable differences</em>')
        self.te.setHtml(text + diff)


class WctxFileTree(QTreeView):
    def __init__(self, repo, parent=None):
        QTreeView.__init__(self, parent)
        self.repo = repo
        self.setSelectionMode(QTreeView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.connect(self, SIGNAL('customContextMenuRequested(const QPoint &)'),
                     self.customContextMenuRequested)

    def keyPressEvent(self, event):
        if event.key() == 32:
            for index in self.selectedRows():
                self.model().toggleRow(index)
        if event.key() == Qt.Key_D and event.modifiers() == Qt.ControlModifier:
            selfiles = []
            for index in self.selectedRows():
                selfiles.append(self.model().getRow(index)[COL_PATH])
            visdiff.visualdiff(self.repo.ui, self.repo, selfiles, {})
        else:
            return super(WctxFileTree, self).keyPressEvent(event)

    def dragObject(self):
        urls = []
        for index in self.selectedRows():
            path = self.model().getRow(index)[COL_PATH]
            u = QUrl()
            u.setPath('file://' + os.path.join(self.repo.root, path))
            urls.append(u)
        if urls:
            d = QDrag(self)
            m = QMimeData()
            m.setUrls(urls)
            d.setMimeData(m)
            d.start(Qt.CopyAction)

    def mouseMoveEvent(self, event):
        self.dragObject()

    def customContextMenuRequested(self, point):
        selrows = []
        for index in self.selectedRows():
            c, status, mst, u, path = self.model().getRow(index)
            selrows.append((set(status+mst.lower()), path))
        point = self.mapToGlobal(point)
        action = wctxactions.wctxactions(self, point, self.repo, selrows)
        if action:
            self.emit(SIGNAL('menuAction()'))

    def selectedRows(self):
        return self.selectionModel().selectedRows()

COL_CHECK = 0
COL_STATUS = 1
COL_MERGE_STATE = 2
COL_PATH_DISPLAY = 3
COL_PATH = 4

colors = {}

class WctxModel(QAbstractTableModel):
    def __init__(self, wctx, ms, opts, parent=None):
        QAbstractTableModel.__init__(self, parent)
        rows = []
        if opts['modified']:
            for m in wctx.modified():
                mst = m in ms and ms[m].upper() or ""
                rows.append([True, 'M', mst, hglib.tounicode(m), m])
        if opts['added']:
            for a in wctx.added():
                mst = a in ms and ms[a].upper() or ""
                rows.append([True, 'A', mst, hglib.tounicode(a), a])
        if opts['removed']:
            for r in wctx.removed():
                mst = r in ms and ms[r].upper() or ""
                rows.append([True, 'R', mst, hglib.tounicode(r), r])
        if opts['deleted']:
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
        elif role == Qt.DecorationRole and index.column() == COL_STATUS:
            status = self.rows[index.row()][COL_STATUS]
            if status in statusTypes:
                ico = QIcon()
                ico.addPixmap(QPixmap('icons/' + statusTypes[status].icon))
                return QVariant(ico)
        elif role == Qt.DisplayRole:
            return QVariant(self.rows[index.row()][index.column()])

        checked, status, mst, upath, path = self.rows[index.row()]
        if role == Qt.TextColorRole:
            if mst:
                return colors.get(mst.lower(), QColor('black'))
            else:
                return colors.get(status, QColor('black'))
        elif role == Qt.ToolTipRole:
            if status in statusTypes:
                tip = statusTypes[status].desc % upath
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

    def getRow(self, index):
        assert index.isValid()
        return self.rows[index.row()]

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

class WctxProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        QSortFilterProxyModel.__init__(self, parent)

    def getRow(self, index):
        index = self.mapToSource(index)
        return self.sourceModel().getRow(index)

    def toggleRow(self, index):
        'Connected to "activated" signal, emitted by dbl-click or enter'
        index = self.mapToSource(index)
        return self.sourceModel().toggleRow(index)

    def pressedRow(self, index):
        'Connected to "pressed" signal, emitted by mouse clicks'
        index = self.mapToSource(index)
        return self.sourceModel().pressedRow(index)

def run(ui, *pats, **opts):
    return StatusWidget(pats, opts)

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
from PyQt4.QtGui import QTextEdit, QFont, QColor, QDrag
from PyQt4.QtGui import QFrame, QHBoxLayout, QLabel, QPushButton, QMenu
from PyQt4.QtGui import QIcon, QPixmap, QToolButton

# This widget can be used as the basis of the commit tool or any other
# working copy browser.

# Technical Debt
#  We need a real icon set for file status types
#  Add some initial drag distance before starting QDrag
#   (it interferes with selection the way it is now)
#  Thread refreshWctx, connect to an external progress bar
#  Thread rowSelected, connect to an external progress bar
#  Show subrepos better
#  Chunk selection
#  tri-state checkboxes for commit
#  Investigate folding/nesting of files
# Maybe, Maybe Not
#  Toolbar
#  double-click visual diffs

COL_PATH = 0
COL_STATUS = 1
COL_MERGE_STATE = 2
COL_PATH_DISPLAY = 3

_colors = {}

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
        self.curRow = None

        # determine the user configured status colors
        # (in the future, we could support full rich-text tags)
        qtlib.configstyles(self.repo.ui)
        labels = [(stat, val.uilabel) for stat, val in statusTypes.items()]
        labels.extend([('r', 'resolve.resolved'), ('u', 'resolve.unresolved')])
        for stat, label in labels:
            effect = qtlib.geteffect(label)
            for e in effect.split(';'):
                if e.startswith('color:'):
                    _colors[stat] = QColor(e[7:])
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
        tv.sortByColumn(COL_PATH_DISPLAY)

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
        self.tv = tv
        self.le = le

        # Diff panel side of splitter
        vbox = QVBoxLayout()
        vbox.setMargin(0)
        docf = QFrame(split)
        docf.setLayout(vbox)
        hbox = QHBoxLayout()
        hbox.setContentsMargins (5, 7, 0, 0)
        self.fnamelabel = QLabel()
        self.fnamelabel.setContextMenuPolicy(Qt.CustomContextMenu)
        self.connect(self.fnamelabel,
                     SIGNAL('customContextMenuRequested(const QPoint &)'),
                     self.customContextMenuRequested)
        hbox.addWidget(self.fnamelabel)
        hbox.addStretch()

        self.override = QToolButton()
        self.override.setText(_('Show Contents'))
        self.override.setCheckable(True)
        self.override.setVisible(False)
        self.override.toggled.connect(self.refreshDiff)
        hbox.addWidget(self.override)

        self.te = QTextEdit()
        self.te.document().setDefaultStyleSheet(qtlib.thgstylesheet)
        self.te.setReadOnly(True)
        self.te.setLineWrapMode(QTextEdit.NoWrap)
        vbox.addLayout(hbox)
        vbox.addWidget(self.te)

        if not parent:
            self.setWindowTitle(_('TortoiseHg Status'))
            self.resize(800, 500)
            # 75% for diff pane
            split.setStretchFactor(0, 1)
            split.setStretchFactor(1, 2)

        self.split = split
        self.refreshWctx()

    def restoreState(self, data):
        return self.split.restoreState(data)

    def saveState(self):
        return self.split.saveState()

    def customContextMenuRequested(self, point):
        'menu request for filename label'
        if self.curRow is None:
            return
        point = self.fnamelabel.mapToGlobal(point)
        path, status, mst, u = self.curRow
        selrows = [(set(status+mst.lower()), path), ]
        action = wctxactions.wctxactions(self, point, self.repo, selrows)
        if action:
            self.emit(SIGNAL('menuAction()'))

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
        self.tv.setSortingEnabled(False)
        if self.tv.model():
            checked = self.tv.model().getChecked()
        else:
            checked = {}
        tm = WctxModel(self.wctx, self.ms, self.opts, checked)
        self.tv.setModel(tm)
        self.tv.setSortingEnabled(True)
        self.tv.setColumnHidden(COL_PATH, self.isMerge())
        self.tv.setColumnHidden(COL_MERGE_STATE, not tm.anyMerge())
        for col in xrange(COL_PATH_DISPLAY):
            self.tv.resizeColumnToContents(col)
        self.connect(self.tv, SIGNAL('activated(QModelIndex)'), tm.toggleRow)
        self.connect(self.tv, SIGNAL('pressed(QModelIndex)'), tm.pressedRow)
        self.connect(self.le, SIGNAL('textEdited(QString)'), tm.setFilter)

    def isMerge(self):
        return bool(self.wctx.p2())

    def rowSelected(self, index):
        'Connected to treeview "clicked" signal'
        self.curRow = None
        self.override.setChecked(False)
        self.curRow = index.model().getRow(index)
        self.refreshDiff()

    def refreshDiff(self):
        if self.curRow is None:
            return
        path, status, mst, upath = self.curRow
        wfile = util.pconvert(path)
        self.fnamelabel.setText(statusMessage(status, mst, upath))
        showanyway = self.override.isChecked()

        if status in '?I':
            if showanyway:
                # Read untracked file contents from working directory
                diff = open(self.repo.wjoin(wfile), 'r').read()
                if '\0' in diff:
                    diff = _('<b>Contents are binary, not previewable</b>')
                    self.te.setHtml(diff)
                else:
                    self.te.setText(diff)
            else:
                diff = _('<b>Not displayed</b>')
                self.te.setHtml(diff)
                self.override.setVisible(True)
            return
        elif status in '!C':
            if showanyway:
                # Read file contents from parent revision
                ctx = self.repo['.']
                diff = ctx.filectx(wfile).data()
                if '\0' in diff:
                    diff = _('<b>Contents are binary, not previewable</b>')
                    self.te.setHtml(diff)
                else:
                    self.te.setText(diff)
            else:
                diff = _('<b>Not displayed</b>')
                self.te.setHtml(diff)
                self.override.setVisible(True)
            return

        warnings = chunkselect.check_max_diff(self.wctx, wfile)
        if warnings and not showanyway:
            text = '<b>Diffs not displayed: %s</b>' % warnings[1]
            self.te.setHtml(text)
            self.override.setVisible(True)
            return

        self.override.setVisible(False)

        # Generate diffs to first parent
        hu = htmlui.htmlui()
        m = cmdutil.matchfiles(self.repo, [wfile])
        try:
            for s, l in patch.difflabel(self.wctx.diff, match=m, git=True):
                hu.write(s, label=l)
        except (IOError, error.RepoError, error.LookupError, util.Abort), e:
            self.status_error = str(e)
            return
        o, e = hu.getdata()
        diff = o or _('<em>No displayable differences</em>')

        if self.isMerge():
            header = _('===== Diff to first parent %d:%s =====\n') % (
                    self.wctx.p1().rev(), str(self.wctx.p1()))
            header = '<h3>' + header + '</h3></br>'
            text = header + diff
        else:
            self.te.setHtml(diff)
            return

        # Generate diffs to second parent
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
            path, status, mst, u = self.model().getRow(index)
            selrows.append((set(status+mst.lower()), path))
        point = self.mapToGlobal(point)
        action = wctxactions.wctxactions(self, point, self.repo, selrows)
        if action:
            self.emit(SIGNAL('menuAction()'))

    def selectedRows(self):
        return self.selectionModel().selectedRows()

class WctxModel(QAbstractTableModel):
    def __init__(self, wctx, ms, opts, checked, parent=None):
        QAbstractTableModel.__init__(self, parent)
        rows = []
        if opts['modified']:
            for m in wctx.modified():
                mst = m in ms and ms[m].upper() or ""
                checked[m] = checked.get(m, True)
                rows.append([m, 'M', mst, hglib.tounicode(m)])
        if opts['added']:
            for a in wctx.added():
                mst = a in ms and ms[a].upper() or ""
                checked[a] = checked.get(a, True)
                rows.append([a, 'A', mst, hglib.tounicode(a)])
        if opts['removed']:
            for r in wctx.removed():
                mst = r in ms and ms[r].upper() or ""
                checked[r] = checked.get(r, True)
                rows.append([r, 'R', mst, hglib.tounicode(r)])
        if opts['deleted']:
            for d in wctx.deleted():
                mst = d in ms and ms[d].upper() or ""
                checked[d] = checked.get(d, False)
                rows.append([d, '!', mst, hglib.tounicode(d)])
        if opts['unknown']:
            for u in wctx.unknown():
                checked[u] = checked.get(u, False)
            	rows.append([u, '?', '', hglib.tounicode(u)])
        if opts['ignored']:
            for i in wctx.ignored():
                checked[i] = checked.get(i, False)
            	rows.append([i, 'I', '', hglib.tounicode(i)])
        if opts['clean']:
            for c in wctx.clean():
                checked[c] = checked.get(c, False)
            	rows.append([c, 'C', '', hglib.tounicode(c)])
        if opts['subrepo']:
            try:
                for s in wctx.substate:
                    if wctx.sub(s).dirty():
                        checked[s] = checked.get(s, False)
                        rows.append([s, 'S', '', hglib.tounicode(s)])
            except (OSError, IOError, error.ConfigError), e:
                self.status_error = str(e)
        self.headers = ('*', _('Stat'), _('M'), _('Filename'))
        self.checked = checked
        self.unfiltered = rows
        self.rows = rows

    def rowCount(self, parent):
        return len(self.rows)

    def columnCount(self, parent):
        return len(self.headers)

    def data(self, index, role):
        if not index.isValid():
            return QVariant()

        path, status, mst, upath = self.rows[index.row()]
        if index.column() == COL_PATH:
            if role == Qt.CheckStateRole:
                # also Qt.PartiallyChecked
                if self.checked[path]:
                    return Qt.Checked
                else:
                    return Qt.Unchecked
        elif role == Qt.DisplayRole:
            return QVariant(self.rows[index.row()][index.column()])
        elif role == Qt.TextColorRole:
            if mst:
                return _colors.get(mst.lower(), QColor('black'))
            else:
                return _colors.get(status, QColor('black'))
        elif role == Qt.ToolTipRole:
            return QVariant(statusMessage(status, mst, upath))
        '''
        elif role == Qt.DecorationRole and index.column() == COL_STATUS:
            if status in statusTypes:
                ico = QIcon()
                ico.addPixmap(QPixmap('icons/' + statusTypes[status].icon))
                return QVariant(ico)
        '''
        return QVariant()

    def headerData(self, col, orientation, role):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return QVariant()
        else:
            return QVariant(self.headers[col])

    def flags(self, index):
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled
        if index.column() == COL_PATH:
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
        fname = self.rows[index.row()][COL_PATH]
        self.emit(SIGNAL("layoutAboutToBeChanged()"))
        self.checked[fname] = not self.checked[fname]
        self.emit(SIGNAL("layoutChanged()"))

    def pressedRow(self, index):
        'Connected to "pressed" signal, emitted by mouse clicks'
        assert index.isValid()
        if index.column() == COL_PATH:
            self.toggleRow(index)

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

    def setFilter(self, match):
        'simple match in filename filter'
        self.emit(SIGNAL("layoutAboutToBeChanged()"))
        self.rows = [r for r in self.unfiltered if match in r[COL_PATH_DISPLAY]]
        self.emit(SIGNAL("layoutChanged()"))
        self.reset()

    def getChecked(self):
        return self.checked.copy()

def statusMessage(status, mst, upath):
    tip = ''
    if status in statusTypes:
        tip = statusTypes[status].desc % upath
        if mst == 'R':
            tip += _(', resolved merge')
        elif mst == 'U':
            tip += _(', unresolved merge')
    return tip

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

def run(ui, *pats, **opts):
    return StatusWidget(pats, opts)

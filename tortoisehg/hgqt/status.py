# status.py - working copy browser
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import ui, hg, util, patch, cmdutil, error, mdiff
from mercurial import context, merge, commands, subrepo
from tortoisehg.hgqt import qtlib, htmlui, wctxactions, visdiff
from tortoisehg.hgqt import thgrepo, cmdui, fileview
from tortoisehg.util import paths, hglib
from tortoisehg.util.util import xml_escape
from tortoisehg.hgqt.i18n import _

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# This widget can be used as the basis of the commit tool or any other
# working copy browser.

# Technical Debt
#  We need a real icon set for file status types
#  Thread rowSelected, connect to an external progress bar
#  Chunk selection, tri-state checkboxes for commit
# Maybe, Maybe Not
#  Investigate folding/nesting of files
#  Toolbar
#  double-click visual diffs

COL_PATH = 0
COL_STATUS = 1
COL_MERGE_STATE = 2
COL_PATH_DISPLAY = 3
COL_EXTENSION = 4
COL_SIZE = 5

_colors = {}

class StatusWidget(QWidget):
    '''Working copy status widget
       SIGNALS:
       progress()                   - for progress bar
       showMessage(unicode)         - for status bar
       titleTextChanged(QString)    - for window title
    '''
    progress = pyqtSignal(QString, object, QString, QString, object)
    titleTextChanged = pyqtSignal(QString)
    linkActivated = pyqtSignal(QString)
    showMessage = pyqtSignal(unicode)
    fileDisplayed = pyqtSignal(QString, QString)

    def __init__(self, pats, opts, root=None, parent=None):
        QWidget.__init__(self, parent)

        root = paths.find_root(root)
        assert(root)
        self.repo = thgrepo.repository(ui.ui(), path=root)
        self.wctx = self.repo[None]
        self.opts = dict(modified=True, added=True, removed=True, deleted=True,
                         unknown=True, clean=False, ignored=False, subrepo=True)
        self.opts.update(opts)
        self.pats = pats
        self.ms = {}
        self.patchecked = {}
        self.refreshing = None

        # determine the user configured status colors
        # (in the future, we could support full rich-text tags)
        labels = [(stat, val.uilabel) for stat, val in statusTypes.items()]
        labels.extend([('r', 'resolve.resolved'), ('u', 'resolve.unresolved')])
        for stat, label in labels:
            effect = qtlib.geteffect(label)
            for e in effect.split(';'):
                if e.startswith('color:'):
                    _colors[stat] = QColor(e[7:])
                    break

        SP = QSizePolicy

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.addWidget(split)
        self.setLayout(layout)

        vbox = QVBoxLayout()
        vbox.setMargin(0)
        frame = QFrame(split)
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        frame.setSizePolicy(sp)
        frame.setLayout(vbox)
        hbox = QHBoxLayout()
        hbox.setContentsMargins (5, 0, 0, 0)
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
                self.titleTextChanged.emit(QString(self.getTitle()))
            cpb = QPushButton(_('Remove filter, show root'))
            vbox.addWidget(cpb)
            cpb.clicked.connect(clearPattern)

        self.countlbl = QLabel()
        hcbox = QHBoxLayout()
        vbox.addLayout(hcbox)
        hcbox.addSpacing(6)
        hcbox.addWidget(self.countlbl)

        tv.clicked.connect(self.rowSelected)
        tv.menuAction.connect(self.refreshWctx)
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
        vbox.setSpacing(0)
        vbox.setContentsMargins(0, 0, 0, 0)
        docf = QFrame(split)
        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(1)
        sp.setVerticalStretch(0)
        docf.setSizePolicy(sp)
        docf.setLayout(vbox)
        self.docf = docf

        self.fileview = fileview.HgFileView(self)
        self.fileview.showMessage.connect(self.showMessage)
        self.fileview.linkActivated.connect(self.linkActivated)
        self.fileview.fileDisplayed.connect(self.fileDisplayed)
        self.fileview.setMode('diff')
        vbox.addWidget(self.fileview, 1)

        self.split = split
        self.diffvbox = vbox

    def getTitle(self):
        if self.pats:
            return _('%s - status (selection filtered)') % self.repo.displayname
        else:
            return _('%s - status') % self.repo.displayname

    def restoreState(self, data):
        return self.split.restoreState(data)

    def saveState(self):
        return self.split.saveState()

    def refreshWctx(self):
        if self.refreshing:
            return
        self.fileview.clearDisplay()

        # store selected paths or current path
        model = self.tv.model()
        if model:
            sp = [model.getRow(i)[COL_PATH] for i in self.tv.selectedRows()]
            if not sp:
                index = self.tv.selectionModel().currentIndex()
                if index.isValid():
                    sp = [model.getRow(index)[COL_PATH]]
        else:
            sp = None
        self.sp = sp

        self.progress.emit(*cmdui.startProgress(_('Refresh'), _('status')))
        self.refreshing = StatusThread(self.repo, self.pats, self.opts)
        self.refreshing.finished.connect(self.reloadComplete)
        self.refreshing.showMessage.connect(self.showMessage)
        self.refreshing.start()

    def reloadComplete(self):
        self.refreshing.wait()
        if self.refreshing.wctx is None:
            return
        self.ms = merge.mergestate(self.repo)
        self.wctx = self.refreshing.wctx
        self.patchecked = self.refreshing.patchecked
        self.updateModel()
        self.progress.emit(*cmdui.stopProgress(_('Refresh')))
        self.refreshing = None

    def updateModel(self):
        self.tv.setSortingEnabled(False)
        if self.tv.model():
            checked = self.tv.model().getChecked()
        else:
            checked = self.patchecked
            if self.pats and not self.patchecked:
                qtlib.WarningMsgBox(_('No appropriate files'),
                                    _('No files found for this operation'),
                                    parent=self)
        tm = WctxModel(self.wctx, self.ms, self.opts, checked)
        self.tv.setModel(tm)
        self.tv.setSortingEnabled(True)
        self.tv.setColumnHidden(COL_PATH, self.isMerge())
        self.tv.setColumnHidden(COL_MERGE_STATE, not tm.anyMerge())

        for col in (COL_PATH, COL_STATUS, COL_MERGE_STATE):
            w = self.tv.sizeHintForColumn(col)
            self.tv.setColumnWidth(col, w)
        for col in (COL_PATH_DISPLAY, COL_EXTENSION, COL_SIZE):
            self.tv.resizeColumnToContents(col)

        self.tv.doubleClicked.connect(tm.toggleRow)
        self.tv.pressed.connect(tm.pressedRow)
        self.le.textEdited.connect(tm.setFilter)
        tm.checkToggled.connect(self.updateCheckCount)
        self.updateCheckCount()

        # reset selection, or select first row
        selmodel = self.tv.selectionModel()
        flags = QItemSelectionModel.Select | QItemSelectionModel.Rows
        if self.sp:
            first = None
            for i, row in enumerate(tm.getAllRows()):
                if row[COL_PATH] in self.sp:
                    index = tm.index(i, 0)
                    selmodel.select(index, flags)
                    if not first: first = index
        else:
            first = tm.index(0, 0)
            selmodel.select(first, flags)
        if first and first.isValid():
            self.rowSelected(first)

    def updateCheckCount(self):
        text = _('Checkmarked file count: %d') % len(self.getChecked())
        self.countlbl.setText(text)

    def isMerge(self):
        return bool(self.wctx.p2())

    def getChecked(self, types=None):
        model = self.tv.model()
        if model:
            checked = model.getChecked()
            if types is None:
                return [f for f, v in checked.iteritems() if v]
            else:
                files = []
                for row in model.getAllRows():
                    path, status, mst, upath, ext, sz = row
                    if status in types and checked[path]:
                        files.append(path)
                return files
        else:
            return []

    def rowSelected(self, index):
        'Connected to treeview "clicked" signal'
        row = index.model().getRow(index)
        if row is None:
            return
        path, status, mst, upath, ext, sz = row
        wfile = util.pconvert(path)
        self.fileview.setContext(self.wctx)
        self.fileview.displayFile(wfile, status=status)


class StatusThread(QThread):
    '''Background thread for generating a workingctx'''

    showMessage = pyqtSignal(QString)

    def __init__(self, repo, pats, opts, parent=None):
        super(StatusThread, self).__init__()
        self.repo = repo
        self.pats = pats
        self.opts = opts
        self.wctx = None
        self.patchecked = None

    def run(self):
        self.repo.dirstate.invalidate()
        extract = lambda x, y: dict(zip(x, map(y.get, x)))
        stopts = extract(('unknown', 'ignored', 'clean'), self.opts)
        patchecked = {}
        try:
            if self.pats:
                m = cmdutil.match(self.repo, self.pats)
                status = self.repo.status(match=m, **stopts)
                # Record all matched files as initially checked
                for i, stat in enumerate(StatusType.preferredOrder):
                    if stat == 'S':
                        continue
                    val = statusTypes[stat]
                    if self.opts[val.name]:
                        d = dict([(fn, True) for fn in status[i]])
                        patchecked.update(d)
                wctx = context.workingctx(self.repo, changes=status)
            else:
                wctx = self.repo[None]
                wctx.status(**stopts)
        except (OSError, IOError), e:
            self.showMessage.emit(hglib.tounicode(str(e)))
        except util.Abort, e:
            if e.hint:
                err = _('%s (hint: %s)') % (hglib.tounicode(str(e)),
                                            hglib.tounicode(e.hint))
            else:
                err = hglib.tounicode(str(e))
            self.showMessage.emit(err)
        try:
            wctx.dirtySubrepos = []
            for s in wctx.substate:
                if wctx.sub(s).dirty():
                    wctx.dirtySubrepos.append(s)
        except (OSError, IOError, error.RepoLookupError, error.ConfigError), e:
            self.showMessage.emit(hglib.tounicode(str(e)))
        except util.Abort, e:
            if e.hint:
                err = _('%s (hint: %s)') % (hglib.tounicode(str(e)),
                                            hglib.tounicode(e.hint))
            else:
                err = hglib.tounicode(str(e))
            self.showMessage.emit(err)
        self.wctx = wctx
        self.patchecked = patchecked


class WctxFileTree(QTreeView):
    menuAction = pyqtSignal()

    def __init__(self, repo, parent=None):
        QTreeView.__init__(self, parent)
        self.repo = repo
        self.setSelectionMode(QTreeView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menuRequested)
        self.setTextElideMode(Qt.ElideLeft)

    def scrollTo(self, index, hint=QAbstractItemView.EnsureVisible):
        # don't update horizontal position by selection change
        orighoriz = self.horizontalScrollBar().value()
        super(WctxFileTree, self).scrollTo(index, hint)
        self.horizontalScrollBar().setValue(orighoriz)

    def keyPressEvent(self, event):
        if event.key() == 32:
            for index in self.selectedRows():
                self.model().toggleRow(index)
        if event.key() == Qt.Key_D and event.modifiers() == Qt.ControlModifier:
            selfiles = []
            for index in self.selectedRows():
                selfiles.append(self.model().getRow(index)[COL_PATH])
            dlg = visdiff.visualdiff(self.repo.ui, self.repo, selfiles, {})
            if dlg:
                dlf.exec_()
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

    def mousePressEvent(self, event):
        self.pressPos = event.pos()
        self.pressTime = QTime.currentTime()
        return QTreeView.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        d = event.pos() - self.pressPos
        if d.manhattanLength() < QApplication.startDragDistance():
            return QTreeView.mouseMoveEvent(self, event)
        elapsed = self.pressTime.msecsTo(QTime.currentTime())
        if elapsed < QApplication.startDragTime():
            return QTreeView.mouseMoveEvent(self, event)
        self.dragObject()
        return QTreeView.mouseMoveEvent(self, event)

    def menuRequested(self, point):
        selrows = []
        for index in self.selectedRows():
            path, status, mst, u, ext, sz = self.model().getRow(index)
            selrows.append((set(status+mst.lower()), path))
        point = self.mapToGlobal(point)
        action = wctxactions.wctxactions(self, point, self.repo, selrows)
        if action:
            self.menuAction.emit()

    def selectedRows(self):
        return self.selectionModel().selectedRows()

class WctxModel(QAbstractTableModel):
    checkToggled = pyqtSignal()

    def __init__(self, wctx, ms, opts, checked, parent=None):
        QAbstractTableModel.__init__(self, parent)
        rows = []
        nchecked = {}
        def mkrow(fname, st):
            ext, sizek = '', ''
            try:
                mst = fname in ms and ms[fname].upper() or ""
                name, ext = os.path.splitext(fname)
                sizebytes = wctx[fname].size()
                sizek = (sizebytes + 1023) // 1024
            except EnvironmentError:
                pass
            return [fname, st, mst, hglib.tounicode(fname), ext[1:], sizek]
        if opts['modified']:
            for m in wctx.modified():
                nchecked[m] = checked.get(m, True)
                rows.append(mkrow(m, 'M'))
        if opts['added']:
            for a in wctx.added():
                nchecked[a] = checked.get(a, True)
                rows.append(mkrow(a, 'A'))
        if opts['removed']:
            for r in wctx.removed():
                mst = r in ms and ms[r].upper() or ""
                nchecked[r] = checked.get(r, True)
                rows.append(mkrow(r, 'R'))
        if opts['deleted']:
            for d in wctx.deleted():
                mst = d in ms and ms[d].upper() or ""
                nchecked[d] = checked.get(d, False)
                rows.append(mkrow(d, '!'))
        if opts['unknown']:
            for u in wctx.unknown():
                nchecked[u] = checked.get(u, False)
                rows.append(mkrow(u, '?'))
        if opts['ignored']:
            for i in wctx.ignored():
                nchecked[i] = checked.get(i, False)
                rows.append(mkrow(i, 'I'))
        if opts['clean']:
            for c in wctx.clean():
                nchecked[c] = checked.get(c, False)
                rows.append(mkrow(c, 'C'))
        if opts['subrepo']:
            for s in wctx.dirtySubrepos:
                nchecked[s] = checked.get(s, True)
                rows.append(mkrow(s, 'S'))
        # include clean unresolved files
        for f in ms:
            if ms[f] == 'u' and f not in nchecked:
                nchecked[f] = checked.get(f, True)
                rows.append(mkrow(f, 'C'))
        self.headers = ('*', _('Stat'), _('M'), _('Filename'), 
                        _('Type'), _('Size (KB)'))
        self.checked = nchecked
        self.unfiltered = rows
        self.rows = rows

    def rowCount(self, parent):
        if parent.isValid():
            return 0 # no child
        return len(self.rows)

    def columnCount(self, parent):
        if parent.isValid():
            return 0 # no child
        return len(self.headers)

    def data(self, index, role):
        if not index.isValid():
            return QVariant()

        path, status, mst, upath, ext, sz = self.rows[index.row()]
        if index.column() == COL_PATH:
            if role == Qt.CheckStateRole:
                # also Qt.PartiallyChecked
                if self.checked[path]:
                    return Qt.Checked
                else:
                    return Qt.Unchecked
            elif role == Qt.DisplayRole:
                return QVariant("")
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

    def getAllRows(self):
        for row in self.rows:
            yield row

    def toggleRow(self, index):
        'Connected to "activated" signal, emitted by dbl-click or enter'
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            # ignore Ctrl-Enter events, the user does not want a row
            # toggled just as they are committing.
            return
        assert index.isValid()
        fname = self.rows[index.row()][COL_PATH]
        self.layoutAboutToBeChanged.emit()
        self.checked[fname] = not self.checked[fname]
        self.layoutChanged.emit()
        self.checkToggled.emit()

    def pressedRow(self, index):
        'Connected to "pressed" signal, emitted by mouse clicks'
        assert index.isValid()
        if index.column() == COL_PATH:
            self.toggleRow(index)

    def sort(self, col, order):
        self.layoutAboutToBeChanged.emit()
        if col == COL_PATH:
            c = self.checked
            self.rows.sort(lambda x, y: cmp(c[x[col]], c[y[col]]))
        else:
            self.rows.sort(lambda x, y: cmp(x[col], y[col]))
        if order == Qt.DescendingOrder:
            self.rows.reverse()
        self.layoutChanged.emit()
        self.reset()

    def setFilter(self, match):
        'simple match in filename filter'
        self.layoutAboutToBeChanged.emit()
        self.rows = [r for r in self.unfiltered if match in r[COL_PATH_DISPLAY]]
        self.layoutChanged.emit()
        self.reset()

    def getChecked(self):
        return self.checked.copy()

def statusMessage(status, mst, upath):
    tip = ''
    if status in statusTypes:
        upath = "<span style='font-family:Courier'>%s </span>" % upath
        tip = statusTypes[status].desc % upath
        if mst == 'R':
            tip += _(', resolved merge')
        elif mst == 'U':
            tip += _(', unresolved merge')
    return tip

class StatusType(object):
    preferredOrder = 'MAR!?ICS'
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

class StatusDialog(QDialog):
    'Standalone status browser'
    def __init__(self, pats, opts, root=None, parent=None):
        QDialog.__init__(self, parent)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 6, 0, 0)
        self.setLayout(layout)
        self.stwidget = StatusWidget(pats, opts, root, self)
        layout.addWidget(self.stwidget, 1)

        s = QSettings()
        self.stwidget.restoreState(s.value('status/state').toByteArray())
        self.restoreGeometry(s.value('status/geom').toByteArray())

        self.statusbar = cmdui.ThgStatusBar(self)
        layout.addWidget(self.statusbar)
        self.stwidget.showMessage.connect(self.statusbar.showMessage)
        self.stwidget.progress.connect(self.statusbar.progress)
        self.stwidget.titleTextChanged.connect(self.setWindowTitle)
        self.setWindowTitle(self.stwidget.getTitle())

        QTimer.singleShot(0, self.stwidget.refreshWctx)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Refresh):
            self.stwidget.refreshWctx()
        else:
            return super(StatusDialog, self).keyPressEvent(event)

    def accept(self):
        s = QSettings()
        s.setValue('status/state', self.stwidget.saveState())
        s.setValue('status/geom', self.saveGeometry())
        QDialog.accept(self)

    def reject(self):
        s = QSettings()
        s.setValue('status/state', self.stwidget.saveState())
        s.setValue('status/geom', self.saveGeometry())
        QDialog.reject(self)

def run(ui, *pats, **opts):
    return StatusDialog(pats, opts)

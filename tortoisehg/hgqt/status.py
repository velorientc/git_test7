# status.py - working copy browser
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import hg, util, cmdutil, error, context, merge

from tortoisehg.util import paths, hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, wctxactions, visdiff, cmdui, fileview, thgrepo

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

    def __init__(self, repo, pats, opts, parent=None, checkable=True):
        QWidget.__init__(self, parent)

        self.opts = dict(modified=True, added=True, removed=True, deleted=True,
                         unknown=True, clean=False, ignored=False, subrepo=True)
        self.opts.update(opts)
        self.repo = repo
        self.pats = pats
        self.checkable = checkable
        self.pctx = None
        self.savechecks = True
        self.refthread = None

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
        hbox.setMargin(4)
        hbox.setContentsMargins(0, 0, 0, 0)
        self.refreshBtn = tb = QToolButton()
        tb.setToolTip(_('Refresh file list'))
        tb.setIcon(qtlib.geticon('view-refresh'))
        tb.clicked.connect(self.refreshWctx)
        le = QLineEdit()
        if hasattr(le, 'setPlaceholderText'): # Qt >= 4.7
            le.setPlaceholderText(_('### filter text ###'))
        else:
            lbl = QLabel(_('Filter:'))
            hbox.addWidget(lbl)

        st = ''
        for s in statusTypes:
            val = statusTypes[s]
            if self.opts[val.name]:
                st = st + s
        self.statusfilter = StatusFilterButton(
            statustext=st, types=StatusType.preferredOrder)

        if self.checkable:
            self.checkAllTT = _('Check all files')
            self.checkNoneTT = _('Uncheck all files')
            self.checkAllNoneBtn = QCheckBox()
            self.checkAllNoneBtn.setToolTip(self.checkAllTT)
            self.checkAllNoneBtn.stateChanged.connect(self.checkAllNone)

        self.filelistToolbar = QToolBar(_('Status File List Toolbar'))
        self.filelistToolbar.setIconSize(QSize(16,16))
        self.filelistToolbar.setStyleSheet(qtlib.tbstylesheet)
        hbox.addWidget(self.filelistToolbar)
        if self.checkable:
            self.filelistToolbar.addWidget(qtlib.Spacer(3, 2))
            self.filelistToolbar.addWidget(self.checkAllNoneBtn)
            self.filelistToolbar.addSeparator()
        self.filelistToolbar.addWidget(le)
        self.filelistToolbar.addSeparator()
        self.filelistToolbar.addWidget(self.statusfilter)
        self.filelistToolbar.addSeparator()
        self.filelistToolbar.addWidget(self.refreshBtn)
        self.actions = wctxactions.WctxActions(self.repo, self)
        tv = WctxFileTree(self.repo, checkable=checkable)
        vbox.addLayout(hbox)
        vbox.addWidget(tv)
        split.addWidget(frame)

        if self.pats:
            def clearPattern():
                self.pats = []
                self.refreshWctx()
                cpb.setVisible(False)
                self.titleTextChanged.emit(self.getTitle())
            cpb = QPushButton(_('Remove filter, show root'))
            vbox.addWidget(cpb)
            cpb.clicked.connect(clearPattern)

        tv.setItemsExpandable(False)
        tv.setRootIsDecorated(False)
        tv.sortByColumn(COL_STATUS, Qt.AscendingOrder)
        tv.clicked.connect(self.onRowClicked)
        tv.doubleClicked.connect(self.onRowDoubleClicked)
        tv.menuRequest.connect(self.onMenuRequest)
        le.textEdited.connect(self.setFilter)

        def statusTypeTrigger(status):
            status = str(status)
            for s in statusTypes:
                val = statusTypes[s]
                self.opts[val.name] = s in status
            self.refreshWctx()
        self.statusfilter.statusChanged.connect(statusTypeTrigger)

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

        self.fileview = fileview.HgFileView(self.repo, self)
        self.fileview.showMessage.connect(self.showMessage)
        self.fileview.linkActivated.connect(self.linkActivated)
        self.fileview.fileDisplayed.connect(self.fileDisplayed)
        self.fileview.shelveToolExited.connect(self.refreshWctx)
        self.fileview.setContext(self.repo[None])
        self.fileview.setMinimumSize(QSize(16, 16))
        vbox.addWidget(self.fileview, 1)

        self.split = split
        self.diffvbox = vbox

    def checkAllNone(self):
        state = self.checkAllNoneBtn.checkState()
        if state == Qt.Checked:
            self.checkAll()
            self.checkAllNoneBtn.setToolTip(self.checkNoneTT)
        else:
            if state == Qt.Unchecked:
                self.checkNone()
            self.checkAllNoneBtn.setToolTip(self.checkAllTT)
        if state != Qt.PartiallyChecked:
            self.checkAllNoneBtn.setTristate(False)

    def getTitle(self):
        if self.pats:
            return _('%s - status (selection filtered)') % self.repo.displayname
        else:
            return _('%s - status') % self.repo.displayname

    def loadSettings(self, qs, prefix):
        self.fileview.loadSettings(qs, prefix+'/fileview')
        self.split.restoreState(qs.value(prefix+'/state').toByteArray())

    def saveSettings(self, qs, prefix):
        self.fileview.saveSettings(qs, prefix+'/fileview')
        qs.setValue(prefix+'/state', self.split.saveState())

    @pyqtSlot(QPoint, object)
    def onMenuRequest(self, point, selected):
        menu = self.actions.makeMenu(selected)
        if menu.exec_(point):
            self.refreshWctx()

    def setPatchContext(self, pctx):
        if pctx != self.pctx:
            self.savechecks = False
        else:
            self.savechecks = True
        self.pctx = pctx

    def refreshWctx(self, synchronous=False):
        if self.refthread:
            return
        self.fileview.clearDisplay()

        # store selected paths or current path
        model = self.tv.model()
        if model and model.rowCount(QModelIndex()):
            smodel = self.tv.selectionModel()
            curidx = smodel.currentIndex()
            if curidx.isValid():
                curpath = model.getRow(curidx)[COL_PATH]
            else:
                curpath = None
            spaths = [model.getRow(i)[COL_PATH] for i in smodel.selectedRows()]
            self.reselection = spaths, curpath
        else:
            self.reselection = None

        if self.checkable:
            self.checkAllNoneBtn.setEnabled(False)
        self.refreshBtn.setEnabled(False)
        self.progress.emit(*cmdui.startProgress(_('Refresh'), _('status')))
        self.refthread = StatusThread(self.repo, self.pctx, self.pats, self.opts)
        if not synchronous:
            self.refthread.finished.connect(self.reloadComplete)
        self.refthread.showMessage.connect(self.showMessage)
        self.refthread.start()
        if synchronous:
            self.reloadComplete()

    def reloadComplete(self):
        self.refthread.wait()
        if self.checkable:
            self.checkAllNoneBtn.setEnabled(True)
        self.refreshBtn.setEnabled(True)
        self.progress.emit(*cmdui.stopProgress(_('Refresh')))
        if self.refthread.wctx is not None:
            self.updateModel(self.refthread.wctx, self.refthread.patchecked)
        self.refthread = None

    def canExit(self):
        return not self.refthread

    def updateModel(self, wctx, patchecked):
        self.tv.setSortingEnabled(False)
        if self.tv.model():
            checked = self.tv.model().getChecked()
        else:
            checked = patchecked
            if self.pats and not checked:
                qtlib.WarningMsgBox(_('No appropriate files'),
                                    _('No files found for this operation'),
                                    parent=self)
        ms = merge.mergestate(self.repo)
        tm = WctxModel(wctx, ms, self.pctx, self.savechecks, self.opts,
                       checked, self, checkable=self.checkable)
        if self.checkable:
            tm.checkToggled.connect(self.updateCheckCount)

        self.tv.setModel(tm)
        self.tv.setSortingEnabled(True)
        self.tv.setColumnHidden(COL_PATH, bool(wctx.p2()) or not self.checkable)
        self.tv.setColumnHidden(COL_MERGE_STATE, not tm.anyMerge())
        if self.checkable:
            self.updateCheckCount()

        for col in (COL_PATH, COL_STATUS, COL_MERGE_STATE):
            w = self.tv.sizeHintForColumn(col)
            self.tv.setColumnWidth(col, w)
        for col in (COL_PATH_DISPLAY, COL_EXTENSION, COL_SIZE):
            self.tv.resizeColumnToContents(col)

        # reset selection, or select first row
        curidx = tm.index(0, 0)
        selmodel = self.tv.selectionModel()
        flags = QItemSelectionModel.Select | QItemSelectionModel.Rows
        if self.reselection:
            selected, current = self.reselection
            for i, row in enumerate(tm.getAllRows()):
                if row[COL_PATH] in selected:
                    selmodel.select(tm.index(i, 0), flags)
                if row[COL_PATH] == current:
                    curidx = tm.index(i, 0)
        else:
            selmodel.select(curidx, flags)
        selmodel.currentChanged.connect(self.onCurrentChange)
        selmodel.selectionChanged.connect(self.onSelectionChange)
        if curidx and curidx.isValid():
            selmodel.setCurrentIndex(curidx, QItemSelectionModel.Current)
        self.onSelectionChange(None, None)

    # Disabled decorator because of bug in older PyQt releases
    #@pyqtSlot(QModelIndex)
    def onRowClicked(self, index):
        'tree view emitted a clicked signal, index guarunteed valid'
        if index.column() == COL_PATH:
            self.tv.model().toggleRows([index])

    # Disabled decorator because of bug in older PyQt releases
    #@pyqtSlot(QModelIndex)
    def onRowDoubleClicked(self, index):
        'tree view emitted a doubleClicked signal, index guarunteed valid'
        path, status, mst, u, ext, sz = self.tv.model().getRow(index)
        if status in 'MAR!':
            self.actions.allactions[0].trigger()
        elif status == 'S':
            self.linkActivated.emit(
                u'subrepo:' + hglib.tounicode(self.repo.wjoin(path)))
        elif status in 'C?':
            qtlib.editfiles(self.repo, [path])

    @pyqtSlot(QString)
    def setFilter(self, match):
        model = self.tv.model()
        if model:
            model.setFilter(match)

    def updateCheckCount(self):
        model = self.tv.model()
        if model:
            model.checkCount = len(self.getChecked())
            if model.checkCount == 0:
                state = Qt.Unchecked
            elif model.checkCount == len(model.rows):
                state = Qt.Checked
            else:
                state = Qt.PartiallyChecked
            self.checkAllNoneBtn.setCheckState(state)

    def checkAll(self):
        model = self.tv.model()
        if model:
            model.checkAll(True)

    def checkNone(self):
        model = self.tv.model()
        if model:
            model.checkAll(False)

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

    # Disabled decorator because of bug in older PyQt releases
    #@pyqtSlot(QItemSelection, QItemSelection)
    def onSelectionChange(self, selected, deselected):
        selrows = []
        for index in self.tv.selectedRows():
            path, status, mst, u, ext, sz = self.tv.model().getRow(index)
            selrows.append((set(status+mst.lower()), path))
        self.actions.updateActionSensitivity(selrows)

    # Disabled decorator because of bug in older PyQt releases
    #@pyqtSlot(QModelIndex, QModelIndex)
    def onCurrentChange(self, index, old):
        'Connected to treeview "currentChanged" signal'
        row = index.model().getRow(index)
        if row is None:
            return
        path, status, mst, upath, ext, sz = row
        wfile = util.pconvert(path)
        pctx = self.pctx and self.pctx.p1() or None
        self.fileview.setContext(self.repo[None], pctx)
        self.fileview.displayFile(wfile, status)


class StatusThread(QThread):
    '''Background thread for generating a workingctx'''

    showMessage = pyqtSignal(QString)

    def __init__(self, repo, pctx, pats, opts, parent=None):
        super(StatusThread, self).__init__()
        self.repo = thgrepo.repository(repo.ui, repo.root)
        self.pctx = pctx
        self.pats = pats
        self.opts = opts
        self.wctx = None
        self.patchecked = {}

    def run(self):
        self.repo.dirstate.invalidate()
        extract = lambda x, y: dict(zip(x, map(y.get, x)))
        stopts = extract(('unknown', 'ignored', 'clean'), self.opts)
        patchecked = {}
        try:
            if self.pats:
                if self.opts.get('checkall'):
                    # quickop sets this flag to pre-check even !?IC files
                    precheckfn = lambda x: True
                else:
                    # status and commit only pre-check MAR files
                    precheckfn = lambda x: x < 4
                m = hglib.match(self.repo[None], self.pats)
                self.repo.bfstatus = True
                self.repo.lfstatus = True
                status = self.repo.status(match=m, **stopts)
                self.repo.bfstatus = False
                self.repo.lfstatus = False
                # Record all matched files as initially checked
                for i, stat in enumerate(StatusType.preferredOrder):
                    if stat == 'S':
                        continue
                    val = statusTypes[stat]
                    if self.opts[val.name]:
                        d = dict([(fn, precheckfn(i)) for fn in status[i]])
                        patchecked.update(d)
                wctx = context.workingctx(self.repo, changes=status)
                self.patchecked = patchecked
            elif self.pctx:
                self.repo.bfstatus = True
                self.repo.lfstatus = True
                status = self.repo.status(node1=self.pctx.p1().node(), **stopts)
                self.repo.bfstatus = False
                self.repo.lfstatus = False
                wctx = context.workingctx(self.repo, changes=status)
            else:
                wctx = self.repo[None]
                self.repo.bfstatus = True
                self.repo.lfstatus = True
                wctx.status(**stopts)
                self.repo.bfstatus = False
                self.repo.lfstatus = False
            self.wctx = wctx

            wctx.dirtySubrepos = []
            for s in wctx.substate:
                if wctx.sub(s).dirty():
                    wctx.dirtySubrepos.append(s)
        except EnvironmentError, e:
            self.showMessage.emit(hglib.tounicode(str(e)))
        except (error.LookupError, error.RepoError, error.ConfigError), e:
            self.showMessage.emit(hglib.tounicode(str(e)))
        except util.Abort, e:
            if e.hint:
                err = _('%s (hint: %s)') % (hglib.tounicode(str(e)),
                                            hglib.tounicode(e.hint))
            else:
                err = hglib.tounicode(str(e))
            self.showMessage.emit(err)


class WctxFileTree(QTreeView):
    menuRequest = pyqtSignal(QPoint, object)

    def __init__(self, repo, parent=None, checkable=True):
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
            self.model().toggleRows(self.selectedRows())
        return super(WctxFileTree, self).keyPressEvent(event)

    def dragObject(self):
        urls = []
        for index in self.selectedRows():
            path = self.model().getRow(index)[COL_PATH]
            urls.append(QUrl.fromLocalFile(self.repo.wjoin(path)))
        if urls:
            drag = QDrag(self)
            data = QMimeData()
            data.setUrls(urls)
            drag.setMimeData(data)
            drag.start(Qt.CopyAction)

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
        if selrows:
            self.menuRequest.emit(self.viewport().mapToGlobal(point), selrows)

    def selectedRows(self):
        if self.selectionModel():
            return self.selectionModel().selectedRows()
        # Invalid selectionModel found
        return []

class WctxModel(QAbstractTableModel):
    checkToggled = pyqtSignal()

    def __init__(self, wctx, ms, pctx, savechecks, opts, checked, parent, checkable=True):
        QAbstractTableModel.__init__(self, parent)
        self.checkCount = 0
        rows = []
        nchecked = {}
        excludes = [f.strip() for f in opts.get('ciexclude', '').split(',')]
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
        if not savechecks:
            checked = {}
        if pctx:
            # Currently, having a patch context means it's a qrefresh, so only
            # auto-check files in pctx.files()
            pctxfiles = pctx.files()
            pctxmatch = lambda f: f in pctxfiles
        else:
            pctxmatch = lambda f: True
        if opts['modified']:
            for m in wctx.modified():
                nchecked[m] = checked.get(m, m not in excludes and pctxmatch(m))
                rows.append(mkrow(m, 'M'))
        if opts['added']:
            for a in wctx.added():
                nchecked[a] = checked.get(a, a not in excludes and pctxmatch(a))
                rows.append(mkrow(a, 'A'))
        if opts['removed']:
            for r in wctx.removed():
                nchecked[r] = checked.get(r, r not in excludes and pctxmatch(r))
                rows.append(mkrow(r, 'R'))
        if opts['deleted']:
            for d in wctx.deleted():
                nchecked[d] = checked.get(d, d not in excludes and pctxmatch(d))
                rows.append(mkrow(d, '!'))
        if opts['unknown']:
            for u in wctx.unknown() or []:
                nchecked[u] = checked.get(u, False)
                rows.append(mkrow(u, '?'))
        if opts['ignored']:
            for i in wctx.ignored() or []:
                nchecked[i] = checked.get(i, False)
                rows.append(mkrow(i, 'I'))
        if opts['clean']:
            for c in wctx.clean() or []:
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
        self.checkable = checkable

    def rowCount(self, parent):
        if parent.isValid():
            return 0 # no child
        return len(self.rows)

    def checkAll(self, state):
        for data in self.rows:
            self.checked[data[0]] = state
        self.layoutChanged.emit()
        self.checkToggled.emit()

    def columnCount(self, parent):
        if parent.isValid():
            return 0 # no child
        return len(self.headers)

    def data(self, index, role):
        if not index.isValid():
            return QVariant()

        path, status, mst, upath, ext, sz = self.rows[index.row()]
        if index.column() == COL_PATH:
            if role == Qt.CheckStateRole and self.checkable:
                # also Qt.PartiallyChecked
                if self.checked[path]:
                    return Qt.Checked
                else:
                    return Qt.Unchecked
            elif role == Qt.DisplayRole:
                return QVariant("")
            elif role == Qt.ToolTipRole:
                return QVariant(_('Checked count: %d') % self.checkCount)
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
        if index.column() == COL_PATH and self.checkable:
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

    def toggleRows(self, indexes):
        'Connected to "activated" signal, emitted by dbl-click or enter'
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            # ignore Ctrl-Enter events, the user does not want a row
            # toggled just as they are committing.
            return
        self.layoutAboutToBeChanged.emit()
        for index in indexes:
            assert index.isValid()
            fname = self.rows[index.row()][COL_PATH]
            self.checked[fname] = not self.checked[fname]
        self.layoutChanged.emit()
        self.checkToggled.emit()

    def sort(self, col, order):
        self.layoutAboutToBeChanged.emit()

        def getStatusRank(value):
            """Helper function used to sort items according to their hg status

            Statuses are ranked in the following order:
                'S','M','A','R','!','?','C','I',''
            """
            sortList = ['S','M','A','R','!','?','C','I','']

            try:
                rank = sortList.index(value)
            except (IndexError, ValueError):
                rank = len(shortList) # Set the lowest rank by default

            return rank

        def getMergeStatusRank(value):
            """Helper function used to sort according to item merge status

            Merge statuses are ranked in the following order:
                'S','U','R',''
            """
            sortList = ['S','U','R','']

            try:
                rank = sortList.index(value)
            except (IndexError, ValueError):
                rank = len(shortList) # Set the lowest rank by default

            return rank

        # We want to sort the list by one of the columns (checked state,
        # mercurial status, file path, file extension, etc)
        # However, for files which have the same status or extension, etc,
        # we want them to be sorted alphabetically (without taking into account
        # the case)
        # Since Python 2.3 the sort function is guaranteed to be stable.
        # Thus we can perform the sort in two passes:
        # 1.- Perform a secondary sort by path
        # 2.- Perform a primary sort by the actual column that we are sorting on

        # Secondary sort:
        self.rows.sort(key=lambda x: x[COL_PATH].lower())

        if col == COL_PATH_DISPLAY:
            # Already sorted!
            pass
        else:
            if order == Qt.DescendingOrder:
                # We want the secondary sort to be by _ascending_ path,
                # even when the primary sort is in descending order
                self.rows.reverse()

            # Now we can perform the primary sort
            if col == COL_PATH:
                c = self.checked
                self.rows.sort(key=lambda x: c[x[col]])
            elif col == COL_STATUS:
                self.rows.sort(key=lambda x: getStatusRank(x[col]))
            elif col == COL_MERGE_STATE:
                self.rows.sort(key=lambda x: getMergeStatusRank(x[col]))
            else:
                self.rows.sort(key=lambda x: x[col])

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
    def __init__(self, name, icon, desc, uilabel, trname):
        self.name = name
        self.icon = icon
        self.desc = desc
        self.uilabel = uilabel
        self.trname = trname

statusTypes = {
    'M' : StatusType('modified', 'menucommit.ico', _('%s is modified'),
                     'status.modified', _('modified')),
    'A' : StatusType('added', 'fileadd.ico', _('%s is added'),
                     'status.added', _('added')),
    'R' : StatusType('removed', 'filedelete.ico', _('%s is removed'),
                     'status.removed', _('removed')),
    '?' : StatusType('unknown', 'shelve.ico', _('%s is not tracked (unknown)'),
                     'status.unknown', _('unknown')),
    '!' : StatusType('deleted', 'menudelete.ico', _('%s is missing!'),
                     'status.deleted', _('deleted')),
    'I' : StatusType('ignored', 'ignore.ico', _('%s is ignored'),
                     'status.ignored', _('ignored')),
    'C' : StatusType('clean', '', _('%s is not modified (clean)'),
                     'status.clean', _('clean')),
    'S' : StatusType('subrepo', 'thg-subrepo.ico', _('%s is a dirty subrepo'),
                     'status.subrepo', _('subrepo')),
}


class StatusFilterButton(QToolButton):
    """Button with drop-down menu for status filter"""
    statusChanged = pyqtSignal(str)

    def __init__(self, statustext, types=None, parent=None, **kwargs):
        self._TYPES = 'MARSC'
        if types is not None:
            self._TYPES = types
        #if 'text' not in kwargs:
        #    kwargs['text'] = _('Status')
        super(StatusFilterButton, self).__init__(
            parent, popupMode=QToolButton.MenuButtonPopup,
            icon=qtlib.geticon('hg-status'),
            toolButtonStyle=Qt.ToolButtonTextBesideIcon, **kwargs)

        self.clicked.connect(self.showMenu)
        self._initactions(statustext)

    def _initactions(self, text):
        self._actions = {}
        menu = QMenu(self)
        for c in self._TYPES:
            st = statusTypes[c]
            a = menu.addAction('%s %s' % (c, st.trname))
            a.setCheckable(True)
            a.setChecked(c in text)
            a.toggled.connect(self._update)
            self._actions[c] = a
        self.setMenu(menu)

    @pyqtSlot()
    def _update(self):
        self.statusChanged.emit(self.status())

    def status(self):
        """Return the text for status filter"""
        return ''.join(c for c in self._TYPES
                       if self._actions[c].isChecked())

    @pyqtSlot(str)
    def setStatus(self, text):
        """Set the status text"""
        assert util.all(c in self._TYPES for c in text)
        for c in self._TYPES:
            self._actions[c].setChecked(c in text)

class StatusDialog(QDialog):
    'Standalone status browser'
    def __init__(self, repo, pats, opts, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowIcon(qtlib.geticon('hg-status'))
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        toplayout = QVBoxLayout()
        toplayout.setContentsMargins(10, 10, 10, 0);
        self.stwidget = StatusWidget(repo, pats, opts, self, checkable=False)
        toplayout.addWidget(self.stwidget, 1)
        layout.addLayout(toplayout)

        self.statusbar = cmdui.ThgStatusBar(self)
        layout.addWidget(self.statusbar)
        self.stwidget.showMessage.connect(self.statusbar.showMessage)
        self.stwidget.progress.connect(self.statusbar.progress)
        self.stwidget.titleTextChanged.connect(self.setWindowTitle)
        self.stwidget.linkActivated.connect(self.linkActivated)

        self.setWindowTitle(self.stwidget.getTitle())
        self.setWindowFlags(Qt.Window)
        self.loadSettings()

        QShortcut(QKeySequence.Refresh, self, self.stwidget.refreshWctx)
        QTimer.singleShot(0, self.stwidget.refreshWctx)

    def linkActivated(self, link):
        link = hglib.fromunicode(link)
        if link.startswith('subrepo:'):
            from tortoisehg.hgqt.run import qtrun
            from tortoisehg.hgqt import commit
            qtrun(commit.run, self.stwidget.repo.ui, root=link[8:])
        if link.startswith('shelve:'):
            from tortoisehg.hgqt import shelve
            dlg = shelve.ShelveDialog(self.stwidget.repo, self)
            dlg.finished.connect(dlg.deleteLater)
            dlg.exec_()
            self.refresh()

    def loadSettings(self):
        s = QSettings()
        self.stwidget.loadSettings(s, 'status')
        self.restoreGeometry(s.value('status/geom').toByteArray())

    def saveSettings(self):
        s = QSettings()
        self.stwidget.saveSettings(s, 'status')
        s.setValue('status/geom', self.saveGeometry())

    def accept(self):
        if not self.stwidget.canExit():
            return
        self.saveSettings()
        QDialog.accept(self)

    def reject(self):
        if not self.stwidget.canExit():
            return
        self.saveSettings()
        QDialog.reject(self)

def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    from tortoisehg.hgqt import thgrepo
    repo = thgrepo.repository(ui, path=paths.find_root())
    pats = hglib.canonpaths(pats)
    os.chdir(repo.root)
    return StatusDialog(repo, pats, opts)

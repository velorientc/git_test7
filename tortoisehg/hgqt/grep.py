# grep.py - Working copy and history search
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import re

from mercurial import ui, hg, error, commands, match, util

from tortoisehg.hgqt import htmlui, visdiff, qtlib, htmllistview, thgrepo
from tortoisehg.util import paths, hglib
from tortoisehg.hgqt.i18n import _

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# This widget can be embedded in any application that would like to
# provide search features

class SearchWidget(QWidget):
    '''Working copy and repository search widget
       SIGNALS:
       loadBegin()                  - for progress bar
       loadComplete()               - for progress bar
       showMessage(unicode)         - for status bar
    '''
    loadBegin = pyqtSignal()
    loadComplete = pyqtSignal()
    showMessage = pyqtSignal(unicode)

    def __init__(self, upats, repo=None, parent=None, **opts):
        QWidget.__init__(self, parent)

        self.thread = None

        mainvbox = QVBoxLayout()
        self.setLayout(mainvbox)

        hbox = QHBoxLayout()
        hbox.setMargin(0)
        lbl = QLabel(_('Regexp:'))
        le = QLineEdit()
        lbl.setBuddy(le)
        lbl.setToolTip(_('Regular expression search pattern'))
        bt = QPushButton(_('Search'))
        bt.setDefault(True)
        chk = QCheckBox(_('Ignore case'))
        hbox.addWidget(lbl)
        hbox.addWidget(le, 1)
        hbox.addWidget(chk)
        hbox.addWidget(bt)

        incle = QLineEdit()
        excle = QLineEdit()
        working = QRadioButton(_('Working Copy'))
        revision = QRadioButton(_('Revision'))
        history = QRadioButton(_('All History'))
        singlematch = QCheckBox(_('Report only the first match per file'))
        revle = QLineEdit()
        grid = QGridLayout()
        grid.addWidget(working, 0, 0)
        grid.addWidget(history, 1, 0)
        grid.addWidget(revision, 2, 0)
        grid.addWidget(revle, 2, 1)
        grid.addWidget(singlematch, 0, 3)
        ilabel = QLabel(_('Includes:'))
        ilabel.setToolTip(_('Comma separated list of inclusion patterns.'
                ' By default, the entire repository is searched.'))
        ilabel.setBuddy(incle)
        elabel = QLabel(_('Excludes:'))
        elabel.setToolTip(_('Comma separated list of exclusion patterns.'
                ' Exclusion patterns are applied after inclusion patterns.'))
        elabel.setBuddy(excle)
        grid.addWidget(ilabel, 1, 2)
        grid.addWidget(incle, 1, 3)
        grid.addWidget(elabel, 2, 2)
        grid.addWidget(excle, 2, 3)
        grid.setColumnStretch(3, 1)
        grid.setColumnStretch(1, 0)
        frame = QFrame()
        frame.setFrameStyle(QFrame.StyledPanel)
        def revisiontoggled(checked):
            revle.setEnabled(checked)
            if checked:
                revle.selectAll()
                QTimer.singleShot(0, lambda:revle.setFocus())
        revision.toggled.connect(revisiontoggled)
        history.toggled.connect(singlematch.setDisabled)
        revle.setEnabled(False)
        revle.returnPressed.connect(self.searchActivated)
        excle.returnPressed.connect(self.searchActivated)
        incle.returnPressed.connect(self.searchActivated)
        bt.clicked.connect(self.searchActivated)
        working.setChecked(True)

        mainvbox.addLayout(hbox)
        frame.setLayout(grid)
        mainvbox.addWidget(frame)

        tv = MatchTree(repo, self)
        tm = MatchModel(self)
        tv.setModel(tm)
        tv.setColumnHidden(COL_REVISION, True)
        tv.setColumnHidden(COL_USER, True)
        mainvbox.addWidget(tv)
        le.returnPressed.connect(self.searchActivated)

        self.repo = repo
        self.tv, self.regexple, self.chk = tv, le, chk
        self.incle, self.excle, self.revle = incle, excle, revle
        self.wctxradio, self.ctxradio, self.aradio = working, revision, history
        self.singlematch, self.eframe = singlematch, frame
        self.regexple.setFocus()

        if 'rev' in opts or 'all' in opts:
            self.setSearch(upats[0], **opts)
        elif len(upats) >= 1:
            le.setText(upats[0])
        if len(upats) > 1:
            incle.setText(','.join(upats[1:]))
        chk.setChecked(opts.get('ignorecase', False))

        if parent:
            mainvbox.setContentsMargins(0, 0, 0, 0)
            self.closeonesc = False
        else:
            self.setWindowTitle(_('TortoiseHg Search'))
            self.resize(800, 550)
            self.closeonesc = True
            self.stbar = QStatusBar()
            mainvbox.addWidget(self.stbar)
            self.showMessage.connect(self.stbar.showMessage)

    def setRevision(self, rev):
        if isinstance(rev, basestring):  # unapplied patch
            return
        elif rev is None:
            self.wctxradio.setChecked(True)
        else:
            self.ctxradio.setChecked(True)
            self.revle.setText(str(rev))

    def setSearch(self, upattern, **opts):
        self.regexple.setText(upattern)
        if opts.get('all'):
            self.aradio.setChecked(True)
        elif opts.get('rev'):
            self.ctxradio.setChecked(True)
            self.revle.setText(opts['rev'])

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.thread and self.thread.isRunning():
                self.thread.terminate()
                # This can lockup, so stop waiting after 2sec
                self.thread.wait( 2000 )
                self.finished()
                self.thread = None
            elif self.closeonesc:
                self.close()
        else:
            return super(SearchWidget, self).keyPressEvent(event)

    def searchActivated(self):
        'User pressed [Return] in QLineEdit'
        if self.thread and self.thread.isRunning():
            return

        model = self.tv.model()
        model.reset()
        pattern = hglib.fromunicode(self.regexple.text())
        if not pattern:
            return
        try:
            icase = self.chk.isChecked()
            regexp = re.compile(pattern, icase and re.I or 0)
        except Exception, inst:
            msg = _('grep: invalid match pattern: %s\n') % \
                    hglib.tounicode(str(inst))
            self.showMessage.emit(msg)
            return

        self.tv.setSortingEnabled(False)
        self.tv.pattern = pattern
        self.regexple.selectAll()
        inc = hglib.fromunicode(self.incle.text())
        if inc: inc = inc.split(', ')
        exc = hglib.fromunicode(self.excle.text())
        if exc: exc = exc.split(', ')
        rev = hglib.fromunicode(self.revle.text()).strip()
        if self.wctxradio.isChecked():
            self.tv.setColumnHidden(COL_REVISION, True)
            self.tv.setColumnHidden(COL_USER, True)
            ctx = self.repo[None]
            self.thread = CtxSearchThread(self.repo, regexp, ctx, inc, exc,
                                          once=self.singlematch.isChecked())
        elif self.ctxradio.isChecked():
            self.tv.setColumnHidden(COL_REVISION, True)
            self.tv.setColumnHidden(COL_USER, True)
            try:
                ctx = self.repo[rev or '.']
            except error.RepoError, e:
                msg = _('grep: %s\n') % hglib.tounicode(str(e))
                self.showMessage.emit(msg)
                return
            self.thread = CtxSearchThread(self.repo, regexp, ctx, inc, exc,
                                          once=self.singlematch.isChecked())
        else:
            assert self.aradio.isChecked()
            self.tv.setColumnHidden(COL_REVISION, False)
            self.tv.setColumnHidden(COL_USER, False)
            self.thread = HistorySearchThread(self.repo, pattern, icase,
                                              inc, exc)

        self.regexple.setEnabled(False)
        self.thread.finished.connect(self.finished)
        self.thread.showMessage.connect(self.showMessage)
        self.thread.matchedRow.connect(
                     lambda wrapper: model.appendRow(*wrapper.data))
        self.loadBegin.emit()
        self.thread.start()

    def reload(self):
        # TODO
        pass

    def finished(self):
        count = self.tv.model().rowCount(None)
        if not count:
            self.showMessage.emit(_('No matches found'))
        else:
            self.showMessage.emit(_('%d matches found') % count)
            for col in xrange(COL_TEXT):
                self.tv.resizeColumnToContents(col)
            self.tv.setSortingEnabled(True)
        self.regexple.setEnabled(True)
        self.regexple.setFocus()
        self.loadComplete.emit()

class DataWrapper(object):
    def __init__(self, data):
        self.data = data

class HistorySearchThread(QThread):
    '''Background thread for searching repository history'''
    matchedRow = pyqtSignal(DataWrapper)
    showMessage = pyqtSignal(unicode)
    finished = pyqtSignal()

    def __init__(self, repo, pattern, icase, inc, exc):
        super(HistorySearchThread, self).__init__()
        self.repo = repo
        self.pattern = pattern
        self.icase = icase
        self.inc = inc
        self.exc = exc

    def run(self):
        # special purpose - not for general use
        class incrui(ui.ui):
            def __init__(self, src=None):
                super(incrui, self).__init__(src)
                self.setconfig('ui', 'interactive', 'off')
                self.setconfig('progress', 'disable', 'True')
                os.environ['TERM'] = 'dumb'
                self.fullmsg = ''

            def plain(self):
                return True

            def write(self, msg, *args, **opts):
                if opts.get('label'):
                    self.fullmsg += self.label(msg, opts['label'])
                else:
                    self.fullmsg += msg
                if self.fullmsg.endswith('\0'):
                    try:
                        fname, line, rev, addremove, user, text = \
                                self.fullmsg.split('\0', 5)
                        text = '<b>%s</b> <span>%s</span>' % (
                                addremove, text[:-1])
                        row = [fname, rev, line, user, text]
                        w = DataWrapper(row)
                        self.obj.matchedRow.emit(w)
                    except ValueError:
                        pass
                    self.fullmsg = ''

            def write_err(self, msg, *args, **opts):
                msg = htlib.tounicode(msg)
                self.obj.showMessage.emit(msg)

            def label(self, msg, label):
                msg = hglib.tounicode(msg)
                msg = Qt.escape(msg)
                msg = msg.replace('\n', '<br />')
                style = qtlib.geteffect(label)
                return '<span style="%s">%s</span>' % (style, msg)

        # hg grep [-i] -afn regexp
        opts = {'all':True, 'user':True, 'follow':True, 'rev':[],
                'line_number':True, 'print0':True,
                'ignore_case':self.icase, 'include':self.inc,
                'exclude':self.exc,
                }
        u = incrui()
        u.obj = self
        commands.grep(u, self.repo, self.pattern, **opts)
        self.finished.emit()

class CtxSearchThread(QThread):
    '''Background thread for searching a changectx'''
    matchedRow = pyqtSignal(object)
    showMessage = pyqtSignal(unicode)
    finished = pyqtSignal()

    def __init__(self, repo, regexp, ctx, inc, exc, once):
        super(CtxSearchThread, self).__init__()
        self.repo = repo
        self.regexp = regexp
        self.ctx = ctx
        self.inc = inc
        self.exc = exc
        self.once = once

    def run(self):
        hu = htmlui.htmlui()
        rev = self.ctx.rev()
        # generate match function relative to repo root
        matchfn = match.match(self.repo.root, '', [], self.inc, self.exc)
        def badfn(f, msg):
            e = hglib.tounicode("%s: %s" % (matchfn.rel(f), msg))
            self.showMessage.emit(e)
        matchfn.bad = badfn

        # searching len(ctx.manifest()) files
        for wfile in self.ctx:                # walk manifest
            if not matchfn(wfile):
                continue
            data = self.ctx[wfile].data()     # load file data
            if util.binary(data):
                continue
            for i, line in enumerate(data.splitlines()):
                pos = 0
                for m in self.regexp.finditer(line): # perform regexp
                    hu.write(line[pos:m.start()], label='ui.status')
                    hu.write(line[m.start():m.end()], label='grep.match')
                    pos = m.end()
                if pos:
                    hu.write(line[pos:], label='ui.status')
                    row = [wfile, i + 1, rev, None, hu.getdata()[0]]
                    w = DataWrapper(row)
                    self.matchedRow.emit(w)
                    if self.once:
                        break
        self.finished.emit()


COL_PATH     = 0
COL_LINE     = 1
COL_REVISION = 2  # Hidden if ctx
COL_USER     = 3  # Hidden if ctx
COL_TEXT     = 4

class MatchTree(QTableView):
    def __init__(self, repo, parent=None):
        QTableView.__init__(self, parent)
        self.repo = repo
        self.delegate = htmllistview.HTMLDelegate(self)
        self.setItemDelegateForColumn(COL_TEXT, self.delegate)
        self.setSelectionMode(QTableView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setShowGrid(False)
        vh = self.verticalHeader()
        vh.hide()
        vh.setDefaultSectionSize(20)

        self.horizontalHeader().setStretchLastSection(True)

        self.customContextMenuRequested.connect(self.menuRequest)
        self.pattern = None
        self.searchwidget = parent

    def dragObject(self):
        snapshots = {}
        for index in self.selectedRows():
            path, line, rev, user, text = self.model().getRow(index)
            if rev not in snapshots:
                snapshots[rev] = [path]
            else:
                snapshots[rev].append(path)
        urls = []
        for rev, paths in snapshots.iteritems():
            if rev is not None:
                base, _ = visdiff.snapshot(self.repo, paths, self.repo[rev])
            else:
                base = self.repo.root
            for p in paths:
                u = QUrl()
                u.setPath('file://' + os.path.join(base, path))
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
        return QTableView.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        d = event.pos() - self.pressPos
        if d.manhattanLength() < QApplication.startDragDistance():
            return QTableView.mouseMoveEvent(self, event)
        elapsed = self.pressTime.msecsTo(QTime.currentTime())
        if elapsed < QApplication.startDragTime():
            return QTableView.mouseMoveEvent(self, event)
        self.dragObject()
        return QTableView.mouseMoveEvent(self, event)

    def menuRequest(self, point):
        selrows = []
        wctxonly = True
        allhistory = False
        for index in self.selectedRows():
            path, line, rev, user, text = self.model().getRow(index)
            if rev is not None:
                wctxonly = False
            if user is not None:
                allhistory = True
            selrows.append((rev, path, line))
        if not selrows:
            return
        point = self.mapToGlobal(point)
        menus = [(_('View file'), self.view), (_('Annotate file'), self.ann)]
        if not wctxonly:
            menus.append((_('View Changeset'), self.ctx))
        if allhistory:
            # need to know files were modified at specified revision
            menus.append((_('Visual Diff'), self.vdiff))
        menu = QMenu(self)
        for name, func in menus:
            def add(name, func):
                action = menu.addAction(name)
                action.triggered.connect(lambda: func(selrows))
            add(name, func)
        menu.exec_(point)

    def ann(self, rows):
        from tortoisehg.hgqt import annotate
        repo, ui, pattern = self.repo, self.repo.ui, self.pattern
        seen = set()
        for rev, path, line in rows:
            # Only open one annotate instance per file
            if path in seen:
                continue
            else:
                seen.add(path)
            dlg = annotate.AnnotateDialog(path, rev=rev, line=line,
                                          pattern=pattern, parent=self,
                                          searchwidget=self.searchwidget,
                                          root=repo.root)
            dlg.show()

    def ctx(self, rows):
        raise NotImplementedError()

    def view(self, rows):
        from tortoisehg.hgqt import wctxactions
        repo, ui, pattern = self.repo, self.repo.ui, self.pattern
        seen = set()
        for rev, path, line in rows:
            # Only open one editor instance per file
            if path in seen:
                continue
            else:
                seen.add(path)
            if rev is None:
                files = [repo.wjoin(path)]
                wctxactions.edit(self, ui, repo, files, line, pattern)
            else:
                base, _ = visdiff.snapshot(repo, [path], repo[rev])
                files = [os.path.join(base, path)]
                wctxactions.edit(self, ui, repo, files, line, pattern)

    def vdiff(self, rows):
        repo, ui = self.repo, self.repo.ui
        while rows:
            defer = []
            crev = rows[0][0]
            files = set([rows[0][1]])
            for rev, path, line in rows[1:]:
                if rev == crev:
                    files.add(path)
                else:
                    defer.append([rev, path, line])
            if crev is not None:
                visdiff.visualdiff(ui, repo, list(files), {'change':crev})
            rows = defer

    def selectedRows(self):
        return self.selectionModel().selectedRows()



class MatchModel(QAbstractTableModel):
    def __init__(self, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.rows = []
        self.headers = (_('File'), _('Line'), _('Rev'), _('User'),
                        _('Match Text'))

    def rowCount(self, parent):
        return len(self.rows)

    def columnCount(self, parent):
        return len(self.headers)

    def data(self, index, role):
        if not index.isValid():
            return QVariant()
        if role == Qt.DisplayRole:
            return QVariant(self.rows[index.row()][index.column()])
        return QVariant()

    def headerData(self, col, orientation, role):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return QVariant()
        else:
            return QVariant(self.headers[col])

    def flags(self, index):
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled
        return flags

    def sort(self, col, order):
        self.layoutAboutToBeChanged.emit()
        self.rows.sort(lambda x, y: cmp(x[col], y[col]))
        if order == Qt.DescendingOrder:
            self.rows.reverse()
        self.layoutChanged.emit()

    ## Custom methods

    def appendRow(self, *args):
        l = len(self.rows)
        self.beginInsertRows(QModelIndex(), l, l)
        self.rows.append(args)
        self.endInsertRows()
        self.layoutChanged.emit()

    def reset(self):
        self.beginRemoveRows(QModelIndex(), 0, len(self.rows)-1)
        self.rows = []
        self.endRemoveRows()
        self.layoutChanged.emit()

    def getRow(self, index):
        assert index.isValid()
        return self.rows[index.row()]

def run(ui, *pats, **opts):
    repo = thgrepo.repository(ui, path=paths.find_root())
    upats = [hglib.tounicode(p) for p in pats]
    return SearchWidget(upats, repo, **opts)

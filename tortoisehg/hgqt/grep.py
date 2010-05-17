# grep.py - Working copy and history search
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import re

from mercurial import ui, hg, error, commands

from tortoisehg.hgqt import htmlui, visdiff, qtlib, htmllistview
from tortoisehg.util import paths, hglib
from tortoisehg.hgqt.i18n import _

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# This widget can be embedded in any application that would like to
# prove search features

# Technical Debt
#  draggable matches from history
#  tortoisehg.editor with line number
#  smart visual diffs
#  context menu for matches

class SearchWidget(QWidget):
    '''Working copy and repository search widget
       SIGNALS:
       loadBegin()                  - for progress bar
       loadComplete()               - for progress bar
       errorMessage(QString)        - for status bar
    '''
    def __init__(self, root=None, parent=None):
        QWidget.__init__(self, parent)

        self.thread = None
        root = paths.find_root(root)
        repo = hg.repository(ui.ui(), path=root)
        assert(repo)

        layout = QVBoxLayout()
        layout.setMargin(0)
        self.setLayout(layout)

        hbox = QHBoxLayout()
        hbox.setMargin(0)
        lbl = QLabel(_('Regexp:'))
        le = QLineEdit()
        lbl.setBuddy(le)
        cb = QComboBox()
        cb.addItems([_('Working Copy'),
                     _('Parent Revision'),
                     _('All History')])
        chk = QCheckBox(_('Ignore case'))

        hbox.addWidget(lbl)
        hbox.addWidget(le, 1)
        hbox.addWidget(cb)
        hbox.addWidget(chk)
        layout.addLayout(hbox)

        tv = MatchTree(repo, self)
        tv.setItemsExpandable(False)
        tv.setRootIsDecorated(False)
        tm = MatchModel()
        tv.setModel(tm)
        tv.setColumnHidden(COL_REVISION, True)
        tv.setColumnHidden(COL_USER, True)
        layout.addWidget(tv)
        le.returnPressed.connect(self.searchActivated)
        self.repo = repo
        self.tv, self.le, self.cb, self.chk = tv, le, cb, chk

        if not parent:
            self.setWindowTitle(_('TortoiseHg Search'))
            self.resize(800, 500)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.thread and self.thread.isRunning():
                self.thread.terminate()
                self.thread.wait()
                self.finished()
            else:
                self.close()
        else:
            return super(SearchWidget, self).keyPressEvent(event)

    def searchActivated(self):
        'User pressed [Return] in QLineEdit'
        if self.thread and self.thread.isRunning():
            return

        model = self.tv.model()
        model.reset()
        pattern = hglib.fromunicode(self.le.text())
        if not pattern:
            return
        try:
            icase = self.chk.isChecked()
            regexp = re.compile(pattern, icase and re.I or 0)
        except Exception, inst:
            msg = _('grep: invalid match pattern: %s\n') % inst
            self.emit(SIGNAL('errorMessage'), msg)
            return

        self.le.selectAll()
        mode = self.cb.currentIndex()
        if mode == 0:
            self.tv.setColumnHidden(COL_REVISION, True)
            self.tv.setColumnHidden(COL_USER, True)
            ctx = self.repo[None]
            self.thread = CtxSearchThread(self.repo, regexp, ctx)
        elif mode == 1:
            self.tv.setColumnHidden(COL_REVISION, True)
            self.tv.setColumnHidden(COL_USER, True)
            ctx = self.repo['.']
            self.thread = CtxSearchThread(self.repo, regexp, ctx)
        else:
            self.tv.setColumnHidden(COL_REVISION, False)
            self.tv.setColumnHidden(COL_USER, False)
            self.thread = HistorySearchThread(self.repo, pattern, icase)

        self.le.setEnabled(False)
        self.connect(self.thread, SIGNAL('finished'), self.finished)
        self.connect(self.thread, SIGNAL('matchedRow'),
                     lambda row: model.appendRow(*row))
        self.emit(SIGNAL('loadBegin'))
        self.thread.start()

    def finished(self):
        for col in xrange(COL_TEXT):
            self.tv.resizeColumnToContents(col)
        self.le.setEnabled(True)
        self.emit(SIGNAL('loadComplete'))


class HistorySearchThread(QThread):
    '''Background thread for searching repository history'''
    def __init__(self, repo, pattern, icase, parent=None):
        super(HistorySearchThread, self).__init__()
        self.repo = repo
        self.pattern = pattern
        self.icase = icase

    def run(self):
        # special purpose - not for general use
        class incrui(ui.ui):
            def __init__(self, src=None):
                super(incrui, self).__init__(src)
                self.setconfig('ui', 'interactive', 'off')
                self.setconfig('progress', 'disable', 'True')
                os.environ['TERM'] = 'dumb'
                qtlib.configstyles(self)
                self.fullmsg = ''

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
                        row = [fname, line, rev, user, text]
                        self.obj.emit(SIGNAL('matchedRow'), row)
                    except ValueError:
                        pass
                    self.fullmsg = ''

            def label(self, msg, label):
                msg = hglib.tounicode(msg)
                msg = Qt.escape(msg)
                msg = msg.replace('\n', '<br />')
                style = qtlib.geteffect(label)
                return '<span style="%s">%s</span>' % (style, msg)

        # hg grep [-i] -afn regexp
        opts = {'all':True, 'user':True, 'follow':True, 'rev':[],
                'line_number':True, 'print0':True,
                'ignore_case':self.icase,
                }
        u = incrui()
        u.obj = self
        commands.grep(u, self.repo, self.pattern, **opts)
        self.emit(SIGNAL('finished'))

class CtxSearchThread(QThread):
    '''Background thread for searching a changectx'''
    def __init__(self, repo, regexp, ctx, parent=None):
        super(CtxSearchThread, self).__init__()
        self.repo = repo
        self.regexp = regexp
        self.ctx = ctx

    def run(self):
        # this will eventually be: hg grep -c 
        hu = htmlui.htmlui()
        # searching len(ctx.manifest()) files
        for wfile in self.ctx:                # walk manifest
            data = self.ctx[wfile].data()     # load file data
            if '\0' in data:
                continue
            for i, line in enumerate(data.splitlines()):
                pos = 0
                for m in self.regexp.finditer(line): # perform regexp
                    hu.write(line[pos:m.start()])
                    hu.write(line[m.start():m.end()], label='grep.match')
                    pos = m.end()
                if pos:
                    hu.write(line[pos:])
                    row = [wfile, i, None, None, hu.getdata()[0]]
                    self.emit(SIGNAL('matchedRow'), row)
        self.emit(SIGNAL('finished'))


COL_PATH     = 0
COL_LINE     = 1
COL_REVISION = 2  # Hidden if ctx
COL_USER     = 3  # Hidden if ctx
COL_TEXT     = 4

class MatchTree(QTreeView):
    def __init__(self, repo, parent=None):
        QTreeView.__init__(self, parent)
        self.repo = repo
        self.delegate = htmllistview.HTMLDelegate(self)
        self.setItemDelegateForColumn(COL_TEXT, self.delegate)
        self.setSelectionMode(QTreeView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.connect(self, SIGNAL('customContextMenuRequested(const QPoint &)'),
                     self.customContextMenuRequested)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_D and event.modifiers() == Qt.ControlModifier:
            selfiles = []
            for index in self.selectedRows():
                # TODO: record rev, prune dups
                selfiles.append(self.model().getRow(index)[COL_PATH])
            visdiff.visualdiff(self.repo.ui, self.repo, selfiles, {})
        else:
            return super(MatchTree, self).keyPressEvent(event)

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
            path, line, rev, user, text = self.model().getRow(index)
            selrows.append((rev, path, line))
        point = self.mapToGlobal(point)
        #action = wctxactions.wctxactions(self, point, self.repo, selrows)
        #if action:
        #    self.emit(SIGNAL('menuAction()'))

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
        self.emit(SIGNAL("layoutAboutToBeChanged()"))
        self.rows.sort(lambda x, y: cmp(x[col], y[col]))
        if order == Qt.DescendingOrder:
            self.rows.reverse()
        self.emit(SIGNAL("layoutChanged()"))

    ## Custom methods

    def appendRow(self, *args):
        self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows))
        self.rows.append(args)
        self.endInsertRows()
        self.emit(SIGNAL("dataChanged()"))

    def reset(self):
        self.beginRemoveRows(QModelIndex(), 0, len(self.rows)-1)
        self.rows = []
        self.endRemoveRows()

def run(ui, *pats, **opts):
    return SearchWidget()

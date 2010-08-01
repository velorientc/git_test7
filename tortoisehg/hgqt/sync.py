# sync.py - TortoiseHg's sync widget
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os
import re
import urlparse

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import url

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib

_schemes = ['local', 'ssh', 'http', 'https']

class SyncWidget(QWidget):

    def __init__(self, root, parent=None, **opts):
        QWidget.__init__(self, parent)

        layout = QVBoxLayout()
        layout.setSpacing(4)
        self.setLayout(layout)

        self.root = root
        self.thread = None
        self.curuser = None
        self.curpw = None
        self.updateInProgress = False
        self.tv = PathsTree(root, self)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        self.savebutton = QPushButton(_('Save'))
        hbox.addWidget(self.savebutton)
        hbox.addWidget(QLabel(_('URL:')))
        self.urlentry = QLineEdit()
        self.urlentry.setReadOnly(True)
        hbox.addWidget(self.urlentry)
        self.inbutton = QPushButton(_('Incoming'))
        hbox.addWidget(self.inbutton)
        self.pullbutton = QPushButton(_('Pull'))
        hbox.addWidget(self.pullbutton)
        self.outbutton = QPushButton(_('Outgoing'))
        hbox.addWidget(self.outbutton)
        self.pushbutton = QPushButton(_('Push'))
        hbox.addWidget(self.pushbutton)
        self.emailbutton = QPushButton(_('Email'))
        hbox.addWidget(self.emailbutton)
        layout.addLayout(hbox)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        self.schemecombo = QComboBox()
        for s in _schemes:
            self.schemecombo.addItem(s)
        self.schemecombo.currentIndexChanged.connect(self.refreshUrl)
        hbox.addWidget(self.schemecombo)
        hbox.addWidget(QLabel(_('Hostname:')))
        self.hostentry = QLineEdit()
        self.hostentry.textChanged.connect(self.refreshUrl)
        hbox.addWidget(self.hostentry)
        hbox.addWidget(QLabel(_('Port:')))
        self.portentry = QLineEdit()
        fontm = QFontMetrics(self.font())
        self.portentry.setFixedWidth(8 * fontm.width('9'))
        self.portentry.textChanged.connect(self.refreshUrl)
        hbox.addWidget(self.portentry)
        hbox.addWidget(QLabel(_('Path:')))
        self.pathentry = QLineEdit()
        self.pathentry.textChanged.connect(self.refreshUrl)
        hbox.addWidget(self.pathentry, 1)
        self.siteauth = QPushButton(_('Site Authentication'))
        hbox.addWidget(self.siteauth)
        layout.addLayout(hbox)

        self.tv.clicked.connect(self.pathSelected)

        pathsframe = QFrame()
        pathsframe.setFrameStyle(QFrame.Panel|QFrame.Raised)
        pathsbox = QVBoxLayout()
        pathsframe.setLayout(pathsbox)
        lbl = QLabel(_('<b>Configured Paths</b>'))
        pathsbox.addWidget(lbl)
        pathsbox.addWidget(self.tv)
        layout.addWidget(pathsframe)

        if parent:
            self.closeonesc = False
        else:
            self.setWindowTitle(_('TortoiseHg Search'))
            self.resize(800, 550)
            self.closeonesc = True

        self.refresh()
        if 'default' in self.paths:
            self.setUrl(self.paths['default'])

    def refresh(self):
        fn = os.path.join(self.root, '.hg', 'hgrc')
        try:
            import iniparse
            # Monkypatch this regex to prevent iniparse from considering
            # 'rem' as a comment
            iniparse.ini.CommentLine.regex = \
                       re.compile(r'^(?P<csep>[%;#])(?P<comment>.*)$')
            cfg = iniparse.INIConfig(file(fn), optionxformvalue=None)
            self.readonly = False
        except ImportError:
            from mercurial import config
            cfg = config.config()
            cfg.read(fn)
            self.readonly = True
        except Exception, e:
            qtlib.WarningMsgBox(_('Unable to parse a config file'),
                    _('%s\nReverting to read-only mode.') % str(e),
                    parent=self)
            self.readonly = True
            cfg = {}
        self.paths = {}
        if 'paths' not in cfg:
            return
        for alias in cfg['paths']:
            self.paths[ alias ] = cfg['paths'][ alias ]
        tm = PathsModel(self.paths, self)
        self.tv.setModel(tm)


    def refreshUrl(self):
        'User has changed schema/host/port/path'
        if self.updateInProgress:
            return
        scheme = _schemes[self.schemecombo.currentIndex()]
        if scheme == 'local':
            self.hostentry.setEnabled(False)
            self.portentry.setEnabled(False)
            self.urlentry.setText(self.pathentry.text())
        else:
            self.hostentry.setEnabled(True)
            self.portentry.setEnabled(True)
            path = self.pathentry.text()
            host = self.hostentry.text()
            port = self.portentry.text()
            parts = [scheme, '://']
            if self.curuser:
                parts.append(self.curuser)
                if self.curpw:
                    parts.append(':***')
                parts.append('@')
            parts.append(unicode(host))
            if port:
                parts.extend([':', unicode(port)])
            parts.extend(['/', unicode(path)])
            self.urlentry.setText(''.join(parts))

    def pathSelected(self, index):
        pathindex = index.sibling(index.row(), 1)
        path = pathindex.data(Qt.DisplayRole).toString()
        self.setUrl(unicode(path))
        aliasindex = index.sibling(index.row(), 0)
        alias = aliasindex.data(Qt.DisplayRole).toString()
        self.curalias = alias

    def setUrl(self, newurl):
        'User has selected a new URL'
        user, host, port, folder, passwd, scheme = self.urlparse(newurl)
        self.updateInProgress = True
        self.urlentry.setText(newurl)
        for i, val in enumerate(_schemes):
            if scheme == val:
                self.schemecombo.setCurrentIndex(i)
                break
        self.hostentry.setText(host or '')
        self.portentry.setText(port or '')
        self.pathentry.setText(folder or '')
        self.curuser = user
        self.curpw = passwd
        self.hostentry.setEnabled(scheme != 'local')
        self.portentry.setEnabled(scheme != 'local')
        self.updateInProgress = False

    def urlparse(self, path):
        m = re.match(r'^ssh://(([^@]+)@)?([^:/]+)(:(\d+))?(/(.*))?$', path)
        if m:
            user = m.group(2)
            host = m.group(3)
            port = m.group(5)
            folder = m.group(7) or '.'
            passwd = ''
            scheme = 'ssh'
        elif path.startswith('http://') or path.startswith('https://'):
            snpaqf = urlparse.urlparse(path)
            scheme, netloc, folder, params, query, fragment = snpaqf
            host, port, user, passwd = url.netlocsplit(netloc)
            if folder.startswith('/'): folder = folder[1:]
        else:
            user, host, port, passwd = [''] * 4
            folder = path
            scheme = 'local'
        return user, host, port, folder, passwd, scheme

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
            return super(SyncWidget, self).keyPressEvent(event)

class PathsTree(QTreeView):
    def __init__(self, root, parent=None):
        QTreeView.__init__(self, parent)
        self.setSelectionMode(QTreeView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.connect(self, SIGNAL('customContextMenuRequested(const QPoint &)'),
                     self.customContextMenuRequested)

    def keyPressEvent(self, event):
        return super(PathsTree, self).keyPressEvent(event)

    def dragObject(self):
        urls = []
        for index in self.selectedRows():
            url = self.model().data(index)[1]
            u = QUrl()
            u.setPath(url)
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
        return super(PathsTree, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        d = event.pos() - self.pressPos
        if d.manhattanLength() < QApplication.startDragDistance():
            return QTreeView.mouseMoveEvent(self, event)
        elapsed = self.pressTime.msecsTo(QTime.currentTime())
        if elapsed < QApplication.startDragTime():
            return super(PathsTree, self).mouseMoveEvent(event)
        self.dragObject()
        return super(PathsTree, self).mouseMoveEvent(event)

    def customContextMenuRequested(self, point):
        point = self.mapToGlobal(point)
        pass

    def selectedRows(self):
        return self.selectionModel().selectedRows()

class PathsModel(QAbstractTableModel):
    def __init__(self, pathdict, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.headers = (_('Alias'), _('URL'))
        self.rows = []
        for alias, url in pathdict.iteritems():
            self.rows.append([alias, url])

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


def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    return SyncWidget(paths.find_root(), **opts)

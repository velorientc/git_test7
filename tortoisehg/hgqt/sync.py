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
        self.authbutton = QPushButton(_('Site Authentication'))
        hbox.addWidget(self.authbutton)
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
            self.setWindowTitle(_('TortoiseHg Sync'))
            self.resize(800, 550)
            self.closeonesc = True

        self.savebutton.clicked.connect(self.saveclicked)
        self.authbutton.clicked.connect(self.authclicked)
        self.inbutton.clicked.connect(self.inclicked)
        self.pullbutton.clicked.connect(self.pullclicked)
        self.outbutton.clicked.connect(self.outclicked)
        self.pushbutton.clicked.connect(self.pushclicked)

        self.refresh()
        if 'default' in self.paths:
            self.setUrl(self.paths['default'])
            self.curalias = 'default'

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
            self.authbutton.setEnabled(False)
            self.urlentry.setText(self.pathentry.text())
        else:
            self.hostentry.setEnabled(True)
            self.portentry.setEnabled(True)
            self.authbutton.setEnabled(True)
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
        self.curalias = unicode(alias)

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
        self.authbutton.setEnabled(scheme != 'local')
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
        if event.matches(QKeySequence.Refresh):
            self.refresh()
        elif event.key() == Qt.Key_Escape:
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

    def saveclicked(self):
        if self.curalias:
            alias = self.curalias
        elif 'default' not in self.paths:
            alias = 'default'
        else:
            alias = 'new'
        url = unicode(self.urlentry.text())
        dialog = SaveDialog(self.root, alias, url, self)
        if dialog.exec_() == QDialog.Accepted:
            self.curalias = unicode(dialog.aliasentry.text())

    def authclicked(self):
        host = unicode(self.hostentry.text())
        user = self.curuser or ''
        pw = self.curpw or ''
        dialog = AuthDialog(self.root, host, user, pw, self)
        if dialog.exec_() == QDialog.Accepted:
            self.curuser, self.curpw = '', ''

    def inclicked(self):
        pass
    def pullclicked(self):
        pass
    def outclicked(self):
        pass
    def pushclicked(self):
        pass

class SaveDialog(QDialog):
    def __init__(self, root, alias, url, parent):
        super(SaveDialog, self).__init__(parent)
        self.root = root
        layout = QVBoxLayout()
        self.setLayout(layout)
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel(_('Alias')))
        self.aliasentry = QLineEdit(alias)
        hbox.addWidget(self.aliasentry, 1)
        layout.addLayout(hbox)
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel(_('URL')))
        self.urlentry = QLineEdit(url)
        hbox.addWidget(self.urlentry, 1)
        layout.addLayout(hbox)
        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Save|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(BB.Save).setAutoDefault(True)
        self.bb = bb
        layout.addWidget(bb)
        self.aliasentry.selectAll()
        self.setWindowTitle(_('Save URL: ') + url)
        QTimer.singleShot(0, lambda:self.aliasentry.setFocus())

    def accept(self):
        super(SaveDialog, self).accept()

    def reject(self):
        super(SaveDialog, self).reject()

class AuthDialog(QDialog):
    def __init__(self, root, host, user, pw, parent):
        super(AuthDialog, self).__init__(parent)
        self.root = root
        layout = QVBoxLayout()
        self.setLayout(layout)
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel(_('Username')))
        self.userentry = QLineEdit(user)
        hbox.addWidget(self.userentry, 1)
        layout.addLayout(hbox)
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel(_('Password')))
        self.pwentry = QLineEdit(pw)
        self.pwentry.setEchoMode(QLineEdit.Password)
        hbox.addWidget(self.pwentry, 1)
        layout.addLayout(hbox)
        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Help|BB.Cancel)
        bb.rejected.connect(self.reject)
        bb.helpRequested.connect(self.keyringHelp)
        bb.button(BB.Help).setText(_('Keyring Help'))
        sr = QPushButton(_('Save In Repo'))
        sr.clicked.connect(self.saveInRepo)
        bb.addButton(sr, BB.ActionRole)
        sg = QPushButton(_('Save Global'))
        sg.clicked.connect(self.saveGlobal)
        sg.setAutoDefault(True)
        bb.addButton(sg, BB.ActionRole)

        self.bb = bb
        layout.addWidget(bb)
        self.setWindowTitle(_('Site Authentication: ') + host)
        self.userentry.selectAll()
        QTimer.singleShot(0, lambda:self.userentry.setFocus())

    def keyringHelp(self):
        pass

    def saveInRepo(self):
        super(AuthDialog, self).accept()

    def saveGlobal(self):
        super(AuthDialog, self).accept()

    def reject(self):
        super(AuthDialog, self).reject()


class PathsTree(QTreeView):
    def __init__(self, root, parent=None):
        QTreeView.__init__(self, parent)
        self.setSelectionMode(QTreeView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menuRequest)

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

    def menuRequest(self, point):
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

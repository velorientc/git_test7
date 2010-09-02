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

from mercurial import hg, ui, url, util, error

from tortoisehg.util import hglib, thgrepo, wconfig
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, cmdui

# TODO
# Write keyring help, connect to help button

_schemes = ['local', 'ssh', 'http', 'https']

class SyncWidget(QWidget):
    invalidate = pyqtSignal()
    outgoingNodes = pyqtSignal(object)

    def __init__(self, root, parent=None, log=None, **opts):
        QWidget.__init__(self, parent)

        layout = QVBoxLayout()
        layout.setSpacing(4)
        self.setLayout(layout)
        self.setAcceptDrops(True)

        self.log = log
        if not log:
            self.setWindowTitle(_('TortoiseHg Sync'))
            self.resize(850, 550)

        self.root = root
        self.repo = thgrepo.repository(ui.ui(), root)
        self.finishfunc = None
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
        self.authbutton = QPushButton(_('Authentication'))
        hbox.addWidget(self.authbutton)
        self.postpullbutton = QPushButton()
        hbox.addWidget(self.postpullbutton)
        layout.addLayout(hbox)

        self.tv.clicked.connect(self.pathSelected)

        pathsframe = QFrame()
        pathsframe.setFrameStyle(QFrame.StyledPanel|QFrame.Raised)
        pathsbox = QVBoxLayout()
        pathsframe.setLayout(pathsbox)
        lbl = QLabel(_('<b>Configured Paths</b>'))
        pathsbox.addWidget(lbl)
        pathsbox.addWidget(self.tv)
        layout.addWidget(pathsframe, 1)

        self.savebutton.clicked.connect(self.saveclicked)
        self.authbutton.clicked.connect(self.authclicked)
        self.inbutton.clicked.connect(self.inclicked)
        self.pullbutton.clicked.connect(self.pullclicked)
        self.outbutton.clicked.connect(self.outclicked)
        self.pushbutton.clicked.connect(self.pushclicked)
        self.emailbutton.clicked.connect(self.emailclicked)
        self.postpullbutton.clicked.connect(self.postpullclicked)

        self.opbuttons = (self.inbutton, self.pullbutton,
                          self.outbutton, self.pushbutton,
                          self.emailbutton)

        cmd = cmdui.Widget(log)
        cmd.commandStarted.connect(self.commandStarted)
        cmd.commandFinished.connect(self.commandFinished)
        cmd.commandCanceling.connect(self.commandCanceled)
        layout.addWidget(cmd)
        cmd.setHidden(True)
        self.cmd = cmd

        self.reload()
        if 'default' in self.paths:
            self.setUrl(self.paths['default'])
            self.curalias = 'default'

    def commandStarted(self):
        for b in self.opbuttons:
            b.setEnabled(False)
        self.cmd.show_output(True)
        self.cmd.setHidden(False)

    def commandFinished(self, wrapper):
        for b in self.opbuttons:
            b.setEnabled(True)
        if wrapper.data == 0 and self.finishfunc:
            output = self.cmd.get_rawoutput()
            self.finishfunc( output )

    def commandCanceled(self):
        for b in self.opbuttons:
            b.setEnabled(True)

    def reload(self):
        fn = os.path.join(self.root, '.hg', 'hgrc')
        fn, cfg = loadIniFile([fn], self)
        self.paths = {}
        if 'paths' not in cfg:
            return
        for alias in cfg['paths']:
            self.paths[ alias ] = cfg['paths'][ alias ]
        tm = PathsModel(self.paths, self)
        self.tv.setModel(tm)
        self.cachedpp = self.repo.postpull
        name = _('Post Pull: ') + self.repo.postpull.title()
        self.postpullbutton.setText(name)

    def refreshUrl(self):
        'User has changed schema/host/port/path'
        if self.updateInProgress:
            return
        self.urlentry.setText(self.currentUrl(True))
        notlocal = (self.schemecombo.currentIndex() != 0)
        self.hostentry.setEnabled(notlocal)
        self.portentry.setEnabled(notlocal)
        self.authbutton.setEnabled(notlocal)

    def currentUrl(self, hidepw):
        scheme = _schemes[self.schemecombo.currentIndex()]
        if scheme == 'local':
            return hglib.fromunicode(self.pathentry.text())
        else:
            path = self.pathentry.text()
            host = self.hostentry.text()
            port = self.portentry.text()
            parts = [scheme, '://']
            if self.curuser:
                parts.append(self.curuser)
                if self.curpw:
                    parts.append(hidepw and ':***' or self.curpw)
                parts.append('@')
            parts.append(hglib.fromunicode(host))
            if port:
                parts.extend([':', hglib.fromunicode(port)])
            parts.extend(['/', hglib.fromunicode(path)])
            return ''.join(parts)

    def pathSelected(self, index):
        path = index.model().realUrl(index)
        self.setUrl(hglib.fromunicode(path))
        aliasindex = index.sibling(index.row(), 0)
        alias = aliasindex.data(Qt.DisplayRole).toString()
        self.curalias = hglib.fromunicode(alias)

    def setUrl(self, newurl):
        'User has selected a new URL'
        try:
            user, host, port, folder, passwd, scheme = self.urlparse(newurl)
        except TypeError:
            return
        self.updateInProgress = True
        for i, val in enumerate(_schemes):
            if scheme == val:
                self.schemecombo.setCurrentIndex(i)
                break
        self.hostentry.setText(host or '')
        self.portentry.setText(port or '')
        self.pathentry.setText(folder or '')
        self.curuser = user
        self.curpw = passwd
        self.updateInProgress = False
        self.refreshUrl()

    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        data = event.mimeData()
        if data.hasUrls():
            url = data.urls()[0]
            self.setUrl(hglib.fromunicode(url.toString()))
            event.accept()
        elif data.hasText():
            text = data.text()
            self.setUrl(hglib.fromunicode(text))
            event.accept()

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
            self.reload()
        elif event.key() == Qt.Key_Escape:
            if self.cmd.core.is_running():
                self.cmd.core.cancel()
            elif not self.log:
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
        url = hglib.fromunicode(self.urlentry.text())
        dialog = SaveDialog(self.root, alias, url, self)
        if dialog.exec_() == QDialog.Accepted:
            self.curalias = hglib.fromunicode(dialog.aliasentry.text())
            self.repo.invalidateui()
            self.reload()

    def authclicked(self):
        host = hglib.fromunicode(self.hostentry.text())
        user = self.curuser or ''
        pw = self.curpw or ''
        dialog = AuthDialog(self.root, host, user, pw, self)
        if dialog.exec_() == QDialog.Accepted:
            self.curuser, self.curpw = '', ''

    def run(self, cmdline):
        if self.cmd.core.is_running():
            return
        url = self.currentUrl(False)
        safeurl = self.currentUrl(True)
        display = ' '.join(['hg'] + cmdline + [safeurl]) + '\n'
        cmdline.append(url)
        self.cmd.run(cmdline, display=display)

    def inclicked(self):
        self.finishfunc = None
        self.run(['--repository', self.root, 'incoming'])

    def pullclicked(self):
        if self.log:
            self.finishfunc = lambda output: self.invalidate.emit()
        else:
            self.finishfunc = None
        cmdline = ['--repository', self.root, 'pull']
        if self.cachedpp == 'rebase':
            cmdline.append('--rebase')
        elif self.cachedpp == 'update':
            cmdline.append('--update')
        elif self.cachedpp == 'fetch':
            cmdline[2] = 'fetch'
        self.run(cmdline)

    def outclicked(self):
        if self.log:
            def outputnodes(data):
                self.outgoingNodes.emit(data.splitlines())
            self.finishfunc = outputnodes
            self.run(['--repository', self.root, 'outgoing',
                      '--quiet', '--template', '{node}\n'])
        else:
            self.finishfunc = None
            self.run(['--repository', self.root, 'outgoing'])

    def pushclicked(self):
        self.finishfunc = None
        self.run(['--repository', self.root, 'push'])

    def postpullclicked(self):
        dlg = PostPullDialog(self.repo, self)
        if dlg.exec_() == QDialog.Accepted:
            self.repo.invalidateui()
            self.reload()

    def emailclicked(self):
        from tortoisehg.hgqt import run as _run
        _run.email(ui.ui(), root=self.root)

    def removeAlias(self, alias):
        fn = os.path.join(self.root, '.hg', 'hgrc')
        fn, cfg = loadIniFile([fn], self)
        if not hasattr(cfg, 'write'):
            qtlib.WarningMsgBox(_('Unable to remove URL'),
                   _('Iniparse must be installed.'), parent=self)
            return
        if fn is None:
            return
        if alias in cfg['paths']:
            del cfg['paths'][alias]
        try:
            wconfig.writefile(cfg, fn)
            self.repo.invalidateui()
            self.reload()
        except IOError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                hglib.tounicode(e), parent=self)


class PostPullDialog(QDialog):
    def __init__(self, repo, parent):
        super(PostPullDialog, self).__init__(parent)
        self.repo = repo
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.setWindowTitle(_('Post Pull Behavior'))

        self.none = QRadioButton(_('None - simply pull changesets'))
        self.update = QRadioButton(_('Update - pull, then try to update'))
        layout.addWidget(self.none)
        layout.addWidget(self.update)

        if 'fetch' in repo.extensions() or repo.postpull == 'fetch':
            if 'fetch' in repo.extensions():
                btntxt = _('Fetch - use fetch extension')
            else:
                btntxt = _('Fetch - use fetch extension (fetch is not active!)')
            self.fetch = QRadioButton(btntxt)
            layout.addWidget(self.fetch)
        else:
            self.fetch = None
        if 'rebase' in repo.extensions() or repo.postpull == 'rebase':
            if 'rebase' in repo.extensions():
                btntxt = _('Rebase - use rebase extension')
            else:
                btntxt = _('Rebase - use rebase extension (rebase is not active!)')
            self.rebase = QRadioButton(btntxt)
            layout.addWidget(self.rebase)

        self.none.setChecked(True)
        if repo.postpull == 'update':
            self.update.setChecked(True)
        elif repo.postpull == 'fetch':
            self.fetch.setChecked(True)
        elif repo.postpull == 'rebase':
            self.rebase.setChecked(True)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Cancel)
        bb.rejected.connect(self.reject)

        sr = QPushButton(_('Save In Repo'))
        sr.clicked.connect(self.saveInRepo)
        bb.addButton(sr, BB.ActionRole)

        sg = QPushButton(_('Save Global'))
        sg.clicked.connect(self.saveGlobal)
        sg.setAutoDefault(True)
        bb.addButton(sg, BB.ActionRole)

        self.bb = bb
        layout.addWidget(bb)

    def saveInRepo(self):
        fn = os.path.join(self.repo.root, '.hg', 'hgrc')
        self.saveToPath([fn])

    def saveGlobal(self):
        self.saveToPath(util.user_rcpath())

    def getValue(self):
        if self.none.isChecked():
            return 'none'
        elif self.update.isChecked():
            return 'update'
        elif (self.fetch and self.fetch.isChecked()):
            return 'fetch'
        else:
            return 'rebase'

    def saveToPath(self, path):
        fn, cfg = loadIniFile(path, self)
        if not hasattr(cfg, 'write'):
            qtlib.WarningMsgBox(_('Unable to save post pull operation'),
                   _('Iniparse must be installed.'), parent=self)
            return
        if fn is None:
            return
        try:
            cfg.set('tortoisehg', 'postpull', self.getValue())
            wconfig.writefile(cfg, fn)
        except IOError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                hglib.tounicode(e), parent=self)
        super(PostPullDialog, self).accept()

    def reject(self):
        super(PostPullDialog, self).reject()

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
        fontm = QFontMetrics(self.font())
        self.urlentry.setFixedWidth(fontm.width(url)+5)
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
        self.setWindowTitle(_('Save Peer Path'))
        QTimer.singleShot(0, lambda:self.aliasentry.setFocus())

    def accept(self):
        fn = os.path.join(self.root, '.hg', 'hgrc')
        fn, cfg = loadIniFile([fn], self)
        if not hasattr(cfg, 'write'):
            qtlib.WarningMsgBox(_('Unable to save an URL'),
                   _('Iniparse must be installed.'), parent=self)
            return
        if fn is None:
            return
        alias = hglib.fromunicode(self.aliasentry.text())
        path = hglib.fromunicode(self.urlentry.text())
        if alias in cfg['paths']:
            if not qtlib.QuestionMsgBox(_('Confirm URL replace'),
                    _('%s already exists, replace URL?') % alias):
                return
        cfg.set('paths', alias, path)
        try:
            wconfig.writefile(cfg, fn)
        except IOError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                hglib.tounicode(e), parent=self)
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
        hbox.addWidget(QLabel(_('Site Alias')))
        self.aliasentry = QLineEdit(host.split('.', 1)[0])
        hbox.addWidget(self.aliasentry, 1)
        layout.addLayout(hbox)

        hbox = QHBoxLayout()
        hbox.addWidget(QLabel(_('Schemes')))
        self.schemes = QComboBox()
        for s in (('http https', 'http', 'https')):
            self.schemes.addItem(s)
        hbox.addWidget(self.schemes, 1)
        layout.addLayout(hbox)

        hbox = QHBoxLayout()
        hbox.addWidget(QLabel(_('Prefix')))
        self.prefixentry = QLineEdit(host)
        hbox.addWidget(self.prefixentry, 1)
        layout.addLayout(hbox)

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
        self.setWindowTitle(_('Authentication: ') + host)
        self.userentry.selectAll()
        QTimer.singleShot(0, lambda:self.userentry.setFocus())

    def keyringHelp(self):
        pass

    def saveInRepo(self):
        fn = os.path.join(self.root, '.hg', 'hgrc')
        self.saveToPath([fn])

    def saveGlobal(self):
        self.saveToPath(util.user_rcpath())

    def saveToPath(self, path):
        fn, cfg = loadIniFile(path, self)
        if not hasattr(cfg, 'write'):
            qtlib.WarningMsgBox(_('Unable to save authentication'),
                   _('Iniparse must be installed.'), parent=self)
            return
        if fn is None:
            return
        schemes = hglib.fromunicode(self.schemes.currentText())
        prefix = hglib.fromunicode(self.prefixentry.text())
        username = hglib.fromunicode(self.userentry.text())
        password = hglib.fromunicode(self.pwentry.text())
        alias = hglib.fromunicode(self.aliasentry.text())
        if alias+'.prefix' in cfg['auth']:
            if not qtlib.QuestionMsgBox(_('Confirm authentication replace'),
                                        _('Authentication info for %s already'
                                          'exists, replace?') % alias):
                return
        cfg.set('auth', alias+'.schemes', schemes)
        cfg.set('auth', alias+'.username', username)
        cfg.set('auth', alias+'.prefix', prefix)
        key = alias+'.password'
        if password:
            cfg.set('auth', key, password)
        elif not password and key in cfg['auth']:
            del cfg['auth'][key]
        try:
            wconfig.writefile(cfg, fn)
        except IOError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                hglib.tounicode(e), parent=self)
        super(AuthDialog, self).accept()

    def reject(self):
        super(AuthDialog, self).reject()


class PathsTree(QTreeView):
    def __init__(self, root, parent=None):
        QTreeView.__init__(self, parent)
        self.setSelectionMode(QTreeView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menuRequest)
        self.parent = parent

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Delete):
            self.deleteSelected()
        else:
            return super(PathsTree, self).keyPressEvent(event)

    def deleteSelected(self):
        for index in self.selectedRows():
            alias = index.data(Qt.DisplayRole).toString()
            r = qtlib.QuestionMsgBox(_('Confirm path delete'),
                    _('Delete %s from your repo configuration file?') % alias,
                    parent=self)
            if r:
                alias = hglib.fromunicode(alias)
                self.parent.removeAlias(alias)

    def dragObject(self):
        urls = []
        for index in self.selectedRows():
            url = index.sibling(index.row(), 1).data(Qt.DisplayRole).toString()
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
        for alias, path in pathdict.iteritems():
            safepath = url.hidepassword(path)
            self.rows.append([alias, safepath, path])

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

    def realUrl(self, index):
        return self.rows[index.row()][2]


def loadIniFile(rcpath, parent):
    for fn in rcpath:
        if os.path.exists(fn):
            break
    else:
        for fn in rcpath:
            # Try to create a file from rcpath
            try:
                f = open(fn, 'w')
                f.write('# Generated by TortoiseHg\n')
                f.close()
                break
            except EnvironmentError:
                pass
        else:
            qtlib.WarningMsgBox(_('Unable to create a config file'),
                   _('Insufficient access rights.'), parent=parent)
            return None, {}

    return fn, wconfig.readfile(fn)



def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    return SyncWidget(paths.find_root(), **opts)

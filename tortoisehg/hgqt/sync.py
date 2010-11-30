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
from mercurial import merge as mergemod

from tortoisehg.util import hglib, wconfig
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, cmdui, thgrepo, rebase, resolve

# TODO
# Write keyring help, connect to help button

_schemes = ['local', 'ssh', 'http', 'https']

class SyncWidget(QWidget):
    outgoingNodes = pyqtSignal(object)
    incomingBundle = pyqtSignal(QString)
    showMessage = pyqtSignal(unicode)

    output = pyqtSignal(QString, QString)
    progress = pyqtSignal(QString, object, QString, QString, object)
    makeLogVisible = pyqtSignal(bool)

    def __init__(self, root, embedded=False, parent=None, **opts):
        QWidget.__init__(self, parent)

        layout = QVBoxLayout()
        layout.setSpacing(4)
        self.setLayout(layout)
        self.setAcceptDrops(True)

        self.root = root
        self.repo = thgrepo.repository(ui.ui(), root)
        self.finishfunc = None
        self.curuser = None
        self.curpw = None
        self.updateInProgress = False
        self.opts = {}

        self.repo.configChanged.connect(self.configChanged)

        if embedded:
            layout.setContentsMargins(2, 2, 2, 2)
        else:
            self.setWindowTitle(_('TortoiseHg Sync'))
            self.resize(850, 550)

        toph = QHBoxLayout()
        toph.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toph)

        urlframe = QFrame()
        urlframe.setFrameStyle(QFrame.StyledPanel|QFrame.Raised)
        urlvbox = QVBoxLayout()
        urlvbox.setContentsMargins(0, 0, 0, 0)
        urlvbox.setSpacing(4)
        urlframe.setLayout(urlvbox)
        toph.addWidget(urlframe, 1)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(4)
        self.savebutton = QPushButton(_('Save'))
        hbox.addWidget(self.savebutton)
        hbox.addWidget(QLabel(_('URL:')))
        self.urlentry = QLineEdit()
        self.urlentry.setReadOnly(True)
        hbox.addWidget(self.urlentry)
        urlvbox.addLayout(hbox)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(4)
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
        urlvbox.addLayout(hbox)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(4)
        hbox.addWidget(QLabel(_('Path:')))
        self.pathentry = QLineEdit()
        self.pathentry.textChanged.connect(self.refreshUrl)
        hbox.addWidget(self.pathentry, 1)
        self.authbutton = QPushButton(_('Authentication'))
        hbox.addWidget(self.authbutton)
        urlvbox.addLayout(hbox)

        buttonframe = QFrame()
        buttonframe.setFrameStyle(QFrame.StyledPanel|QFrame.Raised)
        buttonvbox = QVBoxLayout()
        buttonvbox.setContentsMargins(0, 0, 0, 0)
        buttonvbox.setSpacing(4)
        buttonframe.setLayout(buttonvbox)
        toph.addWidget(buttonframe)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(4)
        self.inbutton = QPushButton(_('Incoming'))
        hbox.addWidget(self.inbutton)
        self.pullbutton = QPushButton(_('Pull'))
        hbox.addWidget(self.pullbutton)
        buttonvbox.addLayout(hbox)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(4)
        self.postpullbutton = QPushButton()
        hbox.addWidget(self.postpullbutton)
        self.detailsbutton = QPushButton(_('Details'))
        hbox.addWidget(self.detailsbutton)
        buttonvbox.addLayout(hbox)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(4)
        self.outbutton = QPushButton(_('Outgoing'))
        hbox.addWidget(self.outbutton)
        self.pushbutton = QPushButton(_('Push'))
        hbox.addWidget(self.pushbutton)
        self.emailbutton = QPushButton(_('Email'))
        hbox.addWidget(self.emailbutton)
        buttonvbox.addLayout(hbox)

        if 'perfarce' in self.repo.extensions():
            self.p4pbutton = QPushButton(_('p4pending'))
            self.p4pbutton.clicked.connect(self.p4pending)
            hbox.addWidget(self.p4pbutton)
        else:
            self.p4pbutton = None


        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)

        self.hgrctv = PathsTree(self, True)
        self.hgrctv.clicked.connect(self.pathSelected)
        self.hgrctv.removeAlias.connect(self.removeAlias)
        pathsframe = QFrame()
        pathsframe.setFrameStyle(QFrame.StyledPanel|QFrame.Raised)
        pathsbox = QVBoxLayout()
        pathsbox.setContentsMargins(0, 0, 0, 0)
        pathsframe.setLayout(pathsbox)
        lbl = QLabel(_('<b>Configured Paths</b>'))
        pathsbox.addWidget(lbl)
        pathsbox.addWidget(self.hgrctv)
        hbox.addWidget(pathsframe)

        self.reltv = PathsTree(self, False)
        self.reltv.clicked.connect(self.pathSelected)
        pathsframe = QFrame()
        pathsframe.setFrameStyle(QFrame.StyledPanel|QFrame.Raised)
        pathsbox = QVBoxLayout()
        pathsbox.setContentsMargins(0, 0, 0, 0)
        pathsframe.setLayout(pathsbox)
        lbl = QLabel(_('<b>Related Paths</b>'))
        pathsbox.addWidget(lbl)
        pathsbox.addWidget(self.reltv)
        hbox.addWidget(pathsframe)

        layout.addLayout(hbox, 1)

        self.savebutton.clicked.connect(self.saveclicked)
        self.authbutton.clicked.connect(self.authclicked)
        self.inbutton.clicked.connect(self.inclicked)
        self.pullbutton.clicked.connect(self.pullclicked)
        self.outbutton.clicked.connect(self.outclicked)
        self.pushbutton.clicked.connect(self.pushclicked)
        self.emailbutton.clicked.connect(self.emailclicked)
        self.postpullbutton.clicked.connect(self.postpullclicked)
        self.detailsbutton.pressed.connect(self.details)

        self.opbuttons = (self.inbutton, self.pullbutton,
                          self.outbutton, self.pushbutton,
                          self.emailbutton, self.p4pbutton)

        cmd = cmdui.Widget(not embedded, self)
        cmd.commandStarted.connect(self.commandStarted)
        cmd.commandFinished.connect(self.commandFinished)
        cmd.commandCanceling.connect(self.commandCanceled)

        cmd.makeLogVisible.connect(self.makeLogVisible)
        cmd.output.connect(self.output)
        cmd.progress.connect(self.progress)

        layout.addWidget(cmd)
        cmd.setVisible(False)
        self.cmd = cmd
        self.embedded = embedded

        self.reload()
        if 'default' in self.paths:
            self.setUrl(self.paths['default'])
            self.curalias = 'default'
        else:
            self.curalias = None

    def configChanged(self):
        'Repository is reporting its config files have changed'
        self.reload()

    def details(self):
        dlg = DetailsDialog(self.opts, self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        if dlg.exec_() == QDialog.Accepted:
            self.opts.update(dlg.outopts)

    def reload(self):
        # Refresh configured paths
        self.paths = {}
        fn = os.path.join(self.root, '.hg', 'hgrc')
        fn, cfg = loadIniFile([fn], self)
        if 'paths' in cfg:
            for alias in cfg['paths']:
                self.paths[ alias ] = cfg['paths'][ alias ]
        tm = PathsModel(self.paths.items(), self)
        self.hgrctv.setModel(tm)

        # Refresh post-pull
        self.cachedpp = self.repo.postpull
        name = _('Post Pull: ') + self.repo.postpull.title()
        self.postpullbutton.setText(name)

        # Refresh related paths
        known = set(self.paths.values())
        known.add(self.repo.root)
        related = {}
        repoid = self.repo[0].node()
        for repo in thgrepo._repocache.values():
            if repo[0].node() != repoid:
                continue
            if repo.root not in known:
                related[repo.root] = repo.shortname
                known.add(repo.root)
            for alias, path in repo.ui.configitems('paths'):
                if path not in known:
                    related[path] = alias
                    known.add(path)
        pairs = [(alias, path) for path, alias in related.items()]
        tm = PathsModel(pairs, self)
        self.reltv.setModel(tm)

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
                    parts.append(':')
                    parts.append(hidepw and '***' or self.curpw)
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

    def canExit(self):
        return not self.cmd.core.is_running()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Refresh):
            self.reload()
        elif event.key() == Qt.Key_Escape:
            if self.cmd.core.is_running():
                self.cmd.cancel()
            elif not self.embedded:
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
        dlg = SaveDialog(self.repo, alias, url, self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        if dlg.exec_() == QDialog.Accepted:
            self.curalias = hglib.fromunicode(dlg.aliasentry.text())

    def authclicked(self):
        host = hglib.fromunicode(self.hostentry.text())
        user = self.curuser or ''
        pw = self.curpw or ''
        dlg = AuthDialog(self.repo, host, user, pw, self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        if dlg.exec_() == QDialog.Accepted:
            self.curuser, self.curpw = '', ''

    def commandStarted(self):
        for b in self.opbuttons:
            if b: b.setEnabled(False)
        if not self.embedded:
            self.cmd.show_output(True)
            self.cmd.setVisible(True)

    def commandFinished(self, ret):
        self.repo.decrementBusyCount()
        for b in self.opbuttons:
            if b: b.setEnabled(True)
        if self.finishfunc:
            output = self.cmd.core.get_rawoutput()
            self.finishfunc(ret, output)

    def commandCanceled(self):
        for b in self.opbuttons:
            if b: b.setEnabled(True)

    def run(self, cmdline, details):
        if self.cmd.core.is_running():
            return
        for name in list(details) + ['remotecmd']:
            val = self.opts.get(name)
            if not val:
                continue
            if isinstance(val, bool):
                if val:
                    cmdline.append('--' + name)
            elif val:
                cmdline.append('--' + name)
                cmdline.append(val)
        url = self.currentUrl(False)
        if not url:
            qtlib.InfoMsgBox(_('No URL selected'),
                    _('An URL must be selected for this operation.'),
                    parent=self)
            return
        safeurl = self.currentUrl(True)
        display = ' '.join(cmdline + [safeurl]).replace('\n', '^M')
        cmdline.append(url)
        self.repo.incrementBusyCount()
        self.cmd.run(cmdline, display=display, useproc='p4://' in url)

    ##
    ## Workbench toolbar buttons
    ##

    def incoming(self):
        if self.cmd.core.is_running():
            self.output.emit(_('sync command already running'), 'control')
            return
        if 'default' in self.paths:
            self.setUrl(self.paths['default'])
            self.curalias = 'default'
            self.inclicked()

    def pull(self):
        if self.cmd.core.is_running():
            self.output.emit(_('sync command already running'), 'control')
            return
        if 'default' in self.paths:
            self.setUrl(self.paths['default'])
            self.curalias = 'default'
            self.pullclicked()

    def outgoing(self):
        if self.cmd.core.is_running():
            self.output.emit(_('sync command already running'), 'control')
            return
        if 'default-push' in self.paths:
            self.setUrl(self.paths['default-push'])
            self.curalias = 'default-push'
            self.outclicked()
        elif 'default' in self.paths:
            self.setUrl(self.paths['default'])
            self.curalias = 'default'
            self.outclicked()

    def push(self):
        if self.cmd.core.is_running():
            self.output.emit(_('sync command already running'), 'control')
            return
        if 'default-push' in self.paths:
            self.setUrl(self.paths['default-push'])
            self.curalias = 'default-push'
            self.pushclicked()
        elif 'default' in self.paths:
            self.setUrl(self.paths['default'])
            self.curalias = 'default'
            self.pushclicked()

    def pullBundle(self, bundle, rev):
        'accept bundle changesets'
        if self.cmd.core.is_running():
            self.output.emit(_('sync command already running'), 'control')
            return
        save = self.currentUrl(False)
        orev = self.opts.get('rev')
        self.setUrl(bundle)
        if rev is not None:
            self.opts['rev'] = str(rev)
        self.pullclicked()
        self.setUrl(save)
        self.opts['rev'] = orev

    def pushToRevision(self, rev):
        'push to specified revision'
        if self.cmd.core.is_running():
            self.output.emit(_('sync command already running'), 'control')
            return
        orev = self.opts.get('rev')
        self.opts['rev'] = str(rev)
        self.pushclicked()
        self.opts['rev'] = orev

    ##
    ## Sync dialog buttons
    ##

    def inclicked(self):
        url = self.currentUrl(True)
        if self.embedded and not url.startswith('p4://'):
            def finished(ret, output):
                if ret == 0:
                    self.showMessage.emit(_('Incoming changesets found'))
                    self.incomingBundle.emit(bfile)
                elif ret == 1:
                    self.showMessage.emit(_('No incoming changesets'))
                else:
                    self.showMessage.emit(_('Incoming aborted, ret %d') % ret)
            bfile = url
            for badchar in (':', '*', '\\', '?', '#'):
                bfile = bfile.replace(badchar, '')
            bfile = bfile.replace('/', '_')
            bfile = os.path.join(qtlib.gettempdir(), bfile) + '.hg'
            self.finishfunc = finished
            cmdline = ['--repository', self.root, 'incoming', '--bundle', bfile]
            self.run(cmdline, ('force', 'branch', 'rev'))
        else:
            def finished(ret, output):
                if ret == 0:
                    self.showMessage.emit(_('Incoming changesets found'))
                elif ret == 1:
                    self.showMessage.emit(_('No incoming changesets'))
                else:
                    self.showMessage.emit(_('Incoming aborted, ret %d') % ret)
            self.finishfunc = finished
            cmdline = ['--repository', self.root, 'incoming']
            self.run(cmdline, ('force', 'branch', 'rev'))

    def pullclicked(self):
        def finished(ret, output):
            if ret == 0:
                self.showMessage.emit(_('Pull completed successfully'))
            else:
                self.showMessage.emit(_('Pull aborted, ret %d') % ret)
            # handle file conflicts during rebase
            if os.path.exists(self.repo.join('rebasestate')):
                dlg = rebase.RebaseDialog(self.repo, self)
                dlg.finished.connect(dlg.deleteLater)
                dlg.exec_()
                return
            # handle file conflicts during update
            ms = mergemod.mergestate(self.repo)
            for path in ms:
                if ms[path] == 'u':
                    dlg = resolve.ResolveDialog(self.repo, self)
                    dlg.exec_()
                    return
        self.finishfunc = finished
        cmdline = ['--repository', self.root, 'pull', '--verbose']
        uimerge = self.repo.ui.configbool('tortoisehg', 'autoresolve') \
            and 'ui.merge=internal:merge' or 'ui.merge=internal:fail'
        if self.cachedpp == 'rebase':
            cmdline += ['--rebase', '--config', uimerge]
        elif self.cachedpp == 'update':
            cmdline += ['--update', '--config', uimerge]
        elif self.cachedpp == 'fetch':
            cmdline[2] = 'fetch'
        self.run(cmdline, ('force', 'branch', 'rev'))

    def outclicked(self):
        if self.embedded:
            def outputnodes(ret, data):
                if ret == 0:
                    nodes = data.splitlines()
                    self.outgoingNodes.emit(nodes)
                    self.showMessage.emit(_('%d outgoing changesets') %
                                          len(nodes))
                elif ret == 1:
                    self.showMessage.emit(_('No outgoing changesets'))
                else:
                    self.showMessage.emit(_('Outgoing aborted, ret %d') % ret)
            self.finishfunc = outputnodes
            cmdline = ['--repository', self.root, 'outgoing', '--quiet',
                       '--template', '{node}\n']
            self.run(cmdline, ('force', 'branch', 'rev'))
        else:
            self.finishfunc = None
            cmdline = ['--repository', self.root, 'outgoing']
            self.run(cmdline, ('force', 'branch', 'rev'))

    def p4pending(self):
        p4url = self.currentUrl(False)
        def finished(ret, output):
            pending = {}
            if ret == 0:
                for line in output.splitlines():
                    try:
                        hashes = line.split(' ')
                        changelist = hashes.pop(0)
                        if len(hashes)>1 and len(hashes[0])==1:
                           state = hashes.pop(0)
                           if state == 's':
                               changelist = _('%s (submitted)') % changelist
                           elif state == 'p':
                               changelist = _('%s (pending)') % changelist
                           else:
                               raise ValueError
                        pending[changelist] = hashes
                    except (ValueError, IndexError):
                        text = _('Unable to parse p4pending output')
                if pending:
                    text = _('%d pending changelists found') % len(pending)
                else:
                    text = _('No pending Perforce changelists')
            elif ret is None:
                text = _('Aborted p4pending')
            else:
                text = _('Unable to determine pending changesets')
            self.showMessage.emit(text)
            if pending:
                from tortoisehg.hgqt.p4pending import PerforcePending
                dlg = PerforcePending(self.repo, pending, p4url, self)
                dlg.showMessage.connect(self.showMessage)
                dlg.output.connect(self.output)
                dlg.makeLogVisible.connect(self.makeLogVisible)
                dlg.exec_()
        self.finishfunc = finished
        self.run(['--repository', self.root, 'p4pending', '--verbose'], ())

    def pushclicked(self):
        def finished(ret, output):
            if ret == 0:
                self.showMessage.emit(_('Push completed successfully'))
            else:
                self.showMessage.emit(_('Push aborted, ret %d') % ret)
        self.finishfunc = finished
        cmdline = ['--repository', self.root, 'push']
        self.run(cmdline, ('force', 'new-branch', 'branch', 'rev'))

    def postpullclicked(self):
        dlg = PostPullDialog(self.repo, self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.exec_()

    def emailclicked(self):
        from tortoisehg.hgqt import run as _run
        _run.email(ui.ui(), root=self.root)

    @pyqtSlot(QString)
    def removeAlias(self, alias):
        alias = hglib.fromunicode(alias)
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
        self.repo.incrementBusyCount()
        try:
            wconfig.writefile(cfg, fn)
        except EnvironmentError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                hglib.tounicode(e), parent=self)
        self.repo.decrementBusyCount()


class PostPullDialog(QDialog):
    def __init__(self, repo, parent):
        super(PostPullDialog, self).__init__(parent)
        self.repo = repo
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.setWindowTitle(_('Post Pull Behavior'))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        lbl = QLabel(_('Select post-pull operation for this repository'))
        layout.addWidget(lbl)

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

        self.autoresolve_chk = QCheckBox(_('Automatically resolve merge conflicts '
                                           'where possible'))
        self.autoresolve_chk.setChecked(
            repo.ui.configbool('tortoisehg', 'autoresolve', False))
        layout.addWidget(self.autoresolve_chk)

        cfglabel = QLabel(_('<a href="config">Launch settings tool...</a>'))
        cfglabel.linkActivated.connect(self.linkactivated)
        layout.addWidget(cfglabel)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Save|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)

        self.bb = bb
        layout.addWidget(bb)

    def linkactivated(self, command):
        if command == 'config':
            from tortoisehg.hgqt.settings import SettingsDialog
            sd = SettingsDialog(configrepo=False, focus='tortoisehg.postpull',
                            parent=self, root=self.repo.root)
            sd.exec_()

    def getValue(self):
        if self.none.isChecked():
            return 'none'
        elif self.update.isChecked():
            return 'update'
        elif (self.fetch and self.fetch.isChecked()):
            return 'fetch'
        else:
            return 'rebase'

    def accept(self):
        path = os.path.join(self.repo.root, '.hg', 'hgrc')
        fn, cfg = loadIniFile([path], self)
        if not hasattr(cfg, 'write'):
            qtlib.WarningMsgBox(_('Unable to save post pull operation'),
                   _('Iniparse must be installed.'), parent=self)
            return
        if fn is None:
            return
        self.repo.incrementBusyCount()
        try:
            cfg.set('tortoisehg', 'postpull', self.getValue())
            cfg.set('tortoisehg', 'autoresolve',
                    self.autoresolve_chk.isChecked())
            wconfig.writefile(cfg, fn)
        except EnvironmentError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                hglib.tounicode(e), parent=self)
        self.repo.decrementBusyCount()
        super(PostPullDialog, self).accept()

    def reject(self):
        super(PostPullDialog, self).reject()

class SaveDialog(QDialog):
    def __init__(self, repo, alias, url, parent):
        super(SaveDialog, self).__init__(parent)
        self.repo = repo
        self.root = repo.root
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
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
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
        self.repo.incrementBusyCount()
        try:
            wconfig.writefile(cfg, fn)
        except EnvironmentError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                hglib.tounicode(e), parent=self)
        self.repo.decrementBusyCount()
        super(SaveDialog, self).accept()

    def reject(self):
        super(SaveDialog, self).reject()

class AuthDialog(QDialog):
    def __init__(self, repo, host, user, pw, parent):
        super(AuthDialog, self).__init__(parent)
        self.repo = repo
        self.root = repo.root
        self.setLayout(QVBoxLayout())

        form = QFormLayout()
        self.aliasentry = QLineEdit(host.split('.', 1)[0])
        form.addRow(_('Site Alias'), self.aliasentry)

        self.schemes = QComboBox()
        self.schemes.addItems(('http https', 'http', 'https'))
        form.addRow(_('Schemes'), self.schemes)

        self.prefixentry = QLineEdit(host)
        form.addRow(_('Prefix'), self.prefixentry)

        self.userentry = QLineEdit(user)
        form.addRow(_('Username'), self.userentry)

        self.pwentry = QLineEdit(pw)
        self.pwentry.setEchoMode(QLineEdit.Password)
        form.addRow(_('Password'), self.pwentry)
        self.layout().addLayout(form)

        self.globalcb = QCheckBox(_('Save this configuration globally'))
        self.globalcb.setChecked(True)
        self.layout().addWidget(self.globalcb)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Help|BB.Save|BB.Cancel)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        bb.helpRequested.connect(self.keyringHelp)
        self.bb = bb
        self.layout().addWidget(bb)

        self.setWindowTitle(_('Authentication: ') + host)
        self.setWindowFlags(self.windowFlags() & \
                            ~Qt.WindowContextHelpButtonHint)
        self.userentry.selectAll()
        QTimer.singleShot(0, lambda:self.userentry.setFocus())

    def keyringHelp(self):
        pass

    def accept(self):
        if self.globalcb:
            path = util.user_rcpath()
        else:
            path = [os.path.join(self.root, '.hg', 'hgrc')]

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
                                        _('Authentication info for %s already '
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
        self.repo.incrementBusyCount()
        try:
            wconfig.writefile(cfg, fn)
        except EnvironmentError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                hglib.tounicode(e), parent=self)
        self.repo.decrementBusyCount()
        super(AuthDialog, self).accept()

    def reject(self):
        super(AuthDialog, self).reject()


class PathsTree(QTreeView):
    removeAlias = pyqtSignal(QString)

    def __init__(self, parent, editable):
        QTreeView.__init__(self, parent)
        self.setSelectionMode(QTreeView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menuRequest)
        self.editable = editable

    def keyPressEvent(self, event):
        if self.editable and event.matches(QKeySequence.Delete):
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
                self.removeAlias.emit(alias)

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
    def __init__(self, pathlist, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.headers = (_('Alias'), _('URL'))
        self.rows = []
        for alias, path in pathlist:
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


class DetailsDialog(QDialog):
    'Utility dialog for configuring uncommon settings'
    def __init__(self, opts, parent):
        QDialog.__init__(self, parent)
        self.repo = parent.repo

        layout = QFormLayout()
        self.setLayout(layout)

        self.newbranchcb = QCheckBox(_('Allow push of a new branch'))
        self.newbranchcb.setChecked(opts.get('new-branch', False))
        layout.addRow(self.newbranchcb, None)
        self.forcecb = QCheckBox(_('Force push or pull (override safety'
                                   ' checks)'))
        self.forcecb.setChecked(opts.get('force', False))
        layout.addRow(self.forcecb, None)

        lbl = QLabel(_('Specify branch for push/pull:'))
        self.branchle = QLineEdit()
        if opts.get('branch'):
            self.branchle.setText(hglib.tounicode(opts['branch']))
        layout.addRow(lbl, self.branchle)

        lbl = QLabel(_('Specify revision for push/pull:'))
        self.revle = QLineEdit()
        if opts.get('rev'):
            self.revle.setText(hglib.tounicode(opts['rev']))
        layout.addRow(lbl, self.revle)

        lbl = QLabel(_('Remote command:'))
        self.remotele = QLineEdit()
        if opts.get('remotecmd'):
            self.remotele.setText(hglib.tounicode(opts['remotecmd']))
        layout.addRow(lbl, self.remotele)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.bb = bb
        layout.addWidget(bb)

        self.setWindowTitle('%s - sync details' % self.repo.displayname)

    def accept(self):
        outopts = {}
        for name, le in (('branch', self.branchle), ('rev', self.revle),
                         ('remotecmd', self.remotele)):
            outopts[name] = hglib.fromunicode(le.text()).strip()

        if outopts.get('branch') and outopts.get('rev'):
            qtlib.WarningMsgBox(_('Configuration Error'),
                                _('You cannot specify a branch and revision'),
                                parent=self)
            return

        outopts['force'] = self.forcecb.isChecked()
        outopts['new-branch'] = self.newbranchcb.isChecked()

        self.outopts = outopts
        QDialog.accept(self)


def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    return SyncWidget(paths.find_root(), **opts)

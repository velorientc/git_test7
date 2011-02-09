# sync.py - TortoiseHg's sync widget
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os
import re
import tempfile
import urlparse

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import hg, ui, url, util, error
from mercurial import merge as mergemod

from tortoisehg.util import hglib, wconfig
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, cmdui, thgrepo, rebase, resolve
from binascii import hexlify

# TODO
# Write keyring help, connect to help button

_schemes = ['local', 'ssh', 'http', 'https']

def parseurl(path):
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
        if folder.startswith('/'):
            folder = folder[1:]
    else:
        user, host, port, passwd = [''] * 4
        folder = path
        scheme = 'local'
    return user, host, port, folder, passwd, scheme

class SyncWidget(QWidget):
    outgoingNodes = pyqtSignal(object)
    incomingBundle = pyqtSignal(QString)
    showMessage = pyqtSignal(unicode)

    output = pyqtSignal(QString, QString)
    progress = pyqtSignal(QString, object, QString, QString, object)
    makeLogVisible = pyqtSignal(bool)

    def __init__(self, repo, parent, **opts):
        QWidget.__init__(self, parent)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.setLayout(layout)
        self.setAcceptDrops(True)

        self.repo = repo
        self.finishfunc = None
        self.curuser = None
        self.curpw = None
        self.updateInProgress = False
        self.opts = {}
        self.cmenu = None

        self.repo.configChanged.connect(self.configChanged)

        if parent:
            layout.setContentsMargins(2, 2, 2, 2)
        else:
            self.setWindowTitle(_('TortoiseHg Sync'))
            self.resize(850, 550)

        tb = QToolBar(self)
        self.layout().addWidget(tb)
        self.opbuttons = []
        for tip, icon, cb in (
            (_('Preview incoming changesets from specified URL'),
             'incoming', self.inclicked),
            (_('Pull incoming changesets from specified URL'),
             'pull', self.pullclicked),
            (_('Filter outgoing changesets to specified URL'),
             'outgoing', self.outclicked),
            (_('Push outgoing changesets to specified URL'),
             'push', self.pushclicked),
            (_('Email outgoing changesets for specified URL'),
             'mail-forward', self.emailclicked)):
            a = QAction(self)
            a.setToolTip(tip)
            a.setIcon(qtlib.geticon(icon))
            a.triggered.connect(cb)
            self.opbuttons.append(a)
            tb.addAction(a)
        if 'perfarce' in self.repo.extensions():
            a = QAction(self)
            a.setToolTip(_('Manage pending perforce changelists'))
            a.setText('P4')
            a.triggered.connect(self.p4pending)
            self.opbuttons.append(a)
            tb.addAction(a)
        tb.addSeparator()
        self.stopAction = a = QAction(self)
        a.setToolTip(_('Stop current operation'))
        a.setIcon(qtlib.geticon('process-stop'))
        a.triggered.connect(self.stopclicked)
        a.setEnabled(False)
        tb.addAction(a)

        tb.addSeparator()
        self.optionsbutton = QPushButton(_('Options'))
        self.postpullbutton = QPushButton()
        tb.addWidget(self.postpullbutton)
        tb.addWidget(self.optionsbutton)

        self.targetcombo = QComboBox()
        self.targetcombo.setEnabled(False)
        self.targetcheckbox = QCheckBox(_('Target:'))
        self.targetcheckbox.toggled.connect(self.targetcombo.setEnabled)
        if parent:
            tb.addSeparator()
            tb.addWidget(self.targetcheckbox)
            tb.addWidget(self.targetcombo)

        self.urllabel = QLabel()
        self.urllabel.setMargin(4)
        self.urllabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.urllabel.setAcceptDrops(False)
        tb.addSeparator()
        tb.addWidget(self.urllabel)

        urlbox = QGroupBox(_('Current URL'))
        self.layout().addWidget(urlbox)
        hbox = QHBoxLayout()
        urlbox.setLayout(hbox)
        hbox.setSpacing(4)

        self.schemecombo = QComboBox()
        for s in _schemes:
            self.schemecombo.addItem(s)
        self.schemecombo.currentIndexChanged.connect(self.refreshUrl)
        hbox.addWidget(self.schemecombo)
        hbox.addWidget(QLabel(_('Hostname:')))
        self.hostentry = QLineEdit()
        self.hostentry.setAcceptDrops(False)
        self.hostentry.textChanged.connect(self.refreshUrl)
        hbox.addWidget(self.hostentry)
        hbox.addWidget(QLabel(_('Port:')))
        self.portentry = QLineEdit()
        self.portentry.setAcceptDrops(False)
        fontm = QFontMetrics(self.font())
        self.portentry.setFixedWidth(8 * fontm.width('9'))
        self.portentry.textChanged.connect(self.refreshUrl)
        hbox.addWidget(self.portentry)
        hbox.addWidget(QLabel(_('Path:')))
        self.pathentry = QLineEdit()
        self.pathentry.setAcceptDrops(False)
        self.pathentry.textChanged.connect(self.refreshUrl)
        hbox.addWidget(self.pathentry, 1)
        self.securebutton = QPushButton(_('Security'))
        self.securebutton.setToolTip(
            _('Manage HTTPS connection security and user authentication'))
        hbox.addWidget(self.securebutton)
        self.savebutton = QPushButton(_('Save'))
        self.savebutton.setToolTip(
            _('Save current URL under an alias'))
        hbox.addWidget(self.savebutton)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        self.hgrctv = PathsTree(self, True)
        self.hgrctv.clicked.connect(self.pathSelected)
        self.hgrctv.removeAlias.connect(self.removeAlias)
        self.hgrctv.menuRequest.connect(self.menuRequest)
        pathsframe = QFrame()
        pathsframe.setFrameStyle(QFrame.StyledPanel|QFrame.Raised)
        pathsbox = QVBoxLayout()
        pathsbox.setContentsMargins(0, 0, 0, 0)
        pathsframe.setLayout(pathsbox)
        lbl = QLabel(_('<b>Saved Paths</b>'))
        pathsbox.addWidget(lbl)
        pathsbox.addWidget(self.hgrctv)
        hbox.addWidget(pathsframe)

        self.reltv = PathsTree(self, False)
        self.reltv.clicked.connect(self.pathSelected)
        self.reltv.menuRequest.connect(self.menuRequest)
        self.reltv.clicked.connect(self.hgrctv.clearSelection)
        self.hgrctv.clicked.connect(self.reltv.clearSelection)
        pathsframe = QFrame()
        pathsframe.setFrameStyle(QFrame.StyledPanel|QFrame.Raised)
        pathsbox = QVBoxLayout()
        pathsbox.setContentsMargins(0, 0, 0, 0)
        pathsframe.setLayout(pathsbox)
        lbl = QLabel(_('<b>Related Paths</b>'))
        pathsbox.addWidget(lbl)
        pathsbox.addWidget(self.reltv)
        hbox.addWidget(pathsframe)

        self.layout().addLayout(hbox, 1)

        self.savebutton.clicked.connect(self.saveclicked)
        self.securebutton.clicked.connect(self.secureclicked)
        self.postpullbutton.clicked.connect(self.postpullclicked)
        self.optionsbutton.pressed.connect(self.editOptions)

        cmd = cmdui.Widget(not parent, self)
        cmd.commandStarted.connect(self.commandStarted)
        cmd.commandFinished.connect(self.commandFinished)

        cmd.makeLogVisible.connect(self.makeLogVisible)
        cmd.output.connect(self.output)
        cmd.progress.connect(self.progress)

        layout.addWidget(cmd)
        cmd.setVisible(False)
        self.cmd = cmd
        self.embedded = bool(parent)

        self.reload()
        if 'default' in self.paths:
            self.setUrl(self.paths['default'])
            self.curalias = 'default'
        else:
            self.curalias = None

    def loadTargets(self, rev):
        self.targetcombo.clear()
        self.targetcombo.addItem(_('rev: ') + str(rev), str(rev))

        for name in self.repo.namedbranches:
            uname = hglib.tounicode(name)
            self.targetcombo.addItem(_('branch: ') + uname, hexlify(name))
        for name, node in self.repo.bookmarks.items():
            uname = hglib.tounicode(name)
            self.targetcombo.addItem(_('bookmark: ') + uname, node)

    def refreshTargets(self, rev):
        if type(rev) is not int:
            return

        if rev >= len(self.repo):
            return

        self.loadTargets(rev)
        ctx = self.repo.changectx(rev)

        target = str(rev)
        if ctx.thgbranchhead():
            target = hexlify(ctx.branch())
        for tag in ctx.thgtags():
            if tag in self.repo.bookmarks.keys():
                target = ctx.node()

        index = self.targetcombo.findData(target)
        if index < 0:
            index = 0
        self.targetcombo.setCurrentIndex(index)

    def applyTargetOption(self, cmdline):
        if self.targetcheckbox.isChecked():
            revtext = hglib.fromunicode(self.targetcombo.currentText())
            args = revtext.split(': ')
            if args[0] == 'rev':
                cmdline += ['--rev', args[1]]
            elif args[0] == 'branch':
                cmdline += ['--branch', args[1]]
            elif args[0] == 'bookmark':
                cmdline += ['--bookmark', args[1]]
        return cmdline

    def configChanged(self):
        'Repository is reporting its config files have changed'
        self.reload()

    def editOptions(self):
        dlg = OptionsDialog(self.opts, self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        if dlg.exec_() == QDialog.Accepted:
            self.opts.update(dlg.outopts)

    def reload(self):
        # Refresh configured paths
        self.paths = {}
        fn = self.repo.join('hgrc')
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
        self.urllabel.setText(hglib.tounicode(self.currentUrl(True)))
        schemeIndex = self.schemecombo.currentIndex()
        self.hostentry.setEnabled(schemeIndex != 0)
        self.portentry.setEnabled(schemeIndex != 0)
        self.securebutton.setEnabled(schemeIndex > 1)

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
        self.setUrl(path)
        aliasindex = index.sibling(index.row(), 0)
        alias = aliasindex.data(Qt.DisplayRole).toString()
        self.curalias = hglib.fromunicode(alias)

    def setUrl(self, newurl):
        'User has selected a new URL: newurl is expected in local encoding'
        try:
            user, host, port, folder, passwd, scheme = parseurl(newurl)
        except TypeError:
            return
        self.updateInProgress = True
        for i, val in enumerate(_schemes):
            if scheme == val:
                self.schemecombo.setCurrentIndex(i)
                break
        self.hostentry.setText(hglib.tounicode(host or ''))
        self.portentry.setText(hglib.tounicode(port or ''))
        self.pathentry.setText(hglib.tounicode(folder or ''))
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

    def canExit(self):
        return not self.cmd.core.running()

    @pyqtSlot(QPoint, QString, QString, bool)
    def menuRequest(self, point, url, alias, editable):
        'menu event emitted by one of the two URL lists'
        if not self.cmenu:
            acts = []
            menu = QMenu(self)
            for text, cb in ((_('Explore'), self.exploreurl),
                             (_('Terminal'), self.terminalurl),
                             (_('Remove'), self.removeurl)):
                act = QAction(text, self)
                act.triggered.connect(cb)
                acts.append(act)
                menu.addAction(act)
            self.cmenu = menu
            self.acts = acts

        self.menuurl = url
        self.menualias = alias
        self.acts[-1].setEnabled(editable)
        self.cmenu.exec_(point)

    def exploreurl(self):
        url = hglib.fromunicode(self.menuurl)
        u, h, p, folder, pw, scheme = parseurl(url)
        if scheme == 'local':
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            QDesktopServices.openUrl(QUrl(url))

    def terminalurl(self):
        url = hglib.fromunicode(self.menuurl)
        u, h, p, folder, pw, scheme = parseurl(url)
        if scheme != 'local':
            qtlib.InfoMsgBox(_('Repository not local'),
                        _('A terminal shell cannot be opened for remote'))
            return
        shell = self.repo.shell()
        if shell:
            cwd = os.getcwd()
            try:
                os.chdir(folder)
                QProcess.startDetached(shell)
            finally:
                os.chdir(cwd)
        else:
            qtlib.InfoMsgBox(_('No shell configured'),
                        _('A terminal shell must be configured'))
    def removeurl(self):
        if qtlib.QuestionMsgBox(_('Confirm path delete'),
            _('Delete %s from your repo configuration file?') % self.menualias,
            parent=self):
            self.removeAlias(self.menualias)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Refresh):
            self.reload()
        elif event.key() == Qt.Key_Escape:
            if self.cmd.core.running():
                self.cmd.cancel()
            elif not self.embedded:
                self.close()
        else:
            return super(SyncWidget, self).keyPressEvent(event)

    def stopclicked(self):
        if self.cmd.core.running():
            self.cmd.cancel()

    def saveclicked(self):
        if self.curalias:
            alias = self.curalias
        elif 'default' not in self.paths:
            alias = 'default'
        else:
            alias = 'new'
        url = self.currentUrl(False)
        safeurl = self.currentUrl(True)
        dlg = SaveDialog(self.repo, alias, url, safeurl, self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        if dlg.exec_() == QDialog.Accepted:
            self.curalias = hglib.fromunicode(dlg.aliasentry.text())

    def secureclicked(self):
        host = hglib.fromunicode(self.hostentry.text())
        user = self.curuser or ''
        pw = self.curpw or ''
        dlg = SecureDialog(self.repo, host, user, pw, self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        if dlg.exec_() == QDialog.Accepted:
            self.curuser, self.curpw = '', ''

    def commandStarted(self):
        for b in self.opbuttons:
            b.setEnabled(False)
        self.stopAction.setEnabled(True)
        if not self.embedded:
            self.cmd.setShowOutput(True)
            self.cmd.setVisible(True)

    def commandFinished(self, ret):
        self.repo.decrementBusyCount()
        for b in self.opbuttons:
            b.setEnabled(True)
        self.stopAction.setEnabled(False)
        if self.finishfunc:
            output = self.cmd.core.rawoutput()
            self.finishfunc(ret, output)

    def run(self, cmdline, details):
        if self.cmd.core.running():
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

        if 'rev' in details and '--rev' not in cmdline:
            cmdline = self.applyTargetOption(cmdline)

        url = self.currentUrl(False)
        if not url:
            qtlib.InfoMsgBox(_('No URL selected'),
                    _('An URL must be selected for this operation.'),
                    parent=self)
            return

        user, host, port, folder, passwd, scheme = parseurl(url)
        if scheme == 'https':
            if self.repo.ui.configbool('insecurehosts', host):
                cmdline.append('--insecure')

        safeurl = self.currentUrl(True)
        display = ' '.join(cmdline + [safeurl]).replace('\n', '^M')
        cmdline.append(url)
        self.repo.incrementBusyCount()
        self.cmd.run(cmdline, display=display, useproc='p4://' in url)

    ##
    ## Workbench toolbar buttons
    ##

    def incoming(self):
        if self.cmd.core.running():
            self.showMessage.emit(_('sync command already running'))
        else:
            self.inclicked()

    def pull(self):
        if self.cmd.core.running():
            self.showMessage.emit(_('sync command already running'))
        else:
            self.pullclicked()

    def outgoing(self):
        if self.cmd.core.running():
            self.showMessage.emit(_('sync command already running'))
        else:
            self.outclicked()

    def push(self):
        if self.cmd.core.running():
            self.showMessage.emit(_('sync command already running'))
        else:
            self.pushclicked()

    def pullBundle(self, bundle, rev):
        'accept bundle changesets'
        if self.cmd.core.running():
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

    ##
    ## Sync dialog buttons
    ##

    def inclicked(self):
        self.showMessage.emit(_('Incoming...'))
        url = self.currentUrl(True)
        if self.embedded and not url.startswith('p4://') and \
           not self.opts.get('subrepos'):
            def finished(ret, output):
                if ret == 0 and os.path.exists(bfile):
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
            bfile = tempfile.mktemp('.hg', bfile+'_', qtlib.gettempdir())
            self.finishfunc = finished
            cmdline = ['--repository', self.repo.root, 'incoming',
                       '--bundle', bfile]
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
            cmdline = ['--repository', self.repo.root, 'incoming']
            self.run(cmdline, ('force', 'branch', 'rev', 'subrepos'))

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
                    qtlib.InfoMsgBox(_('Merge caused file conflicts'),
                                    _('File conflicts need to be resolved'))
                    dlg = resolve.ResolveDialog(self.repo, self)
                    dlg.finished.connect(dlg.deleteLater)
                    dlg.exec_()
                    return
        self.finishfunc = finished
        self.showMessage.emit(_('Pulling...'))
        cmdline = ['--repository', self.repo.root, 'pull', '--verbose']
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
        self.showMessage.emit(_('Outgoing...'))
        if self.embedded and not self.opts.get('subrepos'):
            def outputnodes(ret, data):
                if ret == 0:
                    nodes = [n for n in data.splitlines() if len(n) == 40]
                    self.outgoingNodes.emit(nodes)
                    self.showMessage.emit(_('%d outgoing changesets') %
                                          len(nodes))
                elif ret == 1:
                    self.showMessage.emit(_('No outgoing changesets'))
                else:
                    self.showMessage.emit(_('Outgoing aborted, ret %d') % ret)
            self.finishfunc = outputnodes
            cmdline = ['--repository', self.repo.root, 'outgoing', '--quiet',
                       '--template', '{node}\n']
            self.run(cmdline, ('force', 'branch', 'rev'))
        else:
            self.finishfunc = None
            cmdline = ['--repository', self.repo.root, 'outgoing']
            self.run(cmdline, ('force', 'branch', 'rev', 'subrepos'))

    def p4pending(self):
        p4url = self.currentUrl(False)
        def finished(ret, output):
            pending = {}
            if ret == 0:
                for line in output.splitlines():
                    if line.startswith('ignoring hg revision'):
                        continue
                    try:
                        hashes = line.split(' ')
                        changelist = hashes.pop(0)
                        clnum = int(changelist)
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
        self.showMessage.emit(_('Perforce pending...'))
        self.run(['--repository', self.repo.root, 'p4pending', '--verbose'], ())

    def pushclicked(self):
        self.showMessage.emit(_('Pushing...'))
        def finished(ret, output):
            if ret == 0:
                self.showMessage.emit(_('Push completed successfully'))
            else:
                self.showMessage.emit(_('Push aborted, ret %d') % ret)
        self.finishfunc = finished
        cmdline = ['--repository', self.repo.root, 'push']
        self.run(cmdline, ('force', 'new-branch', 'branch', 'rev'))

    def postpullclicked(self):
        dlg = PostPullDialog(self.repo, self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.exec_()

    def emailclicked(self):
        self.showMessage.emit(_('Determining outgoing changesets to email...'))
        def outputnodes(ret, data):
            if ret == 0:
                nodes = [n for n in data.splitlines() if len(n) == 40]
                self.showMessage.emit(_('%d outgoing changesets') %
                                        len(nodes))
                try:
                    outgoingrevs = [cmdline[cmdline.index('--rev') + 1]]
                except ValueError:
                    outgoingrevs = None
                from tortoisehg.hgqt import run as _run
                _run.email(ui.ui(), repo=self.repo, rev=nodes,
                           outgoing=True, outgoingrevs=outgoingrevs)
            elif ret == 1:
                self.showMessage.emit(_('No outgoing changesets'))
            else:
                self.showMessage.emit(_('Outgoing aborted, ret %d') % ret)
        self.finishfunc = outputnodes
        cmdline = ['--repository', self.repo.root, 'outgoing', '--quiet',
                    '--template', '{node}\n']
        self.run(cmdline, ('force', 'branch', 'rev'))

    @pyqtSlot(QString)
    def removeAlias(self, alias):
        alias = hglib.fromunicode(alias)
        fn = self.repo.join('hgrc')
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
        self.setWindowFlags(self.windowFlags() &
                            ~Qt.WindowContextHelpButtonHint)

        lbl = QLabel(_('Select post-pull operation for this repository'))
        layout.addWidget(lbl)

        self.none = QRadioButton(_('None - simply pull changesets'))
        self.update = QRadioButton(_('Update - pull, then try to update'))
        layout.addWidget(self.none)
        layout.addWidget(self.update)

        if 'fetch' in repo.extensions() or repo.postpull == 'fetch':
            if 'fetch' in repo.extensions():
                btntxt = _('Fetch - use fetch (auto merge pulled changes)')
            else:
                btntxt = _('Fetch - use fetch extension (fetch is not active!)')
            self.fetch = QRadioButton(btntxt)
            layout.addWidget(self.fetch)
        else:
            self.fetch = None
        if 'rebase' in repo.extensions() or repo.postpull == 'rebase':
            if 'rebase' in repo.extensions():
                btntxt = _('Rebase - rebase local commits above pulled changes')
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
        path = self.repo.join('hgrc')
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
    def __init__(self, repo, alias, url, safeurl, parent):
        super(SaveDialog, self).__init__(parent)

        self.setWindowTitle(_('Save Peer Path'))
        self.setWindowFlags(self.windowFlags() &
                            ~Qt.WindowContextHelpButtonHint)

        self.repo = repo
        self.origurl = url
        self.setLayout(QFormLayout(fieldGrowthPolicy=QFormLayout.ExpandingFieldsGrow))

        self.aliasentry = QLineEdit(hglib.tounicode(alias))
        self.aliasentry.selectAll()
        self.layout().addRow(_('Alias'), self.aliasentry)

        self.urllabel = QLabel(hglib.tounicode(safeurl))
        self.layout().addRow(_('URL'), self.urllabel)

        user, host, port, folder, passwd, scheme = parseurl(url)
        if user or passwd:
            cleanurl = '://'.join([scheme, host])
            if port:
                cleanurl = ':'.join([cleanurl, port])
            if folder:
                cleanurl = '/'.join([cleanurl, folder])
            def showurl(showclean):
                newurl = showclean and cleanurl or safeurl
                self.urllabel.setText(hglib.tounicode(newurl))
            self.cleanurl = cleanurl
            self.clearcb = QCheckBox(_('Remove authentication data from URL'))
            self.clearcb.setToolTip(
                _('User authentication data should be associated with the '
                  'hostname using the security dialog.'))
            self.clearcb.toggled.connect(showurl)
            self.clearcb.setChecked(True)
            self.layout().addRow(self.clearcb)
        else:
            self.clearcb = None

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Save|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(BB.Save).setAutoDefault(True)
        self.bb = bb
        self.layout().addRow(None, bb)

        QTimer.singleShot(0, lambda:self.aliasentry.setFocus())

    def accept(self):
        fn = self.repo.join('hgrc')
        fn, cfg = loadIniFile([fn], self)
        if not hasattr(cfg, 'write'):
            qtlib.WarningMsgBox(_('Unable to save an URL'),
                   _('Iniparse must be installed.'), parent=self)
            return
        if fn is None:
            return
        alias = hglib.fromunicode(self.aliasentry.text())
        if self.clearcb and self.clearcb.isChecked():
            path = self.cleanurl
        else:
            path = self.origurl
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

class SecureDialog(QDialog):
    def __init__(self, repo, host, user, pw, parent):
        super(SecureDialog, self).__init__(parent)

        def genfingerprint():
            pem = ssl.get_server_certificate( (host, 443) )
            der = ssl.PEM_cert_to_DER_cert(pem)
            hash = util.sha1(der).hexdigest()
            pretty = ":".join([hash[x:x + 2] for x in xrange(0, len(hash), 2)])
            le.setText(pretty)

        uhost = hglib.tounicode(host)
        self.setWindowTitle(_('Security: ') + uhost)
        self.setWindowFlags(self.windowFlags() & \
                            ~Qt.WindowContextHelpButtonHint)
        self.repo = repo
        self.host = host
        self.alias = host.replace('.', '')
        self.setLayout(QVBoxLayout())

        securebox = QGroupBox(_('Secure HTTPS Connection'))
        self.layout().addWidget(securebox)
        vbox = QVBoxLayout()
        securebox.setLayout(vbox)
        self.layout().addWidget(securebox)

        self.cacertradio = QRadioButton(
            _('Verify with Certificate Authority certificates (best)'))
        self.fprintradio = QRadioButton(
            _('Verify with stored host fingerprint (good)'))
        self.insecureradio = QRadioButton(
            _('No host validation, but still encrypted (bad)'))
        hbox = QHBoxLayout()
        fprint = repo.ui.config('hostfingerprints', host, '')
        self.fprintentry = le = QLineEdit(fprint)
        self.fprintradio.toggled.connect(self.fprintentry.setEnabled)
        self.fprintentry.setEnabled(False)
        if hasattr(le, 'setPlaceholderText'): # Qt >= 4.7 
            le.setPlaceholderText('### host certificate fingerprint ###')
        hbox.addWidget(le)
        try:
            import ssl # Python 2.6 or backport for 2.5
            qb = QPushButton(_('Query'))
            qb.clicked.connect(genfingerprint)
            qb.setEnabled(False)
            self.fprintradio.toggled.connect(qb.setEnabled)
            hbox.addWidget(qb)
        except ImportError:
            pass
        vbox.addWidget(self.cacertradio)
        vbox.addWidget(self.fprintradio)
        vbox.addLayout(hbox)
        vbox.addWidget(self.insecureradio)

        self.cacertradio.setEnabled(bool(repo.ui.config('web', 'cacerts')))
        self.cacertradio.setChecked(True) # default
        if fprint:
            self.fprintradio.setChecked(True)
        elif repo.ui.config('insecurehosts', host):
            self.insecureradio.setChecked(True)

        authbox = QGroupBox(_('User Authentication'))
        form = QFormLayout()
        authbox.setLayout(form)
        self.layout().addWidget(authbox)

        cfg = repo.ui.config('auth', self.alias+'.username', '')
        self.userentry = QLineEdit(user or cfg)
        self.userentry.setToolTip(
_('''Optional. Username to authenticate with. If not given, and the remote
site requires basic or digest authentication, the user will be prompted for
it. Environment variables are expanded in the username letting you do
foo.username = $USER.'''))
        form.addRow(_('Username'), self.userentry)

        cfg = repo.ui.config('auth', self.alias+'.password', '')
        self.pwentry = QLineEdit(pw or cfg)
        self.pwentry.setEchoMode(QLineEdit.Password)
        self.pwentry.setToolTip(
_('''Optional. Password to authenticate with. If not given, and the remote
site requires basic or digest authentication, the user will be prompted for
it.'''))
        form.addRow(_('Password'), self.pwentry)
        if 'mercurial_keyring' in repo.extensions():
            self.pwentry.clear()
            self.pwentry.setEnabled(False)
            self.pwentry.setToolTip(_('Mercurial keyring extension is enabled. '
                 'Passwords will be stored in platform native '
                 'cryptographically secure method.'))

        cfg = repo.ui.config('auth', self.alias+'.key', '')
        self.keyentry = QLineEdit(cfg)
        self.keyentry.setToolTip(
_('''Optional. PEM encoded client certificate key file. Environment variables
are expanded in the filename.'''))
        form.addRow(_('User Certificate Key File'), self.keyentry)

        cfg = repo.ui.config('auth', self.alias+'.cert', '')
        self.chainentry = QLineEdit(cfg)
        self.chainentry.setToolTip(
_('''Optional. PEM encoded client certificate chain file. Environment variables
are expanded in the filename.'''))
        form.addRow(_('User Certificate Chain File'), self.chainentry)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Help|BB.Save|BB.Cancel)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        bb.helpRequested.connect(self.keyringHelp)
        self.bb = bb
        self.layout().addWidget(bb)

        self.userentry.selectAll()
        QTimer.singleShot(0, lambda:self.userentry.setFocus())

    def keyringHelp(self):
        pass

    def accept(self):
        path = util.user_rcpath()
        fn, cfg = loadIniFile(path, self)
        if not hasattr(cfg, 'write'):
            qtlib.WarningMsgBox(_('Unable to save authentication'),
                   _('Iniparse must be installed.'), parent=self)
            return
        if fn is None:
            return

        def setorclear(section, item, value):
            if value:
                cfg.set(section, item, value)
            elif not value and item in cfg[section]:
                del cfg[section][item]

        if self.cacertradio.isChecked():
            fprint = None
            insecure = None
        elif self.fprintradio.isChecked():
            fprint = hglib.fromunicode(self.fprintentry.text())
            insecure = None
        else:
            fprint = None
            insecure = '1'
        setorclear('hostfingerprints', self.host, fprint)
        setorclear('insecurehosts', self.host, insecure)

        username = hglib.fromunicode(self.userentry.text())
        password = hglib.fromunicode(self.pwentry.text())
        key = hglib.fromunicode(self.keyentry.text())
        chain = hglib.fromunicode(self.chainentry.text())

        cfg.set('auth', self.alias+'.prefix', self.host)
        setorclear('auth', self.alias+'.username', username)
        setorclear('auth', self.alias+'.password', password)
        setorclear('auth', self.alias+'.key', key)
        setorclear('auth', self.alias+'.cert', chain)

        self.repo.incrementBusyCount()
        try:
            wconfig.writefile(cfg, fn)
        except EnvironmentError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                hglib.tounicode(e), parent=self)
        self.repo.decrementBusyCount()
        super(SecureDialog, self).accept()

    def reject(self):
        super(SecureDialog, self).reject()


class PathsTree(QTreeView):
    removeAlias = pyqtSignal(QString)
    menuRequest = pyqtSignal(QPoint, QString, QString, bool)

    def __init__(self, parent, editable):
        QTreeView.__init__(self, parent)
        self.setSelectionMode(QTreeView.SingleSelection)
        self.editable = editable

    def contextMenuEvent(self, event):
        for index in self.selectedRows():
            alias = index.data(Qt.DisplayRole).toString()
            url = index.sibling(index.row(), 1).data(Qt.DisplayRole).toString()
            self.menuRequest.emit(event.globalPos(), url, alias, self.editable)
            return

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

    def selectedUrls(self):
        for index in self.selectedRows():
            yield index.sibling(index.row(), 1).data(Qt.DisplayRole).toString()

    def dragObject(self):
        urls = []
        for url in self.selectedUrls():
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

    def selectedRows(self):
        return self.selectionModel().selectedRows()

class PathsModel(QAbstractTableModel):
    def __init__(self, pathlist, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.headers = (_('Alias'), _('URL'))
        self.rows = []
        for alias, path in pathlist:
            safepath = url.hidepassword(path)
            ualias = hglib.tounicode(alias)
            usafepath = hglib.tounicode(safepath)
            self.rows.append([ualias, usafepath, path])

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


class OptionsDialog(QDialog):
    'Utility dialog for configuring uncommon options'
    def __init__(self, opts, parent):
        QDialog.__init__(self, parent)
        self.setWindowTitle('%s - sync options' % parent.repo.displayname)
        self.repo = parent.repo

        layout = QFormLayout()
        self.setLayout(layout)

        self.newbranchcb = QCheckBox(
            _('Allow push of a new branch (--new-branch)'))
        self.newbranchcb.setChecked(opts.get('new-branch', False))
        layout.addRow(self.newbranchcb, None)
        self.forcecb = QCheckBox(
            _('Force push or pull (override safety checks, --force)'))
        self.forcecb.setChecked(opts.get('force', False))
        layout.addRow(self.forcecb, None)

        self.subrepocb = QCheckBox(
            _('Recurse into subrepositories (--subrepos)'))
        self.subrepocb.setChecked(opts.get('subrepos', False))
        layout.addRow(self.subrepocb, None)

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

    def accept(self):
        outopts = {}
        for name, le in (('remotecmd', self.remotele),):
            outopts[name] = hglib.fromunicode(le.text()).strip()

        outopts['subrepos'] = self.subrepocb.isChecked()
        outopts['force'] = self.forcecb.isChecked()
        outopts['new-branch'] = self.newbranchcb.isChecked()

        self.outopts = outopts
        QDialog.accept(self)


def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    from tortoisehg.hgqt import thgrepo
    repo = thgrepo.repository(ui, path=paths.find_root())
    return SyncWidget(repo, None, **opts)

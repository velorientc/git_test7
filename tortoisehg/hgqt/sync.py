# sync.py - TortoiseHg's sync widget
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os
import tempfile

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import hg, ui, util, scmutil, httpconnection

from tortoisehg.util import hglib, paths, wconfig
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, cmdui, thgrepo, rebase, resolve, hgrcutil
from tortoisehg.hgqt import hgemail

def parseurl(url):
    assert type(url) == unicode
    return util.url(hglib.fromunicode(url))

def linkify(url):
    assert type(url) == unicode
    u = util.url(hglib.fromunicode(url))
    if u.scheme in ('local', 'http', 'https'):
        safe = util.hidepassword(hglib.fromunicode(url))
        return u'<a href="%s">%s</a>' % (url, hglib.tounicode(safe))
    else:
        return url

class SyncWidget(QWidget, qtlib.TaskWidget):
    syncStarted = pyqtSignal()  # incoming/outgoing/pull/push started
    outgoingNodes = pyqtSignal(object)
    incomingBundle = pyqtSignal(QString, QString)
    showMessage = pyqtSignal(unicode)
    pullCompleted = pyqtSignal()
    pushCompleted = pyqtSignal()

    output = pyqtSignal(QString, QString)
    progress = pyqtSignal(QString, object, QString, QString, object)
    makeLogVisible = pyqtSignal(bool)
    showBusyIcon = pyqtSignal(QString)
    hideBusyIcon = pyqtSignal(QString)
    switchToRequest = pyqtSignal(QString)

    def __init__(self, repo, parent, **opts):
        QWidget.__init__(self, parent)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.setLayout(layout)
        self.setAcceptDrops(True)

        self.repo = repo
        self.finishfunc = None
        self.opts = {}
        self.cmenu = None
        self.embedded = bool(parent)

        s = QSettings()
        for opt in ('subrepos', 'force', 'new-branch', 'noproxy', 'debug', 'mq'):
            val = s.value('sync/' + opt, None).toBool()
            if val:
                if opt != 'mq' or 'mq' in self.repo.extensions():
                    self.opts[opt] = val
        for opt in ('remotecmd', 'branch'):
            val = hglib.fromunicode(s.value('sync/' + opt, None).toString())
            if val:
                self.opts[opt] = val

        self.repo.configChanged.connect(self.reload)

        if self.embedded:
            layout.setContentsMargins(2, 2, 2, 2)
        else:
            self.setWindowTitle(_('TortoiseHg Sync'))
            self.setWindowIcon(qtlib.geticon('thg-sync'))
            self.resize(850, 550)

        tb = QToolBar(self)
        tb.setStyleSheet(qtlib.tbstylesheet)
        self.layout().addWidget(tb)
        self.opbuttons = []

        def newaction(tip, icon, cb):
            a = QAction(self)
            a.setToolTip(tip)
            a.setIcon(qtlib.geticon(icon))
            a.triggered.connect(cb)
            self.opbuttons.append(a)
            tb.addAction(a)
            return a

        self.incomingAction = \
        newaction(_('Check for incoming changes from selected URL'),
             'hg-incoming', self.inclicked)
        self.pullAction = \
        newaction(_('Pull incoming changes from selected URL'),
             'hg-pull', lambda: self.pullclicked())
        self.outgoingAction = \
        newaction(_('Detect outgoing changes to selected URL'),
             'hg-outgoing', self.outclicked)
        self.pushAction = \
        newaction(_('Push outgoing changes to selected URL'),
             'hg-push', lambda: self.pushclicked(None))
        newaction(_('Email outgoing changesets for remote repository'),
             'mail-forward', self.emailclicked)

        if 'perfarce' in self.repo.extensions():
            a = QAction(self)
            a.setToolTip(_('Manage pending perforce changelists'))
            a.setText('P4')
            a.triggered.connect(self.p4pending)
            self.opbuttons.append(a)
            tb.addAction(a)
        tb.addSeparator()
        newaction(_('Unbundle'),
             'hg-unbundle', self.unbundle)
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
        self.targetcombo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.targetcombo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLength)
        self.targetcombo.setEnabled(False)
        self.targetcheckbox = QCheckBox(_('Target:'))
        self.targetcheckbox.toggled.connect(self.targetcombo.setEnabled)
        if self.embedded:
            tb.addSeparator()
            tb.addWidget(self.targetcheckbox)
            tb.addWidget(self.targetcombo)

        bottomlayout = QVBoxLayout()
        if not parent:
            bottomlayout.setContentsMargins(5, 5, 5, 5)
        else:
            bottomlayout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(bottomlayout)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        bottomlayout.addLayout(hbox)
        self.optionshdrlabel = lbl = QLabel(_('<b>Selected Options:</b>'))
        hbox.addWidget(lbl)
        self.optionslabel = QLabel()
        self.optionslabel.setAcceptDrops(False)
        hbox.addWidget(self.optionslabel)
        hbox.addStretch()

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        bottomlayout.addLayout(hbox)

        self.pathEditToolbar = tbar = QToolBar(_('Path Edit Toolbar'))
        tbar.setStyleSheet(qtlib.tbstylesheet)
        tbar.setIconSize(QSize(16, 16))
        hbox.addWidget(tbar)

        a = tbar.addAction(qtlib.geticon('thg-password'), _('Security'))
        a.setToolTip(_('Manage HTTPS connection security and user authentication'))
        self.securebutton = a
        tbar.addWidget(qtlib.Spacer(2, 2))

        style = QApplication.style()
        a = tbar.addAction(style.standardIcon(QStyle.SP_DialogSaveButton),
                          _('Save'))
        a.setToolTip(_('Save current URL under an alias'))
        self.savebutton = a
        tbar.addWidget(qtlib.Spacer(2, 2))

        self.urlentry = QLineEdit()
        self.urlentry.textChanged.connect(self.urlChanged)
        tbar.addWidget(self.urlentry)

        # even though currentRowChanged fires pathSelected, clicked signal is
        # also connected to it. otherwise urlentry won't be updated when the
        # selection moves between hgrctv and reltv.

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
        lbl = QLabel(_('Paths in Repository Settings:'))
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
        lbl = QLabel(_('Related Paths:'))
        pathsbox.addWidget(lbl)
        pathsbox.addWidget(self.reltv)
        hbox.addWidget(pathsframe)

        bottomlayout.addLayout(hbox, 1)

        self.savebutton.triggered.connect(self.saveclicked)
        self.securebutton.triggered.connect(self.secureclicked)
        self.postpullbutton.clicked.connect(self.postpullclicked)
        self.optionsbutton.pressed.connect(self.editOptions)

        cmd = cmdui.Widget(not self.embedded, True, self)
        cmd.commandStarted.connect(self.commandStarted)
        cmd.commandFinished.connect(self.commandFinished)
        cmd.makeLogVisible.connect(self.makeLogVisible)
        cmd.output.connect(self.outputHook)
        cmd.progress.connect(self.progress)
        if not self.embedded:
            self.showMessage.connect(cmd.stbar.showMessage)

        bottomlayout.addWidget(cmd)
        cmd.setVisible(False)
        self.cmd = cmd

        self._dialogs = qtlib.DialogKeeper(
            lambda self, dlgmeth, *args: dlgmeth(self, *args), parent=self)

        self.curalias = None
        self.reload()
        if 'default' in self.paths:
            self.setUrl('default')
        else:
            self.setEditUrl('')

    def canswitch(self):
        return not self.targetcheckbox.isChecked()

    def loadTargets(self, ctx):
        self.targetcombo.clear()
        # itemData(role=UserRole) is the argument list to pass to hg
        selIndex = 0
        self.targetcombo.addItem(_('rev: %d (%s)') % (ctx.rev(), str(ctx)),
                                 ('--rev', str(ctx.rev())))

        for name in self.repo.namedbranches:
            uname = hglib.tounicode(name)
            self.targetcombo.addItem(_('branch: ') + uname, ('--branch', name))
            self.targetcombo.setItemData(self.targetcombo.count() - 1, name, Qt.ToolTipRole)
            if ctx.thgbranchhead() and name == ctx.branch():
                selIndex = self.targetcombo.count() - 1
        for name in self.repo._bookmarks.keys():
            uname = hglib.tounicode(name)
            self.targetcombo.addItem(_('bookmark: ') + uname, ('--bookmark', name))
            self.targetcombo.setItemData(self.targetcombo.count() - 1, name, Qt.ToolTipRole)
            if name in ctx.bookmarks():
                selIndex = self.targetcombo.count() - 1

        return selIndex

    def refreshTargets(self, rev):
        if type(rev) is not int:
            return

        if rev >= len(self.repo):
            return

        ctx = self.repo.changectx(rev)
        index = self.loadTargets(ctx)

        if index < 0:
            index = 0
        self.targetcombo.setCurrentIndex(index)

    def isTargetSelected(self):
        return self.targetcheckbox.isChecked()

    def editOptions(self):
        dlg = OptionsDialog(self.opts, self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        if dlg.exec_() == QDialog.Accepted:
            self.opts.update(dlg.outopts)
            self.refreshUrl()

            s = QSettings()
            for opt, val in self.opts.iteritems():
                if isinstance(val, str):
                    val = hglib.tounicode(val)
                s.setValue('sync/' + opt, val)

    @pyqtSlot()
    def reload(self):
        # Refresh configured paths
        self.paths = {}
        fn = self.repo.join('hgrc')
        fn, cfg = hgrcutil.loadIniFile([fn], self)
        if 'paths' in cfg:
            for alias in cfg['paths']:
                self.paths[ alias ] = cfg['paths'][ alias ]
        tm = PathsModel(self.paths.items(), self)
        self.hgrctv.setModel(tm)
        sm = self.hgrctv.selectionModel()
        sm.currentRowChanged.connect(self.pathSelected)

        # Refresh post-pull
        self.cachedpp = self.repo.postpull
        name = _('Post Pull: ') + self.repo.postpull.title()
        self.postpullbutton.setText(name)

        # Refresh related paths
        known = set()
        known.add(os.path.abspath(self.repo.root).lower())
        for path in self.paths.values():
            if not util.hasscheme(path):
                known.add(os.path.abspath(util.localpath(path)).lower())
            else:
                known.add(path)
        related = {}
        for root, shortname in thgrepo.relatedRepositories(self.repo[0].node()):
            if root == self.repo.root:
                continue
            abs = os.path.abspath(root).lower()
            if abs not in known:
                related[root] = shortname
                known.add(abs)
            if root in thgrepo._repocache:
                # repositories already opened keep their ui instances in sync
                repo = thgrepo._repocache[root]
                ui = repo.ui
            elif paths.is_on_fixed_drive(root):
                # directly read the repository's configuration file
                tempui = self.repo.ui.copy()
                tempui.readconfig(os.path.join(root, '.hg', 'hgrc'))
                ui = tempui
            else:
                continue
            for alias, path in ui.configitems('paths'):
                if not util.hasscheme(path):
                    abs = os.path.abspath(util.localpath(path)).lower()
                else:
                    abs = path
                if abs not in known:
                    related[path] = alias
                    known.add(abs)
        pairs = [(alias, path) for path, alias in related.items()]
        tm = PathsModel(pairs, self)
        self.reltv.setModel(tm)
        sm = self.reltv.selectionModel()
        sm.currentRowChanged.connect(self.pathSelected)

    def currentUrl(self):
        return unicode(self.urlentry.text())

    def urlChanged(self):
        self.securebutton.setEnabled('https://' in self.currentUrl())

    def refreshUrl(self):
        'User has selected a new URL'
        self.urlChanged()

        opts = []
        for opt, value in self.opts.iteritems():
            if value is True:
                opts.append('--'+opt)
            elif value:
                opts.append('--'+opt+'='+value)
        self.optionslabel.setText(hglib.tounicode(' '.join(opts)))
        self.optionslabel.setVisible(bool(opts))
        self.optionshdrlabel.setVisible(bool(opts))

    def pathSelected(self, index):
        aliasindex = index.sibling(index.row(), 0)
        alias = aliasindex.data(Qt.DisplayRole).toString()
        self.curalias = hglib.fromunicode(alias)
        path = index.model().realUrl(index)
        self.setEditUrl(hglib.tounicode(path))

    def setEditUrl(self, newurl):
        'Set the current URL without changing the alias [unicode]'
        self.urlentry.setText(newurl)
        self.refreshUrl()

    def setUrl(self, newurl):
        'Set the current URL to the given alias or URL [unicode]'
        model = self.hgrctv.model()
        for col in (0, 1):  # search known (alias, url)
            ixs = model.match(model.index(0, col), Qt.DisplayRole, newurl, 1,
                              Qt.MatchFixedString | Qt.MatchCaseSensitive)
            if ixs:
                self.hgrctv.setCurrentIndex(ixs[0])
                self.pathSelected(ixs[0])  # in case of row not changed
                return

        self.setEditUrl(newurl)

    def dragEnterEvent(self, event):
        data = event.mimeData()
        if data.hasUrls() or data.hasText():
            event.setDropAction(Qt.CopyAction)
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        data = event.mimeData()
        if data.hasUrls() or data.hasText():
            event.setDropAction(Qt.CopyAction)
            event.acceptProposedAction()

    def dropEvent(self, event):
        data = event.mimeData()
        if data.hasUrls():
            url = unicode(data.urls()[0].toString())
            event.setDropAction(Qt.CopyAction)
            event.accept()
        elif data.hasText():
            url = unicode(data.text())
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            return
        if url.startswith('file:///'):
            url = url[8:]
        self.setUrl(url)

    def canExit(self):
        return not self.cmd.core.running()

    @pyqtSlot(QPoint, QString, QString, bool)
    def menuRequest(self, point, url, alias, editable):
        'menu event emitted by one of the two URL lists'
        if not self.cmenu:
            separator = (None, None, None)
            acts = []
            menu = QMenu(self)
            for text, cb, icon in (
                (_('E&xplore'), self.exploreurl, 'system-file-manager'),
                (_('&Terminal'), self.terminalurl, 'utilities-terminal'),
                (_('Copy &Path'), self.copypath, ''),
                separator,
                (_('&Edit...'), self.editurl, 'general'),
                (_('&Remove...'), self.removeurl, 'menudelete')):
                if text is None:
                    menu.addSeparator()
                    continue
                act = QAction(text, self)
                if icon:
                    act.setIcon(qtlib.geticon(icon))
                act.triggered.connect(cb)
                acts.append(act)
                menu.addAction(act)
            self.cmenu = menu
            self.acts = acts

        self.menuurl = url
        self.menualias = alias
        for act in self.acts[-2:]:
            act.setEnabled(editable)
        self.cmenu.exec_(point)

    def exploreurl(self):
        url = unicode(self.menuurl)
        u = parseurl(url)
        if not u.scheme or u.scheme == 'file':
            qtlib.openlocalurl(u.path)
        else:
            QDesktopServices.openUrl(QUrl(url))

    def terminalurl(self):
        url = unicode(self.menuurl)
        u = parseurl(url)
        if u.scheme and u.scheme != 'file':
            qtlib.InfoMsgBox(_('Repository not local'),
                        _('A terminal shell cannot be opened for remote'))
            return
        qtlib.openshell(u.path, 'repo ' + u.path)

    def editurl(self):
        alias = hglib.fromunicode(self.menualias)
        urlu = unicode(self.menuurl)
        dlg = SaveDialog(self.repo, alias, urlu, self, edit=True)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        if dlg.exec_() == QDialog.Accepted:
            self.curalias = hglib.fromunicode(dlg.aliasentry.text())
            self.setEditUrl(dlg.urlentry.text())
            self.reload()

    def removeurl(self):
        if qtlib.QuestionMsgBox(_('Confirm path delete'),
            _('Delete %s from your repo configuration file?') % self.menualias,
            parent=self):
            self.removeAlias(self.menualias)

    def copypath(self):
        QApplication.clipboard().setText(self.menuurl)

    def closeEvent(self, event):
        if self.cmd.core.running():
            if not qtlib.QuestionMsgBox(_('TortoiseHg Sync'),
                _('Are you sure that you want to cancel synchronization?'),
                parent=self):
                event.ignore()

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
        dlg = SaveDialog(self.repo, alias, self.currentUrl(), self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        if dlg.exec_() == QDialog.Accepted:
            self.curalias = hglib.fromunicode(dlg.aliasentry.text())
            self.reload()

    def secureclicked(self):
        if not parseurl(self.currentUrl()).host:
            qtlib.WarningMsgBox(_('No host specified'),
                                _('Please set a valid URL to continue.'),
                                parent=self)
            return
        dlg = SecureDialog(self.repo, self.currentUrl(), self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.exec_()

    def commandStarted(self):
        for b in self.opbuttons:
            b.setEnabled(False)
        self.stopAction.setEnabled(True)
        if self.embedded:
            self.showBusyIcon.emit('thg-sync')
        else:
            self.cmd.setShowOutput(True)
            self.cmd.setVisible(True)

    def commandFinished(self, ret):
        self.hideBusyIcon.emit('thg-sync')
        self.repo.decrementBusyCount()
        for b in self.opbuttons:
            b.setEnabled(True)
        self.stopAction.setEnabled(False)
        if self.finishfunc:
            # allow GC to clean temp finishfunc. here we need to nullify it
            # before calling, because it may be reassigned in finishfunc().
            f = self.finishfunc
            self.finishfunc = None
            output = self.cmd.core.rawoutput()
            f(ret, output)

    def run(self, cmdline, details):
        if self.cmd.core.running():
            return
        self.lastcmdline = list(cmdline)
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
            if self.embedded and self.targetcheckbox.isChecked():
                idx = self.targetcombo.currentIndex()
                if idx != -1:
                    args = self.targetcombo.itemData(idx).toPyObject()
                    if args[0][2:] not in details:
                        args = ('--rev',) + args[1:]
                    cmdline += args
        if self.opts.get('noproxy'):
            cmdline += ['--config', 'http_proxy.host=']
        if self.opts.get('debug'):
            cmdline.append('--debug')

        cururl = self.currentUrl()
        lurl = hglib.fromunicode(cururl)
        u = parseurl(cururl)

        if not u.host and not u.path:
            self.switchToRequest.emit('sync')
            qtlib.WarningMsgBox(_('No remote repository URL or path set'),
                    _('No valid <i>default</i> remote repository URL or path '
                      'has been configured for this repository.<p>Please type '
                      'and save a remote repository path on the Sync widget.'),
                    parent=self)
            return

        if u.scheme == 'https':
            if self.repo.ui.configbool('insecurehosts', u.host):
                cmdline.append('--insecure')
            if u.user:
                cleanurl = util.removeauth(lurl)
                res = httpconnection.readauthforuri(self.repo.ui, cleanurl,
                                                    u.user)
                if res:
                    group, auth = res
                    if auth.get('username'):
                        if qtlib.QuestionMsgBox(
                            _('Redundant authentication info'),
                            _('You have authentication info configured for '
                              'this host and inside this URL.  Remove '
                              'authentication info from this URL?'),
                            parent=self):
                            self.setEditUrl(hglib.tounicode(cleanurl))
                            self.saveclicked()

        safeurl = util.hidepassword(lurl)
        display = ' '.join(cmdline + [safeurl]).replace('\n', '^M')
        if not self.opts.get('mq'):
            cmdline.append(lurl)
        self.repo.incrementBusyCount()
        self.cmd.run(cmdline, display=display, useproc='p4://' in lurl)

    @pyqtSlot(QString, QString)
    def outputHook(self, msg, label):
        label = unicode(label)
        if "'hg push --new-branch'" in msg and 'ui.error' in label.split():
            # not report as error because it will be handled internally in the
            # same session (see pushclicked.finished)
            self.needNewBranch = True
            label = ' '.join(l for l in label.split() if l != 'ui.error')
        self.output.emit(msg, label)

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

    def push(self, confirm, **kwargs):
        if self.cmd.core.running():
            self.showMessage.emit(_('sync command already running'))
        else:
            self.pushclicked(confirm, **kwargs)

    def pullBundle(self, bundle, rev, bsource=None):
        'accept bundle changesets'
        if self.cmd.core.running():
            self.output.emit(_('sync command already running'), 'control')
            return
        save = self.currentUrl()
        orev = self.opts.get('rev')
        self.setEditUrl(hglib.tounicode(bundle))
        if rev is not None:
            self.opts['rev'] = str(rev)
        self.pullclicked(bsource)
        self.setEditUrl(save)
        self.opts['rev'] = orev

    ##
    ## Sync dialog buttons
    ##

    def linkifyWithTarget(self, url):
        link = linkify(url)
        if self.embedded and self.targetcheckbox.isChecked():
            link += u" (%s)" % self.targetcombo.currentText()
        return link

    def inclicked(self):
        self.syncStarted.emit()
        url = self.currentUrl()
        link = self.linkifyWithTarget(url)
        self.showMessage.emit(_('Getting incoming changesets from %s...') % link)
        if self.embedded and not url.startswith('p4://') and \
           not self.opts.get('subrepos'):
            def finished(ret, output):
                if ret == 0 and os.path.exists(bfile):
                    self.showMessage.emit(_('Found incoming changesets from %s') % link)
                    self.incomingBundle.emit(hglib.tounicode(bfile), url)
                elif ret == 1:
                    self.showMessage.emit(_('No incoming changesets from %s') % link)
                else:
                    self.showMessage.emit(_('Incoming from %s aborted, ret %d') % (link, ret))
            bfile = hglib.fromunicode(url)
            for badchar in (':', '*', '\\', '?', '#'):
                bfile = bfile.replace(badchar, '')
            bfile = bfile.replace('/', '_')
            bfile = tempfile.mktemp('.hg', bfile+'_', qtlib.gettempdir())
            self.finishfunc = finished
            cmdline = ['--repository', self.repo.root, 'incoming', '--quiet',
                       '--bundle', bfile]
            self.run(cmdline, ('force', 'branch', 'rev'))
        else:
            def finished(ret, output):
                if ret == 0:
                    self.showMessage.emit(_('Found incoming changesets from %s') % link)
                elif ret == 1:
                    self.showMessage.emit(_('No incoming changesets from %s') % link)
                else:
                    self.showMessage.emit(_('Incoming from %s aborted, ret %d') % (link, ret))
            self.finishfunc = finished
            cmdline = ['--repository', self.repo.root, 'incoming']
            self.run(cmdline, ('force', 'branch', 'rev', 'subrepos'))

    def pullclicked(self, url=None):
        self.syncStarted.emit()
        link = self.linkifyWithTarget(url or self.currentUrl())

        def finished(ret, output):
            if ret == 0:
                self.showMessage.emit(_('Pull from %s completed') % link)
            else:
                self.showMessage.emit(_('Pull from %s aborted, ret %d')
                                      % (link, ret))
            self.pullCompleted.emit()
            # handle file conflicts during rebase
            if self.opts.get('rebase') or self.opts.get('updateorrebase'):
                if os.path.exists(self.repo.join('rebasestate')):
                    dlg = rebase.RebaseDialog(self.repo, self)
                    dlg.finished.connect(dlg.deleteLater)
                    dlg.exec_()
                    return
            # handle file conflicts during update
            for root, path, status in thgrepo.recursiveMergeStatus(self.repo):
                if status == 'u':
                    qtlib.InfoMsgBox(_('Merge caused file conflicts'),
                                    _('File conflicts need to be resolved'))
                    dlg = resolve.ResolveDialog(self.repo, self)
                    dlg.finished.connect(dlg.deleteLater)
                    dlg.exec_()
                    return
        self.finishfunc = finished
        self.showMessage.emit(_('Pulling from %s...') % link)
        cmdline = ['--repository', self.repo.root, 'pull', '--verbose']
        uimerge = self.repo.ui.configbool('tortoisehg', 'autoresolve') \
            and 'ui.merge=internal:merge' or 'ui.merge=internal:fail'
        if self.cachedpp == 'rebase':
            cmdline += ['--rebase', '--config', uimerge]
        elif self.cachedpp == 'update':
            cmdline += ['--update', '--config', uimerge]
        elif self.cachedpp == 'updateorrebase':
            cmdline += ['--update', '--rebase', '--config', uimerge]
        elif self.cachedpp == 'fetch':
            cmdline[2] = 'fetch'
        elif self.opts.get('mq'):
            # force the tool to update to the pulled changeset
            cmdline += ['--update', '--config', uimerge]
        self.run(cmdline, ('force', 'branch', 'rev', 'bookmark', 'mq'))

    def outclicked(self):
        self.syncStarted.emit()

        link = self.linkifyWithTarget(self.currentUrl())
        self.showMessage.emit(_('Finding outgoing changesets to %s...') % link)
        if self.embedded and not self.opts.get('subrepos'):
            def verifyhash(hash):
                if len(hash) != 40:
                    return False
                bad = [c for c in hash if c not in '0123456789abcdef']
                return not bad
            def outputnodes(ret, data):
                if ret == 0:
                    nodes = [n for n in data.splitlines() if verifyhash(n)]
                    if nodes:
                        self.outgoingNodes.emit(nodes)
                    self.showMessage.emit(_('%d outgoing changesets to %s') %
                                          (len(nodes), link))
                elif ret == 1:
                    self.showMessage.emit(_('No outgoing changesets to %s') % link)
                else:
                    self.showMessage.emit(_('Outgoing to %s aborted, ret %d') % (link, ret))
            self.finishfunc = outputnodes
            cmdline = ['--repository', self.repo.root, 'outgoing', '--quiet',
                       '--template', '{node}\n']
            self.run(cmdline, ('force', 'branch', 'rev'))
        else:
            def finished(ret, data):
                if ret == 0:
                    self.showMessage.emit(_('outgoing changesets to %s found') % link)
                elif ret == 1:
                    self.showMessage.emit(_('No outgoing changesets to %s') % link)
                else:
                    self.showMessage.emit(_('Outgoing to %s aborted, ret %d') % (link, ret))
            self.finishfunc = finished
            cmdline = ['--repository', self.repo.root, 'outgoing']
            self.run(cmdline, ('force', 'branch', 'rev', 'subrepos'))

    def p4pending(self):
        p4url = hglib.fromunicode(self.currentUrl())
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

    def pushclicked(self, confirm, rev=None, branch=None, pushall=False):
        if confirm is None:
            confirm = self.repo.ui.configbool('tortoisehg', 'confirmpush', True)
        if rev == '':
            rev = None
        if branch == '':
            branch = None
        if pushall and (rev is not None or branch is not None):
            raise ValueError('inconsistent call with pushall=%r, rev=%r and '
                             'branch=%r' % (pushall, rev, branch))
        validopts = ('force', 'new-branch', 'branch', 'rev', 'bookmark', 'mq')
        self.syncStarted.emit()

        lurl = hglib.fromunicode(self.currentUrl())
        link = self.linkifyWithTarget(self.currentUrl())
        if (not hg.islocal(lurl) and confirm and not self.targetcheckbox.isChecked()):
            r = qtlib.QuestionMsgBox(_('Confirm Push to remote Repository'),
                                     _('Push to remote repository\n%s\n?')
                                     % link, parent=self)
            if not r:
                self.showMessage.emit(_('Push to %s aborted') % link)
                self.pushCompleted.emit()
                return

        self.showMessage.emit(_('Pushing to %s...') % link)
        def finished(ret, output):
            if ret == 0:
                self.showMessage.emit(_('Push to %s completed') % link)
            elif ret == 1:
                self.showMessage.emit(_('No outgoing changesets to %s') % link)
            else:
                self.showMessage.emit(_('Push to %s aborted, ret %d') % (link, ret))
                if self.needNewBranch and '--new-branch' not in self.lastcmdline:
                    r = qtlib.QuestionMsgBox(_('Confirm New Branch'),
                                             _('One or more of the changesets that you '
                                               'are attempting to push involve the '
                                               'creation of a new branch.  Do you want '
                                               'to create a new branch in the remote '
                                               'repository?'), parent=self)
                    if r:
                        cmdline = self.lastcmdline
                        cmdline.extend(['--new-branch'])
                        self.finishfunc = finished  # should be called again
                        self.run(cmdline, validopts)
                        return
            self.pushCompleted.emit()
        self.finishfunc = finished

        if not pushall and rev is None and branch is None:
            # Read the tortoisehg.defaultpush setting to determine what to push by default
            defaultpush = self.repo.ui.config('tortoisehg', 'defaultpush', 'all')
            if self.targetcheckbox.isChecked():
                # target selection overrides defaultpush
                pass
            elif defaultpush == 'all':
                # This is the default
                pass
            elif defaultpush == 'branch':
                branch = '.'
            elif defaultpush == 'revision':
                rev = '.'
            else:
                self.showMessage.emit(_('Invalid default push revision: %s. '
                                        'Please check your Mercurial configuration '
                                        '(tortoisehg.defaultpush)') % defaultpush)
                self.pushCompleted.emit()
                return

        cmdline = ['--repository', self.repo.root, 'push']
        if rev:
            cmdline.extend(['--rev', str(rev)])
        if branch:
            cmdline.extend(['--branch', branch])
        self.needNewBranch = False
        self.run(cmdline, validopts)

    def postpullclicked(self):
        dlg = PostPullDialog(self.repo, self)
        dlg.setWindowFlags(Qt.Sheet)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.exec_()

    def emailclicked(self):
        self.showMessage.emit(_('Determining outgoing changesets to email...'))
        def outputnodes(ret, data):
            if ret == 0:
                nodes = tuple(n for n in data.splitlines() if len(n) == 40)
                self.showMessage.emit(_('%d outgoing changesets') %
                                        len(nodes))
                try:
                    outgoingrevs = (cmdline[cmdline.index('--rev') + 1],)
                except ValueError:
                    outgoingrevs = None
                self._dialogs.open(SyncWidget._createEmailDialog, nodes,
                                   outgoingrevs)
            elif ret == 1:
                self.showMessage.emit(_('No outgoing changesets'))
            else:
                self.showMessage.emit(_('Outgoing aborted, ret %d') % ret)
        self.finishfunc = outputnodes
        cmdline = ['--repository', self.repo.root, 'outgoing', '--quiet',
                    '--template', '{node}\n']
        self.run(cmdline, ('force', 'branch', 'rev'))

    def _createEmailDialog(self, revs, outgoingrevs):
        return hgemail.EmailDialog(self.repo, revs, outgoing=True,
                                   outgoingrevs=outgoingrevs)

    def unbundle(self):
        caption = _("Select bundle file")
        _FILE_FILTER = ';;'.join([_("Bundle files (*.hg)"),
                                  _("All files (*)")])
        bundlefile = QFileDialog.getOpenFileName(
            self, caption, hglib.tounicode(self.repo.root), _FILE_FILTER)
        if bundlefile:
            # Set the pull source to the selected bundle file
            self.urlentry.setText(bundlefile)
            # Execute the incomming command, which will show the revisions in
            # the bundle, and let the user accept or reject them
            self.inclicked()

    @pyqtSlot(QString)
    def removeAlias(self, alias):
        alias = hglib.fromunicode(alias)
        fn = self.repo.join('hgrc')
        fn, cfg = hgrcutil.loadIniFile([fn], self)
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
                                hglib.tounicode(str(e)), parent=self)
        self.repo.decrementBusyCount()
        self.reload()


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
        if ('rebase' in repo.extensions()
            or repo.postpull in ('rebase', 'updateorrebase')):
            if 'rebase' in repo.extensions():
                rebasetxt = _('Rebase - rebase local commits above pulled changes')
                updateorrebasetxt = _('UpdateOrRebase - pull, then try to update or rebase')
            else:
                rebasetxt = _('Rebase - use rebase extension (rebase is not active!)')
                updateorrebasetxt = _('UpdateOrRebase - use rebase extension (rebase is not active!)')
            self.rebase = QRadioButton(rebasetxt)
            layout.addWidget(self.rebase)
            self.updateOrRebase = QRadioButton(updateorrebasetxt)
            layout.addWidget(self.updateOrRebase)

        self.none.setChecked(True)
        if repo.postpull == 'update':
            self.update.setChecked(True)
        elif repo.postpull == 'fetch':
            self.fetch.setChecked(True)
        elif repo.postpull == 'rebase':
            self.rebase.setChecked(True)
        elif repo.postpull == 'updateorrebase':
            self.updateOrRebase.setChecked(True)

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
        elif (self.rebase and self.rebase.isChecked()):
            return 'rebase'
        else:
            return 'updateorrebase'

    def accept(self):
        path = self.repo.join('hgrc')
        fn, cfg = hgrcutil.loadIniFile([path], self)
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
                                hglib.tounicode(str(e)), parent=self)
        self.repo.decrementBusyCount()
        super(PostPullDialog, self).accept()

    def reject(self):
        super(PostPullDialog, self).reject()

class SaveDialog(QDialog):
    def __init__(self, repo, alias, urlu, parent, edit=False):
        super(SaveDialog, self).__init__(parent)

        self.setWindowTitle(_('Save Path'))
        self.setWindowFlags(self.windowFlags() &
                            ~Qt.WindowContextHelpButtonHint)

        self.repo = repo
        self.origurl = hglib.fromunicode(urlu)
        self.setLayout(QFormLayout(fieldGrowthPolicy=QFormLayout.ExpandingFieldsGrow))

        self.origalias = alias
        self.aliasentry = QLineEdit(hglib.tounicode(self.origalias))
        self.aliasentry.selectAll()
        self.aliasentry.textChanged.connect(self.aliasChanged)
        self.layout().addRow(_('Alias'), self.aliasentry)

        safeurl = util.hidepassword(self.origurl)

        self.edit = edit
        if edit:
            self.urlentry = QLineEdit(urlu)
            self.urlentry.textChanged.connect(self.urlChanged)
            self.layout().addRow(_('URL'), self.urlentry)
        else:
            self.urllabel = QLabel(hglib.tounicode(safeurl))
            self.layout().addRow(_('URL'), self.urllabel)

        u = parseurl(urlu)
        if not edit and (u.user or u.passwd) and u.scheme in ('http', 'https'):
            cleanurl = util.removeauth(self.origurl)
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

        s = QSettings()
        self.updatesubpaths = QCheckBox(_('Update subrepo paths'))
        self.updatesubpaths.setChecked(
            s.value('sync/updatesubpaths', True).toBool())
        self.updatesubpaths.setToolTip(
            _('Update or create a path alias called \'%s\' on all subrepos, '
              'using this URL as the base URL, '
              'appending the local relative subrepo path to it')
            % hglib.tounicode(alias))
        self.layout().addRow(self.updatesubpaths)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Save|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(BB.Save).setAutoDefault(True)
        self.bb = bb
        self.layout().addRow(None, bb)

        QTimer.singleShot(0, lambda:self.aliasentry.setFocus())

    def savePath(self, repo, alias, path, confirm=True):
        fn = repo.join('hgrc')
        fn, cfg = hgrcutil.loadIniFile([fn], self)
        if not hasattr(cfg, 'write'):
            qtlib.WarningMsgBox(_('Unable to save an URL'),
                   _('Iniparse must be installed.'), parent=self)
            return
        if fn is None:
            return
        if confirm and (not self.edit or path != self.origurl) and alias in cfg['paths']:
            if not qtlib.QuestionMsgBox(_('Confirm URL replace'),
                _('%s already exists, replace URL?') % hglib.tounicode(alias),
                parent=self):
                return
        cfg.set('paths', alias, path)
        if self.edit and alias != self.origalias:
            cfg.remove('paths', self.origalias)
        try:
            wconfig.writefile(cfg, fn)
        except EnvironmentError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                hglib.tounicode(str(e)), parent=self)
        if self.updatesubpaths.isChecked():
            ctx = repo['.']
            for subname in ctx.substate:
                if ctx.substate[subname][2] != 'hg':
                    continue
                if not os.path.exists(repo.wjoin(subname)):
                    continue
                defaultsubpath = ctx.substate[subname][0]
                pathurl = util.url(path)
                if pathurl.scheme:
                    subpath = str(pathurl).rstrip('/') + '/' + subname
                else:
                    subpath = os.path.normpath(os.path.join(path, subname))
                if defaultsubpath != subname:
                    if not qtlib.QuestionMsgBox(
                            _('Confirm URL replace'),
                            _('Subrepo \'%s\' has a non trivial '
                              'default sync URL:<p>%s<p>'
                              'Replace it with the following URL?:'
                              '<p>%s')
                                % (hglib.tounicode(subname),
                                    hglib.tounicode(defaultsubpath),
                                    hglib.tounicode(subpath)),
                            parent=self):
                        continue
                subrepo = hg.repository(repo.ui, path=repo.wjoin(subname))
                self.savePath(subrepo, alias, subpath, confirm=False)

    def accept(self):
        alias = hglib.fromunicode(self.aliasentry.text())
        if self.edit:
            path = hglib.fromunicode(self.urlentry.text())
        elif self.clearcb and self.clearcb.isChecked():
            path = self.cleanurl
        else:
            path = self.origurl
        self.repo.incrementBusyCount()
        self.savePath(self.repo, alias, path)
        self.repo.decrementBusyCount()
        s = QSettings()
        s.setValue('sync/updatesubpaths', self.updatesubpaths.isChecked())
        super(SaveDialog, self).accept()

    def reject(self):
        super(SaveDialog, self).reject()

    def aliasChanged(self, text):
        enabled = len(text) > 0
        if self.edit:
            enabled = enabled and len(self.urlentry.text()) > 0
        self.bb.button(QDialogButtonBox.Save).setEnabled(enabled)

    def urlChanged(self, text):
        enabled = len(text) > 0 and len(self.aliasentry.text()) > 0
        self.bb.button(QDialogButtonBox.Save).setEnabled(enabled)

class SecureDialog(QDialog):
    def __init__(self, repo, urlu, parent):
        super(SecureDialog, self).__init__(parent)

        def genfingerprint():
            if u.port is None:
                portnum = 443
            else:
                try:
                    portnum = int(u.port)
                except ValueError:
                    qtlib.WarningMsgBox(_('Certificate Query Error'),
                                        _('Invalid port number: %s')
                                        % hglib.tounicode(u.port), parent=self)
                    return
            try:
                pem = ssl.get_server_certificate( (u.host, portnum) )
                der = ssl.PEM_cert_to_DER_cert(pem)
            except Exception, e:
                qtlib.WarningMsgBox(_('Certificate Query Error'),
                                    hglib.tounicode(str(e)), parent=self)
                return
            hash = util.sha1(der).hexdigest()
            pretty = ":".join([hash[x:x + 2] for x in xrange(0, len(hash), 2)])
            le.setText(pretty)

        u = parseurl(urlu)
        assert u.host
        uhost = hglib.tounicode(u.host)
        self.setWindowTitle(_('Security: ') + uhost)
        self.setWindowFlags(self.windowFlags() & \
                            ~Qt.WindowContextHelpButtonHint)

        # if the already user has an [auth] configuration for this URL, use it
        cleanurl = util.removeauth(hglib.fromunicode(urlu))
        res = httpconnection.readauthforuri(repo.ui, cleanurl, u.user)
        if res:
            self.alias, auth = res
        else:
            self.alias, auth = u.host, {}
        self.repo = repo
        self.host = u.host
        if cleanurl.startswith('svn+https://'):
            self.schemes = 'svn+https'
        else:
            self.schemes = None

        self.setLayout(QVBoxLayout())
        self.layout().addWidget(QLabel(_('<b>Host:</b> %s') % uhost))

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
        fprint = repo.ui.config('hostfingerprints', u.host, '')
        self.fprintentry = le = QLineEdit(fprint)
        self.fprintradio.toggled.connect(self.fprintentry.setEnabled)
        self.fprintentry.setEnabled(False)
        if hasattr(le, 'setPlaceholderText'): # Qt >= 4.7
            le.setPlaceholderText(_('### host certificate fingerprint ###'))
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
        elif repo.ui.config('insecurehosts', u.host):
            self.insecureradio.setChecked(True)

        authbox = QGroupBox(_('User Authentication'))
        form = QFormLayout()
        authbox.setLayout(form)
        self.layout().addWidget(authbox)

        self.userentry = QLineEdit(u.user or auth.get('username', ''))
        self.userentry.setToolTip(
_('''Optional. Username to authenticate with. If not given, and the remote
site requires basic or digest authentication, the user will be prompted for
it. Environment variables are expanded in the username letting you do
foo.username = $USER.'''))
        form.addRow(_('Username'), self.userentry)

        self.pwentry = QLineEdit(u.passwd or auth.get('password', ''))
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
                 'Passwords will be stored in a platform-native '
                 'secure method.'))

        self.keyentry = QLineEdit(auth.get('key', ''))
        self.keyentry.setToolTip(
_('''Optional. PEM encoded client certificate key file. Environment variables
are expanded in the filename.'''))
        form.addRow(_('User Certificate Key File'), self.keyentry)

        self.chainentry = QLineEdit(auth.get('cert', ''))
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
        qtlib.openhelpcontents('sync.html#security')

    def accept(self):
        path = scmutil.userrcpath()
        fn, cfg = hgrcutil.loadIniFile(path, self)
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
        setorclear('auth', self.alias+'.schemes', self.schemes)

        self.repo.incrementBusyCount()
        try:
            wconfig.writefile(cfg, fn)
        except EnvironmentError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                hglib.tounicode(str(e)), parent=self)
        self.repo.decrementBusyCount()
        super(SecureDialog, self).accept()

    def reject(self):
        super(SecureDialog, self).reject()


class PathsTree(QTreeView):
    removeAlias = pyqtSignal(QString)
    menuRequest = pyqtSignal(QPoint, QString, QString, bool)

    def __init__(self, parent, editable):
        QTreeView.__init__(self, parent)
        self.setDragDropMode(QTreeView.DragOnly)
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

    def selectedRows(self):
        return self.selectionModel().selectedRows()

class PathsModel(QAbstractTableModel):
    def __init__(self, pathlist, parent=None):
        QAbstractTableModel.__init__(self, parent)
        self.headers = (_('Alias'), _('URL'))
        self.rows = []
        for alias, path in sorted(pathlist):
            safepath = util.hidepassword(path)
            ualias = hglib.tounicode(alias)
            usafepath = hglib.tounicode(safepath)
            self.rows.append([ualias, usafepath, path])

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0 # no child
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0 # no child
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        if role == Qt.DisplayRole:
            return QVariant(self.rows[index.row()][index.column()])
        return QVariant()

    def headerData(self, col, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return QVariant()
        else:
            return QVariant(self.headers[col])

    def mimeData(self, indexes):
        urls = []
        for i in indexes:
            u = QUrl()
            u.setPath(self.rows[i.row()][1])
            urls.append(u)

        m = QMimeData()
        m.setUrls(urls)
        return m

    def mimeTypes(self):
        return ['text/uri-list']

    def flags(self, index):
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled
        return flags

    def realUrl(self, index):
        return self.rows[index.row()][2]



class OptionsDialog(QDialog):
    'Utility dialog for configuring uncommon options'
    def __init__(self, opts, parent):
        QDialog.__init__(self, parent)
        self.setWindowTitle(_('%s - sync options') % parent.repo.displayname)
        self.repo = parent.repo

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.newbranchcb = QCheckBox(
            _('Allow push of a new branch (--new-branch)'))
        self.newbranchcb.setChecked(opts.get('new-branch', False))
        layout.addWidget(self.newbranchcb)

        self.forcecb = QCheckBox(
            _('Force push or pull (override safety checks, --force)'))
        self.forcecb.setChecked(opts.get('force', False))
        layout.addWidget(self.forcecb)

        self.subrepocb = QCheckBox(
            _('Recurse into subrepositories') + u' (--subrepos)')
        self.subrepocb.setChecked(opts.get('subrepos', False))
        layout.addWidget(self.subrepocb)

        self.noproxycb = QCheckBox(
            _('Temporarily disable configured HTTP proxy'))
        self.noproxycb.setChecked(opts.get('noproxy', False))
        layout.addWidget(self.noproxycb)
        proxy = self.repo.ui.config('http_proxy', 'host')
        self.noproxycb.setEnabled(bool(proxy))

        self.debugcb = QCheckBox(
            _('Emit debugging output (--debug)'))
        self.debugcb.setChecked(opts.get('debug', False))
        layout.addWidget(self.debugcb)

        if 'mq' in self.repo.extensions():
            self.mqcb = QCheckBox(
                _('Work on patch queue (--mq)'))
            self.mqcb.setChecked(opts.get('mq', False))
            layout.addWidget(self.mqcb)

        form = QFormLayout()
        layout.addLayout(form)

        lbl = QLabel(_('Remote command:'))
        self.remotele = QLineEdit()
        if opts.get('remotecmd'):
            self.remotele.setText(hglib.tounicode(opts['remotecmd']))
        form.addRow(lbl, self.remotele)

        lbl = QLabel(_('Branch:'))
        self.branchle = QLineEdit()
        if opts.get('branch'):
            self.branchle.setText(hglib.tounicode(opts['branch']))
        form.addRow(lbl, self.branchle)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.bb = bb
        layout.addWidget(bb)

    def accept(self):
        outopts = {}
        for name, le in (('remotecmd', self.remotele),
                         ('branch', self.branchle)):
            outopts[name] = hglib.fromunicode(le.text()).strip()

        outopts['subrepos'] = self.subrepocb.isChecked()
        outopts['force'] = self.forcecb.isChecked()
        outopts['new-branch'] = self.newbranchcb.isChecked()
        outopts['noproxy'] = self.noproxycb.isChecked()
        outopts['debug'] = self.debugcb.isChecked()
        if 'mq' in self.repo.extensions():
            outopts['mq'] = self.mqcb.isChecked()

        self.outopts = outopts
        QDialog.accept(self)

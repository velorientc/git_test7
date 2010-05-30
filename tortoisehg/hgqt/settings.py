# settings.py - Configuration dialog for TortoiseHg and Mercurial
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import sys
import re
import urlparse

from mercurial import hg, ui, util, url, filemerge, error, extensions

from tortoisehg.util import hglib, settings, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# Technical Debt
#   stacked widget or pages need to be scrollable
#   add extensions page after THG 1.1 is released
#   we need a consistent icon set

_unspecstr = _('<unspecified>')

class SettingsCombo(QComboBox):
    def __init__(self, parent=None, **opts):
        QComboBox.__init__(self, parent)
        self.opts = opts
        self.setEditable(opts.get('canedit', False))
        self.setValidator(opts.get('validator', None))
        self.defaults = opts.get('defaults', [])
        self.curvalue = None
        self.loaded = False
        if 'nohist' in opts:
            self.previous = []
        else:
            settings = opts['settings']
            slist = settings.value('settings/'+opts['cpath']).toStringList()
            self.previous = [s for s in slist if s]
        self.setDisabled(opts['readonly'])

    def resetList(self):
        self.clear()
        ucur = hglib.tounicode(self.curvalue)
        if self.opts.get('defer') and not self.loaded:
            if self.curvalue == None: # unspecified
                self.addItem(_unspecstr)
            else:
                self.addItem(ucur or '...')
            return
        self.addItem(_unspecstr)
        curindex = None
        for s in self.defaults:
            if ucur == s:
                curindex = self.count()
            self.addItem(s)
        if self.defaults and self.previous:
            self.insertSeparator(len(self.defaults)+1)
        for m in self.previous:
            if ucur == m and not curindex:
                curindex = self.count()
            self.addItem(m)
        if curindex is not None:
            self.setCurrentIndex(curindex)
        elif self.curvalue is None:
            self.setCurrentIndex(0)
        elif self.curvalue:
            self.addItem(ucur)
            self.setCurrentIndex(self.count()-1)
        else:  # empty string
            self.setEditText(ucur)

    def showPopup(self):
        if self.opts.get('defer') and not self.loaded:
            self.defaults = self.opts['defer']()
            self.loaded = True
            self.resetList()
        QComboBox.showPopup(self)

    def focusInEvent(self, e):
        self.opts['descwidget'].setHtml(self.opts['tooltip'])
        QComboBox.focusInEvent(self, e)

    ## common APIs for all edit widgets

    def setValue(self, curvalue):
        self.curvalue = curvalue
        self.resetList()

    def value(self):
        utext = self.currentText()
        if utext == _unspecstr:
            return None
        if 'nohist' in self.opts or utext in self.defaults + self.previous or not utext:
            return hglib.fromunicode(utext)
        self.previous.insert(0, utext)
        self.previous = self.previous[:10]
        settings = QSettings()
        settings.setValue('settings/'+self.opts['cpath'], self.previous)
        return hglib.fromunicode(utext)

    def isDirty(self):
        return self.value() != self.curvalue


class PasswordEntry(QLineEdit):
    def __init__(self, parent=None, **opts):
        QLineEdit.__init__(self, parent)
        self.opts = opts
        self.curvalue = None
        self.setEchoMode(QLineEdit.Password)
        self.setDisabled(opts['readonly'])

    def focusInEvent(self, e):
        self.opts['descwidget'].setHtml(self.opts['tooltip'])
        QLineEdit.focusInEvent(self, e)

    ## common APIs for all edit widgets

    def setValue(self, curvalue):
        self.curvalue = curvalue
        if curvalue:
            self.setText(hglib.tounicode(curvalue))
        else:
            self.setText('')

    def value(self):
        utext = self.text()
        return utext and hglib.fromunicode(utext) or None

    def isDirty(self):
        return self.value() != self.curvalue


def genEditCombo(opts, defaults=[]):
    opts['canedit'] = True
    opts['defaults'] = defaults
    return SettingsCombo(**opts)

def genIntEditCombo(opts):
    'EditCombo, only allows integer values'
    opts['canedit'] = True
    opts['validator'] = QIntValidator()
    return SettingsCombo(**opts)

def genPasswordEntry(opts):
    'Generate a password entry box'
    return PasswordEntry(**opts)

def genDefaultCombo(opts, defaults=[]):
    'user must select from a list'
    opts['defaults'] = defaults
    opts['nohist'] = True
    return SettingsCombo(**opts)

def genBoolCombo(opts):
    'true, false, unspecified'
    opts['defaults'] = ['True', 'False']
    opts['nohist'] = True
    return SettingsCombo(**opts)

def genDeferredCombo(opts, func):
    'Values retrieved from a function at popup time'
    opts['defer'] = func
    opts['nohist'] = True
    return SettingsCombo(**opts)

def findDiffTools():
    return hglib.difftools(ui.ui())

def findMergeTools():
    return hglib.mergetools(ui.ui())

INFO = (
({'name': 'general', 'label': 'TortoiseHg', 'icon': 'thg_logo'}, (
    (_('Three-way Merge Tool'), 'ui.merge', 
        (genDeferredCombo, findMergeTools),
        _('Graphical merge program for resolving merge conflicts.  If left'
        ' unspecified, Mercurial will use the first applicable tool it finds'
        ' on your system or use its internal merge tool that leaves conflict'
        ' markers in place.  Chose internal:merge to force conflict markers,'
        ' internal:prompt to always select local or other, or internal:dump'
        ' to leave files in the working directory for manual merging')),
    (_('Visual Diff Tool'), 'tortoisehg.vdiff', 
        (genDeferredCombo, findDiffTools),
        _('Specify visual diff tool, as described in the [merge-tools]'
          ' section of your Mercurial configuration files.  If left'
          ' unspecified, TortoiseHg will use the selected merge tool.'
          ' Failing that it uses the first applicable tool it finds.')),
    (_('Visual Editor'), 'tortoisehg.editor', genEditCombo,
        _('Specify the visual editor used to view files.  Format:<br>'
          'myeditor -flags [$FILE --num=$LINENUM][--search $SEARCH]<br><br>'
          'See <a href="%s">OpenAtLine</a>'
          % 'http://bitbucket.org/tortoisehg/thg/wiki/OpenAtLine')),
    (_('CLI Editor'), 'ui.editor', genEditCombo,
        _('The editor to use during a commit and other instances where'
        ' Mercurial needs multiline input from the user.  Used by'
        ' command line commands, including patch import.')),
    (_('Tab Width'), 'tortoisehg.tabwidth', genIntEditCombo,
        _('Specify the number of spaces that tabs expand to in various'
        ' TortoiseHg windows.'
        ' Default: Not expanded')),
    (_('Max Diff Size'), 'tortoisehg.maxdiff', genIntEditCombo,
        _('The maximum size file (in KB) that TortoiseHg will '
        'show changes for in the changelog, status, and commit windows.'
        ' A value of zero implies no limit.  Default: 1024 (1MB)')),
    (_('Capture stderr'), 'tortoisehg.stderrcapt', genBoolCombo,
        _('Redirect stderr to a buffer which is parsed at the end of'
        ' the process for runtime errors. Default: True')),
    (_('Fork hgtk'), 'tortoisehg.hgtkfork', genBoolCombo,
        _('When running hgtk from the command line, fork a background'
        ' process to run graphical dialogs.  Default: True')),
    (_('Full Path Title'), 'tortoisehg.fullpath', genBoolCombo,
        _('Show a full directory path of the repository in the dialog title'
        ' instead of just the root directory name.  Default: False')),
    )),

({'name': 'log', 'label': _('Workbench'), 'icon': 'menulog'}, (
    (_('Author Coloring'), 'tortoisehg.authorcolor', genBoolCombo,
        _('Color changesets by author name.  If not enabled,'
        ' the changes are colored green for merge, red for'
        ' non-trivial parents, black for normal.'
        ' Default: False')),
    (_('Long Summary'), 'tortoisehg.longsummary', genBoolCombo,
        _('If true, concatenate multiple lines of changeset summary'
        ' until they reach 80 characters.'
        ' Default: False')),
    (_('Log Batch Size'), 'tortoisehg.graphlimit', genIntEditCombo,
        _('The number of revisions to read and display in the'
        ' changelog viewer in a single batch.'
        ' Default: 500')),
    (_('Dead Branches'), 'tortoisehg.deadbranch', genEditCombo,
        _('Comma separated list of branch names that should be ignored'
        ' when building a list of branch names for a repository.'
        ' Default: None')),
    (_('Branch Colors'), 'tortoisehg.branchcolors', genEditCombo,
        _('Space separated list of branch names and colors of the form'
        ' branch:#XXXXXX. Spaces and colons in the branch name must be'
        ' escaped using a backslash (\\). Likewise some other characters'
        ' can be escaped in this way, e.g. \\u0040 will be decoded to the'
        ' @ character, and \\n to a linefeed.'
        ' Default: None')),
    (_('Hide Tags'), 'tortoisehg.hidetags', genEditCombo,
        _('Space separated list of tags that will not be shown.'
        ' Useful example: Specify "qbase qparent qtip" to hide the'
        ' standard tags inserted by the Mercurial Queues Extension.' 
        ' Default: None')),
    (_('Use Expander'), 'tortoisehg.changeset-expander', genBoolCombo,
        _('Show changeset details with an expander')),
    )),

({'name': 'commit', 'label': _('Commit'), 'icon': 'menucommit'}, (
    (_('Username'), 'ui.username', genEditCombo,
        _('Name associated with commits.  The common format is\n'
          '"Full Name <email.com>"')),
    (_('Summary Line Length'), 'tortoisehg.summarylen', genIntEditCombo,
       _('Maximum length of the commit message summary line.'
         ' If set, TortoiseHg will issue a warning if the'
         ' summary line is too long or not separated by a'
         ' blank line. Default: 0 (unenforced)')),
    (_('Message Line Length'), 'tortoisehg.messagewrap', genIntEditCombo,
       _('Word wrap length of the commit message.  If'
         ' set, the popup menu can be used to format'
         ' the message and a warning will be issued'
         ' if any lines are too long at commit.'
         '  Default: 0 (unenforced)')),
    (_('Push After Commit'), 'tortoisehg.pushafterci', genBoolCombo,
        _('Attempt to push to default push target after every successful'
          ' commit.  Default: False')),
    (_('Auto Commit List'), 'tortoisehg.autoinc', genEditCombo,
       _('Comma separated list of files that are automatically included'
         ' in every commit.  Intended for use only as a repository setting.'
         '  Default: None')),
    (_('Auto Exclude List'), 'tortoisehg.ciexclude', genEditCombo,
       _('Comma separated list of files that are automatically unchecked'
         ' when the status, commit, and shelve dialogs are opened.'
         '  Default: None')),
    (_('English Messages'), 'tortoisehg.engmsg', genBoolCombo,
       _('Generate English commit messages even if LANGUAGE or LANG'
         ' environment variables are set to a non-English language.'
         ' This setting is used by the Merge, Tag and Backout dialogs.'
         '  Default: False')),
    )),

({'name': 'web', 'label': _('Web Server'), 'icon': 'proxy'}, (
    (_('Name'), 'web.name', genEditCombo,
        _('Repository name to use in the web interface.'
        ' Default is the working directory.')),
    (_('Description'), 'web.description', genEditCombo,
        _("Textual description of the repository's purpose or"
        ' contents.')),
    (_('Contact'), 'web.contact', genEditCombo,
        _('Name or email address of the person in charge of the'
        ' repository.')),
    (_('Style'), 'web.style', (genDefaultCombo,
        ['paper', 'monoblue', 'coal', 'spartan', 'gitweb', 'old']),
        _('Which template map style to use')),
    (_('Archive Formats'), 'web.allow_archive', 
        (genEditCombo, ['bz2', 'gz', 'zip']),
        _('Comma separated list of archive formats allowed for'
        ' downloading')),
    (_('Port'), 'web.port', genIntEditCombo, _('Port to listen on')),
    (_('Push Requires SSL'), 'web.push_ssl', genBoolCombo,
        _('Whether to require that inbound pushes be transported'
        ' over SSL to prevent password sniffing.')),
    (_('Stripes'), 'web.stripes', genIntEditCombo,
        _('How many lines a "zebra stripe" should span in multiline output.'
        ' Default is 1; set to 0 to disable.')),
    (_('Max Files'), 'web.maxfiles', genIntEditCombo,
        _('Maximum number of files to list per changeset. Default: 10')),
    (_('Max Changes'), 'web.maxchanges', genIntEditCombo,
        _('Maximum number of changes to list on the changelog. '
          'Default: 10')),
    (_('Allow Push'), 'web.allow_push', (genEditCombo, ['*']),
        _('Whether to allow pushing to the repository. If empty or not'
        ' set, push is not allowed. If the special value "*", any remote'
        ' user can push, including unauthenticated users. Otherwise, the'
        ' remote user must have been authenticated, and the authenticated'
        ' user name must be present in this list (separated by whitespace'
        ' or ","). The contents of the allow_push list are examined after'
        ' the deny_push list.')),
    (_('Deny Push'), 'web.deny_push', (genEditCombo, ['*']),
        _('Whether to deny pushing to the repository. If empty or not set,'
        ' push is not denied. If the special value "*", all remote users'
        ' are denied push. Otherwise, unauthenticated users are all'
        ' denied, and any authenticated user name present in this list'
        ' (separated by whitespace or ",") is also denied. The contents'
        ' of the deny_push list are examined before the allow_push list.')),
    (_('Encoding'), 'web.encoding', (genEditCombo, ['UTF-8']),
        _('Character encoding name')),
    )),

({'name': 'proxy', 'label': _('Proxy'), 'icon': QStyle.SP_DriveNetIcon}, (
    (_('Host'), 'http_proxy.host', genEditCombo,
        _('Host name and (optional) port of proxy server, for'
        ' example "myproxy:8000"')),
    (_('Bypass List'), 'http_proxy.no', genEditCombo,
        _('Optional. Comma-separated list of host names that'
        ' should bypass the proxy')),
    (_('User'), 'http_proxy.user', genEditCombo,
        _('Optional. User name to authenticate with at the proxy server')),
    (_('Password'), 'http_proxy.passwd', genPasswordEntry,
        _('Optional. Password to authenticate with at the proxy server')),
    )),

({'name': 'email', 'label': _('Email'), 'icon': QStyle.SP_ArrowForward}, (
    (_('From'), 'email.from', genEditCombo,
        _('Email address to use in the "From" header and for'
        ' the SMTP envelope')),
    (_('To'), 'email.to', genEditCombo,
        _('Comma-separated list of recipient email addresses')),
    (_('Cc'), 'email.cc', genEditCombo,
        _('Comma-separated list of carbon copy recipient email addresses')),
    (_('Bcc'), 'email.bcc', genEditCombo,
        _('Comma-separated list of blind carbon copy recipient'
        ' email addresses')),
    (_('method'), 'email.method', (genEditCombo, ['smtp']),
        _('Optional. Method to use to send email messages. If value is'
        ' "smtp" (default), use SMTP (configured below).  Otherwise, use as'
        ' name of program to run that acts like sendmail (takes "-f" option'
        ' for sender, list of recipients on command line, message on stdin).'
        ' Normally, setting this to "sendmail" or "/usr/sbin/sendmail"'
        ' is enough to use sendmail to send messages.')),
    (_('SMTP Host'), 'smtp.host', genEditCombo,
        _('Host name of mail server')),
    (_('SMTP Port'), 'smtp.port', genIntEditCombo,
        _('Port to connect to on mail server.'
        ' Default: 25')),
    (_('SMTP TLS'), 'smtp.tls', genBoolCombo,
        _('Connect to mail server using TLS.'
        ' Default: False')),
    (_('SMTP Username'), 'smtp.username', genEditCombo,
        _('Username to authenticate to mail server with')),
    (_('SMTP Password'), 'smtp.password', genPasswordEntry,
        _('Password to authenticate to mail server with')),
    (_('Local Hostname'), 'smtp.local_hostname', genEditCombo,
        _('Hostname the sender can use to identify itself to the'
        ' mail server.')),
    )),

({'name': 'diff', 'label': _('Diff'),
  'icon': QStyle.SP_FileDialogContentsView}, (
    (_('Patch EOL'), 'patch.eol', (genDefaultCombo,
        ['auto', 'strict', 'crlf', 'lf']),
        _('Normalize file line endings during and after patch to lf or'
        ' crlf.  Strict does no normalization.  Auto does per-file'
        ' detection, and is the recommended setting.'
        ' Default: strict')),
    (_('Git Format'), 'diff.git', genBoolCombo,
        _('Use git extended diff header format.'
        ' Default: False')),
    (_('No Dates'), 'diff.nodates', genBoolCombo,
        _('Do not include modification dates in diff headers.'
        ' Default: False')),
    (_('Show Function'), 'diff.showfunc', genBoolCombo,
        _('Show which function each change is in.'
        ' Default: False')),
    (_('Ignore White Space'), 'diff.ignorews', genBoolCombo,
        _('Ignore white space when comparing lines.'
        ' Default: False')),
    (_('Ignore WS Amount'), 'diff.ignorewsamount', genBoolCombo,
        _('Ignore changes in the amount of white space.'
        ' Default: False')),
    (_('Ignore Blank Lines'), 'diff.ignoreblanklines', genBoolCombo,
        _('Ignore changes whose lines are all blank.'
        ' Default: False')),
    )),
)

CONF_GLOBAL = 0
CONF_REPO   = 1

class SettingsDialog(QDialog):
    'Dialog for editing Mercurial.ini or hgrc'
    def __init__(self, configrepo=False, focus=None, parent=None, root=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle(_('TortoiseHg Settings'))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        try:
            if root is None:
                root = paths.find_root()
            if root:
                repo = hg.repository(ui.ui(), root)
            else:
                repo = None
        except error.RepoError:
            repo = None
            if configrepo:
                qtlib.ErrorMsgBox(_('No repository found'),
                                  _('no repo at ') + root, parent=self)
                self.reject()
                return

        try:
            import iniparse
            iniparse.INIConfig
            self.readonly = False
        except ImportError:
            qtlib.ErrorMsgBox(_('Iniparse package not found'),
                         _("Can't change settings without iniparse package - "
                           'view is readonly.'), parent=self)
            print 'Please install http://code.google.com/p/iniparse/'
            self.readonly = True

        layout = QVBoxLayout()
        self.setLayout(layout)

        s = QSettings()
        self.settings = s
        self.restoreGeometry(s.value('settings/geom').toByteArray())

        def username():
            return util.username() or os.environ.get('USERNAME') or _('User')

        self.conftabs = QTabWidget()
        layout.addWidget(self.conftabs)
        self.conftabs.addTab(SettingsForm(rcpath=util.user_rcpath(),
                                          focus=focus, readonly=self.readonly),
                             qtlib.geticon('settings_user'),
                             _("%s's global settings") % username())
        if repo:
            reporcpath = os.sep.join([repo.root, '.hg', 'hgrc'])
            reponame = hglib.tounicode(os.path.basename(repo.root))
            self.conftabs.addTab(SettingsForm(rcpath=reporcpath,
                                              focus=focus, readonly=self.readonly),
                                 qtlib.geticon('settings_repo'),
                                 _('%s repository settings') % reponame)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        self.connect(bb, SIGNAL("accepted()"), self, SLOT("accept()"))
        self.connect(bb, SIGNAL("rejected()"), self, SLOT("reject()"))
        layout.addWidget(bb)
        self.bb = bb

        self.conftabs.setCurrentIndex(configrepo and CONF_REPO or CONF_GLOBAL)

    def isDirty(self):
        return util.any(self.conftabs.widget(i).isDirty()
                        for i in xrange(self.conftabs.count()))

    def applyChanges(self):
        for i in xrange(self.conftabs.count()):
            self.conftabs.widget(i).applyChanges()

    def canExit(self):
        if self.isDirty():
            ret = qtlib.CustomPrompt(_('Confirm Exit'),
                            _('Apply changes before exit?'), self,
                            (_('&Yes'), _('&No (discard changes)'),
                         _  ('&Cancel')), default=2, esc=2).run()
            if ret == 2:
                return False
            elif ret == 0:
                self.applyChanges()
                return True
        return True

    def accept(self):
        self.applyChanges()
        s = self.settings
        s.setValue('settings/geom', self.saveGeometry())
        s.sync()
        QDialog.accept(self)

    def reject(self):
        if not self.canExit():
            return
        s = self.settings
        s.setValue('settings/geom', self.saveGeometry())
        s.sync()
        QDialog.reject(self)

class SettingsForm(QWidget):
    """Widget for each settings file"""

    def __init__(self, rcpath, focus=None, readonly=False, parent=None):
        super(SettingsForm, self).__init__(parent)

        if isinstance(rcpath, (list, tuple)):
            self.rcpath = rcpath
        else:
            self.rcpath = [rcpath]

        layout = QVBoxLayout()
        self.setLayout(layout)

        tophbox = QHBoxLayout()
        layout.addLayout(tophbox)

        self.fnedit = QLineEdit()
        self.fnedit.setReadOnly(True)
        self.fnedit.setFrame(False)
        self.fnedit.setFocusPolicy(Qt.NoFocus)
        self.fnedit.setStyleSheet('QLineEdit { background: transparent; }')
        edit = QPushButton(_('Edit File'))
        edit.clicked.connect(self.editClicked)
        self.editbtn = edit
        reload = QPushButton(_('Reload'))
        reload.clicked.connect(self.reloadClicked)
        self.reloadbtn = reload
        tophbox.addWidget(QLabel(_('Settings File:')))
        tophbox.addWidget(self.fnedit)
        tophbox.addWidget(edit)
        tophbox.addWidget(reload)

        bothbox = QHBoxLayout()
        layout.addLayout(bothbox)
        pageList = QListWidget()
        pageList.setResizeMode(QListView.Fixed)
        stack = QStackedWidget()
        bothbox.addWidget(pageList, 0)
        bothbox.addWidget(stack, 1)
        pageList.currentRowChanged.connect(stack.setCurrentIndex)

        self.pages = {}
        self.stack = stack
        self.pageList = pageList

        desctext = QTextBrowser()
        desctext.setOpenExternalLinks(True)
        layout.addWidget(desctext)
        self.desctext = desctext

        self.settings = QSettings()
        self.readonly = readonly

        # add page items to treeview
        for meta, info in INFO:
            if isinstance(meta['icon'], str):
                icon = qtlib.geticon(meta['icon'])
            else:
                style = QApplication.style()
                icon = QIcon()
                icon.addPixmap(style.standardPixmap(meta['icon']))
            item = QListWidgetItem(icon, meta['label'])
            pageList.addItem(item)
            self.addPage(meta['name'])

        self.refresh()
        self.focusField(focus or 'ui.merge')

    def editClicked(self):
        'Open internal editor in stacked widget'
        if self.isDirty():
            ret = qtlib.CustomPrompt(_('Confirm Save'),
                    _('Save changes before edit?'), self,
                    (_('&Save'), _('&Discard'), _('&Cancel')),
                    default=2, esc=2).run()
            if ret == 0:
                self.applyChanges()
            elif ret == 2:
                return
        if qtlib.fileEditor(self.fn) == QDialog.Accepted:
            self.refresh()

    def refresh(self, *args):
        # refresh config values
        self.ini = self.loadIniFile(self.rcpath)
        self.fnedit.setText(self.fn)
        for info, widgets in self.pages.values():
            for row, (label, cpath, values, tooltip) in enumerate(info):
                curvalue = self.readCPath(cpath)
                widgets[row].setValue(curvalue)

    def isDirty(self):
        if self.readonly:
            return False
        for info, widgets in self.pages.values():
            for w in widgets:
                if w.isDirty():
                    return True
        return False

    def reloadClicked(self):
        if self.isDirty():
            d = QMessageBox.question(self, _('Confirm Reload'),
                            _('Unsaved changes will be lost.\n'
                            'Do you want to reload?'),
                            QMessageBox.Ok | QMessageBox.Cancel)
            if d != QMessageBox.Ok:
                return
        self.refresh()

    def focusField(self, focusfield):
        'Set page and focus to requested datum'
        for i, (meta, info) in enumerate(INFO):
            for n, (label, cpath, values, tip) in enumerate(info):
                if cpath == focusfield:
                    self.pageList.setCurrentRow(i)
                    QTimer.singleShot(0, lambda: \
                            self.pages[meta['name']][1][n].setFocus())
                    return

    def fillFrame(self, info):
        widgets = []
        frame = QFrame()
        form = QFormLayout()
        frame.setLayout(form)
        self.stack.addWidget(frame)

        for row, (label, cpath, values, tooltip) in enumerate(info):
            opts = {'label':label, 'cpath':cpath, 'tooltip':tooltip,
                    'descwidget':self.desctext, 'settings':self.settings,
                    'readonly':self.readonly}
            if isinstance(values, tuple):
                func = values[0]
                w = func(opts, values[1])
            else:
                func = values
                w = func(opts)
            lbl = QLabel(label)
            lbl.installEventFilter(self)
            lbl.tooltip = tooltip
            form.addRow(lbl, w)
            widgets.append(w)
        return widgets

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Enter:
            self.desctext.setHtml(obj.tooltip)
        return False

    def addPage(self, name):
        for data in INFO:
            if name == data[0]['name']:
                meta, info = data
                break
        widgets = self.fillFrame(info)
        self.pages[name] = info, widgets

    def readCPath(self, cpath):
        'Retrieve a value from the parsed config file'
        try:
            # Presumes single section/key level depth
            section, key = cpath.split('.', 1)
            return self.ini[section][key]
        except KeyError:
            return None

    def loadIniFile(self, rcpath):
        for fn in rcpath:
            if os.path.exists(fn):
                break
        else:
            for fn in rcpath:
                # Try to create a file from rcpath
                try:
                    f = open(fn, 'w')
                    f.write('# Generated by TortoiseHg setting dialog\n')
                    f.close()
                    break
                except (IOError, OSError):
                    pass
            else:
                qtlib.WarningMsgBox(_('Unable to create a Mercurial.ini file'),
                       _('Insufficient access rights, reverting to read-only'
                         ' mode.'), parent=self)
                from mercurial import config
                self.fn = rcpath[0]
                cfg = config.config()
                self.readonly = True
                return cfg
        self.fn = fn
        try:
            import iniparse
            # Monkypatch this regex to prevent iniparse from considering
            # 'rem' as a comment
            iniparse.ini.CommentLine.regex = \
                       re.compile(r'^(?P<csep>[%;#])(?P<comment>.*)$')
            return iniparse.INIConfig(file(fn), optionxformvalue=None)
        except ImportError:
            from mercurial import config
            cfg = config.config()
            cfg.read(fn)
            self.readonly = True
            return cfg
        except Exception, e:
            qtlib.WarningMsgBox(_('Unable to parse a config file'),
                    _('%s\nReverting to read-only mode.') % str(e), 
                    parent=self)
            from mercurial import config
            cfg = config.config()
            cfg.read(fn)
            self.readonly = True
            return cfg

    def recordNewValue(self, cpath, newvalue):
        # 'newvalue' is in local encoding
        section, key = cpath.split('.', 1)
        if newvalue == None:
            try:
                del self.ini[section][key]
            except KeyError:
                pass
            return
        if section not in self.ini:
            if hasattr(self.ini, '_new_namespace'):
                self.ini._new_namespace(section)
            else:
                self.ini.new_namespace(section)
        self.ini[section][key] = newvalue

    def applyChanges(self):
        if self.readonly:
            return

        for info, widgets in self.pages.values():
            for row, (label, cpath, values, tip) in enumerate(info):
                newvalue = widgets[row].value()
                self.recordNewValue(cpath, newvalue)

        try:
            f = util.atomictempfile(self.fn, 'w', createmode=None)
            f.write(str(self.ini))
            f.rename()
        except IOError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                str(e), parent=self)

def run(ui, *pats, **opts):
    return SettingsDialog(opts.get('alias') == 'repoconfig',
                          focus=opts.get('focus'))

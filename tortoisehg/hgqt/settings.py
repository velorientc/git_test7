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

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, settings, paths
from tortoisehg.hgqt import qtlib

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# Technical Debt
#   stacked widget or pages need to be scrollable
#   hook up QSci as internal editor, enable ini syntax highlight
#   initial focus not implemented
#   add extensions page after THG 1.1 is released
#   show icons in listview

_unspecstr = _('<unspecified>')

class SettingsCombo(QComboBox):
    def __init__(self, parent=None, **opts):
        QComboBox.__init__(self, parent)
        self.opts = opts
        self.setEditable(opts.get('canedit', False))
        self.setValidator(opts.get('validator', None))
        self.defaults = opts.get('defaults', [])
        self.curvalue = False
        self.loaded = False
        if 'nohist' in opts:
            self.previous = []
        else:
            settings = opts['settings']
            slist = settings.value('settings/'+opts['cpath']).toStringList()
            self.previous = [s for s in slist]
        self.setDisabled(opts['readonly'])
        self.resetList()

    def resetList(self):
        self.clear()
        ucur = hglib.tounicode(self.curvalue or '')
        if self.opts.get('defer') and not self.loaded:
            if self.curvalue == False: # unspecified
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
        elif self.curvalue == False:
            self.setCurrentIndex(0)
        elif self.curvalue:
            self.addItem(ucur)
            self.setCurrentIndex(self.count()-1)

    def showPopup(self):
        if self.opts.get('defer') and not self.loaded:
            self.defaults = self.opts['defer']()
            self.loaded = True
            self.resetList()
        QComboBox.showPopup(self)

    def focusInEvent(self, e):
        self.opts['descwidget'].setPlainText(self.opts['tooltip'])
        QComboBox.focusInEvent(self, e)

    ## common APIs for all edit widgets

    def setValue(self, curvalue):
        self.curvalue = curvalue
        self.resetList()

    def value(self):
        utext = self.currentText()
        if utext == _unspecstr:
            return False
        if 'nohist' in self.opts or utext in self.defaults + self.previous:
            return hglib.fromunicode(utext)
        print 'saving', self.opts['cpath'], utext
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
        self.curvalue = False
        self.setEchoMode(QLineEdit.Password)
        self.setDisabled(opts['readonly'])

    def focusInEvent(self, e):
        self.opts['descwidget'].setPlainText(self.opts['tooltip'])
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
        return utext and hglib.fromunicode(utext) or False

    def isDirty(self):
        return self.value() != self.curvalue

def genEditCombo(opts, defaults=[]):
    # supplied opts keys: cpath, tooltip, descwidget, defaults
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
    'DefaultCombo - user must select from a list'
    opts['defaults'] = defaults
    return SettingsCombo(**opts)

def genBoolCombo(opts):
    'BoolCombo - true, false, unspecified'
    opts['defaults'] = ['True', 'False']
    return SettingsCombo(**opts)

def genDeferredCombo(opts, func):
    opts['defer'] = func
    opts['nohist'] = True
    return SettingsCombo(**opts)

def findDiffTools():
    return hglib.difftools(ui.ui())

def findMergeTools():
    return hglib.mergetools(ui.ui())

INFO = (
({'name': 'general', 'label': 'TortoiseHg', 'icon': 'thg_logo.ico'}, (
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
        _('Specify the visual editor used to view files, etc')),
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

({'name': 'log', 'label': _('Workbench'),
  'icon': 'menulog.ico'}, (
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

({'name': 'commit', 'label': _('Commit'), 'icon': 'menucommit.ico'}, (
    (_('Username'), 'ui.username', genEditCombo,
        _('Name associated with commits')),
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

({'name': 'web', 'label': _('Web Server'), 'icon': 'proxy.ico'}, (
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
        (genDefaultCombo, ['bz2', 'gz', 'zip']),
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

({'name': 'proxy', 'label': _('Proxy'), 'icon': 'general.ico'}, (
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

({'name': 'email', 'label': _('Email'), 'icon': 'general.ico'}, (
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

({'name': 'diff', 'label': _('Diff'), 'icon': 'general.ico'}, (
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
    def __init__(self, configrepo=False, focus=None, parent=None):
        QDialog.__init__(self, parent=None)

        self.ui = ui.ui()
        try:
            root = paths.find_root()
            if root:
                repo = hg.repository(self.ui, root)
                name = hglib.get_reponame(repo)
                self.ui = repo.ui
            else:
                repo = None
            self.root = root
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

        tophbox = QHBoxLayout()
        layout.addLayout(tophbox)

        combo = QComboBox()
        combo.addItem(_('User global settings'))
        if repo:
            combo.addItem(_('%s repository settings') % hglib.tounicode(name))
        else:
            combo.setEnabled(False)
        self.confcombo = combo

        edit = QPushButton(_('Edit File'))
        reload = QPushButton(_('Reload'))
        reload.pressed.connect(self.reloadClicked)
        tophbox.addWidget(combo)
        tophbox.addWidget(edit)
        tophbox.addWidget(reload)
        tophbox.addStretch(1)

        bothbox = QHBoxLayout()
        layout.addLayout(bothbox)
        pageList = QListWidget()
        stack = QStackedWidget()
        bothbox.addWidget(pageList, 0)
        bothbox.addWidget(stack, 1)
        pageList.currentRowChanged.connect(stack.setCurrentIndex)

        self.pages = {}
        self.stack = stack

        s = QSettings()
        self.settings = s
        self.restoreGeometry(s.value('settings/geom').toByteArray())

        desctext = QTextBrowser()
        layout.addWidget(desctext)
        self.desctext = desctext

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        self.connect(bb, SIGNAL("accepted()"), self, SLOT("accept()"))
        self.connect(bb, SIGNAL("rejected()"), self, SLOT("reject()"))
        layout.addWidget(bb)
        self.bb = bb

        # add page items to treeview
        for meta, info in INFO:
            # TODO: set meta['icon']
            pageList.addItem(meta['label'])
            self.addPage(meta['name'])

        combo.setCurrentIndex(configrepo and CONF_REPO or CONF_GLOBAL)
        combo.currentIndexChanged.connect(self.fileselect)
        self.refresh()
        self.focusField(focus or 'ui.merge')

    def fileselect(self, newindex):
        'select another hgrc file'
        combo = self.confcombo
        if self.isDirty():
            ret = qtlib.CustomPrompt(_('Confirm Switch'),
                    _('Switch after saving changes?'), self,
                    (_('&Save'), _('&Discard'), _('&Cancel')),
                    default=2, esc=2).run()
            if ret == 2:
                repo = newindex == CONF_GLOBAL
                combo.setCurrentIndex(repo and CONF_REPO or CONF_GLOBAL)
                return
            elif ret == 0:
                self.applyChanges()
        self.refresh()

    def editClicked(self, button):
        'Open internal editor in stacked widget'
        pass

    def refresh(self, *args):
        # determine target config file
        if self.confcombo.currentIndex() == CONF_REPO:
            repo = hg.repository(ui.ui(), self.root)
            name = hglib.get_reponame(repo)
            self.rcpath = [os.sep.join([repo.root, '.hg', 'hgrc'])]
            self.setWindowTitle(_('TortoiseHg Configure Repository - ') + \
                           hglib.tounicode(name))
            #set_tortoise_icon(self, 'settings_repo.ico')
        else:
            self.rcpath = util.user_rcpath()
            self.setWindowTitle(_('TortoiseHg Configure User-Global Settings'))
            #set_tortoise_icon(self, 'settings_user.ico')

        # refresh config values
        self.ini = self.loadIniFile(self.rcpath)
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
                    self.stack.setCurrentIndex(i)
                    self.pages[meta['name']][1][n].setFocus()
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
            form.addRow(label, w)
            widgets.append(w)
        return widgets

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
            return False

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
                         'mode.'), parent=self)
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
        if newvalue == False:
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

def run(ui, *pats, **opts):
    return SettingsDialog(opts.get('alias') == 'repoconfig',
                          focus=opts.get('focus'))

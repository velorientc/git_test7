# settings.py - Configuration dialog for TortoiseHg and Mercurial
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import ui, util, error

from tortoisehg.util import hglib, settings, paths, wconfig, i18n
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, qscilib, thgrepo

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# Technical Debt
#   stacked widget or pages need to be scrollable
#   we need a consistent icon set
#   connect to thgrepo.configChanged signal and refresh

_unspecstr = _('<unspecified>')
ENTRY_WIDTH = 300

class SettingsCombo(QComboBox):
    def __init__(self, parent=None, **opts):
        QComboBox.__init__(self, parent, toolTip=opts['tooltip'])
        self.opts = opts
        self.setEditable(opts.get('canedit', False))
        self.setValidator(opts.get('validator', None))
        self.defaults = opts.get('defaults', [])
        if self.defaults and self.isEditable():
            self.setCompleter(QCompleter(self.defaults, self))
        self.curvalue = None
        self.loaded = False
        if 'nohist' in opts:
            self.previous = []
        else:
            settings = opts['settings']
            slist = settings.value('settings/'+opts['cpath']).toStringList()
            self.previous = [s for s in slist if s]
        self.setMinimumWidth(ENTRY_WIDTH)

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
        QLineEdit.__init__(self, parent, toolTip=opts['tooltip'])
        self.opts = opts
        self.curvalue = None
        self.setEchoMode(QLineEdit.Password)
        self.setMinimumWidth(ENTRY_WIDTH)

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

class FontEntry(QPushButton):
    def __init__(self, parent=None, **opts):
        QPushButton.__init__(self, parent, toolTip=opts['tooltip'])
        self.opts = opts
        self.curvalue = None
        self.clicked.connect(self.on_clicked)
        cpath = self.opts['cpath']
        assert cpath.startswith('tortoisehg.')
        self.fname = cpath[11:]
        self.setMinimumWidth(ENTRY_WIDTH)

    def on_clicked(self, checked):
        def newFont(font):
            self.setText(font.toString())
            thgf.setFont(font)
        thgf = qtlib.getfont(self.fname)
        origfont = self.currentFont() or thgf.font()
        dlg = QFontDialog(self)
        dlg.currentFontChanged.connect(newFont)
        font, isok = dlg.getFont(origfont, self)
        self.setText(font.toString())
        thgf.setFont(font)

    def currentFont(self):
        """currently selected QFont if specified"""
        if not self.value():
            return None

        f = QFont()
        f.fromString(self.value())
        return f

    ## common APIs for all edit widgets

    def setValue(self, curvalue):
        self.curvalue = curvalue
        if curvalue:
            self.setText(hglib.tounicode(curvalue))
        else:
            self.setText(_unspecstr)

    def value(self):
        utext = self.text()
        if utext == _unspecstr:
            return None
        else:
            return hglib.fromunicode(utext)

    def isDirty(self):
        return self.value() != self.curvalue

class SettingsCheckBox(QCheckBox):
    def __init__(self, parent=None, **opts):
        QCheckBox.__init__(self, parent, toolTip=opts['tooltip'])
        self.opts = opts
        self.curvalue = None
        self.setText(opts['label'])
        self.valfunc = self.opts['valfunc']
        self.toggled.connect(self.valfunc)

    def setValue(self, curvalue):
        if self.curvalue == None:
            self.curvalue = curvalue
        self.setChecked(curvalue)

    def value(self):
        return self.isChecked()

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

def genFontEdit(opts):
    return FontEntry(**opts)

def findDiffTools():
    return hglib.difftools(ui.ui())

def findMergeTools():
    return hglib.mergetools(ui.ui())

def genCheckBox(opts):
    opts['nohist'] = True
    return SettingsCheckBox(**opts)

class _fi(object):
    """Information of each field"""
    __slots__ = ('label', 'cpath', 'values', 'tooltip',
                 'restartneeded', 'globalonly')

    def __init__(self, label, cpath, values, tooltip,
                 restartneeded=False, globalonly=False):
        self.label = label
        self.cpath = cpath
        self.values = values
        self.tooltip = tooltip
        self.restartneeded = restartneeded
        self.globalonly = globalonly

INFO = (
({'name': 'general', 'label': 'TortoiseHg', 'icon': 'thg_logo'}, (
    _fi(_('UI Language'), 'tortoisehg.ui.language',
        (genDeferredCombo, i18n.availablelanguages),
        _('Specify your preferred user interface language (restart needed)'),
        restartneeded=True, globalonly=True),
    _fi(_('Three-way Merge Tool'), 'ui.merge',
        (genDeferredCombo, findMergeTools),
        _('Graphical merge program for resolving merge conflicts.  If left '
        'unspecified, Mercurial will use the first applicable tool it finds '
        'on your system or use its internal merge tool that leaves conflict '
        'markers in place.  Chose internal:merge to force conflict markers ,'
        'internal:prompt to always select local or other, or internal:dump '
        'to leave files in the working directory for manual merging')),
    _fi(_('Visual Diff Tool'), 'tortoisehg.vdiff',
        (genDeferredCombo, findDiffTools),
        _('Specify visual diff tool, as described in the [merge-tools] '
          'section of your Mercurial configuration files.  If left '
          'unspecified, TortoiseHg will use the selected merge tool. '
          'Failing that it uses the first applicable tool it finds.')),
    _fi(_('Visual Editor'), 'tortoisehg.editor', genEditCombo,
        _('Specify the visual editor used to view files.  Format:<br>'
          'myeditor -flags [$FILE --num=$LINENUM][--search $SEARCH]<br><br>'
          'See <a href="%s">OpenAtLine</a>'
          % 'http://bitbucket.org/tortoisehg/thg/wiki/OpenAtLine')),
    _fi(_('Shell'), 'tortoisehg.shell', genEditCombo,
        _('Specify your preferred terminal shell application')),
    _fi(_('Immediate Operations'), 'tortoisehg.immediate', genEditCombo,
        _('Space separated list of shell operations you would like '
          'to be performed immediately, without user interaction. '
          'Commands are "add remove revert forget". '
          'Default: None (leave blank)')),
    _fi(_('Poll Frequency'), 'tortoisehg.pollfreq', genIntEditCombo,
        _('The period (in milliseconds) between modification time polling of '
          'key repository files, looking for changes.  Values under '
          '100ms are ignored.  Default: 500')),
    _fi(_('Tab Width'), 'tortoisehg.tabwidth', genIntEditCombo,
        _('Specify the number of spaces that tabs expand to in various '
          'TortoiseHg windows. '
          'Default: 0, Not expanded')),
    _fi(_('Max Diff Size'), 'tortoisehg.maxdiff', genIntEditCombo,
        _('The maximum size file (in KB) that TortoiseHg will '
          'show changes for in the changelog, status, and commit windows. '
          'A value of zero implies no limit.  Default: 1024 (1MB)')),
    _fi(_('Capture stderr'), 'tortoisehg.stderrcapt', genBoolCombo,
        _('Redirect stderr to a buffer which is parsed at the end of '
          'the process for runtime errors. Default: True')),
    _fi(_('Fork GUI'), 'tortoisehg.guifork', genBoolCombo,
        _('When running from the command line, fork a background '
          'process to run graphical dialogs.  Default: True')),
    _fi(_('Full Path Title'), 'tortoisehg.fullpath', genBoolCombo,
        _('Show a full directory path of the repository in the dialog title '
          'instead of just the root directory name.  Default: False')),
    _fi(_('Auto-resolve merges'), 'tortoisehg.autoresolve', genBoolCombo,
        _('Indicates whether TortoiseHg should attempt to automatically '
          'resolve changes from both sides to the same file, and only report '
          'merge conflicts when this is not possible. When False, all files '
          'with changes on both sides of the merge will report as conflicting, '
          'even if the edits are to different parts of the file. In either '
          'case, when conflicts occur, the user will be invited to review and '
          'resolve changes manually. Default: False.')),
    )),

({'name': 'log', 'label': _('Workbench'), 'icon': 'menulog'}, (
    _fi(_('Author Coloring'), 'tortoisehg.authorcolor', genBoolCombo,
        _('Color changesets by author name.  If not enabled, '
          'the changes are colored green for merge, red for '
          'non-trivial parents, black for normal. '
          'Default: False')),
    _fi(_('Task Tabs'), 'tortoisehg.tasktabs', (genDefaultCombo,
         ['east', 'west', 'off']),
        _('Show tabs along the side of the bottom half of each repo '
          'widget allowing one to switch task tabs without using the toolbar. '
          'Default: off')),
    _fi(_('Long Summary'), 'tortoisehg.longsummary', genBoolCombo,
        _('If true, concatenate multiple lines of changeset summary '
          'until they reach 80 characters. '
          'Default: False')),
    _fi(_('Log Batch Size'), 'tortoisehg.graphlimit', genIntEditCombo,
        _('The number of revisions to read and display in the '
          'changelog viewer in a single batch. '
          'Default: 500')),
    _fi(_('Dead Branches'), 'tortoisehg.deadbranch', genEditCombo,
        _('Comma separated list of branch names that should be ignored '
          'when building a list of branch names for a repository. '
          'Default: None (leave blank)')),
    _fi(_('Branch Colors'), 'tortoisehg.branchcolors', genEditCombo,
        _('Space separated list of branch names and colors of the form '
          'branch:#XXXXXX. Spaces and colons in the branch name must be '
          'escaped using a backslash (\\). Likewise some other characters '
          'can be escaped in this way, e.g. \\u0040 will be decoded to the '
          '@ character, and \\n to a linefeed. '
          'Default: None (leave blank)')),
    _fi(_('Hide Tags'), 'tortoisehg.hidetags', genEditCombo,
        _('Space separated list of tags that will not be shown.'
          'Useful example: Specify "qbase qparent qtip" to hide the '
          'standard tags inserted by the Mercurial Queues Extension. '
          'Default: None (leave blank)')),
    _fi(_('After Pull Operation'), 'tortoisehg.postpull', (genDefaultCombo,
        ['none', 'update', 'fetch', 'rebase']),
        _('Operation which is performed directly after a successful pull. '
          'update equates to pull --update, fetch equates to the fetch '
          'extension, rebase equates to pull --rebase.  Default: none')),
    )),

({'name': 'commit', 'label': _('Commit'), 'icon': 'menucommit'}, (
    _fi(_('Username'), 'ui.username', genEditCombo,
        _('Name associated with commits.  The common format is<br>'
          '"Full Name &lt;email@example.com&gt;"')),
    _fi(_('Summary Line Length'), 'tortoisehg.summarylen', genIntEditCombo,
       _('Suggested length of commit message lines. A red vertical '
         'line will mark this length.  CTRL-E will reflow the current '
         'paragraph to the specified line length. Default: 80')),
    _fi(_('Close After Commit'), 'tortoisehg.closeci', genBoolCombo,
        _('Close the commit tool after every successful '
          'commit.  Default: False')),
    _fi(_('Push After Commit'), 'tortoisehg.cipushafter', genEditCombo,
        _('Attempt to push to specified URL or alias after each successful '
          'commit.  Default: No push')),
    _fi(_('Auto Commit List'), 'tortoisehg.autoinc', genEditCombo,
       _('Comma separated list of files that are automatically included '
         'in every commit.  Intended for use only as a repository setting. '
         'Default: None (leave blank)')),
    _fi(_('Auto Exclude List'), 'tortoisehg.ciexclude', genEditCombo,
       _('Comma separated list of files that are automatically unchecked '
         'when the status, and commit dialogs are opened. '
         'Default: None (leave blank)')),
    _fi(_('English Messages'), 'tortoisehg.engmsg', genBoolCombo,
       _('Generate English commit messages even if LANGUAGE or LANG '
         'environment variables are set to a non-English language. '
         'This setting is used by the Merge, Tag and Backout dialogs. '
         'Default: False')),
    )),

({'name': 'web', 'label': _('Web Server'), 'icon': 'proxy'}, (
    _fi(_('Name'), 'web.name', genEditCombo,
        _('Repository name to use in the web interface, and by TortoiseHg '
          'as a shorthand name.  Default is the working directory.')),
    _fi(_('Description'), 'web.description', genEditCombo,
        _("Textual description of the repository's purpose or "
          'contents.')),
    _fi(_('Contact'), 'web.contact', genEditCombo,
        _('Name or email address of the person in charge of the '
          'repository.')),
    _fi(_('Style'), 'web.style', (genDefaultCombo,
        ['paper', 'monoblue', 'coal', 'spartan', 'gitweb', 'old']),
        _('Which template map style to use')),
    _fi(_('Archive Formats'), 'web.allow_archive',
        (genEditCombo, ['bz2', 'gz', 'zip']),
        _('Comma separated list of archive formats allowed for '
          'downloading')),
    _fi(_('Port'), 'web.port', genIntEditCombo, _('Port to listen on')),
    _fi(_('Push Requires SSL'), 'web.push_ssl', genBoolCombo,
        _('Whether to require that inbound pushes be transported '
          'over SSL to prevent password sniffing.')),
    _fi(_('Stripes'), 'web.stripes', genIntEditCombo,
        _('How many lines a "zebra stripe" should span in multiline output. '
          'Default is 1; set to 0 to disable.')),
    _fi(_('Max Files'), 'web.maxfiles', genIntEditCombo,
        _('Maximum number of files to list per changeset. Default: 10')),
    _fi(_('Max Changes'), 'web.maxchanges', genIntEditCombo,
        _('Maximum number of changes to list on the changelog. '
          'Default: 10')),
    _fi(_('Allow Push'), 'web.allow_push', (genEditCombo, ['*']),
        _('Whether to allow pushing to the repository. If empty or not '
          'set, push is not allowed. If the special value "*", any remote '
          'user can push, including unauthenticated users. Otherwise, the '
          'remote user must have been authenticated, and the authenticated '
          'user name must be present in this list (separated by whitespace '
          'or ","). The contents of the allow_push list are examined after '
          'the deny_push list.')),
    _fi(_('Deny Push'), 'web.deny_push', (genEditCombo, ['*']),
        _('Whether to deny pushing to the repository. If empty or not set, '
          'push is not denied. If the special value "*", all remote users '
          'are denied push. Otherwise, unauthenticated users are all '
          'denied, and any authenticated user name present in this list '
          '(separated by whitespace or ",") is also denied. The contents '
          'of the deny_push list are examined before the allow_push list.')),
    _fi(_('Encoding'), 'web.encoding', (genEditCombo, ['UTF-8']),
        _('Character encoding name')),
    )),

({'name': 'proxy', 'label': _('Proxy'), 'icon': QStyle.SP_DriveNetIcon}, (
    _fi(_('Host'), 'http_proxy.host', genEditCombo,
        _('Host name and (optional) port of proxy server, for '
          'example "myproxy:8000"')),
    _fi(_('Bypass List'), 'http_proxy.no', genEditCombo,
        _('Optional. Comma-separated list of host names that '
          'should bypass the proxy')),
    _fi(_('User'), 'http_proxy.user', genEditCombo,
        _('Optional. User name to authenticate with at the proxy server')),
    _fi(_('Password'), 'http_proxy.passwd', genPasswordEntry,
        _('Optional. Password to authenticate with at the proxy server')),
    )),

({'name': 'email', 'label': _('Email'), 'icon': 'mail-forward'}, (
    _fi(_('From'), 'email.from', genEditCombo,
        _('Email address to use in the "From" header and for '
          'the SMTP envelope')),
    _fi(_('To'), 'email.to', genEditCombo,
        _('Comma-separated list of recipient email addresses')),
    _fi(_('Cc'), 'email.cc', genEditCombo,
        _('Comma-separated list of carbon copy recipient email addresses')),
    _fi(_('Bcc'), 'email.bcc', genEditCombo,
        _('Comma-separated list of blind carbon copy recipient '
          'email addresses')),
    _fi(_('method'), 'email.method', (genEditCombo, ['smtp']),
        _('Optional. Method to use to send email messages. If value is '
          '"smtp" (default), use SMTP (configured below).  Otherwise, use as '
          'name of program to run that acts like sendmail (takes "-f" option '
          'for sender, list of recipients on command line, message on stdin). '
          'Normally, setting this to "sendmail" or "/usr/sbin/sendmail" '
          'is enough to use sendmail to send messages.')),
    _fi(_('SMTP Host'), 'smtp.host', genEditCombo,
        _('Host name of mail server')),
    _fi(_('SMTP Port'), 'smtp.port', genIntEditCombo,
        _('Port to connect to on mail server. '
          'Default: 25')),
    _fi(_('SMTP TLS'), 'smtp.tls', genBoolCombo,
        _('Connect to mail server using TLS. '
          'Default: False')),
    _fi(_('SMTP Username'), 'smtp.username', genEditCombo,
        _('Username to authenticate to mail server with')),
    _fi(_('SMTP Password'), 'smtp.password', genPasswordEntry,
        _('Password to authenticate to mail server with')),
    _fi(_('Local Hostname'), 'smtp.local_hostname', genEditCombo,
        _('Hostname the sender can use to identify itself to the '
          'mail server.')),
    )),

({'name': 'diff', 'label': _('Diff'),
  'icon': QStyle.SP_FileDialogContentsView}, (
    _fi(_('Patch EOL'), 'patch.eol', (genDefaultCombo,
        ['auto', 'strict', 'crlf', 'lf']),
        _('Normalize file line endings during and after patch to lf or '
          'crlf.  Strict does no normalization.  Auto does per-file '
          'detection, and is the recommended setting. '
          'Default: strict')),
    _fi(_('Git Format'), 'diff.git', genBoolCombo,
        _('Use git extended diff header format. '
          'Default: False')),
    _fi(_('MQ Git Format'), 'mq.git', (genDefaultCombo,
        ['auto', 'keep', 'yes', 'no']),
     _("If set to 'keep', mq will obey the [diff] section configuration while"
       " preserving existing git patches upon qrefresh. If set to 'yes' or"
       " 'no', mq will override the [diff] section and always generate git or"
       " regular patches, possibly losing data in the second case.")),
    _fi(_('No Dates'), 'diff.nodates', genBoolCombo,
        _('Do not include modification dates in diff headers. '
          'Default: False')),
    _fi(_('Show Function'), 'diff.showfunc', genBoolCombo,
        _('Show which function each change is in. '
          'Default: False')),
    _fi(_('Ignore White Space'), 'diff.ignorews', genBoolCombo,
        _('Ignore white space when comparing lines. '
          'Default: False')),
    _fi(_('Ignore WS Amount'), 'diff.ignorewsamount', genBoolCombo,
        _('Ignore changes in the amount of white space. '
          'Default: False')),
    _fi(_('Ignore Blank Lines'), 'diff.ignoreblanklines', genBoolCombo,
        _('Ignore changes whose lines are all blank. '
          'Default: False')),
    )),

({'name': 'fonts', 'label': _('Fonts'), 'icon': 'preferences-desktop-font'}, (
    _fi(_('Message Font'), 'tortoisehg.fontcomment', genFontEdit,
        _('Font used to display commit messages. Default: monospace 10'),
       globalonly=True),
    _fi(_('Diff Font'), 'tortoisehg.fontdiff', genFontEdit,
        _('Font used to display text differences. Default: monospace 10'),
       globalonly=True),
    _fi(_('List Font'), 'tortoisehg.fontlist', genFontEdit,
        _('Font used to display file lists. Default: sans 9'),
       globalonly=True),
    _fi(_('ChangeLog Font'), 'tortoisehg.fontlog', genFontEdit,
        _('Font used to display changelog data. Default: monospace 10'),
       globalonly=True),
    _fi(_('Output Font'), 'tortoisehg.fontoutputlog', genFontEdit,
        _('Font used to display output messages. Default: sans 8'),
       globalonly=True),
    )),

({'name': 'extensions', 'label': _('Extensions'), 'icon': 'hg-extensions'}, (
    )),

({'name': 'issue', 'label': _('Issue Tracking'), 'icon': 'edit-file'}, (
    _fi(_('Issue Regex'), 'tortoisehg.issue.regex', genEditCombo,
        _('Defines the regex to match when picking up issue numbers.')),
    _fi(_('Issue Link'), 'tortoisehg.issue.link', genEditCombo,
        _('Defines the command to run when an issue number is recognized. '
          'You may include groups in issue.regex, and corresponding {n} '
          'tokens in issue.link (where n is a non-negative integer). '
          '{0} refers to the entire string matched by issue.regex, '
          'while {1} refers to the first group and so on. If no {n} tokens'
          'are found in issue.link, the entire matched string is appended '
          'instead.')),
    )),

({'name': 'reviewboard', 'label': _('Review Board'), 'icon': 'reviewboard'}, (
    _fi(_('Server'), 'reviewboard.server', genEditCombo,
        _('Path to review board '
          'example "http://demo.reviewboard.org"')),
    _fi(_('User'), 'reviewboard.user', genEditCombo,
        _('User name to authenticate with review board')),
    _fi(_('Password'), 'reviewboard.password', genPasswordEntry,
        _('Password to authenticate with review board')),
    _fi(_('Server Repository ID'), 'reviewboard.repoid', genEditCombo,
        _('The default repository id for this repo on the review board server')),
    _fi(_('Target Groups'), 'reviewboard.target_groups', genEditCombo,
        _('A comma separated list of target groups')),
    _fi(_('Target People'), 'reviewboard.target_people', genEditCombo,
        _('A comma separated list of target people')),
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
        self.setWindowIcon(qtlib.geticon('settings_repo'))

        if not hasattr(wconfig.config(), 'write'):
            qtlib.ErrorMsgBox(_('Iniparse package not found'),
                         _("Can't change settings without iniparse package - "
                           'view is readonly.'), parent=self)
            print 'Please install http://code.google.com/p/iniparse/'

        layout = QVBoxLayout()
        self.setLayout(layout)

        s = QSettings()
        self.settings = s
        self.restoreGeometry(s.value('settings/geom').toByteArray())

        def username():
            name = util.username()
            if name:
                return hglib.tounicode(name)
            name = os.environ.get('USERNAME')
            if name:
                return hglib.tounicode(name)
            return _('User')

        self.conftabs = QTabWidget()
        layout.addWidget(self.conftabs)
        utab = SettingsForm(rcpath=util.user_rcpath(), focus=focus)
        self.conftabs.addTab(utab, qtlib.geticon('settings_user'),
                             _("%s's global settings") % username())
        utab.restartRequested.connect(self._pushRestartRequest)

        try:
            if root is None:
                root = paths.find_root()
            if root:
                repo = thgrepo.repository(ui.ui(), root)
            else:
                repo = None
        except error.RepoError:
            repo = None
            if configrepo:
                uroot = hglib.tounicode(root)
                qtlib.ErrorMsgBox(_('No repository found'),
                                  _('no repo at ') + uroot, parent=self)

        if repo:
            reporcpath = os.sep.join([repo.root, '.hg', 'hgrc'])
            rtab = SettingsForm(rcpath=reporcpath, focus=focus)
            self.conftabs.addTab(rtab, qtlib.geticon('settings_repo'),
                                 _('%s repository settings') % repo.displayname)
            rtab.restartRequested.connect(self._pushRestartRequest)

        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Ok|BB.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)
        self.bb = bb

        self._restartreqs = set()

        self.conftabs.setCurrentIndex(configrepo and CONF_REPO or CONF_GLOBAL)

    def isDirty(self):
        return util.any(self.conftabs.widget(i).isDirty()
                        for i in xrange(self.conftabs.count()))

    @pyqtSlot(unicode)
    def _pushRestartRequest(self, key):
        self._restartreqs.add(unicode(key))

    def applyChanges(self):
        for i in xrange(self.conftabs.count()):
            self.conftabs.widget(i).applyChanges()
        if self._restartreqs:
            qtlib.InfoMsgBox(_('Settings'),
                             _('Restart all TortoiseHg applications '
                               'for the following changes to take effect:'),
                             ', '.join(sorted(self._restartreqs)))
            self._restartreqs.clear()

    def canExit(self):
        if self.isDirty():
            ret = qtlib.CustomPrompt(_('Confirm Exit'),
                            _('Apply changes before exit?'), self,
                            (_('&Yes'), _('&No (discard changes)'),
                         _  ('Cancel')), default=2, esc=2).run()
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

    restartRequested = pyqtSignal(unicode)

    def __init__(self, rcpath, focus=None, parent=None):
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
                    _('Save changes before editing?'), self,
                    (_('&Save'), _('&Discard'), _('Cancel')),
                    default=2, esc=2).run()
            if ret == 0:
                self.applyChanges()
            elif ret == 2:
                return
        if qscilib.fileEditor(self.fn, foldable=True) == QDialog.Accepted:
            self.refresh()

    def refresh(self, *args):
        # refresh config values
        self.ini = self.loadIniFile(self.rcpath)
        self.readonly = not (hasattr(self.ini, 'write')
                                and os.access(self.fn, os.W_OK))
        self.stack.setDisabled(self.readonly)
        self.fnedit.setText(hglib.tounicode(self.fn))
        for name, info, widgets in self.pages.values():
            if name == 'extensions':
                extsmentioned = False
                for row, w in enumerate(widgets):
                    key = w.opts['label']
                    for fullkey in (key, 'hgext.%s' % key, 'hgext/%s' % key):
                        val = self.readCPath('extensions.' + fullkey)
                        if val != None:
                            break
                    if val == None:
                        curvalue = False
                    elif len(val) and val[0] == '!':
                        curvalue = False
                        extsmentioned = True
                    else:
                        curvalue = True
                        extsmentioned = True
                    w.setValue(curvalue)
                    if val == None:
                        w.opts['cpath'] = 'extensions.' + key
                    else:
                        w.opts['cpath'] = 'extensions.' + fullkey
                if not extsmentioned:
                    # make sure widgets are shown properly,
                    # even when no extensions mentioned in the config file
                    self.validateextensions()
            else:
                for row, e in enumerate(info):
                    curvalue = self.readCPath(e.cpath)
                    widgets[row].setValue(curvalue)

    def isDirty(self):
        if self.readonly:
            return False
        for name, info, widgets in self.pages.values():
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
            for n, e in enumerate(info):
                if e.cpath == focusfield:
                    self.pageList.setCurrentRow(i)
                    QTimer.singleShot(0, lambda:
                            self.pages[meta['name']][2][n].setFocus())
                    return

    def fillFrame(self, info):
        widgets = []
        frame = QFrame()
        form = QFormLayout()
        frame.setLayout(form)
        self.stack.addWidget(frame)

        for e in info:
            opts = {'label': e.label, 'cpath': e.cpath, 'tooltip': e.tooltip,
                    'settings':self.settings}
            if isinstance(e.values, tuple):
                func = e.values[0]
                w = func(opts, e.values[1])
            else:
                func = e.values
                w = func(opts)
            w.installEventFilter(self)
            if e.globalonly:
                w.setEnabled(self.rcpath == util.user_rcpath())
            lbl = QLabel(e.label)
            lbl.installEventFilter(self)
            lbl.setToolTip(e.tooltip)
            form.addRow(lbl, w)
            widgets.append(w)
        return widgets

    def fillExtensionsFrame(self):
        widgets = []
        frame = QFrame()
        grid = QGridLayout()
        frame.setLayout(grid)
        self.stack.addWidget(frame)
        allexts = hglib.allextensions()
        allextslist = list(allexts)
        MAXCOLUMNS = 3
        maxrows = (len(allextslist) + MAXCOLUMNS - 1) / MAXCOLUMNS
        i = 0
        extsinfo = ()
        for i, name in enumerate(sorted(allexts)):
            tt = hglib.tounicode(allexts[name])
            opts = {'label':name, 'cpath':'extensions.' + name, 'tooltip':tt,
                    'valfunc':self.validateextensions}
            w = genCheckBox(opts)
            w.installEventFilter(self)
            row, col = i / maxrows, i % maxrows
            grid.addWidget(w, col, row)
            widgets.append(w)
        return extsinfo, widgets

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Enter, QEvent.FocusIn):
            self.desctext.setHtml(obj.toolTip())
        if event.type() == QEvent.ToolTip:
            return True  # tooltip is shown in self.desctext
        return False

    def addPage(self, name):
        for data in INFO:
            if name == data[0]['name']:
                meta, info = data
                break
        if name == 'extensions':
            extsinfo, widgets = self.fillExtensionsFrame()
            self.pages[name] = name, extsinfo, widgets
        else:
            widgets = self.fillFrame(info)
            self.pages[name] = name, info, widgets

    def readCPath(self, cpath):
        'Retrieve a value from the parsed config file'
        # Presumes single section/key level depth
        section, key = cpath.split('.', 1)
        return self.ini.get(section, key)

    def loadIniFile(self, rcpath):
        for fn in rcpath:
            if os.path.exists(fn):
                break
        else:
            for fn in rcpath:
                # Try to create a file from rcpath
                try:
                    f = open(fn, 'w')
                    f.write('# Generated by TortoiseHg settings dialog\n')
                    f.close()
                    break
                except (IOError, OSError):
                    pass
            else:
                qtlib.WarningMsgBox(_('Unable to create a Mercurial.ini file'),
                       _('Insufficient access rights, reverting to read-only '
                         'mode.'), parent=self)
                from mercurial import config
                self.fn = rcpath[0]
                return config.config()
        self.fn = fn
        return wconfig.readfile(self.fn)

    def recordNewValue(self, cpath, newvalue):
        """Set the given value to ini; returns True if changed"""
        # 'newvalue' is in local encoding
        section, key = cpath.split('.', 1)
        if newvalue == self.ini.get(section, key):
            return False
        if newvalue == None:
            try:
                del self.ini[section][key]
            except KeyError:
                pass
        else:
            self.ini.set(section, key, newvalue)
        return True

    def applyChanges(self):
        if self.readonly:
            return

        for name, info, widgets in self.pages.values():
            if name == 'extensions':
                self.applyChangesForExtensions()
            else:
                for row, e in enumerate(info):
                    newvalue = widgets[row].value()
                    changed = self.recordNewValue(e.cpath, newvalue)
                    if changed and e.restartneeded:
                        self.restartRequested.emit(e.label)

        try:
            wconfig.writefile(self.ini, self.fn)
        except IOError, e:
            qtlib.WarningMsgBox(_('Unable to write configuration file'),
                                str(e), parent=self)

    def applyChangesForExtensions(self):
        emitChanged = False
        section = 'extensions'
        enabledexts = hglib.enabledextensions()
        for chk in self.pages['extensions'][2]:
            if (not emitChanged) and chk.isDirty():
                self.restartRequested.emit(_('Extensions'))
                emitChanged = True
            name = chk.opts['label']
            section, key = chk.opts['cpath'].split('.', 1)
            newvalue = chk.value()
            if newvalue and (name in enabledexts):
                continue    # unchanged
            if newvalue:
                self.ini.set(section, key, '')
            else:
                try:
                    del self.ini[section][key]
                except KeyError:
                    pass

    @pyqtSlot()
    def validateextensions(self):
        section = 'extensions'
        enabledexts = hglib.enabledextensions()
        selectedexts = set(chk.opts['label']
                           for chk in self.pages['extensions'][2]
                           if chk.isChecked())
        invalidexts = hglib.validateextensions(selectedexts)

        def getinival(cpath):
            if section not in self.ini:
                return None
            sect, key = cpath.split('.', 1)
            try:
                return self.ini[sect][key]
            except KeyError:
                pass

        def changable(name, cpath):
            curval = getinival(cpath)
            if curval not in ('', None):
                # enabled or unspecified, official extensions only
                return False
            elif name in enabledexts and curval is None:
                # re-disabling ext is not supported
                return False
            elif name in invalidexts and name not in selectedexts:
                # disallow to enable bad exts, but allow to disable it
                return False
            else:
                return True

        allexts = hglib.allextensions()
        for chk in self.pages['extensions'][2]:
            name = chk.opts['label']
            chk.setEnabled(changable(name, chk.opts['cpath']))
            invalmsg = invalidexts.get(name)
            if invalmsg:
                invalmsg = invalmsg.decode('utf-8')
            chk.setToolTip(invalmsg or hglib.tounicode(allexts[name]))


def run(ui, *pats, **opts):
    return SettingsDialog(opts.get('alias') == 'repoconfig',
                          focus=opts.get('focus'))

# thgconfig.py - Configuration dialog for TortoiseHg and Mercurial
#
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import os
import sys
import re
import urlparse
import threading

from mercurial import hg, ui, util, url, filemerge

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, settings, paths

from tortoisehg.hgtk import dialog, gdialog, gtklib, hgcmd

_unspecstr = _('<unspecified>')
_unspeclocalstr = hglib.fromutf(_unspecstr)

_pwfields = ('http_proxy.passwd', 'smtp.password')

_tortoise_info = (
    (_('Three-way Merge Tool'), 'ui.merge', [],
        _('Graphical merge program for resolving merge conflicts.  If left'
        ' unspecified, Mercurial will use the first applicable tool it finds'
        ' on your system or use its internal merge tool that leaves conflict'
        ' markers in place.  Chose internal:merge to force conflict markers,'
        ' internal:prompt to always select local or other, or internal:dump'
        ' to leave files in the working directory for manual merging')),
    (_('Visual Diff Command'), 'tortoisehg.vdiff', [],
        _('Specify visual diff tool; must be an extdiff command')),
    (_('Skip Diff Window'), 'tortoisehg.vdiffnowin', ['False', 'True'],
        _("Bypass the builtin visual diff dialog and directly use your"
          " visual diff tool's directory diff feature.  Only enable this"
          " feature if you know your diff tool has a valid extdiff"
          " configuration.  Default: False")),
    (_('Visual Editor'), 'tortoisehg.editor', [],
        _('Specify the visual editor used to view files, etc')),
    (_('CLI Editor'), 'ui.editor', [],
        _('The editor to use during a commit and other'
        ' instances where Mercurial needs multiline input from'
        ' the user.  Only used by command line interface commands.')),
    (_('Tab Width'), 'tortoisehg.tabwidth', [],
        _('Specify the number of spaces that tabs expand to in various'
        ' TortoiseHG windows.'
        ' Default: Not expanded')),
    (_('Max Diff Size'), 'tortoisehg.maxdiff', ['1024', '0'],
        _('The maximum size file (in KB) that TortoiseHg will '
        'show changes for in the changelog, status, and commit windows.'
        ' A value of zero implies no limit.  Default: 1024 (1MB)')),
    (_('Bottom Diffs'), 'gtools.diffbottom', ['False', 'True'],
        _('Show the diff panel below the file list in status, shelve, and'
        ' commit dialogs.'
        ' Default: False (show diffs to right of file list)')),
    (_('Capture Stderr'), 'tortoisehg.stderrcapt', ['True', 'False'],
        _('Redirect stderr to a buffer which is parsed at the end of'
        ' the process for runtime errors. Default: True')),
    (_('Fork hgtk'), 'tortoisehg.hgtkfork', ['True', 'False'],
        _('When running hgtk from the command line, fork a background'
        ' process to run graphical dialogs.  Default: True')),
    (_('Full path title'), 'tortoisehg.fullpath', ['False', 'True'],
        _('Show a full directory path of the repository in the dialog title'
        ' instead of just the root directory name.  Default: False')))

_commit_info = (
    (_('Username'), 'ui.username', [],
        _('Name associated with commits')),
    (_('Summary Line Length'), 'tortoisehg.summarylen', ['0', '70'],
       _('Maximum length of the commit message summary line.'
         ' If set, TortoiseHG will issue a warning if the'
         ' summary line is too long or not separated by a'
         ' blank line. Default: 0 (unenforced)')),
    (_('Message Line Length'), 'tortoisehg.messagewrap', ['0', '80'],
       _('Word wrap length of the commit message.  If'
         ' set, the popup menu can be used to format'
         ' the message and a warning will be issued'
         ' if any lines are too long at commit.'
         '  Default: 0 (unenforced)')),
    (_('Push After Commit'), 'tortoisehg.pushafterci', ['False', 'True'],
        _('Attempt to push to default push target after every successful'
          ' commit.  Default: False')),
    (_('Auto Commit List'), 'tortoisehg.autoinc', [],
       _('Comma separated list of files that are automatically included'
         ' in every commit.  Intended for use only as a repository setting.'
         '  Default: None')),
    (_('Auto Exclude List'), 'tortoisehg.ciexclude', [],
       _('Comma separated list of files that are automatically unchecked'
         ' when the status, commit, and shelve dialogs are opened.'
         '  Default: None'))
       )

_log_info = (
    (_('Author Coloring'), 'tortoisehg.authorcolor', ['False', 'True'],
        _('Color changesets by author name.  If not enabled,'
        ' the changes are colored green for merge, red for'
        ' non-trivial parents, black for normal.'
        ' Default: False')),
    (_('Long Summary'), 'tortoisehg.longsummary', ['False', 'True'],
        _('If true, concatenate multiple lines of changeset summary'
        ' until they reach 80 characters.'
        ' Default: False')),
    (_('Log Batch Size'), 'tortoisehg.graphlimit', ['500'],
        _('The number of revisions to read and display in the'
        ' changelog viewer in a single batch.'
        ' Default: 500')),
    (_('Copy Hash'), 'tortoisehg.copyhash', ['False', 'True'],
        _('Allow the changelog viewer to copy the changeset hash'
        ' of the currently selected changeset into the clipboard.'
        ' DEPRECATED. Default: False')),
    (_('Dead Branches'), 'tortoisehg.deadbranch', [],
        _('Comma separated list of branch names that should be ignored'
        ' when building a list of branch names for a repository.'
        ' Default: None')),
    (_('Branch Colors'), 'tortoisehg.branchcolors', [],
        _('Space separated list of branch names and colors of the form'
        ' branch:#XXXXXX. Spaces and colons in the branch name must be'
        ' escaped using a backslash (\\). Likewise some other characters'
        ' can be escaped in this way, e.g. \\u0040 will be decoded to the'
        ' @ character, and \\n to a linefeed.'
        ' Default: None')),
    (_('Hide Tags'), 'tortoisehg.hidetags', [],
        _('Space separated list of tags that will not be shown.'
          ' Useful example: Specify "qbase qparent qtip" to hide the'
          ' standard tags inserted by the Mercurial Queues Extension.' 
        ' Default: None')),
    (_('Use Expander'), 'tortoisehg.changeset-expander', ['False', 'True'],
        _('Show changeset details with an expander')),
        )

_paths_info = (
    (_('After pull operation'), 'tortoisehg.postpull',
        ['none', 'update', 'fetch', 'rebase'],
        _('Operation which is performed directly after a successful pull.'
          ' update equates to pull --update, fetch equates to the fetch'
          ' extension, rebase equates to pull --rebase.  Default: none')),)

_web_info = (
    (_('Name'), 'web.name', ['unknown'],
        _('Repository name to use in the web interface.'
        ' Default is the working directory.')),
    (_('Description'), 'web.description', ['unknown'],
        _("Textual description of the repository's purpose or"
        " contents.")),
    (_('Contact'), 'web.contact', ['unknown'],
        _('Name or email address of the person in charge of the'
        ' repository.')),
    (_('Style'), 'web.style',
        ['paper', 'monoblue', 'coal', 'spartan', 'gitweb', 'old'],
        _('Which template map style to use')),
    (_('Archive Formats'), 'web.allow_archive', ['bz2', 'gz', 'zip'],
        _('Comma separated list of archive formats allowed for'
        ' downloading')),
    (_('Port'), 'web.port', ['8000'], _('Port to listen on')),
    (_('Push Requires SSL'), 'web.push_ssl', ['True', 'False'],
        _('Whether to require that inbound pushes be transported'
        ' over SSL to prevent password sniffing.')),
    (_('Stripes'), 'web.stripes', ['1', '0'],
        _('How many lines a "zebra stripe" should span in multiline output.'
        ' Default is 1; set to 0 to disable.')),
    (_('Max Files'), 'web.maxfiles', ['10'],
        _('Maximum number of files to list per changeset.')),
    (_('Max Changes'), 'web.maxchanges', ['10'],
        _('Maximum number of changes to list on the changelog.')),
    (_('Allow Push'), 'web.allow_push', ['*'],
        _('Whether to allow pushing to the repository. If empty or not'
        ' set, push is not allowed. If the special value "*", any remote'
        ' user can push, including unauthenticated users. Otherwise, the'
        ' remote user must have been authenticated, and the authenticated'
        ' user name must be present in this list (separated by whitespace'
        ' or ","). The contents of the allow_push list are examined after'
        ' the deny_push list.')),
    (_('Deny Push'), 'web.deny_push', ['*'],
        _('Whether to deny pushing to the repository. If empty or not set,'
        ' push is not denied. If the special value "*", all remote users'
        ' are denied push. Otherwise, unauthenticated users are all'
        ' denied, and any authenticated user name present in this list'
        ' (separated by whitespace or ",") is also denied. The contents'
        ' of the deny_push list are examined before the allow_push list.')),
    (_('Encoding'), 'web.encoding', ['UTF-8'],
        _('Character encoding name')))

_proxy_info = (
    (_('Host'), 'http_proxy.host', [],
        _('Host name and (optional) port of proxy server, for'
        ' example "myproxy:8000"')),
    (_('Bypass List'), 'http_proxy.no', [],
        _('Optional. Comma-separated list of host names that'
        ' should bypass the proxy')),
    (_('User'), 'http_proxy.user', [],
        _('Optional. User name to authenticate with at the'
        ' proxy server')),
    (_('Password'), 'http_proxy.passwd', [],
        _('Optional. Password to authenticate with at the'
        ' proxy server')))

_email_info = (
    (_('From'), 'email.from', [],
        _('Email address to use in the "From" header and for the SMTP envelope')),
    (_('To'), 'email.to', [],
        _('Comma-separated list of recipient email addresses')),
    (_('Cc'), 'email.cc', [],
        _('Comma-separated list of carbon copy recipient email'
        ' addresses')),
    (_('Bcc'), 'email.bcc', [],
        _('Comma-separated list of blind carbon copy recipient'
        ' email addresses')),
    (_('method'), 'email.method', ['smtp'],
_('Optional. Method to use to send email messages. If value is "smtp" (default),'
' use SMTP (configured below).  Otherwise, use as name of program to run that'
' acts like sendmail (takes "-f" option for sender, list of recipients on'
' command line, message on stdin). Normally, setting this to "sendmail" or'
' "/usr/sbin/sendmail" is enough to use sendmail to send messages.')),
    (_('SMTP Host'), 'smtp.host', [], _('Host name of mail server')),
    (_('SMTP Port'), 'smtp.port', ['25'],
        _('Port to connect to on mail server.'
        ' Default: 25')),
    (_('SMTP TLS'), 'smtp.tls', ['False', 'True'],
        _('Connect to mail server using TLS.'
        ' Default: False')),
    (_('SMTP Username'), 'smtp.username', [],
        _('Username to authenticate to mail server with')),
    (_('SMTP Password'), 'smtp.password', [],
        _('Password to authenticate to mail server with')),
    (_('Local Hostname'), 'smtp.local_hostname', [],
        _('Hostname the sender can use to identify itself to the mail server.')))

_diff_info = (
    (_('Patch EOL'), 'patch.eol', ['strict', 'crlf', 'lf'],
        _('Normalize file line endings during and after patch to lf or'
          ' crlf.  Strict does no normalization.'
        ' Default: strict')),
    (_('Git Format'), 'diff.git', ['False', 'True'],
        _('Use git extended diff header format.'
        ' Default: False')),
    (_('No Dates'), 'diff.nodates', ['False', 'True'],
        _('Do not include modification dates in diff headers.'
        ' Default: False')),
    (_('Show Function'), 'diff.showfunc', ['False', 'True'],
        _('Show which function each change is in.'
        ' Default: False')),
    (_('Ignore White Space'), 'diff.ignorews', ['False', 'True'],
        _('Ignore white space when comparing lines.'
        ' Default: False')),
    (_('Ignore WS Amount'), 'diff.ignorewsamount', ['False', 'True'],
        _('Ignore changes in the amount of white space.'
        ' Default: False')),
    (_('Ignore Blank Lines'), 'diff.ignoreblanklines', ['False', 'True'],
        _('Ignore changes whose lines are all blank.'
        ' Default: False')))

class PathEditDialog(gtk.Dialog):
    _protocols = (('ssh', _('ssh')), ('http', _('http')),
                  ('https', _('https')), ('local', _('local')))

    def __init__(self, path, alias, list):
        gtk.Dialog.__init__(self, parent=None, flags=gtk.DIALOG_MODAL,
                          buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK,
                              gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
        gtklib.set_tortoise_keys(self)
        self.connect('response', self.response)
        self.connect('key-press-event', self.key_press)
        self.set_title(_('Edit remote repository path'))
        self.set_has_separator(False)
        self.set_resizable(False)
        self.newpath, self.newalias = None, None
        self.list = list

        self.entries = {}
        # Tuple: (internal name, translated name)
        for name in (('URL', _('URL')), ('Port', _('Port')),
                     ('Folder', _('Folder')), ('Host', _('Host')),
                     ('User', _('User')), ('Password', _('Password')),
                     ('Alias', _('Alias'))):
            entry = gtk.Entry()
            entry.set_alignment(0)
            label = gtk.Label(name[1])
            label.set_alignment(1, 0.5)
            self.entries[name[0]] = [entry, label, None]

        # persistent settings
        self.settings = settings.Settings('pathedit')

        # configure individual widgets
        self.entries['Alias'][0].set_width_chars(18)
        self.entries['URL'][0].set_width_chars(60)
        self.entries['Port'][0].set_width_chars(8)
        self.entries['User'][0].set_width_chars(18)
        self.entries['Password'][0].set_width_chars(24)
        self.entries['Password'][0].set_visibility(False)

        # table for main entries
        toptable = gtklib.LayoutTable()
        self.vbox.pack_start(toptable, False, False, 2)

        ## alias (and 'Browse...' button)
        browse = gtk.Button(_('Browse...'))
        browse.connect('clicked', self.browse_clicked)
        ealias = self.entries['Alias']
        toptable.add_row(ealias[1], ealias[0], None, browse, expand=0)

        ## final URL
        eurl = self.entries['URL']
        toptable.add_row(eurl[1], eurl[0], padding=False)

        self.expander = expander = gtk.Expander(_('URL Details'))
        self.vbox.pack_start(expander, True, True, 2)

        # table for separated entries
        entrytable = gtklib.LayoutTable()
        expander.add(entrytable)

        ## path type
        self.protocolcombo = gtk.combo_box_new_text()
        for name, label in self._protocols:
            self.protocolcombo.append_text(label)
        toptable.add_row(_('Type'), self.protocolcombo)

        ## host & port
        ehost, eport = self.entries['Host'], self.entries['Port']
        entrytable.add_row(ehost[1], ehost[0], 8, eport[1], eport[0])

        ## folder
        efolder = self.entries['Folder']
        entrytable.add_row(efolder[1], efolder[0], padding=False)

        ## username & password
        euser, epasswd = self.entries['User'], self.entries['Password']
        entrytable.add_row(euser[1], euser[0], 8, epasswd[1], epasswd[0])

        # layout group
        group = gtklib.LayoutGroup()
        group.add(toptable, entrytable)

        # prepare to show
        self.load_settings()
        self.setentries(path, alias)
        self.sethandlers()
        self.lastproto = None
        self.update_sensitive()
        self.show_all()

    def protocolindex(self, pname):
        for (i, (name, label)) in enumerate(self._protocols):
            if name == pname:
                return i
        return None

    def protocolname(self, plabel):
        for (name, label) in self._protocols:
            if label == plabel:
                return name
        return None

    def sethandlers(self, enable=True):
        # protocol combobox
        if enable:
            self.pcombo_hid = self.protocolcombo.connect('changed', self.changed)
        else:
            h = self.pcombo_hid
            if h and self.protocolcombo.handler_is_connected(h):
                self.protocolcombo.disconnect(h)

        # other entries
        for n, (e, l, h) in self.entries.iteritems():
            if enable:
                handler = (n == 'URL' and self.changedurl or self.changed)
                self.entries[n][2] = e.connect('changed', handler)
            else:
                if e.handler_is_connected(h):
                    e.disconnect(h)

    def urlparse(self, path):
        m = re.match(r'^ssh://(([^@]+)@)?([^:/]+)(:(\d+))?(/(.*))?$', path)
        if m:
            user = m.group(2)
            host = m.group(3)
            port = m.group(5)
            folder = m.group(7) or "."
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

    def setentries(self, path, alias=None):
        if alias == None:
            alias = self.entries['Alias'][0].get_text()

        user, host, port, folder, pw, scheme = self.urlparse(path)

        self.entries['Alias'][0].set_text(alias)
        if scheme == 'local':
            self.entries['URL'][0].set_text(path)
        else:
            self.entries['URL'][0].set_text(url.hidepassword(path))
        self.entries['User'][0].set_text(user or '')
        self.entries['Host'][0].set_text(host or '')
        self.entries['Port'][0].set_text(port or '')
        self.entries['Folder'][0].set_text(folder or '')
        self.entries['Password'][0].set_text(pw or '')

        self.protocolcombo.set_active(self.protocolindex(scheme) or 0)

    def update_sensitive(self):
        proto = self.protocolname(self.protocolcombo.get_active_text())
        if proto == self.lastproto:
            return
        self.lastproto = proto
        if proto == 'local':
            for n in ('User', 'Password', 'Port', 'Host'):
                self.entries[n][0].set_sensitive(False)
                self.entries[n][1].set_sensitive(False)
        elif proto == 'ssh':
            for n in ('User', 'Port', 'Host'):
                self.entries[n][0].set_sensitive(True)
                self.entries[n][1].set_sensitive(True)
            self.entries['Password'][0].set_sensitive(False)
            self.entries['Password'][1].set_sensitive(False)
        else:
            for n in ('User', 'Password', 'Port', 'Host'):
                self.entries[n][0].set_sensitive(True)
                self.entries[n][1].set_sensitive(True)

    def load_settings(self):
        expanded = self.settings.get_value('expanded', False, True)
        self.expander.set_property('expanded', expanded)

    def store_settings(self):
        expanded = self.expander.get_property('expanded')
        self.settings.set_value('expanded', expanded)
        self.settings.write()

    def browse_clicked(self, button):
        if self.protocolname(self.protocolcombo.get_active_text()) == 'local':
            initial = self.entries['URL'][0].get_text()
        else:
            initial = None
        path = gtklib.NativeFolderSelectDialog(initial=initial,
                          title=_('Select Local Folder')).run()
        if path:
            self.entries['URL'][0].set_text(path)

    def changed(self, combo):
        newurl = self.buildurl()
        self.sethandlers(False)
        self.entries['URL'][0].set_text(url.hidepassword(newurl))
        self.sethandlers(True)
        self.update_sensitive()

    def changedurl(self, combo):
        self.sethandlers(False)
        self.setentries(self.entries['URL'][0].get_text())
        self.sethandlers(True)
        self.update_sensitive()

    def response(self, widget, response_id):
        if response_id != gtk.RESPONSE_OK:
            self.store_settings()
            self.destroy()
            return
        aliasinput = self.entries['Alias'][0]
        newalias = aliasinput.get_text()
        if newalias == '':
            ret = dialog.error_dialog(self, _('Alias name is empty'),
                    _('Please enter alias name'))
            aliasinput.grab_focus()
            return
        if newalias in self.list:
            ret = gdialog.Confirm(_('Confirm Overwrite'), [], self,
                   _("Overwrite existing '%s' path?") % newalias).run()
            if ret != gtk.RESPONSE_YES:
                return
        self.newpath = self.buildurl()
        self.newalias = newalias
        self.store_settings()
        self.destroy()

    def key_press(self, widget, event):
        if event.keyval in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            self.response(widget, gtk.RESPONSE_OK)

    def buildurl(self):
        proto = self.protocolname(self.protocolcombo.get_active_text())
        host = self.entries['Host'][0].get_text()
        port = self.entries['Port'][0].get_text()
        folder = self.entries['Folder'][0].get_text()
        user = self.entries['User'][0].get_text()
        pwd = self.entries['Password'][0].get_text()
        if proto == 'ssh':
            ret = 'ssh://'
            if user:
                ret += user + '@'
            ret += host
            if port:
                ret += ':' + port
            ret += '/' + folder
        elif proto == 'local':
            ret = folder
        else:
            ret = proto + '://'
            netloc = url.netlocunsplit(host, port, user, pwd)
            ret += netloc + '/' + folder
        return ret

class ConfigDialog(gtk.Dialog):
    def __init__(self, configrepo=False):
        """ Initialize the Dialog. """
        gtk.Dialog.__init__(self, parent=None, flags=0,
                            buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK,
                                     gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                     gtk.STOCK_APPLY, gtk.RESPONSE_APPLY))
        gtklib.set_tortoise_keys(self)
        self._btn_apply = self.action_area.get_children()[0]
        self.set_has_separator(False)

        self.ui = ui.ui()
        try:
            root = paths.find_root()
            if root:
                repo = hg.repository(self.ui, root)
                name = self.get_reponame(repo)
                self.ui = repo.ui
            else:
                repo = None
            self.root = root
        except hglib.RepoError:
            repo = None
            if configrepo:
                dialog.error_dialog(self, _('No repository found'),
                             _('no repo at ') + root)
                self.destroy()
                return

        try:
            import iniparse
            iniparse.INIConfig
            self.readonly = False
        except ImportError:
            dialog.error_dialog(self, _('Iniparse package not found'),
                         _('Please install iniparse package\n'
                           'Settings are only shown, no changing is possible'))
            print 'Please install http://code.google.com/p/iniparse/'
            self.readonly = True

        # Catch close events
        self.connect('response', self.should_live)
        self.connect('thg-accept', self.thgaccept)
        self.connect('delete-event', self.delete_event)

        combo = gtk.combo_box_new_text()
        combo.append_text(_('User global settings'))
        if repo:
            combo.append_text(_('%s repository settings') % hglib.toutf(name))
        combo.connect('changed', self.fileselect)

        hbox = gtk.HBox()
        hbox.pack_start(combo, False, False, 2)
        edit = gtk.Button(_('Edit File'))
        hbox.pack_start(edit, False, False, 2)
        edit.connect('clicked', self.edit_clicked)
        self.vbox.pack_start(hbox, False, False, 4)

        # Create a new notebook, place the position of the tabs
        self.notebook = notebook = gtk.Notebook()
        notebook.set_tab_pos(gtk.POS_TOP)
        self.vbox.pack_start(notebook, True, True)
        notebook.show()
        self.show_tabs = True
        self.show_border = True

        self.dirty = False
        self.pages = []
        self.tooltips = gtk.Tooltips()
        self.history = settings.Settings('thgconfig')

        # add spell ckeck entry if spell check is supported
        tortoise_info = _tortoise_info
        if gtklib.hasspellcheck():
            tortoise_info += ((
                _('Spell Check Language'), 'tortoisehg.spellcheck', [],
                _('Default language for spell check. '
                  'System language is used if not specified. '
                  'Examples: en, en_GB, en_US')),)

        # create pages for each section of configuration file
        self.tortoise_frame = self.add_page(notebook, 'TortoiseHG')
        self.fill_frame(self.tortoise_frame, tortoise_info)

        self.commit_frame = self.add_page(notebook, _('Commit'))
        self.fill_frame(self.commit_frame, _commit_info)

        self.log_frame = self.add_page(notebook, _('Changelog'))
        self.fill_frame(self.log_frame, _log_info)

        self.paths_frame = self.add_page(notebook, _('Sync'))
        vbox = self.fill_frame(self.paths_frame, _paths_info)
        self.fill_path_frame(vbox)

        self.web_frame = self.add_page(notebook, _('Web'))
        self.fill_frame(self.web_frame, _web_info)

        self.proxy_frame = self.add_page(notebook, _('Proxy'))
        self.fill_frame(self.proxy_frame, _proxy_info)

        self.email_frame = self.add_page(notebook, _('Email'))
        self.fill_frame(self.email_frame, _email_info)

        self.diff_frame = self.add_page(notebook, _('Diff'))
        self.fill_frame(self.diff_frame, _diff_info)

        self.configrepo = configrepo

        # Force dialog into clean state in the beginning
        self._btn_apply.set_sensitive(False)
        self.dirty = False
        combo.set_active(configrepo and 1 or 0)

    def fileselect(self, combo):
        'select another hgrc file'
        if self.dirty:
            ret = gdialog.Confirm(_('Unapplied changes'), [], self,
                   _('Lose changes and switch files?.')).run()
            if ret != gtk.RESPONSE_YES:
               return
        self.configrepo = combo.get_active() and True or False
        self.refresh()

    def get_reponame(self, repo):
        if repo.ui.config('tortoisehg', 'fullpath', False):
            name = repo.root
        else:
            name = repo.ui.config('web', 'name') \
                        or os.path.basename(repo.root)
        return hglib.toutf(name)

    def refresh(self):
        if self.configrepo:
            repo = hg.repository(ui.ui(), self.root)
            name = self.get_reponame(repo)
            self.rcpath = [os.sep.join([repo.root, '.hg', 'hgrc'])]
            self.set_title(_('TortoiseHg Configure Repository - ') + hglib.toutf(name))
            gtklib.set_tortoise_icon(self, 'settings_repo.ico')
        else:
            self.rcpath = util.user_rcpath()
            self.set_title(_('TortoiseHg Configure User-Global Settings'))
            gtklib.set_tortoise_icon(self, 'settings_user.ico')
        self.ini = self.load_config(self.rcpath)
        self.refresh_vlist()
        self.pathdata.clear()
        if 'paths' in self.ini:
            for name in self.ini['paths']:
                path = self.ini['paths'][name]
                safepath = hglib.toutf(url.hidepassword(path))
                self.pathdata.append([hglib.toutf(name), safepath,
                    hglib.toutf(path)])
        self.refresh_path_list()
        self._btn_apply.set_sensitive(False)
        self.dirty = False

    def edit_clicked(self, button):
        def doedit():
            util.system("%s \"%s\"" % (editor, self.fn))
        # reload configs, in case they have been written since opened
        if self.configrepo:
            repo = hg.repository(ui.ui(), self.root)
            u = repo.ui
        else:
            u = ui.ui()
        editor = (u.config('tortoisehg', 'editor') or
                u.config('gtools', 'editor') or
                os.environ.get('HGEDITOR') or
                u.config('ui', 'editor') or
                os.environ.get('EDITOR', 'vi'))
        if os.path.basename(editor) in ('vi', 'vim', 'hgeditor'):
            gdialog.Prompt(_('No visual editor configured'),
                   _('Please configure a visual editor.'), self).run()
            self.focus_field('tortoisehg.editor')
            return True
        thread = threading.Thread(target=doedit, name='edit config')
        thread.setDaemon(True)
        thread.start()
        return True

    def delete_event(self, dlg, event):
        return True

    def thgaccept(self, dlg):
        self.response(gtk.RESPONSE_OK)

    def should_live(self, dialog=None, resp=None):
        if resp == gtk.RESPONSE_APPLY:
            self._apply_clicked()
            self.emit_stop_by_name('response')
            return True
        elif resp == gtk.RESPONSE_CANCEL:
            return False
        if self.dirty and not self.readonly:
            if resp == gtk.RESPONSE_OK:
                ret = 0
            else:
                ret = gdialog.CustomPrompt(_('Confirm Exit'),
                        _("Exit after saving changes?"), self,
                        (_('&Yes'), _('&No (discard changes)'),
                         _('&Cancel')), default=2, esc=2).run()
            if ret == 2:
                if resp is not None:
                    self.emit_stop_by_name('response')
                return True
            elif ret == 0:
                self._apply_clicked()
        return False

    def focus_field(self, focusfield):
        '''Set page and focus to requested datum'''
        for page_num, (vbox, info, widgets) in enumerate(self.pages):
            for w, (label, cpath, values, tip) in enumerate(info):
                if cpath == focusfield:
                    self.notebook.set_current_page(page_num)
                    widgets[w].grab_focus()
                    return

    def new_path(self, newpath, alias='new'):
        '''Add a new path to [paths], give default name, focus'''
        i = self.pathdata.insert_before(None, None)
        safepath = url.hidepassword(newpath)
        if alias in [row[0] for row in self.pathdata]:
            num = 0
            while len([row for row in self.pathdata if row[0] == alias]) > 0:
                num += 1
                alias = 'new_%d' % num
        self.pathdata.set_value(i, 0, alias)
        self.pathdata.set_value(i, 1, '%s' % hglib.toutf(safepath))
        self.pathdata.set_value(i, 2, '%s' % hglib.toutf(newpath))
        self.pathtree.get_selection().select_iter(i)
        self.pathtree.set_cursor(
                self.pathdata.get_path(i),
                self.pathtree.get_column(0))
        self.refresh_path_list()
        # This method may be called from hgtk.sync, so ensure page is visible
        self.notebook.set_current_page(3)
        self.dirty_event()

    def dirty_event(self, *args):
        if not self.dirty:
            self._btn_apply.set_sensitive(not self.readonly)
            self.dirty = True

    def _add_path(self, *args):
        self.new_path('http://')
        self._edit_path(new=True)

    def _edit_path(self, *args, **opts):
        selection = self.pathtree.get_selection()
        if not selection.count_selected_rows():
            return
        model, path = selection.get_selected()
        dialog = PathEditDialog(model[path][2], model[path][0],
                [p[0] for p in self.pathdata if p[0] != model[path][0]])
        dialog.set_transient_for(self)
        dialog.run()
        if dialog.newpath:
            if model[path][0] != dialog.newalias:
                # remove existing path
                rows = [row for row in model if row[0] == dialog.newalias]
                if len(rows) > 0:
                    del model[rows[0].iter]
            # update path info
            model[path][0] = dialog.newalias
            model[path][1] = url.hidepassword(dialog.newpath)
            model[path][2] = dialog.newpath
            self.dirty_event()
        elif opts.has_key('new') and opts['new'] == True:
            del self.pathdata[path]
            self.refresh_path_list()
            self.dirty_event()

    def _remove_path(self, *args):
        selection = self.pathtree.get_selection()
        if not selection.count_selected_rows():
            return
        model, path = selection.get_selected()
        next_iter = self.pathdata.iter_next(path)
        del self.pathdata[path]
        if next_iter:
            selection.select_iter(next_iter)
        elif len(self.pathdata):
            selection.select_path(len(self.pathdata) - 1)
        self.refresh_path_list()
        self.dirty_event()

    def _test_path(self, *args):
        selection = self.pathtree.get_selection()
        if not selection.count_selected_rows():
            return
        if not self.root:
            dialog.error_dialog(self, _('No Repository Found'),
                    _('Path testing cannot work without a repository'))
            return
        model, path = selection.get_selected()
        testpath = hglib.fromutf(model[path][2])
        if not testpath:
            return
        if testpath[0] == '~':
            testpath = os.path.expanduser(testpath)
        cmdline = ['hg', 'incoming', '--verbose', testpath]
        dlg = hgcmd.CmdDialog(cmdline, text='hg incoming')
        dlg.run()
        dlg.hide()

    def _default_path(self, *args):
        selection = self.pathtree.get_selection()
        if not selection.count_selected_rows():
            return
        model, path = selection.get_selected()
        if model[path][0] == 'default':
            return
        # collect rows has 'default' alias
        rows = [row for row in model if row[0] == 'default']
        if len(rows) > 0:
            ret = gdialog.Confirm(_('Confirm Overwrite'), [], self,
                   _("Overwrite existing '%s' path?") % 'default').run()
            if ret != gtk.RESPONSE_YES:
                return
            # remove old default path
            default_iter = rows[0].iter
            del model[default_iter]
        # set 'default' alias to selected path
        model[path][0] = 'default'
        self.refresh_path_list()
        self.dirty_event()

    def _pathtree_changed(self, sel):
        self.refresh_path_list()

    def _pathtree_pressed(self, widget, event):
        if event.button == 1 and event.type == gtk.gdk._2BUTTON_PRESS:
            x, y = int(event.x), int(event.y)
            pathinfo = self.pathtree.get_path_at_pos(x, y)
            if pathinfo is not None:
                self._edit_path()
        elif event.button == 1:
            selection = self.pathtree.get_selection()
            selection.unselect_all()
            self.refresh_path_list()

    def refresh_path_list(self):
        """Update sensitivity of buttons"""
        selection = self.pathtree.get_selection()
        path_selected = (len(self.pathdata) > 0
            and selection.count_selected_rows() > 0)
        repo_available = self.root is not None
        if path_selected:
            model, path = selection.get_selected()
            default_path = model[path][0] == 'default'
        else:
            default_path = False
        self._editpathbutton.set_sensitive(path_selected)
        self._delpathbutton.set_sensitive(path_selected)
        self._testpathbutton.set_sensitive(repo_available and path_selected)
        self._defaultpathbutton.set_sensitive(not default_path and path_selected)

    def fill_path_frame(self, frvbox):
        frame = gtk.Frame(_('Remote repository paths'))
        frame.set_border_width(4)
        frvbox.pack_start(frame, True, True, 2)
        vbox = gtk.VBox()
        vbox.set_border_width(4)
        frame.add(vbox)

        # Initialize data model for 'Paths' tab
        self.pathdata = gtk.ListStore(str, str, str)

        # Define view model for 'Paths' tab
        self.pathtree = gtk.TreeView(self.pathdata)
        self.pathtree.set_enable_search(False)
        self.pathtree.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.pathtree.connect("cursor-changed", self._pathtree_changed)
        self.pathtree.connect("button-press-event", self._pathtree_pressed)

        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_('Alias'), renderer, text=0)
        self.pathtree.append_column(column)

        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_('Repository Path'), renderer, text=1)
        self.pathtree.append_column(column)

        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.add(self.pathtree)
        vbox.add(scrolledwindow)

        buttonbox = gtk.HBox()
        self.addButton = gtk.Button(_('_Add'))
        self.addButton.set_use_underline(True)
        self.addButton.connect('clicked', self._add_path)
        buttonbox.pack_start(self.addButton, True, True, 2)

        self._editpathbutton = gtk.Button(_('_Edit'))
        self._editpathbutton.set_use_underline(True)
        self._editpathbutton.connect('clicked', self._edit_path)
        buttonbox.pack_start(self._editpathbutton, True, True, 2)

        self._delpathbutton = gtk.Button(_('_Remove'))
        self._delpathbutton.set_use_underline(True)
        self._delpathbutton.connect('clicked', self._remove_path)
        buttonbox.pack_start(self._delpathbutton, True, True, 2)

        self._testpathbutton = gtk.Button(_('_Test'))
        self._testpathbutton.set_use_underline(True)
        self._testpathbutton.connect('clicked', self._test_path)
        buttonbox.pack_start(self._testpathbutton, True, True, 2)

        self._defaultpathbutton = gtk.Button(_('Set as _default'))
        self._defaultpathbutton.set_use_underline(True)
        self._defaultpathbutton.connect('clicked', self._default_path)
        buttonbox.pack_start(self._defaultpathbutton, True, True, 2)

        vbox.pack_start(buttonbox, False, False, 4)

    def set_help(self, widget, event, buffer, tooltip):
        text = ' '.join(tooltip.splitlines())
        buffer.set_text(text)

    def fill_frame(self, frame, info):
        widgets = []

        descframe = gtk.Frame(_('Description'))
        descframe.set_border_width(4)
        desctext = gtk.TextView()
        desctext.set_wrap_mode(gtk.WRAP_WORD)
        desctext.set_editable(False)
        desctext.set_sensitive(False)
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.add(desctext)
        scrolledwindow.set_border_width(4)
        descframe.add(scrolledwindow)

        vbox = gtk.VBox()
        table = gtk.Table(len(info), 2, False)
        vbox.pack_start(table, False, False, 2)
        if info != _paths_info:
            vbox.pack_start(gtk.Label(), True, True, 0)
        vbox.pack_start(descframe, False, False, 2)
        frame.add(vbox)

        for row, (label, cpath, values, tooltip) in enumerate(info):
            vlist = gtk.ListStore(str, bool)
            combo = gtk.ComboBoxEntry(vlist, 0)
            combo.connect('changed', self.dirty_event)
            combo.child.connect('focus-in-event', self.set_help,
                    desctext.get_buffer(), tooltip)
            combo.set_row_separator_func(lambda model, path: model[path][1])
            combo.child.set_width_chars(40)
            if cpath in _pwfields:
                combo.child.set_visibility(False)
            widgets.append(combo)

            lbl = gtk.Label(label + ':')
            lbl.set_alignment(1.0, 0.0)
            eventbox = gtk.EventBox()
            eventbox.set_visible_window(False)
            eventbox.add(lbl)
            table.attach(eventbox, 0, 1, row, row+1, gtk.FILL, 0, 4, 2)
            table.attach(combo, 1, 2, row, row+1, gtk.FILL|gtk.EXPAND, 0, 4, 2)
            self.tooltips.set_tip(eventbox, tooltip)

        self.pages.append((vbox, info, widgets))
        return vbox

    def refresh_vlist(self):
        for vbox, info, widgets in self.pages:
            for row, (label, cpath, values, tooltip) in enumerate(info):
                ispw = cpath in _pwfields
                combo = widgets[row]
                vlist = combo.get_model()
                vlist.clear()

                # Get currently configured value from this config file
                curvalue = self.get_ini_config(cpath)

                if cpath == 'tortoisehg.vdiff':
                    # Special case, add extdiff.cmd.* to possible values
                    for name, value in self.ui.configitems('extdiff'):
                        if name.startswith('cmd.'):
                            if name[4:] not in values:
                                values.append(name[4:])
                        elif not name.startswith('opts.'):
                            if name not in values:
                                values.append(name)
                elif cpath == 'ui.merge':
                    # Special case, add [merge-tools] to possible values
                    hglib.mergetools(self.ui, values)

                currow = None
                if not ispw:
                    vlist.append([_unspecstr, False])
                if values:
                    vlist.append([_('Suggested'), True])
                    for v in values:
                        vlist.append([hglib.toutf(v), False])
                        if v == curvalue:
                            currow = len(vlist) - 1
                if cpath in self.history.get_keys() and not ispw:
                    separator = False
                    for v in self.history.mrul(cpath):
                        if v in values: continue
                        if not separator:
                            vlist.append([_('History'), True])
                            separator = True
                        vlist.append([hglib.toutf(v), False])
                        if v == curvalue:
                            currow = len(vlist) - 1

                if curvalue is None and len(vlist):
                    combo.set_active(0)
                elif currow is None and curvalue:
                    combo.child.set_text(hglib.toutf(curvalue))
                elif currow:
                    combo.set_active(currow)

    def add_page(self, notebook, tab):
        frame = gtk.VBox()
        frame.set_border_width(4)
        frame.show()

        label = gtk.Label(tab)
        notebook.append_page(frame, label)
        return frame

    def get_ini_config(self, cpath):
        '''Retrieve a value from the parsed config file'''
        try:
            # Presumes single section/key level depth
            section, key = cpath.split('.', 1)
            return self.ini[section][key]
        except KeyError:
            return None

    def load_config(self, rcpath):
        for fn in rcpath:
            if os.path.exists(fn):
                break
        else:
            for fn in rcpath:
                # Try to create a file from rcpath
                try:
                    f = open(fn, 'w')
                    f.write(_('# Generated by tortoisehg-config\n'))
                    f.close()
                    break
                except (IOError, OSError):
                    pass
            else:
                gdialog.Prompt(_('Unable to create a Mercurial.ini file'),
                       _('Insufficient access rights, reverting to read-only'
                         'mode.'), self).run()
                from mercurial import config
                self.fn = rcpath[0]
                cfg = config.config()
                return cfg
        self.fn = fn
        try:
            import iniparse
            # Monkypatch this regex to prevent iniparse from considering
            # 'rem' as a comment
            iniparse.ini.CommentLine.regex = \
                       re.compile(r'^(?P<csep>[;#])(?P<comment>.*)$')
            return iniparse.INIConfig(file(fn), optionxformvalue=None)
        except ImportError:
            from mercurial import config
            cfg = config.config()
            cfg.read(fn)
            return cfg

    def record_new_value(self, cpath, newvalue, keephistory=True):
        # 'newvalue' is converted to local encoding
        section, key = cpath.split('.', 1)
        if newvalue == _unspeclocalstr or newvalue == '':
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
        if not keephistory:
            return
        if cpath not in self.history.get_keys():
            self.history.set_value(cpath, [])
        elif newvalue in self.history.get_keys():
            self.history.get_value(cpath).remove(newvalue)
        self.history.mrul(cpath).add(newvalue)

    def _apply_clicked(self, *args):
        if self.readonly:
            #dialog? Read only access, please install ...
            return
        # Reload history, since it may have been modified externally
        self.history.read()

        # flush changes on paths page
        if len(self.pathdata):
            refreshlist = []
            for row in self.pathdata:
                name = hglib.fromutf(row[0])
                path = hglib.fromutf(row[2])
                if not name:
                    gdialog.Prompt(_('Invalid path'),
                           _('Skipped saving path with no alias'), self).run()
                    continue
                cpath = '.'.join(['paths', name])
                self.record_new_value(cpath, path, False)
                refreshlist.append(name)
            for name in self.ini.paths:
                if name not in refreshlist:
                    del self.ini['paths'][name]
        elif 'paths' in list(self.ini):
            for name in list(self.ini.paths):
                del self.ini['paths'][name]

        # Flush changes on all pages
        for vbox, info, widgets in self.pages:
            for w, (label, cpath, values, tip) in enumerate(info):
                newvalue = hglib.fromutf(widgets[w].child.get_text())
                self.record_new_value(cpath, newvalue)

        self.history.write()
        self.refresh_vlist()

        try:
            f = open(self.fn, "w")
            f.write(str(self.ini))
            f.close()
            self._btn_apply.set_sensitive(False)
            self.dirty = False
        except IOError, e:
            dialog.error_dialog(self, _('Unable to write configuration file'),
                    str(e))

        return 0

def run(ui, *pats, **opts):
    dlg = ConfigDialog(opts.get('alias') == 'repoconfig')
    if opts.get('focus', ''):
        dlg.focus_field(opts['focus'])
    return dlg

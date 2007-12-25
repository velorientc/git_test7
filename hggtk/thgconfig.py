#
# Configuration dialog for TortoiseHg and Mercurial
#
# Copyright (C) 2007 Steve Borho <steve@borho.org>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import gtk
import gobject
import os
import pango
from mercurial import hg, ui, cmdutil, util
from dialog import error_dialog, question_dialog
from shlib import set_tortoise_icon
import shelve
import iniparse

_unspecstr = '<unspecified>'

class ConfigDialog(gtk.Dialog):
    def __init__(self, root='', configrepo=False, focusfield=None):
        """ Initialize the Dialog. """        
        gtk.Dialog.__init__(self, parent=None, flags=0,
                          buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))

        self.ui = ui.ui()
        try:
            repo = hg.repository(self.ui, path=root)
        except hg.RepoError:
            repo = None
            if configrepo:
                error_dialog('No repository found', 'Unable to configure')
                return

        if configrepo:
            self.ui = repo.ui
            self.rcpath = [os.sep.join([repo.root, '.hg', 'hgrc'])]
            self.set_title('TortoiseHg Configure Repository - ' + repo.root)
        else:
            self.rcpath = util.user_rcpath()
            self.set_title('TortoiseHg Configure User-Global Settings')

        #set_tortoise_icon(self, 'menurepobrowse.ico')
        self.ini = self.load_config(self.rcpath)

        self.connect('response', gtk.main_quit)
        # Create a new notebook, place the position of the tabs
        self.notebook = notebook = gtk.Notebook()
        notebook.set_tab_pos(gtk.POS_TOP)
        self.vbox.pack_start(notebook)
        notebook.show()
        self.show_tabs = True
        self.show_border = True

        self._btn_apply = gtk.Button("Apply")
        self._btn_apply.connect('clicked', self._apply_clicked)
        self.action_area.pack_end(self._btn_apply)

        self.pages = []
        self.history = self.load_history()

        # create pages for each section of configuration file
        self._tortoise_info = (
                ('Commit Tool', 'tortoisehg.commit', ['qct', 'internal'],
                    'Select commit tool launched by TortoiseHg. Qct is' +
                    'not included, must be installed separately'),
                ('Revision Graph Viewer', 'tortoisehg.view', ['hgk', 'hgview'],
                    'Select revision graph (DAG) viewer launched by' +
                    'TortoiseHg'),
                ('Visual Diff Tool', 'tortoisehg.vdiff', [],
                    'Specify the visual diff tool; must be extdiff command'))
        self.tortoise_frame = self.add_page(notebook, 'TortoiseHG')
        self.fill_frame(self.tortoise_frame, self._tortoise_info)

        self._user_info = (
                ('Username', 'ui.username', [], 
                    'Name associated with commits'),
                ('Editor', 'ui.editor', [],
                    'The editor to use during a commit'),
                ('Verbose', 'ui.verbose', ['False', 'True'],
                    'Increase the amount of output printed'),
                ('Debug', 'ui.debug', ['False', 'True'],
                    'Print debugging information'))
        self.user_frame = self.add_page(notebook, 'User')
        self.fill_frame(self.user_frame, self._user_info)

        self._paths_info = (
                ('default', 'paths.default', [],
'''Directory or URL to use when pulling if no source is specified.
Default is set to repository from which the current repository was cloned.'''),
                ('default-push', 'paths.default-push', [],
'''Optional. Directory or URL to use when pushing if no
destination is specified.'''))
        self.paths_frame = self.add_page(notebook, 'Paths')
        self.fill_frame(self.paths_frame, self._paths_info)
        # paths page is special TODO borrow from hg-config

        self._web_info = (
                ('Description', 'web.description', ['unknown'],
                    'Textual description of the repository''s purpose or' +
                    'contents.'),
                ('Contact', 'web.contact', ['unknown'],
                    'Name or email address of the person in charge of the' +
                    'repository.'),
                ('Style', 'web.style', ['default', 'gitweb', 'old'],
                    'Which template map style to use'),
                ('Archive Formats', 'web.allow_archive', ['bz2', 'gz', 'zip'],
                    'List of archive formats allowed for downloading'),
                ('Port', 'web.port', ['8000'], 'Port to listen on'),
                ('Push Requires SSL', 'web.push_ssl', ['True', 'False'],
                    'Whether to require that inbound pushes be transported' +
                    'over SSL to prevent password sniffing.'),
                ('Stripes', 'web.stripes', ['1', '0'],
                    'How many lines a "zebra stripe" should span in multiline' +
                    'output. Default is 1; set to 0 to disable.'),
                ('Max Files', 'web.maxfiles', ['10'],
                    'Maximum number of files to list per changeset.'),
                ('Max Changes', 'web.maxfiles', ['10'],
                    'Maximum number of changes to list on the changelog.'),
                ('Allow Push', 'ui.allow_push', ['*'],
'''Whether to allow pushing to the repository. If empty or not
set, push is not allowed. If the special value "*", any remote
user can push, including unauthenticated users. Otherwise, the
remote user must have been authenticated, and the authenticated
user name must be present in this list (separated by whitespace
or ","). The contents of the allow_push list are examined after
the deny_push list.'''),
                ('Deny Push', 'ui.deny_push', ['*'],
'''Whether to deny pushing to the repository. If empty or not set,
push is not denied. If the special value "*", all remote users
are denied push. Otherwise, unauthenticated users are all
denied, and any authenticated user name present in this list
(separated by whitespace or ",") is also denied. The contents
of the deny_push list are examined before the allow_push list.'''),
                ('Encoding', 'web.encoding', ['UTF-8'],
                    'Character encoding name'))
        self.web_frame = self.add_page(notebook, 'Web')
        self.fill_frame(self.web_frame, self._web_info)

        self._email_info = (
                ('From:', 'email.from', [],
                    'Email address to use in "From" header and SMTP envelope'),
                ('To:', 'email.to', [],
                    'Comma-separated list of recipients'' email addresses'),
                ('Cc:', 'email.cc', [],
                    'Comma-separated list of carbon copy recipients'' email ' +
                    'addresses'),
                ('Bcc:', 'email.bcc', [],
                    'Comma-separated list of blind carbon copy recipients'' ' +
                    'email addresses'),
                ('method:', 'email.method', ['smtp'],
'''Optional. Method to use to send email messages. If value is "smtp" (default),
use SMTP (configured below).  Otherwise, use as name of program to run that
acts like sendmail (takes "-f" option for sender, list of recipients on command
line, message on stdin). Normally, setting this to "sendmail" or
"/usr/sbin/sendmail" is enough to use sendmail to send messages.'''),
                ('SMTP Host:', 'smtp.host', [], 'Host name of mail server'),
                ('SMTP Port:', 'smtp.port', ['25'],
                    'Port to connect to on mail server. Default: 25'),
                ('SMTP TLS:', 'smtp.tls', ['False', 'True'],
                    'Connect to mail server using TLS.  Default: False'),
                ('SMTP Username:', 'smtp.username', [],
                    'Username to authenticate to SMTP server with'),
                ('SMTP Password:', 'smtp.password', [],
                    'Password to authenticate to SMTP server with'),
                ('SMTP Local Hostname:', 'smtp.local_hostname', [],
                    'Hostname the sender can use to identify itself to MTA'))
        self.email_frame = self.add_page(notebook, 'Email')
        self.fill_frame(self.email_frame, self._email_info)

        self._hgmerge_info = (
                ('Default 3-way Merge', 'hgmerge.interactive',
                    ['gpyfm', 'kdiff3', 'tortoisemerge', 'p4merge',
                        'meld', 'tkdiff', 'filemerge', 'ecmerge',
                        'xxdiff', 'guiffy', 'diffmerge'],
                    'Textual merge program for resolving merge conflicts'),)
        self.hgmerge_frame = self.add_page(notebook, 'Merge')
        self.fill_frame(self.hgmerge_frame, self._hgmerge_info)
        # TODO add ability to specify file extension based merge tools

        if focusfield:
            # Set page and focus to requested datum
            for page_num, (frame, info, widgets) in enumerate(self.pages):
                for w, (label, cpath, values, tip) in enumerate(info):
                    if cpath == focusfield:
                        self.notebook.set_current_page(page_num)
                        widgets[w].grab_focus()

    def fill_frame(self, frame, info):
        #tooltips = gtk.GtkTooltips()  TODO, why is this not working?
        widgets = []
        vbox = gtk.VBox()
        frame.add(vbox)

        for label, cpath, values, tooltip in info:
            vlist = gtk.ListStore(str)
            combo = gtk.ComboBoxEntry(vlist, 0)
            #tooltips.set_tip(combo, tooltip)
            widgets.append(combo)

            # Get currently configured value from this config file
            curvalue = self.get_ini_config(cpath)

            if cpath == 'tortoisehg.vdiff':
                # Special case, add extdiff.cmd.* to possible values
                for name, value in self.ui.configitems('extdiff'):
                    if name.startswith('cmd.'):
                        values.append(name[4:])

            currow = None
            vlist.append([_unspecstr])
            for v in values:
                vlist.append([v])
                if v == curvalue:
                    currow = len(vlist) - 1
            if cpath in self.history:
                for v in self.history[cpath]:
                    if v in values: continue
                    vlist.append([v])
                    if v == curvalue:
                        currow = len(vlist) - 1

            if curvalue is None:
                combo.set_active(0)
            elif currow is None:
                combo.get_child().set_text(curvalue)
            else:
                combo.set_active(currow)

            lbl = gtk.Label(label)
            hbox = gtk.HBox()
            hbox.pack_start(lbl, False, False, 4)
            hbox.pack_start(combo, True, True, 4)
            vbox.pack_start(hbox, False, False, 4)

        self.pages.append((frame, info, widgets))
        
    def add_page(self, notebook, tab):
        frame = gtk.Frame()
        frame.set_border_width(10)
        frame.set_size_request(508, 500)
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
            fn = rcpath[0]
            f = open(fn, "w")
            f.write("# Generated by tortoisehg-config\n")
            f.close()
        self.fn = fn
        return iniparse.INIConfig(file(fn))

    def _apply_clicked(self, *args):
        # Reload history, since it may have been modified externally
        self.history = self.load_history()
        for frame, info, widgets in self.pages:
            for w, (label, cpath, values, tip) in enumerate(info):
                newvalue = widgets[w].get_child().get_text()
                section, key = cpath.split('.', 1)
                if newvalue == _unspecstr:
                    try:
                        del self.ini[section][key]
                    except KeyError:
                        pass
                else:
                    if section not in list(self.ini):
                        self.ini.new_namespace(section)
                    self.ini[section][key] = newvalue
                    if cpath not in self.history:
                        self.history[cpath] = []
                    elif newvalue in self.history[cpath]:
                        self.history[cpath].remove(newvalue)
                    self.history[cpath].insert(0, newvalue)
        # TODO: Add special code for paths, hgmerge extensions
        self.save_history(self.history)
        try:
            f = open(self.fn, "w")
            f.write(str(self.ini))
            f.close()
        except IOError, e:
            error_dialog('Unable to write back configuration file', str(e))
        return 0

    def load_history(self):
        path = os.path.join(os.path.expanduser('~'), '.hgext', 'tortoisehg')
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        dbase = shelve.open(path)
        history = dbase.get('config_history', {})
        dbase.close()
        return history

    def save_history(self, history):
        path = os.path.join(os.path.expanduser('~'), '.hgext', 'tortoisehg')
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        dbase = shelve.open(path)
        dbase['config_history'] = history
        dbase.close()
    
def run(root='', cmdline=[], **opts):
    if '--focusfield' in cmdline:
        field = cmdline[cmdline.index('--focusfield')+1]
    else:
        field = None
    dialog = ConfigDialog(root, '--configrepo' in cmdline, field)
    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    # example command line
    # python hggtk/thgconfig.py --focusfield ui.editor
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or ''
    opts['cmdline'] = sys.argv
    run(**opts)

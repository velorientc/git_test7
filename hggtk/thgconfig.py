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
import shlib
import shelve
import iniparse

_unspecstr = '<unspecified>'

class ConfigDialog(gtk.Dialog):
    def __init__(self, root='',
            configrepo=False,
            focusfield=None,
            newpath=None):
        """ Initialize the Dialog. """        
        gtk.Dialog.__init__(self, parent=None, flags=0,
                          buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))

        self.ui = ui.ui()
        try:
            repo = hg.repository(self.ui, path=root)
        except hg.RepoError:
            repo = None
            if configrepo:
                error_dialog('No repository found', 'no repo at ' + root)
                self.response(gtk.RESPONSE_CANCEL)

        # Catch close events
        self.connect('delete-event', self._delete)
        self.connect('response', self._response)

        if configrepo:
            self.ui = repo.ui
            name = repo.ui.config('web', 'name') or os.path.basename(repo.root)
            self.rcpath = [os.sep.join([repo.root, '.hg', 'hgrc'])]
            self.set_title('TortoiseHg Configure Repository - ' + name)
        else:
            self.rcpath = util.user_rcpath()
            self.set_title('TortoiseHg Configure User-Global Settings')

        shlib.set_tortoise_icon(self, 'menusettings.ico')
        self.ini = self.load_config(self.rcpath)

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

        self.dirty = False
        self.pages = []
        self.tooltips = gtk.Tooltips()
        self.history = shlib.read_history()

        # create pages for each section of configuration file
        self._tortoise_info = (
                ('Commit Tool', 'tortoisehg.commit', ['qct', 'internal'],
                    'Select commit tool launched by TortoiseHg. Qct is'
                    ' not included, must be installed separately'),
                ('Revision Graph Viewer', 'tortoisehg.view', ['hgk', 'hgview'],
                    'Select revision graph (DAG) viewer launched by'
                    ' TortoiseHg'),
                ('Visual Diff Tool', 'tortoisehg.vdiff', [],
                    'Specify the visual diff tool; must be extdiff command'))
        self.tortoise_frame = self.add_page(notebook, 'TortoiseHG')
        self.fill_frame(self.tortoise_frame, self._tortoise_info)

        self._user_info = (
                ('Username', 'ui.username', [], 
                    'Name associated with commits'),
                ('Editor', 'ui.editor', [],
                    'The editor to use during a commit and other'
                    ' instances where Mercurial needs multiline input from'
                    ' the user.  Only required by CLI commands.'),
                ('Verbose', 'ui.verbose', ['False', 'True'],
                    'Increase the amount of output printed'),
                ('Debug', 'ui.debug', ['False', 'True'],
                    'Print debugging information'))
        self.user_frame = self.add_page(notebook, 'User')
        self.fill_frame(self.user_frame, self._user_info)

        self._paths_info = (
                ('default', 'paths.default', [],
'Directory or URL to use when pulling if no source is specified.'
' Default is set to repository from which the current repository was cloned.'),
                ('default-push', 'paths.default-push', [],
'Optional. Directory or URL to use when pushing if no'
' destination is specified.'''))
        self.paths_frame = self.add_page(notebook, 'Paths')
        vbox = self.fill_frame(self.paths_frame, self._paths_info)

        self.pathtree = gtk.TreeView()
        self.pathsel = self.pathtree.get_selection()
        self.pathsel.connect("changed", self._pathlist_rowchanged)
        column = gtk.TreeViewColumn('Peer Repository Paths',
                gtk.CellRendererText(), text=2)
        self.pathtree.append_column(column) 
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.add(self.pathtree)
        vbox.add(scrolledwindow)

        self.pathlist = []
        if 'paths' in list(self.ini):
            for name in self.ini['paths']:
                if name in ('default', 'default-push'): continue
                self.pathlist.append((name, self.ini['paths'][name]))
        self.curpathrow = 0

        buttonbox = gtk.HBox()
        self.addButton = gtk.Button("Add")
        self.addButton.connect('clicked', self._add_path)
        buttonbox.pack_start(self.addButton)

        self._delpathbutton = gtk.Button("Remove")
        self._delpathbutton.connect('clicked', self._remove_path)
        buttonbox.pack_start(self._delpathbutton)

        self._refreshpathbutton = gtk.Button("Refresh")
        self._refreshpathbutton.connect('clicked', self._refresh_path)
        buttonbox.pack_start(self._refreshpathbutton)

        self._testpathbutton = gtk.Button("Test")
        self._testpathbutton.connect('clicked', self._test_path)
        buttonbox.pack_start(self._testpathbutton)

        hbox = gtk.HBox()
        self._pathnameedit = gtk.Entry()
        hbox.pack_start(gtk.Label('Name:'), False, False, 4)
        hbox.pack_start(self._pathnameedit, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)

        hbox = gtk.HBox()
        self._pathpathedit = gtk.Entry()
        hbox.pack_start(gtk.Label('Path:'), False, False, 4)
        hbox.pack_start(self._pathpathedit, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)
        vbox.pack_start(buttonbox, False, False, 4)
        self.refresh_path_list()

        self._web_info = (
                ('Name', 'web.name', ['unknown'],
                    'Repository name to use in the web interface.  Default'
                    ' is the working directory.'),
                ('Description', 'web.description', ['unknown'],
                    'Textual description of the repository''s purpose or'
                    ' contents.'),
                ('Contact', 'web.contact', ['unknown'],
                    'Name or email address of the person in charge of the'
                    ' repository.'),
                ('Style', 'web.style', ['default', 'gitweb', 'old'],
                    'Which template map style to use'),
                ('Archive Formats', 'web.allow_archive', ['bz2', 'gz', 'zip'],
                    'Comma separated list of archive formats allowed for'
                    ' downloading'),
                ('Port', 'web.port', ['8000'], 'Port to listen on'),
                ('Push Requires SSL', 'web.push_ssl', ['True', 'False'],
                    'Whether to require that inbound pushes be transported'
                    ' over SSL to prevent password sniffing.'),
                ('Stripes', 'web.stripes', ['1', '0'],
                    'How many lines a "zebra stripe" should span in multiline'
                    ' output. Default is 1; set to 0 to disable.'),
                ('Max Files', 'web.maxfiles', ['10'],
                    'Maximum number of files to list per changeset.'),
                ('Max Changes', 'web.maxfiles', ['10'],
                    'Maximum number of changes to list on the changelog.'),
                ('Allow Push', 'ui.allow_push', ['*'],
'Whether to allow pushing to the repository. If empty or not'
' set, push is not allowed. If the special value "*", any remote'
' user can push, including unauthenticated users. Otherwise, the'
' remote user must have been authenticated, and the authenticated'
' user name must be present in this list (separated by whitespace'
' or ","). The contents of the allow_push list are examined after'
' the deny_push list.'),
                ('Deny Push', 'ui.deny_push', ['*'],
'Whether to deny pushing to the repository. If empty or not set,'
' push is not denied. If the special value "*", all remote users'
' are denied push. Otherwise, unauthenticated users are all'
' denied, and any authenticated user name present in this list'
' (separated by whitespace or ",") is also denied. The contents'
' of the deny_push list are examined before the allow_push list.'),
                ('Encoding', 'web.encoding', ['UTF-8'],
                    'Character encoding name'))
        self.web_frame = self.add_page(notebook, 'Web')
        self.fill_frame(self.web_frame, self._web_info)

        self._email_info = (
                ('From:', 'email.from', [],
                    'Email address to use in "From" header and SMTP envelope'),
                ('To:', 'email.to', [],
                    'Comma-separated list of recipient email addresses'),
                ('Cc:', 'email.cc', [],
                    'Comma-separated list of carbon copy recipient email'
                    ' addresses'),
                ('Bcc:', 'email.bcc', [],
                    'Comma-separated list of blind carbon copy recipient'
                    ' email addresses'),
                ('method:', 'email.method', ['smtp'],
'Optional. Method to use to send email messages. If value is "smtp" (default),'
' use SMTP (configured below).  Otherwise, use as name of program to run that'
' acts like sendmail (takes "-f" option for sender, list of recipients on'
' command line, message on stdin). Normally, setting this to "sendmail" or'
' "/usr/sbin/sendmail" is enough to use sendmail to send messages.'),
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
                ('Default 3-way Merge Tool', 'hgmerge.interactive',
                    ['gpyfm', 'kdiff3', 'tortoisemerge', 'p4merge',
                        'meld', 'tkdiff', 'filemerge', 'ecmerge',
                        'xxdiff', 'guiffy', 'diffmerge'],
'Textual merge program for resolving merge conflicts.  If left'
' unspecified, the hgmerge wrapper will use the first applicable'
' tool it finds on your system'),)
        self.hgmerge_frame = self.add_page(notebook, 'Merge')
        self.fill_frame(self.hgmerge_frame, self._hgmerge_info)
        # TODO add ability to specify file extension based merge tools

        # Force dialog into clean state in the beginning
        self._btn_apply.set_sensitive(False)
        self.dirty = False

    def _delete(self, widget, event):
        return True

    def _response(self, widget, response_id):
        if self.dirty:
            if question_dialog('Quit without saving?',
                'Yes to abandon changes, No to continue') != gtk.RESPONSE_YES:
                widget.emit_stop_by_name('response')

    def focus_field(self, focusfield):
        '''Set page and focus to requested datum'''
        for page_num, (vbox, info, widgets) in enumerate(self.pages):
            for w, (label, cpath, values, tip) in enumerate(info):
                if cpath == focusfield:
                    self.notebook.set_current_page(page_num)
                    widgets[w].grab_focus()
                    return

    def new_path(self, newpath):
        '''Add a new path to [paths], give default name, focus'''
        self.pathlist.append(('new', newpath))
        self.curpathrow = len(self.pathlist)-1
        self.refresh_path_list()
        self.notebook.set_current_page(2)
        self._pathnameedit.grab_focus()

    def dirty_event(self, *args):
        if not self.dirty:
            self._btn_apply.set_sensitive(True)
            self.dirty = True

    def _add_path(self, *args):
        if len(self.pathlist):
            self.pathlist.append(self.pathlist[self.curpathrow])
        else:
            self.pathlist.append(('default', 'http://'))
        self.curpathrow = len(self.pathlist)-1
        self.refresh_path_list()
        self._pathnameedit.grab_focus()
        self.dirty_event()

    def _remove_path(self, *args):
        del self.pathlist[self.curpathrow]
        if self.curpathrow > len(self.pathlist)-1:
            self.curpathrow = len(self.pathlist)-1
        self.refresh_path_list()
        self.dirty_event()

    def _test_path(self, *args):
        testpath = self._pathpathedit.get_text()
        if not testpath:
            return
        if testpath[0] == '~':
            testpath = os.path.expanduser(testpath)
        cmdline = ['hg', 'incoming', '--verbose', testpath]
        from hgcmd import CmdDialog
        dlg = CmdDialog(cmdline)
        dlg.run()
        dlg.hide()

    def _refresh_path(self, *args):
        self.pathlist[self.curpathrow] = (self._pathnameedit.get_text(),
                self._pathpathedit.get_text())
        self.refresh_path_list()
        self.dirty_event()

    def _pathlist_rowchanged(self, sel):
        model, iter = sel.get_selected()
        if not iter:
            return
        self._pathnameedit.set_text(model.get(iter, 0)[0])
        self._pathpathedit.set_text(model.get(iter, 1)[0])
        self.curpathrow = model.get(iter, 3)[0]

    def refresh_path_list(self):
        model = gtk.ListStore(gobject.TYPE_PYOBJECT,
                gobject.TYPE_PYOBJECT,
                gobject.TYPE_STRING,
                gobject.TYPE_PYOBJECT)
        row = 0
        for (name, path) in self.pathlist:
            iter = model.insert_before(None, None)
            model.set_value(iter, 0, name)
            model.set_value(iter, 1, path)
            model.set_value(iter, 2, "%s = %s" % (name, path))
            model.set_value(iter, 3, row)
            row += 1
        self.pathtree.set_model(model)
        if len(self.pathlist):
            self._delpathbutton.set_sensitive(True)
            self._testpathbutton.set_sensitive(True)
            self._refreshpathbutton.set_sensitive(True)
            self._pathnameedit.set_sensitive(True)
            self._pathpathedit.set_sensitive(True)
        else:
            self._delpathbutton.set_sensitive(False)
            self._testpathbutton.set_sensitive(False)
            self._refreshpathbutton.set_sensitive(False)
            self._pathnameedit.set_sensitive(False)
            self._pathpathedit.set_sensitive(False)
        if self.curpathrow < len(self.pathlist):
             self.pathsel.select_path(self.curpathrow)

    def fill_frame(self, frame, info):
        widgets = []
        vbox = gtk.VBox()
        frame.add(vbox)

        for label, cpath, values, tooltip in info:
            vlist = gtk.ListStore(str)
            combo = gtk.ComboBoxEntry(vlist, 0)
            combo.connect("changed", self.dirty_event)
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
                combo.child.set_text(curvalue)
            else:
                combo.set_active(currow)

            lbl = gtk.Label(label)
            hbox = gtk.HBox()
            eventbox = gtk.EventBox()
            self.tooltips.set_tip(eventbox, tooltip)
            eventbox.add(lbl)
            hbox.pack_start(eventbox, False, False, 4)
            hbox.pack_start(combo, True, True, 4)
            vbox.pack_start(hbox, False, False, 4)

        self.pages.append((vbox, info, widgets))
        return vbox
        
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

    def record_new_value(self, cpath, newvalue, keephistory=True):
        section, key = cpath.split('.', 1)
        if newvalue == _unspecstr:
            try:
                del self.ini[section][key]
            except KeyError:
                pass
            return
        if section not in list(self.ini):
            self.ini.new_namespace(section)
        self.ini[section][key] = newvalue
        if not keephistory:
            return
        if cpath not in self.history:
            self.history[cpath] = []
        elif newvalue in self.history[cpath]:
            self.history[cpath].remove(newvalue)
        self.history[cpath].insert(0, newvalue)

    def _apply_clicked(self, *args):
        # Reload history, since it may have been modified externally
        self.history = shlib.read_history()

        # flush changes on paths page
        if len(self.pathlist):
            self._refresh_path(None)
            refreshlist = []
            for (name, path) in self.pathlist:
                cpath = '.'.join(['paths', name])
                self.record_new_value(cpath, path, False)
                refreshlist.append(name)
            if 'paths' not in list(self.ini):
                self.ini.new_namespace('paths')
            for name in list(self.ini.paths):
                if name not in refreshlist:
                    del self.ini['paths'][name]

        # TODO: Add special code for flushing hgmerge extensions

        # Flush changes on all pages
        for vbox, info, widgets in self.pages:
            for w, (label, cpath, values, tip) in enumerate(info):
                newvalue = widgets[w].child.get_text()
                self.record_new_value(cpath, newvalue)

        shlib.save_history(self.history)
        try:
            f = open(self.fn, "w")
            f.write(str(self.ini))
            f.close()
        except IOError, e:
            error_dialog('Unable to write back configuration file', str(e))

        self._btn_apply.set_sensitive(False)
        self.dirty = False
        return 0

def run(root='', cmdline=[], files=[], **opts):
    dialog = ConfigDialog(root, bool(files))
    dialog.show_all()
    dialog.connect('response', gtk.main_quit)
    if '--focusfield' in cmdline:
        field = cmdline[cmdline.index('--focusfield')+1]
        dialog.focus_field(field)
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    # example command lines
    # python hggtk/thgconfig.py --focusfield ui.editor
    # python hggtk/thgconfig.py --focusfield paths.default --configrepo
    import sys
    opts = {}
    opts['root'] = os.getcwd()
    opts['cmdline'] = sys.argv
    opts['files'] = '--configrepo' in sys.argv and ['.'] or []
    run(**opts)

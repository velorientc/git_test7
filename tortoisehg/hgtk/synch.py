# synch.py - Repository synchronization dialog for TortoiseHg
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import gobject
import pango
import Queue
import os
import sys
import threading
import urllib

from mercurial import hg, ui, extensions, url, error

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, settings, paths

from tortoisehg.hgtk import dialog, gtklib, hgthread, thgconfig
from tortoisehg.hgtk import thgshelve, hgemail, update, statusbar

class SynchDialog(gtk.Window):
    def __init__(self, repos=[], pushmode=False):
        """ Initialize the Dialog. """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        gtklib.set_tortoise_icon(self, 'menusynch.ico')
        gtklib.set_tortoise_keys(self)

        self.root = paths.find_root()
        self.selected_path = None
        self.hgthread = None
        self.notify_func = None
        self.last_drop_time = None
        self.lastcmd = []

        # Replace stdout file descriptor with our own pipe
        self.oldstdout = os.dup(sys.__stdout__.fileno())
        self.stdoutq = Queue.Queue()
        self.readfd, writefd = os.pipe()
        os.dup2(writefd, sys.__stdout__.fileno())

        # persistent app data
        self._settings = settings.Settings('synch')
        self.set_default_size(655, 552)

        self.paths = self.get_paths()
        self.set_title(_('%s - synchronize') % hglib.get_reponame(self.repo))

        self.connect('delete-event', self.delete)

        # toolbar
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()
        self.stop_button = self.toolbutton(gtk.STOCK_STOP,
                _('Stop'), self.stop_clicked, tip=_('Stop the hg operation'))
        self.stop_button.set_sensitive(False)
        tbuttons = [
                self.toolbutton(gtk.STOCK_GO_DOWN,
                                 _('Incoming'),
                                 self.incoming_clicked,
                                 tip=_('Display changes that can be pulled'
                                 ' from selected repository')),
                self.toolbutton(gtk.STOCK_GOTO_BOTTOM,
                                 _('   Pull   '),
                                 self.pull_clicked,
                                 tip=_('Pull changes from selected'
                                 ' repository')),
                gtk.SeparatorToolItem(),
                self.toolbutton(gtk.STOCK_GO_UP,
                                 _('Outgoing'),
                                 self.outgoing_clicked,
                                 tip=_('Display local changes that will be '
                                 ' pushed to selected repository')),
                self.toolbutton(gtk.STOCK_GOTO_TOP,
                                 _('Push'),
                                 self.push_clicked,
                                 tip=_('Push local changes to selected'
                                 ' repository')),
                self.toolbutton(gtk.STOCK_GOTO_LAST,
                                 _('Email'),
                                 self.email_clicked,
                                 tip=_('Email local outgoing changes to'
                                 ' one or more recipients')),
                self.toolbutton(gtk.STOCK_UNDO,
                                 _('Shelve'),
                                 self.shelve_clicked,
                                 tip=_('Shelve uncommited changes')),
                gtk.SeparatorToolItem(),
                self.stop_button,
                gtk.SeparatorToolItem(),
                self.toolbutton(gtk.STOCK_PREFERENCES,
                                 _('Configure'),
                                 self.conf_clicked,
                                 tip=_('Configure peer repository paths')),
                gtk.SeparatorToolItem(),
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)

        # Base box
        self.basevbox = basevbox = gtk.VBox()
        self.add(basevbox)
        basevbox.pack_start(self.tbar, False, False, 2)

        # Sync Target Path
        targethbox = gtk.HBox()

        ## target selection buttons
        lbl = gtk.Button(_('Repo:'))
        lbl.unset_flags(gtk.CAN_FOCUS)
        lbl.connect('clicked', self.btn_remotepath_clicked)
        targethbox.pack_start(lbl, False, False)

        lbl = gtk.Button(_('Bundle:'))
        lbl.unset_flags(gtk.CAN_FOCUS)
        lbl.connect('clicked', self.btn_bundlepath_clicked)
        targethbox.pack_start(lbl, False, False)

        ## target path combobox
        self.pathlist = gtk.ListStore(str, str)
        self.pathbox = gtk.ComboBoxEntry(self.pathlist, 0)
        self.pathtext = self.pathbox.get_child()
        cell = gtk.CellRendererText()
        self.pathbox.pack_end(cell, False)
        self.pathbox.add_attribute(cell, 'text', 1)
        targethbox.pack_start(self.pathbox, True, True)

        self.fill_path_combo()
        defrow = None
        defpushrow = None
        for i, (path, alias) in enumerate(self.pathlist):
            if alias == 'default':
                defrow = i
                if defpushrow is None:
                    defpushrow = i
            elif alias == 'default-push':
                defpushrow = i

        if repos:
            self.pathtext.set_text(hglib.toutf(repos[0]))
        elif defpushrow is not None and pushmode:
            self.pathbox.set_active(defpushrow)
        elif defrow is not None:
            self.pathbox.set_active(defrow)

        exs = [ name for name, module in extensions.extensions() ]

        # Post Pull Operation
        ppullhbox = gtk.HBox()
        self.ppulldata = [('none', _('Nothing')), ('update', _('Update'))]
        cfg = self.repo.ui.config('tortoisehg.postpull', 'none')
        if 'fetch' in exs or 'fetch' == cfg:
            self.ppulldata.append(('fetch', _('Fetch')))
        if 'rebase' in exs or 'rebase' == cfg:
            self.ppulldata.append(('rebase', _('Rebase')))
        self.ppullcombo = combo = gtk.combo_box_new_text()
        for (index, (name, label)) in enumerate(self.ppulldata):
            combo.insert_text(index, label)
        ppullhbox.pack_start(gtk.Label(_('Post Pull: ')), False, False, 2)
        ppullhbox.pack_start(self.ppullcombo, True, True)

        # Fixed options box (non-foldable)
        fixedhbox = gtk.HBox()
        fixedhbox.pack_start(targethbox, True, True, 2)
        fixedhbox.pack_start(ppullhbox, False, False, 2)

        # Advanced options (foldable)
        opthbox = gtk.HBox()
        self.expander = expander = gtk.Expander(_('Advanced Options'))
        expander.set_expanded(False)
        expander.connect_after('activate', self.expanded)
        expander.add(opthbox)

        ## checkbox options
        chkopthbox = gtk.HBox()
        self.force = gtk.CheckButton(_('Force pull or push'))
        self.tips.set_tip(self.force, _('Run even when remote repository'
                ' is unrelated.'))
        self.use_proxy = gtk.CheckButton(_('Use proxy server'))
        if ui.ui().config('http_proxy', 'host', ''):
            self.use_proxy.set_active(True)
        else:
            self.use_proxy.set_sensitive(False)
        chkopthbox.pack_start(self.force, False, False, 4)
        chkopthbox.pack_start(self.use_proxy, False, False, 4)

        ## target revision option
        revhbox = gtk.HBox()
        self.reventry = gtk.Entry()
        revhbox.pack_start(gtk.Label(_('Target revision:')), False, False, 2)
        revhbox.pack_start(self.reventry, True, True, 2)
        reveventbox = gtk.EventBox()
        reveventbox.add(revhbox)
        self.tips.set_tip(reveventbox, _('A specific revision up to which you'
                ' would like to push or pull.'))

        ## remote command option
        cmdhbox = gtk.HBox()
        self.cmdentry = gtk.Entry()
        cmdhbox.pack_start(gtk.Label(_('Remote command:')), False, False, 2)
        cmdhbox.pack_start(self.cmdentry, True, True, 2)
        cmdeventbox = gtk.EventBox()
        cmdeventbox.add(cmdhbox)
        self.tips.set_tip(cmdeventbox, _('Name of hg executable on remote'
                ' machine.'))

        revvbox = gtk.VBox()
        revvbox.pack_start(chkopthbox, False, False, 8)
        revvbox.pack_start(reveventbox, False, False, 4)
        revvbox.pack_start(cmdeventbox, False, False, 4)
        opthbox.pack_start(revvbox, True, True, 4)

        ## incoming/outgoing options
        frame = gtk.Frame(_('Incoming/Outgoing'))
        opthbox.pack_start(frame, False, False, 2)

        self.showpatch = gtk.CheckButton(_('Show patches'))
        self.newestfirst = gtk.CheckButton(_('Show newest first'))
        self.nomerge = gtk.CheckButton(_('Show no merges'))

        iovbox = gtk.VBox()
        iovbox.pack_start(self.showpatch, False, False, 2)
        iovbox.pack_start(self.newestfirst, False, False, 2)
        iovbox.pack_start(self.nomerge, False, False, 2)
        frame.add(iovbox)

        # Main option box
        topvbox = gtk.VBox()
        topvbox.pack_start(fixedhbox, True, True, 2)
        topvbox.pack_start(expander, False, False, 2)
        basevbox.pack_start(topvbox, False, False, 2)

        # hg output window
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.textview = gtk.TextView(buffer=None)
        self.textview.set_editable(False)
        fontlog = hglib.getfontconfig()['fontlog']
        self.textview.modify_font(pango.FontDescription(fontlog))
        scrolledwindow.add(self.textview)
        self.textview.connect('populate-popup', self.add_to_popup)
        self.textbuffer = self.textview.get_buffer()
        self.textbuffer.create_tag('error', weight=pango.WEIGHT_HEAVY,
                                   foreground=gtklib.DRED)
        basevbox.pack_start(scrolledwindow, True, True)

        # statusbar
        self.stbar = statusbar.StatusBar()
        basevbox.pack_end(self.stbar, False, False, 2)

        # support dropping of repos or bundle files
        self.drag_dest_set(gtk.DEST_DEFAULT_ALL,
                [("text/uri-list", 0, 1)], gtk.gdk.ACTION_COPY)
        self.connect('drag_data_received', self._drag_receive)

        # prepare to show
        self.load_settings()
        self.update_pull_setting()
        gtklib.idle_add_single_call(self.finalize_startup)

    def create_bottombox(self):
        self.buttonhbox = gtk.HBox()
        self.updatetip = gtk.Button(_('Update to branch tip'))
        self.updatetip.connect('clicked', self._update_to_tip)
        self.buttonhbox.pack_start(self.updatetip, False, False, 2)
        self.basevbox.pack_start(self.buttonhbox, False, False, 2)

    def finalize_startup(self, *args):
        self.create_bottombox()
        def pollstdout(*args):
            while True:
                # blocking read of stdout pipe
                o = os.read(self.readfd, 1024)
                if o:
                    self.stdoutq.put(o)
                else:
                    break
        thread = threading.Thread(target=pollstdout, args=[])
        thread.start()

    def update_pull_setting(self):
        ppull = self.repo.ui.config('tortoisehg', 'postpull', 'none')
        for (index, (name, label)) in enumerate(self.ppulldata):
            if ppull == name:
                pos = index
                break;
        else:
            pos = [index for (index, (name, label))
                    in enumerate(self.ppulldata) if name == 'none'][0]
        self.ppullcombo.set_active(pos)

    def show_dialog(self, dlg):
        # copy from history.py
        dlg.set_transient_for(self)
        dlg.show_all()
        dlg.present()
        if gtk.pygtk_version < (2, 12, 0):
            # Workaround for old PyGTK (< 2.12.0) issue.
            # See background of this: f668034aeda3
            dlg.set_transient_for(None)

    def fill_path_combo(self):
        self.pathlist.clear()
        for alias, path in self.paths:
            path = url.hidepassword(path)
            self.pathlist.append([hglib.toutf(path), hglib.toutf(alias)])

    def _drag_receive(self, widget, context, x, y, selection, targetType, time):
        if time != self.last_drop_time:
            files = selection.get_uris()
            gtklib.idle_add_single_call(self._set_path, files[0])
            self.last_drop_time = time

    def _set_path(self, uri):
        if not uri.startswith('file://'):
            return
        path = urllib.unquote(uri[7:])
        if paths.find_root(path) == path:
            self.pathtext.set_text(hglib.toutf(path))
        elif not os.path.isdir(path) and path.endswith('.hg'):
            self.pathtext.set_text(hglib.toutf(path))

    def update_buttons(self):
        try:
            # open a new repo, rebase can confuse cached repo
            repo = hg.repository(ui.ui(), path=self.root)
        except error.RepoError:
            return

        wc = repo[None]
        bhead = repo.branchtags().get(wc.branch())
        parents = repo.parents()
        if len(parents) > 1 or parents[0].node() == bhead or not bhead:
            self.buttonhbox.hide()
        else:
            self.buttonhbox.show()
        self.repo = repo

    def _update_to_tip(self, button):
        def update_notify(arg):
            if self.notify_func:
                self.notify_func(self.notify_args)
            self.update_buttons()

        wc = self.repo[None]
        dialog = update.UpdateDialog(wc.branch())
        dialog.set_notify_func(update_notify, None)
        self.show_dialog(dialog)

    def get_paths(self, sort="value"):
        """ retrieve symbolic paths """
        try:
            self.ui = ui.ui()
            self.repo = hg.repository(self.ui, path=self.root)
            uipaths = self.repo.ui.configitems('paths')
            if sort:
                if sort == "value":
                    sortfunc = lambda a,b: cmp(a[1], b[1])
                elif sort == "name":
                    sortfunc = lambda a,b: cmp(a[0], b[0])
                else:
                    raise _("unknown sort key '%s'") % sort
                uipaths.sort(sortfunc)
            return uipaths
        except error.RepoError:
            return None

    def btn_remotepath_clicked(self, button):
        """ select source folder to clone """
        result = gtklib.NativeFolderSelectDialog(
                        initial=self.root,
                        title=_('Select Repository')).run()
        if result:
            self.pathtext.set_text(result)

    def btn_bundlepath_clicked(self, button):
        """ select bundle to read from """
        result = gtklib.NativeSaveFileDialogWrapper(
                        title=_('Select Bundle'),
                        initial=self.root,
                        filter=((_('Bundle (*.hg)'), '*.hg'),
                                (_('Bundle (*)'), '*.*')),
                        open=True).run()
        if result:
            self.pathtext.set_text(result)

    def should_live(self):
        if self.cmd_running():
            dialog.error_dialog(self, _('Cannot close now'),
                    _('command is running'))
            return True
        else:
            self.update_settings()
            self._settings.write()
            os.dup2(self.oldstdout, sys.__stdout__.fileno())
            os.close(self.oldstdout)
            return False

    def delete(self, widget, event):
        if not self.should_live():
            self.destroy()

    def toolbutton(self, stock, label, handler,
                    menu=None, userdata=None, tip=None):
        if menu:
            tbutton = gtk.MenuToolButton(stock)
            tbutton.set_menu(menu)
        else:
            tbutton = gtk.ToolButton(stock)

        tbutton.set_label(label)
        if tip:
            tbutton.set_tooltip(self.tips, tip)
        tbutton.connect('clicked', handler, userdata)
        return tbutton

    def get_advanced_options(self):
        opts = {}
        if self.showpatch.get_active():
            opts['patch'] = ['--patch']
        if self.nomerge.get_active():
            opts['no-merges'] = ['--no-merges']
        if self.force.get_active():
            opts['force'] = ['--force']
        if self.newestfirst.get_active():
            opts['newest-first'] = ['--newest-first']
        remotecmd = self.cmdentry.get_text().strip()
        if remotecmd != "":
            opts['remotecmd'] = ['--remotecmd', remotecmd]
        target_rev = self.reventry.get_text().strip()
        if target_rev != "":
            opts['rev'] = ['--rev', target_rev]

        return opts

    def pull_clicked(self, toolbutton, data=None):
        sel = self.ppullcombo.get_active_text()
        ppull = [name for (name, label) in self.ppulldata if sel == label][0]
        aopts = self.get_advanced_options()
        if ppull == 'fetch':
            cmd = ['fetch', '--message', 'merge']
            # load the fetch extension explicitly
            hglib.loadextension(self.ui, 'fetch')
        else:
            cmd = ['pull']
            cmd += aopts.get('force', [])
            cmd += aopts.get('remotecmd', [])
            if ppull == 'update':
                cmd.append('--update')
            elif ppull == 'rebase':
                cmd.append('--rebase')
                # load the rebase extension explicitly
                hglib.loadextension(self.ui, 'rebase')
        cmd += aopts.get('rev', [])
        self.exec_cmd(cmd)

    def push_clicked(self, toolbutton, data=None):
        aopts = self.get_advanced_options()
        cmd = ['push']
        cmd += aopts.get('rev', [])
        cmd += aopts.get('force', [])
        cmd += aopts.get('remotecmd', [])
        self.exec_cmd(cmd)

    def conf_clicked(self, toolbutton, data=None):
        newpath = hglib.fromutf(self.pathtext.get_text()).strip()
        for alias, path in self.paths:
            if newpath in (path, url.hidepassword(path)):
                newpath = None
                break
        dlg = thgconfig.ConfigDialog(True)
        dlg.show_all()
        if newpath:
            dlg.new_path(newpath, 'default')
        else:
            dlg.focus_field('tortoisehg.postpull')
        dlg.run()
        dlg.hide()
        self.paths = self.get_paths()
        self.fill_path_combo()
        self.update_pull_setting()

    def email_clicked(self, toolbutton, data=None):
        opts = []
        path = hglib.fromutf(self.pathtext.get_text()).strip()
        rev = self.get_advanced_options().get('rev')
        if path:
            opts.extend(['--outgoing', path])
        elif not rev:
            dialog.info_dialog(self, _('No repository selected'),
                        _('Select a peer repository to compare with'))
            self.pathbox.grab_focus()
            return
        if rev:
            opts.extend(rev)
        dlg = hgemail.EmailDialog(self.root, opts)
        self.show_dialog(dlg)

    def shelve_clicked(self, toolbutton, data=None):
        dlg = thgshelve.run(self.ui)
        dlg.display()

    def incoming_clicked(self, toolbutton, data=None):
        aopts = self.get_advanced_options()
        cmd = ['incoming']
        cmd += aopts.get('rev', [])
        cmd += aopts.get('patch', [])
        cmd += aopts.get('no-merges', [])
        cmd += aopts.get('force', [])
        cmd += aopts.get('newest-first', [])
        cmd += aopts.get('remotecmd', [])
        self.exec_cmd(cmd)

    def outgoing_clicked(self, toolbutton, data=None):
        aopts = self.get_advanced_options()
        cmd = ['outgoing']
        cmd += aopts.get('rev', [])
        cmd += aopts.get('patch', [])
        cmd += aopts.get('no-merges', [])
        cmd += aopts.get('force', [])
        cmd += aopts.get('newest-first', [])
        cmd += aopts.get('remotecmd', [])
        self.exec_cmd(cmd)

    def stop_clicked(self, toolbutton, data=None):
        if self.cmd_running():
            try:
                self.hgthread.terminate()
            except ValueError:
                pass # race, thread was already terminated
            self.stop_button.set_sensitive(False)

    def exec_cmd(self, cmd):
        if self.cmd_running():
            dialog.error_dialog(self, _('Cannot run now'),
                _('Please try again after the previous command is completed'))
            return

        self.stop_button.set_sensitive(True)

        proxy_host = ui.ui().config('http_proxy', 'host', '')
        use_proxy = self.use_proxy.get_active()
        text_entry = self.pathbox.get_child()
        remote_path = hglib.fromutf(text_entry.get_text()).strip()
        remote_path = hglib.validate_synch_path(remote_path, self.repo)

        cmdline = cmd[:]
        cmdline += ['--verbose']
        if proxy_host and not use_proxy:
            cmdline += ["--config", "http_proxy.host="]
        cmdline += ['--', remote_path]
        self.lastcmd = cmdline

        # show command to be executed
        self.write("", False)

        # execute command and show output on text widget
        gobject.timeout_add(10, self.process_queue)
        self.hgthread = hgthread.HgThread(cmdline, parent=self)
        self.hgthread.start()
        self.stbar.begin()
        self.stbar.set_text('hg ' + ' '.join(cmd))

        self.add_src_to_recent(remote_path)

    def cmd_running(self):
        if self.hgthread and self.hgthread.isAlive():
            return True
        else:
            return False

    def add_src_to_recent(self, src):
        # add src path to recent list in history (read by clone tool)
        self._settings.mrul('src_paths').add(src)
        self._settings.write()

    def flush(self, *args):
        pass

    def write(self, msg, append=True):
        msg = hglib.toutf(msg)
        if append:
            enditer = self.textbuffer.get_end_iter()
            self.textbuffer.insert(enditer, msg)
            self.textview.scroll_to_mark(self.textbuffer.get_insert(), 0)
        else:
            self.textbuffer.set_text(msg)

    def write_err(self, msg):
        enditer = self.textbuffer.get_end_iter()
        self.textbuffer.insert_with_tags_by_name(enditer, msg, 'error')
        self.textview.scroll_to_mark(self.textbuffer.get_insert(), 0)

    def process_queue(self):
        """
        Handle all the messages currently in the queue (if any).
        """
        self.hgthread.process_dialogs()
        while self.hgthread.getqueue().qsize():
            try:
                msg = self.hgthread.getqueue().get(0)
                self.write(msg)
            except Queue.Empty:
                pass
        while self.hgthread.geterrqueue().qsize():
            try:
                msg = self.hgthread.geterrqueue().get(0)
                self.write_err(msg)
            except Queue.Empty:
                pass
        while self.stdoutq.qsize():
            try:
                msg = self.stdoutq.get(0)
                self.write_err(msg)
            except Queue.Empty:
                pass

        if self.cmd_running():
            return True
        else:
            # Update button states
            self.update_buttons()
            self.stbar.end()
            self.stop_button.set_sensitive(False)
            if self.hgthread.return_code() is None:
                self.write_err(_('[command interrupted]'))
            if not self.notify_func or self.lastcmd[0] != 'pull':
                return False
            if ' '.join(self.lastcmd[:2]) == 'pull --rebase':
                # disable notification; rebase can be poisonous
                self.notify_func = None
                self.notify_args = None
            else:
                self.notify_func(self.notify_args)
            return False # Stop polling this function

    AdvancedDefaults = {
        'expander.expanded': False,
        'reventry.text': '',
        'cmdentry.text': '',
        'force.active': False,
        'showpatch.active': False,
        'newestfirst.active': False,
        'nomerge.active': False,}

    def expanded(self, expander):
        if not expander.get_expanded():
            self.load_settings(SynchDialog.AdvancedDefaults.get)

    def load_settings(self, get_value = None):
        get_value = get_value or self._settings.get_value
        for key, default in SynchDialog.AdvancedDefaults.iteritems():
            member, attr = key.split('.')
            value = get_value(key, default)
            getattr(getattr(self, member), 'set_%s'%attr)(value)

    def update_settings(self, set_value = None):
        set_value = set_value or self._settings.set_value
        for key, default in SynchDialog.AdvancedDefaults.iteritems():
            member, attr = key.split('.')
            value = getattr(getattr(self, member), 'get_%s'%attr)()
            set_value(key, value)

    def add_to_popup(self, textview, menu):
        menu_items = (('----', None),
                      (_('Toggle _Wordwrap'), self.toggle_wordwrap),
                     )
        for label, handler in menu_items:
            if label == '----':
                menuitem = gtk.SeparatorMenuItem()
            else:
                menuitem = gtk.MenuItem(label)
            if handler:
                menuitem.connect('activate', handler)
            menu.append(menuitem)
        menu.show_all()

    def toggle_wordwrap(self, sender):
        if self.textview.get_wrap_mode() != gtk.WRAP_NONE:
            self.textview.set_wrap_mode(gtk.WRAP_NONE)
        else:
            self.textview.set_wrap_mode(gtk.WRAP_WORD)

    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = args


def run(ui, *pats, **opts):
    return SynchDialog(pats, opts.get('pushmode'))

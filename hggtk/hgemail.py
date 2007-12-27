#
# hgemail.py - TortoiseHg's dialog for sending patches via email
#
# Copyright (C) 2007 Steve Borho <steve@borho.org>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import sys
import gtk
import pango
import shelve
import shlib
from dialog import *
from mercurial import hg, ui
from thgconfig import ConfigDialog
from hgcmd import CmdDialog

class EmailDialog(gtk.Dialog):
    """ Send patches or bundles via email """
    def __init__(self, root='', revargs=[]):
        """ Initialize the Dialog """
        buttons = (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        super(EmailDialog, self).__init__(flags=gtk.DIALOG_MODAL, 
                                           buttons=buttons)
        #shlib.set_tortoise_icon(self, 'menucheckout.ico')
        self.root = root
        self.revargs = revargs
        
        self._button_conf = gtk.Button('Preferences', gtk.STOCK_PREFERENCES)
        self._button_conf.connect('clicked', self._on_conf_clicked)
        self.action_area.pack_end(self._button_conf)

        self._button_send = gtk.Button('Send', gtk.STOCK_OK)
        self._button_send.connect('clicked', self._on_send_clicked)
        self.action_area.pack_end(self._button_send)

        # set dialog title
        title = "Email Mercurial Patches"
        self.set_title(title)
        self.set_default_size(620, 400)

        hbox = gtk.HBox()
        envframe = gtk.Frame('Envelope')
        flagframe = gtk.Frame('Options')
        hbox.pack_start(envframe, True, True, 4)
        hbox.pack_start(flagframe, False, False, 4)
        self.vbox.pack_start(hbox, False, True, 4)

        vbox = gtk.VBox()
        envframe.add(vbox)

        # To: combo box
        hbox = gtk.HBox()
        self._tolist = gtk.ListStore(str)
        self._tobox = gtk.ComboBoxEntry(self._tolist, 0)
        hbox.pack_start(gtk.Label('To:'), False, False, 4)
        hbox.pack_start(self._tobox, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)

        # Cc: combo box
        hbox = gtk.HBox()
        self._cclist = gtk.ListStore(str)
        self._ccbox = gtk.ComboBoxEntry(self._cclist, 0)
        hbox.pack_start(gtk.Label('Cc:'), False, False, 4)
        hbox.pack_start(self._ccbox, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)

        # From: combo box
        hbox = gtk.HBox()
        self._fromlist = gtk.ListStore(str)
        self._frombox = gtk.ComboBoxEntry(self._fromlist, 0)
        hbox.pack_start(gtk.Label('From:'), False, False, 4)
        hbox.pack_start(self._frombox, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)

        vbox = gtk.VBox()
        flagframe.add(vbox)

        self._git = gtk.CheckButton("Use extended (git) patch format")
        vbox.pack_start(self._git, True, True, 4)

        self._plain = gtk.CheckButton("Plain, do not prepend HG header")
        vbox.pack_start(self._plain, True, True, 4)

        self._bundle = gtk.CheckButton("Send single binary bundle, not patches")
        vbox.pack_start(self._bundle, True, True, 4)

        self.descview = gtk.TextView(buffer=None)
        self.descview.set_editable(False)
        self.descview.modify_font(pango.FontDescription("Monospace"))
        self.descbuffer = self.descview.get_buffer()
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.add(self.descview)
        frame = gtk.Frame('Patch (list) Description')
        frame.set_border_width(4)
        frame.add(scrolledwindow)
        self.vbox.pack_start(frame, True, True, 4)
        self.connect('map_event', self._on_window_map_event)

    def _on_window_map_event(self, event, param):
        self._refresh()

    def _refresh(self):
        def fill_history(history, vlist, cpath):
            vlist.clear()
            if cpath not in history:
                return
            for v in history[cpath]:
                vlist.append([v])

        history = shlib.read_history()
        try:
            repo = hg.repository(ui.ui(), path=self.root)
            self.repo = repo
        except hg.RepoError:
            self.repo = None
            return

        if repo.ui.config('extensions', 'patchbomb') is not None:
            pass
        elif repo.ui.config('extensions', 'hgext.patchbomb') is not None:
            pass
        else:
            error_dialog('Email not enabled',
                    'You must enable the patchbomb extension to use this tool')
            self.response(gtk.RESPONSE_CANCEL)

        self._tobox.get_child().set_text(repo.ui.config('email', 'to', ''))
        self._ccbox.get_child().set_text(repo.ui.config('email', 'cc', ''))
        self._frombox.get_child().set_text(repo.ui.config('email', 'from', ''))
        fill_history(history, self._tolist, 'email.to')
        fill_history(history, self._cclist, 'email.cc')
        fill_history(history, self._fromlist, 'email.from')

        # See if user has set flags in defaults.email
        defaults = repo.ui.config('defaults', 'email', '').split()
        if '-g' in defaults:      self._git.set_active(True)
        if '-b' in defaults:      self._bundle.set_active(True)
        if '--plain' in defaults: self._plain.set_active(True)

    def _on_conf_clicked(self, button):
        dlg = ConfigDialog(self.root, False, 'email.from')
        dlg.show_all()
        dlg.run()
        dlg.hide()
        self._refresh()

    def _on_send_clicked(self, button):
        def record_new_value(cpath, history, newvalue):
            if cpath not in history:
                history[cpath] = []
            elif newvalue in history[cpath]:
                history[cpath].remove(newvalue)
            history[cpath].insert(0, newvalue)

        totext = self._tobox.get_child().get_text()
        cctext = self._ccbox.get_child().get_text()
        fromtext = self._frombox.get_child().get_text()

        if not totext:
            info_dialog('Info required', 'You must specify a recipient')
            self._tobox.grab_focus()
            return
        if not fromtext:
            info_dialog('Info required', 'You must specify a sender address')
            self._frombox.grab_focus()
            return
        if not self.repo:
            return

        if self.repo.ui.config('email', 'method', 'smtp') == 'smtp':
            if not self.repo.ui.config('smtp', 'host'):
                info_dialog('Info required', 'You must configure SMTP')
                dlg = ConfigDialog(self.root, False, 'smtp.host')
                dlg.show_all()
                dlg.run()
                dlg.hide()
                self._refresh()
                return

        history = shlib.read_history()
        record_new_value('email.to', history, totext)
        record_new_value('email.cc', history, cctext)
        record_new_value('email.from', history, fromtext)
        shlib.save_history(history)

        cmdline = ['hg', 'email', '-f', fromtext, '-t', totext, '-c', cctext]
        if self._bundle.get_active():   cmdline += ['--bundle']
        elif self._plain.get_active():  cmdline += ['--plain']
        elif self._git.get_active():    cmdline += ['--git']
        cmdline.extend(self.revargs)
        print 'cmdline =', cmdline
        # TODO: --subject and --desc
        dlg = CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()

def run(root='', **opts):
    # In most use cases, this dialog will be launched by other
    # hggtk tools like glog and synch.  It's not expected to be
    # used from hgproc or the command line.  I leave this path in
    # place for testing purposes.
    dialog = EmailDialog(root, ['tip'])
    dialog.show_all()
    dialog.connect('response', gtk.main_quit)
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or os.getcwd()
    run(**opts)

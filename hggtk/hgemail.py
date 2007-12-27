#
# email.py - TortoiseHg's dialog for sending patches via email
#
# Copyright (C) 2007 Steve Borho <steve@borho.org>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import sys
import gtk
import pango
from dialog import *
from shlib import set_tortoise_icon
from hglib import HgThread

class EmailDialog(gtk.Dialog):
    """ Send patches or bundles via email """
    def __init__(self, root='', revargs=[]):
        """ Initialize the Dialog """
        buttons = (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        super(EmailDialog, self).__init__(flags=gtk.DIALOG_MODAL, 
                                           buttons=buttons)
        #set_tortoise_icon(self, 'menucheckout.ico')
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
        self._tolist = gtk.ListStore(str, str)
        self._tobox = gtk.ComboBoxEntry(self._tolist, 0)
        hbox.pack_start(gtk.Label('To:'), False, False, 4)
        hbox.pack_start(self._tobox, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)

        # Cc: combo box
        hbox = gtk.HBox()
        self._cclist = gtk.ListStore(str, str)
        self._ccbox = gtk.ComboBoxEntry(self._cclist, 0)
        hbox.pack_start(gtk.Label('Cc:'), False, False, 4)
        hbox.pack_start(self._ccbox, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)

        # From: combo box
        hbox = gtk.HBox()
        self._fromlist = gtk.ListStore(str, str)
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
        self._refresh()

    def _refresh(self):
        # TODO: Allocate a repo object, load dialog from current
        # configuration.  Check for -b, -p, -g in defaults.email
        pass

    def _on_conf_clicked(self, button):
        from thgconfig import ConfigDialog
        dlg = ConfigDialog(self.root, False, 'email.from')
        dlg.show_all()
        dlg.run()
        dlg.hide()

    def _on_send_clicked(self, button):
        # TODO: check for prerequisites, launch config dialog if no
        # method or SMTP host is configured
        # run hgcmd or return command line to caller?
        pass
        
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

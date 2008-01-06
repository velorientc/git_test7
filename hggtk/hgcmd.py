#
# A simple dialog to execute random command for TortoiseHg
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import pygtk
pygtk.require("2.0")

import gtk
import gobject
import pango
import os
import threading
import Queue
from hglib import HgThread
from shlib import set_tortoise_icon, get_system_times

class CmdDialog(gtk.Dialog):
    def __init__(self, cmdline, progressbar=False, width=520, height=400):
        title = 'hg ' + ' '.join(cmdline[1:])
        gtk.Dialog.__init__(self,
                            title=title,
                            flags=gtk.DIALOG_MODAL, 
                            #buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)
                            )

        set_tortoise_icon(self, 'hg.ico')
        self.cmdline = cmdline

        # construct dialog
        self.set_default_size(width, height)
        
        self._button_ok = gtk.Button("OK")
        self.action_area.pack_end(self._button_ok)
        
        self.pbar = None
        if progressbar:
            self.last_pbar_update = 0
            
            # Create a centering alignment object
            align = gtk.Alignment(0.0, 0.0, 1, 0)
            self.vbox.pack_start(align, False, False, 3)
            align.show()
            
            # create the progress bar
            self.pbar = gtk.ProgressBar()
            align.add(self.pbar)
            self.pbar.pulse()
            self.pbar.show()
        
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.textview = gtk.TextView(buffer=None)
        self.textview.set_editable(False)
        self.textview.modify_font(pango.FontDescription("Monospace"))
        scrolledwindow.add(self.textview)
        self.textbuffer = self.textview.get_buffer()
        
        self.vbox.pack_start(scrolledwindow, True, True)
        self.connect('map_event', self._on_window_map_event)

        self._button_ok.connect('clicked', self._on_ok_clicked)
        self.show_all()

    def _on_ok_clicked(self, button):
        """ Ok button clicked handler. """
        self.response(gtk.RESPONSE_ACCEPT)
        
    def _on_window_map_event(self, event, param):
        self.hgthread = HgThread(self.cmdline[1:])
        self.hgthread.start()
        self._button_ok.set_sensitive(False)
        gobject.timeout_add(10, self.process_queue)
    
    def write(self, msg, append=True):
        msg = unicode(msg, 'iso-8859-1')
        if append:
            enditer = self.textbuffer.get_end_iter()
            self.textbuffer.insert(enditer, msg)
        else:
            self.textbuffer.set_text(msg)

    def process_queue(self):
        """
        Handle all the messages currently in the queue (if any).
        """
        self.hgthread.process_dialogs()
        enditer = self.textbuffer.get_end_iter()
        while self.hgthread.getqueue().qsize():
            try:
                msg = self.hgthread.getqueue().get(0)
                msg = unicode(msg, 'iso-8859-1')
                self.textbuffer.insert(enditer, msg)
            except Queue.Empty:
                pass
        self.update_progress()
        if threading.activeCount() == 1:
            self._button_ok.set_sensitive(True)
            return False # Stop polling this function
        else:
            return True

    def update_progress(self):
        if not self.pbar:
            return          # progress bar not enabled
            
        if threading.activeCount() == 1:
            self.pbar.set_fraction(1.0)
        else:
            # pulse the progress bar every ~100ms
            tm = get_system_times()[4]
            if tm - self.last_pbar_update < 0.100:
                return
            self.last_pbar_update = tm
            self.pbar.pulse()

def run(cmdline=[], progressbar=False, **opts):
    dlg = CmdDialog(cmdline, progressbar)
    dlg.connect('response', gtk.main_quit)
    dlg.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()
    
if __name__ == "__main__":
    import sys
    #run(sys.argv)
    run(sys.argv, True)


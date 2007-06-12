#
# A simple dialog to execute random command for TortoiseHg
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import pygtk
pygtk.require("2.0")

import gtk
import pango
import subprocess
import threading
from mercurial import hg, commands, util

class CmdDialog(gtk.Dialog):
    def __init__(self, cmdline, width=520, height=400):
        self.cmdline = cmdline
        
        if type(cmdline) == type([]):
            title = " ".join(cmdline)
        else:
            title = cmdline
            
        gtk.Dialog.__init__(self,
                            title=title,
                            flags=gtk.DIALOG_MODAL, 
                            #buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)
                            )
        
        # construct dialog
        self.set_default_size(width, height)
        
        self._button_ok = gtk.Button("OK")
        self._button_ok.connect('clicked', self._on_commit_clicked)
        self.action_area.pack_end(self._button_ok)
        
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.textview = gtk.TextView(buffer=None)
        self.textview.set_editable(False)
        self.textview.modify_font(pango.FontDescription("Monospace"))
        scrolledwindow.add(self.textview)
        self.textview.set_editable(False)
        self.textbuffer = self.textview.get_buffer()
        
        self.vbox.pack_start(scrolledwindow, True, True)
        self.vbox.show_all()

        self.connect('map_event', self._on_window_map_event)

    def _on_commit_clicked(self, button):
        """ Commit button clicked handler. """
        self.response(gtk.RESPONSE_OK)
        
    def _on_window_map_event(self, event, param):
        self._exec_cmd()
    
    def _exec_cmd(self):
        self.write("", False)
        
        # show command to be executed
        if type(self.cmdline) == type([]):
            cmd = " ".join(self.cmdline)
        else:
            cmd = self.cmdline
        self.write("%s\n" % cmd)
        self.write("=" * 60 + "\n")
        
        # execute comnand and show output on text widget
        self._start_thread()

    def write(self, msg, append=True):
        gtk.gdk.threads_enter()
        msg = unicode(msg, 'iso-8859-1')
        if append:
            enditer = self.textbuffer.get_end_iter()
            self.textbuffer.insert(enditer, msg)
        else:
            self.textbuffer.set_text(msg)
        gtk.gdk.threads_leave()

    def _start_thread(self):
        self.thread1 = threading.Thread(target=self._do_popen)
        self.thread1.start()
        
    def _do_popen(self):        
        if not self.cmdline:
            return

        #print("start popen: %s\n" % self.cmdline)
        pop = subprocess.Popen(self.cmdline, 
                               shell=True,
                               stderr=subprocess.STDOUT,
                               stdout=subprocess.PIPE,
                               stdin=subprocess.PIPE)

        self._button_ok.set_sensitive(False)
        try:
            line = 0
            blocksize = 1024
            while pop.poll() == None:
                if line < 100:
                    out = pop.stdout.readline()
                    line += 1
                else:
                    out = pop.stdout.read(blocksize)
                    if blocksize < 1024 * 50:
                        blocksize *= 2
                self.write(out)
            out = pop.stdout.read()
            self.write(out)
        except IOError:
            pass

        self._button_ok.set_sensitive(True)

def run(cmd=''):
    gtk.gdk.threads_init()
    dlg = CmdDialog(cmd)
    gtk.gdk.threads_enter()
    dlg.run()
    gtk.gdk.threads_leave()
    
if __name__ == "__main__":
    import sys
    run(sys.argv[1:])


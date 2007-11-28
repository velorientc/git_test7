#
# TortoiseHg dialog to start web server
#
# Copyright (C) 2007 Steve Borho <steve@borho.org>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

try:
    import pygtk
    pygtk.require("2.0")
except:
    pass

import gtk
import gobject
import os
import pango
import Queue
import signal
import socket
import subprocess
import sys
from tempfile import mkstemp
import threading
from dialog import question_dialog, error_dialog, info_dialog
from mercurial import hg, ui, cmdutil, util
from mercurial.i18n import _
from mercurial.node import *

class ServeDialog(gtk.Dialog):
    """ Dialog to run web server"""
    def __init__(self, cwd='', repo = None):
        """ Initialize the Dialog """
        super(ServeDialog, self).__init__(flags=gtk.DIALOG_MODAL)

        self._button_start = gtk.Button("Start")
        self._button_start.connect('clicked', self._on_start_clicked)
        self.action_area.pack_end(self._button_start)

        self._button_stop = gtk.Button("Stop")
        self._button_stop.connect('clicked', self._on_stop_clicked)
        self.action_area.pack_end(self._button_stop)
        self._button_stop.set_sensitive(False)

        self._repo = repo
        if cwd: os.chdir(cwd)
        
        # set dialog title
        title = "hg serve --pid-file pid.tmp"
        title += " - %s" % (os.getcwd())
        self.set_title(title)
        self.queue = Queue.Queue()
        
        self.set_default_size(730, 300)
        ewidth = 16
        
        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Label("HTTP Port:")
        lbl.set_property("width-chars", ewidth)
        lbl.set_alignment(0, 0.5)
        self._port_input = gtk.Entry()
        self._port_input.set_text("8000")
        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self._port_input, False, False)
        self.vbox.pack_start(revbox, False, False, 2)

        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.textview = gtk.TextView(buffer=None)
        self.textview.set_editable(False)
        self.textview.modify_font(pango.FontDescription("Monospace"))
        scrolledwindow.add(self.textview)
        self.textview.set_editable(False)
        self.textbuffer = self.textview.get_buffer()
        self.vbox.pack_start(scrolledwindow, True, True)

        # show them all
        self.vbox.show_all()

    def _on_start_clicked(self, button):
        # gather input data
        try:
            port = int(self._port_input.get_text())
        except:
            error_dialog("Invalid port 2048..65535", "Defaulting to 8000")
            port = None
        
        # start server
        (fd, filename) = mkstemp()
        self.cmdline = 'hg serve --pid-file ' + filename
        if self._repo:
            self.cmdline += ' --repository ' + self._repo
        if port:
            self.cmdline += ' --port %d' % port

        # run hg in unbuffered mode, so the output can be captured and
        # display a.s.a.p.
        os.environ['PYTHONUNBUFFERED'] = "1"
        #self.write(self.cmdline + '\n')
        self.write('Web server started, now available at ')
        self.write('http://%s:%d/\n' % (socket.getfqdn(), port))

        self._button_start.set_sensitive(False)
        self._button_stop.set_sensitive(True)

        # start hg operation on a subprocess and capture the output
        self.tmp_file = filename
        self.tmp_fd = fd
        self.proc = subprocess.Popen(self.cmdline, 
                               shell=True,
                               stderr=subprocess.STDOUT,
                               stdout=subprocess.PIPE,
                               stdin=subprocess.PIPE,
                               bufsize=1) # line buffered

        PollThread(self.proc, self.queue).start()
        gobject.timeout_add(10, self.process_queue)

    def _on_stop_clicked(self, button):
        if self.proc and self.proc.poll() == None:
            file = os.fdopen(self.tmp_fd, "r")
            pid = int(file.read())
            file.close()
            os.unlink(self.tmp_file)
            if os.name == 'nt':
                import win32api
                handle = win32api.OpenProcess(1, 0, pid)
                win32api.TerminateProcess(handle, 0)
            else:
                os.kill(pid, signal.SIGHUP)
            self.write('Web server stopped.\n')

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
        while self.queue.qsize():
            try:
                msg = self.queue.get(0)
                self.write(msg)
            except Queue.Empty:
                pass

        if threading.activeCount() == 1:
            self._button_start.set_sensitive(True)
            self._button_stop.set_sensitive(False)
            return False # Stop polling this function
        else:
            return True
        
class PollThread(threading.Thread):
    def __init__(self, proc, queue):
        self.proc = proc
        self.queue = queue
        threading.Thread.__init__(self)

    def run(self):
        try:
            while self.proc.poll() == None:
                out = self.proc.stdout.readline()
                if not out: break
                self.queue.put(out)
            out = self.proc.stdout.read()
            self.queue.put(out)
        except IOError:
            pass

def run(cwd='', repo=None):
    dialog = ServeDialog(cwd, repo)
    dialog.run()
    dialog._on_stop_clicked(None)
    dialog.hide()
    
if __name__ == "__main__":
    import sys
    if len(sys.argv) == 2:
        run(os.getcwd(), sys.argv[1])
    else:
        run(os.getcwd())

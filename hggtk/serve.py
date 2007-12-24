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
from shlib import set_tortoise_icon

class ServeDialog(gtk.Dialog):
    """ Dialog to run web server"""
    def __init__(self, cwd='', root='', hgpath='hg'):
        """ Initialize the Dialog """
        super(ServeDialog, self).__init__(flags=gtk.DIALOG_MODAL)

        set_tortoise_icon(self, 'proxy.ico')
        self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_NORMAL)

        self.connect('delete-event', self._delete)
        self.connect('response', self._response)

        self._btn_close = gtk.Button("Close")
        self._btn_close.connect('clicked', self._close_clicked)
        self.action_area.pack_end(self._btn_close)

        self.proc = None
        self._url = None
        self._root = root
        self._hgpath = hgpath
        if cwd: os.chdir(cwd)
        
        try:
            repo = hg.repository(ui.ui(), path=root)
            self.defport = repo.ui.config('web', 'port') or '8000'
        except hg.RepoError:
            self.defport = '8000'

        # set dialog title
        title = "hg serve"
        title += " - %s" % (os.getcwd())
        self.set_title(title)
        self.queue = Queue.Queue()
        
        self.set_default_size(500, 300)
        
        # toolbar
        self.tbar = gtk.Toolbar()
        self._button_start = self._toolbutton(gtk.STOCK_MEDIA_PLAY,
                                              'Start', 
                                              self._on_start_clicked,
                                              None)
        self._button_stop  = self._toolbutton(gtk.STOCK_MEDIA_STOP,
                                              'Stop',
                                              self._on_stop_clicked,
                                              None)
        self._button_browse = self._toolbutton(gtk.STOCK_HOME,
                                              'Browse',
                                              self._on_browse_clicked,
                                              None)
        tbuttons = [
                self._button_start,
                gtk.SeparatorToolItem(),
                self._button_stop,
                gtk.SeparatorToolItem(),
                self._button_browse,
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        self.vbox.pack_start(self.tbar, False, False, 2)
        
        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Label("HTTP Port:")
        lbl.set_property("width-chars", 16)
        lbl.set_alignment(0, 0.5)
        self._port_input = gtk.Entry()
        self._port_input.set_text(self.defport)
        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self._port_input, False, False)
        self.vbox.pack_start(revbox, False, False, 2)

        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.textview = gtk.TextView(buffer=None)
        self.textview.set_editable(False)
        self.textview.modify_font(pango.FontDescription("Monospace"))
        scrolledwindow.add(self.textview)
        self.textview.set_editable(False)
        self.textbuffer = self.textview.get_buffer()
        self.vbox.pack_start(scrolledwindow, True, True)

        self._set_button_states()

    def _toolbutton(self, stock, label, handler, menu=None, userdata=None):
        if menu:
            tbutton = gtk.MenuToolButton(stock)
            tbutton.set_menu(menu)
        else:
            tbutton = gtk.ToolButton(stock)
            
        tbutton.set_label(label)
        tbutton.connect('clicked', handler, userdata)
        return tbutton
            
    def _close_clicked(self, *args):
        #if self._server_stopped() == True:
        self.response(gtk.RESPONSE_CLOSE)
        
    def _delete(self, widget, event):
        return True

    def _response(self, widget, response_id):
        if self._server_stopped() == False:
            widget.emit_stop_by_name('response')
        else:
            gtk.main_quit()
    
    def _server_stopped(self):
        '''
        check if server is running, or to terminate if running
        '''
        if self.proc and self.proc.poll() == None:
            if question_dialog("Really Exit?", "Server process is still running\n" +
                    "Exiting will stop the server.") != gtk.RESPONSE_YES:
                return False
            else:
                self._stop_server()
                return True
        else:
            return True

    def _set_button_states(self):
        if self.proc and self.proc.poll() == None:
            self._button_start.set_sensitive(False)
            self._button_stop.set_sensitive(True)
            self._button_browse.set_sensitive(True)
        else:
            self._button_start.set_sensitive(True)
            self._button_stop.set_sensitive(False)
            self._button_browse.set_sensitive(False)
            
    def _on_start_clicked(self, *args):
        self._start_server()
        self._set_button_states()
        
    def _on_stop_clicked(self, *args):
        self._stop_server()

    def _on_browse_clicked(self, *args):
        ''' launch default browser to view repo '''
        if self._url:
            def start_browser():
                if os.name == 'nt':
                    import win32api, win32con
                    win32api.ShellExecute(0, "open", self._url, None, "", 
                        win32con.SW_SHOW)
                else:
                    import gconf
                    client = gconf.client_get_default()
                    browser = client.get_string(
                            '/desktop/gnome/url-handlers/http/command') + '&'
                    os.system(browser % self._url)
            threading.Thread(target=start_browser).start()
    
    def _start_server(self):
        # gather input data
        try:
            port = int(self._port_input.get_text())
        except:
            try: port = int(self.defport)
            except: port = '8000'
            error_dialog("Invalid port 2048..65535", "Defaulting to " +
                    self.defport)
        
        # start server
        (fd, filename) = mkstemp()
        self.cmdline = [self._hgpath, 'serve', '--pid-file', filename]
        if self._root:
            self.cmdline.append('--repository')
            self.cmdline.append(self._root)
        self.cmdline.append('--port')
        self.cmdline.append(str(port))

        # run hg in unbuffered mode, so the output can be captured and
        # display a.s.a.p.
        os.environ['PYTHONUNBUFFERED'] = "1"
        #self.write(self.cmdline + '\n')
        self._url = 'http://%s:%d/' % (socket.getfqdn(), port)
        self.write('Web server started, now available at %s\n' % self._url)

        # start hg operation on a subprocess and capture the output
        self.tmp_file = filename
        self.tmp_fd = fd
        self.proc = subprocess.Popen(self.cmdline, 
                               shell=False,
                               stderr=subprocess.STDOUT,
                               stdout=subprocess.PIPE,
                               stdin=subprocess.PIPE,
                               bufsize=1) # line buffered

        PollThread(self.proc, self.queue).start()
        gobject.timeout_add(10, self.process_queue)
        
    def _stop_server(self):
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
            self._url = None
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
            self._set_button_states()
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

def run(cwd='', root='', hgpath='hg', **opts):
    dialog = ServeDialog(cwd, root, hgpath)
    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()
    
if __name__ == "__main__":
    import sys
    opts = {}
    opts['cwd'] = os.getcwd()
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or ''
    run(**opts)

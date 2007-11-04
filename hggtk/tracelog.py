#
# A PyGtk-based Python Trace Collector dialog
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import pygtk
pygtk.require("2.0")
import gtk
import gobject
import pango
import threading
import Queue
import win32trace

class TraceDialog(gtk.Dialog):
    def __init__(self, width=700, height=400):
        gtk.Dialog.__init__(self,
                            title="Python Trace Collector",
                            flags=gtk.DIALOG_MODAL,
                           )

        # construct dialog
        self.set_default_size(width, height)
        
        self._button_ok = gtk.Button("OK")
        self._button_ok.connect('clicked', self._on_ok_clicked)
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
        self.connect('delete_event', self._on_window_close_clicked)

    def _on_ok_clicked(self, button):
        self._stop_read_thread()
        self.response(gtk.RESPONSE_ACCEPT)
        
    def _on_window_close_clicked(self, event, param):
        self._stop_read_thread()
        
    def _on_window_map_event(self, event, param):
        self._begin_trace()
    
    def _begin_trace(self):
        self.queue = Queue.Queue()
        win32trace.InitRead()
        self.write("Collecting Python Trace Output...\n")
        gobject.timeout_add(10, self._process_queue)
        self._start_read_thread()
        
    def _start_read_thread(self):
        self._read_trace = True
        self.thread1 = threading.Thread(target=self._do_read_trace)
        self.thread1.start()

    def _stop_read_thread(self):
        self._read_trace = False

        # wait for worker thread to to fix Unhandled exception in thread
        self.thread1.join() 
        
    def _process_queue(self):
        """
        Handle all the messages currently in the queue (if any).
        """
        while self.queue.qsize():
            try:
                msg = self.queue.get(0)
                self.write(msg)
            except Queue.Empty:
                pass
                
        return True
        
    def _do_read_trace(self):
        """
        print buffer collected in win32trace
        """
        while self._read_trace:
            msg = win32trace.read()
            if msg:
                self.queue.put(msg)
        
    def write(self, msg, append=True):
        msg = unicode(msg, 'iso-8859-1')
        if append:
            enditer = self.textbuffer.get_end_iter()
            self.textbuffer.insert(enditer, msg)
        else:
            self.textbuffer.set_text(msg)

def run():
    dlg = TraceDialog()
    dlg.run()
    
if __name__ == "__main__":
    run()


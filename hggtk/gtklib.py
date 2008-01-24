#
# miscellaneous PyGTK classes and functions for TortoiseHg
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import pygtk
pygtk.require('2.0')
import gtk
import gobject
import pango

class StatusBar(gtk.HBox):
    def __init__(self, extra=None):
        gtk.HBox.__init__(self)
        self.pbar = gtk.ProgressBar()
        self.sttext = gtk.Label("")
        self.sttext.set_ellipsize(pango.ELLIPSIZE_END)
        self.sttext.set_alignment(0, 0.5)

        self.pbox = gtk.HBox()
        self.pbox.pack_start(gtk.VSeparator(), False, False)
        self.pbox.pack_start(self.pbar, False, False)
        
        self.pack_start(self.sttext, padding=1)
        if extra:
            self.pack_end(extra, False, False)
        self.pack_end(self.pbox, False, False, padding=1)
        self.show_all()
        
    def _pulse_timer(self, now=False):
        self.pbar.pulse()
        return True

    def begin(self, msg="Running", timeout=100):
        self.pbox.map()
        self.set_status_text(msg)
        self._timeout_event = gobject.timeout_add(timeout, self._pulse_timer)

    def end(self, msg="Done", unmap=True):
        gobject.source_remove(self._timeout_event)
        self.set_status_text(msg)
        if unmap:
            self.pbox.unmap()
        else:
            self.pbar.set_fraction(1.0)

    def set_status_text(self, msg):
        self.sttext.set_text(str(msg))
        
    def set_pulse_step(self, val):
        self.pbar.set_pulse_step(val)


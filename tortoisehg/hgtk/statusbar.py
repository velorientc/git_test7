# statusbar.py - status bar widget for TortoiseHg
#
# Copyright 2008 TK Soh <teekaysoh@gmail.com>
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import gobject

from tortoisehg.util.i18n import _

class StatusBar(gtk.HBox):
    def __init__(self, extra=None):
        gtk.HBox.__init__(self)
        self.idle_text = None
        self.started = False

        self.pbar = gtk.ProgressBar()
        self.sttext = gtk.Label("")
        self.sttext.set_alignment(0, 0.5)

        self.pbox = gtk.HBox()
        self.pbox.pack_start(gtk.VSeparator(), False, False)
        self.pbox.pack_start(self.pbar, False, False)

        self.pack_start(self.sttext, padding=4)
        if extra:
            self.pack_end(extra, False, False)
        self.right1_label = gtk.Label()
        self.pack_end(self.right1_label, False, False, padding=20)
        self.pack_end(self.pbox, False, False, padding=1)
        self.pbox.set_child_visible(False)
        self.right2_label = gtk.Label()
        self.pack_end(self.right2_label, False, False, padding=5)
        self.right3_label = gtk.Label()
        self.pack_end(self.right3_label, False, False, padding=20)
        self.show_all()

    def _pulse_timer(self, now=False):
        self.pbar.pulse()
        return True

    def begin(self, msg=_('Running'), timeout=100):
        self.pbox.set_child_visible(True)
        self.pbox.map()
        self.set_status_text(msg)
        self.started = True 
        self._timeout_event = gobject.timeout_add(timeout, self._pulse_timer)

    def end(self, msg=None, unmap=True):
        self.started = False 
        gobject.source_remove(self._timeout_event)

        t = ''
        if msg:
            t = msg
        elif self.idle_text:
            t = self.idle_text
        self.set_status_text(t)

        if unmap:
            self.pbox.unmap()
        else:
            self.pbar.set_fraction(1.0)

    def set_status_text(self, msg):
        self.sttext.set_text(str(msg))

    def set_idle_text(self, msg):
        self.idle_text = msg
        if msg and not self.started:
            self.set_status_text(msg)

    def set_right1_text(self, msg):
        self.right1_label.set_text(str(msg))

    def set_right2_text(self, msg):
        self.right2_label.set_text(str(msg))

    def set_right3_text(self, msg):
        self.right3_label.set_text(str(msg))

    def set_pulse_step(self, val):
        self.pbar.set_pulse_step(val)

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
from tortoisehg.hgtk import gtklib

ALIGN_MAP = {   gtk.JUSTIFY_LEFT: 0,
                gtk.JUSTIFY_CENTER: 0.5,
                gtk.JUSTIFY_RIGHT: 1}

class StatusBar(gtk.HBox):
    def __init__(self, extra=None):
        gtk.HBox.__init__(self)

        self.fields = {}
        self.boxes = {}

        self.idle_text = None
        self.timeout_id = None

        self.append_field('status', expand=True, sep=False)

        self.pbar = gtk.ProgressBar()
        self.pbar.set_no_show_all(True)
        self.append_widget(self.pbar, pack=gtk.PACK_START)

        gtklib.idle_add_single_call(self.after_init)

    ### public methods ###

    def begin(self, msg=_('Running...'), timeout=100):
        self.set_text(msg)
        self.pbar.show_all()
        if self.pbar.get_property('visible'):
            self.pbar.map()
        self.timeout_id = gobject.timeout_add(timeout, self.pulse_timer)

    def end(self, msg=None, unmap=True):
        if self.timeout_id:
            gobject.source_remove(self.timeout_id)
            self.timeout_id = None

        text = ''
        if msg:
            text = msg
        elif self.idle_text:
            text = self.idle_text
        self.set_text(text)

        if unmap:
            self.pbar.unmap()
        else:
            self.pbar.set_fraction(1.0)

    def set_text(self, msg, name='status'):
        try:
            label, box = self.fields[name], self.boxes[name]
        except KeyError:
            raise _('unknown field name: %s') % name

        if not msg and not name == 'status':
            label.set_text('')
            box.hide_all()
            box.unmap()
            box.set_no_show_all(True)
            return

        label.set_text(msg)
        if box.get_no_show_all():
            box.set_no_show_all(False)
            box.show_all()
            if box.get_property('visible'):
                box.map()

    def set_idle_text(self, msg):
        self.idle_text = msg
        if msg and self.timeout_id is None:
            self.set_text(msg, name='status')

    def append_widget(self, widget, expand=False, pack=gtk.PACK_START):
        if pack == gtk.PACK_START:
            packfunc = self.pack_start
        elif pack == gtk.PACK_END:
            packfunc = self.pack_end
        else:
            raise _('invalid pack direction: %s') % pack
        packfunc(widget, expand, expand, 2)

    def append_field(self, name, expand=False, pack=gtk.PACK_START,
                     align=gtk.JUSTIFY_LEFT, sep=True):
        label = gtk.Label()
        try:
            label.set_alignment(ALIGN_MAP[align], 0.5)
        except KeyError:
            raise _('invalid alignment value: %s') % align

        box = gtk.HBox()
        if sep:
            box.pack_start(gtk.VSeparator(), False, False, 2)
        box.pack_start(label, expand, expand, 2)
        self.append_widget(box, expand, pack)
        box.set_no_show_all(True)

        self.fields[name] = label
        self.boxes[name] = box

    def set_pulse_step(self, val):
        self.pbar.set_pulse_step(val)

    ### signal handlers ###

    def after_init(self, *args):
        self.pbar.set_no_show_all(False)

    def pulse_timer(self, now=False):
        self.pbar.pulse()
        return True

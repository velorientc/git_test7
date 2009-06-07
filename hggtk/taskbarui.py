#
# taskbarui.py - User interface for the TortoiseHg taskbar app
#
# Copyright (C) 2009 Steve Borho <steve@borho.org>
#

import os
import gtk
import gobject

from thgutil.i18n import _
from hggtk import gtklib

class TaskBarUI(gtk.Window):
    'User interface for the TortoiseHg taskbar application'
    def __init__(self, inputq):
        'Initialize the Dialog'
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        gtklib.set_tortoise_icon(self, 'hg.ico')
        gtklib.set_tortoise_keys(self)

        self.set_default_size(500, 220)
        self.set_title(_('TortoiseHg Taskbar'))

        vbox = gtk.VBox()
        self.add(vbox)

        frame = gtk.Frame(_('Event Log'))
        frame.set_border_width(2)
        vbox.pack_start(frame, True, True, 2)

        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.set_border_width(2)
        textview = gtk.TextView()
        textview.set_editable(False)
        scrolledwindow.add(textview)
        frame.add(scrolledwindow)
        gobject.timeout_add(10, self.pollq, inputq, textview)

        hbbox = gtk.HButtonBox()
        hbbox.set_layout(gtk.BUTTONBOX_END)
        vbox.pack_start(hbbox, False, False, 2)
        close = gtk.Button(_('Close'))
        close.connect('clicked', lambda x: self.destroy())

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)
        key, modifier = gtk.accelerator_parse('Escape')
        close.add_accelerator('clicked', accelgroup, key, 0,
                gtk.ACCEL_VISIBLE)
        hbbox.add(close)

    def pollq(self, queue, textview):
        'Poll the input queue'
        buf = textview.get_buffer()
        enditer = buf.get_end_iter()
        while queue.qsize():
            try:
                msg = queue.get(0)
                buf.insert(enditer, msg+'\n')
                textview.scroll_to_mark(buf.get_insert(), 0)
            except Queue.Empty:
                pass
        return True

def run(ui, *pats, **opts):
    return TaskBarUI(opts['queue'])

'''
import Queue
q = Queue.Queue()
q.put('Test1')
q.put('Test2')
from mercurial import ui
from hggtk import hgtk
hgtk.gtkrun(run(ui.ui(), queue=q))
'''

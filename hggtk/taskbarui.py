#
# taskbarui.py - User interface for the TortoiseHg taskbar app
#
# Copyright (C) 2009 Steve Borho <steve@borho.org>
#

import os
import gtk
import gobject

from thgutil.i18n import _
from thgutil import hglib, settings
from hggtk import gtklib

class TaskBarUI(gtk.Window):
    'User interface for the TortoiseHg taskbar application'
    def __init__(self, inputq, requestq):
        'Initialize the Dialog'
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        gtklib.set_tortoise_icon(self, 'hg.ico')
        gtklib.set_tortoise_keys(self)

        self.set_default_size(500, 220)
        self.set_title(_('TortoiseHg Taskbar'))

        vbox = gtk.VBox()
        self.add(vbox)

        frame = gtk.Frame(_('Exclude Paths'))
        frame.set_border_width(2)
        vbox.pack_start(frame, True, True, 2)

        tree = gtk.TreeView()
        tree.get_selection().set_mode(gtk.SELECTION_SINGLE)
        tree.set_enable_search(False)
        tree.set_reorderable(False)
        cell = gtk.CellRendererText()
        cell.set_property('editable', True)
        col = gtk.TreeViewColumn(_('Paths'), cell, text=0)
        tree.append_column(col)
        win = gtk.ScrolledWindow()
        win.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        win.set_border_width(4)
        win.add(tree)
        model = gtk.ListStore(str)
        tree.set_model(model)
        tree.set_headers_visible(False)

        fvbox = gtk.VBox()
        fvbox.pack_start(win, True, True, 2)
        bhbox = gtk.HBox()
        apply = gtk.Button(_('Apply'))
        add = gtk.Button(_('Add'))
        delete = gtk.Button(_('Del'))
        apply.connect('clicked', self.applyclicked, model, requestq)
        add.connect('clicked', self.addclicked, model, apply)
        delete.connect('clicked', self.delclicked, tree, apply)
        cell.connect('edited', self.edited, model, apply)
        bhbox.pack_start(add, False, False, 2)
        bhbox.pack_start(delete, False, False, 2)
        bhbox.pack_end(apply, False, False, 2)
        fvbox.pack_start(bhbox, False, False, 2)
        fvbox.set_border_width(2)
        frame.add(fvbox)

        apply.set_sensitive(False)
        set = settings.Settings('taskbar')
        for path in set.get_value('excludes', []):
            model.append([hglib.toutf(path)])

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

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)

        hbbox = gtk.HButtonBox()
        hbbox.set_layout(gtk.BUTTONBOX_END)
        vbox.pack_start(hbbox, False, False, 2)

        about = gtk.Button(_('About'))
        about.connect('clicked', self.about)
        key, modifier = gtk.accelerator_parse('Escape')
        hbbox.add(about)

        close = gtk.Button(_('Close'))
        close.connect('clicked', lambda x: self.destroy())
        key, modifier = gtk.accelerator_parse('Escape')
        close.add_accelerator('clicked', accelgroup, key, 0,
                gtk.ACCEL_VISIBLE)
        hbbox.add(close)

    def about(self, button):
        from hggtk import about
        dlg = about.AboutDialog()
        dlg.show_all()

    def applyclicked(self, button, model, requests):
        'apply button clicked'
        paths = [hglib.fromutf(r[0]) for r in model]
        set = settings.Settings('taskbar')
        set.set_value('excludes', paths)
        set.write()
        button.set_sensitive(False)
        requests.put('load-config')

    def edited(self, cell, path, new_text, model, applybutton):
        dirty = model[path][0] != new_text
        model[path][0] = new_text
        if dirty:
            applybutton.set_sensitive(True)

    def addclicked(self, button, model, applybutton):
        'add button clicked'
        model.append(['C:\\'])
        applybutton.set_sensitive(True)

    def delclicked(self, button, tree, applybutton):
        'delete button clicked'
        model, pathlist = tree.get_selection().get_selected_rows()
        if pathlist:
            del model[pathlist[0]]
            applybutton.set_sensitive(True)

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

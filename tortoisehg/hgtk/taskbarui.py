# taskbarui.py - User interface for the TortoiseHg taskbar app
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, settings, menuthg
from tortoisehg.hgtk import gtklib

shellcmds = '''about add clone commit datamine init log recovery
shelve synch status thgstatus userconf repoconf remove rename
revert serve update vdiff'''.split()

class TaskBarUI(gtk.Window):
    'User interface for the TortoiseHg taskbar application'
    def __init__(self, inputq, requestq):
        'Initialize the Dialog'
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        gtklib.set_tortoise_icon(self, 'hg.ico')
        gtklib.set_tortoise_keys(self)

        self.set_default_size(400, 520)
        self.set_title(_('TortoiseHg Taskbar'))

        about = gtk.Button(_('About'))
        okay = gtk.Button(_('OK'))
        cancel = gtk.Button(_('Cancel'))
        self.apply = gtk.Button(_('Apply'))

        vbox = gtk.VBox()
        vbox.set_border_width(5)
        self.add(vbox)

        # Create a new notebook, place the position of the tabs
        self.notebook = notebook = gtk.Notebook()
        notebook.set_tab_pos(gtk.POS_TOP)
        vbox.pack_start(notebook, True, True)
        notebook.show()
        self.show_tabs = True
        self.show_border = True

        # Options page
        settingsframe = self.add_page(notebook, _('Options'))
        settingsvbox = gtk.VBox()
        settingsframe.add(settingsvbox)

        ## Overlays group
        ovframe = gtk.Frame(_('Overlays'))
        ovframe.set_border_width(2)
        settingsvbox.pack_start(ovframe, False, False, 2)
        ovcvbox = gtk.VBox()
        ovframe.add(ovcvbox)
        hbox = gtk.HBox()
        ovcvbox.pack_start(hbox, False, False, 2)
        self.ovenable = gtk.CheckButton(_('Enable overlays'))
        hbox.pack_start(self.ovenable, False, False, 2)
        self.lclonly = gtk.CheckButton(_('Local disks only'))
        hbox.pack_start(self.lclonly, False, False, 2)

        ## Context Menu group
        cmframe = gtk.Frame(_('Context Menu'))
        cmframe.set_border_width(2)
        settingsvbox.pack_start(cmframe, False, False, 2)

        table = gtk.Table(2, 3)
        cmframe.add(table)
        def setcell(child, row, col):
            table.attach(child, col, col + 1, row, row + 1, gtk.FILL|gtk.EXPAND, 0, 4, 2)
        def withframe(widget):
            scroll = gtk.ScrolledWindow()
            scroll.set_policy(gtk.POLICY_NEVER, gtk.POLICY_ALWAYS)
            scroll.set_shadow_type(gtk.SHADOW_ETCHED_IN)
            scroll.add(widget)
            return scroll

        # Sub menus pane
        label = gtk.Label(_('Sub menu items:'))
        label.set_alignment(0, 0.5)
        setcell(label, 0, 0)

        # model: [0]hgcmd, [1]translated menu label
        self.submmodel = model = gtk.ListStore(gobject.TYPE_STRING,
                gobject.TYPE_STRING)
        self.submlist = list = gtk.TreeView(model)
        list.set_size_request(-1, 180)
        list.set_headers_visible(False)
        list.connect('row-activated', self.row_activated)
        column = gtk.TreeViewColumn()
        list.append_column(column)
        cell = gtk.CellRendererText()
        column.pack_start(cell, True)
        column.add_attribute(cell, 'text', 1)
        setcell(withframe(list), 1, 0)

        # Top menus pane
        label = gtk.Label(_('Top menu items:'))
        label.set_alignment(0, 0.5)
        setcell(label, 0, 2)

        # model: [0]hgcmd, [1]translated menu label
        self.topmmodel = model = gtk.ListStore(gobject.TYPE_STRING,
                gobject.TYPE_STRING)
        self.topmlist = list = gtk.TreeView(model)
        list.set_size_request(-1, 180)
        list.set_headers_visible(False)
        list.connect('row-activated', self.row_activated)
        column = gtk.TreeViewColumn()
        list.append_column(column)
        cell = gtk.CellRendererText()
        column.pack_start(cell, True)
        column.add_attribute(cell, 'text', 1)
        setcell(withframe(list), 1, 2)

        # move buttons
        mbbox = gtk.VBox()
        setcell(mbbox, 1, 1)

        topbutton = gtk.Button(_('Top ->'))
        topbutton.connect('clicked', self.top_clicked)
        mbbox.add(topbutton)
        subbutton = gtk.Button(_('<- Sub'))
        subbutton.connect('clicked', self.sub_clicked)
        mbbox.add(subbutton)

        ## Taskbar group
        taskbarframe = gtk.Frame(_('Taskbar'))
        taskbarframe.set_border_width(2)
        settingsvbox.pack_start(taskbarframe, False, False, 2)
        taskbarbox = gtk.VBox()
        taskbarframe.add(taskbarbox)
        hbox = gtk.HBox()
        taskbarbox.pack_start(hbox, False, False, 2)
        self.hgighlight_taskbaricon = gtk.CheckButton(_('Highlight Icon'))
        hbox.pack_start(self.hgighlight_taskbaricon, False, False, 2)        

        # Tooltips
        tips = gtk.Tooltips()

        tooltip = _('Enable/Disable the overlay icons globally')
        tips.set_tip(self.ovenable, tooltip)
        self.ovenable.connect('toggled', self.ovenable_toggled)
        tooltip = _('Only enable overlays on local disks')
        tips.set_tip(self.lclonly, tooltip)
        self.lclonly.connect('toggled', lambda x: self.apply.set_sensitive(True))

        tooltip = _('Highlight the taskbar icon during activity')
        tips.set_tip(self.hgighlight_taskbaricon, tooltip)
        self.hgighlight_taskbaricon.connect('toggled', lambda x: self.apply.set_sensitive(True))

        self.load_shell_configs()

        # Event log page
        frame = self.add_page(notebook, _('Event Log'))
        frame.set_border_width(2)

        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.set_border_width(2)
        textview = gtk.TextView()
        textview.set_editable(False)
        scrolledwindow.add(textview)
        frame.add(scrolledwindow)
        gobject.timeout_add(100, self.pollq, inputq, textview)

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)

        # Padding
        vbox.pack_start(gtk.HBox(), False, False, 3)

        # Bottom buttons
        bbox = gtk.HBox()
        vbox.pack_start(bbox, False, False)

        lefthbbox = gtk.HButtonBox()
        lefthbbox.set_layout(gtk.BUTTONBOX_START)
        lefthbbox.set_spacing(6)
        bbox.pack_start(lefthbbox, False, False)

        about.connect('clicked', self.about)
        lefthbbox.pack_start(about, False, False)

        bbox.pack_start(gtk.Label(''), True, True)

        righthbbox = gtk.HButtonBox()
        righthbbox.set_layout(gtk.BUTTONBOX_END)
        righthbbox.set_spacing(6)
        bbox.pack_start(righthbbox, False, False)

        okay.connect('clicked', self.okay_clicked)
        key, modifier = gtk.accelerator_parse('Return')
        okay.add_accelerator('clicked', accelgroup, key, 0,
                gtk.ACCEL_VISIBLE)
        righthbbox.pack_start(okay, False, False)

        cancel.connect('clicked', lambda x: self.destroy())
        key, modifier = gtk.accelerator_parse('Escape')
        cancel.add_accelerator('clicked', accelgroup, key, 0,
                gtk.ACCEL_VISIBLE)
        righthbbox.pack_start(cancel, False, False)

        self.apply.connect('clicked', self.apply_clicked)
        self.apply.set_sensitive(False)
        righthbbox.pack_start(self.apply, False, False)

    def add_page(self, notebook, tab):
        frame = gtk.Frame()
        frame.set_border_width(5)
        frame.set_shadow_type(gtk.SHADOW_NONE)
        frame.show()
        label = gtk.Label(tab)
        notebook.append_page(frame, label)
        return frame

    def about(self, button):
        from tortoisehg.hgtk import about
        dlg = about.AboutDialog()
        dlg.show_all()

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

    def load_shell_configs(self):
        overlayenable = True
        localdisks = False
        promoteditems = 'commit'
        hgighlight_taskbaricon = True
        try:
            from _winreg import HKEY_CURRENT_USER, OpenKey, QueryValueEx
            hkey = OpenKey(HKEY_CURRENT_USER, r'Software\TortoiseHg')
            t = ('1', 'True')
            try: overlayenable = QueryValueEx(hkey, 'EnableOverlays')[0] in t
            except EnvironmentError: pass
            try: localdisks = QueryValueEx(hkey, 'LocalDisksOnly')[0] in t
            except EnvironmentError: pass
            try: hgighlight_taskbaricon = QueryValueEx(hkey, 'HighlightTaskbarIcon')[0] in t
            except EnvironmentError: pass
            try: promoteditems = QueryValueEx(hkey, 'PromotedItems')[0]
            except EnvironmentError: pass
        except (ImportError, WindowsError):
            pass

        self.ovenable.set_active(overlayenable)
        self.lclonly.set_active(localdisks)
        self.lclonly.set_sensitive(overlayenable)
        self.hgighlight_taskbaricon.set_active(hgighlight_taskbaricon)

        promoted = [pi.strip() for pi in promoteditems.split(',')]
        self.submmodel.clear()
        self.topmmodel.clear()
        for cmd, info in menuthg.thgcmenu.items():
            label = info['label']['str']
            if cmd in promoted:
                self.topmmodel.append((cmd, label))
            else:
                self.submmodel.append((cmd, label))
        self.submmodel.set_sort_column_id(1, gtk.SORT_ASCENDING)
        self.topmmodel.set_sort_column_id(1, gtk.SORT_ASCENDING)

    def store_shell_configs(self):
        overlayenable = self.ovenable.get_active() and '1' or '0'
        localdisks = self.lclonly.get_active() and '1' or '0'
        hgighlight_taskbaricon = self.hgighlight_taskbaricon.get_active() and '1' or '0'
        promoted = []
        for row in self.topmmodel:
            promoted.append(row[0])
        try:
            from _winreg import HKEY_CURRENT_USER, CreateKey, SetValueEx, REG_SZ
            hkey = CreateKey(HKEY_CURRENT_USER, r"Software\TortoiseHg")
            SetValueEx(hkey, 'EnableOverlays', 0, REG_SZ, overlayenable)
            SetValueEx(hkey, 'LocalDisksOnly', 0, REG_SZ, localdisks)
            SetValueEx(hkey, 'HighlightTaskbarIcon', 0, REG_SZ, hgighlight_taskbaricon)
            SetValueEx(hkey, 'PromotedItems', 0, REG_SZ, ','.join(promoted))
        except ImportError:
            pass

    def move_to_other(self, list, paths=None):
        if paths == None:
            model, paths = list.get_selection().get_selected_rows()
        else:
            model = list.get_model()
        if list == self.submlist:
            otherlist = self.topmlist
            othermodel = self.topmmodel
        else:
            otherlist = self.submlist
            othermodel = self.submmodel
        for path in paths:
            cmd, label = model[path]
            model.remove(model.get_iter(path))
            othermodel.append((cmd, label))
        othermodel.set_sort_column_id(1, gtk.SORT_ASCENDING)
        self.apply.set_sensitive(True)

    def row_activated(self, list, path, column):
        self.move_to_other(list, (path,))

    def sub_clicked(self, button):
        self.move_to_other(self.topmlist)

    def top_clicked(self, button):
        self.move_to_other(self.submlist)

    def okay_clicked(self, button):
        self.store_shell_configs()
        self.destroy()

    def apply_clicked(self, button):
        self.store_shell_configs()
        button.set_sensitive(False)

    def ovenable_toggled(self, check):
        self.lclonly.set_sensitive(check.get_active())
        self.apply.set_sensitive(True)

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
        apply = gtk.Button(_('Apply'))
        close = gtk.Button(_('Close'))

        vbox = gtk.VBox()
        self.add(vbox)

        # Create a new notebook, place the position of the tabs
        self.notebook = notebook = gtk.Notebook()
        notebook.set_tab_pos(gtk.POS_TOP)
        vbox.pack_start(notebook, True, True)
        notebook.show()
        self.show_tabs = True
        self.show_border = True

        settingsframe = self.add_page(notebook, _('Options'))
        settingsvbox = gtk.VBox()
        settingsframe.add(settingsvbox)

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

        cmframe = gtk.Frame(_('Context Menu'))
        cmframe.set_border_width(2)
        settingsvbox.pack_start(cmframe, False, False, 2)
        cmcvbox = gtk.VBox()
        cmframe.add(cmcvbox)

        lbl = gtk.Label(_('Promote menu items to the top menu'))
        cmcvbox.pack_start(lbl, False, False, 2)

        tips = gtk.Tooltips()
        rows = (len(shellcmds) + 2) / 3
        table = gtk.Table(rows, 3, False)
        cmcvbox.pack_start(table, False, False, 2)
        self.cmptoggles = {}
        for i, cmd in enumerate(shellcmds):
            row, col = divmod(i, 3)
            check = gtk.CheckButton(cmd)
            table.attach(check, col, col+1,
                         row, row+1, gtk.FILL|gtk.EXPAND, 0, 4, 3)
            self.cmptoggles[cmd] = check
            tooltip = _('Promote menu item "%s" to top menu') % cmd
            tips.set_tip(check, tooltip)
            check.connect('toggled', lambda x: apply.set_sensitive(True))

        taskbarframe = gtk.Frame(_('Taskbar'))
        taskbarframe.set_border_width(2)
        settingsvbox.pack_start(taskbarframe, False, False, 2)
        taskbarbox = gtk.VBox()
        taskbarframe.add(taskbarbox)
        hbox = gtk.HBox()
        taskbarbox.pack_start(hbox, False, False, 2)
        self.hgighlight_taskbaricon = gtk.CheckButton(_('Highlight Icon'))
        hbox.pack_start(self.hgighlight_taskbaricon, False, False, 2)        

        tooltip = _('Enable/Disable the overlay icons globally')
        tips.set_tip(self.ovenable, tooltip)
        self.ovenable.connect('toggled', self.ovenable_toggled, apply)
        tooltip = _('Only enable overlays on local disks')
        tips.set_tip(self.lclonly, tooltip)
        self.lclonly.connect('toggled', lambda x: apply.set_sensitive(True))

        tooltip = _('Highlight the taskbar icon during activity')
        tips.set_tip(self.hgighlight_taskbaricon, tooltip)
        self.hgighlight_taskbaricon.connect('toggled', lambda x: apply.set_sensitive(True))

        self.load_shell_configs()

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

        hbbox = gtk.HButtonBox()
        hbbox.set_layout(gtk.BUTTONBOX_END)
        vbox.pack_start(hbbox, False, False, 2)

        about.connect('clicked', self.about)
        hbbox.pack_end(about, True, True, 0)

        apply.connect('clicked', self.applyclicked)
        apply.set_sensitive(False)
        hbbox.add(apply)

        close.connect('clicked', lambda x: self.destroy())
        key, modifier = gtk.accelerator_parse('Escape')
        close.add_accelerator('clicked', accelgroup, key, 0,
                gtk.ACCEL_VISIBLE)
        hbbox.add(close)

    def add_page(self, notebook, tab):
        frame = gtk.Frame()
        frame.set_border_width(5)
        frame.show()
        label = gtk.Label(tab)
        notebook.append_page(frame, label)
        return frame

    def about(self, button):
        from hggtk import about
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
        self.hgighlight_taskbaricon.set_active(hgighlight_taskbaricon)
        promoted = [pi.strip() for pi in promoteditems.split(',')]
        for cmd, check in self.cmptoggles.iteritems():
            check.set_active(cmd in promoted)

    def applyclicked(self, button):
        overlayenable = self.ovenable.get_active() and '1' or '0'
        localdisks = self.lclonly.get_active() and '1' or '0'
        hgighlight_taskbaricon = self.hgighlight_taskbaricon.get_active() and '1' or '0'
        promoted = []
        for cmd, check in self.cmptoggles.iteritems():
            if check.get_active():
                promoted.append(cmd)
        try:
            from _winreg import HKEY_CURRENT_USER, CreateKey, SetValueEx, REG_SZ
            hkey = CreateKey(HKEY_CURRENT_USER, r"Software\TortoiseHg")
            SetValueEx(hkey, 'EnableOverlays', 0, REG_SZ, overlayenable)
            SetValueEx(hkey, 'LocalDisksOnly', 0, REG_SZ, localdisks)
            SetValueEx(hkey, 'HighlightTaskbarIcon', 0, REG_SZ, hgighlight_taskbaricon)
            SetValueEx(hkey, 'PromotedItems', 0, REG_SZ, ','.join(promoted))
        except ImportError:
            pass
        button.set_sensitive(False)

    def ovenable_toggled(self, check, apply):
        self.lclonly.set_sensitive(check.get_active())
        apply.set_sensitive(True)

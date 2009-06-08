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
shelve synch status thgstatus userconfig repoconfig guess remove rename
revert serve update vdiff'''.split()

class TaskBarUI(gtk.Window):
    'User interface for the TortoiseHg taskbar application'
    def __init__(self, inputq, requestq):
        'Initialize the Dialog'
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        gtklib.set_tortoise_icon(self, 'hg.ico')
        gtklib.set_tortoise_keys(self)

        self.set_default_size(500, 420)
        self.set_title(_('TortoiseHg Taskbar'))

        about = gtk.Button(_('About'))
        apply = gtk.Button(_('Apply'))
        close = gtk.Button(_('Close'))

        vbox = gtk.VBox()
        self.add(vbox)

        ovframe = gtk.Frame(_('Overlay configuration'))
        ovframe.set_border_width(10)
        vbox.pack_start(ovframe, False, False, 2)
        ovcvbox = gtk.VBox()
        ovframe.add(ovcvbox)
        hbox = gtk.HBox()
        ovcvbox.pack_start(hbox, False, False, 2)
        self.ovenable = gtk.CheckButton(_('Enable overlays'))
        hbox.pack_start(self.ovenable, False, False, 2)
        self.lclonly = gtk.CheckButton(_('Local disks only'))
        hbox.pack_start(self.lclonly, False, False, 2)

        cmframe = gtk.Frame(_('Context menu configuration'))
        cmframe.set_border_width(10)
        vbox.pack_start(cmframe, False, False, 2)
        cmcvbox = gtk.VBox()
        cmframe.add(cmcvbox)

        descframe = gtk.Frame(_('Description'))
        descframe.set_border_width(10)
        desctext = gtk.TextView()
        desctext.set_wrap_mode(gtk.WRAP_WORD)
        desctext.set_editable(False)
        desctext.set_sensitive(False)
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.add(desctext)
        descframe.add(scrolledwindow)
        vbox.pack_start(gtk.Label(), True, True, 2)
        vbox.pack_start(descframe, False, False, 2)

        lbl = gtk.Label(_('Promote menu items to the top menu'))
        cmcvbox.pack_start(lbl, False, False, 2)

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
            check.connect('toggled', lambda x: apply.set_sensitive(True))
            check.connect('focus-in-event', self.set_help,
                    desctext.get_buffer(), tooltip)

        tooltip = _('Enable/Disable the overlay icons globally')
        self.ovenable.connect('focus-in-event', self.set_help,
                desctext.get_buffer(), tooltip)
        self.ovenable.connect('toggled', self.ovenable_toggled, apply)
        tooltip = _('Only enable overlays on local disks')
        self.lclonly.connect('toggled', lambda x: apply.set_sensitive(True))
        self.lclonly.connect('focus-in-event', self.set_help,
                desctext.get_buffer(), tooltip)
        self.load_shell_configs()

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
        gobject.timeout_add(100, self.pollq, inputq, textview)

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)

        hbbox = gtk.HButtonBox()
        hbbox.set_layout(gtk.BUTTONBOX_END)
        vbox.pack_start(hbbox, False, False, 2)

        about.connect('clicked', self.about)
        hbbox.add(about)

        apply.connect('clicked', self.applyclicked)
        apply.set_sensitive(False)
        hbbox.add(apply)

        close.connect('clicked', lambda x: self.destroy())
        key, modifier = gtk.accelerator_parse('Escape')
        close.add_accelerator('clicked', accelgroup, key, 0,
                gtk.ACCEL_VISIBLE)
        hbbox.add(close)

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
        try:
            from _winreg import HKEY_CURRENT_USER, OpenKey, QueryValueEx
            hkey = OpenKey(HKEY_CURRENT_USER, r'Software\TortoiseHg')
            t = ('1', 'True')
            try: overlayenable = QueryValueEx(hkey, 'EnableOverlays')[0] in t
            except EnvironmentError: pass
            try: localdisks = QueryValueEx(hkey, 'LocalDisksOnly')[0] in t
            except EnvironmentError: pass
            try: promoteditems = QueryValueEx(hkey, 'PromotedItems')[0]
            except EnvironmentError: pass
        except (ImportError, WindowsError):
            pass

        self.ovenable.set_active(overlayenable)
        self.lclonly.set_active(localdisks)
        promoted = [pi.strip() for pi in promoteditems.split(',')]
        for cmd, check in self.cmptoggles.iteritems():
            check.set_active(cmd in promoted)

    def applyclicked(self, button):
        overlayenable = self.ovenable.get_active() and '1' or '0'
        localdisks = self.lclonly.get_active() and '1' or '0'
        promoted = []
        for cmd, check in self.cmptoggles.iteritems():
            if check.get_active():
                promoted.append(cmd)
        try:
            from _winreg import HKEY_CURRENT_USER, CreateKey, SetValueEx, REG_SZ
            hkey = CreateKey(HKEY_CURRENT_USER, r"Software\TortoiseHg")
            SetValueEx(hkey, 'EnableOverlays', 0, REG_SZ, overlayenable)
            SetValueEx(hkey, 'LocalDisksOnly', 0, REG_SZ, localdisks)
            SetValueEx(hkey, 'PromotedItems', 0, REG_SZ, ','.join(promoted))
        except ImportError:
            pass
        button.set_sensitive(False)

    def set_help(self, widget, event, buffer, tooltip):
        text = ' '.join(tooltip.splitlines())
        buffer.set_text(text)

    def ovenable_toggled(self, check, apply):
        self.lclonly.set_sensitive(check.get_active())
        apply.set_sensitive(True)

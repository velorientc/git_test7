# backout.py - TortoiseHg's dialog for backing out changeset
#
# Copyright 2008 TK Soh <teekaysoh@gmail.com>
# Copyright 2008 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import gobject
import pango

from mercurial import hg, ui

from thgutil.i18n import _
from thgutil import hglib, paths

from hggtk import changesetinfo, gtklib, hgcmd

class BackoutDialog(gtk.Window):
    """ Backout effect of a changeset """
    def __init__(self, rev=None):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        gtklib.set_tortoise_keys(self)

        self.set_title(_('Backout changeset - ') + rev)
        self.set_default_size(600, 400)
        self.notify_func = None

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except hglib.RepoError:
            gobject.idle_add(self.destroy)
            return

        vbox = gtk.VBox()
        self.add(vbox)

        frame = gtk.Frame(_('Changeset Description'))
        rev, desc = changesetinfo.changesetinfo(repo, rev)
        frame.add(desc)
        frame.set_border_width(5)
        vbox.pack_start(frame, False, False, 2)

        self.logview = gtk.TextView(buffer=None)
        self.logview.set_editable(True)
        self.logview.modify_font(pango.FontDescription('Monospace'))
        buf = self.logview.get_buffer()
        buf.set_text(_('Backed out changeset: ') + rev)
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.add(self.logview)
        scrolledwindow.set_border_width(4)
        frame = gtk.Frame(_('Backout commit message'))
        frame.set_border_width(4)
        frame.add(scrolledwindow)
        self.tips = gtk.Tooltips()
        self.tips.set_tip(frame,
                _('Commit message text for new changeset that reverses the'
                '  effect of the change being backed out.'))
        vbox.pack_start(frame, True, True, 4)

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)
        mod = gtklib.get_thg_modifier()

        hbbox = gtk.HButtonBox()
        hbbox.set_layout(gtk.BUTTONBOX_END)
        vbox.pack_start(hbbox, False, False, 2)

        close = gtk.Button(_('Close'))
        close.connect('clicked', lambda x: self.destroy())
        key, modifier = gtk.accelerator_parse('Escape')
        close.add_accelerator('clicked', accelgroup, key, 0,
                gtk.ACCEL_VISIBLE)
        hbbox.add(close)

        backout = gtk.Button(_('Backout'))
        key, modifier = gtk.accelerator_parse(mod+'Return')
        backout.add_accelerator('clicked', accelgroup, key, modifier,
                gtk.ACCEL_VISIBLE)
        hbbox.add(backout)
        backout.grab_focus()

        backout.connect('clicked', self.backout, buf, rev)

    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = args

    def backout(self, button, buf, revstr):
        start, end = buf.get_bounds()
        msg = buf.get_text(start, end)
        cmdline = ['hg', 'backout', '--rev', revstr, '--message', hglib.fromutf(msg)]
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        if dlg.returncode == 0:
            if self.notify_func:
                self.notify_func(self.notify_args)
            self.destroy()

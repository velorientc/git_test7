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

class BackoutDialog(gtk.Dialog):
    """ Backout effect of a changeset """
    def __init__(self, rev=None):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self, title=_('Backout changeset - %s') % rev,
                          buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
        gtklib.set_tortoise_icon(self, 'menurevert.ico')
        gtklib.set_tortoise_keys(self)
        self.set_has_separator(False)
        self.set_default_size(600, 400)
        self.connect('response', self.dialog_response)

        # add Backout button
        backoutbutton = gtk.Button(_('Backout'))
        backoutbutton.connect('clicked', self.backout, rev)
        self.action_area.pack_end(backoutbutton)

        self.notify_func = None

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except hglib.RepoError:
            gobject.idle_add(self.destroy)
            return

        frame = gtk.Frame(_('Changeset Description'))
        revid, desc = changesetinfo.changesetinfo(repo, rev)
        frame.add(desc)
        frame.set_border_width(5)
        self.vbox.pack_start(frame, False, False, 2)

        self.logview = gtk.TextView(buffer=None)
        self.logview.set_editable(True)
        self.logview.modify_font(pango.FontDescription('Monospace'))
        self.buf = self.logview.get_buffer()
        self.buf.set_text(_('Backed out changeset: ') + rev)
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
        self.vbox.pack_start(frame, True, True, 4)

        # prepare to show
        backoutbutton.grab_focus()

    def dialog_response(self, dialog, response_id):
        if response_id == gtk.RESPONSE_CLOSE \
                or response_id == gtk.RESPONSE_DELETE_EVENT:
            self.destroy()

    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = args

    def backout(self, button, revstr):
        start, end = self.buf.get_bounds()
        msg = self.buf.get_text(start, end)
        cmdline = ['hg', 'backout', '--rev', revstr, '--message', hglib.fromutf(msg)]
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        if dlg.returncode == 0:
            if self.notify_func:
                self.notify_func(self.notify_args)
            self.destroy()

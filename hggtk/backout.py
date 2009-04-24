#
# backout.py - TortoiseHg's dialog for backing out changeset
#
# Copyright (C) 2008 Steve Borho <steve@borho.org>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import gtk
import pango
from mercurial.i18n import _
import histselect
import shlib

class BackoutDialog(gtk.Window):
    """ Backout effect of a changeset """
    def __init__(self, root='', rev=''):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        shlib.set_tortoise_keys(self)

        self.root = root
        self.set_title(_('Backout changeset - ') + rev)
        self.set_default_size(600, 400)
        self.notify_func = None
        
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()

        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)

        tbuttons = [
                self._toolbutton(gtk.STOCK_GO_BACK, _('Backout'),
                                 self._backout_clicked,
                                 _('Backout selected changeset'))
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        vbox = gtk.VBox()
        self.add(vbox)
        vbox.pack_start(self.tbar, False, False, 2)

        # From: combo box
        self.reventry = gtk.Entry()
        self.reventry.set_text(rev)
        self.browse = gtk.Button(_('Browse...'))
        self.browse.connect('clicked', self._btn_rev_clicked)

        hbox = gtk.HBox()
        hbox.pack_start(gtk.Label(_('Revision to backout:')), False, False, 4)
        hbox.pack_start(self.reventry, True, True, 4)
        hbox.pack_start(self.browse, False, False, 4)
        vbox.pack_start(hbox, False, False, 4)

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
        self.tips.set_tip(frame, 
                _('Commit message text for new changeset that reverses the'
                '  effect of the change being backed out.'))
        vbox.pack_start(frame, True, True, 4)

    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = args

    def _btn_rev_clicked(self, button):
        """ select revision from history dialog """
        rev = histselect.select(self.root)
        if rev is not None:
            self.reventry.set_text(rev)
            buf = self.logview.get_buffer()
            buf.set_text(_('Backed out changeset: ') + rev)

    def _toolbutton(self, stock, label, handler, tip):
        tbutton = gtk.ToolButton(stock)
        tbutton.set_label(label)
        tbutton.set_tooltip(self.tips, tip)
        tbutton.connect('clicked', handler)
        return tbutton
        
    def _backout_clicked(self, button):
        buf = self.logview.get_buffer()
        start, end = buf.get_bounds()
        cmdline = ['hg', 'backout', '--rev', self.reventry.get_text(),
            '--message', buf.get_text(start, end)]
        from hgcmd import CmdDialog
        dlg = CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        if self.notify_func:
            self.notify_func(self.notify_args)

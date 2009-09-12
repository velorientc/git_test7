# histdetails.py - TortoiseHg dialog for defining log viewing details
#
# Copyright 2009 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import gobject

from thgutil.i18n import _

from hggtk import gtklib

class LogDetailsDialog(gtk.Dialog):

    def __init__(self, model, apply_func):
        buttons = (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        super(LogDetailsDialog, self).__init__(
            flags=gtk.DIALOG_MODAL, buttons=buttons)

        self.apply_func = apply_func
        self.dirty = False

        gtklib.set_tortoise_icon(self, 'general.ico')
        gtklib.set_tortoise_keys(self)

        self._btn_apply = gtk.Button(_('Apply'))
        self._btn_apply.set_sensitive(False)
        self._btn_apply.connect('clicked', self._btn_apply_clicked)
        self.action_area.pack_end(self._btn_apply)

        self.set_title(_('Log Details'))

        self.set_default_size(350, 120)

        hbox = gtk.HBox()
        lb = gtk.Label(_('Columns') + ':')
        hbox.pack_start(lb, False, False, 4)
        self.vbox.pack_start(hbox, False, False, 4)

        tv = gtk.TreeView(model)
        tv.set_headers_visible(False)

        cr = gtk.CellRendererToggle()
        cr.set_property('activatable', True)

        def toggled(cell, path):
            model[path][0] = not model[path][0]
            self.dirty = True
            self.update_buttons()

        cr.connect('toggled', toggled)

        show_col = gtk.TreeViewColumn('', cr, active=0)
        tv.append_column(show_col)

        cr = gtk.CellRendererText()
        info_col = gtk.TreeViewColumn('', cr, text=1)
        tv.append_column(info_col)

        def activated(treeview, path, column):
            toggled(None, path)
        tv.connect('row-activated', activated)

        vbox = gtk.VBox()
        vbox.set_border_width(4)
        vbox.pack_start(tv)

        self.vbox.pack_start(vbox, True, True)

        self.show_all()

    def update_buttons(self):
        self._btn_apply.set_sensitive(self.dirty)

    def _btn_apply_clicked(self, button, data=None):
        self.apply_func()
        self.dirty = False
        self.update_buttons()


# histdetails.py - TortoiseHg dialog for defining log viewing details
#
# Copyright 2009 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import gobject

from tortoisehg.util.i18n import _

from tortoisehg.hgtk import gtklib

class LogDetailsDialog(gtk.Dialog):

    def __init__(self, model, apply_func):
        super(LogDetailsDialog, self).__init__(
            flags=gtk.DIALOG_MODAL)
        self.set_has_separator(False)
        self.connect('response', self.dialog_response)

        self.apply_func = apply_func
        self.dirty = False

        gtklib.set_tortoise_icon(self, 'general.ico')
        gtklib.set_tortoise_keys(self)

        # add dialog buttons
        self.okbtn = self.add_button(gtk.STOCK_OK, gtk.RESPONSE_OK)
        self.cancelbtn = self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CLOSE)
        self.applybtn = self.add_button(gtk.STOCK_APPLY, gtk.RESPONSE_APPLY)
        self.set_default_response(gtk.RESPONSE_OK)

        self.set_title(_('Log Details'))

        self.set_default_size(350, 120)

        hbox = gtk.HBox()
        lb = gtk.Label(_('Columns') + ':')
        hbox.pack_start(lb, False, False, 6)
        self.vbox.pack_start(gtk.HBox(), False, False, 3)
        self.vbox.pack_start(hbox, False, False)

        mainhbox = gtk.HBox()
        self.vbox.pack_start(mainhbox)

        leftvbox = gtk.VBox()
        rightvbox = gtk.VBox()
        mainhbox.pack_start(leftvbox, True, True)
        mainhbox.pack_start(gtk.VBox(), False, False, 0)
        mainhbox.pack_start(rightvbox, False, False, 4)

        tv = self.tv = gtk.TreeView(model)
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

        frm = gtk.Frame()
        frm.add(tv)

        vbox = gtk.VBox()
        vbox.set_border_width(4)
        vbox.pack_start(frm)

        leftvbox.pack_start(vbox, True, True)

        self.up_button = gtk.Button(_('Move Up'))
        self.up_button.connect('clicked', self.up_clicked)

        self.down_button = gtk.Button(_('Move Down'))
        self.down_button.connect('clicked', self.down_clicked)

        rightvbox.pack_start(self.up_button, False, False, 2)
        rightvbox.pack_start(self.down_button, False, False, 4)

        self.tv.connect('cursor-changed', lambda tv: self.update_buttons())

        self.show_all()

    def dialog_response(self, dialog, response_id):
        if response_id == gtk.RESPONSE_OK:
            self.apply()
            self.destroy()
        elif response_id == gtk.RESPONSE_APPLY:
            self.apply()
        else:
            self.destroy()

    def update_buttons(self):
        self.applybtn.set_sensitive(self.dirty)

        model, seliter = self.tv.get_selection().get_selected()
        if not seliter:
            self.down_button.set_sensitive(False)
            self.up_button.set_sensitive(False)
            return

        next = model.iter_next(seliter)
        self.down_button.set_sensitive(next != None)

        firstiter = model.get_iter_first()
        islast = model.get_path(seliter) != model.get_path(firstiter)
        self.up_button.set_sensitive(islast)

    def up_clicked(self, button):
        model, seliter = self.tv.get_selection().get_selected()
        i = model.get_iter_first()
        if model.get_path(seliter) != model.get_path(i):
            while True:
                next = model.iter_next(i)
                if next == None:
                    break
                if model.get_path(next) == model.get_path(seliter):
                    model.swap(i, next)
                    self.dirty = True
                    break
                i = next
        self.update_buttons()

    def down_clicked(self, button):
        model, seliter = self.tv.get_selection().get_selected()
        next = model.iter_next(seliter)
        if next:
            model.swap(seliter, next)
            self.dirty = True
        self.update_buttons()

    def apply(self):
        self.apply_func()
        self.dirty = False
        self.update_buttons()


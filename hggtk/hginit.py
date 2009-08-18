# hginit.py - TortoiseHg dialog to initialize a repo
#
# Copyright 2008 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk

from mercurial import hg, ui, util

from thgutil.i18n import _
from thgutil import hglib, shlib

from hggtk import dialog, gtklib

class InitDialog(gtk.Dialog):
    """ Dialog to initialize a Mercurial repo """
    def __init__(self, repos=[]):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self, title=_('Create a new repository'),
                          buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
        gtklib.set_tortoise_icon(self, 'menucreaterepos.ico')
        gtklib.set_tortoise_keys(self)
        self.set_resizable(False)
        self.set_has_separator(False)

        # add create button
        createbutton = gtk.Button(_('Create'))
        createbutton.connect('clicked', self._btn_init_clicked)
        self.action_area.pack_end(createbutton)

        self.cwd = os.getcwd()

        # preconditioning info
        self._dest_path = os.path.abspath(repos and repos[0] or self.cwd)

        # copy from 'thgconfig.py'
        table = gtk.Table(1, 2)
        self.vbox.pack_start(table, True, True, 2)
        def addrow(*widgets):
            row = table.get_property('n-rows')
            table.set_property('n-rows', row + 1)
            if len(widgets) == 1:
                col = table.get_property('n-columns')
                table.attach(widgets[0], 0, col, row, row + 1, gtk.FILL|gtk.EXPAND, 0, 2, 2)
            else:
                for col, widget in enumerate(widgets):
                    flag = gtk.FILL if col == 0 else gtk.FILL|gtk.EXPAND
                    table.attach(widget, col, col + 1, row, row + 1, flag, 0, 4, 2)

        # init destination
        lbl = gtk.Label(_('Destination:'))

        srcbox = gtk.HBox()
        self._dest_input = gtk.Entry()
        self._dest_input.set_size_request(260, -1)
        self._dest_input.size_request()
        self._dest_input.set_text(hglib.toutf(self._dest_path))
        self._dest_input.grab_focus()
        self._dest_input.set_position(-1)
        self._dest_input.connect('activate', self._entry_dest_activated, createbutton)
        srcbox.pack_start(self._dest_input, True, True, 2)

        self._btn_dest_browse = gtk.Button(_('Browse...'))
        self._btn_dest_browse.connect('clicked', self._btn_dest_clicked)
        srcbox.pack_start(self._btn_dest_browse, False, False, 2)

        addrow(lbl, srcbox)

        # options
        self._opt_specialfiles = gtk.CheckButton(
                _('Add special files (.hgignore, ...)'))
        self._opt_oldrepoformat = gtk.CheckButton(
                _('Make repo compatible with Mercurial 1.0'))
        addrow(self._opt_specialfiles)
        addrow(self._opt_oldrepoformat)

        # set option states
        self._opt_specialfiles.set_active(True)
        try:
            usefncache = ui.ui().configbool('format', 'usefncache', True)
            self._opt_oldrepoformat.set_active(not usefncache)
        except:
            pass

    def _entry_dest_activated(self, entry, button):
        self._btn_init_clicked(button)

    def _btn_dest_clicked(self, button):
        """ select source folder to clone """
        response = gtklib.NativeFolderSelectDialog(
                          initial=self.cwd,
                          title='Select Destination Folder').run()
        if response:
            self._dest_input.set_text(response)
            self._dest_input.set_position(-1)

    def _btn_init_clicked(self, button, data=None):
        # gather input data
        dest = hglib.fromutf(self._dest_input.get_text())

        # verify input
        if dest == "":
            dialog.error_dialog(self, _('Destination path is empty'),
                    _('Please enter the directory path'))
            self._dest_input.grab_focus()
            return False

        # start
        u = ui.ui()

        # fncache is the new default repo format in Mercurial 1.1
        if self._opt_oldrepoformat.get_active():
            u.setconfig('format', 'usefncache', 'False')

        try:
            hg.repository(u, dest, create=1)
        except hglib.RepoError, inst:
            dialog.error_dialog(self, _('Unable to create new repository'),
                    hglib.toutf(str(inst)))
            return False
        except util.Abort, inst:
            dialog.error_dialog(self, _('Error when creating repository'),
                    hglib.toutf(str(inst)))
            return False
        except:
            import traceback
            dialog.error_dialog(self, _('Error when creating repository'),
                    traceback.format_exc())
            return False

        # create the .hg* file, mainly to workaround
        # Explorer's problem in creating files with name
        # begins with a dot.
        if self._opt_specialfiles.get_active():
            hgignore = os.path.join(dest, '.hgignore')
            if not os.path.exists(hgignore):
                try:
                    open(hgignore, 'wb')
                except:
                    pass

        shlib.shell_notify([dest])

        dialog.info_dialog(self, _('New repository created'),
                _('in directory %s') % hglib.toutf(os.path.abspath(dest)))

def run(ui, *pats, **opts):
    return InitDialog(pats)

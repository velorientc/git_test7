# hginit.py - TortoiseHg dialog to initialize a repo
#
# Copyright 2008 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk

from mercurial import hg, ui, util

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, shlib

from tortoisehg.hgtk import dialog, gtklib

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
        createbutton.connect('clicked', lambda b: self.init())
        self.action_area.pack_end(createbutton)

        self.cwd = os.getcwd()

        # preconditioning info
        self.dest_path = os.path.abspath(repos and repos[0] or self.cwd)

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

        destbox = gtk.HBox()
        self.destentry = gtk.Entry()
        self.destentry.set_size_request(260, -1)
        self.destentry.size_request()
        self.destentry.set_text(hglib.toutf(self.dest_path))
        self.destentry.grab_focus()
        self.destentry.set_position(-1)
        self.destentry.connect('activate', lambda b: self.init())
        destbox.pack_start(self.destentry, True, True, 2)

        destbrowse = gtk.Button(_('Browse...'))
        destbrowse.connect('clicked', self.dest_clicked)
        destbox.pack_start(destbrowse, False, False, 2)

        addrow(lbl, destbox)

        # options
        self.optspfiles = gtk.CheckButton(
                _('Add special files (.hgignore, ...)'))
        self.optoldrepo = gtk.CheckButton(
                _('Make repo compatible with Mercurial 1.0'))
        addrow(self.optspfiles)
        addrow(self.optoldrepo)

        # set option states
        self.optspfiles.set_active(True)
        try:
            usefncache = ui.ui().configbool('format', 'usefncache', True)
            self.optoldrepo.set_active(not usefncache)
        except:
            pass

    def dest_clicked(self, button):
        """ select destination folder to clone """
        response = gtklib.NativeFolderSelectDialog(
                          initial=self.cwd,
                          title=_('Select Destination Folder')).run()
        if response:
            self.destentry.set_text(response)
            self.destentry.set_position(-1)

    def init(self):
        # gather input data
        dest = hglib.fromutf(self.destentry.get_text())

        # verify input
        if dest == "":
            dialog.error_dialog(self, _('Destination path is empty'),
                    _('Please enter the directory path'))
            self.destentry.grab_focus()
            return False

        # start
        u = ui.ui()

        # fncache is the new default repo format in Mercurial 1.1
        if self.optoldrepo.get_active():
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
        if self.optspfiles.get_active():
            hgignore = os.path.join(dest, '.hgignore')
            if not os.path.exists(hgignore):
                try:
                    open(hgignore, 'wb')
                except:
                    pass

        shlib.shell_notify([dest])

        dialog.info_dialog(self, _('New repository created'),
                _('in directory %s') % hglib.toutf(os.path.abspath(dest)))

        self.response(gtk.RESPONSE_OK)

def run(ui, *pats, **opts):
    return InitDialog(pats)

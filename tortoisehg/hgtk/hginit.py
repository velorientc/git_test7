# hginit.py - TortoiseHg dialog to initialize a repo
#
# Copyright 2008 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk

from mercurial import hg, ui, util, error

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, shlib

from tortoisehg.hgtk import dialog, gtklib

class InitDialog(gtk.Dialog):
    """ Dialog to initialize a Mercurial repo """
    def __init__(self, repos=[]):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self, title=_('TortoiseHg Init'))
        gtklib.set_tortoise_icon(self, 'menucreaterepos.ico')
        gtklib.set_tortoise_keys(self)
        self.set_resizable(False)
        self.set_has_separator(False)
        self.connect('response', self.dialog_response)

        # add buttons
        self.add_button(_('Create'), gtk.RESPONSE_OK)
        self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)

        self.cwd = os.getcwd()

        # preconditioning info
        path = os.path.abspath(repos and repos[0] or self.cwd)
        if not os.path.isdir(path):
            path = os.path.dirname(path)
        self.dest_path = path

        # layout table
        table = gtklib.LayoutTable()
        self.vbox.pack_start(table, True, True, 2)

        # init destination
        self.destentry = gtk.Entry()
        self.destentry.set_size_request(260, -1)
        self.destentry.size_request()
        self.destentry.set_text(hglib.toutf(self.dest_path))
        self.destentry.grab_focus()
        self.destentry.set_position(-1)
        self.destentry.connect('activate',
                               lambda b: self.response(gtk.RESPONSE_OK))

        destbrowse = gtk.Button(_('Browse...'))
        destbrowse.connect('clicked', self.dest_clicked)

        table.add_row(_('Destination:'), self.destentry, 0, destbrowse)

        # options
        self.optspfiles = gtk.CheckButton(
                _('Add special files (.hgignore, ...)'))
        self.optoldrepo = gtk.CheckButton(
                _('Make repo compatible with Mercurial 1.0'))
        self.optrunci = gtk.CheckButton(_('Run Commit after init'))
        table.add_row(self.optspfiles, xpad=2)
        table.add_row(self.optoldrepo, xpad=2)
        table.add_row(self.optrunci, xpad=2)

        # set option states
        self.optspfiles.set_active(True)
        try:
            usefncache = ui.ui().configbool('format', 'usefncache', True)
            self.optoldrepo.set_active(not usefncache)
        except:
            pass
        self.optrunci.set_active(False)

    def dialog_response(self, dialog, response_id):
        # Create button
        if response_id == gtk.RESPONSE_OK:
            gtklib.idle_add_single_call(self.init)
        # Cancel button or dialog closing by the user
        elif response_id in (gtk.RESPONSE_CLOSE, gtk.RESPONSE_DELETE_EVENT):
            return # close dialog
        else:
            raise _('unexpected response id: %s') % response_id

        self.run() # don't close dialog

    def dest_clicked(self, button):
        """ select destination folder to init """
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
        if dest == '':
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
        except error.RepoError, inst:
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

        if self.optrunci.get_active():
            self.emit_stop_by_name('response')
            self.emit_stop_by_name('destroy')
            self.hide()
            os.chdir(dest)
            from tortoisehg.hgtk.commit import run as cirun
            win = cirun(ui.ui())
            win.display()
            win.show_all()
            win.connect('destroy', gtk.main_quit)
        else:
            self.response(gtk.RESPONSE_CLOSE)

def run(ui, *pats, **opts):
    return InitDialog(pats)

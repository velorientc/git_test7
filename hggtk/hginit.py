#
# TortoiseHg dialog to initialize a repo
#
# Copyright (C) 2008 TK Soh <teekaysoh@gmail.com>
#

import os
import gtk

from mercurial import hg, ui, util

from thgutil.i18n import _
from thgutil import hglib, shlib

from hggtk import dialog, gtklib

class InitDialog(gtk.Window):
    """ Dialog to initialize a Mercurial repo """
    def __init__(self, repos=[]):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        gtklib.set_tortoise_icon(self, 'menucreaterepos.ico')
        gtklib.set_tortoise_keys(self)

        # set dialog title and icon
        self.cwd = os.getcwd()
        title = 'hg init - %s' % hglib.toutf(self.cwd)
        self.set_title(title)

        # preconditioning info
        self._dest_path = os.path.abspath(repos and repos[0] or os.getcwd())

        # build dialog
        self._create()


    def _create(self):
        self.set_default_size(350, 130)
        self.set_title(_('Create a new repository'))

        vbox = gtk.VBox()
        self.add(vbox)

        # init destination
        srcbox = gtk.HBox()
        lbl = gtk.Label(_('Destination:'))
        srcbox.pack_start(lbl, False, False, 2)

        self._dest_input = gtk.Entry()
        self._dest_input.set_text(hglib.toutf(self._dest_path))
        srcbox.pack_start(self._dest_input, True, True)

        self._btn_dest_browse = gtk.Button("...")
        self._btn_dest_browse.connect('clicked', self._btn_dest_clicked)
        srcbox.pack_end(self._btn_dest_browse, False, False, 5)

        vbox.pack_start(srcbox, False, False, 2)
        self._dest_input.grab_focus()
        self._dest_input.set_position(-1)

        # options
        option_box = gtk.VBox()
        self._opt_specialfiles = gtk.CheckButton(
                _('Add special files (.hgignore, ...)'))
        self._opt_oldrepoformat = gtk.CheckButton(
                _('Make repo compatible with Mercurial 1.0'))
        option_box.pack_start(self._opt_specialfiles, False, False)
        option_box.pack_start(self._opt_oldrepoformat, False, False)
        vbox.pack_start(option_box, False, False, 15)

        # set option states
        self._opt_specialfiles.set_active(True)
        try:
            usefncache = ui.ui().configbool('format', 'usefncache', True)
            self._opt_oldrepoformat.set_active(not usefncache)
        except:
            pass

        # buttons at bottom
        hbbox = gtk.HButtonBox()
        hbbox.set_layout(gtk.BUTTONBOX_END)
        vbox.pack_start(hbbox, False, False, 2)

        close = gtk.Button(_('Close'))
        close.connect('clicked', lambda x: self.destroy())
        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)
        key, modifier = gtk.accelerator_parse('Escape')
        close.add_accelerator('clicked', accelgroup, key, 0,
                gtk.ACCEL_VISIBLE)
        hbbox.add(close)

        create = gtk.Button(_('Create'))
        create.connect('clicked', self._btn_init_clicked)
        mod = gtklib.get_thg_modifier()
        key, modifier = gtk.accelerator_parse(mod+'Return')
        create.add_accelerator('clicked', accelgroup, key, modifier,
                gtk.ACCEL_VISIBLE)
        hbbox.add(create)

    def _btn_dest_clicked(self, button):
        """ select source folder to clone """
        response = gtklib.NativeFolderSelectDialog(
                          initial=self.cwd,
                          title='Select Destination Folder').run()
        if response:
            self._dest_input.set_text(response)
            self._dest_input.set_position(-1)

    def _btn_init_clicked(self, toolbutton, data=None):
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

        shlib.shell_notify(dest)

        dialog.info_dialog(self, _('New repository created'),
                _('in directory %s') % hglib.toutf(os.path.abspath(dest)))

def run(ui, *pats, **opts):
    return InitDialog(pats)

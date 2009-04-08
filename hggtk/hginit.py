#
# TortoiseHg dialog to initialize a repo
#
# Copyright (C) 2008 TK Soh <teekaysoh@gmail.com>
#

import pygtk
pygtk.require("2.0")
import os
import gtk
from dialog import error_dialog, info_dialog
from mercurial import hg, ui, util
from mercurial.i18n import _
from hglib import toutf, fromutf, RepoError
import shlib

class InitDialog(gtk.Window):
    """ Dialog to add tag to Mercurial repo """
    def __init__(self, cwd='', repos=[]):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        
        # set dialog title and icon
        self.cwd = cwd and cwd or os.getcwd()
        title = 'hg init - %s' % toutf(self.cwd)
        self.set_title(title)
        shlib.set_tortoise_icon(self, 'menucreaterepos.ico')

        # preconditioning info
        self._dest_path = os.path.abspath(repos and repos[0] or os.getcwd())

        # build dialog
        self._create()

    def _create(self):
        self.set_default_size(350, 150)
        self.connect('destroy', gtk.main_quit)
        
        # add toolbar with tooltips
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()
        
        self._btn_init = self._toolbutton(
                gtk.STOCK_NEW,
                _('Create'), 
                self._btn_init_clicked,
                tip=_('Create a new repository in destination directory'))
        tbuttons = [
                self._btn_init,
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)
        vbox = gtk.VBox()
        self.add(vbox)
        vbox.pack_start(self.tbar, False, False, 2)

        # clone source
        srcbox = gtk.HBox()
        lbl = gtk.Label(_(' Destination :'))
        lbl.set_property('width-chars', 12)
        lbl.set_alignment(0, 0.5)
        self._dest_input = gtk.Entry()
        self._dest_input.set_text(toutf(self._dest_path))
        self._dest_input.set_position(-1)

        self._btn_dest_browse = gtk.Button("...")
        self._btn_dest_browse.connect('clicked', self._btn_dest_clicked)
        srcbox.pack_start(lbl, False, False)
        srcbox.pack_start(self._dest_input, True, True)
        srcbox.pack_end(self._btn_dest_browse, False, False, 5)
        vbox.pack_start(srcbox, False, False, 2)
        
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

    def _toolbutton(self, stock, label, handler,
                    menu=None, userdata=None, tip=None):
        if menu:
            tbutton = gtk.MenuToolButton(stock)
            tbutton.set_menu(menu)
        else:
            tbutton = gtk.ToolButton(stock)
            
        tbutton.set_label(label)
        if tip:
            tbutton.set_tooltip(self.tips, tip)
        tbutton.connect('clicked', handler, userdata)
        return tbutton
        
    def _btn_dest_clicked(self, button):
        """ select source folder to clone """
        dialog = gtk.FileChooserDialog(title=None,
                action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,
                         gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        dialog.set_default_response(gtk.RESPONSE_OK)
        dialog.set_current_folder(self.cwd)
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            self._dest_input.set_text(dialog.get_filename())
            self._dest_input.set_position(-1)
        dialog.destroy()

    def _btn_init_clicked(self, toolbutton, data=None):
        # gather input data
        dest = fromutf(self._dest_input.get_text())
        
        # verify input
        if dest == "":
            error_dialog(self, _('Destination path is empty'),
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
        except RepoError, inst:
            error_dialog(self, _('Unable to create new repository'), str(inst))
            return False
        except util.Abort, inst:
            error_dialog(self, _('Error when creating repository'), str(inst))
            return False
        except:
            import traceback
            error_dialog(self, _('Error when creating repository'), 
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
        
        info_dialog(self, _('New repository created'),
                _('in directory %s') % toutf(os.path.abspath(dest)))

def run(cwd='', files=[], **opts):
    dialog = InitDialog(cwd, repos=files)
    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()
    
if __name__ == "__main__":
    import sys
    opts = {}
    opts['cwd'] = os.getcwd()
    opts['files'] = sys.argv[1:]
    run(**opts)

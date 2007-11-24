#
# TortoiseHg dialog to add tag
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

try:
    import pygtk
    pygtk.require("2.0")
except:
    pass

import os
import sys
import gtk
from dialog import question_dialog, error_dialog, info_dialog
from mercurial import hg, ui, cmdutil, util
from mercurial.i18n import _
from mercurial.node import *

class CloneDialog(gtk.Dialog):
    """ Dialog to add tag to Mercurial repo """
    def __init__(self, cwd=''):
        """ Initialize the Dialog """
        buttons = (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        super(CloneDialog, self).__init__(flags=gtk.DIALOG_MODAL, 
                                           buttons=buttons)

        if cwd: os.chdir(cwd)
        
        # set dialog title
        title = "hg clone "
        title += " - %s" % (os.getcwd())
        self.set_title(title)

        # build dialog
        self._create()

    def _create(self):
        self.set_default_size(400, 180)
        ewidth = 16
        
        # clone source
        srcbox = gtk.HBox()
        lbl = gtk.Label("Source Path:")
        lbl.set_property("width-chars", ewidth)
        lbl.set_alignment(0, 0.5)
        self._src_input = gtk.Entry()
        self._btn_src_browse = gtk.Button("Browse...")
        self._btn_src_browse.connect('clicked', self._btn_src_clicked)
        srcbox.pack_start(lbl, False, False)
        srcbox.pack_start(self._src_input, True, True)
        srcbox.pack_end(self._btn_src_browse, False, False, 5)
        self.vbox.pack_start(srcbox, False, False, 2)

        # clone destination
        destbox = gtk.HBox()
        lbl = gtk.Label("Destination Path:")
        lbl.set_property("width-chars", ewidth)
        lbl.set_alignment(0, 0.5)
        self._dest_input = gtk.Entry()
        self._dest_input.set_text("")
        self._btn_dest_browse = gtk.Button("Browse...")
        self._btn_dest_browse.connect('clicked', self._btn_dest_clicked)
        destbox.pack_start(lbl, False, False)
        destbox.pack_start(self._dest_input, True, True)
        destbox.pack_end(self._btn_dest_browse, False, False, 5)
        self.vbox.pack_start(destbox, False, False, 2)

        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Label("Checkout Revision:")
        lbl.set_property("width-chars", ewidth)
        lbl.set_alignment(0, 0.5)
        self._rev_input = gtk.Entry()
        self._rev_input.set_text("tip")
        self._btn_rev_browse = gtk.Button("Select...")
        self._btn_rev_browse.connect('clicked', self._btn_rev_clicked)
        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self._rev_input, False, False)
        #revbox.pack_start(self._btn_rev_browse, False, False, 5)
        self.vbox.pack_start(revbox, False, False, 2)

        # options
        option_box = gtk.VBox()
        self._opt_update = gtk.CheckButton("do not update the new working directory")
        self._opt_pull = gtk.CheckButton("use pull protocol to copy metadata")
        self._opt_uncomp = gtk.CheckButton("use uncompressed transfer")
        option_box.pack_start(self._opt_update, False, False)
        option_box.pack_start(self._opt_pull, False, False)
        option_box.pack_start(self._opt_uncomp, False, False)
        self.vbox.pack_start(option_box, False, False, 15)

        # remote cmd
        lbl = gtk.Label("Remote Cmd:")
        lbl.set_alignment(0, 0.5)
        self._remote_cmd = gtk.Entry()
        self.vbox.pack_end(self._remote_cmd, False, False, 1)
        self.vbox.pack_end(lbl, False, False, 1)
        
        # add action buttn
        self._btn_clone = gtk.Button("Clone")
        self._btn_clone.connect('clicked', self._btn_clone_clicked)
        self.action_area.pack_end(self._btn_clone)
        
        # show them all
        self.vbox.show_all()

    def _btn_dest_clicked(self, button):
        """ select folder as clone destination """
        dialog = gtk.FileChooserDialog(title=None,
                action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,
                         gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        dialog.set_default_response(gtk.RESPONSE_OK)
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            self._dest_input.set_text(dialog.get_filename())
        dialog.destroy()
        
    def _btn_src_clicked(self, button):
        """ select source folder to clone """
        dialog = gtk.FileChooserDialog(title=None,
                action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,
                         gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        dialog.set_default_response(gtk.RESPONSE_OK)
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            self._src_input.set_text(dialog.get_filename())
        dialog.destroy()

    def _btn_rev_clicked(self, button):
        """ select revision from history dialog """
        import history
        rev = history.select(self.root)
        if rev is not None:
            self._rev_input.set_text(rev)
            
    def _btn_clone_clicked(self, button):
        # gather input data
        src = self._src_input.get_text()
        dest = self._dest_input.get_text()
        remotecmd = self._remote_cmd.get_text()
        rev = self._rev_input.get_text()

        # verify input
        if src == "":
            error_dialog("Source path is empty", "Please enter")
            self._src_input.grab_focus()
            return False
        
        # start cloning        
        try:            
            cmdline = 'hg clone'
            if self._opt_update.get_active():
                cmdline += ' --noupdate'
            if self._opt_uncomp.get_active():
                cmdline += ' --uncompressed'
            if self._opt_pull.get_active():
                cmdline += ' --pull'
            if remotecmd:   
                cmdline += ' --remotecmd %s' % util.shellquote(remotecmd)
            if rev:   
                cmdline += ' --rev %s' % rev

            cmdline += ' --verbose'
            cmdline += ' %s' % util.shellquote(src)
            if dest:
                cmdline += ' %s' % util.shellquote(dest)
            print "cmdline: ", cmdline
            import cmd
            cmd.run(cmdline)
        except util.Abort, inst:
            error_dialog("Clone aborted", str(inst))
            return False
        except:
            import traceback
            error_dialog("Clone error", traceback.format_exc())
            return False

def run(cwd=''):
    dialog = CloneDialog(cwd)
    dialog.run()
    
if __name__ == "__main__":
    import sys
    run()

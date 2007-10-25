#
# merge.py - TortoiseHg's dialog for merging revisions
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import pygtk
pygtk.require("2.0")

import sys
import gtk
from dialog import *
from mercurial import util

class MergeDialog(gtk.Dialog):
    """ Dialog to merge revisions of a Mercurial repo """
    def __init__(self, root=''):
        """ Initialize the Dialog """
        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        super(MergeDialog, self).__init__(flags=gtk.DIALOG_MODAL, 
                                          buttons=buttons)

        self.root = root

        # set dialog title
        title = "hg merge"
        if root: title += " - %s" % root
        self.set_title(title)

        self._create()
        
    def _create(self):
        self.set_default_size(350, 120)

        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Label("Merge with revision:")
        lbl.set_property("width-chars", 20)
        lbl.set_justify(gtk.JUSTIFY_LEFT)
        self._rev_input = gtk.Entry()
        self._rev_input.set_text("tip")
        self._btn_rev_browse = gtk.Button("Browse...")
        self._btn_rev_browse.connect('clicked', self._btn_rev_clicked)
        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self._rev_input, False, False)
        revbox.pack_start(self._btn_rev_browse, False, False, 5)
        self.vbox.pack_start(revbox, False, False, 2)

        self._chbox_force = gtk.CheckButton("allow merge with uncommited changes")
        self.vbox.pack_end(self._chbox_force, False, False, 10)

        # add action buttn
        self._btn_merge = gtk.Button("Merge")
        self._btn_merge.connect('clicked', self._btn_merge_clicked)
        self.action_area.pack_end(self._btn_merge)
        
        # show them all
        self.vbox.show_all()

    def _btn_rev_clicked(self, button):
        """ select revision from history dialog """
        import history
        rev = history.select(self.root)
        if rev is not None:
            self._rev_input.set_text(rev)

    def _btn_merge_clicked(self, button):
        self._do_merge()
        
    def _do_merge(self):
        rev = self._rev_input.get_text()
        force = self._chbox_force.get_active()
        
        response = question_dialog("Really want to merge?",
                                   "with revision %s" % rev)
        if response != gtk.RESPONSE_YES:
            return
            
        import cmd
        cmdline = 'hg merge --repository %s --rev %s' % \
                        (util.shellquote(self.root), rev)
        if force: cmdline += " --force"
        cmd.run(cmdline)

def run(root=''):
    dialog = MergeDialog(root=root)
    dialog.run()
    return 

if __name__ == "__main__":
    import sys
    root = len(sys.argv) > 1 and sys.argv[1:] or []
    run(*root)

                                           
                                           
                       
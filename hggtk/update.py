#
# update.py - TortoiseHg's dialog for updating repo
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import pygtk
pygtk.require("2.0")

import os
import sys
import gtk
from dialog import *
from mercurial.node import *
from mercurial import util, hg, ui
from shlib import shell_notify
from hglib import rootpath

class UpdateDialog(gtk.Dialog):
    """ Dialog to update Mercurial repo """
    def __init__(self, cwd=''):
        """ Initialize the Dialog """
        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        super(UpdateDialog, self).__init__(flags=gtk.DIALOG_MODAL, 
                                           buttons=buttons)
        self.cwd = cwd or os.getcwd()
        self.root = rootpath(self.cwd)
        
        u = ui.ui()
        try:
            self.repo = hg.repository(u, path=self.root)
        except hg.RepoError:
            return None

        # set dialog title
        title = "hg update - %s" % self.cwd
        self.set_title(title)

        self._create()
        
    def _create(self):
        self.set_default_size(350, 120)

        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Label("Update to revision:")
        lbl.set_property("width-chars", 20)
        lbl.set_justify(gtk.JUSTIFY_LEFT)
        
        # revisions  combo box
        revlist = gtk.ListStore(str, str)
        self._revbox = gtk.ComboBoxEntry(revlist, 0)
        
        # add extra column to droplist for type of changeset
        cell = gtk.CellRendererText()
        self._revbox.pack_start(cell)
        self._revbox.add_attribute(cell, 'text', 1)
    
        # populate revision data
        self._rev_input = self._revbox.get_child()
        heads = self.repo.heads()
        tip = self.repo.changelog.node(nullrev+self.repo.changelog.count())
        revlist.append([short(tip), "(tip)"])
        self._rev_input.set_text(short(tip))
        if len(heads) > 1:
            for i, node in enumerate(heads):
                revlist.append([short(node), "(head %d)" % (i+1)])
        
        # setup buttons
        self._btn_rev_browse = gtk.Button("Browse...")
        self._btn_rev_browse.connect('clicked', self._btn_rev_clicked)
        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self._revbox, False, False)
        revbox.pack_start(self._btn_rev_browse, False, False, 5)
        self.vbox.pack_start(revbox, False, False, 2)

        self._overwrite = gtk.CheckButton("Overwrite local changes")
        self.vbox.pack_end(self._overwrite, False, False, 10)

        # add action buttn
        self._btn_update = gtk.Button("Update")
        self._btn_update.connect('clicked', self._btn_update_clicked)
        self.action_area.pack_end(self._btn_update)
        
        # show them all
        self.vbox.show_all()

    def _btn_rev_clicked(self, button):
        """ select revision from history dialog """
        import history
        rev = history.select(self.root)
        if rev is not None:
            self._rev_input.set_text(rev)

    def _btn_update_clicked(self, button):
        self._do_update()
        
    def _do_update(self):
        rev = self._rev_input.get_text()
        overwrite = self._overwrite.get_active()
        
        response = question_dialog("Really want to update?",
                                   "to revision %s" % rev)
        if response != gtk.RESPONSE_YES:
            return
            
        import cmd
        cmdline = 'hg update --repository %s --rev %s' % \
                        (util.shellquote(self.root), rev)
        if overwrite: cmdline += " --clean"
        cmd.run(cmdline)
        print "running cmd..."
        shell_notify([self.cwd])

def run(cwd=''):
    dialog = UpdateDialog(cwd=cwd)
    dialog.run()
    return 

if __name__ == "__main__":
    import sys
    path = len(sys.argv) > 1 and sys.argv[1] or ''
    run(path)

                                           
                                           
                       
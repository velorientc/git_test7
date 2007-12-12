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
        buttons = (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
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

        # repo parent revisions
        parentbox = gtk.HBox()
        lbl = gtk.Label("Parent revisions:")
        lbl.set_property("width-chars", 18)
        lbl.set_alignment(0, 0.5)
        self._parent_revs = gtk.Entry()
        self._parent_revs.set_sensitive(False)
        parentbox.pack_start(lbl, False, False)
        parentbox.pack_start(self._parent_revs, False, False)
        self.vbox.pack_start(parentbox, False, False, 2)

        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Label("Update to revision:")
        lbl.set_property("width-chars", 18)
        lbl.set_alignment(0, 0.5)
        
        # revisions  combo box
        self._revlist = gtk.ListStore(str, str)
        self._revbox = gtk.ComboBoxEntry(self._revlist, 0)
        
        # add extra column to droplist for type of changeset
        cell = gtk.CellRendererText()
        self._revbox.pack_start(cell)
        self._revbox.add_attribute(cell, 'text', 1)
        self._rev_input = self._revbox.get_child()
        
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
        self._refresh()

    def _refresh(self):
        """ update display on dialog with recent repo data """
        try:
            # FIXME: force hg to refresh parents info
            del self.repo
            self.repo = hg.repository(ui.ui(), path=self.root)
        except hg.RepoError:
            return None

        # populate parent rev data
        self._parents = [x.node() for x in self.repo.workingctx().parents()]
        self._parent_revs.set_text(", ".join([short(x) for x in self._parents]))

        # populate revision data        
        heads = self.repo.heads()
        tip = self.repo.changelog.node(nullrev+self.repo.changelog.count())
        self._revlist.clear()
        for i, node in enumerate(heads):
            status = "head %d" % (i+1)
            if node == tip:
                status += ", tip"
            self._revlist.append([short(node), "(%s)" %status])
        self._revbox.set_active(0)
            
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
        
        if not rev:
            error_dialog("Can't update", "please enter revision to update to")
            return
        
        response = question_dialog("Really want to update?",
                                   "to revision %s" % rev)
        if response != gtk.RESPONSE_YES:
            return
            
        import cmd
        cmdline = 'hg update --repository %s --rev %s' % \
                        (util.shellquote(self.root), rev)
        if overwrite: cmdline += " --clean"
        cmd.run(cmdline)
        self._refresh()
        shell_notify([self.cwd])

def run(cwd=''):
    dialog = UpdateDialog(cwd=cwd)
    dialog.run()
    return 

if __name__ == "__main__":
    import sys
    path = len(sys.argv) > 1 and sys.argv[1] or ''
    run(path)

                                           
                                           
                       
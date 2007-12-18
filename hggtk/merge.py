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
from mercurial.node import *
from mercurial import util, hg, ui

class MergeDialog(gtk.Dialog):
    """ Dialog to merge revisions of a Mercurial repo """
    def __init__(self, root=''):
        """ Initialize the Dialog """
        buttons = (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        super(MergeDialog, self).__init__(flags=gtk.DIALOG_MODAL, 
                                          buttons=buttons)

        # set dialog title
        title = "hg merge"
        if root: title += " - %s" % root
        self.set_title(title)
        self.connect('response', gtk.main_quit)

        self.root = root
        self.repo = None
        self._create()

    def _create(self):
        self.set_default_size(350, 120)
        
        # repo parent revisions
        parentbox = gtk.HBox()
        lbl = gtk.Label("Parent revisions:")
        lbl.set_property("width-chars", 18)
        lbl.set_alignment(0, 0.5)
        self._parent_revs = gtk.Entry()
        parentbox.pack_start(lbl, False, False)
        parentbox.pack_start(self._parent_revs, False, False)
        self.vbox.pack_start(parentbox, False, False, 2)

        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Label("Merge with revision:")
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

        self._btn_rev_browse = gtk.Button("Browse...")
        self._btn_rev_browse.connect('clicked', self._btn_rev_clicked)
        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self._revbox, False, False)
        revbox.pack_start(self._btn_rev_browse, False, False, 5)
        self.vbox.pack_start(revbox, False, False, 2)

        self._chbox_force = gtk.CheckButton("allow merge with uncommited changes")
        self.vbox.pack_end(self._chbox_force, False, False, 10)

        # add action buttn
        self._btn_merge = gtk.Button("Merge")
        self._btn_merge.connect('clicked', self._btn_merge_clicked)
        self.action_area.pack_end(self._btn_merge)
        
        # show them all
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
        print "merge: parents = ", self._parents 
        self._parent_revs.set_sensitive(True)
        self._parent_revs.set_text(", ".join([short(x) for x in self._parents]))
        self._parent_revs.set_sensitive(False)
        
        # disable merge if repo already have uncommited merge
        if len(self._parents) > 1:
            self._btn_merge.set_sensitive(False)
            
        # populate revision data        
        heads = self.repo.heads()
        tip = self.repo.changelog.node(nullrev+self.repo.changelog.count())
        self._revlist.clear()
        self._rev_input.set_text("")
        for i, node in enumerate(heads):
            if node in self._parents:
                continue
            
            status = "head %d" % (i+1)
            if node == tip:
                status += ", tip"
            
            self._revlist.append([short(node), "(%s)" %status])
            self._rev_input.set_text(short(node))
        
    def _btn_rev_clicked(self, button):
        """ select revision from history dialog """
        import histselect
        rev = histselect.select(self.root)
        if rev is not None:
            self._rev_input.set_text(rev)

    def _btn_merge_clicked(self, button):
        self._do_merge()
        
    def _do_merge(self):
        rev = self._rev_input.get_text()
        force = self._chbox_force.get_active()
        
        if not rev:
            error_dialog("Can't merge", "please enter revision to merge")
            return
        
        response = question_dialog("Really want to merge?",
                                   "with revision %s" % rev)
        if response != gtk.RESPONSE_YES:
            return

        cmdline = 'hg merge --repository %s --rev %s' % \
                        (util.shellquote(self.root), rev)
        if force: cmdline += " --force"

        from command import CmdDialog
        dlg = CmdDialog(cmdline)
        dlg.run()
        dlg.hide()
        self._refresh()

def run(root='', **opts):
    dialog = MergeDialog(root)
    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or ''
    run(**opts)

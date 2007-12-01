#
# Path selection dialog for TortoiseHg dialogs
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
# Copyright (C) 2007 Steve Borho <steve@borho.org>
#

try:
    import pygtk
    pygtk.require("2.0")
except:
    pass

import gtk
from mercurial import hg, ui 
from mercurial.node import *

class PathsDialog(gtk.Dialog):
    def __init__(self, root='', pull=False):
        """ Initialize the Dialog. """        
        gtk.Dialog.__init__(self, title="TortoiseHg Select Remote Repository",
                                  parent=None,
                                  flags=0,
                                  buttons=None)
        self.root = root
        self.selected_path = None

        self.set_default_size(550, 50)

        self._btn_ok = gtk.Button("Ok")
        self._btn_ok.connect('clicked', self._ok_clicked)
        self.action_area.pack_end(self._btn_ok)

        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Label("%s path:" % \
                (pull and "Incoming" or "Outgoing"))
        lbl.set_justify(gtk.JUSTIFY_LEFT)
        
        # revisions  combo box
        revlist = gtk.ListStore(str)
        self._pathbox = gtk.ComboBoxEntry(revlist, 0)
        
        self.paths = self._get_paths()
        defrow = None
        defpushrow = None
        for row, (name, path) in enumerate(self.paths):
            if name == 'default':
                defrow = row
                if defpushrow is None:
                    defpushrow = row
            elif name == 'default-push':
                defpushrow = row
            revlist.append([path])

        if pull and defrow:
            self._pathbox.set_active(defrow)
        elif not pull and defpushrow:
            self._pathbox.set_active(defpushrow)
    
        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self._pathbox, True, True)
        self.vbox.pack_start(revbox, False, False, 2)
        self.vbox.show_all()
        
    def _get_paths(self):
        """ retrieve repo revisions """
        try:
            repo = hg.repository(ui.ui(), path=self.root)
            return repo.ui.configitems('paths')
        except hg.RepoError:
            return None

    def _ok_clicked(self, buttons):
        text_entry = self._pathbox.get_child()
        self.selected_path = str(text_entry.get_text())
        self.hide()
        
def run(root='', pull=False):
    dlg = PathsDialog(root=root, pull=pull)
    dlg.run()
    return dlg.selected_path

if __name__ == "__main__":
    import sys
    run()

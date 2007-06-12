# Copyright (C) 2006 by Szilveszter Farkas (Phanatic) <szilveszter.farkas@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

try:
    import pygtk
    pygtk.require("2.0")
except:
    pass

import sys
import gtk
from mercurial import hg, repo, ui, cmdutil, util
from mercurial.i18n import _

class StatusDialog(gtk.Dialog):
    """ Display Status window and perform the needed actions. """
    def __init__(self, root='', files=[], list_clean=False):
        """ Initialize the Status window. """
        super(StatusDialog, self).__init__(flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
        self.set_title("Working tree changes")
        self._create()
        self.root = root
        self.files = files
        self.list_clean = list_clean
        
        # Generate status output
        self._generate_status()

    def _create(self):
        self.set_default_size(400, 300)
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.treeview = gtk.TreeView()
        scrolledwindow.add(self.treeview)
        self.vbox.pack_start(scrolledwindow, True, True)
        self.vbox.show_all()

    def row_diff(self, tv, path, tvc):
        file = self.model[path][1]
        if file is not None:
            import os.path
            from diff import DiffWindow
            
            diff = DiffWindow()
            diff._set_as_dialog(modal=True)
            
            selpath = os.path.join(self.repo.root, file)
            diff.set_diff(self.root, [ selpath ])
            diff.show()

    def _generate_status(self):
        """ Generate 'hg status' output. """
        self.model = gtk.TreeStore(str, str)
        self.treeview.set_headers_visible(False)
        self.treeview.set_model(self.model)
        self.treeview.connect("row-activated", self.row_diff)
        
        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 20)
        column = gtk.TreeViewColumn()
        column.pack_start(cell, expand=True)
        column.add_attribute(cell, "text", 0)
        self.treeview.append_column(column)
        
        u = ui.ui()
        try:
            repo = hg.repository(u, path=self.root)
        except repo.RepoError:
            return None
        self.repo = repo
        
        # get file status
        try:
            files, matchfn, anypats = cmdutil.matchpats(repo, self.files)
            modified, added, removed, deleted, unknown, ignored, clean = [
                    n for n in repo.status(files=files, list_clean=self.list_clean)]
        except util.Abort, inst:
            return None

        changes = False
        
        if len(added):
            changes = True
            titer = self.model.append(None, [ _('Added'), None ])
            for path in added:
                self.model.append(titer, [ path, path ])

        if len(removed):
            changes = True
            titer = self.model.append(None, [ _('Removed'), None ])
            for path in removed:
                self.model.append(titer, [ path, path ])

        if len(modified):
            changes = True
            titer = self.model.append(None, [ _('Modified'), None ])
            for path in modified:
                self.model.append(titer, [ path, path ])
        
        self.treeview.expand_all()
    
    def display(self):
        """ Display the Diff window. """
        self.window.show_all()

    def close(self, widget=None):
        self.window.destroy()

def run(root='', files=[]):
    dialog = StatusDialog(root=root, files=files)
    dialog.run()
    
if __name__ == "__main__":
    import sys
    root = "D:\\Profiles\\r28629\\My Documents\\Mercurial\\repos\\c1\\"
    #dialog = StatusDialog(root=root)
    dialog = StatusDialog(files=sys.argv[1:])
    dialog.run()

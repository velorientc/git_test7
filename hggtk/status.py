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

import gtk

class StatusDialog(gtk.Dialog):
    """ Display Status window and perform the needed actions. """
    def __init__(self, wt, wtpath):
        """ Initialize the Status window. """
        super(StatusDialog, self).__init__(flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
        self.set_title("Working tree changes")
        self._create()
        self.wt = wt
        self.wtpath = wtpath
        # Set the old working tree
        self.old_tree = self.wt.branch.repository.revision_tree(self.wt.branch.last_revision())
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
        if file is None:
            return
        from bzrlib.plugins.gtk.diff import DiffWindow
        window = DiffWindow()
        window.set_diff("Working tree changes", self.old_tree, self.wt)
        window.set_file(file)
        window.show()

    def _generate_status(self):
        """ Generate 'bzr status' output. """
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
        
        delta = self.wt.changes_from(self.old_tree)

        changes = False
        
        if len(delta.added):
            changes = True
            titer = self.model.append(None, [ _('Added'), None ])
            for path, id, kind in delta.added:
                self.model.append(titer, [ path, path ])

        if len(delta.removed):
            changes = True
            titer = self.model.append(None, [ _('Removed'), None ])
            for path, id, kind in delta.removed:
                self.model.append(titer, [ path, path ])

        if len(delta.renamed):
            changes = True
            titer = self.model.append(None, [ _('Renamed'), None ])
            for oldpath, newpath, id, kind, text_modified, meta_modified \
                    in delta.renamed:
                self.model.append(titer, [ oldpath, newpath ])

        if len(delta.modified):
            changes = True
            titer = self.model.append(None, [ _('Modified'), None ])
            for path, id, kind, text_modified, meta_modified in delta.modified:
                self.model.append(titer, [ path, path ])
        
        done_unknown = False
        for path in self.wt.unknowns():
            changes = True
            if not done_unknown:
                titer = self.model.append(None, [ _('Unknown'), None ])
                done_unknown = True
            self.model.append(titer, [ path, path ])

        if not changes:
            self.model.append(None, [ _('No changes.'), None ])

        self.treeview.expand_all()
    
    def display(self):
        """ Display the Diff window. """
        self.window.show_all()

    def close(self, widget=None):
        self.window.destroy()

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
from dialog import question_dialog, error_dialog
from mercurial import util
from mercurial.i18n import _
import hglib

class StatusDialog(gtk.Dialog):
    """ Display Status window and perform the needed actions. """
    def __init__(self, path='', files=[], list_clean=False):
        """ Initialize the Status window. """
        super(StatusDialog, self).__init__(flags=gtk.DIALOG_MODAL, 
                                           buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))

        # set dialog title
        title = "hg status "
        if root: title += " - %s" % root
        self.set_title(title)

        self.path = path
        self.hg = hglib.Hg(path)
        self.root = self.hg.root
        self.files = files
        self.list_clean = list_clean
        
        # build dialog
        self._create()

        # Generate status output
        self._generate_status()

    def _create(self):
        self.set_default_size(400, 300)
        
        # add treeview to list change files
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.treeview = gtk.TreeView()
        self._create_treestore()
        scrolledwindow.add(self.treeview)
        self.vbox.pack_start(scrolledwindow, True, True)
        
        # add revert button
        self._button_revert = gtk.Button("Revert")
        self._button_revert.connect('clicked', self._on_revert_clicked)
        self._button_revert.set_flags(gtk.CAN_DEFAULT)
        self.action_area.pack_end(self._button_revert)
        
        # show them all
        self.vbox.show_all()

    def _create_treestore(self):
        """ Generate 'hg status' output. """
        self.model = gtk.TreeStore(str, str)
        self.treeview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        self.treeview.set_headers_visible(False)
        self.treeview.set_model(self.model)
        self.treeview.connect("row-activated", self.row_diff)
        
        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 20)
        column = gtk.TreeViewColumn()
        column.pack_start(cell, expand=True)
        column.add_attribute(cell, "text", 0)
        self.treeview.append_column(column)
        
    def _generate_status(self):
        # clear changed files display
        self.model.clear()

        # get file status
        try:
            status = self.hg.status(self.files, list_clean=self.list_clean)
            modified, added, removed, deleted, unknown, ignored, clean = status
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
        
        if len(deleted):
            changes = True
            titer = self.model.append(None, [ _('Deleted'), None ])
            for path in deleted:
                self.model.append(titer, [ path, path ])

        self.treeview.expand_all()
        
    def row_diff(self, tv, path, tvc):
        file = self.model[path][1]
        if file is not None:
            import os.path
            from diff import DiffWindow
            
            diff = DiffWindow()
            diff._set_as_dialog(modal=True)
            
            selpath = os.path.join(self.root, file)
            diff.set_diff(self.root, [ selpath ])
            diff.show()

    def _on_revert_clicked(self, button):
        files = self._get_tree_selections(self.treeview, 1)
        files = [x for x in files if not x is None]
        if not files:
            return
        
        response = question_dialog("Do you really want to revert", "\n".join(files))
        if response == gtk.RESPONSE_YES:
            import os.path
            if self._do_revert(files) == True:
                # refresh changed file display
                self._generate_status()
   
    def _get_tree_selections(self, treeview, index=0):
        treeselection = treeview.get_selection()
        mode = treeselection.get_mode()
        list = []
        if mode == gtk.SELECTION_MULTIPLE:
            (model, pathlist) = treeselection.get_selected_rows()
            for p in pathlist:
                iter = model.get_iter(p)
                list.append(model.get_value(iter, index))
        else:
            (model, iter) = treeselection.get_selected()
            list.append(model.get_value(iter, index))
        
        return list
        
    def _do_revert(self, files):
        try:
            self.hg.command('revert', files=files)
        except util.Abort, inst:
            error_dialog("Error in revert", "abort: %s" % inst)
            return False
        except:
            import traceback
            error_dialog("Error in revert", "Traceback:\n%s" % traceback.format_exc())
            return False
        return True

def run(root='', files=[]):
    dialog = StatusDialog(root=root, files=files)
    dialog.run()
    
if __name__ == "__main__":
    import sys
    root = len(sys.argv) > 1 and sys.argv[1:] or []
    dialog = StatusDialog(*root)
    dialog.run()

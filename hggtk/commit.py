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
import gobject
import pango
from mercurial import hg, repo, ui, cmdutil, util
from mercurial.i18n import _
from dialog import error_dialog, question_dialog

class CommitDialog(gtk.Dialog):
    """ New implementation of the Commit dialog. """
    def __init__(self, root='', files=[], parent=None):
        """ Initialize the Commit Dialog. """
        gtk.Dialog.__init__(self, title="TortoiseHg commit - %s" % root,
                                  parent=parent,
                                  flags=0,
                                  buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
              
        self.root = root
        self.files = files
        
        # Create the widgets
        self._button_commit = gtk.Button(_("Comm_it"), use_underline=True)
        self._expander_files = gtk.Expander(_("File(s) to commit"))
        self._vpaned_main = gtk.VPaned()
        self._scrolledwindow_files = gtk.ScrolledWindow()
        self._scrolledwindow_message = gtk.ScrolledWindow()
        self._treeview_files = gtk.TreeView()
        self._vbox_message = gtk.VBox()
        self._label_message = gtk.Label(_("Commit message:"))
        self._textview_message = gtk.TextView()

        # Set callbacks
        self._button_commit.connect('clicked', self._on_commit_clicked)
        self._treeview_files.connect('row_activated', self._on_treeview_files_row_activated)
        
        # Set properties
        self._scrolledwindow_files.set_policy(gtk.POLICY_AUTOMATIC,
                                              gtk.POLICY_AUTOMATIC)
        self._scrolledwindow_message.set_policy(gtk.POLICY_AUTOMATIC,
                                                gtk.POLICY_AUTOMATIC)
        self._textview_message.modify_font(pango.FontDescription("Monospace"))
        self.set_default_size(500, 500)
        self._vpaned_main.set_position(200)
        self._button_commit.set_flags(gtk.CAN_DEFAULT)

        # Construct the dialog
        self.action_area.pack_end(self._button_commit)
        
        self._scrolledwindow_files.add(self._treeview_files)
        self._scrolledwindow_message.add(self._textview_message)
        
        self._expander_files.add(self._scrolledwindow_files)
        
        self._vbox_message.pack_start(self._label_message, False, False)
        self._vbox_message.pack_start(self._scrolledwindow_message, True, True)
        
        self._vpaned_main.add1(self._expander_files)
        self._vpaned_main.add2(self._vbox_message)
        
        self.vbox.pack_start(self._vpaned_main, True, True)

        # Create the file list
        self._create_file_view()
        
        # Expand the corresponding expander
        self._expander_files.set_expanded(True)
        
        # Display dialog
        self.vbox.show_all()
        
        # Default to Commit button
        self._button_commit.grab_default()
    
    def _on_treeview_files_row_activated(self, treeview, path, view_column):
        # FIXME: the diff window freezes for some reason
        treeselection = treeview.get_selection()
        (model, iter) = treeselection.get_selected()
        
        if iter is not None:
            from diff import DiffWindow
            
            _selected = model.get_value(iter, 1)
            
            diff = DiffWindow()
            diff.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
            diff.set_modal(True)
            parent_tree = self.wt.branch.repository.revision_tree(self.wt.branch.last_revision())
            diff.set_diff(self.wt.branch.nick, self.wt, parent_tree)
            try:
                diff.set_file(_selected)
            except errors.NoSuchFile:
                pass
            diff.show()
    
    def _on_commit_clicked(self, button):
        """ Commit button clicked handler. """
        textbuffer = self._textview_message.get_buffer()
        start, end = textbuffer.get_bounds()
        message = textbuffer.get_text(start, end).decode('utf-8')
        
        specific_files = self._get_specific_files()
        if not specific_files:
            error_dialog(_('No file selected?'),
                         _('You can select files to commit.'))
            return

        if message == '':
            error_dialog(_('Commit message is empty'),
                         _('Please enter the commit message.'))
            # Kindly give focus to message area
            self._textview_message.grab_focus()
            return

        try:
            self.repo.commit(specific_files, message)
        except ValueError, inst:
            error_dialog(_('Error during commit'),
                         _(str(inst)))
            return

        self.response(gtk.RESPONSE_OK)

    def _create_file_view(self):
        self._file_store = gtk.ListStore(gobject.TYPE_BOOLEAN,   # [0] checkbox
                                         gobject.TYPE_STRING,    # [1] path to display
                                         gobject.TYPE_STRING,    # [2] changes type
                                         gobject.TYPE_STRING)    # [3] real path
        self._treeview_files.set_model(self._file_store)
        crt = gtk.CellRendererToggle()
        crt.set_property("activatable", True)
        crt.connect("toggled", self._toggle_commit, self._file_store)
        self._treeview_files.append_column(gtk.TreeViewColumn(_('Commit'),
                                     crt, active=0))
        self._treeview_files.append_column(gtk.TreeViewColumn(_('Path'),
                                     gtk.CellRendererText(), text=1))
        self._treeview_files.append_column(gtk.TreeViewColumn(_('Type'),
                                     gtk.CellRendererText(), text=2))

        # open Hg repo
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
                    n for n in repo.status(files=files, list_clean=False)]
        except util.Abort, inst:
            return None

        # add change files to list window
        for path in modified:
            self._file_store.append([ True, path, _('added'), path ])
        for path in added:
            self._file_store.append([ True, path, _('added'), path ])
        for path in removed:
            self._file_store.append([ True, path, _('added'), path ])
    
    def _get_specific_files(self):
        ret = []
        it = self._file_store.get_iter_first()
        while it:
            if self._file_store.get_value(it, 0):
                # get real path from hidden column 3
                ret.append(self._file_store.get_value(it, 3))
            it = self._file_store.iter_next(it)

        return ret
    
    def _toggle_commit(self, cell, path, model):
        model[path][0] = not model[path][0]
        return

def run(root='', files=[]):
    dialog = CommitDialog(root=root, files=files)
    dialog.run()

if __name__ == "__main__":
    run()

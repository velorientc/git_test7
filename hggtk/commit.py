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

import os.path

import bzrlib.errors as errors
from bzrlib import osutils

from dialog import error_dialog, question_dialog
from errors import show_bzr_error

try:
    import dbus
    import dbus.glib
    have_dbus = True
except ImportError:
    have_dbus = False

class CommitDialog(gtk.Dialog):
    """ New implementation of the Commit dialog. """
    def __init__(self, wt, wtpath, notbranch, selected=None, parent=None):
        """ Initialize the Commit Dialog. """
        gtk.Dialog.__init__(self, title="Commit - Olive",
                                  parent=parent,
                                  flags=0,
                                  buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
        
        # Get arguments
        self.wt = wt
        self.wtpath = wtpath
        self.notbranch = notbranch
        self.selected = selected
        
        # Set the delta
        self.old_tree = self.wt.branch.repository.revision_tree(self.wt.branch.last_revision())
        self.delta = self.wt.changes_from(self.old_tree)
        
        # Get pending merges
        self.pending = self._pending_merges(self.wt)
        
        # Do some preliminary checks
        self._is_checkout = False
        self._is_pending = False
        if self.wt is None and not self.notbranch:
            error_dialog(_('Directory does not have a working tree'),
                         _('Operation aborted.'))
            self.close()
            return

        if self.notbranch:
            error_dialog(_('Directory is not a branch'),
                         _('You can perform this action only in a branch.'))
            self.close()
            return
        else:
            if self.wt.branch.get_bound_location() is not None:
                # we have a checkout, so the local commit checkbox must appear
                self._is_checkout = True
            
            if self.pending:
                # There are pending merges, file selection not supported
                self._is_pending = True
        
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
        
        if self._is_pending:
            self._expander_merges = gtk.Expander(_("Pending merges"))
            self._vpaned_list = gtk.VPaned()
            self._scrolledwindow_merges = gtk.ScrolledWindow()
            self._treeview_merges = gtk.TreeView()

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

        if self._is_pending:
            self._scrolledwindow_merges.set_policy(gtk.POLICY_AUTOMATIC,
                                                   gtk.POLICY_AUTOMATIC)
            self._treeview_files.set_sensitive(False)
        
        # Construct the dialog
        self.action_area.pack_end(self._button_commit)
        
        self._scrolledwindow_files.add(self._treeview_files)
        self._scrolledwindow_message.add(self._textview_message)
        
        self._expander_files.add(self._scrolledwindow_files)
        
        self._vbox_message.pack_start(self._label_message, False, False)
        self._vbox_message.pack_start(self._scrolledwindow_message, True, True)
        
        if self._is_pending:        
            self._expander_merges.add(self._scrolledwindow_merges)
            self._scrolledwindow_merges.add(self._treeview_merges)
            self._vpaned_list.add1(self._expander_files)
            self._vpaned_list.add2(self._expander_merges)
            self._vpaned_main.add1(self._vpaned_list)
        else:
            self._vpaned_main.add1(self._expander_files)

        self._vpaned_main.add2(self._vbox_message)
        
        self.vbox.pack_start(self._vpaned_main, True, True)
        if self._is_checkout: 
            self._check_local = gtk.CheckButton(_("_Only commit locally"),
                                                use_underline=True)
            self.vbox.pack_start(self._check_local, False, False)
            if have_dbus:
                bus = dbus.SystemBus()
                proxy_obj = bus.get_object('org.freedesktop.NetworkManager', 
                              '/org/freedesktop/NetworkManager')
                dbus_iface = dbus.Interface(
                        proxy_obj, 'org.freedesktop.NetworkManager')
                # 3 is the enum value for STATE_CONNECTED
                self._check_local.set_active(dbus_iface.state() != 3)
        
        # Create the file list
        self._create_file_view()
        # Create the pending merges
        self._create_pending_merges()
        
        # Expand the corresponding expander
        if self._is_pending:
            self._expander_merges.set_expanded(True)
        else:
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
    
    @show_bzr_error
    def _on_commit_clicked(self, button):
        """ Commit button clicked handler. """
        textbuffer = self._textview_message.get_buffer()
        start, end = textbuffer.get_bounds()
        message = textbuffer.get_text(start, end).decode('utf-8')
        
        if not self.pending:
            specific_files = self._get_specific_files()
        else:
            specific_files = None

        if message == '':
            response = question_dialog(_('Commit with an empty message?'),
                                       _('You can describe your commit intent in the message.'))
            if response == gtk.RESPONSE_NO:
                # Kindly give focus to message area
                self._textview_message.grab_focus()
                return

        if self._is_checkout:
            local = self._check_local.get_active()
        else:
            local = False

        if list(self.wt.unknowns()) != []:
            response = question_dialog(_("Commit with unknowns?"),
               _("Unknown files exist in the working tree. Commit anyway?"))
            if response == gtk.RESPONSE_NO:
                return
        
        try:
            self.wt.commit(message,
                       allow_pointless=False,
                       strict=False,
                       local=local,
                       specific_files=specific_files)
        except errors.PointlessCommit:
            response = question_dialog(_('Commit with no changes?'),
                                       _('There are no changes in the working tree.'))
            if response == gtk.RESPONSE_YES:
                self.wt.commit(message,
                               allow_pointless=True,
                               strict=False,
                               local=local,
                               specific_files=specific_files)
        self.response(gtk.RESPONSE_OK)

    def _pending_merges(self, wt):
        """ Return a list of pending merges or None if there are none of them. """
        parents = wt.get_parent_ids()
        if len(parents) < 2:
            return None
        
        import re
        from bzrlib.osutils import format_date
        
        pending = parents[1:]
        branch = wt.branch
        last_revision = parents[0]
        
        if last_revision is not None:
            try:
                ignore = set(branch.repository.get_ancestry(last_revision))
            except errors.NoSuchRevision:
                # the last revision is a ghost : assume everything is new 
                # except for it
                ignore = set([None, last_revision])
        else:
            ignore = set([None])
        
        pm = []
        for merge in pending:
            ignore.add(merge)
            try:
                m_revision = branch.repository.get_revision(merge)
                
                rev = {}
                rev['committer'] = re.sub('<.*@.*>', '', m_revision.committer).strip(' ')
                rev['summary'] = m_revision.get_summary()
                rev['date'] = format_date(m_revision.timestamp,
                                          m_revision.timezone or 0, 
                                          'original', date_fmt="%Y-%m-%d",
                                          show_offset=False)
                
                pm.append(rev)
                
                inner_merges = branch.repository.get_ancestry(merge)
                assert inner_merges[0] is None
                inner_merges.pop(0)
                inner_merges.reverse()
                for mmerge in inner_merges:
                    if mmerge in ignore:
                        continue
                    mm_revision = branch.repository.get_revision(mmerge)
                    
                    rev = {}
                    rev['committer'] = re.sub('<.*@.*>', '', mm_revision.committer).strip(' ')
                    rev['summary'] = mm_revision.get_summary()
                    rev['date'] = format_date(mm_revision.timestamp,
                                              mm_revision.timezone or 0, 
                                              'original', date_fmt="%Y-%m-%d",
                                              show_offset=False)
                
                    pm.append(rev)
                    
                    ignore.add(mmerge)
            except errors.NoSuchRevision:
                print "DEBUG: NoSuchRevision:", merge
        
        return pm

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

        for path, id, kind in self.delta.added:
            marker = osutils.kind_marker(kind)
            if self.selected is not None:
                if path == os.path.join(self.wtpath, self.selected):
                    self._file_store.append([ True, path+marker, _('added'), path ])
                else:
                    self._file_store.append([ False, path+marker, _('added'), path ])
            else:
                self._file_store.append([ True, path+marker, _('added'), path ])

        for path, id, kind in self.delta.removed:
            marker = osutils.kind_marker(kind)
            if self.selected is not None:
                if path == os.path.join(self.wtpath, self.selected):
                    self._file_store.append([ True, path+marker, _('removed'), path ])
                else:
                    self._file_store.append([ False, path+marker, _('removed'), path ])
            else:
                self._file_store.append([ True, path+marker, _('removed'), path ])

        for oldpath, newpath, id, kind, text_modified, meta_modified in self.delta.renamed:
            marker = osutils.kind_marker(kind)
            if text_modified or meta_modified:
                changes = _('renamed and modified')
            else:
                changes = _('renamed')
            if self.selected is not None:
                if newpath == os.path.join(self.wtpath, self.selected):
                    self._file_store.append([ True,
                                              oldpath+marker + '  =>  ' + newpath+marker,
                                              changes,
                                              newpath
                                            ])
                else:
                    self._file_store.append([ False,
                                              oldpath+marker + '  =>  ' + newpath+marker,
                                              changes,
                                              newpath
                                            ])
            else:
                self._file_store.append([ True,
                                          oldpath+marker + '  =>  ' + newpath+marker,
                                          changes,
                                          newpath
                                        ])

        for path, id, kind, text_modified, meta_modified in self.delta.modified:
            marker = osutils.kind_marker(kind)
            if self.selected is not None:
                if path == os.path.join(self.wtpath, self.selected):
                    self._file_store.append([ True, path+marker, _('modified'), path ])
                else:
                    self._file_store.append([ False, path+marker, _('modified'), path ])
            else:
                self._file_store.append([ True, path+marker, _('modified'), path ])
    
    def _create_pending_merges(self):
        if not self.pending:
            return
        
        liststore = gtk.ListStore(gobject.TYPE_STRING,
                                  gobject.TYPE_STRING,
                                  gobject.TYPE_STRING)
        self._treeview_merges.set_model(liststore)
        
        self._treeview_merges.append_column(gtk.TreeViewColumn(_('Date'),
                                            gtk.CellRendererText(), text=0))
        self._treeview_merges.append_column(gtk.TreeViewColumn(_('Committer'),
                                            gtk.CellRendererText(), text=1))
        self._treeview_merges.append_column(gtk.TreeViewColumn(_('Summary'),
                                            gtk.CellRendererText(), text=2))
        
        for item in self.pending:
            liststore.append([ item['date'],
                               item['committer'],
                               item['summary'] ])
    
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

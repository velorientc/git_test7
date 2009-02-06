#
# status.py - status dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#


import os
import cStringIO

import pygtk
pygtk.require('2.0')
import gtk
import pango

from mercurial.i18n import _
from mercurial import cmdutil, util, ui, hg, commands, patch, mdiff
from mercurial import merge as merge_
from shlib import shell_notify
from hglib import toutf, rootpath, diffexpand
from gdialog import *
from dialog import entry_dialog
import hgshelve

# file model row enumerations
FM_CHECKED = 0
FM_STATUS = 1
FM_PATH_UTF8 = 2
FM_PATH = 3
FM_MERGE_STATUS = 4
FM_PARTIAL_SELECTED = 5

# diff_model row enumerations
DM_REJECTED = 0
DM_NOT_REJECTED = 1
DM_CHUNK_TEXT = 2
DM_HEADER_CHUNK = 3
DM_CHUNK_ID = 4

class GStatus(GDialog):
    """GTK+ based dialog for displaying repository status

    Also provides related operations like add, delete, remove, revert, refresh,
    ignore, diff, and edit.

    The following methods are meant to be overridden by subclasses. At this
    point GCommit is really the only intended subclass.

        auto_check(self)
        get_menu_info(self)
    """

    ### Following methods are meant to be overridden by subclasses ###

    def init(self):
        GDialog.init(self)
        
    def auto_check(self):
        if self.test_opt('check'):
            for entry in self.filemodel:
                entry[FM_CHECKED] = True
            self._update_check_count()


    def get_menu_info(self):
        """Returns menu info in this order:
            merge, addrem, unknown, clean, ignored, deleted, 
            unresolved, resolved 
        """
        return (
                # merge
                (('_difference', self._diff_file),
                    ('_view right', self._view_file), 
                    ('view _left', self._view_left_file),
                    ('_revert', self._revert_file),
                    ('l_og', self._log_file)),
                # addrem
                (('_difference', self._diff_file),
                    ('_view', self._view_file), 
                    ('_revert', self._revert_file), 
                    ('l_og', self._log_file)),
                # unknown
                (('_view', self._view_file),
                    ('_delete', self._delete_file), 
                    ('_add', self._add_file),
                    ('_guess rename', self._guess_rename),
                    ('_ignore', self._ignore_file)),
                # clean
                (('_view', self._view_file),
                    ('re_move', self._remove_file),
                    ('re_name', self._rename_file),
                    ('_copy', self._copy_file),
                    ('l_og', self._log_file)),
                # ignored
                (('_view', self._view_file),
                    ('_delete', self._delete_file)),
                # deleted
                (('_view', self._view_file),
                    ('_revert', self._revert_file), 
                    ('re_move', self._remove_file),
                    ('l_og', self._log_file)),
                # unresolved
                (('_difference', self._diff_file),
                    ('_view right', self._view_file), 
                    ('view _left', self._view_left_file),
                    ('_revert', self._revert_file),
                    ('l_og', self._log_file),
                    ('resolve', self._do_resolve),
                    ('mark resolved', self._mark_resolved)),
                # resolved
                (('_difference', self._diff_file),
                    ('_view right', self._view_file), 
                    ('view _left', self._view_left_file),
                    ('_revert', self._revert_file),
                    ('l_og', self._log_file),
                    ('mark unresolved', self._unmark_resolved)),
                )

    ### End of overridable methods ###


    ### Overrides of base class methods ###

    def parse_opts(self):
        self._ready = False

        # Determine which files to display
        if self.test_opt('all'):
            for check in self._show_checks.values():
                check.set_active(True)
        else:
            set = False
            for opt in self.opts :
                if opt in self._show_checks and self.opts[opt]:
                    set = True
                    self._show_checks[opt].set_active(True)
            if not set:
                for check in [item[1] for item in self._show_checks.iteritems() 
                              if item[0] in ('modified', 'added', 'removed', 
                                             'deleted', 'unknown')]:
                    check.set_active(True)


    def get_title(self):
        root = os.path.basename(self.repo.root)
        revs = self.opts.get('rev')
        if revs:
            return root + ' status ' + ':'.join(revs) + ' ' + ' '.join(self.pats)
        elif self.mqmode:
            patch = self.repo.mq.lookup('qtip')
            return root + ' applied MQ patch ' + patch
        else:
            return root + ' status ' + ' '.join(self.pats)

    def get_icon(self):
        return 'menushowchanged.ico'

    def get_defsize(self):
        return self._setting_defsize


    def get_tbbuttons(self):
        tbuttons = [self.make_toolbutton(gtk.STOCK_REFRESH, 'Re_fresh',
            self._refresh_clicked, tip='refresh'),
                     gtk.SeparatorToolItem()]

        if self.count_revs() < 2:
            tbuttons += [
                    self.make_toolbutton(gtk.STOCK_MEDIA_REWIND, 'Re_vert',
                        self._revert_clicked, tip='revert'),
                    self.make_toolbutton(gtk.STOCK_ADD, '_Add',
                        self._add_clicked, tip='add'),
                    self.make_toolbutton(gtk.STOCK_JUMP_TO, 'Move',
                        self._move_clicked,
                        tip='move selected files to other directory'),
                    self.make_toolbutton(gtk.STOCK_DELETE, '_Remove',
                        self._remove_clicked, tip='remove'),
                    gtk.SeparatorToolItem()]

        self.showdiff_toggle = gtk.ToggleToolButton(gtk.STOCK_JUSTIFY_FILL)
        self.showdiff_toggle.set_use_underline(True)
        self.showdiff_toggle.set_label('_Show Diff')
        self.showdiff_toggle.set_tooltip(self.tooltips, 'show diff pane')
        self.showdiff_toggle.set_active(False)
        self._showdiff_toggled_id = self.showdiff_toggle.connect('toggled',
                self._showdiff_toggled )
        tbuttons.append(self.showdiff_toggle)
        
        # Shelving does not work when visualizing diffs between
        # revisions (though this could eventually be made to work)
        if not self.opts.get('rev'):
            self.shelve_btn = self.make_toolbutton(gtk.STOCK_FILE, 'Shelve',
                    self._shelve_clicked, tip='set aside selected changes')
            self.unshelve_btn = self.make_toolbutton(gtk.STOCK_EDIT, 'Unshelve',
                    self._unshelve_clicked, tip='restore shelved changes')
            tbuttons += [
                    gtk.SeparatorToolItem(),
                    self.shelve_btn,
                    self.unshelve_btn,
                ]

        return tbuttons


    def save_settings(self):
        settings = GDialog.save_settings(self)
        settings['gstatus'] = (self._diffpane.get_position(),
                               self._setting_lastpos)
        return settings


    def load_settings(self, settings):
        GDialog.load_settings(self, settings)
        if settings:
            mysettings = settings['gstatus']
            self._setting_pos = mysettings[0]
            self._setting_lastpos = mysettings[1]
        else:
            self._setting_pos = 64000
            self._setting_lastpos = 270
        self.mqmode = None
        if hasattr(self.repo, 'mq') and self.repo.mq.applied:
            self.mqmode = True


    def get_body(self):
        self.connect('map-event', self._displayed)

        # TODO: should generate menus dynamically during right-click, currently
        # there can be entires that are not always supported or relavant.
        merge, addrem, unknown, clean, ignored, deleted, unresolved, resolved \
                = self.get_menu_info()
        merge_menu = self.make_menu(merge)
        addrem_menu = self.make_menu(addrem)
        unknown_menu = self.make_menu(unknown)
        clean_menu = self.make_menu(clean)
        ignored_menu = self.make_menu(ignored)
        deleted_menu = self.make_menu(deleted)
        resolved_menu = self.make_menu(resolved)
        unresolved_menu = self.make_menu(unresolved)

        # Dictionary with a key of file-stat and values containing context-menus
        self._menus = {}
        self._menus['M'] = merge_menu
        self._menus['A'] = addrem_menu
        self._menus['R'] = addrem_menu
        self._menus['?'] = unknown_menu
        self._menus['C'] = clean_menu
        self._menus['I'] = ignored_menu
        self._menus['!'] = deleted_menu
        self._menus['MR'] = resolved_menu
        self._menus['MU'] = unresolved_menu

        # model stores the file list.
        self.filemodel = gtk.ListStore(bool, str, str, str, str, bool)
        self.filemodel.set_sort_func(1001, self._sort_by_stat)
        self.filemodel.set_default_sort_func(self._sort_by_stat)

        self.filetree = gtk.TreeView(self.filemodel)
        self.filetree.connect('button-press-event', self._tree_button_press)
        self.filetree.connect('button-release-event', self._tree_button_release)
        self.filetree.connect('popup-menu', self._tree_popup_menu)
        self.filetree.connect('row-activated', self._tree_row_act)
        self.filetree.connect('key-press-event', self._tree_key_press)
        self.filetree.set_reorderable(False)
        self.filetree.set_enable_search(True)
        self.filetree.set_search_column(2)
        if hasattr(self.filetree, 'set_rubber_banding'):
            self.filetree.set_rubber_banding(True)
        self.filetree.modify_font(pango.FontDescription(self.fontlist))
        self.filetree.set_headers_clickable(True)
        
        toggle_cell = gtk.CellRendererToggle()
        toggle_cell.connect('toggled', self._select_toggle)
        toggle_cell.set_property('activatable', True)

        path_cell = gtk.CellRendererText()
        stat_cell = gtk.CellRendererText()

        self.selcb = None
        if self.count_revs() < 2 and len(self.repo.changectx(None).parents()) == 1:
            col0 = gtk.TreeViewColumn('', toggle_cell)
            col0.add_attribute(toggle_cell, 'active', FM_CHECKED)
            col0.add_attribute(toggle_cell, 'inconsistent', FM_PARTIAL_SELECTED)
            #col0.set_sort_column_id(0)
            col0.set_resizable(False)
            self.filetree.append_column(col0)
            self.selcb = self._add_header_checkbox(col0, self._sel_clicked)
        
        col1 = gtk.TreeViewColumn('st', stat_cell)
        col1.add_attribute(stat_cell, 'text', FM_STATUS)
        col1.set_cell_data_func(stat_cell, self._text_color)
        col1.set_sort_column_id(1001)
        col1.set_resizable(False)
        self.filetree.append_column(col1)
        
        col = gtk.TreeViewColumn('ms', stat_cell)
        col.add_attribute(stat_cell, 'text', FM_MERGE_STATUS)
        #col.set_cell_data_func(stat_cell, self._text_color)
        col.set_sort_column_id(4)
        col.set_resizable(False)
        self.filetree.append_column(col)
        
        col2 = gtk.TreeViewColumn('path', path_cell)
        col2.add_attribute(path_cell, 'text', FM_PATH_UTF8)
        col2.set_cell_data_func(path_cell, self._text_color)
        col2.set_sort_column_id(2)
        col2.set_resizable(True)
        self.filetree.append_column(col2)
       
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(self.filetree)
        
        tree_frame = gtk.Frame()
        tree_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        tree_frame.add(scroller)

        diff_frame = gtk.Frame()
        diff_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

        if self.count_revs() == 2 or len(self.repo.changectx(None).parents()) == 1:
            # use treeview to diff hunks

            sel = (os.name == 'nt') and 'CLIPBOARD' or 'PRIMARY'
            self.clipboard = gtk.Clipboard(selection=sel)

            self.diff_model = gtk.ListStore(bool, bool, str, bool, int)
            self.diff_tree = gtk.TreeView(self.diff_model)
            self.diff_tree.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
            self.diff_tree.modify_font(pango.FontDescription(self.fontlist))
            self.diff_tree.set_headers_visible(False)
            self.diff_tree.set_property('enable-grid-lines', True)
            self.diff_tree.connect('row-activated',
                    self._diff_tree_row_act)
            self.diff_tree.set_enable_search(False)
            self.diff_tree.set_headers_visible(False)
            self.diff_tree.connect('button-release-event',
                    self._patch_button_release)
            
            diff_hunk_cell = gtk.CellRendererText()
            diff_hunk_cell.set_property('cell-background', '#EEEEEE')
            diffcol = gtk.TreeViewColumn('diff', diff_hunk_cell)
            diffcol.set_resizable(True)
            self.diff_tree.append_column(diffcol)
            self.filetree.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
            self.filetree.get_selection().connect('changed',
                    self._tree_selection_changed, False)
            scroller.add(self.diff_tree)

            vbox = gtk.VBox()
            visiblerejects = gtk.CheckButton("Hide Rejected Chunks")
            visiblerejects.connect('toggled', self._toggle_rejects, diffcol,
                    diff_hunk_cell)
            vbox.pack_start(visiblerejects, False, False, 2)
            vbox.pack_start(scroller, True, True, 2)
            self._toggle_rejects(visiblerejects, diffcol, diff_hunk_cell)
            diff_frame.add(vbox)
        else:
            # display merge diffs in simple text view
            self.clipboard = None
            self.merge_diff_text = gtk.TextView()
            self.merge_diff_text.set_wrap_mode(gtk.WRAP_NONE)
            self.merge_diff_text.set_editable(False)
            self.merge_diff_text.modify_font(pango.FontDescription(self.fontdiff))
            self.filetree.get_selection().set_mode(gtk.SELECTION_SINGLE)
            self.filetree.get_selection().connect('changed',
                    self._merge_tree_selection_changed, False)
            self._activate_shelve_buttons(False)
            scroller.add(self.merge_diff_text)
            diff_frame.add(scroller)

        if self.diffbottom:
            self._diffpane = gtk.VPaned()
        else:
            self._diffpane = gtk.HPaned()

        self._diffpane.pack1(tree_frame, True, False)
        self._diffpane.pack2(diff_frame, True, True)
        self._diffpane.set_position(self._setting_pos)
        self._diffpane_moved_id = self._diffpane.connect('notify::position',
                self._diffpane_moved)
        self.filetree.set_headers_clickable(True)
        return self._diffpane

    def _patch_button_release(self, widget, event):
        '''Detect release of right mouse button on diff tree'''
        if event.button == 3 and not (event.state & gtk.gdk.CONTROL_MASK):
            self._diff_popup_menu(widget, event)
        return False

    def _diff_popup_menu(self, tree, event):
        sel = tree.get_selection()
        model, paths = sel.get_selected_rows()
        path = tree.get_path_at_pos(int(event.x), int(event.y))[0]
        if path not in paths:
            sel.unselect_all()
            sel.select_path(path)
            paths = [path]
        if not self.clipboard:
            return

        menu = gtk.Menu()
        menuitem = gtk.MenuItem('Copy to Clipboard', True)
        menuitem.connect('activate', self.copy_to_clipboard, paths)
        menuitem.set_border_width(1)
        menu.append(menuitem)
        menu.show_all()
        menu.popup(None, None, None, 0, 0)

    def copy_to_clipboard(self, menu, paths):
        fp = cStringIO.StringIO()
        for row, in paths:
            chunkid = self.diff_model[row][DM_CHUNK_ID]
            self._shelve_chunks[chunkid].write(fp)
        fp.seek(0)
        self.clipboard.set_text(fp.read())

    def _toggle_rejects(self, widget, diffcol, cell):
        diffcol.clear_attributes(cell)
        if widget.get_active():
            diffcol.set_attributes(cell,
                    visible=DM_NOT_REJECTED, 
                    markup=DM_CHUNK_TEXT,
                    cell_background_set=DM_HEADER_CHUNK)
        else:
            diffcol.set_attributes(cell,
                    strikethrough=DM_REJECTED, 
                    markup=DM_CHUNK_TEXT,
                    cell_background_set=DM_HEADER_CHUNK)

    def get_extras(self):
        table = gtk.Table(rows=2, columns=3)
        table.set_col_spacings(8)

        self._show_checks = {}
        row, col = 0, 0
        checks = ('modified', 'added', 'removed')
        if self.count_revs() <= 1:
            checks += ('deleted', 'unknown', 'clean', 'ignored')

        for type in checks:
            check = gtk.CheckButton('_' + type)
            check.connect('toggled', self._show_toggle, type)
            table.attach(check, col, col+1, row, row+1)
            self._show_checks[type] = check
            col += row
            row = not row
            
        self.counter = gtk.Label('')
        self.counter.set_alignment(1.0, 0.0) # right up

        hbox = gtk.HBox()
        hbox.pack_start(table, expand=False)
        hbox.pack_end(self.counter, expand=True, padding=2)
        
        return hbox

    def _add_header_checkbox(self, col, post=None, pre=None, toggle=False):
        def cbclick(hdr, cb):
            state = cb.get_active()
            if pre:
                pre(state)
            if toggle:
                cb.set_active(not state)
            if post:
                post(not state)
            
        cb = gtk.CheckButton(col.get_title())
        cb.show()
        col.set_widget(cb)
        wgt = cb.get_parent()
        while wgt:
            if type(wgt) == gtk.Button:
                wgt.connect("clicked", cbclick, cb)
                return cb
            wgt = wgt.get_parent()
        print "Warning: checkbox action not connected"
        return


    def _update_check_count(self):
        file_count = 0
        check_count = 0
        for row in self.filemodel:
            file_count = file_count + 1
            if row[FM_CHECKED]:
                check_count = check_count + 1
        self.counter.set_text(_('%d selected, %d total') % (check_count, file_count))
        if self.selcb:
            self.selcb.set_active(file_count and file_count == check_count)

    def prepare_display(self):
        self._ready = True
        self._last_file = None
        self._shelve_chunks = []
        self._filechunks = {}
        # If the status load failed, no reason to continue
        if not self.reload_status():
            raise util.Abort('could not load status')


    def _displayed(self, widget, event):
        self._diffpane_moved(self._diffpane)
        return False

    ### End of overrides ###

    def _do_reload_status(self):
        """Clear out the existing ListStore model and reload it from the repository status. 
        Also recheck and reselect files that remain in the list.
        """
        self.repo.dirstate.invalidate()
        self.repo.invalidate()

        # The following code was copied from the status function in mercurial\commands.py
        # and modified slightly to work here
        
        if self.mqmode and not self.opts.get('rev'):
            # when a patch is applied, show diffs to parent of top patch
            self._node1 = self.repo.lookup(-3)
            self._node2 = None
        else:
            # node2 is None (the working dir) when 0 or 1 rev is specificed
            self._node1, self._node2 = cmdutil.revpair(self.repo, self.opts.get('rev'))

        matcher = cmdutil.match(self.repo, self.pats, self.opts)
        cwd = (self.pats and self.repo.getcwd()) or ''
        status = [n for n in self.repo.status(node1=self._node1, node2=self._node2,
                                 match=matcher,
                                 ignored=self.test_opt('ignored'),
                                 clean=self.test_opt('clean'),
                                 unknown=self.test_opt('unknown'))]

        (modified, added, removed, deleted, unknown, ignored, clean) = status
        self.modified = modified

        if not self.opts.get('rev') and deleted and unknown:
            print "Suggest to detect copies or renames"

        changetypes = (('modified', 'M', modified),
                       ('added', 'A', added),
                       ('removed', 'R', removed),
                       ('deleted', '!', deleted),
                       ('unknown', '?', unknown),
                       ('ignored', 'I', ignored))
    
        explicit_changetypes = changetypes + (('clean', 'C', clean),)

        # List of the currently checked and selected files to pass on to the new data
        model, paths = self.filetree.get_selection().get_selected_rows()
        recheck = [entry[FM_PATH_UTF8] for entry in model if entry[FM_CHECKED]]
        reselect = [model[iter][FM_PATH_UTF8] for iter in paths]

        # merge-state of files
        ms = merge_.mergestate(self.repo)
        
        # Load the new data into the tree's model
        self.filetree.hide()
        self.filemodel.clear()
    
        for opt, char, changes in ([ct for ct in explicit_changetypes
                                    if self.test_opt(ct[0])] or changetypes) :
            for file in changes:
                mst = file in ms and ms[file].upper() or ""
                file = util.localpath(file)
                self.filemodel.append([file in recheck, char, toutf(file), file, mst, False])

        selection = self.filetree.get_selection()
        selected = False
        for row in model:
            if row[FM_PATH_UTF8] in reselect:
                selection.select_iter(row.iter)
                selected = True

        if not selected:
            selection.select_path((0,))

        files = [row[FM_PATH] for row in self.filemodel]
        self._show_diff_hunks(files)

        self.filetree.show()
        if hasattr(self, 'text'):
            self.text.grab_focus()
        else:
            self.filetree.grab_focus()
        return True


    def reload_status(self):
        if not self._ready: return False
        success, outtext = self._hg_call_wrapper('Status', self._do_reload_status)
        self.auto_check()
        self._update_check_count()
        return success


    def make_menu(self, entries):
        menu = gtk.Menu()
        for entry in entries:
            menu.append(self._make_menuitem(entry[0], entry[1]))
        menu.show_all()
        return menu


    def _make_menuitem(self, label, handler):
        menuitem = gtk.MenuItem(label, True)
        menuitem.connect('activate', self._context_menu_act, handler)
        menuitem.set_border_width(1)
        return menuitem


    def _select_toggle(self, cellrenderer, path):
        '''User manually toggled file status'''
        self.filemodel[path][FM_CHECKED] = not self.filemodel[path][FM_CHECKED]
        self._update_chunk_state(self.filemodel[path])
        self._update_check_count()
        return True

    def _update_chunk_state(self, entry):
        '''Update chunk toggle state to match file toggle state'''
        file = entry[FM_PATH]
        if file not in self._filechunks: return
        entry[FM_PARTIAL_SELECTED] = False
        for n in self._filechunks[file][1:]:
            self.diff_model[n][DM_NOT_REJECTED] = entry[FM_CHECKED]
            self.diff_model[n][DM_REJECTED] = not entry[FM_CHECKED]

    def _show_toggle(self, check, type):
        self.opts[type] = check.get_active()
        self.reload_status()
        return True


    def _sort_by_stat(self, model, iter1, iter2):
        order = 'MAR!?IC'
        lhs, rhs = (model.get_value(iter1, FM_STATUS), model.get_value(iter2, FM_STATUS))

        # GTK+ bug that calls sort before a full row is inserted causing values to be None.
        # When this happens, just return any value since the call is irrelevant and will be
        # followed by another with the correct (non-None) value
        if None in (lhs, rhs) :
            return 0

        result = order.find(lhs) - order.find(rhs)
        return min(max(result, -1), 1)
        

    def _text_color(self, column, text_renderer, list, row_iter):
        stat = list[row_iter][FM_STATUS]
        if stat == 'M':  
            text_renderer.set_property('foreground', '#000090')
        elif stat == 'A':
            text_renderer.set_property('foreground', '#006400')
        elif stat == 'R':
            text_renderer.set_property('foreground', '#900000')
        elif stat == 'C':
            text_renderer.set_property('foreground', 'black')
        elif stat == '!':
            text_renderer.set_property('foreground', 'red')
        elif stat == '?':
            text_renderer.set_property('foreground', '#AA5000')
        elif stat == 'I':
            text_renderer.set_property('foreground', 'black')
        else:
            text_renderer.set_property('foreground', 'black')


    def _view_left_file(self, stat, file):
        return self._view_file(stat, file, True)


    def _remove_file(self, stat, file):
        self._hg_remove([file])
        return True


    def _rename_file(self, stat, file):
        fdir, fname = os.path.split(file)
        newfile = entry_dialog(self, "Rename file to:", True, fname)
        if newfile and newfile != fname:
            self._hg_move([file, os.path.join(fdir, newfile)])
        return True


    def _copy_file(self, stat, file):
        file = self.repo.wjoin(file)
        fdir, fname = os.path.split(file)
        dialog = gtk.FileChooserDialog(parent=self,
                title='Copy file to',
                action=gtk.FILE_CHOOSER_ACTION_SAVE,
                buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,
                         gtk.STOCK_COPY,gtk.RESPONSE_OK))
        dialog.set_default_response(gtk.RESPONSE_OK)
        dialog.set_current_folder(fdir)
        dialog.set_current_name(fname)
        response = dialog.run()
        newfile=file
        if response == gtk.RESPONSE_OK:
            newfile = dialog.get_filename()
        dialog.destroy()
        if newfile != file:
            self._hg_copy([file, newfile])
        return True


    def _hg_remove(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        if self.count_revs() > 1:
            Prompt('Nothing Removed', 'Remove is not enabled when multiple revisions are specified.', self).run()
            return

        # Create new opts, so nothing unintented gets through
        removeopts = self.merge_opts(commands.table['^remove|rm'][1], ('include', 'exclude'))
        def dohgremove():
            commands.remove(self.ui, self.repo, *wfiles, **removeopts)
        success, outtext = self._hg_call_wrapper('Remove', dohgremove)
        if success:
            self.reload_status()


    def _hg_move(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        if self.count_revs() > 1:
            Prompt('Nothing Moved', 'Move is not enabled when '
                    'multiple revisions are specified.', self).run()
            return

        # Create new opts, so nothing unintented gets through
        moveopts = self.merge_opts(commands.table['rename|mv'][1],
                ('include', 'exclude'))
        def dohgmove():
            #moveopts['force'] = True
            commands.rename(self.ui, self.repo, *wfiles, **moveopts)
        success, outtext = self._hg_call_wrapper('Move', dohgmove)
        if success:
            self.reload_status()


    def _hg_copy(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        if self.count_revs() > 1:
            Prompt('Nothing Copied', 'Copy is not enabled when '
                    'multiple revisions are specified.', self).run()
            return

        # Create new opts, so nothing unintented gets through
        cmdopts = self.merge_opts(commands.table['copy|cp'][1],
                ('include', 'exclude'))
        def dohgcopy():
            commands.copy(self.ui, self.repo, *wfiles, **cmdopts)
        success, outtext = self._hg_call_wrapper('Copy', dohgcopy)
        if success:
            self.reload_status()

    def _merge_tree_selection_changed(self, selection, force):
        ''' Update the diff text with merge diff to both parents'''
        def dohgdiff():
            difftext = ['===== Diff to first parent =====\n']
            wfiles = [self.repo.wjoin(file)]
            matcher = cmdutil.match(self.repo, wfiles, self.opts)
            for s in patch.diff(self.repo, self.repo.dirstate.parents()[0], None,
                    match=matcher, opts=patch.diffopts(self.ui, self.opts)):
                difftext.extend(s.splitlines(True))
            difftext.append('\n===== Diff to second parent =====\n')
            for s in patch.diff(self.repo, self.repo.dirstate.parents()[1], None,
                    match=matcher, opts=patch.diffopts(self.ui, self.opts)):
                difftext.extend(s.splitlines(True))

            buffer = gtk.TextBuffer()
            buffer.create_tag('removed', foreground='#900000')
            buffer.create_tag('added', foreground='#006400')
            buffer.create_tag('position', foreground='#FF8000')
            buffer.create_tag('header', foreground='#000090')

            iter = buffer.get_start_iter()
            for line in difftext:
                line = toutf(line)
                if line.startswith('---') or line.startswith('+++'):
                    buffer.insert_with_tags_by_name(iter, line, 'header')
                elif line.startswith('-'):
                    line = diffexpand(line)
                    buffer.insert_with_tags_by_name(iter, line, 'removed')
                elif line.startswith('+'):
                    line = diffexpand(line)
                    buffer.insert_with_tags_by_name(iter, line, 'added')
                elif line.startswith('@@'):
                    buffer.insert_with_tags_by_name(iter, line, 'position')
                else:
                    line = diffexpand(line)
                    buffer.insert(iter, line)

            self.merge_diff_text.set_buffer(buffer)

        if self.showdiff_toggle.get_active():
            sel = self.filetree.get_selection().get_selected_rows()[1]
            if not sel:
                self._last_file = None
                return False
            file = self.filemodel[sel[0]][FM_PATH_UTF8]
            if force or file != self._last_file:
                self._last_file = file
                self._hg_call_wrapper('Diff', dohgdiff)
        return False


    def _tree_selection_changed(self, selection, force):
        if self.showdiff_toggle.get_active():
            sel = self.filetree.get_selection().get_selected_rows()[1]
            if not sel:
                self._last_file = None
                return False
            file = self.filemodel[sel[0]][FM_PATH_UTF8]
            if force or file != self._last_file:
                self._last_file = file
                if file in self._filechunks:
                    row = self._filechunks[file][0]
                    self.diff_tree.scroll_to_cell((row, ), None, True)
                    selection = self.diff_tree.get_selection()
                    selection.unselect_all()
                    selection.select_path((row,))
        return False

    def _diff_tree_row_act(self, dtree, path, column):
        dmodel = dtree.get_model()
        try:
            row = dmodel[path]
            chunk = self._shelve_chunks[row[DM_CHUNK_ID]]
            file = chunk.filename()
            if file not in self._filechunks:
                return
            for fr in self.filemodel:
                if fr[FM_PATH] == file:
                    break
            fchunks = self._filechunks[file][1:]
            if row[DM_HEADER_CHUNK]:
                for n in fchunks:
                    dmodel[n][DM_REJECTED] = fr[FM_CHECKED]
                fr[FM_CHECKED] = not fr[FM_CHECKED]
                fr[FM_PARTIAL_SELECTED] = False
                self._update_check_count()
            else:
                row[DM_REJECTED] = not row[DM_REJECTED]
                rej = [ n for n in fchunks if dmodel[n][DM_REJECTED] ]
                nonrej = [ n for n in fchunks if not dmodel[n][DM_REJECTED] ]
                newvalue = nonrej and True or False
                partial = rej and nonrej and True or False
                # Update file's check status
                fr[FM_PARTIAL_SELECTED] = partial
                if fr[FM_CHECKED] != newvalue:
                    fr[FM_CHECKED] = newvalue
                    self._update_check_count()
        finally:
            for row in dmodel:
                row[DM_NOT_REJECTED] = not row[DM_REJECTED]


    def _show_diff_hunks(self, files):
        ''' Update the diff text '''
        def markup(chunk):
            hunk = ""
            chunk.seek(0)
            lines = chunk.readlines()
            lines[-1] = lines[-1].strip('\n\r')
            for line in lines:
                line = gobject.markup_escape_text(toutf(line))
                if line.startswith('---') or line.startswith('+++'):
                    hunk += '<span foreground="#000090">%s</span>' % line
                elif line.startswith('-'):
                    hunk += '<span foreground="#900000">%s</span>' % line
                elif line.startswith('+'):
                    hunk += '<span foreground="#006400">%s</span>' % line
                elif line.startswith('@@'):
                    hunk = '<span foreground="#FF8000">%s</span>' % line
                else:
                    hunk += line

            return hunk

        def dohgdiff():
            self.diff_model.clear()
            try:
                difftext = []
                if len(files) != 0:
                    wfiles = [self.repo.wjoin(x) for x in files]
                    matcher = cmdutil.match(self.repo, wfiles, self.opts)
                    diffopts = mdiff.diffopts(git=True, nodates=True)
                    for s in patch.diff(self.repo, self._node1, self._node2,
                            match=matcher, opts=diffopts):
                        difftext.extend(s.splitlines(True))
                difftext = cStringIO.StringIO(''.join(difftext))
                difftext.seek(0)

                self._shelve_chunks = hgshelve.parsepatch(difftext)
                self._filechunks = {}
                skip = False
                for n, chunk in enumerate(self._shelve_chunks):
                    fp = cStringIO.StringIO()
                    chunk.pretty(fp)
                    markedup = markup(fp)
                    isheader = isinstance(chunk, hgshelve.header)
                    if isheader:
                        for f in chunk.files():
                            self._filechunks[f] = [len(self.diff_model)]
                        self.diff_model.append([False, True, markedup, True, n])
                        skip = chunk.special()
                    elif skip != True:
                        self._filechunks[chunk.filename()].append(len(self.diff_model))
                        self.diff_model.append([False, True, markedup, False, n])
            finally:
                difftext.close()

        if hasattr(self, 'merge_diff_text'):
            self.merge_diff_text.set_buffer(gtk.TextBuffer())
            return
        self._hg_call_wrapper('Diff', dohgdiff)

    def _has_shelve_file(self):
        return os.path.exists(self.repo.join('shelve'))
        
    def _activate_shelve_buttons(self, status):
        if status:
            self.shelve_btn.set_sensitive(True)
            self.unshelve_btn.set_sensitive(self._has_shelve_file())
        else:
            self.shelve_btn.set_sensitive(False)
            self.unshelve_btn.set_sensitive(False)

    def _showdiff_toggled(self, togglebutton, data=None):
        # prevent movement events while setting position
        self._diffpane.handler_block(self._diffpane_moved_id)

        if togglebutton.get_active():
            if hasattr(self, 'merge_diff_text'):
                self._merge_tree_selection_changed(self.filetree.get_selection(), True)
                self._activate_shelve_buttons(False)
            else:
                self._activate_shelve_buttons(True)
                self._tree_selection_changed(self.filetree.get_selection(), True)
            self._diffpane.set_position(self._setting_lastpos)
        else:
            self._setting_lastpos = self._diffpane.get_position()
            self._diffpane.set_position(64000)
            self._activate_shelve_buttons(False)

        self._diffpane.handler_unblock(self._diffpane_moved_id)
        return True


    def _diffpane_moved(self, paned, data=None):
        # prevent toggle events while setting toolbar state
        self.showdiff_toggle.handler_block(self._showdiff_toggled_id)
        if self.diffbottom:
            sizemax = self._diffpane.get_allocation().height
        else:
            sizemax = self._diffpane.get_allocation().width

        if self.showdiff_toggle.get_active():
            if paned.get_position() >= sizemax - 55:
                self.showdiff_toggle.set_active(False)
            self._activate_shelve_buttons(self.showdiff_toggle.get_active())
        elif paned.get_position() < sizemax - 55:
            self.showdiff_toggle.set_active(True)
            if hasattr(self, 'merge_diff_text'):
                self._merge_tree_selection_changed(self.filetree.get_selection(), True)
                self._activate_shelve_buttons(False)
            else:
                self._tree_selection_changed(self.filetree.get_selection(), True)
                self._activate_shelve_buttons(True)

        self.showdiff_toggle.handler_unblock(self._showdiff_toggled_id)
        return False
        

    def _refresh_clicked(self, toolbutton, data=None):
        self.reload_status()
        return True


    def _revert_clicked(self, toolbutton, data=None):
        revert_list = self._relevant_files('MAR!')
        if len(revert_list) > 0:
            self._hg_revert(revert_list)
        else:
            Prompt('Nothing Reverted', 'No revertable files selected', self).run()
        return True


    def _revert_file(self, stat, file):
        self._hg_revert([file])
        return True


    def _log_file(self, stat, file):
        from gtools import cmdtable
        from history import GLog
        
        # Might want to include 'rev' here... trying without
        statopts = self.merge_opts(cmdtable['glog|ghistory'][1], ('include', 'exclude', 'git'))
        dialog = GLog(self.ui, self.repo, self.cwd, [file], statopts, False)
        dialog.display()
        return True


    def _hg_revert(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        if self.count_revs() > 1:
            Prompt('Nothing Reverted', 'Revert is not enabled when multiple revisions are specified.', self).run()
            return

        # Create new opts,  so nothing unintented gets through.
        # commands.table revert key changed after 0.9.5, in change d4ec6d61b3ee
        key = '^revert' in commands.table and '^revert' or 'revert'
        revertopts = self.merge_opts(commands.table[key][1], ('include', 'exclude', 'rev'))
        def dohgrevert():
            commands.revert(self.ui, self.repo, *wfiles, **revertopts)

        # TODO: Ask which revision when multiple parents (currently just shows abort message)
        # TODO: Don't need to prompt when reverting added or removed files
        if self.count_revs() == 1:
            # rev options needs extra tweaking since is not an array for revert command
            revertopts['rev'] = revertopts['rev'][0]
            dialog = Confirm('Revert', files, self, 'Revert files to revision ' + revertopts['rev'] + '?')
        else:
            # rev options needs extra tweaking since it must be an empty string when unspecified for revert command
            revertopts['rev'] = ''
            dialog = Confirm('Revert', files, self)
        if dialog.run() == gtk.RESPONSE_YES:
            success, outtext = self._hg_call_wrapper('Revert', dohgrevert)
            if success:
                shell_notify(wfiles)
                self.reload_status()

    def _add_clicked(self, toolbutton, data=None):
        add_list = self._relevant_files('?I')
        if len(add_list) > 0:
            self._hg_add(add_list)
        else:
            Prompt('Nothing Added', 'No addable files selected', self).run()
        return True


    def _add_file(self, stat, file):
        self._hg_add([file])
        return True


    def _hg_add(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        # Create new opts, so nothing unintented gets through
        addopts = self.merge_opts(commands.table['^add'][1], ('include', 'exclude'))
        def dohgadd():
            commands.add(self.ui, self.repo, *wfiles, **addopts)
        success, outtext = self._hg_call_wrapper('Add', dohgadd)
        if success:
            shell_notify(wfiles)
            self.reload_status()

    def _shelve_selected(self):
        # get list of hunks that have not been rejected
        hlist = [x[DM_CHUNK_ID] for x in self.diff_model if not x[DM_REJECTED]]
        if not hlist:
            Prompt('Shelve', 'Please select diff chunks to shelve',
                    self).run()
            return

        doforce = False
        doappend = False
        if self._has_shelve_file():
            from gtklib import MessageDialog
            dialog = MessageDialog(flags=gtk.DIALOG_MODAL)
            dialog.set_title('Shelve')
            dialog.set_markup('<b>Shelve file exists!</b>')
            dialog.add_buttons('Overwrite', 1, 'Append', 2, 'Cancel', -1)
            dialog.set_transient_for(self)
            rval = dialog.run()
            dialog.destroy()
            if rval == -1:
                return
            if rval == 1:
                doforce = True
            if rval == 2:
                doappend = True

        # capture the selected hunks to shelve
        fc = []
        sc = []
        for n, c in enumerate(self._shelve_chunks):
            if isinstance(c, hgshelve.header):
                if len(fc) > 1 or (len(fc) == 1 and fc[0].binary()):
                    sc += fc
                fc = [c]
            elif n in hlist:
                fc.append(c)
        if len(fc) > 1 or (len(fc) == 1 and fc[0].binary()):
            sc += fc
                
        def filter_patch(ui, chunks):
            return sc

        # shelve them!
        self.ui.interactive = True  # hgshelve only works 'interactively'
        opts = {'addremove': None, 'include': [], 'force': doforce,
                'append': doappend, 'exclude': []}
        hgshelve.filterpatch = filter_patch
        hgshelve.shelve(self.ui, self.repo, **opts)
        self.reload_status()
        
    def _unshelve(self):
        opts = {'addremove': None, 'include': [], 'force': None,
                'append': None, 'exclude': [], 'inspect': None}
        try:
            hgshelve.unshelve(self.ui, self.repo, **opts)
            self.reload_status()
        except:
            pass

    def _shelve_clicked(self, toolbutton, data=None):
        self._shelve_selected()
        self._activate_shelve_buttons(True)

    def _unshelve_clicked(self, toolbutton, data=None):
        self._unshelve()
        self._activate_shelve_buttons(True)

    def _remove_clicked(self, toolbutton, data=None):
        remove_list = self._relevant_files('C')
        delete_list = self._relevant_files('?I')
        if len(remove_list) > 0:
            self._hg_remove(remove_list)
        if len(delete_list) > 0:
            self._delete_files(delete_list)
        if not remove_list and not delete_list:
            Prompt('Nothing Removed', 'No removable files selected', self).run()
        return True

    def _move_clicked(self, toolbutton, data=None):
        move_list = self._relevant_files('C')
        if move_list:
            # get destination directory to files into
            dialog = gtk.FileChooserDialog(title="Move files to diretory...",
                    parent=self,
                    action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                    buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,
                             gtk.STOCK_OPEN,gtk.RESPONSE_OK))
            dialog.set_default_response(gtk.RESPONSE_OK)
            dialog.set_current_folder(self.repo.root)
            response = dialog.run()
            destdir = dialog.get_filename()
            dialog.destroy()
            if response != gtk.RESPONSE_OK:
                return True
            
            # verify directory
            destroot = rootpath(destdir)
            if destroot != self.repo.root:
                Prompt('Nothing Moved', "Can't move outside repo!", self).run()
                return True
            
            # move the files to dest directory
            move_list.append(destdir)
            self._hg_move(move_list)
        else:
            Prompt('Nothing Moved', 'No movable files selected\n\n'
                    'Note: only clean files can be moved.', self).run()
        return True

    def _delete_file(self, stat, file):
        self._delete_files([file])

    def _delete_files(self, files):
        dialog = Confirm('Delete unrevisioned', files, self)
        if dialog.run() == gtk.RESPONSE_YES :
            errors = ''
            for file in files:
                try: 
                    os.unlink(self.repo.wjoin(file))
                except Exception, inst:
                    errors += str(inst) + '\n\n'

            if errors:
                errors = errors.replace('\\\\', '\\')
                if len(errors) > 500:
                    errors = errors[:errors.find('\n',500)] + '\n...'
                Prompt('Delete Errors', errors, self).run()

            self.reload_status()
        return True

    def _guess_rename(self, stat, file):
        import rename
        dialog = rename.DetectRenameDialog(self.repo.root)
        dialog.show_all()
        dialog.set_notify_func(self.ignoremask_updated)

    def _ignore_file(self, stat, file):
        import hgignore
        dialog = hgignore.HgIgnoreDialog(self.repo.root, util.pconvert(file))
        dialog.show_all()
        dialog.set_notify_func(self.ignoremask_updated)
        return True

    def ignoremask_updated(self):
        '''User has changed the ignore mask in hgignore dialog'''
        self.reload_status()

    def _mark_resolved(self, stat, file):
        ms = merge_.mergestate(self.repo)
        ms.mark(util.pconvert(file), "r")
        self.reload_status()


    def _unmark_resolved(self, stat, file):
        ms = merge_.mergestate(self.repo)
        ms.mark(util.pconvert(file), "u")
        self.reload_status()


    def _do_resolve(self, stat, file):
        ms = merge_.mergestate(self.repo)
        wctx = self.repo[None]
        mctx = wctx.parents()[-1]
        ms.resolve(util.pconvert(file), wctx, mctx)
        self.reload_status()


    def _sel_clicked(self, state):
        self._select_files(state)
        return True


    def _select_files(self, state, ctype=None):
        for entry in self.filemodel:
            if ctype and not entry[FM_STATUS] in ctype:
                continue
            if entry[FM_CHECKED] != state:
                entry[FM_CHECKED] = state
                self._update_chunk_state(entry)
        self._update_check_count()

    
    def _relevant_files(self, stats):
        return [item[FM_PATH] for item in self.filemodel \
                if item[FM_CHECKED] and item[FM_STATUS] in stats]


    def _context_menu_act(self, menuitem, handler):
        selection = self.filetree.get_selection()
        assert(selection.count_selected_rows() == 1)

        list, paths = selection.get_selected_rows() 
        path = paths[0]
        handler(list[path][1], list[path][3])
        return True


    def _tree_button_press(self, widget, event) :
        # Set the flag to ignore the next activation when the shift/control keys are
        # pressed. This avoids activations with multiple rows selected.
        if event.type == gtk.gdk._2BUTTON_PRESS and  \
          (event.state & (gtk.gdk.SHIFT_MASK | gtk.gdk.CONTROL_MASK)):
            self._ignore_next_act = True
        else:
            self._ignore_next_act = False
        return False


    def _tree_button_release(self, widget, event) :
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK | gtk.gdk.CONTROL_MASK)):
            self._tree_popup_menu(widget, event.button, event.time)
        return False

    def _get_file_context_menu(self, rowdata):
        st = rowdata[FM_STATUS]
        ms = rowdata[FM_MERGE_STATUS]
        if ms:
            menu = self._menus['M' + ms]
        else:
            menu = self._menus[st]
        return menu
            
    def _tree_popup_menu(self, widget, button=0, time=0) :
        selection = self.filetree.get_selection()
        if selection.count_selected_rows() != 1:
            return False

        list, paths = selection.get_selected_rows() 
        menu = self._get_file_context_menu(list[paths[0]])
        menu.popup(None, None, None, button, time)
        return True


    def _tree_key_press(self, tree, event):
        if event.keyval == 32:
            def toggler(list, path, iter):
                list[path][FM_CHECKED] = not list[path][FM_CHECKED]
                self._update_chunk_state(list[path])

            selection = self.filetree.get_selection()
            selection.selected_foreach(toggler)
            return True
        return False


    def _tree_row_act(self, tree, path, column) :
        """Default action is the first entry in the context menu
        """
        # Ignore activations (like double click) on the first column,
        # and ignore all actions if the flag is set
        if column.get_sort_column_id() == 0 or self._ignore_next_act:
            self._ignore_next_act = False
            return True

        selection = self.filetree.get_selection()
        if selection.count_selected_rows() != 1:
            return False

        list, paths = selection.get_selected_rows() 
        menu = self._get_file_context_menu(list[paths[0]])
        menu.get_children()[0].activate()
        return True

def run(root='', cwd='', files=[], **opts):
    u = ui.ui()
    u.updateopts(debug=False, traceback=False, quiet=True)
    repo = hg.repository(u, path=root)

    cmdoptions = {
        'all':False, 'clean':False, 'ignored':False, 'modified':True,
        'added':True, 'removed':True, 'deleted':True, 'unknown':True, 'rev':[],
        'exclude':[], 'include':[], 'debug':True, 'verbose':True, 'git':False,
        'check':True
    }
    
    dialog = GStatus(u, repo, cwd, files, cmdoptions, True)

    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    dialog.display()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or ''
    run(**opts)

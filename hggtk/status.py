#
# status.py - status dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright (C) 2007-8 TK Soh <teekaysoh@gmail.com>
# Copyright (C) 2008-9 Steve Borho <steve@borho.org>
#


import os
import cStringIO
import gtk
import gobject
import pango

from mercurial import cmdutil, util, commands, patch, mdiff
from mercurial import merge as merge_

from thgutil.i18n import _
from thgutil import hglib, shlib, paths

from hggtk import dialog, gdialog, hgshelve, gtklib, rename, hgignore

# file model row enumerations
FM_CHECKED = 0
FM_STATUS = 1
FM_PATH_UTF8 = 2
FM_PATH = 3
FM_MERGE_STATUS = 4
FM_PARTIAL_SELECTED = 5

# diff_model row enumerations
DM_REJECTED = 0
DM_MARKUP = 1
DM_TEXT = 2
DM_DISPLAYED = 3
DM_IS_HEADER = 4
DM_CHUNK_ID = 5
DM_FONT = 6

class GStatus(gdialog.GDialog):
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
        gdialog.GDialog.init(self)
        self.mode = 'status'

    def auto_check(self):
        if self.pats or self.opts.get('check'):
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
                ((_('_difference'), self._diff_file),
                    (_('edit'), self._view_file),
                    (_('view other'), self._view_left_file),
                    (_('_revert'), self._revert_file),
                    (_('l_og'), self._log_file)),
                # addrem
                ((_('_difference'), self._diff_file),
                    (_('_view'), self._view_file),
                    (_('_revert'), self._revert_file),
                    (_('l_og'), self._log_file)),
                # unknown
                ((_('_view'), self._view_file),
                    (_('_delete'), self._delete_file),
                    (_('_add'), self._add_file),
                    (_('_guess rename'), self._guess_rename),
                    (_('_ignore'), self._ignore_file)),
                # clean
                ((_('_view'), self._view_file),
                    (_('re_move'), self._remove_file),
                    (_('re_name'), self._rename_file),
                    (_('_copy'), self._copy_file),
                    (_('l_og'), self._log_file)),
                # ignored
                ((_('_view'), self._view_file),
                    (_('_delete'), self._delete_file)),
                # deleted
                ((_('_view'), self._view_file),
                    (_('_revert'), self._revert_file),
                    (_('re_move'), self._remove_file),
                    (_('l_og'), self._log_file)),
                # unresolved
                ((_('_difference'), self._diff_file),
                    (_('edit'), self._view_file),
                    (_('view other'), self._view_left_file),
                    (_('_revert'), self._revert_file),
                    (_('l_og'), self._log_file),
                    (_('resolve'), self._do_resolve),
                    (_('mark resolved'), self._mark_resolved)),
                # resolved
                ((_('_difference'), self._diff_file),
                    (_('edit'), self._view_file),
                    (_('view other'), self._view_left_file),
                    (_('_revert'), self._revert_file),
                    (_('l_og'), self._log_file),
                    (_('mark unresolved'), self._unmark_resolved)),
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
            wasset = False
            for opt in self.opts :
                if opt in self._show_checks and self.opts[opt]:
                    wasset = True
                    self._show_checks[opt].set_active(True)
            if not wasset:
                for check in [item[1] for item in self._show_checks.iteritems()
                              if item[0] in ('modified', 'added', 'removed',
                                             'deleted', 'unknown')]:
                    check.set_active(True)


    def get_title(self):
        root = os.path.basename(self.repo.root)
        revs = self.opts.get('rev')
        name = self.pats and _('filtered status') or _('status')
        r = revs and ':'.join(revs) or ''
        return ' '.join([root, name, r])

    def get_icon(self):
        return 'menushowchanged.ico'

    def get_defsize(self):
        return self._setting_defsize


    def get_tbbuttons(self):
        tbuttons = [self.make_toolbutton(gtk.STOCK_REFRESH, _('Re_fresh'),
            self._refresh_clicked, tip=_('refresh')),
                     gtk.SeparatorToolItem()]

        if self.count_revs() == 2:
            tbuttons += [
                    self.make_toolbutton(gtk.STOCK_SAVE_AS, _('Save As'),
                        self._save_clicked, tip=_('Save selected changes'))]
        else:
            tbuttons += [
                    self.make_toolbutton(gtk.STOCK_MEDIA_REWIND, _('Re_vert'),
                        self._revert_clicked, tip=_('revert')),
                    self.make_toolbutton(gtk.STOCK_ADD, _('_Add'),
                        self._add_clicked, tip=_('add')),
                    self.make_toolbutton(gtk.STOCK_JUMP_TO, _('Move'),
                        self._move_clicked,
                        tip=_('move selected files to other directory')),
                    self.make_toolbutton(gtk.STOCK_DELETE, _('_Remove'),
                        self._remove_clicked, tip=_('remove')),
                    gtk.SeparatorToolItem()]

        self.showdiff_toggle = gtk.ToggleToolButton(gtk.STOCK_JUSTIFY_FILL)
        self.showdiff_toggle.set_use_underline(True)
        self.showdiff_toggle.set_label(_('_Show Diff'))
        self.showdiff_toggle.set_tooltip(self.tooltips, _('show diff pane'))
        self.showdiff_toggle.set_active(False)
        self._showdiff_toggled_id = self.showdiff_toggle.connect('toggled',
                self._showdiff_toggled )
        tbuttons.append(self.showdiff_toggle)

        return tbuttons


    def save_settings(self):
        settings = gdialog.GDialog.save_settings(self)
        settings['gstatus-hpane'] = self._diffpane.get_position()
        settings['gstatus-lastpos'] = self._setting_lastpos
        return settings


    def load_settings(self, settings):
        gdialog.GDialog.load_settings(self, settings)
        self._setting_pos = 270
        self._setting_lastpos = 64000
        try:
            self._setting_pos = settings['gstatus-hpane']
            self._setting_lastpos = settings['gstatus-lastpos']
        except KeyError:
            pass
        self.mqmode = None
        if hasattr(self.repo, 'mq') and self.repo.mq.applied:
            self.mqmode = True


    def get_body(self):
        wctx = self.repo[None]
        self.merging = len(wctx.parents()) == 2

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
        self.filetree.set_search_equal_func(self.search_filelist)
        if hasattr(self.filetree, 'set_rubber_banding'):
            self.filetree.set_rubber_banding(True)
        self.filetree.modify_font(pango.FontDescription(self.fontlist))
        self.filetree.set_headers_clickable(True)

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)
        mod = gtklib.get_thg_modifier()
        key, modifier = gtk.accelerator_parse(mod+'d')
        self.filetree.add_accelerator('thg-diff', accelgroup, key,
                        modifier, gtk.ACCEL_VISIBLE)
        self.filetree.connect('thg-diff', self.thgdiff)
        self.connect('thg-refresh', self.thgrefresh)

        toggle_cell = gtk.CellRendererToggle()
        toggle_cell.connect('toggled', self._select_toggle)
        toggle_cell.set_property('activatable', True)

        path_cell = gtk.CellRendererText()
        stat_cell = gtk.CellRendererText()

        if self.merging:
            self.selcb = None
        else:
            # show file selection checkboxes only when applicable
            col0 = gtk.TreeViewColumn('', toggle_cell)
            col0.add_attribute(toggle_cell, 'active', FM_CHECKED)
            col0.add_attribute(toggle_cell, 'radio', FM_PARTIAL_SELECTED)
            col0.set_resizable(False)
            self.filetree.append_column(col0)
            self.selcb = self._add_header_checkbox(col0, self._sel_clicked)

        col1 = gtk.TreeViewColumn(_('st'), stat_cell)
        col1.add_attribute(stat_cell, 'text', FM_STATUS)
        col1.set_cell_data_func(stat_cell, self._text_color)
        col1.set_sort_column_id(1001)
        col1.set_resizable(False)
        self.filetree.append_column(col1)

        if self.merging:
            col = gtk.TreeViewColumn(_('ms'), stat_cell)
            col.add_attribute(stat_cell, 'text', FM_MERGE_STATUS)
            col.set_sort_column_id(4)
            col.set_resizable(False)
            self.filetree.append_column(col)

        col2 = gtk.TreeViewColumn(_('path'), path_cell)
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

        self.difffont = pango.FontDescription(self.fontlist)
        if self.merging:
            # display merge diffs in simple text view
            self.clipboard = None
            self.merge_diff_text = gtk.TextView()
            self.merge_diff_text.set_wrap_mode(gtk.WRAP_NONE)
            self.merge_diff_text.set_editable(False)
            self.merge_diff_text.modify_font(self.difffont)
            self.filetree.get_selection().set_mode(gtk.SELECTION_SINGLE)
            self.filetree.get_selection().connect('changed',
                    self.merge_sel_changed, False)
            scroller.add(self.merge_diff_text)
            diff_frame.add(scroller)
        else:
            # use treeview to show selectable diff hunks
            sel = (os.name == 'nt') and 'CLIPBOARD' or 'PRIMARY'
            self.clipboard = gtk.Clipboard(selection=sel)

            self.diff_model = gtk.ListStore(bool, str, str, str, bool, int,
                    pango.FontDescription)

            self.diff_tree = gtk.TreeView(self.diff_model)

            # set CTRL-c accelerator for copy-clipboard
            mod = gtklib.get_thg_modifier()
            key, modifier = gtk.accelerator_parse(mod+'c')
            self.diff_tree.add_accelerator('copy-clipboard', accelgroup, key,
                            modifier, gtk.ACCEL_VISIBLE)
            self.diff_tree.connect('copy-clipboard', self.copy_to_clipboard)

            self.diff_tree.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
            self.diff_tree.set_headers_visible(False)
            self.diff_tree.set_enable_search(False)
            self.diff_tree.set_property('enable-grid-lines', True)
            self.diff_tree.connect('row-activated',
                    self._diff_tree_row_act)

            cell = gtk.CellRendererText()
            diffcol = gtk.TreeViewColumn('diff', cell)
            diffcol.set_resizable(True)
            diffcol.add_attribute(cell, 'markup', DM_DISPLAYED)

            # differentiate header chunks
            cell.set_property('cell-background', '#DDDDDD')
            diffcol.add_attribute(cell, 'cell_background_set', DM_IS_HEADER)
            self.headerfont = self.difffont.copy()
            self.headerfont.set_weight(pango.WEIGHT_HEAVY)

            # differentiate rejected hunks
            self.rejfont = self.difffont.copy()
            self.rejfont.set_weight(pango.WEIGHT_LIGHT)
            diffcol.add_attribute(cell, 'font-desc', DM_FONT)
            cell.set_property('background', '#EEEEEE')
            cell.set_property('foreground', '#888888')
            diffcol.add_attribute(cell, 'background-set', DM_REJECTED)
            diffcol.add_attribute(cell, 'foreground-set', DM_REJECTED)

            self.diff_tree.append_column(diffcol)
            self.filetree.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
            self.filetree.get_selection().connect('changed',
                    self.tree_sel_changed, False)
            scroller.add(self.diff_tree)
            diff_frame.add(scroller)

        if self.diffbottom:
            self._diffpane = gtk.VPaned()
        else:
            self._diffpane = gtk.HPaned()

        self._diffpane.pack1(tree_frame, True, False)
        self._diffpane.pack2(diff_frame, True, True)
        self._diffpane_moved_id = self._diffpane.connect('notify::position',
                self._diffpane_moved)
        self.filetree.set_headers_clickable(True)
        gobject.idle_add(self.realize_status_settings)
        return self._diffpane

    def realize_status_settings(self):
        self._diffpane.set_position(self._setting_pos)

    def search_filelist(self, model, column, key, iter):
        'case insensitive filename search'
        key = key.lower()
        if key in model.get_value(iter, FM_PATH).lower():
            return False
        return True

    def thgdiff(self, treeview):
        selection = treeview.get_selection()
        model, tpaths = selection.get_selected_rows()
        row = model[tpaths[0]]
        self._diff_file(row[FM_STATUS], row[FM_PATH])

    def thgrefresh(self, window):
        self.reload_status()

    def copy_to_clipboard(self, treeview):
        'Write highlighted hunks to the clipboard'
        if not treeview.is_focus():
            w = self.get_focus()
            w.emit('copy-clipboard')
            return False
        model, tpaths = treeview.get_selection().get_selected_rows()
        cids = [ model[row][DM_CHUNK_ID] for row, in tpaths ]
        headers = {}
        fp = cStringIO.StringIO()
        for cid in cids:
            chunk = self._shelve_chunks[cid]
            wfile = chunk.filename()
            if not isinstance(chunk, hgshelve.header):
                # Ensure each hunk has a file header
                if wfile not in headers:
                    hrow = self._filechunks[wfile][0]
                    hcid = model[hrow][DM_CHUNK_ID]
                    self._shelve_chunks[hcid].write(fp)
            headers[wfile] = cid
            chunk.write(fp)
        fp.seek(0)
        self.clipboard.set_text(fp.read())

    def get_extras(self):
        table = gtk.Table(rows=2, columns=3)
        table.set_col_spacings(8)

        self._show_checks = {}
        row, col = 0, 0
        # Tuple: (ctype, translated label)
        checks = (('modified', _('modified')),
                  ('added', _('added')),
                  ('removed', _('removed')))
        if self.count_revs() <= 1:
            checks += (('deleted', _('deleted')),
                       ('unknown', _('unknown')),
                       ('close', _('clean')),
                       ('ignored', _('ignored')))

        for ctuple in checks:
            check = gtk.CheckButton(ctuple[1])
            check.connect('toggled', self._show_toggle, ctuple[0])
            table.attach(check, col, col+1, row, row+1)
            self._show_checks[ctuple[0]] = check
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
                wgt.connect('clicked', cbclick, cb)
                return cb
            wgt = wgt.get_parent()
        print 'Warning: checkbox action not connected'
        return


    def _update_check_count(self):
        file_count = 0
        check_count = 0
        for row in self.filemodel:
            file_count = file_count + 1
            if row[FM_CHECKED]:
                check_count = check_count + 1
        self.counter.set_text(_('%d selected, %d total') % (check_count,
                              file_count))
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
        """Clear out the existing ListStore model and reload it from the
        repository status.  Also recheck and reselect files that remain
        in the list.
        """
        selection = self.filetree.get_selection()
        if selection is None:
            return

        repo = self.repo
        hglib.invalidaterepo(repo)
        if hasattr(repo, 'mq'):
            self.mqmode = repo.mq.applied
            self.set_title(self.get_title())

        if self.mqmode and self.mode != 'status':
            # when a patch is applied, show diffs to parent of top patch
            qtip = repo['.']
            n1 = qtip.parents()[0].node()
            n2 = None
        else:
            # node2 is None (the working dir) when 0 or 1 rev is specificed
            n1, n2 = cmdutil.revpair(repo, self.opts.get('rev'))

        matcher = cmdutil.match(repo, self.pats, self.opts)
        status = repo.status(node1=n1, node2=n2, match=matcher,
                             ignored=self.test_opt('ignored'),
                             clean=self.test_opt('clean'),
                             unknown=self.test_opt('unknown'))

        (modified, added, removed, deleted, unknown, ignored, clean) = status
        self._node1, self._node2, self.modified = n1, n2, modified

        changetypes = (('modified', 'M', modified),
                       ('added', 'A', added),
                       ('removed', 'R', removed),
                       ('deleted', '!', deleted),
                       ('unknown', '?', unknown),
                       ('ignored', 'I', ignored))

        explicit_changetypes = changetypes + (('clean', 'C', clean),)

        # List of the currently checked and selected files to pass on to
        # the new data
        model, tpaths = selection.get_selected_rows()
        recheck = [entry[FM_PATH] for entry in model if entry[FM_CHECKED]]
        reselect = [model[path][FM_PATH] for path in tpaths]

        # merge-state of files
        ms = merge_.mergestate(repo)

        # Load the new data into the tree's model
        self.filetree.hide()
        self.filemodel.clear()

        for opt, char, changes in ([ct for ct in explicit_changetypes
                                    if self.test_opt(ct[0])] or changetypes):
            for wfile in changes:
                mst = wfile in ms and ms[wfile].upper() or ""
                wfile = util.localpath(wfile)
                self.filemodel.append([wfile in recheck, char,
                                       hglib.toutf(wfile), wfile, mst, False])

        selected = False
        for row in model:
            if row[FM_PATH] in reselect:
                selection.select_iter(row.iter)
                selected = True

        if not selected:
            selection.select_path((0,))

        files = [row[FM_PATH] for row in self.filemodel]
        self._show_diff_hunks(files)

        # clear buffer after a merge commit
        if not files and hasattr(self, 'merge_diff_text'):
            self.merge_diff_text.set_buffer(gtk.TextBuffer())

        self.filetree.show()
        if self.mode == 'commit':
            self.text.grab_focus()
        else:
            self.filetree.grab_focus()
        return True


    def reload_status(self):
        if not self._ready: return False
        self._last_file = None
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
        wfile = util.pconvert(entry[FM_PATH])
        if wfile not in self._filechunks: return
        selected = entry[FM_CHECKED]
        for n in self._filechunks[wfile][1:]:
            self.diff_model[n][DM_REJECTED] = not selected
            self._update_diff_hunk(self.diff_model[n])
        entry[FM_PARTIAL_SELECTED] = False
        self._update_diff_header(self.diff_model, wfile, selected)

    def _update_diff_hunk(self, row):
        if row[DM_REJECTED]:
            row[DM_FONT] = self.rejfont
            row[DM_DISPLAYED] = row[DM_TEXT]
        else:
            row[DM_FONT] = self.difffont
            row[DM_DISPLAYED] = row[DM_MARKUP]

    def _update_diff_header(self, dmodel, wfile, selected):
        fc = self._filechunks[wfile]
        hc = fc[0]
        lasthunk = len(fc)-1
        row = dmodel[hc]
        sel = lambda x: x >= lasthunk or not dmodel[hc+x+1][DM_REJECTED]
        newtext = self._shelve_chunks[row[DM_CHUNK_ID]].selpretty(sel)
        if not selected:
            newtext = "<span foreground='#888888'>" + newtext + "</span>"
        row[DM_DISPLAYED] = newtext

    def _show_toggle(self, check, toggletype):
        self.opts[toggletype] = check.get_active()
        self.reload_status()
        return True


    def _sort_by_stat(self, model, iter1, iter2):
        order = 'MAR!?IC'
        lhs, rhs = (model.get_value(iter1, FM_STATUS),
                    model.get_value(iter2, FM_STATUS))
        # GTK+ bug that calls sort before a full row is inserted causing
        # values to be None.  When this happens, just return any value
        # since the call is irrelevant and will be followed by another
        # with the correct (non-None) value
        if None in (lhs, rhs) :
            return 0

        result = order.find(lhs) - order.find(rhs)
        return min(max(result, -1), 1)


    def _text_color(self, column, text_renderer, model, row_iter):
        stat = model[row_iter][FM_STATUS]
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


    def _view_left_file(self, stat, wfile):
        return self._view_file(stat, wfile, True)


    def _remove_file(self, stat, wfile):
        self._hg_remove([wfile])
        return True


    def _rename_file(self, stat, wfile):
        fdir, fname = os.path.split(wfile)
        newfile = dialog.entry_dialog(self, _('Rename file to:'), True, fname)
        if newfile and newfile != fname:
            self._hg_move([wfile, os.path.join(fdir, newfile)])
        return True


    def _copy_file(self, stat, wfile):
        wfile = self.repo.wjoin(wfile)
        fdir, fname = os.path.split(wfile)
        dlg = gtk.FileChooserDialog(parent=self,
                title=_('Copy file to'),
                action=gtk.FILE_CHOOSER_ACTION_SAVE,
                buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,
                         gtk.STOCK_COPY,gtk.RESPONSE_OK))
        dlg.set_default_response(gtk.RESPONSE_OK)
        dlg.set_current_folder(fdir)
        dlg.set_current_name(fname)
        response = dlg.run()
        newfile=wfile
        if response == gtk.RESPONSE_OK:
            newfile = dlg.get_filename()
        dlg.destroy()
        if newfile != wfile:
            self._hg_copy([wfile, newfile])
        return True


    def _hg_remove(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        if self.count_revs() > 1:
            gdialog.Prompt(_('Nothing Removed'),
              _('Remove is not enabled when multiple revisions are specified.'),
              self).run()
            return

        # Create new opts, so nothing unintented gets through
        removeopts = self.merge_opts(commands.table['^remove|rm'][1],
                                     ('include', 'exclude'))
        def dohgremove():
            commands.remove(self.ui, self.repo, *wfiles, **removeopts)
        success, outtext = self._hg_call_wrapper('Remove', dohgremove)
        if success:
            shlib.update_thgstatus(self.ui, self.repo.root)
            self.reload_status()


    def _hg_move(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        if self.count_revs() > 1:
            gdialog.Prompt(_('Nothing Moved'), _('Move is not enabled when '
                    'multiple revisions are specified.'), self).run()
            return

        # Create new opts, so nothing unintented gets through
        moveopts = self.merge_opts(commands.table['rename|mv'][1],
                ('include', 'exclude'))
        def dohgmove():
            #moveopts['force'] = True
            commands.rename(self.ui, self.repo, *wfiles, **moveopts)
        success, outtext = self._hg_call_wrapper('Move', dohgmove)
        if success:
            shlib.update_thgstatus(self.ui, self.repo.root, wait=True)
            self.reload_status()


    def _hg_copy(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        if self.count_revs() > 1:
            gdialog.Prompt(_('Nothing Copied'), _('Copy is not enabled when '
                    'multiple revisions are specified.'), self).run()
            return

        # Create new opts, so nothing unintented gets through
        cmdopts = self.merge_opts(commands.table['copy|cp'][1],
                ('include', 'exclude'))
        def dohgcopy():
            commands.copy(self.ui, self.repo, *wfiles, **cmdopts)
        success, outtext = self._hg_call_wrapper('Copy', dohgcopy)
        if success:
            shlib.update_thgstatus(self.ui, self.repo.root, wait=True)
            self.reload_status()

    def merge_sel_changed(self, selection, force):
        ''' Update the diff text with merge diff to both parents'''
        def dohgdiff():
            difftext = [_('===== Diff to first parent =====\n')]
            wfiles = [self.repo.wjoin(wfile)]
            wctx = self.repo[None]
            matcher = cmdutil.match(self.repo, wfiles, self.opts)
            for s in patch.diff(self.repo, wctx.p1().node(), None,
                    match=matcher, opts=patch.diffopts(self.ui, self.opts)):
                difftext.extend(s.splitlines(True))
            difftext.append(_('\n===== Diff to second parent =====\n'))
            for s in patch.diff(self.repo, wctx.p2().node(), None,
                    match=matcher, opts=patch.diffopts(self.ui, self.opts)):
                difftext.extend(s.splitlines(True))

            buf = gtk.TextBuffer()
            buf.create_tag('removed', foreground='#900000')
            buf.create_tag('added', foreground='#006400')
            buf.create_tag('position', foreground='#FF8000')
            buf.create_tag('header', foreground='#000090')

            bufiter = buf.get_start_iter()
            for line in difftext:
                line = hglib.toutf(line)
                if line.startswith('---') or line.startswith('+++'):
                    buf.insert_with_tags_by_name(bufiter, line, 'header')
                elif line.startswith('-'):
                    line = hglib.diffexpand(line)
                    buf.insert_with_tags_by_name(bufiter, line, 'removed')
                elif line.startswith('+'):
                    line = hglib.diffexpand(line)
                    buf.insert_with_tags_by_name(bufiter, line, 'added')
                elif line.startswith('@@'):
                    buf.insert_with_tags_by_name(bufiter, line, 'position')
                else:
                    line = hglib.diffexpand(line)
                    buf.insert(bufiter, line)

            self.merge_diff_text.set_buffer(buf)

        if self.showdiff_toggle.get_active():
            sel = self.filetree.get_selection().get_selected_rows()[1]
            if not sel:
                self._last_file = None
                return False
            wfile = self.filemodel[sel[0]][FM_PATH]
            if force or wfile != self._last_file:
                self._last_file = wfile
                self._hg_call_wrapper('Diff', dohgdiff)
        return False


    def tree_sel_changed(self, selection, force):
        if self.showdiff_toggle.get_active():
            sel = self.filetree.get_selection().get_selected_rows()[1]
            if not sel:
                self._last_file = None
                return False
            wfile = util.pconvert(self.filemodel[sel[0]][FM_PATH])
            if force or wfile != self._last_file:
                self._last_file = wfile
                if wfile in self._filechunks:
                    row = self._filechunks[wfile][0]
                    self.diff_tree.scroll_to_cell((row, ), None, True)
                    selection = self.diff_tree.get_selection()
                    selection.unselect_all()
                    selection.select_path((row,))
        return False

    def _diff_tree_row_act(self, dtree, path, column):
        dmodel = dtree.get_model()
        row = dmodel[path]
        chunk = self._shelve_chunks[row[DM_CHUNK_ID]]
        wfile = chunk.filename()
        if wfile not in self._filechunks:
            return
        for fr in self.filemodel:
            if util.pconvert(fr[FM_PATH]) == wfile:
                break
        fchunks = self._filechunks[wfile][1:]
        if row[DM_IS_HEADER]:
            for n in fchunks:
                dmodel[n][DM_REJECTED] = fr[FM_CHECKED]
                self._update_diff_hunk(dmodel[n])
            newvalue = not fr[FM_CHECKED]
            partial = False
        else:
            row[DM_REJECTED] = not row[DM_REJECTED]
            self._update_diff_hunk(row)
            rej = [ n for n in fchunks if dmodel[n][DM_REJECTED] ]
            nonrej = [ n for n in fchunks if not dmodel[n][DM_REJECTED] ]
            newvalue = nonrej and True or False
            partial = rej and nonrej and True or False

        # Update file's check status
        if fr[FM_PARTIAL_SELECTED] != partial:
            fr[FM_PARTIAL_SELECTED] = partial
        if fr[FM_CHECKED] != newvalue:
            fr[FM_CHECKED] = newvalue
            self._update_check_count()
        self._update_diff_header(dmodel, wfile, newvalue)

    def _show_diff_hunks(self, files):
        ''' Update the diff text '''
        def markup(chunk):
            hunk = ""
            chunk.seek(0)
            lines = chunk.readlines()
            lines[-1] = lines[-1].strip('\n\r')
            for line in lines:
                line = gobject.markup_escape_text(hglib.toutf(line[:128]))
                if line[-1] != '\n':
                    line += '\n'
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

        def unmarkup(fp):
            hunk = ""
            fp.seek(0)
            lines = fp.readlines()
            lines[-1] = lines[-1].strip('\n\r')
            for line in lines:
                line = gobject.markup_escape_text(hglib.toutf(line[:128]))
                if line[-1] != '\n':
                    line += '\n'
                hunk += line
            return hunk

        def dohgdiff():
            self.diff_model.clear()
            difftext = cStringIO.StringIO()
            try:
                if len(files) != 0:
                    wfiles = [self.repo.wjoin(x) for x in files]
                    matcher = cmdutil.match(self.repo, wfiles, self.opts)
                    diffopts = mdiff.diffopts(git=True, nodates=True)
                    for s in patch.diff(self.repo, self._node1, self._node2,
                            match=matcher, opts=diffopts):
                        difftext.writelines(s.splitlines(True))
                difftext.seek(0)

                self._shelve_chunks = hgshelve.parsepatch(difftext)
                self._filechunks = {}
                skip = False
                for n, chunk in enumerate(self._shelve_chunks):
                    if isinstance(chunk, hgshelve.header):
                        text = chunk.selpretty(lambda x: True)
                        for f in chunk.files():
                            self._filechunks[f] = [len(self.diff_model)]
                        row = [False, text, text, text,
                               True, n, self.headerfont]
                        self.diff_model.append(row)
                        skip = chunk.special()
                    elif not skip:
                        fp = cStringIO.StringIO()
                        chunk.pretty(fp)
                        markedup = markup(fp)
                        text = unmarkup(fp)
                        f = chunk.filename()
                        self._filechunks[f].append(len(self.diff_model))
                        row = [False, markedup, text, markedup,
                               False, n, self.difffont]
                        self.diff_model.append(row)
            finally:
                difftext.close()

        if hasattr(self, 'merge_diff_text'):
            return
        self._hg_call_wrapper('Diff', dohgdiff)

    def _showdiff_toggled(self, togglebutton, data=None):
        # prevent movement events while setting position
        self._diffpane.handler_block(self._diffpane_moved_id)

        if togglebutton.get_active():
            if hasattr(self, 'merge_diff_text'):
                self.merge_sel_changed(self.filetree.get_selection(), True)
            else:
                self.tree_sel_changed(self.filetree.get_selection(), True)
            self._diffpane.set_position(self._setting_lastpos)
        else:
            self._setting_lastpos = self._diffpane.get_position()
            self._diffpane.set_position(64000)

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
        elif paned.get_position() < sizemax - 55:
            self.showdiff_toggle.set_active(True)
            selection = self.filetree.get_selection()
            if hasattr(self, 'merge_diff_text'):
                self.merge_sel_changed(selection, True)
            else:
                self.tree_sel_changed(selection, True)

        self.showdiff_toggle.handler_unblock(self._showdiff_toggled_id)
        return False


    def _refresh_clicked(self, toolbutton, data=None):
        self.reload_status()
        return True

    def _save_clicked(self, toolbutton, data=None):
        'Write selected diff hunks to a patch file'
        revrange = self.opts.get('rev')[0]
        filename = "%s.patch" % revrange.replace(':', '_to_')
        fd = gdialog.NativeSaveFileDialogWrapper(Title=_('Save patch to'),
                                         InitialDir=self.repo.root,
                                         FileName=filename)
        result = fd.run()
        if not result:
            return

        cids = []
        dmodel = self.diff_model
        for row in self.filemodel:
            if row[FM_CHECKED]:
                wfile = util.pconvert(row[FM_PATH])
                fc = self._filechunks[wfile]
                cids.append(fc[0])
                cids += [dmodel[r][DM_CHUNK_ID] for r in fc[1:] if not dmodel[r][DM_REJECTED]]
        try:
            fp = open(result, "w")
            for cid in cids:
                self._shelve_chunks[cid].write(fp)
        except OSError:
            pass
        finally:
            fp.close()

    def _revert_clicked(self, toolbutton, data=None):
        revert_list = self._relevant_files('MAR!')
        if len(revert_list) > 0:
            self._hg_revert(revert_list)
        else:
            gdialog.Prompt(_('Nothing Reverted'),
                   _('No revertable files selected'), self).run()
        return True


    def _revert_file(self, stat, wfile):
        self._hg_revert([wfile])
        return True


    def _log_file(self, stat, wfile):
        # Might want to include 'rev' here... trying without
        from hggtk import history
        dlg = history.GLog(self.ui, self.repo, self.cwd, [wfile], self.opts)
        dlg.display()
        return True


    def _hg_revert(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        if self.count_revs() > 1:
            gdialog.Prompt(_('Nothing Reverted'),
                   _('Revert not allowed when viewing revision range.'),
                   self).run()
            return

        # Create new opts,  so nothing unintented gets through.
        key = '^revert' in commands.table and '^revert' or 'revert'
        revertopts = self.merge_opts(commands.table[key][1],
                                     ('include', 'exclude', 'rev'))
        def dohgrevert():
            commands.revert(self.ui, self.repo, *wfiles, **revertopts)

        if self.count_revs() == 1:
            # rev options needs extra tweaking since is not an array for
            # revert command
            revertopts['rev'] = revertopts['rev'][0]
            dlg = gdialog.Confirm(_('Confirm Revert'), files, self,
                    _('Revert files to revision ') + revertopts['rev'] + '?')
        else:
            # rev options needs extra tweaking since it must be an empty
            # string when unspecified for revert command
            revertopts['rev'] = ''
            dlg = gdialog.Confirm('Confirm Revert', files, self)
        if not dlg or dlg.run() == gtk.RESPONSE_YES:
            success, outtext = self._hg_call_wrapper('Revert', dohgrevert)
            if success:
                shlib.update_thgstatus(self.ui, self.repo.root, wait=True)
                shlib.shell_notify(wfiles)
                self.reload_status()

    def _add_clicked(self, toolbutton, data=None):
        add_list = self._relevant_files('?I')
        if len(add_list) > 0:
            self._hg_add(add_list)
        else:
            gdialog.Prompt(_('Nothing Added'),
                   _('No addable files selected'), self).run()
        return True


    def _add_file(self, stat, wfile):
        self._hg_add([wfile])
        return True


    def _hg_add(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        # Create new opts, so nothing unintented gets through
        addopts = self.merge_opts(commands.table['^add'][1], ('include', 'exclude'))
        def dohgadd():
            commands.add(self.ui, self.repo, *wfiles, **addopts)
        success, outtext = self._hg_call_wrapper('Add', dohgadd)
        if success:
            shlib.update_thgstatus(self.ui, self.repo.root)
            shlib.shell_notify(wfiles)
            self.reload_status()

    def _remove_clicked(self, toolbutton, data=None):
        remove_list = self._relevant_files('C!')
        delete_list = self._relevant_files('?I')
        if len(remove_list) > 0:
            self._hg_remove(remove_list)
        if len(delete_list) > 0:
            self._delete_files(delete_list)
        if not remove_list and not delete_list:
            gdialog.Prompt(_('Nothing Removed'),
                   _('No removable files selected'), self).run()
        return True

    def _move_clicked(self, toolbutton, data=None):
        move_list = self._relevant_files('C')
        if move_list:
            # get destination directory to files into
            dlg = gtk.FileChooserDialog(title=_('Move files to diretory...'),
                    parent=self,
                    action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                    buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,
                             gtk.STOCK_OPEN,gtk.RESPONSE_OK))
            dlg.set_default_response(gtk.RESPONSE_OK)
            dlg.set_current_folder(self.repo.root)
            response = dlg.run()
            destdir = dlg.get_filename()
            dlg.destroy()
            if response != gtk.RESPONSE_OK:
                return True

            # verify directory
            destroot = paths.find_root(destdir)
            if destroot != self.repo.root:
                gdialog.Prompt(_('Nothing Moved'),
                       _('Cannot move outside repo!'), self).run()
                return True

            # move the files to dest directory
            move_list.append(hglib.fromutf(destdir))
            self._hg_move(move_list)
        else:
            gdialog.Prompt(_('Nothing Moved'), _('No movable files selected\n\n'
                    'Note: only clean files can be moved.'), self).run()
        return True

    def _delete_file(self, stat, wfile):
        self._delete_files([wfile])

    def _delete_files(self, files):
        dlg = gdialog.Confirm(_('Confirm Delete Unrevisioned'), files, self)
        if dlg.run() == gtk.RESPONSE_YES :
            errors = ''
            for wfile in files:
                try:
                    os.unlink(self.repo.wjoin(wfile))
                except Exception, inst:
                    errors += str(inst) + '\n\n'

            if errors:
                errors = errors.replace('\\\\', '\\')
                if len(errors) > 500:
                    errors = errors[:errors.find('\n',500)] + '\n...'
                gdialog.Prompt(_('Delete Errors'), errors, self).run()

            self.reload_status()
        return True

    def _guess_rename(self, stat, wfile):
        dlg = rename.DetectRenameDialog(self.repo.root)
        dlg.show_all()
        dlg.set_notify_func(self.ignoremask_updated)

    def _ignore_file(self, stat, wfile):
        dlg = hgignore.HgIgnoreDialog(self.repo.root, util.pconvert(wfile))
        dlg.show_all()
        dlg.set_notify_func(self.ignoremask_updated)
        return True

    def ignoremask_updated(self):
        '''User has changed the ignore mask in hgignore dialog'''
        self.reload_status()

    def _mark_resolved(self, stat, wfile):
        ms = merge_.mergestate(self.repo)
        ms.mark(util.pconvert(wfile), "r")
        self.reload_status()


    def _unmark_resolved(self, stat, wfile):
        ms = merge_.mergestate(self.repo)
        ms.mark(util.pconvert(wfile), "u")
        self.reload_status()


    def _do_resolve(self, stat, wfile):
        ms = merge_.mergestate(self.repo)
        wctx = self.repo[None]
        mctx = wctx.parents()[-1]
        ms.resolve(util.pconvert(wfile), wctx, mctx)
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

        model, tpaths = selection.get_selected_rows()
        path = tpaths[0]
        handler(model[path][FM_STATUS], model[path][FM_PATH])
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

        model, tpaths = selection.get_selected_rows()
        menu = self._get_file_context_menu(model[tpaths[0]])
        menu.popup(None, None, None, button, time)
        return True


    def _tree_key_press(self, tree, event):
        if event.keyval == 32:
            def toggler(model, path, bufiter):
                model[path][FM_CHECKED] = not model[path][FM_CHECKED]
                self._update_chunk_state(model[path])

            selection = self.filetree.get_selection()
            selection.selected_foreach(toggler)
            self._update_check_count()
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

        model, tpaths = selection.get_selected_rows()
        menu = self._get_file_context_menu(model[tpaths[0]])
        menu.get_children()[0].activate()
        return True

def run(ui, *pats, **opts):
    showclean = pats and True or False
    rev = opts.get('rev', [])
    cmdoptions = {
        'all':False, 'clean':showclean, 'ignored':False, 'modified':True,
        'added':True, 'removed':True, 'deleted':True, 'unknown':True, 'rev': rev,
        'exclude':[], 'include':[], 'debug':True, 'verbose':True, 'git':False,
        'check':True
    }
    return GStatus(ui, None, None, pats, cmdoptions)

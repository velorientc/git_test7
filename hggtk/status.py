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

from hggtk import dialog, gdialog, hgshelve, gtklib, guess, hgignore

# file model row enumerations
FM_CHECKED = 0
FM_STATUS = 1
FM_PATH_UTF8 = 2
FM_PATH = 3
FM_MERGE_STATUS = 4
FM_PARTIAL_SELECTED = 5

# diffmodel row enumerations
DM_REJECTED  = 0
DM_DISP_TEXT = 1
DM_IS_HEADER = 2
DM_PATH      = 3
DM_CHUNK_ID  = 4
DM_FONT      = 5

def hunk_markup(text):
    'Format a diff hunk for display in a TreeView row with markup'
    hunk = ""
    lines = text.split('\n')
    for line in lines:
        line = gtklib.markup_escape_text(hglib.toutf(line[:512])) + '\n'
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

def hunk_unmarkup(text):
    'Format a diff hunk for display in a TreeView row without markup'
    hunk = ""
    lines = text.split('\n')
    for line in lines:
        line = gtklib.markup_escape_text(hglib.toutf(line[:512])) + '\n'
        hunk += line
    return hunk

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
        self.ready = False
        self.filerowstart = {}
        self.filechunks = {}

    def auto_check(self):
        if self.pats or self.opts.get('check'):
            for entry in self.filemodel:
                entry[FM_CHECKED] = True
            self.update_check_count()

    def get_menu_info(self):
        """Returns menu info in this order:
            merge, addrem, unknown, clean, ignored, deleted,
            unresolved, resolved
        """
        return (
                # merge
                ((_('_difference'), self._diff_file),
                    (_('edit'), self._view_file),
                    (_('view other'), self.view_left_file),
                    (_('_revert'), self.revert_file),
                    (_('l_og'), self.log_file)),
                # addrem
                ((_('_difference'), self._diff_file),
                    (_('_view'), self._view_file),
                    (_('_revert'), self.revert_file),
                    (_('l_og'), self.log_file)),
                # unknown
                ((_('_view'), self._view_file),
                    (_('_delete'), self.delete_file),
                    (_('_add'), self.add_file),
                    (_('_guess rename'), self.guess_rename),
                    (_('_ignore'), self.ignore_file)),
                # clean
                ((_('_view'), self._view_file),
                    (_('re_move'), self.remove_file),
                    (_('re_name'), self.rename_file),
                    (_('_copy'), self.copy_file),
                    (_('l_og'), self.log_file)),
                # ignored
                ((_('_view'), self._view_file),
                    (_('_delete'), self.delete_file)),
                # deleted
                ((_('_view'), self._view_file),
                    (_('_revert'), self.revert_file),
                    (_('re_move'), self.remove_file),
                    (_('l_og'), self.log_file)),
                # unresolved
                ((_('_difference'), self._diff_file),
                    (_('edit'), self._view_file),
                    (_('view other'), self.view_left_file),
                    (_('_revert'), self.revert_file),
                    (_('l_og'), self.log_file),
                    (_('resolve'), self.do_resolve),
                    (_('mark resolved'), self.mark_resolved)),
                # resolved
                ((_('_difference'), self._diff_file),
                    (_('edit'), self._view_file),
                    (_('view other'), self.view_left_file),
                    (_('_revert'), self.revert_file),
                    (_('l_og'), self.log_file),
                    (_('mark unresolved'), self.unmark_resolved)),
                )

    ### End of overridable methods ###


    ### Overrides of base class methods ###

    def parse_opts(self):
        # Disable refresh while we toggle checkboxes
        self.ready = False

        # Determine which files to display
        if self.test_opt('all'):
            for check in self._show_checks.values():
                check.set_active(True)
        else:
            wasset = False
            for opt in self.opts:
                if opt in self._show_checks and self.opts[opt]:
                    wasset = True
                    self._show_checks[opt].set_active(True)
            if not wasset:
                for check in [item[1] for item in self._show_checks.iteritems()
                              if item[0] in ('modified', 'added', 'removed',
                                             'deleted', 'unknown')]:
                    check.set_active(True)
            if self.pats:
                for name, check in self._show_checks.iteritems():
                    check.set_sensitive(False)
        self.ready = True


    def get_title(self):
        root = hglib.toutf(os.path.basename(self.repo.root))
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
            self.refresh_clicked, tip=_('refresh')),
                     gtk.SeparatorToolItem()]

        if self.count_revs() == 2:
            tbuttons += [
                    self.make_toolbutton(gtk.STOCK_SAVE_AS, _('Save As'),
                        self.save_clicked, tip=_('Save selected changes'))]
        else:
            tbuttons += [
                    self.make_toolbutton(gtk.STOCK_MEDIA_REWIND, _('Re_vert'),
                        self.revert_clicked, tip=_('revert')),
                    self.make_toolbutton(gtk.STOCK_ADD, _('_Add'),
                        self.add_clicked, tip=_('add')),
                    self.make_toolbutton(gtk.STOCK_JUMP_TO, _('Move'),
                        self.move_clicked,
                        tip=_('move selected files to other directory')),
                    self.make_toolbutton(gtk.STOCK_DELETE, _('_Remove'),
                        self.remove_clicked, tip=_('remove')),
                    gtk.SeparatorToolItem()]
        return tbuttons


    def save_settings(self):
        settings = gdialog.GDialog.save_settings(self)
        settings['gstatus-hpane'] = self.diffpane.get_position()
        settings['gstatus-lastpos'] = self.setting_lastpos
        return settings


    def load_settings(self, settings):
        gdialog.GDialog.load_settings(self, settings)
        self.setting_pos = 270
        self.setting_lastpos = 64000
        try:
            self.setting_pos = settings['gstatus-hpane']
            self.setting_lastpos = settings['gstatus-lastpos']
        except KeyError:
            pass
        self.mqmode, repo = None, self.repo
        if hasattr(repo, 'mq') and repo.mq.applied and repo['.'] == repo['qtip']:
            self.mqmode = True


    def get_body(self):
        self.merging = len(self.repo.parents()) == 2

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
        fm = gtk.ListStore(bool, str, str, str, str, bool)
        fm.set_sort_func(1001, self.sort_by_stat)
        fm.set_default_sort_func(self.sort_by_stat)
        self.filemodel = fm

        self.filetree = gtk.TreeView(self.filemodel)
        self.filetree.connect('button-press-event', self.tree_button_press)
        self.filetree.connect('button-release-event', self.tree_button_release)
        self.filetree.connect('popup-menu', self.tree_popup_menu)
        self.filetree.connect('row-activated', self.tree_row_act)
        self.filetree.connect('key-press-event', self.tree_key_press)
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
        toggle_cell.connect('toggled', self.select_toggle)
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
            self.selcb = self.add_header_checkbox(col0, self.sel_clicked)

        col1 = gtk.TreeViewColumn(_('st'), stat_cell)
        col1.add_attribute(stat_cell, 'text', FM_STATUS)
        col1.set_cell_data_func(stat_cell, self.text_color)
        col1.set_sort_column_id(1001)
        col1.set_resizable(False)
        self.filetree.append_column(col1)

        if self.count_revs() <= 1:
            col = gtk.TreeViewColumn(_('ms'), stat_cell)
            col.add_attribute(stat_cell, 'text', FM_MERGE_STATUS)
            col.set_sort_column_id(4)
            col.set_resizable(False)
            self.filetree.append_column(col)

        col2 = gtk.TreeViewColumn(_('path'), path_cell)
        col2.add_attribute(path_cell, 'text', FM_PATH_UTF8)
        col2.set_cell_data_func(path_cell, self.text_color)
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
            sel = self.filetree.get_selection()
            sel.set_mode(gtk.SELECTION_SINGLE)
            self.treeselid = sel.connect('changed', self.merge_sel_changed)
            scroller.add(self.merge_diff_text)
            diff_frame.add(scroller)
        else:
            # use treeview to show selectable diff hunks
            sel = (os.name == 'nt') and 'CLIPBOARD' or 'PRIMARY'
            self.clipboard = gtk.Clipboard(selection=sel)

            self.diffmodel = gtk.ListStore(
                    bool, # DM_REJECTED
                    str,  # DM_DISP_TEXT
                    bool, # DM_IS_HEADER
                    str,  # DM_PATH
                    int,  # DM_CHUNK_ID
                    pango.FontDescription)

            difftree = gtk.TreeView(self.diffmodel)

            # set CTRL-c accelerator for copy-clipboard
            mod = gtklib.get_thg_modifier()
            key, modifier = gtk.accelerator_parse(mod+'c')
            difftree.add_accelerator('copy-clipboard', accelgroup, key,
                            modifier, gtk.ACCEL_VISIBLE)
            difftree.connect('copy-clipboard', self.copy_to_clipboard)

            difftree.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
            difftree.set_headers_visible(False)
            difftree.set_enable_search(False)
            difftree.set_property('enable-grid-lines', True)
            difftree.connect('row-activated', self.diff_tree_row_act)

            cell = gtk.CellRendererText()
            diffcol = gtk.TreeViewColumn('diff', cell)
            diffcol.set_resizable(True)
            diffcol.add_attribute(cell, 'markup', DM_DISP_TEXT)

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
            difftree.append_column(diffcol)
            scroller.add(difftree)
            diff_frame.add(scroller)

            sel = self.filetree.get_selection()
            sel.set_mode(gtk.SELECTION_MULTIPLE)
            self.treeselid = sel.connect('changed',
                    self.tree_sel_changed, difftree)

        if self.diffbottom:
            self.diffpane = gtk.VPaned()
        else:
            self.diffpane = gtk.HPaned()

        self.diffpane.pack1(tree_frame, True, False)
        self.diffpane.pack2(diff_frame, True, True)
        self.filetree.set_headers_clickable(True)
        return self.diffpane


    def get_extras(self):
        table = gtk.Table(rows=2, columns=3)
        table.set_col_spacings(8)

        self._show_checks = {}
        row, col = 0, 0
        # Tuple: (ctype, translated label)
        checks = (('modified', _('M: modified')),
                  ('added',    _('A: added')),
                  ('removed',  _('R: removed')))
        if self.count_revs() <= 1:
            checks += (('deleted', _('!: deleted')),
                       ('unknown', _('?: unknown')),
                       ('clean',   _('C: clean')),
                       ('ignored', _('I: ignored')))

        for ctuple in checks:
            check = gtk.CheckButton(ctuple[1])
            check.connect('toggled', self.show_toggle, ctuple[0])
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

    def add_header_checkbox(self, col, post=None, pre=None, toggle=False):
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
        return

    def update_check_count(self):
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
        gobject.idle_add(self.realize_status_settings)

    ### End of overrides ###

    def realize_status_settings(self):
        self.diffpane.set_position(self.setting_pos)
        self.reload_status()

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
        saves = {}
        model, tpaths = treeview.get_selection().get_selected_rows()
        for row, in tpaths:
            wfile, cid = model[row][DM_PATH], model[row][DM_CHUNK_ID]
            if wfile not in saves:
                saves[wfile] = [cid]
            else:
                saves[wfile].append(cid)
        fp = cStringIO.StringIO()
        for wfile in saves.keys():
            chunks = self.filechunks[wfile]
            chunks[0].write(fp)
            for cid in saves[wfile]:
                if cid != 0:
                    chunks[cid].write(fp)
        fp.seek(0)
        self.clipboard.set_text(fp.read())

    def do_reload_status(self):
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
            self.mqmode = repo.mq.applied and repo['.'] == repo['qtip']
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

        changetypes = (('M', 'modified', modified),
                       ('A', 'added', added),
                       ('R', 'removed', removed),
                       ('!', 'deleted', deleted),
                       ('?', 'unknown', unknown),
                       ('I', 'ignored', ignored),
                       ('C', 'clean', clean))

        # List of the currently checked and selected files to pass on to
        # the new data
        model, tpaths = selection.get_selected_rows()
        reselect = [model[path][FM_PATH] for path in tpaths]
        waschecked = {}
        for row in model:
            waschecked[row[FM_PATH]] = row[FM_CHECKED], row[FM_PARTIAL_SELECTED]

        # merge-state of files
        ms = merge_.mergestate(repo)

        # Load the new data into the tree's model
        self.filetree.hide()
        selection.handler_block(self.treeselid)
        self.filemodel.clear()

        types = [ct for ct in changetypes if self.opts.get(ct[1])]
        for stat, _, wfiles in types:
            for wfile in wfiles:
                mst = wfile in ms and ms[wfile].upper() or ""
                wfile = util.localpath(wfile)
                ck, p = waschecked.get(wfile, (stat in 'MAR', False))
                model.append([ck, stat, hglib.toutf(wfile), wfile, mst, p])

        self.auto_check() # may check more files

        # recover selections
        firstrow = None
        for i, row in enumerate(model):
            if row[FM_PATH] in reselect:
                if firstrow is None:
                    firstrow = i
                else:
                    selection.select_iter(row.iter)
        selection.handler_unblock(self.treeselid)

        if len(model):
            selection.select_path((firstrow or 0,))
        else:
            # clear diff pane if no files
            if self.merging:
                self.merge_diff_text.set_buffer(gtk.TextBuffer())
            else:
                self.diffmodel.clear()

        self.filetree.show()
        if self.mode == 'commit':
            self.text.grab_focus()
        else:
            self.filetree.grab_focus()
        return True


    def reload_status(self):
        if not self.ready: return False
        self.do_reload_status()
        self.update_check_count()


    def make_menu(self, entries):
        menu = gtk.Menu()
        for entry in entries:
            menu.append(self.make_menuitem(entry[0], entry[1]))
        menu.show_all()
        return menu


    def make_menuitem(self, label, handler):
        menuitem = gtk.MenuItem(label, True)
        menuitem.connect('activate', self.context_menu_act, handler)
        menuitem.set_border_width(1)
        return menuitem


    def select_toggle(self, cellrenderer, path):
        'User manually toggled file status via checkbox'
        self.filemodel[path][FM_CHECKED] = not self.filemodel[path][FM_CHECKED]
        self.update_chunk_state(self.filemodel[path])
        self.update_check_count()
        return True

    def update_chunk_state(self, fileentry):
        'Update chunk toggle state to match file toggle state'
        fileentry[FM_PARTIAL_SELECTED] = False
        wfile = fileentry[FM_PATH]
        selected = fileentry[FM_CHECKED]
        if wfile not in self.filechunks:
            return
        chunks = self.filechunks[wfile]
        for chunk in chunks:
            chunk.active = selected
        # this file's chunks may not be in diffmodel
        if wfile not in self.filerowstart:
            return
        rowstart = self.filerowstart[wfile]
        for n, chunk in enumerate(chunks):
            if n == 0:
                continue
            self.diffmodel[rowstart+n][DM_REJECTED] = not selected
            self.update_diff_hunk(self.diffmodel[rowstart+n])
        self.update_diff_header(self.diffmodel, wfile, selected)

    def update_diff_hunk(self, row):
        'Update the contents of a diff row based on its chunk state'
        wfile = row[DM_PATH]
        chunks = self.filechunks[wfile]
        chunk = chunks[row[DM_CHUNK_ID]]
        buf = cStringIO.StringIO()
        chunk.pretty(buf)
        buf.seek(0)
        if chunk.active:
            row[DM_REJECTED] = False
            row[DM_FONT] = self.difffont
            row[DM_DISP_TEXT] = hunk_markup(buf.read())
        else:
            row[DM_REJECTED] = True
            row[DM_FONT] = self.rejfont
            row[DM_DISP_TEXT] = hunk_unmarkup(buf.read())

    def update_diff_header(self, dmodel, wfile, selected):
        try:
            hc = self.filerowstart[wfile]
            chunks = self.filechunks[wfile]
        except IndexError:
            return
        lasthunk = len(chunks)-1
        sel = lambda x: x >= lasthunk or not dmodel[hc+x+1][DM_REJECTED]
        newtext = chunks[0].selpretty(sel)
        if not selected:
            newtext = "<span foreground='#888888'>" + newtext + "</span>"
        dmodel[hc][DM_DISP_TEXT] = newtext

    def show_toggle(self, check, toggletype):
        self.opts[toggletype] = check.get_active()
        self.reload_status()
        return True


    def sort_by_stat(self, model, iter1, iter2):
        order = 'MAR!?IC'
        lhs, rhs = (model.get_value(iter1, FM_STATUS),
                    model.get_value(iter2, FM_STATUS))
        # GTK+ bug that calls sort before a full row is inserted causing
        # values to be None.  When this happens, just return any value
        # since the call is irrelevant and will be followed by another
        # with the correct (non-None) value
        if None in (lhs, rhs):
            return 0

        result = order.find(lhs) - order.find(rhs)
        return min(max(result, -1), 1)


    def text_color(self, column, text_renderer, model, row_iter):
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


    def view_left_file(self, stat, wfile):
        return self._view_file(stat, wfile, True)


    def remove_file(self, stat, wfile):
        self.hg_remove([wfile])
        return True


    def rename_file(self, stat, wfile):
        fdir, fname = os.path.split(wfile)
        newfile = dialog.entry_dialog(self, _('Rename file to:'), True, fname)
        if newfile and newfile != fname:
            self.hg_move([wfile, os.path.join(fdir, newfile)])
        return True


    def copy_file(self, stat, wfile):
        wfile = self.repo.wjoin(wfile)
        fdir, fname = os.path.split(wfile)
        response = gtklib.NativeSaveFileDialogWrapper(
                Title=_('Copy file to'),
                InitialDir=fdir,
                FileName=fname).run()
        if not response:
            return
        if reponse != wfile:
            self.hg_copy([wfile, reponse])
        return True


    def hg_remove(self, files):
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
            self.reload_status()


    def hg_move(self, files):
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
            self.reload_status()


    def hg_copy(self, files):
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
            self.reload_status()

    def merge_sel_changed(self, selection):
        'Selected row in file tree activated changed (merge mode)'
        # Update the diff text with merge diff to both parents
        model, paths = selection.get_selected_rows()
        if not paths:
            return
        wfile = self.filemodel[paths[0]][FM_PATH]
        difftext = [_('===== Diff to first parent =====\n')]
        wfiles = [self.repo.wjoin(wfile)]
        wctx = self.repo[None]
        pctxs = wctx.parents()
        matcher = cmdutil.match(self.repo, wfiles, self.opts)
        for s in patch.diff(self.repo, pctxs[0].node(), None,
                match=matcher, opts=patch.diffopts(self.ui, self.opts)):
            difftext.extend(s.splitlines(True))
        if len(pctxs) > 1:
            difftext.append(_('\n===== Diff to second parent =====\n'))
            for s in patch.diff(self.repo, pctxs[1].node(), None,
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


    def tree_sel_changed(self, selection, tree):
        'Selected row in file tree activated changed'
        # Read this file's diffs into diff model
        model, paths = selection.get_selected_rows()
        if not paths:
            return
        wfile = self.filemodel[paths[0]][FM_PATH]
        # TODO: this could be a for-loop
        self.filerowstart = {}
        self.diffmodel.clear()
        self.append_diff_hunks(wfile)
        if len(self.diffmodel):
            tree.scroll_to_cell(0, use_align=True, row_align=0.0)

    def read_file_chunks(self, wfile):
        'Get diffs of working file, parse into (c)hunks'
        difftext = cStringIO.StringIO()
        ctx = self.repo[self._node1]
        try:
            fctx = ctx.filectx(wfile)
        except hglib.LookupError:
            fctx = None
        if fctx and fctx.size() > hglib.getmaxdiffsize(self.ui):
            # Fake patch that displays size warning
            lines = ['diff --git a/%s b/%s\n' % (wfile, wfile)]
            lines.append(_('File is larger than the specified max size.\n'))
            lines.append(_('Hunk selection is disabled for this file.\n'))
            lines.append('--- a/%s\n' % wfile)
            lines.append('+++ b/%s\n' % wfile)
            difftext.writelines(lines)
            difftext.seek(0)
        else:
            wfiles = [self.repo.wjoin(wfile)]
            matcher = cmdutil.match(self.repo, wfiles, self.opts)
            diffopts = mdiff.diffopts(git=True, nodates=True)
            for s in patch.diff(self.repo, self._node1, self._node2,
                    match=matcher, opts=diffopts):
                difftext.writelines(s.splitlines(True))
            difftext.seek(0)
        return hgshelve.parsepatch(difftext)

    def append_diff_hunks(self, wfile):
        'Append diff hunks of one file to the diffmodel'
        chunks = self.read_file_chunks(wfile)
        if not chunks:
            if wfile in self.filechunks:
                del self.filechunks[wfile]
            return

        for fr in self.filemodel:
            if fr[FM_PATH] == wfile:
                break
        else:
            # should not be possible
            return

        rows = []
        for n, chunk in enumerate(chunks):
            if isinstance(chunk, hgshelve.header):
                # header chunk is always active
                chunk.active = True
                rows.append([False, '', True, wfile, n, self.headerfont])
                if chunk.special():
                    chunks = chunks[:1]
                    break
            else:
                # chunks take file's selection state by default
                chunk.active = fr[FM_CHECKED]
                rows.append([False, '', False, wfile, n, self.difffont])


        # recover old chunk selection/rejection states, match fromline
        if wfile in self.filechunks:
            ochunks = self.filechunks[wfile]
            next = 1
            for oc in ochunks[1:]:
                for n in xrange(next, len(chunks)):
                    nc = chunks[n]
                    if oc.fromline == nc.fromline:
                        nc.active = oc.active
                        next = n+1
                        break
                    elif nc.fromline > oc.fromline:
                        break

        self.filerowstart[wfile] = len(self.diffmodel)
        self.filechunks[wfile] = chunks

        # Set row status based on chunk state
        rej, nonrej = False, False
        for n, row in enumerate(rows):
            if not row[DM_IS_HEADER]:
                if chunks[n].active:
                    nonrej = True
                else:
                    rej = True
                row[DM_REJECTED] = not chunks[n].active
                self.update_diff_hunk(row)
            self.diffmodel.append(row)

        if len(rows) == 1:
            newvalue = fr[FM_CHECKED]
        else:
            newvalue = nonrej
            partial = rej and nonrej
            if fr[FM_PARTIAL_SELECTED] != partial:
                fr[FM_PARTIAL_SELECTED] = partial
            if fr[FM_CHECKED] != newvalue:
                fr[FM_CHECKED] = newvalue
                self.update_check_count()
        self.update_diff_header(self.diffmodel, wfile, newvalue)


    def diff_tree_row_act(self, dtree, path, column):
        'Row in diff tree (hunk) activated/toggled'
        dmodel = dtree.get_model()
        row = dmodel[path]
        wfile = row[DM_PATH]
        try:
            startrow = self.filerowstart[wfile]
            chunks = self.filechunks[wfile]
        except IndexError:
            pass
        chunkrows = xrange(startrow+1, startrow+len(chunks))
        for fr in self.filemodel:
            if fr[FM_PATH] == wfile:
                break
        if row[DM_IS_HEADER]:
            for n, chunk in enumerate(chunks[1:]):
                chunk.active = not fr[FM_CHECKED]
                self.update_diff_hunk(dmodel[startrow+n+1])
            newvalue = not fr[FM_CHECKED]
            partial = False
        else:
            chunk = chunks[row[DM_CHUNK_ID]]
            chunk.active = not chunk.active
            self.update_diff_hunk(row)
            rej = [ n for n in chunkrows if dmodel[n][DM_REJECTED] ]
            nonrej = [ n for n in chunkrows if not dmodel[n][DM_REJECTED] ]
            newvalue = nonrej and True or False
            partial = rej and nonrej and True or False

        # Update file's check status
        if fr[FM_PARTIAL_SELECTED] != partial:
            fr[FM_PARTIAL_SELECTED] = partial
        if fr[FM_CHECKED] != newvalue:
            fr[FM_CHECKED] = newvalue
            chunks[0].active = newvalue
            self.update_check_count()
        self.update_diff_header(dmodel, wfile, newvalue)


    def refresh_clicked(self, toolbutton, data=None):
        self.reload_status()
        return True

    def save_clicked(self, toolbutton, data=None):
        'Write selected diff hunks to a patch file'
        revrange = self.opts.get('rev')[0]
        filename = "%s.patch" % revrange.replace(':', '_to_')
        fd = gtklib.NativeSaveFileDialogWrapper(Title=_('Save patch to'),
                                         InitialDir=self.repo.root,
                                         FileName=filename)
        result = fd.run()
        if not result:
            return

        buf = cStringIO.StringIO()
        dmodel = self.diffmodel
        for row in self.filemodel:
            if not row[FM_CHECKED]:
                continue
            wfile = row[FM_PATH]
            if wfile not in self.filechunks:
                continue
            chunks = self.filechunks[wfile]
            for i, chunk in enumerate(chunks):
                if i == 0:
                    chunk.write(buf)
                elif chunk.active:
                    chunk.write(buf)
        buf.seek(0)
        try:
            try:
                fp = open(result, "w")
                fp.write(buf.read())
            except OSError:
                pass
        finally:
            fp.close()

    def revert_clicked(self, toolbutton, data=None):
        revert_list = self.relevant_files('MAR!')
        if len(revert_list) > 0:
            self.hg_revert(revert_list)
        else:
            gdialog.Prompt(_('Nothing Reverted'),
                   _('No revertable files selected'), self).run()
        return True


    def revert_file(self, stat, wfile):
        self.hg_revert([wfile])
        return True


    def log_file(self, stat, wfile):
        # Might want to include 'rev' here... trying without
        from hggtk import history
        dlg = history.GLog(self.ui, self.repo, self.cwd, [wfile], self.opts)
        dlg.display()
        return True


    def hg_revert(self, files):
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
                    _('Revert files to revision %s?') % revertopts['rev'])
        elif self.merging:
            resp = gdialog.CustomPrompt(_('Which parent to revert to?'),
                    _('Revert file(s) to local or other parent?'),
                    self, (_('&local'), _('&other')), _('l')).run()
            if resp == ord(_('l')):
                revertopts['rev'] = self.repo[None].p1().rev()
            elif resp == ord(_('o')):
                revertopts['rev'] = self.repo[None].p2().rev()
            else:
                return
            dlg = None
        else:
            # rev options needs extra tweaking since it must be an empty
            # string when unspecified for revert command
            revertopts['rev'] = ''
            dlg = gdialog.Confirm(_('Confirm Revert'), files, self,
                    _('Revert the following files?'))
        if not dlg or dlg.run() == gtk.RESPONSE_YES:
            success, outtext = self._hg_call_wrapper('Revert', dohgrevert)
            if success:
                shlib.shell_notify(wfiles)
                self.reload_status()

    def add_clicked(self, toolbutton, data=None):
        add_list = self.relevant_files('?I')
        if len(add_list) > 0:
            self.hg_add(add_list)
        else:
            gdialog.Prompt(_('Nothing Added'),
                   _('No addable files selected'), self).run()
        return True


    def add_file(self, stat, wfile):
        self.hg_add([wfile])
        return True


    def hg_add(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        # Create new opts, so nothing unintented gets through
        addopts = self.merge_opts(commands.table['^add'][1],
                                  ('include', 'exclude'))
        def dohgadd():
            commands.add(self.ui, self.repo, *wfiles, **addopts)
        success, outtext = self._hg_call_wrapper('Add', dohgadd)
        if success:
            shlib.shell_notify(wfiles)
            self.reload_status()

    def remove_clicked(self, toolbutton, data=None):
        remove_list = self.relevant_files('C!')
        delete_list = self.relevant_files('?I')
        if len(remove_list) > 0:
            self.hg_remove(remove_list)
        if len(delete_list) > 0:
            self.delete_files(delete_list)
        if not remove_list and not delete_list:
            gdialog.Prompt(_('Nothing Removed'),
                   _('No removable files selected'), self).run()
        return True

    def move_clicked(self, toolbutton, data=None):
        move_list = self.relevant_files('C')
        if move_list:
            # get destination directory to files into
            dlg = gtklib.NativeFolderSelectDialog(
                    title=_('Move files to directory...'),
                    initial=self.repo.root)
            destdir = dlg.run()
            if not destdir:
                return True

            # verify directory
            destroot = paths.find_root(destdir)
            if destroot != self.repo.root:
                gdialog.Prompt(_('Nothing Moved'),
                       _('Cannot move outside repo!'), self).run()
                return True

            # move the files to dest directory
            move_list.append(hglib.fromutf(destdir))
            self.hg_move(move_list)
        else:
            gdialog.Prompt(_('Nothing Moved'), _('No movable files selected\n\n'
                    'Note: only clean files can be moved.'), self).run()
        return True

    def delete_file(self, stat, wfile):
        self.delete_files([wfile])

    def delete_files(self, files):
        dlg = gdialog.Confirm(_('Confirm Delete Unrevisioned'), files, self,
                _('Delete the following unrevisioned files?'))
        if dlg.run() == gtk.RESPONSE_YES:
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

    def guess_rename(self, stat, wfile):
        dlg = guess.DetectRenameDialog()
        dlg.show_all()
        dlg.set_notify_func(self.ignoremask_updated)

    def ignore_file(self, stat, wfile):
        dlg = hgignore.HgIgnoreDialog(self.repo.root, util.pconvert(wfile))
        dlg.show_all()
        dlg.set_notify_func(self.ignoremask_updated)
        return True

    def ignoremask_updated(self):
        '''User has changed the ignore mask in hgignore dialog'''
        self.reload_status()

    def mark_resolved(self, stat, wfile):
        ms = merge_.mergestate(self.repo)
        ms.mark(util.pconvert(wfile), "r")
        self.reload_status()


    def unmark_resolved(self, stat, wfile):
        ms = merge_.mergestate(self.repo)
        ms.mark(util.pconvert(wfile), "u")
        self.reload_status()


    def do_resolve(self, stat, wfile):
        ms = merge_.mergestate(self.repo)
        wctx = self.repo[None]
        mctx = wctx.parents()[-1]
        ms.resolve(util.pconvert(wfile), wctx, mctx)
        self.reload_status()


    def sel_clicked(self, state):
        self.select_files(state)
        return True


    def select_files(self, state, ctype=None):
        for entry in self.filemodel:
            if ctype and not entry[FM_STATUS] in ctype:
                continue
            if entry[FM_CHECKED] != state:
                entry[FM_CHECKED] = state
                self.update_chunk_state(entry)
        self.update_check_count()


    def relevant_files(self, stats):
        return [item[FM_PATH] for item in self.filemodel \
                if item[FM_CHECKED] and item[FM_STATUS] in stats]


    def context_menu_act(self, menuitem, handler):
        selection = self.filetree.get_selection()
        assert(selection.count_selected_rows() == 1)

        model, tpaths = selection.get_selected_rows()
        path = tpaths[0]
        handler(model[path][FM_STATUS], model[path][FM_PATH])
        return True


    def tree_button_press(self, widget, event):
        # Set the flag to ignore the next activation when the
        # shift/control keys are pressed. This avoids activations with
        # multiple rows selected.
        if event.type == gtk.gdk._2BUTTON_PRESS and  \
          (event.state & (gtk.gdk.SHIFT_MASK | gtk.gdk.CONTROL_MASK)):
            self._ignore_next_act = True
        else:
            self._ignore_next_act = False
        return False


    def tree_button_release(self, widget, event):
        if event.button != 3:
            return False
        if not (event.state & (gtk.gdk.SHIFT_MASK | gtk.gdk.CONTROL_MASK)):
            self.tree_popup_menu(widget, event.button, event.time)
        return False

    def get_file_context_menu(self, rowdata):
        st = rowdata[FM_STATUS]
        ms = rowdata[FM_MERGE_STATUS]
        if ms:
            menu = self._menus['M' + ms]
        else:
            menu = self._menus[st]
        return menu

    def tree_popup_menu(self, widget, button=0, time=0):
        selection = self.filetree.get_selection()
        if selection.count_selected_rows() != 1:
            return False

        model, tpaths = selection.get_selected_rows()
        menu = self.get_file_context_menu(model[tpaths[0]])
        menu.popup(None, None, None, button, time)
        return True


    def tree_key_press(self, tree, event):
        if event.keyval == 32:
            def toggler(model, path, bufiter):
                model[path][FM_CHECKED] = not model[path][FM_CHECKED]
                self.update_chunk_state(model[path])

            selection = self.filetree.get_selection()
            selection.selected_foreach(toggler)
            self.update_check_count()
            return True
        return False


    def tree_row_act(self, tree, path, column):
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
        menu = self.get_file_context_menu(model[tpaths[0]])
        menu.get_children()[0].activate()
        return True

def run(ui, *pats, **opts):
    showclean = pats and True or False
    rev = opts.get('rev', [])
    cmdoptions = {
        'all':False, 'clean':showclean, 'ignored':False, 'modified':True,
        'added':True, 'removed':True, 'deleted':True, 'unknown':True,
        'exclude':[], 'include':[], 'debug':True, 'verbose':True, 'git':False,
        'rev':rev, 'check':True
    }
    return GStatus(ui, None, None, pats, cmdoptions)

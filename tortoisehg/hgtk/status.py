# status.py - status dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2008 Steve Borho <steve@borho.org>
# Copyright 2008 Emmanuel Rosa <goaway1000@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import cStringIO
import gtk
import gobject
import pango
import threading

from mercurial import cmdutil, util, commands, patch, mdiff
from mercurial import merge as merge_

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, shlib, paths, hgshelve

from tortoisehg.hgtk import dialog, gdialog, gtklib, guess, hgignore, statusbar

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
    # don't use splitlines, should split with only LF for the patch
    lines = hglib.tounicode(text).split(u'\n')
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
    # don't use splitlines, should split with only LF for the patch
    lines = hglib.tounicode(text).split(u'\n')
    for line in lines:
        hunk += gtklib.markup_escape_text(hglib.toutf(line[:512])) + '\n'
    return hunk

class GStatus(gdialog.GDialog):
    """GTK+ based dialog for displaying repository status

    Also provides related operations like add, delete, remove, revert, refresh,
    ignore, diff, and edit.

    The following methods are meant to be overridden by subclasses. At this
    point GCommit is really the only intended subclass.

        auto_check(self)
    """

    ### Following methods are meant to be overridden by subclasses ###

    def init(self):
        gdialog.GDialog.init(self)
        self.mode = 'status'
        self.ready = False
        self.filerowstart = {}
        self.filechunks = {}
        self.status_error = None
        self.preview_tab_name_label = None

    def auto_check(self):
        # Only auto-check files once, and only if a pattern was given.
        if self.pats and self.opts.get('check'):
            for entry in self.filemodel:
                if entry[FM_PATH] not in self.excludes:
                    entry[FM_CHECKED] = True
            self.update_check_count()
            self.opts['check'] = False

    def get_custom_menus(self):
        return []

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
        root = self.get_reponame()
        revs = self.opts.get('rev')
        name = self.pats and _('filtered status') or _('status')
        r = revs and ':'.join(revs) or ''
        return root + ' - ' + ' '.join([name, r])

    def get_icon(self):
        return 'menushowchanged.ico'

    def get_defsize(self):
        return self._setting_defsize


    def get_tbbuttons(self):
        tbuttons = []

        if self.count_revs() == 2:
            tbuttons += [
                    self.make_toolbutton(gtk.STOCK_SAVE_AS, _('Save As'),
                        self.save_clicked, tip=_('Save selected changes'))]
        else:
            tbuttons += [
                    self.make_toolbutton(gtk.STOCK_JUSTIFY_FILL, _('_Diff'),
                        self.diff_clicked, name='diff',
                        tip=_('Visual diff checked files')),
                    self.make_toolbutton(gtk.STOCK_MEDIA_REWIND, _('Re_vert'),
                        self.revert_clicked, name='revert',
                        tip=_('Revert checked files')),
                    self.make_toolbutton(gtk.STOCK_ADD, _('_Add'),
                        self.add_clicked, name='add',
                        tip=_('Add checked files')),
                    self.make_toolbutton(gtk.STOCK_JUMP_TO, _('Move'),
                        self.move_clicked, name='move',
                        tip=_('Move checked files to other directory')),
                    self.make_toolbutton(gtk.STOCK_DELETE, _('_Remove'),
                        self.remove_clicked, name='remove',
                        tip=_('Remove or delete checked files')),
                    self.make_toolbutton(gtk.STOCK_CLEAR, _('_Forget'),
                        self.forget_clicked, name='forget',
                        tip=_('Forget checked files on next commit')),
                    gtk.SeparatorToolItem(),
                    self.make_toolbutton(gtk.STOCK_REFRESH, _('Re_fresh'),
                        self.refresh_clicked,
                        tip=_('refresh')),
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

    def is_merge(self):
        return self.count_revs() < 2 and len(self.repo.parents()) == 2

    def get_body(self):
        is_merge = self.is_merge()

        # model stores the file list.
        fm = gtk.ListStore(bool, str, str, str, str, bool)
        fm.set_sort_func(1001, self.sort_by_stat)
        fm.set_default_sort_func(self.sort_by_stat)
        self.filemodel = fm

        self.filetree = gtk.TreeView(self.filemodel)
        self.filetree.connect('popup-menu', self.tree_popup_menu)
        self.filetree.connect('button-release-event', self.tree_button_release)
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

        # file selection checkboxes
        col0 = gtk.TreeViewColumn('', toggle_cell)
        col0.set_visible(not is_merge) # hide when merging
        col0.add_attribute(toggle_cell, 'active', FM_CHECKED)
        col0.add_attribute(toggle_cell, 'radio', FM_PARTIAL_SELECTED)
        col0.set_resizable(False)
        self.filetree.append_column(col0)
        self.selcb = self.add_header_checkbox(col0, self.sel_clicked)
        self.file_sel_column = col0

        col1 = gtk.TreeViewColumn(_('st'), stat_cell)
        col1.add_attribute(stat_cell, 'text', FM_STATUS)
        col1.set_cell_data_func(stat_cell, self.text_color)
        col1.set_sort_column_id(1001)
        col1.set_resizable(False)
        self.filetree.append_column(col1)

        # merge status column
        col = gtk.TreeViewColumn(_('ms'), stat_cell)
        col.set_visible(self.count_revs() <= 1)
        col.add_attribute(stat_cell, 'text', FM_MERGE_STATUS)
        col.set_sort_column_id(4)
        col.set_resizable(False)
        self.filetree.append_column(col)
        self.merge_state_column = col

        col2 = gtk.TreeViewColumn(_('path'), path_cell)
        col2.add_attribute(path_cell, 'text', FM_PATH_UTF8)
        col2.set_cell_data_func(path_cell, self.text_color)
        col2.set_sort_column_id(2)
        col2.set_resizable(True)
        self.filetree.append_column(col2)

        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(self.filetree)

        # Status Types expander
        # We don't assign an expander child. We instead monitor the
        # expanded property and do the hiding ourselves
        expander = gtk.Expander(_('View'))
        self.types_expander = expander
        expander.connect("notify::expanded", self.types_expander_expanded)
        exp_labelbox = gtk.HBox()
        exp_labelbox.pack_start(expander, False, False)
        exp_labelbox.pack_start(gtk.Label(), True, True)
        self.counter = gtk.Label('')
        exp_labelbox.pack_end(self.counter, False, False, 2)
        self.status_types = self.get_status_types()
        self.status_types.hide()
        expander_box = gtk.VBox()
        expander_box.pack_start(exp_labelbox)
        expander_box.pack_start(self.status_types)

        tvbox = gtk.VBox()
        tvbox.pack_start(scroller, True, True, 0)
        tvbox.pack_start(gtk.HSeparator(), False, False)
        tvbox.pack_start(expander_box, False, False)
        if self.pats:
            button = gtk.Button(_('Remove filter, show root'))
            button.connect('pressed', self.remove_filter)
            tvbox.pack_start( button, False, False, 2)

        tree_frame = gtk.Frame()
        tree_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        tree_frame.add(tvbox)

        diff_frame = gtk.Frame()
        diff_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)

        self.diff_notebook = gtk.Notebook()
        self.diff_notebook.set_tab_pos(gtk.POS_BOTTOM)
        self.diff_notebook_pages = {}

        self.difffont = pango.FontDescription(self.fontdiff)

        self.clipboard = None

        self.diff_text = gtk.TextView()
        self.diff_text.set_wrap_mode(gtk.WRAP_NONE)
        self.diff_text.set_editable(False)
        self.diff_text.modify_font(self.difffont)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(self.diff_text)
        self.append_page('text-diff', scroller, gtk.Label(_('Text Diff')))

        # use treeview to show selectable diff hunks
        self.clipboard = gtk.Clipboard()

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
        if getattr(difftree, 'enable-grid-lines', None) is not None:
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

        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(difftree)
        self.append_page('hunk-selection', scroller, gtk.Label(_('Hunk Selection')))

        # Add a page for commit preview
        self.preview_text = gtk.TextView()
        self.preview_text.set_wrap_mode(gtk.WRAP_NONE)
        self.preview_text.set_editable(False)
        self.preview_text.modify_font(self.difffont)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(self.preview_text)
        self.preview_tab_name_label = gtk.Label(self.get_preview_tab_name())
        self.append_page('commit-preview', scroller,
            self.preview_tab_name_label)

        diff_frame.add(self.diff_notebook)

        if self.diffbottom:
            self.diffpane = gtk.VPaned()
        else:
            self.diffpane = gtk.HPaned()

        self.diffpane.pack1(tree_frame, shrink=False)
        self.diffpane.pack2(diff_frame, shrink=False)
        self.filetree.set_headers_clickable(True)

        sel = self.filetree.get_selection()
        sel.set_mode(gtk.SELECTION_MULTIPLE)
        self.treeselid = sel.connect('changed', self.tree_sel_changed,
                difftree)

        self.diff_notebook.connect('switch-page', self.page_switched,
                                   sel, difftree)
        return self.diffpane

    def append_page(self, name, child, label):
        num = self.diff_notebook.append_page(child,  label)
        self.diff_notebook_pages[num] = name

    def page_switched(self, notebook, page, page_num, filesel, difftree):
        self.tree_sel_changed(filesel, difftree, page_num)

    def get_extras(self):
        self.stbar = statusbar.StatusBar()
        return self.stbar

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
        if self.count_revs() == 2:
            return
        sensitive = check_count and not self.is_merge()
        for cmd in ('diff', 'revert', 'add', 'remove', 'move', 'forget'):
            self.cmd_set_sensitive(cmd, sensitive)
        if self.diff_notebook.get_current_page() == 2:
            self.update_commit_preview()

    def prepare_display(self):
        val = self.repo.ui.config('tortoisehg', 'ciexclude', '')
        self.excludes = [i.strip() for i in val.split(',') if i.strip()]
        gtklib.idle_add_single_call(self.realize_status_settings)

    def refresh_complete(self):
        pass

    def get_preview_tab_name(self):
        if self.count_revs() == 2:
            res = _('Save Preview')
        elif self.mqmode:
            res = _('Patch Preview')
        elif self.mode == 'shelve':
            res = _('Shelf Preview')
        else:
            res = _('Commit Preview')
        return res

    ### End of overrides ###

    def set_preview_tab_name(self, name=None):
        if self.preview_tab_name_label == None:
            return
        if name == None:
            name = self.get_preview_tab_name()
        self.preview_tab_name_label.set_text(name)

    def types_expander_expanded(self, expander, dummy):
        if expander.get_expanded():
            self.status_types.show()
        else:
            self.status_types.hide()

    def get_status_types(self):
        # Tuple: (onmerge, ctype, translated label)
        allchecks = [(False, False, 'unknown',  _('?: unknown')),
                     (True,  False, 'modified', _('M: modified')),
                     (False, False, 'ignored',  _('I: ignored')),
                     (True,  False, 'added',    _('A: added')),
                     (False, False, 'clean',    _('C: clean')),
                     (True,  False, 'removed',  _('R: removed')),
                     (False, True,  'deleted',  _('!: deleted')) ]

        checks = []
        nomerge = (self.count_revs() <= 1)
        for onmerge, fixed, button, text in allchecks:
            if onmerge or nomerge:
                checks.append((fixed, button, text))

        table = gtk.Table(rows=2, columns=3)
        table.set_col_spacings(8)

        self._show_checks = {}
        row, col = 0, 0

        for fixed, name, labeltext in checks:
            button = gtk.CheckButton(labeltext)
            widget = button
            if fixed:
                widget = gtk.Label(labeltext)
            button.connect('toggled', self.show_toggle, name)
            self._show_checks[name] = button
            table.attach(widget, col, col+1, row, row+1)
            col += row
            row = not row

        hbox = gtk.HBox()
        hbox.pack_start(table, False, False)

        return hbox

    def realize_status_settings(self):
        if not self.types_expander.get_expanded():
            self.status_types.hide()
        self.diffpane.set_position(self.setting_pos)
        self.reload_status()

    def remove_filter(self, button):
        button.hide()
        self.pats = []
        for name, check in self._show_checks.iteritems():
            check.set_sensitive(True)
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
        files = [model[p][FM_PATH] for p in tpaths]
        self._do_diff(files, self.opts)

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

    def refresh_file_tree(self):
        """Clear out the existing ListStore model and reload it from the
        repository status.  Also recheck and reselect files that remain
        in the list.
        """

        is_merge = self.is_merge()
        self.file_sel_column.set_visible(not is_merge)
        self.merge_state_column.set_visible(self.count_revs() <= 1)

        selection = self.filetree.get_selection()
        if selection is None:
            return

        (modified, added, removed, deleted, unknown, ignored, clean) = self.status
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
        model = self.filemodel
        reselect = [model[path][FM_PATH] for path in tpaths]
        waschecked = {}
        for row in model:
            waschecked[row[FM_PATH]] = row[FM_CHECKED], row[FM_PARTIAL_SELECTED]

        # merge-state of files
        ms = merge_.mergestate(self.repo)

        # Load the new data into the tree's model
        self.filetree.hide()
        selection.handler_block(self.treeselid)
        self.filemodel.clear()

        types = [ct for ct in changetypes if self.opts.get(ct[1])]
        for stat, _, wfiles in types:
            for wfile in wfiles:
                mst = wfile in ms and ms[wfile].upper() or ""
                wfile = util.localpath(wfile)
                defcheck = stat in 'MAR' and wfile not in self.excludes
                ck, p = waschecked.get(wfile, (defcheck, False))
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
            self.diff_text.set_buffer(gtk.TextBuffer())
            self.preview_text.set_buffer(gtk.TextBuffer())
            if not is_merge:
                self.diffmodel.clear()

        self.filetree.show()
        if self.mode == 'commit':
            self.text.grab_focus()
        else:
            self.filetree.grab_focus()
        return True


    def reload_status(self):
        if not self.ready: return False

        def get_repo_status():
            if self.mqmode and self.mode != 'status':
                # when a patch is applied, show diffs to parent of top patch
                qtip = repo['.']
                n1 = qtip.parents()[0].node()
                n2 = None
            else:
                # node2 is None (the working dir) when 0 or 1 rev is specificed
                n1, n2 = cmdutil.revpair(repo, self.opts.get('rev'))

            self._node1, self._node2, = n1, n2
            self.status_error = None
            matcher = cmdutil.match(repo, self.pats, self.opts)
            unknown = self.test_opt('unknown') and not self.is_merge()
            clean = self.test_opt('clean') and not self.is_merge()
            ignored = self.test_opt('ignored') and not self.is_merge()
            try:
                status = repo.status(node1=n1, node2=n2, match=matcher,
                                     ignored=ignored,
                                     clean=clean,
                                     unknown=unknown)
                self.status = status
            except IOError, e:
                self.status_error = str(e)

        def status_wait(thread):
            if thread.isAlive():
                return True
            else:
                if self.status_error:
                    self.ready = True
                    self.update_check_count()
                    self.stbar.end()
                    self.stbar.set_status_text(self.status_error)
                    return False
                self.refresh_file_tree()
                self.update_check_count()
                self.refresh_complete()
                self.ready = True
                self.stbar.end()
                return False

        self.set_preview_tab_name()
        repo = self.repo
        hglib.invalidaterepo(repo)
        if hasattr(repo, 'mq'):
            self.mqmode = repo.mq.applied and repo['.'] == repo['qtip']
            self.set_title(self.get_title())

        self.ready = False
        self.stbar.begin()
        thread = threading.Thread(target=get_repo_status)
        thread.setDaemon(True)
        thread.start()
        gobject.timeout_add(50, status_wait, thread)
        return True

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

    def updated_codes(self):
        types = [('modified', 'M'),
                 ('added',    'A'),
                 ('removed',  'R'),
                 ('unknown',  '?'),
                 ('deleted',  '!'),
                 ('ignored',  'I'),
                 ('clean',    'C') ]
        codes = ''
        try:
            for name, code in types:
                if self.opts[name]:
                    codes += code
        except KeyError:
            pass
        self.types_expander.set_label(_("View '%s'") % codes)

    def show_toggle(self, check, toggletype):
        self.opts[toggletype] = check.get_active()
        self.reload_status()
        self.updated_codes()
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


    def rename_file(self, wfile):
        fdir, fname = os.path.split(wfile)
        newfile = dialog.entry_dialog(self, _('Rename file to:'), True, fname)
        if newfile and newfile != fname:
            self.hg_move([wfile, os.path.join(fdir, newfile)])
        return True


    def copy_file(self, wfile):
        wfile = self.repo.wjoin(wfile)
        fdir, fname = os.path.split(wfile)
        result = gtklib.NativeSaveFileDialogWrapper(title=_('Copy file to'),
                                                    initial=fdir,
                                                    filename=fname).run()
        if not result:
            return
        if result != wfile:
            self.hg_copy([wfile, result])
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

    def tree_sel_changed(self, selection, tree, page_num=None):
        'Selection changed in file tree'
        # page_num may be supplied, if called from switch-page event
        model, paths = selection.get_selected_rows()
        if not paths:
            return
        row = paths[0]

        # desensitize the text diff and hunk selection tabs
        # if a non-MAR file is selected
        status = model[row][FM_STATUS]
        enable = (status in 'MAR')
        self.enable_page('text-diff', enable)
        self.enable_page('hunk-selection', enable and not self.is_merge())

        if page_num is None:
            page_num = self.diff_notebook.get_current_page()

        pname = self.get_page_name(page_num)
        if pname == 'text-diff':
            buf = self.generate_text_diffs(row)
            self.diff_text.set_buffer(buf)
        elif pname == 'hunk-selection':
            self.update_hunk_model(row, tree)
        elif pname == 'commit-preview':
            self.update_hunk_model(row, tree)
            self.update_commit_preview()

    def get_page_name(self, num):
        try:
            return self.diff_notebook_pages[num]
        except KeyError:
            return ''

    def enable_page(self, name, enable):
        for pnum in self.diff_notebook_pages:
            pname = self.get_page_name(pnum)
            if pname == name:
                child = self.diff_notebook.get_nth_page(pnum)
                if child:
                    child.set_sensitive(enable)
                    lb = self.diff_notebook.get_tab_label(child)
                    lb.set_sensitive(enable)
                return

    def update_commit_preview(self):
        if self.is_merge():
            difftext = [_('===== Diff to first parent =====\n')]
            for s in patch.diff(self.repo, self._node1, self._node2,
                    opts=patch.diffopts(self.ui, self.opts)):
                difftext.extend(s.splitlines(True))
            pctxs = self.repo[None].parents()
            difftext.append(_('\n===== Diff to second parent =====\n'))
            for s in patch.diff(self.repo, pctxs[1].node(), None,
                    opts=patch.diffopts(self.ui, self.opts)):
                difftext.extend(s.splitlines(True))
        else:
            buf = cStringIO.StringIO()
            for row in self.filemodel:
                if not row[FM_CHECKED]:
                    continue
                wfile = row[FM_PATH]
                if wfile in self.filechunks:
                    chunks = self.filechunks[wfile]
                else:
                    chunks = self.read_file_chunks(wfile)
                    for c in chunks:
                        c.active = True
                    self.filechunks[wfile] = chunks
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        chunk.write(buf)
                    elif chunk.active:
                        chunk.write(buf)
            difftext = buf.getvalue().splitlines(True)
        self.preview_text.set_buffer(self.diff_highlight_buffer(difftext))

    def diff_highlight_buffer(self, difftext):
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
        return buf

    def generate_text_diffs(self, row):
        wfile = self.filemodel[row][FM_PATH]
        pfile = util.pconvert(wfile)
        difftext = []
        is_merge = self.is_merge()
        if is_merge:
            difftext = [_('===== Diff to first parent =====\n')]
        matcher = cmdutil.matchfiles(self.repo, [pfile])
        for s in patch.diff(self.repo, self._node1, self._node2,
                match=matcher, opts=patch.diffopts(self.ui, self.opts)):
            difftext.extend(s.splitlines(True))
        if is_merge:
            pctxs = self.repo[None].parents()
            difftext.append(_('\n===== Diff to second parent =====\n'))
            for s in patch.diff(self.repo, pctxs[1].node(), None,
                    match=matcher, opts=patch.diffopts(self.ui, self.opts)):
                difftext.extend(s.splitlines(True))
        return self.diff_highlight_buffer(difftext)


    def update_hunk_model(self, row, tree):
        # Read this file's diffs into hunk selection model
        wfile = self.filemodel[row][FM_PATH]
        self.filerowstart = {}
        self.diffmodel.clear()
        if not self.is_merge():
            self.append_diff_hunks(wfile)
            if len(self.diffmodel):
                tree.scroll_to_cell(0, use_align=True, row_align=0.0)

    def read_file_chunks(self, wfile):
        'Get diffs of working file, parse into (c)hunks'
        difftext = cStringIO.StringIO()
        ctx = self.repo[self._node1]
        try:
            pfile = util.pconvert(wfile)
            fctx = ctx.filectx(pfile)
        except hglib.LookupError:
            fctx = None
        if fctx and fctx.size() > hglib.getmaxdiffsize(self.repo.ui):
            # Fake patch that displays size warning
            lines = ['diff --git a/%s b/%s\n' % (wfile, wfile)]
            lines.append(_('File is larger than the specified max size.\n'))
            lines.append(_('Hunk selection is disabled for this file.\n'))
            lines.append('--- a/%s\n' % wfile)
            lines.append('+++ b/%s\n' % wfile)
            difftext.writelines(lines)
            difftext.seek(0)
        else:
            matcher = cmdutil.matchfiles(self.repo, [pfile])
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
        result = gtklib.NativeSaveFileDialogWrapper(title=_('Save patch to'),
                                                    initial=self.repo.root,
                                                    filename=filename).run()
        if not result:
            return

        buf = cStringIO.StringIO()
        dmodel = self.diffmodel
        for row in self.filemodel:
            if not row[FM_CHECKED]:
                continue
            wfile = row[FM_PATH]
            if wfile in self.filechunks:
                chunks = self.filechunks[wfile]
            else:
                chunks = self.read_file_chunks(wfile)
                for c in chunks:
                    c.active = True
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

    def diff_clicked(self, toolbutton, data=None):
        diff_list = self.relevant_checked_files('MAR!')
        if len(diff_list) > 0:
            self._do_diff(diff_list, self.opts)
        else:
            gdialog.Prompt(_('Nothing Diffed'),
                   _('No diffable files selected'), self).run()
        return True

    def revert_clicked(self, toolbutton, data=None):
        revert_list = self.relevant_checked_files('MAR!')
        if len(revert_list) > 0:
            self.hg_revert(revert_list)
        else:
            gdialog.Prompt(_('Nothing Reverted'),
                   _('No revertable files selected'), self).run()
        return True


    def hg_revert(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        if self.count_revs() > 1:
            gdialog.Prompt(_('Nothing Reverted'),
                   _('Revert not allowed when viewing revision range.'),
                   self).run()
            return

        # Create new opts,  so nothing unintented gets through.
        revertopts = self.merge_opts(commands.table['revert'][1],
                                     ('include', 'exclude', 'rev'))
        def dohgrevert():
            commands.revert(self.ui, self.repo, *wfiles, **revertopts)

        def filelist(files):
            text = '\n'.join(files[:5])
            if len(files) > 5:
                text += '  ...\n'
            return text

        if self.is_merge():
            res = gdialog.CustomPrompt(
                    _('Uncommited merge - please select a parent revision'),
                    _('Revert files to local or other parent?'),
                    self, (_('&Local'), _('&Other'), _('&Cancel')), 2).run()
            if res == 0:
                revertopts['rev'] = self.repo[None].p1().rev()
            elif res == 1:
                revertopts['rev'] = self.repo[None].p2().rev()
            else:
                return
            response = None
        else:
            # response: 0=Yes, 1=Yes,no backup, 2=Cancel
            revs = revertopts['rev']
            if revs and type(revs) == list:
                revertopts['rev'] = revs[0]
            else:
                revertopts['rev'] = str(self.repo['.'].rev())
            response = gdialog.CustomPrompt(_('Confirm Revert'),
                    _('Revert files to revision %s?\n\n%s') % (revertopts['rev'],
                    filelist(files)), self, (_('&Yes (backup changes)'),
                                             _('Yes (&discard changes)'),
                                             _('&Cancel')), 2, 2).run()
        if response in (None, 0, 1):
            if response == 1:
                revertopts['no_backup'] = True
            success, outtext = self._hg_call_wrapper('Revert', dohgrevert)
            if success:
                shlib.shell_notify(wfiles)
                self.reload_status()

    def hg_forget(self, files):
        wfiles = [self.repo.wjoin(x) for x in files]
        commands.forget(self.ui, self.repo, *wfiles)
        self.reload_status()

    def add_clicked(self, toolbutton, data=None):
        add_list = self.relevant_checked_files('?I')
        if len(add_list) > 0:
            self.hg_add(add_list)
        else:
            gdialog.Prompt(_('Nothing Added'),
                   _('No addable files selected'), self).run()
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
        remove_list = self.relevant_checked_files('C!')
        delete_list = self.relevant_checked_files('?I')
        if len(remove_list) > 0:
            self.hg_remove(remove_list)
        if len(delete_list) > 0:
            self.delete_files(delete_list)
        if not remove_list and not delete_list:
            gdialog.Prompt(_('Nothing Removed'),
                   _('No removable files selected'), self).run()
        return True

    def move_clicked(self, toolbutton, data=None):
        move_list = self.relevant_checked_files('C')
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

    def forget_clicked(self, toolbutton, data=None):
        forget_list = self.relevant_checked_files('CM')
        if len(forget_list) > 0:
            self.hg_forget(forget_list)
        else:
            gdialog.Prompt(_('Nothing Forgotten'),
                   _('No clean files selected'), self).run()

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

    def ignoremask_updated(self):
        '''User has changed the ignore mask in hgignore dialog'''
        self.reload_status()

    def relevant_checked_files(self, stats):
        return [item[FM_PATH] for item in self.filemodel \
                if item[FM_CHECKED] and item[FM_STATUS] in stats]

    def sel_clicked(self, state):
        'selection header checkbox clicked'
        for entry in self.filemodel:
            if entry[FM_CHECKED] != state:
                entry[FM_CHECKED] = state
                self.update_chunk_state(entry)
        self.update_check_count()

    def tree_button_release(self, treeview, event):
        if event.button != 3:
            return False
        self.tree_popup_menu(treeview)
        return True

    def tree_popup_menu(self, treeview):
        model, tpaths = treeview.get_selection().get_selected_rows()
        types = {'M':[], 'A':[], 'R':[], '!':[], 'I':[], '?':[], 'C':[],
                 'r':[], 'u':[]}
        all = []
        for p in tpaths:
            row = model[p]
            file = util.pconvert(row[FM_PATH])
            ms = row[FM_MERGE_STATUS]
            if ms == 'R':
                types['r'].append(file)
            elif ms == 'U':
                types['u'].append(file)
            else:
                types[row[FM_STATUS]].append(file)
            all.append(file)

        def make(label, handler, stats, enabled=True):
            files = []
            for t in stats:
                files.extend(types[t])
            if not files:
                return
            item = gtk.MenuItem(label, True)
            item.connect('activate', handler, files)
            item.set_border_width(1)
            item.set_sensitive(enabled)
            menu.append(item)
            return files

        def vdiff(menuitem, files):
            self._do_diff(files, self.opts)
        def viewmissing(menuitem, files):
            self._view_files(files, True)
        def edit(menuitem, files):
            self._view_files(files, False)
        def other(menuitem, files):
            self._view_files(files, True)
        def revert(menuitem, files):
            self.hg_revert(files)
        def remove(menuitem, files):
            self.hg_remove(files)
        def log(menuitem, files):
            from tortoisehg.hgtk import history
            dlg = history.run(self.ui, canonpats=files)
            dlg.display()
        def forget(menuitem, files):
            self.hg_forget(files)
        def add(menuitem, files):
            self.hg_add(files)
        def delete(menuitem, files):
            self.delete_files(files)
        def unmark(menuitem, files):
            ms = merge_.mergestate(self.repo)
            for wfile in files:
                ms.mark(wfile, "u")
            self.reload_status()
        def mark(menuitem, files):
            ms = merge_.mergestate(self.repo)
            for wfile in files:
                ms.mark(wfile, "r")
            self.reload_status()
        def resolve(stat, files):
            wctx = self.repo[None]
            mctx = wctx.parents()[-1]
            for wfile in files:
                ms = merge_.mergestate(self.repo)
                ms.resolve(wfile, wctx, mctx)
            self.reload_status()
        def resolve_with(stat, tool, files):
            if tool:
                oldmergeenv = os.environ.get('HGMERGE')
                os.environ['HGMERGE'] = tool
            resolve(stat, files)
            if tool:
                if oldmergeenv:
                    os.environ['HGMERGE'] = oldmergeenv
                else:
                    del os.environ['HGMERGE']
        def rename(menuitem, files):
            self.rename_file(files[0])
        def copy(menuitem, files):
            self.copy_file(files[0])
        def guess_rename(menuitem, files):
            dlg = guess.DetectRenameDialog()
            dlg.show_all()
            dlg.set_notify_func(self.ignoremask_updated)
        def ignore(menuitem, files):
            dlg = hgignore.HgIgnoreDialog(files[0])
            dlg.show_all()
            dlg.set_notify_func(self.ignoremask_updated)

        menu = gtklib.MenuItems()
        make(_('_Visual Diff'), vdiff, 'MAR!ru')
        make(_('Edit'), edit, 'MACI?ru')
        make(_('View missing'), viewmissing, 'R!')
        make(_('View other'), other, 'MAru', self.is_merge())
        menu.append_sep()
        make(_('_Revert'), revert, 'MAR!ru')
        menu.append_sep()
        make(_('L_og'), log, 'MARC!ru')
        menu.append_sep()
        make(_('_Forget'), forget, 'MARC!ru')
        make(_('_Add'), add, 'I?')
        make(_('_Guess Rename...'), guess_rename, '?')
        make(_('_Ignore'), ignore, '?')
        make(_('Remove versioned'), remove, 'C')
        make(_('_Delete unversioned'), delete, '?I')
        if len(all) == 1:
            menu.append_sep()
            make(_('_Copy...'), copy, 'MC')
            make(_('Rename...'), rename, 'MC')
        menu.append_sep()
        f = make(_('Restart Merge...'), resolve, 'u')
        make(_('Mark unresolved'), unmark, 'r')
        make(_('Mark resolved'), mark, 'u')
        if f:
            rmenu = gtk.Menu()
            for tool in hglib.mergetools(self.repo.ui):
                item = gtk.MenuItem(tool, True)
                item.connect('activate', resolve_with, tool, f)
                item.set_border_width(1)
                rmenu.append(item)
            item = gtk.MenuItem(_('Restart merge with'), True)
            item.set_submenu(rmenu)
            menu.append(item)

        for label, func, stats in self.get_custom_menus():
            make(label, func, stats)

        menu = menu.create_menu()
        if len(menu.get_children()) > 0:
            menu.show_all()
            menu.popup(None, None, None, 0, 0)
            return True


    def tree_key_press(self, tree, event):
        'Make spacebar toggle selected rows'
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
        'Activation (return) triggers visual diff of selected rows'
        # Ignore activations (like double click) on the first column
        if column.get_sort_column_id() == 0:
            return True

        model, tpaths = self.filetree.get_selection().get_selected_rows()
        files = [model[p][FM_PATH] for p in tpaths]
        self._do_diff(files, self.opts)
        return True

    def isuptodate(self):
        oldparents = self.repo.dirstate.parents()
        self.repo.dirstate.invalidate()
        if oldparents == self.repo.dirstate.parents():
            return True
        response = gdialog.CustomPrompt(_('not up to date'),
                    _('The parents have changed since the last refresh.\n'
                      'Continue anyway?'),
                    self, (_('&Yes'), _('&Refresh'), _('&Cancel')), 1, 2).run()
        if response == 0: # Yes
            return True
        if response == 1:
            self.reload_status()
        return False

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

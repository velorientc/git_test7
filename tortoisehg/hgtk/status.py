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
import threading

from mercurial import cmdutil, util, patch, error, hg
from mercurial import merge as merge_, filemerge

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths, hgshelve

from tortoisehg.hgtk import dialog, gdialog, gtklib, guess, hgignore, statusbar, statusact
from tortoisehg.hgtk import chunks

# file model row enumerations
FM_CHECKED = 0
FM_STATUS = 1
FM_PATH_UTF8 = 2
FM_PATH = 3
FM_MERGE_STATUS = 4
FM_PARTIAL_SELECTED = 5


class GStatus(gdialog.GWindow):
    """GTK+ based dialog for displaying repository status

    Also provides related operations like add, delete, remove, revert, refresh,
    ignore, diff, and edit.

    The following methods are meant to be overridden by subclasses. At this
    point GCommit is really the only intended subclass.

        auto_check(self)
    """

    ### Following methods are meant to be overridden by subclasses ###

    def init(self):
        gdialog.GWindow.init(self)
        self.mode = 'status'
        self.ready = False
        self.status = ([],) * 7
        self.status_error = None
        self.preview_tab_name_label = None
        self.subrepos = []
        self.colorstyle = self.repo.ui.config('tortoisehg', 'diffcolorstyle')
        self.act = statusact.statusact(self)

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
            for opt in self.opts:
                if opt in self._show_checks and self.opts[opt]:
                    self._show_checks[opt].set_active(True)
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
        settings = gdialog.GWindow.save_settings(self)
        settings['gstatus-hpane'] = self.diffpane.get_position()
        settings['gstatus-lastpos'] = self.setting_lastpos
        settings['gstatus-type-expander'] = self.types_expander.get_expanded()
        return settings


    def load_settings(self, settings):
        gdialog.GWindow.load_settings(self, settings)
        self.setting_pos = 270
        self.setting_lastpos = 64000
        self.setting_types_expanded = False
        try:
            self.setting_pos = settings['gstatus-hpane']
            self.setting_lastpos = settings['gstatus-lastpos']
            self.setting_types_expanded = settings['gstatus-type-expander']
        except KeyError:
            pass
        self.mqmode, repo = None, self.repo
        if hasattr(repo, 'mq') and repo.mq.applied and repo['.'] == repo['qtip']:
            self.mqmode = True

    def is_merge(self):
        try:
            numparents = len(self.repo.parents())
        except error.Abort, e:
            self.stbar.set_text(str(e) + _(', please refresh'))
            numparents = 1
        return self.count_revs() < 2 and numparents == 2


    def get_accelgroup(self):
        accelgroup = gtk.AccelGroup()
        mod = gtklib.get_thg_modifier()
        
        gtklib.add_accelerator(self.filetree, 'thg-diff', accelgroup, mod+'d')
        self.filetree.connect('thg-diff', self.thgdiff)
        self.connect('thg-refresh', self.thgrefresh)

        # set CTRL-c accelerator for copy-clipboard
        gtklib.add_accelerator(self.chunks.difftree(), 'copy-clipboard', accelgroup, mod+'c')

        def scroll_diff_notebook(widget, direction=gtk.SCROLL_PAGE_DOWN):
            page_num = self.diff_notebook.get_current_page()
            page = self.diff_notebook.get_nth_page(page_num)

            page.emit("scroll-child", direction, False)

        def toggle_filetree_selection(*arguments):
            self.sel_clicked(not self.selcb.get_active())

        def next_diff_notebook_page(*arguments):
            notebook = self.diff_notebook
            if notebook.get_current_page() >= len(notebook) - 1:
                notebook.set_current_page(0)
            else:
                notebook.next_page()
                
        def previous_diff_notebook_page(*arguments):
            notebook = self.diff_notebook
            if notebook.get_current_page() <= 0:
                notebook.set_current_page(len(notebook) - 1)
            else:
                notebook.prev_page()
                
        # signal, accelerator key, handler, (parameters)
        status_accelerators = [
            ('status-scroll-down', 'bracketright', scroll_diff_notebook,
             (gtk.SCROLL_PAGE_DOWN,)),
            ('status-scroll-up', 'bracketleft', scroll_diff_notebook,
             (gtk.SCROLL_PAGE_UP,)),
            ('status-next-file', 'period', gtklib.move_treeview_selection,
             (self.filetree, 1)),
            ('status-previous-file', 'comma', gtklib.move_treeview_selection,
             (self.filetree, -1)),
            ('status-select-all', 'u', toggle_filetree_selection, ()),
            ('status-next-page', 'p', next_diff_notebook_page, ()),
            ('status-previous-page', '<Shift>p',
             previous_diff_notebook_page, ()),
        ]
        
        for signal, accelerator, handler, parameters in status_accelerators:
            gtklib.add_accelerator(self, signal, accelgroup,
                                   mod + accelerator)
            self.connect(signal, handler, *parameters)

        return accelgroup
                
    def get_body(self):
        is_merge = self.is_merge()

        # model stores the file list.
        fm = gtk.ListStore(
              bool, # FM_CHECKED
              str,  # FM_STATUS
              str,  # FM_PATH_UTF8
              str,  # FM_PATH
              str,  # FM_MERGE_STATUS
              bool  # FM_PARTIAL_SELECTED
            )
        fm.set_sort_func(1001, self.sort_by_stat)
        fm.set_default_sort_func(self.sort_by_stat)
        self.filemodel = fm

        self.filetree = gtk.TreeView(self.filemodel)
        self.filetree.connect('popup-menu', self.tree_popup_menu)
        self.filetree.connect('button-press-event', self.tree_button_press)
        self.filetree.connect('button-release-event', self.tree_button_release)
        self.filetree.connect('row-activated', self.tree_row_act)
        self.filetree.connect('key-press-event', self.tree_key_press)
        self.filetree.set_reorderable(False)
        self.filetree.set_enable_search(True)
        self.filetree.set_search_equal_func(self.search_filelist)
        if hasattr(self.filetree, 'set_rubber_banding'):
            self.filetree.set_rubber_banding(True)
        self.filetree.modify_font(self.fonts['list'])
        self.filetree.set_headers_clickable(True)

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
        if self.setting_types_expanded:
            expander.set_expanded(True)
            self.status_types.show()
        else:
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

        self.difffont = self.fonts['diff']

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

        # create chunks object
        self.chunks = chunks.chunks(self)

        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(self.chunks.difftree())
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
        self.treeselid = sel.connect('changed', self.tree_sel_changed)

        self.diff_notebook.connect('switch-page', self.page_switched, sel)

        # add keyboard accelerators
        accelgroup = self.get_accelgroup()     
        self.add_accel_group(accelgroup)
        
        return self.diffpane

    def append_page(self, name, child, label):
        num = self.diff_notebook.append_page(child,  label)
        self.diff_notebook_pages[num] = name

    def page_switched(self, notebook, page, page_num, filesel):
        self.tree_sel_changed(filesel, page_num)

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
        allchecks = [(False, 'unknown',  _('?: unknown')),
                     (True,  'modified', _('M: modified')),
                     (False, 'ignored',  _('I: ignored')),
                     (True,  'added',    _('A: added')),
                     (False, 'clean',    _('C: clean')),
                     (True,  'removed',  _('R: removed')),
                     (False, 'deleted',  _('!: deleted')),
                     (True, 'subrepo',  _('S: subrepo'))]

        checks = []
        nomerge = (self.count_revs() <= 1)
        for onmerge, button, text in allchecks:
            if onmerge or nomerge:
                checks.append((button, text))

        table = gtk.Table(rows=2, columns=3)
        table.set_col_spacings(8)

        self._show_checks = {}
        row, col = 0, 0

        for name, labeltext in checks:
            button = gtk.CheckButton(labeltext)
            widget = button
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
        try:
            tab = self.ui.config('tortoisehg', 'statustab', '0')
            tab = int(tab)
            self.diff_notebook.set_current_page(tab)
        except (error.ConfigError, ValueError):
            pass
        self.reload_status()

    def remove_filter(self, button):
        button.hide()
        self.pats = []
        for name, check in self._show_checks.iteritems():
            check.set_sensitive(True)
        self.set_title(self.get_title())
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

        (M, A, R, D, U, I, C) = self.status
        changetypes = (('M', 'modified', M),
                       ('A', 'added', A),
                       ('R', 'removed', R),
                       ('!', 'deleted', D),
                       ('?', 'unknown', U),
                       ('I', 'ignored', I),
                       ('C', 'clean', C))

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
                lfile = util.localpath(wfile)
                defcheck = stat in 'MAR' and lfile not in self.excludes
                ck, p = waschecked.get(lfile, (defcheck, False))
                model.append([ck, stat, hglib.toutf(lfile), lfile, mst, p])

        if self.test_opt('subrepo') or self.is_merge():
            for sdir in self.subrepos:
                lfile = util.localpath(sdir)
                defcheck = lfile not in self.excludes
                ck, p = waschecked.get(lfile, (defcheck, False))
                model.append([ck, 'S', hglib.toutf(lfile), lfile, '', p])

        self.auto_check() # may check more files

        for row in model:
            if row[FM_PARTIAL_SELECTED]:
                # force refresh of partially selected files
                self.chunks.update_hunk_model(row[FM_PATH], row[FM_CHECKED])
                self.chunks.clear()
            else:
                # demand refresh of full or non selection
                self.chunks.del_file(row[FM_PATH])

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
                self.chunks.clear()

        self.filetree.show()
        if self.mode == 'commit':
            self.text.grab_focus()
        else:
            self.filetree.grab_focus()
        return True


    def reload_status(self):
        if not self.ready: return False

        def get_repo_status():
            # Create a new repo object
            repo = hg.repository(self.ui, path=self.repo.root)
            self.newrepo = repo
            self.subrepos = []

            try:
                if self.mqmode and self.mode != 'status':
                    # when a patch is applied, show diffs to parent of top patch
                    qtip = repo['.']
                    n1 = qtip.parents()[0].node()
                    n2 = None
                else:
                    # node2 is None (working dir) when 0 or 1 rev is specified
                    n1, n2 = cmdutil.revpair(repo, self.opts.get('rev'))
            except (util.Abort, error.RepoError), e:
                self.status_error = str(e)
                return

            self._node1, self._node2 = n1, n2
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
            except (OSError, IOError, util.Abort), e:
                self.status_error = str(e)

            if n2 is not None or self.mqmode:
                return

            wctx = repo[None]
            try:
                for s in wctx.substate:
                    if matcher(s) and wctx.sub(s).dirty():
                        self.subrepos.append(s)
            except (error.ConfigError, error.RepoError), e:
                self.status_error = str(e)
            except (OSError, IOError, util.Abort), e:
                self.status_error = str(e)

        def status_wait(thread):
            if thread.isAlive():
                return True
            else:
                if self.status_error:
                    self.ready = True
                    self.update_check_count()
                    self.stbar.end()
                    self.stbar.set_text(self.status_error)
                    return False
                self.repo = self.newrepo
                self.ui = self.repo.ui
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

    def nodes(self):
        return (self._node1, self._node2)

    def get_ctx(self):
        'Return current changectx or workingctx'
        if self._node2 == None and not self.mqmode:
            return self.repo[None]
        else:
            return self.repo[self._node1]

    def set_file_states(self, paths, state=True):
        for p in paths:
            self.filemodel[p][FM_CHECKED] = state
            self.update_chunk_state(self.filemodel[p])
        self.update_check_count()

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
        self.chunks.update_chunk_state(wfile, selected)

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
        order = 'MAR!?SIC'
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
            text_renderer.set_property('foreground', gtklib.DBLUE)
        elif stat == 'A':
            text_renderer.set_property('foreground', gtklib.DGREEN)
        elif stat == 'R':
            text_renderer.set_property('foreground', gtklib.DRED)
        elif stat == 'C':
            text_renderer.set_property('foreground', gtklib.NORMAL)
        elif stat == '!':
            text_renderer.set_property('foreground', gtklib.RED)
        elif stat == '?':
            text_renderer.set_property('foreground', gtklib.DORANGE)
        elif stat == 'I':
            text_renderer.set_property('foreground', gtklib.DGRAY)
        else:
            text_renderer.set_property('foreground', gtklib.NORMAL)


    def tree_sel_changed(self, selection, page_num=None):
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
            fmrow = self.filemodel[row]
            self.chunks.update_hunk_model(fmrow[FM_PATH], fmrow[FM_CHECKED])
            if not self.is_merge() and self.chunks.len():
                self.chunks.difftree().scroll_to_cell(0, use_align=True, row_align=0.0)
        elif pname == 'commit-preview':
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
            opts = patch.diffopts(self.ui, self.opts)
            opts.git = True
            wctx = self.repo[None]
            pctx1, pctx2 = wctx.parents()
            difftext = [_('===== Diff to first parent %d:%s =====\n') % (
                        pctx1.rev(), str(pctx1))]
            try:
                for s in patch.diff(self.repo, pctx1.node(), None, opts=opts):
                    difftext.extend(s.splitlines(True))
                difftext.append(_('\n===== Diff to second parent %d:%s =====\n') % (
                                pctx2.rev(), str(pctx2)))
                for s in patch.diff(self.repo, pctx2.node(), None, opts=opts):
                    difftext.extend(s.splitlines(True))
            except (IOError, error.RepoError, error.LookupError, util.Abort), e:
                self.stbar.set_text(str(e))
        else:
            buf = cStringIO.StringIO()
            for row in self.filemodel:
                if not row[FM_CHECKED]:
                    continue
                wfile = row[FM_PATH]
                chunks = self.chunks.get_chunks(wfile)
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        chunk.write(buf)
                    elif chunk.active:
                        chunk.write(buf)

            difftext = buf.getvalue().splitlines(True)
        self.preview_text.set_buffer(self.diff_highlight_buffer(difftext))

    def diff_highlight_buffer(self, difftext):
        buf = gtk.TextBuffer()
        if self.colorstyle == 'background':
            buf.create_tag('removed', paragraph_background=gtklib.PRED)
            buf.create_tag('added', paragraph_background=gtklib.PGREEN)
        elif self.colorstyle == 'none':
            buf.create_tag('removed')
            buf.create_tag('added')
        else:
            buf.create_tag('removed', foreground=gtklib.DRED)
            buf.create_tag('added', foreground=gtklib.DGREEN)
        buf.create_tag('position', foreground=gtklib.DORANGE)
        buf.create_tag('header', foreground=gtklib.DBLUE)

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
        lines = chunks.check_max_diff(self.get_ctx(), pfile)
        if lines:
            return self.diff_highlight_buffer(lines)
        matcher = cmdutil.matchfiles(self.repo, [pfile])
        opts = patch.diffopts(self.ui, self.opts)
        opts.git = True
        difftext = []
        if self.is_merge():
            wctx = self.repo[None]
            pctx1, pctx2 = wctx.parents()
            difftext = [_('===== Diff to first parent %d:%s =====\n') % (
                        pctx1.rev(), str(pctx1))]
            try:
                for s in patch.diff(self.repo, pctx1.node(), None,
                                    match=matcher, opts=opts):
                    difftext.extend(s.splitlines(True))
                difftext.append(_('\n===== Diff to second parent %d:%s =====\n') % (
                                pctx2.rev(), str(pctx2)))
                for s in patch.diff(self.repo, pctx2.node(), None,
                                    match=matcher, opts=opts):
                    difftext.extend(s.splitlines(True))
            except (IOError, error.RepoError, error.LookupError, util.Abort), e:
                self.stbar.set_text(str(e))
        else:
            try:
                for s in patch.diff(self.repo, self._node1, self._node2,
                        match=matcher, opts=opts):
                    difftext.extend(s.splitlines(True))
            except (IOError, error.RepoError, error.LookupError, util.Abort), e:
                self.stbar.set_text(str(e))
        return self.diff_highlight_buffer(difftext)

    def update_check_state(self, wfile, partial, newvalue):
        for fr in self.filemodel:
            if fr[FM_PATH] == wfile:
                if fr[FM_PARTIAL_SELECTED] != partial:
                    fr[FM_PARTIAL_SELECTED] = partial
                if fr[FM_CHECKED] != newvalue:
                    fr[FM_CHECKED] = newvalue
                    self.update_check_count()
                return

    def get_checked(self, wfile):
        for fr in self.filemodel:
            if fr[FM_PATH] == wfile:
                return fr[FM_CHECKED]
        return False

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
        files = []
        for row in self.filemodel:
            if not row[FM_CHECKED]:
                continue
            files.append(row[FM_PATH])

        self.chunks.save(files, result)

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
            self.act.hg_revert(revert_list)
        else:
            gdialog.Prompt(_('Nothing Reverted'),
                   _('No revertable files selected'), self).run()
        return True

    def add_clicked(self, toolbutton, data=None):
        add_list = self.relevant_checked_files('?IR')
        if len(add_list) > 0:
            self.act.hg_add(add_list)
        else:
            gdialog.Prompt(_('Nothing Added'),
                   _('No addable files selected'), self).run()
        return True

    def remove_clicked(self, toolbutton, data=None):
        remove_list = self.relevant_checked_files('C!')
        delete_list = self.relevant_checked_files('?I')
        if len(remove_list) > 0:
            self.act.hg_remove(remove_list)
        if len(delete_list) > 0:
            self.act.delete_files(delete_list)
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
            self.act.hg_move(move_list)
        else:
            gdialog.Prompt(_('Nothing Moved'), _('No movable files selected\n\n'
                    'Note: only clean files can be moved.'), self).run()
        return True

    def forget_clicked(self, toolbutton, data=None):
        forget_list = self.relevant_checked_files('CM')
        if len(forget_list) > 0:
            self.act.hg_forget(forget_list)
        else:
            gdialog.Prompt(_('Nothing Forgotten'),
                   _('No clean files selected'), self).run()

    def ignoremask_updated(self):
        '''User has changed the ignore mask in hgignore dialog'''
        self.opts['check'] = True
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

    def tree_button_press(self, treeview, event):
        '''Selection management for filetree right-click

        If the user right-clicks on a currently-selected item in the
        filetree, preserve their entire existing selection for the popup menu.

        http://www.daa.com.au/pipermail/pygtk/2005-June/010465.html
        '''
        if event.button != 3:
            return False

        clicked_row = treeview.get_path_at_pos(int(event.x),
                                               int(event.y))
        if not clicked_row:
            return False

        selection = treeview.get_selection()
        selected_rows = selection.get_selected_rows()[1]

        # If they didn't right-click on a currently selected row,
        # change the selection
        if clicked_row[0] not in selected_rows:
            selection.unselect_all()
            selection.select_path(clicked_row[0])

        return True

    def tree_button_release(self, treeview, event):
        if event.button != 3:
            return False
        self.tree_popup_menu(treeview)
        return True

    def tree_popup_menu(self, treeview):
        model, tpaths = treeview.get_selection().get_selected_rows()
        types = {'M':[], 'A':[], 'R':[], '!':[], 'I':[], '?':[], 'C':[],
                 'r':[], 'u':[], 'S':[]}
        all = []
        pathmap = {}
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
            pathmap[file] = p

        def make(label, func, stats, icon=None, sens=True, paths=False):
            files = []
            for t in stats:
                files.extend(types[t])
            if not files:
                return
            args = [files]
            if paths:
                p = [pathmap[f] for f in files]
                args.append(p)
            item = menu.append(label, func, icon, args=args, sensitive=sens)
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
            self.act.hg_revert(files)
        def remove(menuitem, files):
            self.act.hg_remove(files)
        def log(menuitem, files):
            from tortoisehg.hgtk import history
            dlg = history.run(self.ui, canonpats=files)
            dlg.display()
        def annotate(menuitem, files):
            from tortoisehg.hgtk import datamine
            dlg = datamine.run(self.ui, *files)
            dlg.display()
        def forget(menuitem, files, paths):
            self.act.hg_forget(files)
            self.set_file_states(paths, state=False)
        def add(menuitem, files, paths):
            self.act.hg_add(files)
            self.set_file_states(paths, state=True)
        def delete(menuitem, files):
            self.act.delete_files(files)
        def unmark(menuitem, files):
            ms = merge_.mergestate(self.repo)
            for wfile in files:
                ms.mark(wfile, "u")
            ms.commit()
            self.reload_status()
        def mark(menuitem, files):
            ms = merge_.mergestate(self.repo)
            for wfile in files:
                ms.mark(wfile, "r")
            ms.commit()
            self.reload_status()
        def resolve(stat, files):
            wctx = self.repo[None]
            mctx = wctx.parents()[-1]
            ms = merge_.mergestate(self.repo)
            for wfile in files:
                ms.resolve(wfile, wctx, mctx)
            ms.commit()
            self.reload_status()
        def resolve_with(stat, tool, files):
            if tool:
                exe = filemerge._findtool(self.repo.ui, tool)
                oldmergeenv = os.environ.get('HGMERGE')
                os.environ['HGMERGE'] = exe
            resolve(stat, files)
            if tool:
                if oldmergeenv:
                    os.environ['HGMERGE'] = oldmergeenv
                else:
                    del os.environ['HGMERGE']
        def rename(menuitem, files):
            self.act.rename_file(files[0])
        def copy(menuitem, files):
            self.act.copy_file(files[0])
        def guess_rename(menuitem, files):
            dlg = guess.DetectRenameDialog()
            dlg.show_all()
            dlg.set_notify_func(self.ignoremask_updated)
        def ignore(menuitem, files):
            dlg = hgignore.HgIgnoreDialog(files[0])
            dlg.show_all()
            dlg.set_notify_func(self.ignoremask_updated)

        menu = gtklib.MenuBuilder()
        make(_('_Visual Diff'), vdiff, 'MAR!ru', gtk.STOCK_JUSTIFY_FILL)
        make(_('Edit'), edit, 'MACI?ru', gtk.STOCK_EDIT)
        make(_('View missing'), viewmissing, 'R!')
        make(_('View other'), other, 'MAru', None, self.is_merge())
        menu.append_sep()
        make(_('_Revert'), revert, 'MAR!ru', gtk.STOCK_MEDIA_REWIND)
        make(_('_Add'), add, 'R', gtk.STOCK_ADD, paths=True)
        menu.append_sep()
        make(_('File History'), log, 'MARC!ru', 'menulog.ico')
        make(_('Annotate'), annotate, 'MARC!ru', 'menublame.ico')
        menu.append_sep()
        make(_('_Forget'), forget, 'MAC!ru', gtk.STOCK_CLEAR, paths=True)
        make(_('_Add'), add, 'I?', gtk.STOCK_ADD, paths=True)
        make(_('_Guess Rename...'), guess_rename, 'A?!', 'detect_rename.ico')
        make(_('_Ignore'), ignore, '?', 'ignore.ico')
        make(_('Remove versioned'), remove, 'C', 'menudelete.ico')
        make(_('_Delete unversioned'), delete, '?I', gtk.STOCK_DELETE)
        if len(all) == 1:
            menu.append_sep()
            make(_('_Copy...'), copy, 'MC', gtk.STOCK_COPY)
            make(_('Rename...'), rename, 'MC', 'general.ico')
        menu.append_sep()
        f = make(_('Restart Merge...'), resolve, 'u', 'menumerge.ico')
        make(_('Mark unresolved'), unmark, 'r', gtk.STOCK_NO)
        make(_('Mark resolved'), mark, 'u', gtk.STOCK_YES)
        if f:
            rmenu = gtk.Menu()
            for tool in hglib.mergetools(self.repo.ui):
                item = gtk.MenuItem(tool, True)
                item.connect('activate', resolve_with, tool, f)
                item.set_border_width(1)
                rmenu.append(item)
            menu.append_submenu(_('Restart merge with'), rmenu,
                                'menumerge.ico')

        for label, func, stats, icon in self.get_custom_menus():
            make(label, func, stats, icon)

        menu = menu.build()
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
    showclean = util.any(os.path.isfile(e) for e in pats)
    rev = opts.get('rev', [])
    cmdoptions = {
        'all':False, 'clean':showclean, 'ignored':False, 'modified':True,
        'added':True, 'removed':True, 'deleted':True, 'unknown':True,
        'exclude':[], 'include':[], 'debug':True, 'verbose':True, 'git':False,
        'rev':rev, 'check':True, 'subrepo':True
    }
    return GStatus(ui, None, None, pats, cmdoptions)

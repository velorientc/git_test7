# history.py - Changelog dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright 2008 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject
import pango
import StringIO

from mercurial import ui, hg, cmdutil, commands, extensions, util, match

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths

from tortoisehg.hgtk.logview.treeview import TreeView as LogTreeView

from tortoisehg.hgtk import gdialog, gtklib, hgcmd, logfilter, gorev
from tortoisehg.hgtk import backout, status, hgemail, tagadd, update, merge
from tortoisehg.hgtk import archive, changeset, thgconfig, thgmq, histdetails

def create_menu(label, callback):
    menuitem = gtk.MenuItem(label, True)
    menuitem.connect('activate', callback)
    menuitem.set_border_width(1)
    return menuitem

class GLog(gdialog.GDialog):
    'GTK+ based dialog for displaying repository logs'
    def init(self):
        self.filter = 'all'
        self.lastrevid = None
        self.currevid = None
        self.origtip = len(self.repo)
        self.ready = False
        self.filterbox = None
        self.details_model = None
        os.chdir(self.repo.root)

        # Load extension support for commands which need it
        extensions.loadall(self.ui)
        self.exs = [ name for name, module in extensions.extensions() ]

    def get_title(self):
        return _('%s log') % self.get_reponame()

    def get_icon(self):
        return 'menulog.ico'

    def get_default_setting(self):
        return 'tortoisehg.authorcolor'

    def parse_opts(self):
        # Disable quiet to get full log info
        self.ui.quiet = False

    def get_tbbuttons(self):
        tbar = [
                self.make_toolbutton(gtk.STOCK_REFRESH,
                    _('Re_fresh'),
                    self.refresh_clicked,
                    tip=_('Reload revision history')),
                gtk.SeparatorToolItem(),
               ]
        if not self.opts.get('from-synch'):
            self.synctb = self.make_toolbutton(gtk.STOCK_NETWORK,
                              _('Synchronize'),
                              self.synch_clicked,
                              tip=_('Launch synchronize tool'))
            tbar += [self.synctb, gtk.SeparatorToolItem()]
        if 'mq' in self.exs:
            self.mqtb = self.make_toolbutton(gtk.STOCK_DIRECTORY,
                            _('MQ'),
                            self.mq_clicked,
                            tip=_('Toggle MQ panel'),
                            toggle=True,
                            icon='menupatch.ico')
            tbar += [self.mqtb, gtk.SeparatorToolItem()]
        return tbar

    def get_menu_list(self):
        def refresh(menuitem, resettip):
            if resettip:
                self.origtip = len(self.repo)
            self.reload_log()
        def navigate(menuitem, revname):
            if revname:
                self.goto_rev(revname)
            elif self.gorev_dialog:
                self.gorev_dialog.show()
                self.gorev_dialog.present()
            else:
                self.show_goto_dialog()
        lb = self.get_live_branches()
        bmenus = []
        if len(lb) > 1 or (lb and lb[0] != 'default'):
            bmenus.append(('----', None, None, None, None))
            for name in lb[:10]:
                bmenus.append((name, False, navigate, [name], None))
            
        fnc = self.toggle_view_column
        return [(_('View'), [
            (_('Filter Bar'), True, self.toggle_show_filterbar, [],
                self.show_filterbar),
            ('----', None, None, None, None),
            (_('Choose Details...'), False, self.details_clicked, [], None),
            ('----', None, None, None, None),
            (_('Refresh'), False, refresh, [False], gtk.STOCK_REFRESH),
            (_('Reset Tip'), False, refresh, [True], gtk.STOCK_REMOVE),
            ('----', None, None, None, None),
            (_('Compact Graph'), True, self.toggle_compactgraph, [],
                self.compactgraph),
            (_('Color by Branch'), True, self.toggle_branchcolor, [],
                self.branch_color),
                ]),

            (_('Navigate'), [
                (_('Tip'), False, navigate, ['tip'], None),
                (_('Working Parent'), False, navigate, ['.'], None),
                ('----', None, None, None, None),
                (_('Revision...'), False, navigate, [None], None),
                ] + bmenus)
            ]

    def synch_clicked(self, toolbutton, data):
        def sync_closed(dialog):
            self.synctb.set_sensitive(True)

        def synch_callback(parents):
            self.repo.invalidate()
            newparents = [x.node() for x in self.repo.parents()]
            if len(self.repo) != self.origtip:
                if self.newbutton.get_active():
                    self.reload_log()
                else:
                    self.newbutton.set_active(True)
            elif not parents == newparents:
                self.refresh_model()

        from tortoisehg.hgtk import synch
        parents = [x.node() for x in self.repo.parents()]
        dlg = synch.SynchDialog([], False, True)
        dlg.set_notify_func(synch_callback, parents)
        dlg.connect('destroy', sync_closed)
        dlg.show_all()
        self.synctb.set_sensitive(False)

    def toggle_view_column(self, button, property):
        active = button.get_active()
        self.graphview.set_property(property, active)

    def toggle_branchcolor(self, button):
        active = button.get_active()
        if self.branch_color != active:
            self.graphview.set_property('branch-color', active)
            self.branch_color = active
            self.reload_log()

    def toggle_graphcol(self, button):
        active = button.get_active()
        if self.graphcol != active:
            self.graphcol = active
            self.reload_log()
            # TODO: this could be tricky
            #self.compactgraph_button.set_sensitive(self.graphcol)

    def toggle_compactgraph(self, button):
        active = button.get_active()
        if self.compactgraph != active:
            self.compactgraph = active
            self.reload_log()         

    def toggle_show_filterbar(self, button):
        self.show_filterbar = button.get_active()
        if self.filterbox is not None:
            self.filterbox.set_property('visible', self.show_filterbar)

    def more_clicked(self, button, data=None):
        self.graphview.next_revision_batch(self.limit)

    def load_all_clicked(self, button, data=None):
        self.graphview.load_all_revisions()
        self.loadnextbutton.set_sensitive(False)
        self.loadallbutton.set_sensitive(False)

    def selection_changed(self, graphview):
        'Graphview reports a new row selected'
        treeview = graphview.treeview
        (model, paths) = treeview.get_selection().get_selected_rows()
        if not paths:
            self.currevid = None
            return False
        self.currevid = graphview.get_revid_at_path(paths[0])
        self.ancestrybutton.set_sensitive(True)
        if self.currevid != self.lastrevid:
            self.lastrevid = self.currevid
            self.changeview.opts['rev'] = [str(self.currevid)]
            self.changeview.load_details(self.currevid)
        return False

    def revisions_loaded(self, graphview):
        'Graphview reports log generator has exited'
        if not graphview.graphdata:
            self.changeview._buffer.set_text('')
            self.changeview._filelist.clear()
        self.loadnextbutton.set_sensitive(False)
        self.loadallbutton.set_sensitive(False)

    def details_clicked(self, toolbutton, data=None):
        self.show_details_dialog()

    def show_details_dialog(self):

        def close(dialog, response_id):
            dialog.destroy()

        model = gtk.ListStore(
            gobject.TYPE_BOOLEAN, gobject.TYPE_STRING, gobject.TYPE_STRING)

        model.append([self.graphcol, _('Graph'), 'graphcol'])
        def column(col, default, text):
            prop = col + '-column-visible'
            vis = self.graphview.get_property(prop)
            model.append([vis, text, prop])
        column('rev', True, _('Revision Number'))
        column('id', False, _('Changeset ID'))
        column('branch', False, _('Branch Name'))
        column('date', False, _('Local Date'))
        column('utc', False, _('UTC Date'))
        column('age', True, _('Age'))
        column('tag', False, _('Tags'))

        self.details_model = model

        dlg = histdetails.LogDetailsDialog(model, self.apply_details)
        dlg.connect('response', close)
        dlg.show()

    def apply_details(self):
        if self.details_model:
            reload = False
            for show, uitext, property in self.details_model:
                if property == 'graphcol':
                    if self.graphcol != show:
                        self.graphcol = show
                        reload = True
                else:
                    self.graphview.set_property(property, show)
                    self.showcol[property] = show
            if reload:
                self.reload_log()

    def filter_entry_activated(self, entry, combo):
        'User pressed enter in the filter entry'
        opts = {}
        mode = combo.get_active()
        text = entry.get_text()
        if not text:
            return
        if mode == 0: # Rev Range
            try:
                opts['revs'] = cmdutil.revrange(self.repo, [text])
            except Exception, e:
                gdialog.Prompt(_('Invalid revision range'), str(e), self).run()
                return
        elif mode == 1: # File Patterns
            opts['pats'] = [w.strip() for w in text.split(',')]
        elif mode == 2: # Keywords
            opts['keyword'] = [w.strip() for w in text.split(',')]
        elif mode == 3: # Date
            try:
                # return of matchdate not used, just sanity checking
                util.matchdate(text)
                opts['date'] = text
            except (ValueError, util.Abort), e:
                gdialog.Prompt(_('Invalid date specification'),
                               str(e), self).run()
                return
        else:
            return
        self.custombutton.set_active(True)
        self.filter = 'custom'
        self.reload_log(**opts)

    def filter_selected(self, widget, type):
        if not widget.get_active():
            return
        if type == 'branch':
            self.select_branch(self.branchcombo)
        else:
            self.filter = type
            self.reload_log()

    def patch_selected(self, mqwidget, revid, patchname):
        if revid < 0:
            patchfile = os.path.join(self.repo.root, '.hg', 'patches', patchname)
            self.currevid = self.lastrevid = None
            self.changeview.load_patch_details(patchfile)
        else:
            self.currevid = revid
            if self.currevid != self.lastrevid:
                self.lastrevid = self.currevid
                self.changeview.opts['rev'] = [str(self.currevid)]
                self.changeview.load_details(self.currevid)

    def repo_invalidated(self, mqwidget):
        self.reload_log()

    def prepare_display(self):
        'Called at end of display() method'
        self.ready = True
        root = self.repo.root
        os.chdir(root)  # for paths relative to repo root

        self.origtip = self.opts['orig-tip'] or len(self.repo)
        self.graphview.set_property('branch-color', self.branch_color)

        # ignore file patterns that imply repo root
        if len(self.pats) == 1 and self.pats[0] in (root, root+os.sep, ''):
            self.pats = []

        opts = self.opts
        if opts['filehist']:
            self.custombutton.set_active(True)
            self.filter = 'custom'
            self.filtercombo.set_active(1)
            self.filterentry.set_text(opts['filehist'])
            opts['pats'] = [opts['filehist']]
        elif self.pats:
            self.custombutton.set_active(True)
            self.filter = 'custom'
            self.filtercombo.set_active(1)
            self.filterentry.set_text(', '.join(self.pats))
            opts['pats'] = self.pats
        self.reload_log(**opts)

        self.filterbox.set_property('visible', self.show_filterbar)
        self.filterbox.set_no_show_all(True)

        for col in ('rev', 'date', 'id', 'branch', 'utc', 'age', 'tag'):
            if col in self.showcol:
                self.graphview.set_property(col+'-column-visible',
                        self.showcol[col])

        # enable MQ panel
        self.enable_mqpanel()

    def get_graphlimit(self, suggestion):
        limit_opt = self.repo.ui.config('tortoisehg', 'graphlimit', '500')
        l = 0
        for limit in (suggestion, limit_opt):
            try:
                l = int(limit)
                if l > 0:
                    return l
            except (TypeError, ValueError):
                pass
        return l or 500

    def save_settings(self):
        settings = gdialog.GDialog.save_settings(self)
        settings['glog-vpane'] = self.vpaned.get_position()
        settings['glog-hpane'] = self.hpaned.get_position()
        settings['branch-color'] = self.graphview.get_property('branch-color')
        settings['show-filterbar'] = self.show_filterbar
        settings['graphcol'] = self.graphcol
        settings['compactgraph'] = self.compactgraph
        for col in ('rev', 'date', 'id', 'branch', 'utc', 'age', 'tag'):
            vis = self.graphview.get_property(col+'-column-visible')
            settings['glog-vis-'+col] = vis
        return settings

    def load_settings(self, settings):
        'Called at beginning of display() method'
        gdialog.GDialog.load_settings(self, settings)
        self.setting_vpos = settings.get('glog-vpane', -1)
        self.setting_hpos = settings.get('glog-hpane', -1)
        self.branch_color = settings.get('branch-color', False)
        self.show_filterbar = settings.get('show-filterbar', True)
        self.graphcol = settings.get('graphcol', True)
        self.compactgraph = settings.get('compactgraph', False)
        self.showcol = {}
        for col in ('rev', 'date', 'id', 'branch', 'utc', 'age', 'tag'):
            key = 'glog-vis-'+col
            if key in settings:
                self.showcol[col] = settings[key]

    def refresh_model(self):
        'Refresh data in the history model, without reloading graph'
        if self.graphview.model:
            self.graphview.model.refresh()

        # refresh MQ widget if exists
        if hasattr(self, 'mqwidget'):
            self.mqwidget.refresh()

    def reload_log(self, **kwopts):
        'Send refresh event to treeview object'
        opts = {'date': None, 'no_merges':False, 'only_merges':False,
                'keyword':[], 'branch':None, 'pats':[], 'filehist':None,
                'revrange':[], 'revlist':[], 'noheads':False,
                'branch-view':self.compactgraph, 'rev':[] }
        opts.update(kwopts)

        # handle strips, rebases, etc
        self.origtip = min(len(self.repo), self.origtip)
        opts['orig-tip'] = self.origtip

        self.loadnextbutton.set_sensitive(True)
        self.loadallbutton.set_sensitive(True)
        self.newbutton.set_sensitive(self.origtip != len(self.repo))
        self.ancestrybutton.set_sensitive(False)
        pats = opts.get('pats', [])
        self.changeview.pats = pats
        self.lastrevid = None

        def ftitle(filtername):
            t = self.get_title()
            if filtername is not None:
                t = t + ' - ' + filtername
            self.set_title(t)

        if self.filter == 'branch':
            branch = opts.get('branch', None)
            self.graphview.refresh(self.graphcol, branch, opts)
            ftitle(_('%s branch') % branch)
        elif self.filter == 'custom':
            npats = hglib.normpats(pats)
            if len(npats) == 1:
                kind, name = match._patsplit(npats[0], None)
                if kind == 'path' and not os.path.isdir(name):
                    ftitle(_('file history: ') + hglib.toutf(name))
                    opts['filehist'] = name
                    self.graphview.refresh(self.graphcol, [name], opts)
            if not opts.get('filehist'):
                ftitle(_('custom filter'))
                self.graphview.refresh(False, npats, opts)
        elif self.filter == 'all':
            ftitle(None)
            self.graphview.refresh(self.graphcol, None, opts)
        elif self.filter == 'new':
            ftitle(_('new revisions'))
            assert len(self.repo) > self.origtip
            opts['revrange'] = [len(self.repo)-1, self.origtip]
            self.graphview.refresh(self.graphcol, None, opts)
        elif self.filter == 'only_merges':
            ftitle(_('merges'))
            opts['only_merges'] = True
            self.graphview.refresh(False, [], opts)
        elif self.filter == 'ancestry':
            ftitle(_('revision ancestry'))
            range = [self.currevid, 0]
            opts['noheads'] = True
            opts['revrange'] = range
            self.graphview.refresh(self.graphcol, None, opts)
        elif self.filter == 'tagged':
            ftitle(_('tagged revisions'))
            tagged = []
            for t, r in self.repo.tagslist():
                hr = self.repo[r].rev()
                if hr not in tagged:
                    tagged.insert(0, hr)
            opts['revlist'] = tagged
            self.graphview.refresh(False, [], opts)
        elif self.filter == 'parents':
            ftitle(_('working parents'))
            repo_parents = [x.rev() for x in self.repo.parents()]
            opts['revlist'] = [str(x) for x in repo_parents]
            self.graphview.refresh(False, [], opts)
        elif self.filter == 'heads':
            ftitle(_('heads'))
            heads = [self.repo[x].rev() for x in self.repo.heads()]
            opts['revlist'] = [str(x) for x in heads]
            self.graphview.refresh(False, [], opts)

        # refresh MQ widget if exists
        if hasattr(self, 'mqwidget'):
            self.mqwidget.refresh()

    def tree_context_menu(self):
        m = gtk.Menu()
        m.append(create_menu(_('visualize change'), self.vdiff_change))
        m.append(create_menu(_('di_splay change'), self.show_status))
        m.append(create_menu(_('diff to local'), self.vdiff_local))
        m.append(create_menu(_('_update'), self.checkout))
        self.cmenu_merge = create_menu(_('_merge with'), self.domerge)
        m.append(self.cmenu_merge)
        m.append(create_menu(_('_copy hash'), self.copy_hash))
        m.append(create_menu(_('_export patch'), self.export_patch))
        m.append(create_menu(_('e_mail patch'), self.email_patch))
        m.append(create_menu(_('_bundle rev:tip'), self.bundle_rev_to_tip))
        m.append(create_menu(_('add/remove _tag'), self.add_tag))
        self.cmenu_backout = create_menu(_('backout revision'),
                                         self.backout_rev)
        m.append(self.cmenu_backout)
        m.append(create_menu(_('_revert'), self.revert))
        m.append(create_menu(_('_archive'), self.archive))

        # need transplant extension for transplant command
        if 'transplant' in self.exs:
            m.append(create_menu(_('transp_lant to local'),
                     self.transplant_rev))
        
        # need mq extension for strip command
        if 'mq' in self.exs:
            m.append(create_menu(_('qimport'), self.qimport_rev))
            m.append(create_menu(_('strip revision'), self.strip_rev))

        m.show_all()
        return m

    def restore_original_selection(self, widget, *args):
        self.tree.get_selection().set_mode(gtk.SELECTION_SINGLE)
        self.tree.get_selection().select_path(self.origsel)

    def tree_diff_context_menu(self):
        m = gtk.Menu()
        m.append(create_menu(_('_diff with selected'), self.diff_revs))
        m.append(create_menu(_('visual diff with selected'),
                 self.vdiff_selected))
        m.append(create_menu(_('email from here to selected'),
                 self.email_revs))
        m.append(create_menu(_('bundle from here to selected'),
                 self.bundle_revs))
        m.append(create_menu(_('export patches from here to selected'),
                 self.export_revs))
        self.cmenu_merge2 = create_menu(_('_merge with'), self.domerge)
        m.append(self.cmenu_merge2)
        
        # need transplant extension for transplant command
        if 'transplant' in self.exs:
            m.append(create_menu(_('transplant revision range to local'),
                     self.transplant_revs))

        # need rebase extension for rebase command
        if 'rebase' in self.exs:
            m.append(create_menu(_('rebase on top of selected'),
                     self.rebase_selected))
        
        # need MQ extension for qimport command
        if 'mq' in self.exs:
            m.append(create_menu(_('qimport from here to selected'),
                     self.qimport_revs))
        m.connect_after('selection-done', self.restore_original_selection)
        m.show_all()
        return m

    def get_body(self):
        self.gorev_dialog = None
        self._menu = self.tree_context_menu()
        self._menu2 = self.tree_diff_context_menu()
        self.stbar = gtklib.StatusBar()
        self.limit = self.get_graphlimit(None)

        # Allocate TreeView instance to use internally
        if self.opts['limit']:
            firstlimit = self.get_graphlimit(self.opts['limit'])
            self.graphview = LogTreeView(self.repo, firstlimit, self.stbar)
        else:
            self.graphview = LogTreeView(self.repo, self.limit, self.stbar)

        # Allocate ChangeSet instance to use internally
        self.changeview = changeset.ChangeSet(self.ui, self.repo, self.cwd, [],
                self.opts, self.stbar)
        self.changeview.display(False)
        self.changeview.glog_parent = self

        # Add extra toolbar buttons
        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)
        self.loadnextbutton = self.make_toolbutton(gtk.STOCK_GO_DOWN,
            _('Load more'), self.more_clicked, tip=_('load more revisions'))
        self.loadallbutton = self.make_toolbutton(gtk.STOCK_GOTO_BOTTOM,
            _('Load all'), self.load_all_clicked, tip=_('load all revisions'))

        tbar = self.changeview.get_tbbuttons()
        tbar += [sep, self.loadnextbutton, self.loadallbutton]
        for tbutton in tbar:
            self.toolbar.insert(tbutton, -1)

        # PyGtk 2.6 and below did not automatically register types
        if gobject.pygtk_version < (2, 8, 0):
            gobject.type_register(LogTreeView)

        self.tree = self.graphview.treeview
        self.graphview.connect('revision-selected', self.selection_changed)
        self.graphview.connect('revisions-loaded', self.revisions_loaded)

        self.tree.connect('popup-menu', self.tree_popup_menu)
        self.tree.connect('button-press-event', self.tree_button_press)
        self.tree.connect('row-activated', self.tree_row_act)

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)
        mod = gtklib.get_thg_modifier()
        key, modifier = gtk.accelerator_parse(mod+'d')
        self.tree.add_accelerator('thg-diff', accelgroup, key,
                        modifier, gtk.ACCEL_VISIBLE)
        self.tree.connect('thg-diff', self.thgdiff)
        key, modifier = gtk.accelerator_parse(mod+'p')
        self.tree.add_accelerator('thg-parent', accelgroup, key,
                        modifier, gtk.ACCEL_VISIBLE)
        self.tree.connect('thg-parent', self.thgparent)
        self.connect('thg-refresh', self.thgrefresh)

        self.filterbox = gtk.HBox()
        filterbox = self.filterbox

        all = gtk.RadioButton(None, _('all'))
        all.set_active(True)
        all.connect('toggled', self.filter_selected, 'all')
        filterbox.pack_start(all, False)

        self.newbutton = gtk.RadioButton(all, _('new'))
        self.newbutton.connect('toggled', self.filter_selected, 'new')
        filterbox.pack_start(self.newbutton, False)

        tagged = gtk.RadioButton(all, _('tagged'))
        tagged.connect('toggled', self.filter_selected, 'tagged')
        filterbox.pack_start(tagged, False)

        ancestry = gtk.RadioButton(all, _('ancestry'))
        ancestry.connect('toggled', self.filter_selected, 'ancestry')
        filterbox.pack_start(ancestry, False)
        self.ancestrybutton = ancestry

        parents = gtk.RadioButton(all, _('parents'))
        parents.connect('toggled', self.filter_selected, 'parents')
        filterbox.pack_start(parents, False)

        heads = gtk.RadioButton(all, _('heads'))
        heads.connect('toggled', self.filter_selected, 'heads')
        filterbox.pack_start(heads, False)

        merges = gtk.RadioButton(all, _('merges'))
        merges.connect('toggled', self.filter_selected, 'only_merges')
        filterbox.pack_start(merges, False)

        branches = gtk.RadioButton(all, _('branch'))
        branches.connect('toggled', self.filter_selected, 'branch')
        branches.set_sensitive(False)
        self.branchbutton = branches
        filterbox.pack_start(branches, False)

        branchcombo = gtk.combo_box_new_text()
        for name in self.get_live_branches():
            branchcombo.append_text(name)
        branchcombo.connect('changed', self.select_branch)
        self.lastbranchrow = None
        filterbox.pack_start(branchcombo, False)
        self.branchcombo = branchcombo

        self.custombutton = gtk.RadioButton(all, _('custom'))
        self.custombutton.set_sensitive(False)
        filterbox.pack_start(self.custombutton, False)

        filtercombo = gtk.combo_box_new_text()
        for f in (_('Rev Range'), _('File Patterns'),
                  _('Keywords'), _('Date')):
            filtercombo.append_text(f)
        filtercombo.set_active(1)
        self.filtercombo = filtercombo
        filterbox.pack_start(filtercombo, False)

        entry = gtk.Entry()
        entry.connect('activate', self.filter_entry_activated, filtercombo)
        self.filterentry = entry
        filterbox.pack_start(entry, True)

        midpane = gtk.VBox()
        midpane.pack_start(filterbox, False, False, 0)
        midpane.pack_start(self.graphview, True, True, 0)
        midpane.show_all()

        if 'mq' in self.exs:
            # create MQWidget
            self.mqwidget = thgmq.MQWidget(self.repo, accelgroup, self.tooltips)
            self.mqwidget.connect('patch-selected', self.patch_selected)
            self.mqwidget.connect('repo-invalidated', self.repo_invalidated)

            def wrapframe(widget):
                frame = gtk.Frame()
                frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
                frame.add(widget)
                return frame
            self.mqpaned = gtk.HPaned()
            self.mqpaned.add1(wrapframe(self.mqwidget))
            self.mqpaned.add2(wrapframe(midpane))

            midpane = self.mqpaned

        # Add ChangeSet instance to bottom half of vpane
        self.changeview.graphview = self.graphview
        self.hpaned = self.changeview.get_body()

        self.vpaned = gtk.VPaned()
        self.vpaned.pack1(midpane, True, False)
        self.vpaned.pack2(self.hpaned)
        gobject.idle_add(self.realize_settings)

        vbox = gtk.VBox()
        vbox.pack_start(self.vpaned, True, True)

        # Append status bar
        vbox.pack_start(gtk.HSeparator(), False, False)
        vbox.pack_start(self.stbar, False, False)
        return vbox

    def realize_settings(self):
        self.vpaned.set_position(self.setting_vpos)
        self.hpaned.set_position(self.setting_hpos)

    def thgdiff(self, treeview):
        'ctrl-d handler'
        self.vdiff_change(None)

    def thgparent(self, treeview):
        'ctrl-p handler'
        parent = self.repo['.'].rev()
        self.graphview.set_revision_id(parent)

    def get_live_branches(self):
        live = []
        dblist = self.repo.ui.config('tortoisehg', 'deadbranch', '')
        deadbranches = [ x.strip() for x in dblist.split(',') ]
        for name in self.repo.branchtags().keys():
            if name not in deadbranches:
                live.append(name)
        return live

    def select_branch(self, combo):
        row = combo.get_active()
        if row >= 0 and row != self.lastbranchrow:
            self.filter = 'branch'
            self.lastbranchrow = row
            self.branchbutton.set_active(True)
            self.branchbutton.set_sensitive(True)
            self.reload_log(branch=combo.get_model()[row][0])
        else:
            self.lastbranchrow = None
            self.branchbutton.set_sensitive(False)

    def show_goto_dialog(self):
        'Launch a modeless goto revision dialog'
        def goto_rev_(rev):
            self.goto_rev(rev)

        def response_(dialog, response_id):
            dialog.hide()

        def delete_event(dialog, event, data=None):
            # return True to prevent the dialog from being destroyed
            return True

        dlg = gorev.GotoRevDialog(goto_rev_)
        dlg.connect('response', response_)
        dlg.connect('delete-event', delete_event)
        dlg.set_modal(False)
        dlg.show()

        self.gorev_dialog = dlg

    def goto_rev(self, revision):
        rid = self.repo[revision].rev()
        self.graphview.set_revision_id(rid, load=True)

    def strip_rev(self, menuitem):
        rev = self.currevid
        res = gdialog.Confirm(_('Confirm Strip Revision(s)'), [], self,
                _('Remove revision %d and all descendants?') % rev).run()
        if res != gtk.RESPONSE_YES:
            return
        cmdline = ['hg', 'strip', str(rev)]
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        self.repo.invalidate()
        self.reload_log()
        self.changeview._buffer.set_text('')
        self.changeview._filelist.clear()

    def backout_rev(self, menuitem):
        oldlen = len(self.repo)
        hash = str(self.repo[self.currevid])
        parents = [x.node() for x in self.repo.parents()]

        def refresh(*args):
            self.repo.invalidate()
            if len(self.repo) != oldlen:
                self.reload_log()

        dlg = backout.BackoutDialog(hash)
        dlg.set_transient_for(self)
        dlg.connect('destroy', refresh)
        dlg.show_all()
        dlg.present()
        dlg.set_transient_for(None)

    def revert(self, menuitem):
        rev = self.currevid
        res = gdialog.Confirm(_('Confirm Revert All Files'), [], self,
                _('Revert all files to revision %d?\nThis will overwrite your '
                  'local changes') % rev).run()
        if res != gtk.RESPONSE_YES:
            return
        cmdline = ['hg', 'revert', '--verbose', '--all', '--rev', str(rev)]
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()

    def vdiff_change(self, menuitem, pats=[]):
        self._do_diff(pats, {'change' : str(self.currevid)})

    def vdiff_local(self, menuitem, pats=[]):
        self._do_diff(pats, {'rev' : [str(self.currevid)]})

    def diff_revs(self, menuitem):
        rev0, rev1 = self.revrange
        statopts = self.merge_opts(commands.table['^status|st'][1],
                ('include', 'exclude', 'git'))
        statopts['rev'] = ['%u:%u' % (rev0, rev1)]
        statopts['modified'] = True
        statopts['added'] = True
        statopts['removed'] = True
        dialog = status.GStatus(self.ui, self.repo, self.cwd, self.pats,
                         statopts)
        dialog.display()
        return True

    def vdiff_selected(self, menuitem):
        strrevs = [str(r) for r in self.revrange]
        self._do_diff(self.pats, {'rev' : strrevs})

    def email_revs(self, menuitem):
        revrange = list(self.revrange)
        revrange.sort()
        opts = ['--rev', str(revrange[0]) + ':' + str(revrange[1])]
        dlg = hgemail.EmailDialog(self.repo.root, opts)
        dlg.set_transient_for(self)
        dlg.show_all()
        dlg.present()
        dlg.set_transient_for(None)

    def export_revs(self, menuitem):
        result = gtklib.NativeFolderSelectDialog(title=_('Save patches to'),
                                                 initial=self.repo.root).run()
        if result:
            revs = list(self.revrange)
            revs.sort()
            rev = '%d:%d' % (revs[0], revs[1])
            # In case new export args are added in the future, merge the
            # hg defaults
            opts= self.merge_opts(commands.table['^export'][1], ())
            opts['output'] = os.path.join(result, '%b_rev%R.patch')
            def dohgexport():
                commands.export(self.ui,self.repo, rev, **opts)
            s, o = self._hg_call_wrapper('Export', dohgexport, False)

    def bundle_revs(self, menuitem):
        revrange = list(self.revrange)
        revrange.sort()
        parent = self.repo[revrange[0]].parents()[0].rev()
        # Special case for revision 0's parent.
        if parent == -1: parent = 'null'

        filename = "%s_rev%d_to_rev%s.hg" % (os.path.basename(self.repo.root),
                   revrange[0], revrange[1])
        result = gtklib.NativeSaveFileDialogWrapper(Title=_('Write bundle to'),
                                         InitialDir=self.repo.root,
                                         FileName=filename).run()
        if result:
            cmdline = ['hg', 'bundle', '--base', str(parent),
                      '--rev', str(revrange[1]), result]
            dlg = hgcmd.CmdDialog(cmdline)
            dlg.show_all()
            dlg.run()
            dlg.hide()

    def qimport_rev(self, menuitem):
        """QImport selected revision."""
        rev = str(self.currevid)
        self.qimport_revs(menuitem, rev)

    def qimport_revs(self, menuitem, rev=None):
        """QImport revision range."""
        if rev == None:
            revs = list(self.revrange)
            revs.sort()
            rev = '%s:%s' % (str(revs[0]), str(revs[1]))
        cmdline = ['hg', 'qimport', '--rev', rev]
        dialog = hgcmd.CmdDialog(cmdline)
        dialog.show_all()
        dialog.run()
        dialog.hide()
        self.repo.invalidate()
        self.reload_log()
        self.changeview._buffer.set_text('')
        self.changeview._filelist.clear()
        self.enable_mqpanel()

    def rebase_selected(self, menuitem):
        """Rebase revision on top of selection (1st on top of 2nd).""" 
        revs = self.revrange
        res = gdialog.Confirm(_('Confirm Rebase Revision'), [], self,
            _('Rebase revision %d on top of %d?') % (revs[0], revs[1])).run()
        if res != gtk.RESPONSE_YES:
            return
        cmdline = ['hg', 'rebase', '--source', str(revs[0]),
                   '--dest', str(revs[1])]
        dialog = hgcmd.CmdDialog(cmdline)
        dialog.show_all()
        dialog.run()
        dialog.hide()
        self.repo.invalidate()
        self.reload_log()
        self.changeview._buffer.set_text('')
        self.changeview._filelist.clear()

    def transplant_revs(self, menuitem):
        """Transplant revision range on top of current revision."""
        revs = list(self.revrange)
        revs.sort()
        cmdline = ['hg', 'transplant', '%d:%d' % (revs[0], revs[1])]
        dialog = hgcmd.CmdDialog(cmdline)
        dialog.show_all()
        dialog.run()
        dialog.hide()
        self.repo.invalidate()
        self.reload_log()
        self.changeview._buffer.set_text('')
        self.changeview._filelist.clear()

    def add_tag(self, menuitem):
        # save tag info for detecting new tags added
        oldtags = self.repo.tagslist()
        oldlen = len(self.repo)
        rev = self.currevid

        def refresh(*args):
            self.repo.invalidate()
            if len(self.repo) != oldlen:
                self.reload_log()
            else:
                newtags = self.repo.tagslist()
                if newtags != oldtags:
                    self.refresh_model()

        dialog = tagadd.TagAddDialog(self.repo, rev=str(rev))
        dialog.set_transient_for(self)
        dialog.connect('destroy', refresh)
        dialog.show_all()
        dialog.present()
        dialog.set_transient_for(None)

    def show_status(self, menuitem):
        rev = self.currevid
        statopts = self.merge_opts(commands.table['^status|st'][1],
                ('include', 'exclude', 'git'))
        if self.changeview.parent_toggle.get_active():
            parent = self.repo[rev].parents()[1].rev()
        else:
            parent = self.repo[rev].parents()[0].rev()
        statopts['rev'] = [str(parent), str(rev)]
        statopts['modified'] = True
        statopts['added'] = True
        statopts['removed'] = True
        dialog = status.GStatus(self.ui, self.repo, self.cwd, self.pats,
                         statopts)
        dialog.display()

    def copy_hash(self, menuitem):
        hash = self.repo[self.currevid].hex()
        sel = (os.name == 'nt') and 'CLIPBOARD' or 'PRIMARY'
        clipboard = gtk.Clipboard(selection=sel)
        clipboard.set_text(hash)

    def export_patch(self, menuitem):
        rev = self.currevid
        filename = "%s_rev%s.patch" % (os.path.basename(self.repo.root), rev)
        result = gtklib.NativeSaveFileDialogWrapper(Title=_('Save patch to'),
                                             InitialDir=self.repo.root,
                                             FileName=filename).run()
        if result:
            if os.path.exists(result):
                res = gdialog.Confirm(_('Confirm Overwrite'), [], self,
                   _('The file "%s" already exists!\n\n'
                     'Do you want to overwrite it?') % result).run()
                if res != gtk.RESPONSE_YES:
                    return
                os.remove(result)

            # In case new export args are added in the future, merge the
            # hg defaults
            exportOpts= self.merge_opts(commands.table['^export'][1], ())
            exportOpts['output'] = result
            def dohgexport():
                commands.export(self.ui,self.repo,str(rev),**exportOpts)
            success, outtext = self._hg_call_wrapper("Export",dohgexport,False)

    def bundle_rev_to_tip(self, menuitem):
        try:
            rev = self.currevid
            parent = self.repo[rev].parents()[0].rev()
            # Special case for revision 0's parent.
            if parent == -1: parent = 'null'
        except (ValueError, hglib.LookupError):
            return
        filename = "%s_rev%d_to_tip.hg" % (os.path.basename(self.repo.root), rev)
        result = gtklib.NativeSaveFileDialogWrapper(Title=_('Write bundle to'),
                                         InitialDir=self.repo.root,
                                         FileName=filename).run()
        if result:
            if os.path.exists(result):
                res = gdialog.Confirm(_('Confirm Overwrite'), [], self,
                   _('The file "%s" already exists!\n\n'
                     'Do you want to overwrite it?') % result).run()
                if res != gtk.RESPONSE_YES:
                    return
                os.remove(result)
        
            cmdline = ['hg', 'bundle', '--base', str(parent), result]
            dlg = hgcmd.CmdDialog(cmdline)
            dlg.show_all()
            dlg.run()
            dlg.hide()

    def email_patch(self, menuitem):
        rev = self.currevid
        dlg = hgemail.EmailDialog(self.repo.root, ['--rev', str(rev)])
        dlg.set_transient_for(self)
        dlg.show_all()
        dlg.present()
        dlg.set_transient_for(None)

    def checkout(self, menuitem):
        rev = self.currevid
        parents = [x.node() for x in self.repo.parents()]
        dialog = update.UpdateDialog(rev)
        dialog.set_transient_for(self)
        dialog.show_all()
        dialog.set_notify_func(self.checkout_completed, parents)
        dialog.present()
        dialog.set_transient_for(None)

    def checkout_completed(self, oldparents):
        self.repo.invalidate()
        self.repo.dirstate.invalidate()
        newparents = [x.node() for x in self.repo.parents()]
        if not oldparents == newparents:
            self.refresh_model()

    def domerge(self, menuitem):
        rev = self.currevid
        parents = [x.node() for x in self.repo.parents()]
        if rev == self.repo.parents()[0].rev():
            rev = self.revrange[1]
        dialog = merge.MergeDialog(rev)
        dialog.set_transient_for(self)
        dialog.show_all()
        dialog.set_notify_func(self.merge_completed, parents, len(self.repo))
        dialog.present()
        dialog.set_transient_for(None)

    def merge_completed(self, args):
        self.repo.invalidate()
        self.repo.dirstate.invalidate()
        oldparents, repolen = args
        newparents = [x.node() for x in self.repo.parents()]
        if len(self.repo) != repolen:
            self.reload_log()
        elif not oldparents == newparents:
            self.refresh_model()

    def archive(self, menuitem):
        rev = self.currevid
        parents = [x.node() for x in self.repo.parents()]
        dialog = archive.ArchiveDialog(rev)
        dialog.set_transient_for(self)
        dialog.show_all()
        dialog.present()
        dialog.set_transient_for(None)

    def transplant_rev(self, menuitem):
        """Transplant selection on top of current revision."""
        rev = self.currevid
        cmdline = ['hg', 'transplant', str(rev)]
        dialog = hgcmd.CmdDialog(cmdline)
        dialog.show_all()
        dialog.run()
        dialog.hide()
        self.repo.invalidate()
        self.reload_log()
        self.changeview._buffer.set_text('')
        self.changeview._filelist.clear()

    def thgrefresh(self, window):
        self.reload_log()

    def refresh_clicked(self, toolbutton, data=None):
        self.reload_log()
        return True

    def enable_mqpanel(self, enable=None):
        if not hasattr(self, 'mqpaned'):
            return
        if enable == None:
            enable = self.mqwidget.has_patch()
        self.mqpaned.set_position(enable and 180 or 0)

        # set the state of MQ toolbutton
        if hasattr(self, 'mqtb'):
            self.mqtb.handler_block_by_func(self.mq_clicked)
            self.mqtb.set_active(enable)
            self.mqtb.handler_unblock_by_func(self.mq_clicked)

    def mq_clicked(self, toolbutton, data=None):
        self.enable_mqpanel(self.mqtb.get_active())

    def tree_button_press(self, tree, event):
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            path = tree.get_path_at_pos(int(event.x), int(event.y))
            if not path:
                return False
            crow = path[0]
            (model, pathlist) = tree.get_selection().get_selected_rows()
            if pathlist == []:
                return False
            srow = pathlist[0]
            if srow == crow:
                self.tree_popup_menu(tree, event.button, event.time)
            else:
                tree.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
                tree.get_selection().select_path(crow)
                self.origsel = srow
                rev0 = self.graphview.get_revid_at_path(srow)
                rev1 = self.graphview.get_revid_at_path(crow)
                self.revrange = (rev0, rev1)
                self.tree_popup_menu_diff(tree, event.button, event.time)
            return True
        return False

    def tree_popup_menu(self, treeview, button=0, time=0) :
        # disable/enable menus as required
        parents = [x.rev() for x in self.repo.parents()]
        can_merge = self.currevid not in parents and len(parents) < 2
        self.cmenu_merge.set_sensitive(can_merge)

        op1, op2 = self.repo.dirstate.parents()
        node = self.repo[self.currevid].node()
        a = self.repo.changelog.ancestor(op1, node)
        self.cmenu_backout.set_sensitive(a == node)

        # display the context menu
        self._menu.popup(None, None, None, button, time)
        return True

    def tree_popup_menu_diff(self, treeview, button=0, time=0):
        # disable/enable menus as required
        parents = [x.rev() for x in self.repo.parents()]
        can_merge = self.currevid in parents and len(parents) < 2
        self.cmenu_merge2.set_sensitive(can_merge)

        # display the context menu
        self._menu2.popup(None, None, None, button, time)
        return True

    def tree_row_act(self, tree, path, column) :
        'Default action is the first entry in the context menu'
        self._menu.get_children()[0].activate()
        return True

def run(ui, *pats, **opts):
    cmdoptions = {
        'follow':False, 'follow-first':False, 'copies':False, 'keyword':[],
        'limit':0, 'rev':[], 'removed':False, 'no_merges':False,
        'date':None, 'only_merges':None, 'prune':[], 'git':False,
        'verbose':False, 'include':[], 'exclude':[], 'from-synch':False,
        'orig-tip':None, 'filehist':None, 'canonpats':[]
    }
    cmdoptions.update(opts)
    pats = hglib.canonpaths(pats) + cmdoptions['canonpats']
    return GLog(ui, None, None, pats, cmdoptions)

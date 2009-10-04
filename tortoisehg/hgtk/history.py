# history.py - Changelog dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright 2008 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import sys
import gtk
import gobject
import Queue
import shutil
import tempfile
import atexit

from mercurial import ui, hg, cmdutil, commands, extensions, util, match, url

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, thread2

from tortoisehg.hgtk.logview.treeview import TreeView as LogTreeView

from tortoisehg.hgtk import gdialog, gtklib, hgcmd, gorev
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
        self.no_merges = False
        self.lastrevid = None
        self.currevid = None
        self.origtip = len(self.repo)
        self.ready = False
        self.filterbox = None
        self.details_model = None
        self.syncbox = None
        self.filteropts = None
        self.bundledir = None
        self.bfile = None
        self.npreviews = 0
        self.outgoing = []
        os.chdir(self.repo.root)

        # Load extension support for commands which need it
        extensions.loadall(self.ui)
        self.exs = [ name for name, module in extensions.extensions() ]

    def get_title(self):
        str = _('%s log') % self.get_reponame()
        if self.bfile:
            str += _(' (Bundle Preview)')
        return str

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
                self.make_toolbutton(gtk.STOCK_NETWORK,
                     _('Synchronize'),
                     self.synch_clicked,
                     tip=_('Launch synchronize tool')),
                gtk.SeparatorToolItem(),
               ]
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
        def refresh(menuitem, resetmarks):
            if resetmarks:
                self.outgoing = []
                self.graphview.set_outgoing([])
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
        def disable_maxdiff(menuitem):
            if menuitem.get_active():
                hglib._maxdiff = sys.maxint
            else:
                hglib._maxdiff = None
            self.reload_log()
        lb = self.get_live_branches()
        bmenus = []
        if len(lb) > 1 or (lb and lb[0] != 'default'):
            bmenus.append(('----', None, None, None, None))
            for name in lb[:10]:
                bmenus.append((hglib.toutf(name), False, navigate, [name], None))
            
        fnc = self.toggle_view_column
        if self.repo.ui.configbool('tortoisehg', 'disable-syncbar'):
            sync_bar_item = []
        else:
            sync_bar_item = [(_('Sync Bar'), True, self.toggle_show_syncbar,
                    [], self.show_syncbar)]

        return [(_('_View'), sync_bar_item + [
            (_('Filter Bar'), True, self.toggle_show_filterbar, [],
                self.show_filterbar),
            ('----', None, None, None, None),
            (_('Choose Details...'), False, self.details_clicked, [], None),
            ('----', None, None, None, None),
            (_('Refresh'), False, refresh, [False], gtk.STOCK_REFRESH),
            (_('Reset Marks'), False, refresh, [True], gtk.STOCK_REMOVE),
            ('----', None, None, None, None),
            (_('Compact Graph'), True, self.toggle_compactgraph, [],
                self.compactgraph),
            (_('Color by Branch'), True, self.toggle_branchcolor, [],
                self.branch_color),
            (_('Ignore Max Diff Size'), True, disable_maxdiff, [], False),
                ]),

            (_('_Navigate'), [
                (_('Tip'), False, navigate, ['tip'], None),
                (_('Working Parent'), False, navigate, ['.'], None),
                ('----', None, None, None, None),
                (_('Revision...'), False, navigate, [None], None),
                ] + bmenus)
            ]

    def synch_clicked(self, toolbutton, data):
        def sync_closed(dialog):
            self.get_toolbutton(_('Synchronize')).set_sensitive(True)

        def synch_callback(parents):
            self.repo.invalidate()
            newparents = [x.node() for x in self.repo.parents()]
            if parents != newparents:
                self.refresh_model()

        from tortoisehg.hgtk import synch
        parents = [x.node() for x in self.repo.parents()]
        dlg = synch.SynchDialog([], False)
        dlg.set_notify_func(synch_callback, parents)
        dlg.connect('destroy', sync_closed)
        dlg.show_all()
        self.get_toolbutton(_('Synchronize')).set_sensitive(False)

    def toggle_view_column(self, button, property):
        active = button.get_active()
        self.graphview.set_property(property, active)

    def toggle_branchcolor(self, button):
        active = button.get_active()
        if self.branch_color != active:
            self.graphview.set_property('branch-color', active)
            self.branch_color = active
            self.reload_log()

    def toggle_compactgraph(self, button):
        active = button.get_active()
        if self.compactgraph != active:
            self.compactgraph = active
            self.reload_log()         

    def toggle_show_filterbar(self, button):
        self.show_filterbar = button.get_active()
        if self.filterbox is not None:
            self.filterbox.set_property('visible', self.show_filterbar)

    def toggle_show_syncbar(self, button):
        self.show_syncbar = button.get_active()
        if self.syncbox is not None:
            self.syncbox.set_property('visible', self.show_syncbar)

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

        columns = {}
        columns['graph'] = (self.graphcol, _('Graph'), 'graphcol', 'graph')

        def column(col, text):
            prop = col + '-column-visible'
            vis = self.graphview.get_property(prop)
            columns[col] = (vis, text, prop, col)

        column('rev', _('Revision Number'))
        column('id', _('Changeset ID'))
        column('branch', _('Branch Name'))
        column('msg', _('Summary'))
        column('user', _('User'))
        column('date', _('Local Date'))
        column('utc', _('UTC Date'))
        column('age', _('Age'))
        column('tag', _('Tags'))

        model = gtk.ListStore(
            gobject.TYPE_BOOLEAN, 
            gobject.TYPE_STRING, 
            gobject.TYPE_STRING,
            gobject.TYPE_STRING)

        for c in self.graphview.get_columns():
            vis, text, prop, col = columns[c]
            model.append([vis, text, prop, col])

        self.details_model = model

        dlg = histdetails.LogDetailsDialog(model, self.apply_details)
        dlg.show()

    def apply_details(self):
        if self.details_model:
            columns = []
            for show, uitext, property, colname in self.details_model:
                columns.append(colname)
            self.graphview.set_columns(columns)
            self.column_order = ' '.join(columns)
            reload = False
            for show, uitext, property, colname in self.details_model:
                if property == 'graphcol':
                    if self.graphcol != show:
                        self.graphcol = show
                        reload = True
                        item = self.get_menuitem(_('Compact Graph'))
                        item.set_sensitive(self.graphcol)
                        item = self.get_menuitem(_('Color by Branch'))
                        item.set_sensitive(self.graphcol)
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
        elif mode == 4: # User
            opts['user'] = [w.strip() for w in text.split(',')]
        else:
            return
        self.custombutton.set_active(True)
        self.filter = 'custom'
        self.reload_log(**opts)

    def filter_selected(self, widget, type):
        if type == 'no_merges':
            self.no_merges = widget.get_active()
            self.reload_log()
            return

        if not widget.get_active():
            return

        if type == 'branch':
            self.select_branch(self.branchcombo)
            return

        self.filter = type
        self.filteropts = None
        self.reload_log()

    def update_hide_merges_button(self):
        compatible = self.filter in ['all', 'branch', 'custom']
        if not self.graphcol and compatible:
            self.hidemerges.set_sensitive(True)
        else:
            self.hidemerges.set_active(False)
            self.hidemerges.set_sensitive(False)
            self.no_merges = False

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

        self.origtip = len(self.repo)
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
        self.syncbox.set_property('visible', self.show_syncbar)
        self.syncbox.set_no_show_all(True)

        for col in ('rev', 'date', 'id', 'branch', 'utc', 'age', 'tag'):
            if col in self.showcol:
                self.graphview.set_property(col+'-column-visible',
                        self.showcol[col])
        try:
            self.graphview.set_columns(self.column_order.split())
        except KeyError:
            # ignore unknown column names, these could originate from garbeled
            # persisted data
            pass
        self.get_menuitem(_('Compact Graph')).set_sensitive(self.graphcol)
        self.get_menuitem(_('Color by Branch')).set_sensitive(self.graphcol)

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
        settings['show-syncbar'] = self.show_syncbar
        settings['graphcol'] = self.graphcol
        settings['compactgraph'] = self.compactgraph
        for col in ('rev', 'date', 'id', 'branch', 'utc', 'age', 'tag'):
            vis = self.graphview.get_property(col+'-column-visible')
            settings['glog-vis-'+col] = vis
        settings['filter-mode'] = self.filtercombo.get_active()
        settings['column-order'] = ' '.join(self.graphview.get_columns())
        return settings

    def load_settings(self, settings):
        'Called at beginning of display() method'
        gdialog.GDialog.load_settings(self, settings)
        self.setting_vpos = settings.get('glog-vpane', -1)
        self.setting_hpos = settings.get('glog-hpane', -1)
        self.branch_color = settings.get('branch-color', False)
        self.show_filterbar = settings.get('show-filterbar', True)
        self.show_syncbar = settings.get('show-syncbar', True)
        if self.repo.ui.configbool('tortoisehg', 'disable-syncbar'):
            self.show_syncbar = False
        self.graphcol = settings.get('graphcol', True)
        self.compactgraph = settings.get('compactgraph', False)
        self.showcol = {}
        for col in ('rev', 'date', 'id', 'branch', 'utc', 'age', 'tag'):
            key = 'glog-vis-'+col
            if key in settings:
                self.showcol[col] = settings[key]
        self.filter_mode = settings.get('filter-mode', 1)
        default_co = 'graph rev id branch msg user date utc age tag'
        self.column_order = settings.get('column-order', default_co)

    def refresh_model(self):
        'Refresh data in the history model, without reloading graph'
        if self.graphview.model:
            self.graphview.model.refresh()

        # refresh MQ widget if exists
        if hasattr(self, 'mqwidget'):
            self.mqwidget.refresh()

    def reload_log(self, **kwopts):
        'Send refresh event to treeview object'
        self.update_hide_merges_button()

        opts = {'date': None, 'no_merges':False, 'only_merges':False,
                'keyword':[], 'branch':None, 'pats':[], 'filehist':None,
                'revrange':[], 'revlist':[], 'noheads':False,
                'branch-view':False, 'rev':[], 'user':[]}
        if self.filteropts and not kwopts: opts = self.filteropts
        opts['branch-view'] = self.compactgraph
        opts.update(kwopts)

        # handle strips, rebases, etc
        self.origtip = min(len(self.repo), self.origtip)
        if not self.bfile:
            self.npreviews = 0
        
        opts['orig-tip'] = self.origtip
        opts['npreviews'] = self.npreviews

        opts['no_merges'] = self.no_merges

        self.loadnextbutton.set_sensitive(True)
        self.loadallbutton.set_sensitive(True)
        self.ancestrybutton.set_sensitive(False)
        pats = opts.get('pats', [])
        self.changeview.pats = pats
        self.lastrevid = None

        def ftitle(filtername):
            t = self.get_title()
            if filtername is not None:
                t = t + ' - ' + filtername
            self.set_title(t)

        if self.filter != 'custom':
            self.filterentry.set_text('')

        if self.filter == 'branch':
            branch = opts.get('branch', None)
            self.graphview.refresh(self.graphcol, None, opts)
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

        # Remember options to next time reload_log is called
        self.filteropts = opts

    def tree_context_menu(self):
        m = gtk.Menu()
        m.append(create_menu(_('visualize change'), self.vdiff_change))
        m.append(create_menu(_('di_splay change'), self.show_status))
        m.append(create_menu(_('diff to local'), self.vdiff_local))
        m.append(create_menu(_('_copy hash'), self.copy_hash))
        if self.bfile:
            if self.currevid >= len(self.repo) - self.npreviews:
                m.append(create_menu(_('pull to here'), self.pull_to))
            m.show_all()
            return m

        if self.repo[self.currevid].node() in self.outgoing:
            m.append(create_menu(_('push to here'), self.push_to))
        m.append(create_menu(_('_update'), self.checkout))
        cmenu_merge = create_menu(_('_merge with'), self.domerge)
        m.append(cmenu_merge)
        m.append(create_menu(_('_export patch'), self.export_patch))
        m.append(create_menu(_('e_mail patch'), self.email_patch))
        m.append(create_menu(_('_bundle rev:tip'), self.bundle_rev_to_tip))
        m.append(create_menu(_('add/remove _tag'), self.add_tag))
        cmenu_backout = create_menu(_('backout revision'), self.backout_rev)
        m.append(cmenu_backout)
        m.append(create_menu(_('_revert'), self.revert))
        m.append(create_menu(_('_archive'), self.archive))

        # disable/enable menus as required
        parents = [x.rev() for x in self.repo.parents()]
        can_merge = self.currevid not in parents and len(parents) < 2

        op1, op2 = self.repo.dirstate.parents()
        node = self.repo[self.currevid].node()
        a = self.repo.changelog.ancestor(op1, node)
        cmenu_backout.set_sensitive(a == node)
        cmenu_merge.set_sensitive(can_merge)

        # need transplant extension for transplant command
        if 'transplant' in self.exs:
            m.append(create_menu(_('transp_lant to local'),
                     self.transplant_rev))
        
        # need mq extension for strip command
        if 'mq' in self.exs:
            cmenu_qimport = create_menu(_('qimport'), self.qimport_rev)
            cmenu_strip = create_menu(_('strip revision'), self.strip_rev)

            try:
                ctx = self.repo[self.currevid]
                qbase = self.repo['qbase']
                actx = ctx.ancestor(qbase)
                if self.repo['qparent'] == ctx:
                    cmenu_qimport.set_sensitive(True)
                    cmenu_strip.set_sensitive(False)
                elif actx == qbase or actx == ctx:
                    # we're in the mq revision range or the mq
                    # is a descendant of us
                    cmenu_qimport.set_sensitive(False)
                    cmenu_strip.set_sensitive(False)
            except:
                pass

            m.append(cmenu_qimport)
            m.append(cmenu_strip)

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
        if self.bfile:
            m.connect_after('selection-done', self.restore_original_selection)
            m.show_all()
            return m

        m.append(create_menu(_('email from here to selected'),
                 self.email_revs))
        m.append(create_menu(_('bundle from here to selected'),
                 self.bundle_revs))
        m.append(create_menu(_('export patches from here to selected'),
                 self.export_revs))
        cmenu_merge = create_menu(_('_merge with'), self.domerge)
        m.append(cmenu_merge)
        
        # disable/enable menus as required
        parents = [x.rev() for x in self.repo.parents()]
        can_merge = self.currevid in parents and len(parents) < 2
        cmenu_merge.set_sensitive(can_merge)

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
        key, modifier = gtk.accelerator_parse(mod+'g')
        self.tree.add_accelerator('thg-revision', accelgroup, key,
                        modifier, gtk.ACCEL_VISIBLE)
        self.tree.connect('thg-revision', self.thgnavigate)
        self.connect('thg-refresh', self.thgrefresh)

        # synch bar
        self.syncbox = gtklib.SlimToolbar(self.tooltips)
        syncbox = self.syncbox

        incoming = syncbox.append_stock(gtk.STOCK_GO_DOWN,
                        _('Download and view incoming changesets'))
        pull = syncbox.append_stock(gtk.STOCK_GOTO_BOTTOM,
                        _('Pull incoming changesets'))
        outgoing = syncbox.append_stock(gtk.STOCK_GO_UP,
                        _('Determine and mark outgoing changesets'))
        push = syncbox.append_stock(gtk.STOCK_GOTO_TOP,
                        _('Push outgoing changesets'))
        email = syncbox.append_stock(gtk.STOCK_GOTO_LAST,
                        _('Email outgoing changesets'))
        conf = syncbox.append_stock(gtk.STOCK_PREFERENCES,
                        _('Configure aliases and after pull behavior'))
        stop = syncbox.append_stock(gtk.STOCK_STOP,
                        _('Stop current transaction'))
        stop.set_sensitive(False)

        ## target path combobox
        urllist = gtk.ListStore(str, str)
        urlcombo = gtk.ComboBoxEntry(urllist, 0)
        cell = gtk.CellRendererText()
        urlcombo.pack_end(cell, False)
        urlcombo.add_attribute(cell, 'text', 1)
        self.pathentry = urlcombo.get_child()
        syncbox.append_widget(urlcombo, expand=True)

        for alias, path in self.repo.ui.configitems('paths'):
            path = url.hidepassword(path)
            urllist.append([hglib.toutf(path), hglib.toutf(alias)])
            if alias == 'default':
                urlcombo.set_active(len(urllist)-1)

        outgoing.connect('clicked', self.outgoing_clicked, urlcombo, stop)
        push.connect('clicked', self.push_clicked, urlcombo)
        conf.connect('clicked', self.conf_clicked, urlcombo)
        email.connect('clicked', self.email_clicked, urlcombo)

        syncbox.append_widget(gtk.Label(_('After Pull:')))
        ppulldata = [('none', _('Nothing')), ('update', _('Update'))]
        ppull = self.repo.ui.config('tortoisehg', 'postpull', 'none')
        if 'fetch' in self.exs or 'fetch' == ppull:
            ppulldata.append(('fetch', _('Fetch')))
        if 'rebase' in self.exs or 'rebase' == ppull:
            ppulldata.append(('rebase', _('Rebase')))

        self.ppullcombo = gtk.combo_box_new_text()
        ppullcombo = self.ppullcombo
        for (index, (name, label)) in enumerate(ppulldata):
            ppullcombo.insert_text(index, label)

        for (index, (name, label)) in enumerate(ppulldata):
            if ppull == name:
                pos = index
                break;
        else:
            pos = [index for (index, (name, label))
                    in enumerate(ppulldata) if name == 'none'][0]
        ppullcombo.set_active(pos)

        incoming.connect('clicked', self.incoming_clicked, urlcombo,
                         ppullcombo, ppulldata)
        pull.connect('clicked', self.pull_clicked, urlcombo, ppullcombo,
                     ppulldata)
        syncbox.append_widget(ppullcombo)

        # filter bar
        self.filterbox = gtklib.SlimToolbar()
        filterbox = self.filterbox

        all = gtk.RadioButton(None, _('all'))
        all.set_active(True)
        all.connect('toggled', self.filter_selected, 'all')
        filterbox.append_widget(all, padding=0)

        tagged = gtk.RadioButton(all, _('tagged'))
        tagged.connect('toggled', self.filter_selected, 'tagged')
        filterbox.append_widget(tagged, padding=0)

        ancestry = gtk.RadioButton(all, _('ancestry'))
        ancestry.connect('toggled', self.filter_selected, 'ancestry')
        filterbox.append_widget(ancestry, padding=0)
        self.ancestrybutton = ancestry

        parents = gtk.RadioButton(all, _('parents'))
        parents.connect('toggled', self.filter_selected, 'parents')
        filterbox.append_widget(parents, padding=0)

        heads = gtk.RadioButton(all, _('heads'))
        heads.connect('toggled', self.filter_selected, 'heads')
        filterbox.append_widget(heads, padding=0)

        merges = gtk.RadioButton(all, _('merges'))
        merges.connect('toggled', self.filter_selected, 'only_merges')
        filterbox.append_widget(merges, padding=0)

        hidemerges = gtk.CheckButton(_('hide merges'))
        hidemerges.connect('toggled', self.filter_selected, 'no_merges')
        filterbox.append_widget(hidemerges, padding=0)
        self.hidemerges = hidemerges

        branches = gtk.RadioButton(all, _('branch'))
        branches.connect('toggled', self.filter_selected, 'branch')
        branches.set_sensitive(False)
        filterbox.append_widget(branches, padding=0)
        self.branchbutton = branches

        branchcombo = gtk.combo_box_new_text()
        for name in self.get_live_branches():
            branchcombo.append_text(hglib.toutf(name))
        branchcombo.connect('changed', self.select_branch)
        self.lastbranchrow = None
        filterbox.append_widget(branchcombo, padding=0)
        self.branchcombo = branchcombo

        self.custombutton = gtk.RadioButton(all, _('custom'))
        self.custombutton.set_sensitive(False)
        filterbox.append_widget(self.custombutton, padding=0)

        filtercombo = gtk.combo_box_new_text()
        filtercombo_entries = (_('Rev Range'), _('File Patterns'),
                  _('Keywords'), _('Date'), _('User'))
        for f in filtercombo_entries:
            filtercombo.append_text(f)
        if (self.filter_mode >= len(filtercombo_entries) or
                self.filter_mode < 0):
            self.filter_mode = 1
        filtercombo.set_active(self.filter_mode)
        self.filtercombo = filtercombo
        filterbox.append_widget(filtercombo, padding=0)

        entry = gtk.Entry()
        entry.connect('activate', self.filter_entry_activated, filtercombo)
        self.filterentry = entry
        filterbox.append_widget(entry, expand=True, padding=0)

        midpane = gtk.VBox()
        midpane.pack_start(syncbox, False)
        midpane.pack_start(filterbox, False)
        midpane.pack_start(self.graphview)
        midpane.show_all()

        # MQ widget
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

        return vbox

    def get_extras(self):
        return self.stbar

    def incoming_clicked(self, toolbutton, combo, ppullcombo, ppulldata):
        def apply_clicked(button, bfile):
            sel = ppullcombo.get_active_text()
            ppull = [name for (name, label) in ppulldata if sel == label][0]
            if ppull == 'fetch':
                cmd = ['fetch', '--message', 'merge']
                # load the fetch extension explicitly
                extensions.load(self.ui, 'fetch', None)
            else:
                cmd = ['pull']
                if ppull == 'update':
                    cmd.append('--update')
                elif ppull == 'rebase':
                    cmd.append('--rebase')
                    # load the rebase extension explicitly
                    extensions.load(self.ui, 'rebase', None)

            cmdline = ['hg'] + cmd + [bfile]
            dlg = hgcmd.CmdDialog(cmdline)
            dlg.show_all()
            dlg.run()
            dlg.hide()
            remove_overlay('--rebase' in cmd)

        def reject_clicked(button):
            remove_overlay(False)

        def remove_overlay(resettip):
            self.bfile = None
            self.npreviews = 0
            combo.get_child().set_text('')
            self.repo = hg.repository(self.ui, path=self.repo.root)
            self.graphview.set_repo(self.repo, self.stbar)
            self.changeview.repo = self.repo
            self.changeview.bfile = None
            if resettip:
                self.origtip = len(self.repo)
            self.reload_log()
            self.toolbar.remove(self.toolbar.get_nth_item(0))
            self.toolbar.remove(self.toolbar.get_nth_item(0))
            for w in disabled:
                w.set_sensitive(True)

        def cleanup():
            try:
                shutil.rmtree(self.bundledir)
            except IOError:
                pass

        if not self.bundledir:
            self.bundledir = tempfile.mkdtemp(prefix='thg-incoming-')
            atexit.register(cleanup)

        path = combo.get_child().get_text()
        bfile = path
        for badchar in (':', '*', '\\', '?', '#'):
            bfile = bfile.replace(badchar, '')
        bfile = bfile.replace('/', '_')
        bfile = os.path.join(self.bundledir, bfile) + '.hg'
        cmdline = ['hg', 'incoming', '--bundle', bfile, path]
        dlg = hgcmd.CmdDialog(cmdline, text='hg incoming')
        dlg.show_all()
        dlg.run()
        dlg.hide()
        if dlg.return_code() == 0 and os.path.isfile(bfile):
            combo.get_child().set_text(bfile)

            # create apply/reject toolbar buttons
            apply = gtk.ToolButton(gtk.STOCK_APPLY)
            apply.set_tooltip(self.tooltips,
                              _('Accept incoming previewed changesets'))
            apply.set_label(_('Accept'))
            apply.show()

            reject = gtk.ToolButton(gtk.STOCK_DIALOG_ERROR)
            reject.set_tooltip(self.tooltips,
                               _('Reject incoming previewed changesets'))
            reject.set_label(_('Reject'))
            reject.show()

            apply.connect('clicked', apply_clicked, bfile)
            reject.connect('clicked', reject_clicked)

            self.toolbar.insert(reject, 0)
            self.toolbar.insert(apply, 0)

            disabled = []
            for label in (_('Re_fresh'), _('Synchronize'), _('MQ')):
                tb = self.get_toolbutton(label)
                if tb:
                    tb.set_sensitive(False)
                    disabled.append(tb)
            self.syncbox.set_sensitive(False)
            disabled.append(self.syncbox)

            self.bfile = bfile
            oldtip = len(self.repo)
            self.repo = hg.repository(self.ui, path=bfile)
            self.graphview.set_repo(self.repo, self.stbar)
            self.changeview.repo = self.repo
            self.changeview.bfile = bfile
            self.npreviews = len(self.repo) - oldtip
            self.reload_log()

    def pull_clicked(self, toolbutton, combo, ppullcombo, ppulldata):
        sel = ppullcombo.get_active_text()
        ppull = [name for (name, label) in ppulldata if sel == label][0]
        if ppull == 'fetch':
            cmd = ['fetch', '--message', 'merge']
            # load the fetch extension explicitly
            extensions.load(self.ui, 'fetch', None)
        else:
            cmd = ['pull']
            if ppull == 'update':
                cmd.append('--update')
            elif ppull == 'rebase':
                cmd.append('--rebase')
                # load the rebase extension explicitly
                extensions.load(self.ui, 'rebase', None)

        cmdline = ['hg'] + cmd + [combo.get_child().get_text()]
        dlg = hgcmd.CmdDialog(cmdline, text=' '.join(['hg'] + cmd))
        dlg.show_all()
        dlg.run()
        dlg.hide()
        if dlg.return_code() == 0:
            self.repo.invalidate()
            if '--rebase' in cmd:
                self.origtip = len(self.repo)
                self.reload_log()
            elif len(self.repo) > self.origtip:
                self.reload_log()

    def outgoing_clicked(self, toolbutton, combo, stop):
        q = Queue.Queue()
        cmd = [q, 'outgoing', '--quiet', '--template', '{node}\n',
                combo.get_child().get_text()]

        def threadfunc(q, *args):
            try:
                hglib.hgcmd_toq(q, *args)
            except (util.Abort, hglib.RepoError), e:
                self.stbar.set_status_text(_('Abort: %s') % str(e))

        def out_wait():
            while q.qsize():
                hash = q.get(0).strip()
                try:
                    node = self.repo[hash].node()
                    outgoing.append(node)
                except:
                    pass
            if thread.isAlive():
                return True
            else:
                self.stbar.end()
                self.graphview.set_outgoing(outgoing)
                self.outgoing = outgoing
                self.reload_log()
                stop.disconnect(stop_handler)
                stop.set_sensitive(False)

        def stop_clicked(button):
            thread.terminate()

        outgoing = []
        thread = thread2.Thread(target=threadfunc, args=cmd)
        thread.start()
        self.stbar.begin()
        stop_handler = stop.connect('clicked', stop_clicked)
        stop.set_sensitive(True)
        gobject.timeout_add(50, out_wait)

    def email_clicked(self, toolbutton, combo):
        path = hglib.fromutf(combo.get_child().get_text()).strip()
        if not path:
            gdialog.Prompt(_('No repository selected'),
                           _('Select a peer repository to compare with'),
                           self).run()
            combo.get_child().grab_focus()
            return
        opts = ['--outgoing', path]
        dlg = hgemail.EmailDialog(self.repo.root, opts)
        self.show_dialog(dlg)

    def push_clicked(self, toolbutton, combo):
        entry = combo.get_child()
        remote_path = hglib.fromutf(entry.get_text()).strip()
        for alias, path in self.repo.ui.configitems('paths'):
            if remote_path == alias:
                remote_path = path
            elif remote_path == url.hidepassword(path):
                remote_path = path
        cmdline = ['hg', 'push', remote_path]
        dlg = hgcmd.CmdDialog(cmdline, text='hg push')
        dlg.show_all()
        dlg.run()
        dlg.hide()
        if dlg.return_code() == 0 and self.outgoing:
            self.outgoing = []
            self.graphview.set_outgoing([])
            self.reload_log()

    def conf_clicked(self, toolbutton, combo):
        newpath = hglib.fromutf(combo.get_child().get_text()).strip()
        for alias, path in self.repo.ui.configitems('paths'):
            if newpath in (path, url.hidepassword(path)):
                newpath = None
                break
        dlg = thgconfig.ConfigDialog(True)
        dlg.show_all()
        if newpath:
            dlg.new_path(newpath, 'default')
        else:
            dlg.focus_field('tortoisehg.postpull')
        dlg.run()
        dlg.hide()

        self.refreshui()
        urllist = combo.get_model()
        urllist.clear()
        for alias, path in self.repo.ui.configitems('paths'):
            path = url.hidepassword(path)
            urllist.append([hglib.toutf(path), hglib.toutf(alias)])
            if alias == 'default':
                combo.set_active(len(urllist)-1)

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

    def thgnavigate(self, treeview):
        'ctrl-g handler'
        self.show_goto_dialog()

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
        res = gdialog.Confirm(_('Confirm Strip Revisions'), [], self,
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

    def show_dialog(self, dlg):
        dlg.set_transient_for(self)
        dlg.show_all()
        dlg.present()
        if gtk.pygtk_version < (2, 12, 0):
            # Workaround for old PyGTK (< 2.12.0) issue.
            # See background of this: f668034aeda3
            dlg.set_transient_for(None)

    def backout_rev(self, menuitem):
        oldlen = len(self.repo)
        hash = str(self.repo[self.currevid])
        parents = [x.node() for x in self.repo.parents()]

        def cinotify(dlg):
            'User comitted the merge'
            dlg.ready = False
            dlg.hide()
            self.reload_log()

        def refresh(*args):
            self.repo.invalidate()
            if len(self.repo) != oldlen:
                self.reload_log()
            if len(self.repo.parents()) != len(parents):
                # User auto-merged the backout
                from tortoisehg.hgtk import commit
                dlg = commit.run(ui.ui())
                dlg.set_transient_for(self)
                dlg.set_modal(True)
                dlg.set_notify_func(cinotify, dlg)
                dlg.display()

        dlg = backout.BackoutDialog(hash)
        dlg.connect('destroy', refresh)
        self.show_dialog(dlg)

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
        opts = {'change':str(self.currevid), 'bundle':self.bfile}
        self._do_diff(pats, opts)

    def vdiff_local(self, menuitem, pats=[]):
        opts = {'rev':[str(self.currevid)], 'bundle':self.bfile}
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
        self.show_dialog(dlg)

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
        result = gtklib.NativeSaveFileDialogWrapper(title=_('Write bundle to'),
                                                    initial=self.repo.root,
                                                    filename=filename).run()
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
        dialog.connect('destroy', refresh)
        self.show_dialog(dialog)

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

    def push_to(self, menuitem):
        remote_path = hglib.fromutf(self.pathentry.get_text()).strip()
        for alias, path in self.repo.ui.configitems('paths'):
            if remote_path == alias:
                remote_path = path
            elif remote_path == url.hidepassword(path):
                remote_path = path
        node = self.repo[self.currevid].node()
        cmdline = ['hg', 'push', '--rev', str(self.currevid), remote_path]
        dlg = hgcmd.CmdDialog(cmdline, text='hg push')
        dlg.show_all()
        dlg.run()
        dlg.hide()
        if dlg.return_code() == 0 and self.outgoing:
            d = self.outgoing.index(node)
            self.outgoing = self.outgoing[d+1:]
            self.graphview.set_outgoing(self.outgoing)
            self.reload_log()

    def pull_to(self, menuitem):
        cmdline = ['hg', 'pull', '--rev', str(self.currevid), self.bfile]
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        curtip = len(hg.repository(self.ui, self.repo.root))
        self.repo = hg.repository(self.ui, path=self.bfile)
        self.graphview.set_repo(self.repo, self.stbar)
        self.changeview.repo = self.repo
        self.npreviews = len(self.repo) - curtip
        self.reload_log()

    def copy_hash(self, menuitem):
        hash = self.repo[self.currevid].hex()
        clipboard = gtk.Clipboard()
        clipboard.set_text(hash)

    def export_patch(self, menuitem):
        rev = self.currevid
        filename = "%s_rev%s.patch" % (os.path.basename(self.repo.root), rev)
        result = gtklib.NativeSaveFileDialogWrapper(title=_('Save patch to'),
                                                    initial=self.repo.root,
                                                    filename=filename).run()
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
        result = gtklib.NativeSaveFileDialogWrapper(title=_('Write bundle to'),
                                                    initial=self.repo.root,
                                                    filename=filename).run()
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
        self.show_dialog(dlg)

    def checkout(self, menuitem):
        rev = self.currevid
        parents = [x.node() for x in self.repo.parents()]
        dialog = update.UpdateDialog(rev)
        dialog.set_notify_func(self.checkout_completed, parents)
        self.show_dialog(dialog)

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
        dlg = merge.MergeDialog(rev)
        dlg.set_notify_func(self.merge_completed, parents, len(self.repo))
        self.show_dialog(dlg)

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
        dlg = archive.ArchiveDialog(rev)
        self.show_dialog(dlg)

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
        menu = self.tree_context_menu()
        menu.popup(None, None, None, button, time)
        return True

    def tree_popup_menu_diff(self, treeview, button=0, time=0):
        menu = self.tree_diff_context_menu()
        menu.popup(None, None, None, button, time)
        return True

    def tree_row_act(self, tree, path, column) :
        'Default action is the first entry in the context menu'
        self.tree_context_menu().get_children()[0].activate()
        return True

def run(ui, *pats, **opts):
    cmdoptions = {
        'follow':False, 'follow-first':False, 'copies':False, 'keyword':[],
        'limit':0, 'rev':[], 'removed':False, 'no_merges':False,
        'date':None, 'only_merges':None, 'prune':[], 'git':False,
        'verbose':False, 'include':[], 'exclude':[], 'filehist':None,
        'canonpats':[]
    }
    cmdoptions.update(opts)
    pats = hglib.canonpaths(pats) + cmdoptions['canonpats']
    return GLog(ui, None, None, pats, cmdoptions)

#
# history.py - Changelog dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import gtk
import gobject
import pango
import StringIO

from mercurial import ui, hg, commands, extensions, util

from thgutil.i18n import _
from thgutil import hglib, paths

from hggtk.logview import treemodel
from hggtk.logview.treeview import TreeView as LogTreeView

from hggtk import gdialog, gtklib, hgcmd, datamine, logfilter
from hggtk import backout, status, hgemail, tagadd, update, merge
from hggtk import changeset

def create_menu(label, callback):
    menuitem = gtk.MenuItem(label, True)
    menuitem.connect('activate', callback)
    menuitem.set_border_width(1)
    return menuitem

class GLog(gdialog.GDialog):
    'GTK+ based dialog for displaying repository logs'
    def init(self):
        self.last_rev = None
        self.filter = 'all'
        self.currow = None
        self.curfile = None

    def get_title(self):
        return hglib.toutf(os.path.basename(self.repo.root)) + ' log'

    def get_icon(self):
        return 'menulog.ico'

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
                self.make_toolbutton(gtk.STOCK_INDEX,
                    _('_Filter'),
                    self.filter_clicked,
                    menu=self.filter_menu(),
                    tip=_('Filter revisions for display')),
                gtk.SeparatorToolItem(),
                self.make_toolbutton(gtk.STOCK_FIND,
                    _('_DataMine'),
                    self.datamine_clicked,
                    tip=_('Search Repository History')),
                gtk.SeparatorToolItem()
             ] + self.changeview.get_tbbuttons()
        if not self.opts.get('from-synch'):
            self.synctb = self.make_toolbutton(gtk.STOCK_NETWORK,
                                 _('Synchronize'),
                                 self.synch_clicked,
                                 tip=_('Launch synchronize tool'))
            tbar += [gtk.SeparatorToolItem(), self.synctb]
        return tbar

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

        from hggtk import synch
        parents = [x.node() for x in self.repo.parents()]
        dlg = synch.SynchDialog([], False, True)
        dlg.set_notify_func(synch_callback, parents)
        dlg.connect('destroy', sync_closed)
        dlg.show_all()
        self.synctb.set_sensitive(False)

    def toggle_view_column(self, button, property):
        active = button.get_active()
        self.graphview.set_property(property, active)

    def more_clicked(self, button):
        self.graphview.next_revision_batch(self.limit)

    def load_all_clicked(self, button):
        self.graphview.load_all_revisions()
        self.nextbutton.set_sensitive(False)
        self.allbutton.set_sensitive(False)

    def revisions_loaded(self, graphview):
        'Treeview reports log generator has exited'
        if not self.graphview.graphdata:
            self.changeview._buffer.set_text('')
            self.changeview._filelist.clear()
            self.last_rev = None
        self.nextbutton.set_sensitive(False)
        self.allbutton.set_sensitive(False)

    def datamine_clicked(self, toolbutton, data=None):
        dlg = datamine.DataMineDialog(self.ui, self.repo, self.cwd, [], {})
        dlg.display()

    def filter_clicked(self, toolbutton, data=None):
        if self.filter_dialog:
            self.filter_dialog.show()
            self.filter_dialog.present()
        else:
            self.show_filter_dialog()

    def show_filter_dialog(self):
        'Launch a modeless filter dialog'
        def do_reload(opts):
            self.custombutton.set_active(True)
            self.reload_log(**opts)

        def close_filter_dialog(dialog, response_id):
            dialog.hide()

        def delete_event(dialog, event, data=None):
            # return True to prevent the dialog from being destroyed
            return True

        revs = []
        if self.currow is not None:
            revs.append(self.currow[treemodel.REVID])

        dlg = logfilter.FilterDialog(self.repo.root, revs, self.pats,
                filterfunc=do_reload)
        dlg.connect('response', close_filter_dialog)
        dlg.connect('delete-event', delete_event)
        dlg.set_modal(False)
        dlg.show()

        self.filter_dialog = dlg

    def filter_selected(self, widget, data=None):
        if widget.get_active():
            self.filter = data
            self.reload_log()

    def view_menu(self):
        menu = gtk.Menu()

        button = gtk.CheckMenuItem(_('Show Rev'))
        button.connect('toggled', self.toggle_view_column,
                'rev-column-visible')
        button.set_active(self.showcol.get('rev', True))
        button.set_draw_as_radio(True)
        menu.append(button)
        button = gtk.CheckMenuItem(_('Show ID'))
        button.connect('toggled', self.toggle_view_column,
                'id-column-visible')
        button.set_active(self.showcol.get('id', False))
        button.set_draw_as_radio(True)
        menu.append(button)
        button = gtk.CheckMenuItem(_('Show Local Date'))
        button.connect('toggled', self.toggle_view_column,
                'date-column-visible')
        button.set_active(self.showcol.get('date', True))
        button.set_draw_as_radio(True)
        menu.append(button)
        button = gtk.CheckMenuItem(_('Show UTC Date'))
        button.connect('toggled', self.toggle_view_column,
                'utc-column-visible')
        button.set_active(self.showcol.get('utc', False))
        button.set_draw_as_radio(True)
        menu.append(button)
        button = gtk.CheckMenuItem(_('Show Branch'))
        button.connect('toggled', self.toggle_view_column,
                'branch-column-visible')
        button.set_active(self.showcol.get('branch', False))
        button.set_draw_as_radio(True)
        menu.append(button)
        menu.show_all()
        return menu

    def filter_menu(self):
        menu = gtk.Menu()

        button = gtk.RadioMenuItem(None, _('Show All Revisions'))
        button.set_active(True)
        button.connect('toggled', self.filter_selected, 'all')
        menu.append(button)

        self.newbutton = gtk.RadioMenuItem(button, _('Show New Revisions'))
        self.newbutton.connect('toggled', self.filter_selected, 'new')
        menu.append(self.newbutton)

        button = gtk.RadioMenuItem(button, _('Show Tagged Revisions'))
        button.connect('toggled', self.filter_selected, 'tagged')
        menu.append(button)

        button = gtk.RadioMenuItem(button, _('Show Revision Ancestry'))
        button.connect('toggled', self.filter_selected, 'ancestry')
        menu.append(button)

        button = gtk.RadioMenuItem(button, _('Show Working Parents'))
        button.connect('toggled', self.filter_selected, 'parents')
        menu.append(button)

        button = gtk.RadioMenuItem(button, _('Show Head Revisions'))
        button.connect('toggled', self.filter_selected, 'heads')
        menu.append(button)

        button = gtk.RadioMenuItem(button, _('Show Only Merge Revisions'))
        button.connect('toggled', self.filter_selected, 'only_merges')
        menu.append(button)

        button = gtk.RadioMenuItem(button, _('Show Non-Merge Revisions'))
        button.connect('toggled', self.filter_selected, 'no_merges')
        menu.append(button)

        self.custombutton = gtk.RadioMenuItem(button, _('Custom Filter'))
        self.custombutton.set_sensitive(False)
        menu.append(self.custombutton)

        menu.show_all()
        return menu

    def open_with_file(self, file):
        'Call this before display() to open with file history'
        self.opts['filehist'] = file

    def prepare_display(self):
        'Called at end of display() method'
        self.opts['rev'] = [] # This option is dangerous - used directly by hg
        self.opts['revs'] = None
        os.chdir(self.repo.root)  # for paths relative to repo root

        origtip = len(self.repo)
        self.graphview.set_property('original-tip-revision', origtip)
        self.origtip = origtip

        if 'orig-tip' in self.opts:
            origtip = self.opts['orig-tip']
            if origtip != len(self.repo):
                self.origtip = origtip
                self.graphview.set_property('original-tip-revision', origtip)
                self.newbutton.set_active(True)
        elif 'filehist' in self.opts:
            self.custombutton.set_active(True)
            self.reload_log(pats = [self.opts['filehist']])
        elif 'revrange' in self.opts:
            self.custombutton.set_active(True)
            self.graphview.refresh(True, None, self.opts)
        elif self.pats == [self.repo.root] or self.pats == ['']:
            self.pats = []
            self.reload_log()
        elif self.pats:
            self.custombutton.set_active(True)
            self.reload_log(pats = self.pats)
        else:
            self.reload_log()

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
        for col in ('rev', 'date', 'id', 'branch', 'utc'):
            vis = self.graphview.get_property(col+'-column-visible')
            settings['glog-vis-'+col] = vis
        return settings

    def load_settings(self, settings):
        'Called at beginning of display() method'
        self.stbar = gtklib.StatusBar()
        self.limit = self.get_graphlimit(None)

        # Allocate TreeView instance to use internally
        if 'limit' in self.opts:
            firstlimit = self.get_graphlimit(self.opts['limit'])
            self.graphview = LogTreeView(self.repo, firstlimit, self.stbar)
        else:
            self.graphview = LogTreeView(self.repo, self.limit, self.stbar)

        # Allocate ChangeSet instance to use internally
        self.changeview = changeset.ChangeSet(self.ui, self.repo, self.cwd, [],
                self.opts, self.stbar)
        self.changeview.display(False)
        self.changeview.glog_parent = self

        gdialog.GDialog.load_settings(self, settings)
        self.setting_vpos = -1
        self.setting_hpos = -1
        self.showcol = {}
        try:
            self.setting_vpos = settings['glog-vpane']
            self.setting_hpos = settings['glog-hpane']
            for col in ('rev', 'date', 'id', 'branch', 'utc'):
                vis = settings['glog-vis-'+col]
                self.showcol[col] = vis
        except KeyError:
            pass

    def refresh_model(self):
        'Refresh data in the history model, without reloading graph'
        if self.graphview.model:
            self.graphview.model.refresh()

    def reload_log(self, **filteropts):
        'Send refresh event to treeview object'
        os.chdir(self.repo.root)  # for paths relative to repo root
        self.nextbutton.set_sensitive(True)
        self.allbutton.set_sensitive(True)
        self.newbutton.set_sensitive(self.origtip != len(self.repo))
        self.opts['rev'] = []
        self.opts['revs'] = None
        self.opts['no_merges'] = False
        self.opts['only_merges'] = False
        self.opts['revrange'] = filteropts.get('revrange', None)
        self.opts['date'] = filteropts.get('date', None)
        self.opts['keyword'] = filteropts.get('keyword', [])
        if filteropts:
            if 'revrange' in filteropts or 'branch' in filteropts:
                branch = filteropts.get('branch', None)
                self.graphview.refresh(True, branch, self.opts)
            else:
                self.pats = filteropts.get('pats', [])
                self.graphview.refresh(False, self.pats, self.opts)
        elif self.filter == 'all':
            self.graphview.refresh(True, None, self.opts)
        elif self.filter == 'new':
            self.opts['revrange'] = [len(self.repo)-1, self.origtip]
            self.graphview.refresh(True, None, self.opts)
        elif self.filter == 'only_merges':
            self.opts['only_merges'] = True
            self.graphview.refresh(False, [], self.opts)
        elif self.filter == 'no_merges':
            self.opts['no_merges'] = True
            self.graphview.refresh(False, [], self.opts)
        elif self.filter == 'ancestry':
            if not self.currow:
                return
            range = [self.currow[treemodel.REVID], 0]
            sopts = {'noheads': True, 'revrange': range}
            self.graphview.refresh(True, None, sopts)
        elif self.filter == 'tagged':
            tagged = []
            for t, r in self.repo.tagslist():
                hr = self.repo[r].rev()
                if hr not in tagged:
                    tagged.insert(0, hr)
            self.opts['revs'] = tagged
            self.graphview.refresh(False, [], self.opts)
        elif self.filter == 'parents':
            repo_parents = [x.rev() for x in self.repo.parents()]
            self.opts['revs'] = [str(x) for x in repo_parents]
            self.graphview.refresh(False, [], self.opts)
        elif self.filter == 'heads':
            heads = [self.repo[x].rev() for x in self.repo.heads()]
            self.opts['revs'] = [str(x) for x in heads]
            self.graphview.refresh(False, [], self.opts)

    def tree_context_menu(self):
        m = gtk.Menu()
        m.append(create_menu(_('visualize change'), self.vdiff_change))
        m.append(create_menu(_('di_splay change'), self.show_status))
        m.append(create_menu(_('diff to local'), self.vdiff_local))
        m.append(create_menu(_('_update'), self.checkout))
        self.cmenu_merge = create_menu(_('_merge with'), self.merge)
        m.append(self.cmenu_merge)
        m.append(create_menu(_('_copy hash'), self.copy_hash))
        m.append(create_menu(_('_export patch'), self.export_patch))
        m.append(create_menu(_('e_mail patch'), self.email_patch))
        m.append(create_menu(_('_bundle rev:tip'), self.bundle_rev_to_tip))
        m.append(create_menu(_('add/remove _tag'), self.add_tag))
        m.append(create_menu(_('backout revision'), self.backout_rev))
        m.append(create_menu(_('_revert'), self.revert))

        # need mq extension for strip command
        extensions.loadall(self.ui)
        extensions.load(self.ui, 'mq', None)
        m.append(create_menu(_('strip revision'), self.strip_rev))

        m.show_all()
        return m

    def restore_original_selection(self, widget, *args):
        self.tree.get_selection().set_mode(gtk.SELECTION_SINGLE)
        self.tree.get_selection().select_path(self.orig_sel)

    def tree_diff_context_menu(self):
        m = gtk.Menu()
        m.append(create_menu(_('_diff with selected'), self.diff_revs))
        m.append(create_menu(_('visual diff with selected'),
                 self.vdiff_selected))
        m.append(create_menu(_('email from here to selected'),
                 self.email_revs))
        m.append(create_menu(_('bundle from here to selected'),
                 self.bundle_revs))
        self.cmenu_merge2 = create_menu(_('_merge with'), self.merge)
        m.append(self.cmenu_merge2)
        m.connect_after('selection-done', self.restore_original_selection)
        m.show_all()
        return m

    def get_body(self):
        self.filter_dialog = None
        self._menu = self.tree_context_menu()
        self._menu2 = self.tree_diff_context_menu()

        treeframe = gtk.Frame()
        treeframe.set_shadow_type(gtk.SHADOW_ETCHED_IN)

        # PyGtk 2.6 and below did not automatically register types
        if gobject.pygtk_version < (2, 8, 0):
            gobject.type_register(LogTreeView)

        self.tree = self.graphview.treeview
        self.graphview.connect('revision-selected', self.selection_changed)
        self.graphview.connect('revisions-loaded', self.revisions_loaded)

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

        hbox = gtk.HBox()
        hbox.pack_start(self.graphview, True, True, 0)
        vbox = gtk.VBox()
        self.colmenu = gtk.MenuToolButton('')
        self.colmenu.set_menu(self.view_menu())
        # A MenuToolButton has two parts; a Button and a ToggleButton
        # we want to see the togglebutton, but not the button
        b = self.colmenu.child.get_children()[0]
        b.unmap()
        b.set_sensitive(False)
        self.nextbutton = gtk.ToolButton(gtk.STOCK_GO_DOWN)
        self.nextbutton.connect('clicked', self.more_clicked)
        self.allbutton = gtk.ToolButton(gtk.STOCK_GOTO_BOTTOM)
        self.allbutton.connect('clicked', self.load_all_clicked)
        vbox.pack_start(self.colmenu, False, False)
        vbox.pack_start(gtk.Label(''), True, True) # expanding blank label
        vbox.pack_start(self.nextbutton, False, False)
        vbox.pack_start(self.allbutton, False, False)

        self.nextbutton.set_tooltip(self.tooltips,
                _('show next %d revisions') % self.limit)
        self.allbutton.set_tooltip(self.tooltips,
                _('show all remaining revisions'))

        hbox.pack_start(vbox, False, False, 0)
        treeframe.add(hbox)
        treeframe.show_all()

        # Add ChangeSet instance to bottom half of vpane
        self.changeview.graphview = self.graphview
        self.hpaned = self.changeview.get_body()

        self.vpaned = gtk.VPaned()
        self.vpaned.pack1(treeframe, True, False)
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

    def strip_rev(self, menuitem):
        rev = self.currow[treemodel.REVID]
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

    def backout_rev(self, menuitem):
        rev = self.currow[treemodel.REVID]
        rev = str(self.repo[rev])
        parents = [x.node() for x in self.repo.parents()]
        dlg = backout.BackoutDialog(rev)
        dlg.set_transient_for(self)
        dlg.show_all()
        dlg.set_notify_func(self.checkout_completed, parents)
        dlg.present()
        dlg.set_transient_for(None)

    def revert(self, menuitem):
        rev = self.currow[treemodel.REVID]
        res = gdialog.Confirm(_('Confirm Revert Revision(s)'), [], self,
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
        rev = self.currow[treemodel.REVID]
        self._do_diff(pats, {'change' : rev}, modal=True)

    def vdiff_local(self, menuitem, pats=[]):
        rev = self.currow[treemodel.REVID]
        opts = {'rev' : ["%s" % rev]}
        self._do_diff(pats, opts, modal=True)

    def diff_revs(self, menuitem):
        rev0, rev1 = self.revs
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
        rev0, rev1 = self.revs
        self.opts['rev'] = ["%s:%s" % (rev0, rev1)]
        if len(self.pats) == 1:
            self._diff_file(None, self.pats[0])
        else:
            self._diff_file(None, None)

    def email_revs(self, menuitem):
        revs = list(self.revs)
        revs.sort()
        opts = ['--rev', str(revs[0]) + ':' + str(revs[1])]
        dlg = hgemail.EmailDialog(self.repo.root, opts)
        dlg.set_transient_for(self)
        dlg.show_all()
        dlg.present()
        dlg.set_transient_for(None)

    def bundle_revs(self, menuitem):
        revs = list(self.revs)
        revs.sort()
        parent = self.repo[revs[0]].parents()[0].rev()
        # Special case for revision 0's parent.
        if parent == -1: parent = 'null'

        filename = "%s_rev%d_to_rev%s.hg" % (os.path.basename(self.repo.root),
                   revs[0], revs[1])
        result = gtklib.NativeSaveFileDialogWrapper(Title=_('Write bundle to'),
                                         InitialDir=self.repo.root,
                                         FileName=filename).run()
        if result:
            cmdline = ['hg', 'bundle', '--base', str(parent),
                      '--rev', str(revs[1]), result]
            dlg = hgcmd.CmdDialog(cmdline)
            dlg.show_all()
            dlg.run()
            dlg.hide()

    def add_tag(self, menuitem):
        # save tag info for detecting new tags added
        oldtags = self.repo.tagslist()
        oldlen = len(self.repo)
        rev = self.currow[treemodel.REVID]

        def refresh(*args):
            self.repo.invalidate()
            if len(self.repo) != oldlen:
                self.reload_log()
            else:
                newtags = self.repo.tagslist()
                if newtags != oldtags:
                    self.refresh_model()

        dialog = tagadd.TagAddDialog(self.repo.root, rev=str(rev))
        dialog.set_transient_for(self)
        dialog.connect('destroy', refresh)
        dialog.show_all()
        dialog.present()
        dialog.set_transient_for(None)

    def show_status(self, menuitem):
        rev = self.currow[treemodel.REVID]
        statopts = {'rev' : [str(rev)] }
        dialog = changeset.ChangeSet(self.ui, self.repo, self.cwd, [], statopts)
        dialog.display()

    def copy_hash(self, menuitem):
        rev = self.currow[treemodel.REVID]
        node = str(self.repo[rev])
        sel = (os.name == 'nt') and 'CLIPBOARD' or 'PRIMARY'
        clipboard = gtk.Clipboard(selection=sel)
        clipboard.set_text(node)

    def export_patch(self, menuitem):
        rev = self.currow[treemodel.REVID]
        filename = "%s_rev%s.patch" % (os.path.basename(self.repo.root), rev)
        fd = gtklib.NativeSaveFileDialogWrapper(Title=_('Save patch to'),
                                         InitialDir=self.repo.root,
                                         FileName=filename)
        result = fd.run()

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
            rev = int(self.currow[treemodel.REVID])
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
        rev = self.currow[treemodel.REVID]
        dlg = hgemail.EmailDialog(self.repo.root, ['--rev', str(rev)])
        dlg.set_transient_for(self)
        dlg.show_all()
        dlg.present()
        dlg.set_transient_for(None)

    def checkout(self, menuitem):
        rev = self.currow[treemodel.REVID]
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

    def merge(self, menuitem):
        rev = self.currow[treemodel.REVID]
        parents = [x.node() for x in self.repo.parents()]
        if rev == self.repo.parents()[0].rev():
            rev = self.revs[1]
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

    def selection_changed(self, treeview):
        self.currow = self.graphview.get_revision()
        rev = self.currow[treemodel.REVID]
        if rev != self.last_rev:
            self.last_rev = rev
            self.changeview.opts['rev'] = [str(rev)]
            self.changeview.load_details(rev)
        return False

    def thgrefresh(self, window):
        self.reload_log()

    def refresh_clicked(self, toolbutton, data=None):
        self.reload_log()
        return True

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
                self.orig_sel = srow
                self.revs = (int(model[srow][treemodel.REVID]),
                        int(model[crow][treemodel.REVID]))
                self.tree_popup_menu_diff(tree, event.button, event.time)
            return True
        return False

    def tree_popup_menu(self, treeview, button=0, time=0) :
        selrev = self.currow[treemodel.REVID]

        # disable/enable menus as required
        parents = [x.rev() for x in self.repo.parents()]
        can_merge = selrev not in parents and len(parents) < 2
        self.cmenu_merge.set_sensitive(can_merge)

        # display the context menu
        self._menu.popup(None, None, None, button, time)
        return True

    def tree_popup_menu_diff(self, treeview, button=0, time=0):
        selrev = self.revs[0]

        # disable/enable menus as required
        parents = [x.rev() for x in self.repo.parents()]
        can_merge = selrev in parents and len(parents) < 2
        self.cmenu_merge2.set_sensitive(can_merge)

        # display the context menu
        self._menu2.popup(None, None, None, button, time)
        return True

    def tree_row_act(self, tree, path, column) :
        'Default action is the first entry in the context menu'
        self._menu.get_children()[0].activate()
        return True

def run(ui, *pats, **opts):
    limit = opts.get('limit')
    cmdoptions = {
        'follow':False, 'follow-first':False, 'copies':False, 'keyword':[],
        'limit':limit, 'rev':[], 'removed':False, 'no_merges':False,
        'date':None, 'only_merges':None, 'prune':[], 'git':False,
        'verbose':False, 'include':[], 'exclude':[]
    }
    root = paths.find_root()
    canonpats = []
    for f in pats:
        canonpats.append(util.canonpath(root, os.getcwd(), f))
    return GLog(ui, None, None, canonpats, cmdoptions)

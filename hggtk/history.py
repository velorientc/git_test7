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

from mercurial.node import *
from mercurial.i18n import _
from mercurial import ui, hg, commands, extensions
from gdialog import *
from changeset import ChangeSet
from vis import treemodel
from vis.treeview import TreeView
import hglib
import gtklib

def create_menu(label, callback):
    menuitem = gtk.MenuItem(label, True)
    menuitem.connect('activate', callback)
    menuitem.set_border_width(1)
    return menuitem

class GLog(GDialog):
    """GTK+ based dialog for displaying repository logs
    """
    def get_title(self):
        return os.path.basename(self.repo.root) + ' log'

    def get_icon(self):
        return 'menulog.ico'

    def parse_opts(self):
        # Disable quiet to get full log info
        self.ui.quiet = False

    def get_tbbuttons(self):
        tbar = [
                self.make_toolbutton(gtk.STOCK_REFRESH,
                    _('Re_fresh'),
                    self._refresh_clicked,
                    tip=_('Reload revision history')),
                gtk.SeparatorToolItem(),
                self.make_toolbutton(gtk.STOCK_INDEX,
                    _('_Filter'),
                    self._filter_clicked,
                    menu=self._filter_menu(),
                    tip=_('Filter revisions for display')),
                gtk.SeparatorToolItem(),
                self.make_toolbutton(gtk.STOCK_FIND,
                    _('_DataMine'),
                    self._datamine_clicked,
                    tip=_('Search Repository History')),
                gtk.SeparatorToolItem()
             ] + self.changeview.get_tbbuttons()
        if not self.opts.get('from-synch'):
            tbar += [
                gtk.SeparatorToolItem(),
                self.make_toolbutton(gtk.STOCK_NETWORK,
                                 _('Synchronize'),
                                 self._synch_clicked,
                                 tip=_('Launch synchronize tool')),
                    ]
        return tbar

    def _synch_clicked(self, toolbutton, data):
        from synch import SynchDialog
        dlg = SynchDialog([], False)
        dlg.show_all()

    def toggle_view_column(self, button, property):
        active = button.get_active()
        self.graphview.set_property(property, active)

    def _more_clicked(self, button):
        self.graphview.next_revision_batch(self.limit)

    def _load_all_clicked(self, button):
        self.graphview.load_all_revisions()
        self.nextbutton.set_sensitive(False)
        self.allbutton.set_sensitive(False)

    def revisions_loaded(self, graphview):
        '''Treeview reports log generator has exited'''
        if not self.graphview.graphdata:
            self.changeview._buffer.set_text('')
            self.changeview._filelist.clear()
            self._last_rev = None
        self.nextbutton.set_sensitive(False)
        self.allbutton.set_sensitive(False)

    def _datamine_clicked(self, toolbutton, data=None):
        from datamine import DataMineDialog
        dialog = DataMineDialog(self.ui, self.repo, self.cwd, [], {})
        dialog.display()

    def _filter_clicked(self, toolbutton, data=None):
        if self._filter_dialog:
            self._filter_dialog.show()
            self._filter_dialog.present()
        else:
            self._show_filter_dialog()

    def _show_filter_dialog(self):
        '''Launch a modeless filter dialog'''
        def do_reload(opts):
            self.custombutton.set_active(True)
            self.reload_log(opts)

        def close_filter_dialog(dialog, response_id):
            dialog.hide()

        def delete_event(dialog, event, data=None):
            # return True to prevent the dialog from being destroyed
            return True

        revs = []
        if self.currow is not None:
            revs.append(self.currow[treemodel.REVID])

        from logfilter import FilterDialog
        dlg = FilterDialog(self.repo.root, revs, self.pats,
                filterfunc=do_reload)
        dlg.connect('response', close_filter_dialog)
        dlg.connect('delete-event', delete_event)
        dlg.set_modal(False)
        dlg.show()

        self._filter_dialog = dlg

    def _filter_selected(self, widget, data=None):
        if widget.get_active():
            self._filter = data
            self.reload_log()

    def _view_menu(self):
        menu = gtk.Menu()

        button = gtk.CheckMenuItem(_('Show Rev'))
        button.connect("toggled", self.toggle_view_column,
                'rev-column-visible')
        button.set_active(self._show_rev)
        button.set_draw_as_radio(True)
        menu.append(button)
        button = gtk.CheckMenuItem(_('Show ID'))
        button.connect("toggled", self.toggle_view_column,
                'id-column-visible')
        button.set_active(self._show_id)
        button.set_draw_as_radio(True)
        menu.append(button)
        button = gtk.CheckMenuItem(_('Show Date'))
        button.connect("toggled", self.toggle_view_column,
                'date-column-visible')
        button.set_active(self._show_date)
        button.set_draw_as_radio(True)
        menu.append(button)
        button = gtk.CheckMenuItem(_("Show Branch"))
        button.connect("toggled", self.toggle_view_column,
                'branch-column-visible')
        button.set_active(self._show_branch)
        button.set_draw_as_radio(True)
        menu.append(button)
        menu.show_all()
        return menu

    def _filter_menu(self):
        menu = gtk.Menu()

        button = gtk.RadioMenuItem(None, _('Show All Revisions'))
        button.set_active(True)
        button.connect('toggled', self._filter_selected, 'all')
        menu.append(button)

        button = gtk.RadioMenuItem(button, _('Show Tagged Revisions'))
        button.connect('toggled', self._filter_selected, 'tagged')
        menu.append(button)

        button = gtk.RadioMenuItem(button, _('Show Revision Ancestry'))
        button.connect('toggled', self._filter_selected, 'ancestry')
        menu.append(button)

        button = gtk.RadioMenuItem(button, _('Show Working Parents'))
        button.connect('toggled', self._filter_selected, 'parents')
        menu.append(button)

        button = gtk.RadioMenuItem(button, _('Show Head Revisions'))
        button.connect('toggled', self._filter_selected, 'heads')
        menu.append(button)

        button = gtk.RadioMenuItem(button, _('Show Only Merge Revisions'))
        button.connect('toggled', self._filter_selected, 'only_merges')
        menu.append(button)

        button = gtk.RadioMenuItem(button, _('Show Non-Merge Revisions'))
        button.connect('toggled', self._filter_selected, 'no_merges')
        menu.append(button)

        self.custombutton = gtk.RadioMenuItem(button, _('Custom Filter'))
        self.custombutton.set_sensitive(False)
        menu.append(self.custombutton)

        menu.show_all()
        return menu

    def open_with_file(self, file):
        '''Call this before display() to open with file history'''
        self.opts['filehist'] = file

    def prepare_display(self):
        '''Called at end of display() method'''
        self._last_rev = None
        self._filter = "all"
        self.currow = None
        self.curfile = None
        self.opts['rev'] = [] # This option is dangerous - used directly by hg
        self.opts['revs'] = None
        os.chdir(self.repo.root)  # for paths relative to repo root

        if 'filehist' in self.opts:
            self.custombutton.set_active(True)
            self.reload_log({'pats' : [self.opts['filehist']]})
        elif 'revrange' in self.opts:
            self.custombutton.set_active(True)
            self.graphview.refresh(True, None, self.opts)
        elif self.pats == [self.repo.root] or self.pats == ['']:
            self.pats = []
            self.reload_log()
        elif self.pats:
            self.custombutton.set_active(True)
            self.reload_log({'pats' : self.pats})
        else:
            self.reload_log()

    def save_settings(self):
        settings = GDialog.save_settings(self)
        settings['glog'] = (self._vpaned.get_position(),
                self._hpaned.get_position(),
                self.graphview.get_property('rev-column-visible'),
                self.graphview.get_property('date-column-visible'),
                self.graphview.get_property('id-column-visible'),
                self.graphview.get_property('branch-column-visible'))
        return settings

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

    def load_settings(self, settings):
        '''Called at beginning of display() method'''

        self.stbar = gtklib.StatusBar()
        self.limit = self.get_graphlimit(None)

        # Allocate TreeView instance to use internally
        if 'limit' in self.opts:
            firstlimit = self.get_graphlimit(self.opts['limit'])
            self.graphview = TreeView(self.repo, firstlimit, self.stbar)
        else:
            self.graphview = TreeView(self.repo, self.limit, self.stbar)

        # Allocate ChangeSet instance to use internally
        self.changeview = ChangeSet(self.ui, self.repo, self.cwd, [],
                self.opts, self.stbar)
        self.changeview.display(False)
        self.changeview.glog_parent = self

        GDialog.load_settings(self, settings)
        self._setting_vpos = -1
        self._setting_hpos = -1
        (self._show_rev, self._show_date, self._show_id,
                self._show_branch) = True, True, False, False
        if settings:
            data = settings['glog']
            if type(data) == int:
                self._setting_vpos = data
            elif len(data) == 2:
                (self._setting_vpos, self._setting_hpos) = data
            elif len(data) == 5:
                (self._setting_vpos, self._setting_hpos,
                 self._show_rev, self._show_date, self._show_id) = data
            elif len(data) == 6:
                (self._setting_vpos, self._setting_hpos,
                 self._show_rev, self._show_date, self._show_id,
                 self._show_branch) = data

    def reload_log(self, filteropts={}):
        """Send refresh event to treeview object"""
        os.chdir(self.repo.root)  # for paths relative to repo root
        self.nextbutton.set_sensitive(True)
        self.allbutton.set_sensitive(True)
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
        elif self._filter == "all":
            self.graphview.refresh(True, None, self.opts)
        elif self._filter == "only_merges":
            self.opts['only_merges'] = True
            self.graphview.refresh(False, [], self.opts)
        elif self._filter == "no_merges":
            self.opts['no_merges'] = True
            self.graphview.refresh(False, [], self.opts)
        elif self._filter == "ancestry":
            if not self.currow:
                return
            range = [self.currow[treemodel.REVID], 0]
            sopts = {'noheads': True, 'revrange': range}
            self.graphview.refresh(True, None, sopts)
        elif self._filter == "tagged":
            tagged = []
            for t, r in self.repo.tagslist():
                hr = hex(r)
                if hr not in tagged:
                    tagged.insert(0, hr)
            self.opts['revs'] = tagged
            self.graphview.refresh(False, [], self.opts)
        elif self._filter == "parents":
            repo_parents = [x.rev() for x in self.repo.changectx(None).parents()]
            self.opts['revs'] = [str(x) for x in repo_parents]
            self.graphview.refresh(False, [], self.opts)
        elif self._filter == "heads":
            heads = [self.repo.changelog.rev(x) for x in self.repo.heads()]
            self.opts['revs'] = [str(x) for x in heads]
            self.graphview.refresh(False, [], self.opts)

    def tree_context_menu(self):
        _menu = gtk.Menu()
        _menu.append(create_menu(_('di_splay'), self._show_status))
        _menu.append(create_menu(_('visualize change'), self._vdiff_change))
        _menu.append(create_menu(_('diff to local'), self._vdiff_local))
        _menu.append(create_menu(_('_update'), self._checkout))
        self._cmenu_merge = create_menu(_('_merge with'), self._merge)
        _menu.append(self._cmenu_merge)
        _menu.append(create_menu(_('_copy hash'), self._copy_hash))
        _menu.append(create_menu(_('_export patch'), self._export_patch))
        _menu.append(create_menu(_('e_mail patch'), self._email_patch))
        _menu.append(create_menu(_('_bundle rev:tip'), self._bundle_rev_to_tip))
        _menu.append(create_menu(_('add/remove _tag'), self._add_tag))
        _menu.append(create_menu(_('backout revision'), self._backout_rev))
        _menu.append(create_menu(_('_revert'), self._revert))

        # need mq extension for strip command
        extensions.loadall(self.ui)
        extensions.load(self.ui, 'mq', None)
        _menu.append(create_menu(_('strip revision'), self._strip_rev))

        _menu.show_all()
        return _menu

    def _restore_original_selection(self, widget, *args):
        self.tree.get_selection().set_mode(gtk.SELECTION_SINGLE)
        self.tree.get_selection().select_path(self._orig_sel)

    def tree_diff_context_menu(self):
        _menu = gtk.Menu()
        _menu.append(create_menu(_('_diff with selected'), self._diff_revs))
        _menu.append(create_menu(_('visual diff with selected'),
                self._vdiff_selected))
        _menu.append(create_menu(_('email from here to selected'),
            self._email_revs))
        _menu.append(create_menu(_('bundle from here to selected'),
            self._bundle_revs))
        _menu.connect_after('selection-done', self._restore_original_selection)
        _menu.show_all()
        return _menu

    def get_body(self):
        self._filter_dialog = None
        self._menu = self.tree_context_menu()
        self._menu2 = self.tree_diff_context_menu()

        self.tree_frame = gtk.Frame()
        self.tree_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)

        # PyGtk 2.6 and below did not automatically register types
        if gobject.pygtk_version < (2, 8, 0):
            gobject.type_register(TreeView)

        self.tree = self.graphview.treeview
        self.graphview.connect('revision-selected', self.selection_changed)
        self.graphview.connect('revisions-loaded', self.revisions_loaded)

        #self.tree.connect('button-release-event', self._tree_button_release)
        self.tree.connect('button-press-event', self._tree_button_press)
        #self.tree.connect('popup-menu', self._tree_popup_menu)
        self.tree.connect('row-activated', self._tree_row_act)
        #self.tree.modify_font(pango.FontDescription(self.fontlist))

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)
        mod = shlib.get_thg_modifier()
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
        self.colmenu.set_menu(self._view_menu())
        # A MenuToolButton has two parts; a Button and a ToggleButton
        # we want to see the togglebutton, but not the button
        b = self.colmenu.child.get_children()[0]
        b.unmap()
        b.set_sensitive(False)
        self.nextbutton = gtk.ToolButton(gtk.STOCK_GO_DOWN)
        self.nextbutton.connect('clicked', self._more_clicked)
        self.allbutton = gtk.ToolButton(gtk.STOCK_GOTO_BOTTOM)
        self.allbutton.connect('clicked', self._load_all_clicked)
        vbox.pack_start(self.colmenu, False, False)
        vbox.pack_start(gtk.Label(''), True, True) # expanding blank label
        vbox.pack_start(self.nextbutton, False, False)
        vbox.pack_start(self.allbutton, False, False)

        self.nextbutton.set_tooltip(self.tooltips,
                _('show next %d revisions') % self.limit)
        self.allbutton.set_tooltip(self.tooltips,
                _('show all remaining revisions'))

        hbox.pack_start(vbox, False, False, 0)
        self.tree_frame.add(hbox)
        self.tree_frame.show_all()

        # Add ChangeSet instance to bottom half of vpane
        self.changeview.graphview = self.graphview
        self._hpaned = self.changeview.get_body()

        self._vpaned = gtk.VPaned()
        self._vpaned.pack1(self.tree_frame, True, False)
        self._vpaned.pack2(self._hpaned)
        gobject.idle_add(self.realize_settings)

        vbox = gtk.VBox()
        vbox.pack_start(self._vpaned, True, True)

        # Append status bar
        vbox.pack_start(gtk.HSeparator(), False, False)
        vbox.pack_start(self.stbar, False, False)
        return vbox

    def realize_settings(self):
        self._vpaned.set_position(self._setting_vpos)
        self._hpaned.set_position(self._setting_hpos)

    def thgdiff(self, treeview):
        'ctrl-d handler'
        self._vdiff_change(None)

    def thgparent(self, treeview):
        'ctrl-p handler'
        parent = self.repo['.'].rev()
        self.graphview.set_revision_id(parent)

    def _strip_rev(self, menuitem):
        rev = self.currow[treemodel.REVID]
        res = Confirm(_('Confirm Strip Revision(s)'), [], self,
                _('Remove revision %d and all descendants?') % rev).run()
        if res != gtk.RESPONSE_YES:
            return
        from hgcmd import CmdDialog
        cmdline = ['hg', 'strip', str(rev)]
        dlg = CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        self.repo.invalidate()
        self.reload_log()

    def _backout_rev(self, menuitem):
        from backout import BackoutDialog
        rev = self.currow[treemodel.REVID]
        rev = short(self.repo.changelog.node(rev))
        parents = [x.node() for x in self.repo.changectx(None).parents()]
        dialog = BackoutDialog(rev)
        dialog.set_transient_for(self)
        dialog.show_all()
        dialog.set_notify_func(self.checkout_completed, parents)
        dialog.present()
        dialog.set_transient_for(None)

    def _revert(self, menuitem):
        rev = self.currow[treemodel.REVID]
        res = Confirm(_('Confirm Revert Revision(s)'), [], self,
                _('Revert all files to revision %d?\nThis will overwrite your '
                  'local changes') % rev).run()

        if res != gtk.RESPONSE_YES:
            return

        cmdline = ['hg', 'revert', '--verbose', '--all', '--rev', str(rev)]

        from hgcmd import CmdDialog
        dlg = CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()

    def _vdiff_change(self, menuitem, pats=[]):
        rev = self.currow[treemodel.REVID]
        self._do_diff(pats, {'change' : rev}, modal=True)

    def _vdiff_local(self, menuitem, pats=[]):
        rev = self.currow[treemodel.REVID]
        opts = {'rev' : ["%s:." % rev]}
        self._do_diff(pats, opts, modal=True)

    def _diff_revs(self, menuitem):
        from status import GStatus
        rev0, rev1 = self._revs
        statopts = self.merge_opts(commands.table['^status|st'][1],
                ('include', 'exclude', 'git'))
        statopts['rev'] = ['%u:%u' % (rev0, rev1)]
        statopts['modified'] = True
        statopts['added'] = True
        statopts['removed'] = True
        dialog = GStatus(self.ui, self.repo, self.cwd, self.pats,
                         statopts)
        dialog.display()
        return True

    def _vdiff_selected(self, menuitem):
        rev0, rev1 = self._revs
        self.opts['rev'] = ["%s:%s" % (rev0, rev1)]
        if len(self.pats) == 1:
            self._diff_file(None, self.pats[0])
        else:
            self._diff_file(None, None)

    def _email_revs(self, menuitem):
        from hgemail import EmailDialog
        revs = list(self._revs)
        revs.sort()
        opts = ['--rev', str(revs[0]) + ':' + str(revs[1])]
        dlg = EmailDialog(self.repo.root, opts)
        dlg.set_transient_for(self)
        dlg.show_all()
        dlg.present()
        dlg.set_transient_for(None)

    def _bundle_revs(self, menuitem):
        revs = list(self._revs)
        revs.sort()
        parent = self.repo[revs[0]].parents()[0].rev()
        # Special case for revision 0's parent.
        if parent == -1: parent = 'null'

        filename = "%s_rev%d_to_rev%s.hg" % (os.path.basename(self.repo.root),
                   revs[0], revs[1])
        result = NativeSaveFileDialogWrapper(Title=_('Write bundle to'),
                                         InitialDir=self.repo.root,
                                         FileName=filename).run()
        if result:
            from hgcmd import CmdDialog
            cmdline = ['hg', 'bundle', '--base', str(parent),
                      '--rev', str(revs[1]), result]
            dlg = CmdDialog(cmdline)
            dlg.show_all()
            dlg.run()
            dlg.hide()

    def _add_tag(self, menuitem):
        from tagadd import TagAddDialog

        # save tag info for detecting new tags added
        oldtags = self.repo.tagslist()
        rev = self.currow[treemodel.REVID]

        def refresh(*args):
            self.repo.invalidate()
            newtags = self.repo.tagslist()
            if newtags != oldtags:
                self.reload_log()

        dialog = TagAddDialog(self.repo.root, rev=str(rev))
        dialog.set_transient_for(self)
        dialog.connect('destroy', refresh)
        dialog.show_all()
        dialog.present()
        dialog.set_transient_for(None)

    def _show_status(self, menuitem):
        rev = self.currow[treemodel.REVID]
        statopts = {'rev' : [str(rev)] }
        dialog = ChangeSet(self.ui, self.repo, self.cwd, [], statopts)
        dialog.display()

    def _copy_hash(self, menuitem):
        rev = self.currow[treemodel.REVID]
        node = self.repo[rev].node()
        sel = (os.name == 'nt') and 'CLIPBOARD' or 'PRIMARY'
        clipboard = gtk.Clipboard(selection=sel)
        clipboard.set_text(hex(node))

    def _export_patch(self, menuitem):
        rev = self.currow[treemodel.REVID]
        filename = "%s_rev%s.patch" % (os.path.basename(self.repo.root), rev)
        fd = NativeSaveFileDialogWrapper(Title=_('Save patch to'),
                                         InitialDir=self.repo.root,
                                         FileName=filename)
        result = fd.run()

        if result:
            if os.path.exists(result):
                os.remove(result)

            # In case new export args are added in the future, merge the
            # hg defaults
            exportOpts= self.merge_opts(commands.table['^export'][1], ())
            exportOpts['output'] = result
            def dohgexport():
                commands.export(self.ui,self.repo,str(rev),**exportOpts)
            success, outtext = self._hg_call_wrapper("Export",dohgexport,False)

    def _bundle_rev_to_tip(self, menuitem):
        try:
            rev = int(self.currow[treemodel.REVID])
            parent = self.repo[rev].parents()[0].rev()
            # Special case for revision 0's parent.
            if parent == -1: parent = 'null'
        except (ValueError, hglib.LookupError):
            return
        filename = "%s_rev%d_to_tip.hg" % (os.path.basename(self.repo.root), rev)
        result = NativeSaveFileDialogWrapper(Title=_('Write bundle to'),
                                         InitialDir=self.repo.root,
                                         FileName=filename).run()
        if result:
            from hgcmd import CmdDialog
            cmdline = ['hg', 'bundle', '--base', str(parent), result]
            dlg = CmdDialog(cmdline)
            dlg.show_all()
            dlg.run()
            dlg.hide()

    def _email_patch(self, menuitem):
        from hgemail import EmailDialog
        rev = self.currow[treemodel.REVID]
        dlg = EmailDialog(self.repo.root, ['--rev', str(rev)])
        dlg.set_transient_for(self)
        dlg.show_all()
        dlg.present()
        dlg.set_transient_for(None)

    def _checkout(self, menuitem):
        from update import UpdateDialog
        rev = self.currow[treemodel.REVID]
        parents = [x.node() for x in self.repo.changectx(None).parents()]
        dialog = UpdateDialog(rev)
        dialog.set_transient_for(self)
        dialog.show_all()
        dialog.set_notify_func(self.checkout_completed, parents)
        dialog.present()
        dialog.set_transient_for(None)

    def checkout_completed(self, oldparents):
        newparents = [x.node() for x in self.repo.changectx(None).parents()]
        if not oldparents == newparents:
            self.reload_log()

    def _merge(self, menuitem):
        from merge import MergeDialog
        rev = self.currow[treemodel.REVID]
        parents = [x.node() for x in self.repo.changectx(None).parents()]
        dialog = MergeDialog(rev)
        dialog.set_transient_for(self)
        dialog.show_all()
        dialog.set_notify_func(self.merge_completed, parents)
        dialog.present()
        dialog.set_transient_for(None)

    def merge_completed(self, oldparents):
        newparents = [x.node() for x in self.repo.changectx(None).parents()]
        if not oldparents == newparents:
            self.reload_log()

    def selection_changed(self, treeview):
        self.currow = self.graphview.get_revision()
        rev = self.currow[treemodel.REVID]
        if rev != self._last_rev:
            self._last_rev = rev
            self.changeview.opts['rev'] = [str(rev)]
            self.changeview.load_details(rev)
        return False

    def thgrefresh(self, window):
        self.reload_log()

    def _refresh_clicked(self, toolbutton, data=None):
        self.reload_log()
        return True

    def _tree_button_release(self, widget, event) :
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            self._tree_popup_menu(widget, event.button, event.time)
        return False

    def _tree_button_press(self, widget, event):
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            crow = widget.get_path_at_pos(int(event.x), int(event.y))[0]
            (model, pathlist) = widget.get_selection().get_selected_rows()
            if pathlist == []:
                return False
            srow = pathlist[0]
            if srow == crow:
                self._tree_popup_menu(widget, event.button, event.time)
            else:
                widget.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
                widget.get_selection().select_path(crow)
                self._orig_sel = srow
                self._revs = (int(model[srow][treemodel.REVID]),
                        int(model[crow][treemodel.REVID]))
                self._tree_popup_menu_diff(widget, event.button, event.time)
            return True
        return False

    def _tree_popup_menu(self, treeview, button=0, time=0) :
        selrev = self.currow[treemodel.REVID]

        # disable/enable menus as required
        parents = [self.repo.changelog.rev(x.node()) for x in
                   self.repo.changectx(None).parents()]
        can_merge = selrev not in parents and len(parents) < 2
        self._cmenu_merge.set_sensitive(can_merge)

        # display the context menu
        self._menu.popup(None, None, None, button, time)
        return True

    def _tree_popup_menu_diff(self, treeview, button=0, time=0):
        # display the context menu
        self._menu2.popup(None, None, None, button, time)
        return True

    def _tree_row_act(self, tree, path, column) :
        """Default action is the first entry in the context menu
        """
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
    root = hglib.rootpath()
    canonpats = []
    for f in pats:
        canonpats.append(util.canonpath(root, os.getcwd(), f))
    return GLog(ui, None, None, canonpats, cmdoptions)

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
import shutil
import tempfile
import atexit

from mercurial import ui, hg, cmdutil, commands, extensions, util, match, url
from mercurial import error, revset

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib

from tortoisehg.hgtk.logview.treeview import TreeView as LogTreeView
from tortoisehg.hgtk.logview.treeview import COLS
DEFAULT_COLS = 'graph msg user age'.split()

from tortoisehg.hgtk import gdialog, gtklib, hgcmd, gorev, thgstrip
from tortoisehg.hgtk import backout, status, hgemail, tagadd, update, merge
from tortoisehg.hgtk import archive, changeset, thgconfig, thgmq, histdetails
from tortoisehg.hgtk import statusbar, bookmark, thgimport
from tortoisehg.hgtk import thgpbranch

MODE_REVRANGE = 0
MODE_KEYWORDS = 1
MODE_DATE     = 2
MODE_USER     = 3
MODE_FILEPATS = 4

HIST_DND_URI_LIST = 1024

DND_DEST_GRAPHVIEW = 0
DND_DEST_PATHENTRY = 1

class FilterBar(gtklib.SlimToolbar):
    'Filter Toolbar for repository log'

    def __init__(self, tooltips, filter_mode, branch_names, repo):
        gtklib.SlimToolbar.__init__(self, tooltips)
        self.filter_mode = filter_mode
        self.buttons = {}
        self.handlers = {}

        self.all = gtk.RadioButton(None, _('All'))
        self.all.set_active(True)
        self.append_widget(self.all, padding=0)
        self.buttons['all'] = self.all

        self.tagged = gtk.RadioButton(self.all, _('Tagged'))
        self.append_widget(self.tagged, padding=0)
        self.buttons['tagged'] = self.tagged

        self.ancestry = gtk.RadioButton(self.all, _('Ancestry'))
        self.append_widget(self.ancestry, padding=0)
        self.buttons['ancestry'] = self.ancestry

        self.parents = gtk.RadioButton(self.all, _('Parents'))
        self.append_widget(self.parents, padding=0)
        self.buttons['parents'] = self.parents

        self.heads = gtk.RadioButton(self.all, _('Heads'))
        self.append_widget(self.heads, padding=0)
        self.buttons['heads'] = self.heads

        self.merges = gtk.RadioButton(self.all, _('Merges'))
        self.append_widget(self.merges, padding=0)
        self.buttons['only_merges'] = self.merges

        self.hidemerges = gtk.CheckButton(_('Hide Merges'))
        self.append_widget(self.hidemerges, padding=0)
        self.buttons['no_merges'] = self.hidemerges

        self.branches = gtk.RadioButton(self.all)
        tooltips.set_tip(self.branches, _('Branch Filter'))
        self.branches.set_sensitive(False)
        self.append_widget(self.branches, padding=0)
        self.buttons['branch'] = self.branches

        self.branchcombo = gtk.combo_box_new_text()
        self.refresh(branch_names)
        self.branchcombo.set_active(0)
        self.append_widget(self.branchcombo, padding=0)

        self.custombutton = gtk.RadioButton(self.all)
        tooltips.set_tip(self.custombutton, _('Custom Filter'))
        self.custombutton.set_sensitive(False)
        self.append_widget(self.custombutton, padding=0)
        self.buttons['custom'] = self.custombutton

        self.filtercombo = gtk.combo_box_new_text()
        self.filtercombo_entries = [_('Revision Set'), _('Keywords'),
                                    _('Date'), _('User'), _('File Patterns')]
        try:
            enclist = repo.ui.configlist('tortoisehg', 'fsencodings')
            if enclist:
                l = [_('File Patterns') + ' (%s)' % enc for enc in enclist]
                self.filtercombo_entries = self.filtercombo_entries[:-1] + l
        except (error.ConfigError, error.Abort):
            pass
        for f in self.filtercombo_entries:
            self.filtercombo.append_text(f)
        if (self.filter_mode >= len(self.filtercombo_entries) or
                self.filter_mode < 0):
            self.filter_mode = 1
        self.filtercombo.set_active(self.filter_mode)
        self.append_widget(self.filtercombo, padding=0)

        searchlist = gtk.ListStore(int, # filtercombo value
                                   str, # search string (utf-8)
                                   str) # mode string (utf-8)
        entrycombo = gtk.ComboBoxEntry(searchlist, 1)
        cell = gtk.CellRendererText()
        entrycombo.pack_end(cell, False)
        entrycombo.add_attribute(cell, 'text', 2)
        entry = entrycombo.child
        self.entrycombo = entrycombo
        self.entry = entry
        self.append_widget(entrycombo, expand=True, padding=0)

    def connect(self, detailed_signal, handler, *opts):
        '''Connect an external signal handler to an internal widget
           Signal format is '[widget_name]_[signal]'.'''
        widget_name, signal = detailed_signal.split('_')
        widget = self.__dict__[widget_name]
        widget.connect(signal, handler, *opts)

        if not self.handlers.has_key(widget_name):
            self.handlers[widget_name] = []
        self.handlers[widget_name].append(handler)

    def get_button(self, type):
        return self.buttons.get(type)

    def refresh(self, branch_names):
        ''' refresh branch names in drop-down list '''
        # block all handlers
        if self.handlers.has_key('branchcombo'):
            handlers = self.handlers['branchcombo']
            for handler in handlers:
                self.branchcombo.handler_block_by_func(handler)
        else:
            handlers = ()

        # save selected item
        text = self.branchcombo.get_active_text()

        # refresh branch names
        self.branchcombo.get_model().clear()
        self.branchcombo.append_text(_('Branches...'))
        for name in sorted(branch_names):
            self.branchcombo.append_text(name)

        # try to restore previously selected item
        for row in self.branchcombo.get_model():
            if row[0] == text:
                self.branchcombo.set_active_iter(row.iter)
                break
        else:
            # fallback to 'All' filter if no matches
            self.branchcombo.set_active(0)
            self.all.set_active(True)

        # unblock all handlers
        for handler in handlers:
            self.branchcombo.handler_unblock_by_func(handler)

class GLog(gdialog.GWindow):
    'GTK+ based dialog for displaying repository logs'
    def init(self):
        self.filter = 'all'
        self.no_merges = False
        self.lastrevid = None
        self.currevid = None
        self.origtip = len(self.repo)
        self.ready = False
        self.filterbar = None
        self.details_model = None
        self.syncbox = None
        self.filteropts = None
        self.bundledir = None
        self.bfile = None
        self.npreviews = 0
        self.outgoing = []
        self.useproxy = None
        self.revrange = None
        self.forcesync = False
        self.newbranch = False
        self.bundle_autoreject = False
        self.runner = hgcmd.CmdRunner()
        os.chdir(self.repo.root)
        self.exs = [ name for name, module in extensions.extensions() ]

    def get_help_url(self):
        return 'changelog.html'

    def delete(self, window, event):
        if not self.should_live():
            self.destroy()
        else:
            return True

    def should_live(self, widget=None, event=None):
        live = False
        if self.bfile and not self.bundle_autoreject:
            t = _('New changesets from the preview bundle are still pending.'
                  '\n\nAccept or reject the new changesets?')
            # response: 0=Yes, 1=No, 2=Cancel
            response = gdialog.CustomPrompt(_('Accept new Changesets'),
                t,
                self,
                (_('&Accept'), _('&Reject'), _('&Cancel')), 2, 2).run()
            if response == 0:
                self.apply_clicked(None)
            elif response == 2:
                live = True
        if not live:
            self._destroying(widget)
        return live

    def get_title(self):
        str = self.get_reponame() + ' - ' + _('Repository Explorer')
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
                    self.refresh_clicked, name='refresh',
                    tip=_('Reload revision history')),
                self.make_toolbutton(gtk.STOCK_CLEAR,
                    _('Reset _Marks'),
                    self.refresh_clicked, userdata=True, name='reset',
                    tip=_('Reset revision marks')),
               ]
        if 'mq' in self.exs:
            self.mqtb = self.make_toolbutton(gtk.STOCK_DIRECTORY,
                            _('Patch Queue'),
                            self.mq_clicked, name='mq',
                            tip=_('Show/Hide Patch Queue'),
                            toggle=True,
                            icon='menupatch.ico')
            tbar += [self.mqtb]
        if 'pbranch' in self.exs:
            self.pbranchtb = self.make_toolbutton(gtk.STOCK_DIRECTORY,
                            _('Patch Branch'),
                            self.pbranch_clicked, name='pbranch',
                            tip=_('Show/Hide Patch Branch'),
                            toggle=True,
                            icon='menupatch.ico')
            tbar += [self.pbranchtb]
        if 'mq' in self.exs or 'pbranch' in self.exs:
            tbar += [gtk.SeparatorToolItem()]
        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)
        tbar.append(sep)
        tbar += [
            self.make_toolbutton(gtk.STOCK_OK, _('Commit'),
                self.launch, userdata='commit', icon='menucommit.ico',
                tip=_('Launch commit tool')),
            self.make_toolbutton(gtk.STOCK_OK, _('Datamine'),
                self.launch, userdata='datamine', icon='menurepobrowse.ico',
                tip=_('Launch data mining tool')),
            self.make_toolbutton(gtk.STOCK_OK, _('Recovery'),
                self.launch, userdata='recovery', icon='general.ico',
                tip=_('Launch recovery tool')),
            self.make_toolbutton(gtk.STOCK_OK, _('Serve'),
                self.launch, userdata='serve', icon='proxy.ico',
                tip=_('Launch web server')),
            self.make_toolbutton(gtk.STOCK_OK, _('Shelve'),
                self.launch, userdata='shelve', icon='shelve.ico',
                tip=_('Launch shelve tool')),
                ]
        return tbar

    def get_menu_list(self):
        def toggle_proxy(menuitem):
            self.useproxy = menuitem.get_active()
        def toggle_force(menuitem):
            self.forcesync = menuitem.get_active()
        def toggle_newbranch(menuitem):
            self.newbranch = menuitem.get_active()
        def refresh(menuitem, resetmarks):
            if resetmarks:
                self.stbar.set_idle_text(None)
                self.outgoing = []
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

        # navigation menu (branches, tags)
        navi_menu = []

        lb = hglib.getlivebranch(self.repo)
        filter_b = []
        if len(lb) > 1 or (lb and lb[0] != 'default'):
            navi_b = []
            for name in lb[:10]:
                lname = hglib.fromutf(name)
                navi_b.append(dict(text=name, func=navigate, args=[lname],
                                   use_underline=False))
                filter_b.append(dict(text=name, name='@' + name,
                         func=self.filter_handler, args=['branch', name],
                         asradio=True, rg='all', use_underline=False))
            if len(navi_b) > 0:
                navi_menu.append(dict(text='----'))
                navi_menu.append(dict(text=_('Branches'), subitems=navi_b,
                                      icon='branch.ico'))

        ft = hglib.getfilteredtags(self.repo)
        ft.sort()
        ft.reverse()
        navi_t = []
        for tag in ft:
            tname = hglib.toutf(tag)
            navi_t.append(dict(text=tname, func=navigate, args=[tag],
                               use_underline=False))
        if len(navi_t) > 0:
            if len(navi_menu) == 0:
                navi_menu.append(dict(text='----'))
            navi_menu.append(dict(text=_('Tags'), subitems=navi_t,
                                  icon=gtk.STOCK_ITALIC))

        # sync menu
        fnc = self.toggle_view_column
        if self.repo.ui.configbool('tortoisehg', 'disable-syncbar'):
            sync_bar_item = []
        else:
            sync_bar_item = [dict(text=_('Sync Bar'), ascheck=True, 
                    func=self.toggle_show_syncbar, check=self.show_syncbar)]

        # MQ extension menu
        if 'mq' in self.exs:
            mq_item = [dict(text=_('Patch Queue'), name='mq', ascheck=True,
                func=self.mq_clicked, check=self.setting_mqvis) ]
        else:
            mq_item = []

        # Perforce extension menu
        if 'perfarce' in self.exs:
            p4menu = [dict(text=_('_Perforce'), subitems=[
                dict(text=_('Identify'), func=self.p4identify,
                    icon=gtk.STOCK_PROPERTIES),
                dict(text=_('Pending'), func=self.p4pending,
                    icon=gtk.STOCK_APPLY),
                ])]
        else:
            p4menu = []

        if 'pbranch' in self.exs:
            pbranch_item = [dict(text=_('Patch Branch'), name='pbranch', ascheck=True,
                func=self.pbranch_clicked, check=self.setting_pbranchvis) ]
        else:
            pbranch_item = []

        return [
        dict(text=_('_View'), subitems=[
            dict(text=_('Load more Revisions'), name='load-more',
                func=self.more_clicked, icon=gtk.STOCK_GO_DOWN),
            dict(text=_('Load all Revisions'), name='load-all',
                func=self.load_all_clicked, icon=gtk.STOCK_GOTO_BOTTOM),
            dict(text='----'),
            dict(text=_('Toolbar'), ascheck=True, check=self.show_toolbar,
                func=self.toggle_show_toolbar),
            ] + sync_bar_item + [
            dict(text=_('Filter Bar'), ascheck=True,
                func=self.toggle_show_filterbar, check=self.show_filterbar),
            ] + mq_item + pbranch_item + [
            dict(text='----'),
            dict(text=_('Refresh'), func=refresh, args=[False],
                icon=gtk.STOCK_REFRESH),
            dict(text=_('Reset Marks'), func=refresh, args=[True],
                icon=gtk.STOCK_CLEAR),
            dict(text='----'),
            dict(text=_('Choose Details...'), func=self.details_clicked,
                icon='general.ico'),
            dict(text='----'),
            dict(name='compact-graph', text=(_('Compact Graph')),
                ascheck=True, func=self.toggle_compactgraph,
                check=self.compactgraph),
            dict(name='color-by-branch', text=_('Color by Branch'),
                ascheck=True, func=self.toggle_branchcolor,
                check=self.branch_color),
            dict(text=_('Ignore Max Diff Size'), ascheck=True,
                func=disable_maxdiff),
            dict(name='always-show-output', text=(_('Always Show Output')),
                ascheck=True, func=self.toggle_showoutput,
                check=self.showoutput),
            ]),

        dict(text=_('_Navigate'), subitems=[
            dict(text=_('Tip'), func=navigate, args=['tip'],
                icon=gtk.STOCK_ABOUT),
            dict(text=_('Working Parent'), func=navigate, args=['.'],
                icon=gtk.STOCK_HOME),
            dict(text=_('Previously Selected'), icon=gtk.STOCK_GO_BACK,
                func=lambda *a: self.goto_prev_sel()),
            dict(text='----'),
            dict(text=_('Revision...'), icon=gtk.STOCK_JUMP_TO,
                func=lambda *a: self.show_goto_dialog()),
            ] + navi_menu),

        dict(text=_('_Synchronize'), subitems=[
            dict(text=_('Incoming'), name='incoming',
                func=self.incoming_clicked, icon=gtk.STOCK_GO_DOWN),
            dict(text=_('Pull'), name='pull',
                func=self.pull_clicked, icon=gtk.STOCK_GOTO_BOTTOM),
            dict(text=_('Outgoing'), name='outgoing',
                func=self.outgoing_clicked, icon=gtk.STOCK_GO_UP),
            dict(text=_('Push'), name='push',
                func=self.push_clicked, icon=gtk.STOCK_GOTO_TOP),
            dict(text=_('Email...'), name='email',
                func=self.email_clicked, icon=gtk.STOCK_GOTO_LAST),
            dict(text=_('Stop'), name='stop', sensitive=False,
                func=self.stop_clicked, icon=gtk.STOCK_STOP),
            dict(text='----'),
            dict(text=_('Accept Bundle'), name='accept',
                sensitive=bool(self.bfile),
                func=self.apply_clicked, icon=gtk.STOCK_APPLY),
            dict(text=_('Reject Bundle'), name='reject',
                sensitive=bool(self.bfile),
                func=self.reject_clicked, icon=gtk.STOCK_DIALOG_ERROR),
            dict(text='----'),
            dict(text=_('Import...'), name='import',
                func=self.import_clicked, icon='menuimport.ico'),
            dict(text=_('Add Bundle...'), name='add-bundle',
                sensitive=not bool(self.bfile),
                func=self.add_bundle_clicked, icon=gtk.STOCK_ADD),
            dict(text='----'),
            dict(text=_('Configure Paths...'), name='path',
                func=self.conf_clicked, icon=gtk.STOCK_PREFERENCES),
            dict(text='----'),
            dict(text=_('Use proxy server'), name='use-proxy-server',
                ascheck=True, func=toggle_proxy),
            dict(text=_('Force pull or push'), ascheck=True, func=toggle_force),
            dict(text=_('Push new branch'), ascheck=True,
                func=toggle_newbranch),
            ]),

        dict(text=_('_Filter'), subitems=[
            dict(text=_('All'), name='all', asradio=True,
                func=self.filter_handler, args=['all'], check=True),
            dict(text=_('Tagged'), name='tagged', asradio=True,
                func=self.filter_handler, args=['tagged'], rg='all'),
            dict(text=_('Ancestry'), name='ancestry', asradio=True,
                func=self.filter_handler, args=['ancestry'], rg='all'),
            dict(text=_('Parents'), name='parents', asradio=True,
                func=self.filter_handler, args=['parents'], rg='all'),
            dict(text=_('Heads'), name='heads', asradio=True,
                func=self.filter_handler, args=['heads'], rg='all'),
            dict(text=_('Merges'), name='only_merges', asradio=True,
                func=self.filter_handler, args=['only_merges'], rg='all'),
            dict(text=_('Branch'), name='branch', icon='branch.ico',
                subitems=filter_b),
            dict(text=_('Custom'), name='custom', subitems=[
                dict(text=_('Revision Range'), name='revrange', asradio=True,
                    rg='all', func=self.filter_handler,
                    args=['custom', MODE_REVRANGE]),
                dict(text=_('File Patterns'), name='filepats', asradio=True,
                    rg='all', func=self.filter_handler,
                    args=['custom', MODE_FILEPATS]),
                dict(text=_('Keywords'), name='keywords', asradio=True,
                    rg='all', func=self.filter_handler,
                    args=['custom', MODE_KEYWORDS]),
                dict(text=_('Date'), name='date', asradio=True,
                    rg='all', func=self.filter_handler,
                    args=['custom', MODE_DATE]),
                dict(text=_('User'), name='user', asradio=True,
                    rg='all', func=self.filter_handler,
                    args=['custom', MODE_USER]),
                ], icon='general.ico'),
            dict(text='----'),
            dict(text=_('Hide Merges'), name='no_merges', ascheck=True,
                func=self.filter_handler, args=['no_merges']),
            ])] + p4menu

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

    def toggle_showoutput(self, button):
        active = button.get_active()
        if self.showoutput != active:
            self.showoutput = active

    def toggle_show_filterbar(self, button):
        self.show_filterbar = button.get_active()
        if self.filterbar is not None:
            self.filterbar.set_property('visible', self.show_filterbar)

    def toggle_show_syncbar(self, button):
        self.show_syncbar = button.get_active()
        if self.syncbox is not None:
            self.syncbox.set_property('visible', self.show_syncbar)

    def toggle_show_toolbar(self, button):
        self.show_toolbar = button.get_active()
        self.syncbox.set_visible('reload', not self.show_toolbar)
        self.sttool.set_visible('load', not self.show_toolbar)
        self._show_toolbar(self.show_toolbar)

    def execute_command(self, cmd, callback=None, status=None,
                        title=None, force=False):
        if self.showoutput or force:
            dlg = hgcmd.CmdDialog(cmd)
            dlg.show_all()
            dlg.run()
            dlg.hide()
            callback and callback(dlg.return_code(), dlg.get_buffer())
            return dlg
        def wrapper(*args):
            self.stbar.end()
            self.syncbox.set_enable('stop', False)
            self.cmd_set_sensitive('stop', False)
            callback and callback(*args)
        self.stbar.begin(*(status and (status,) or ()))
        if title:
            self.runner.set_title(title)
        self.syncbox.set_enable('stop', True)
        self.cmd_set_sensitive('stop', True)
        return self.runner.execute(cmd, wrapper)

    def p4pending(self, button):
        'revert or submit these pending changelists'
        cmd = ['hg', 'p4pending', '--verbose']
        def callback(return_code, buffer, *args):
            pending = {}
            if return_code == 0:
                submitted = 0
                for line in buffer.splitlines()[:-1]:
                    try:
                        hashes = line.split(' ')
                        changelist = hashes.pop(0)
                        if len(hashes)>1 and len(hashes[0])==1:
                           state = hashes.pop(0)
                           if state == 's':
                               changelist = _('%s (submitted)') % changelist
                           elif state == 'p':
                               changelist = _('%s (pending)') % changelist
                        else:
                           if changelist == 'submitted':
                               changelist = _('Submitted') + str(submitted)
                               submitted += 1
                           else:
                               changelist = _('%s (pending)') % changelist
                        pending[changelist] = hashes
                    except (ValueError, IndexError):
                        text = _('Unable to parse p4pending output')
                if pending:
                    text = _('%d pending changelists found') % len(pending)
                else:
                    text = _('No pending Perforce changelists')
            elif return_code is None:
                text = _('Aborted p4pending')
            else:
                text = _('Unable to determine pending changesets')
            self.stbar.set_idle_text(text)
            if pending:
                from tortoisehg.hgtk.p4pending import PerforcePending
                dialog = PerforcePending(self.repo, pending, self.graphview)
                dialog.show_all()
                dialog.present()
        if not self.execute_command(cmd, callback,
                    status=_('Finding pending Perforce changelists...'),
                    title=_('Pending Perforce changelists')):
            gdialog.Prompt(_('Cannot run now'),
                           _('Please try again after the previous '
                             'command has completed'), self).run()

    def p4identify(self, button):
        cmd = ['hg', 'p4identify']
        def callback(return_code, buffer, *args):
            if return_code == 0:
                lines = buffer.splitlines()[:-1]
                if len(lines) == 1:
                    changelist, hash = lines[0].split(' ')
                    text = _('Perforce changelist %s') % changelist
                    try:
                        ctx = self.repo[hash]
                        self.graphview.set_revision_id(ctx.rev(), load=True)
                    except error.LookupError:
                        text = _('Unable to find rev %s') % hash
            elif return_code is None:
                text = _('Aborted p4identify')
            else:
                text = _('Unable to identify Perforce tip')
            self.stbar.set_idle_text(text)
        if not self.execute_command(cmd, callback,
                    status=_('Finding tip Perforce changelist...'),
                    title=_('Identifying Perforce tip')):
            gdialog.Prompt(_('Cannot run now'),
                           _('Please try again after the previous '
                             'command has completed'), self).run()

    def more_clicked(self, button, data=None):
        self.graphview.next_revision_batch(self.limit)

    def load_all_clicked(self, button, data=None):
        self.graphview.load_all_revisions()
        self.cmd_set_sensitive('load-more', False)
        self.cmd_set_sensitive('load-all', False)
        self.sttool.set_enable('load', False)

    def selection_changed(self, graphview):
        'Graphview reports a new row selected'
        treeview = graphview.treeview
        path, col = treeview.get_cursor()
        if not path:
            self.currevid = None
            return False
        self.prevrevid = self.currevid
        self.currevid = graphview.get_revid_at_path(path)
        self.filterbar.get_button('ancestry').set_sensitive(True)
        self.menuitems['ancestry'].set_sensitive(True)
        if self.currevid != self.lastrevid:
            self.lastrevid = self.currevid
            self.changeview.opts['rev'] = [str(self.currevid)]
            self.changeview.load_details(self.currevid)
        return False

    def revisions_loaded(self, graphview):
        'Graphview reports log generator has exited'
        if not graphview.graphdata:
            self.changeview.clear()
        self.cmd_set_sensitive('load-more', False)
        self.cmd_set_sensitive('load-all', False)
        self.sttool.set_enable('load', False)

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
        column('revhex', _('Revision Number/ID'))
        column('branch', _('Branch Name'))
        column('changes', _('Changes'))
        column('msg', _('Summary'))
        column('user', _('User'))
        column('date', _('Local Date'))
        column('utc', _('UTC Date'))
        column('age', _('Age'))
        column('tag', _('Tags'))
        column('svn', _('Subversion'))

        model = gtk.ListStore(
            gobject.TYPE_BOOLEAN,
            gobject.TYPE_STRING,
            gobject.TYPE_STRING,
            gobject.TYPE_STRING)

        for c in self.column_order.split():
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
                        self.cmd_set_sensitive('compact-graph', self.graphcol)
                        self.cmd_set_sensitive('color-by-branch', self.graphcol)
                else:
                    self.graphview.set_property(property, show)
                    self.showcol[property] = show
            if reload:
                self.reload_log()

    def filter_entry_changed(self, entrycombo, filtercombo):
        row = entrycombo.get_active()
        if row < 0:
            return
        mode, text, display = entrycombo.get_model()[row]
        filtercombo.set_active(mode)
        entrycombo.child.set_text(text)
        self.activate_filter(text, mode)

    def filter_entry_activated(self, entry, combo):
        'User pressed enter in the filter entry'
        mode = combo.get_active()
        text = entry.get_text()
        if not text:
            return
        row = [mode, text, combo.get_active_text()]
        model = self.entrycombo.get_model()
        for r in model:
            if r[0] == row[0] and r[1] == row[1]:
                break
        else:
            self.entrycombo.get_model().append( row )
        self.activate_filter(text, mode)

    def check_filter_text(self, text, mode):
        ret = True
        if not text:
            return False
        elif mode == MODE_REVRANGE:
            try:
                func = revset.match(text)
                func(self.repo, range(0, 1))
                l = []
                for c in func(self.repo, range(len(self.repo))):
                    l.append(c)
                if not l:
                    gdialog.Prompt(_('No matches'),
                                   _('No revisions matched search'), self).run()
                    return False
                ret = l
            except Exception, e:
                gdialog.Prompt(_('Invalid revision set'), str(e), self).run()
                return False
        elif mode == MODE_DATE:
            try:
                util.matchdate(text)
            except (ValueError, util.Abort), e:
                gdialog.Prompt(_('Invalid date specification'),
                               str(e), self).run()
                return False
        elif mode == MODE_FILEPATS:
            try:
                match.match(self.repo.root, self.repo.root, [text])
            except (ValueError, util.Abort), e:
                gdialog.Prompt(_('Invalid file pattern'),
                               str(e), self).run()
                return False
        return ret

    def activate_filter(self, text, mode):
        ret = self.check_filter_text(text, mode)
        if not ret:
            return
        text = hglib.fromutf(text)
        opts = {}
        if mode == MODE_REVRANGE:
            opts['revlist'] = ret
            name = 'revrange'
        elif mode == MODE_KEYWORDS:
            opts['keyword'] = [w.strip() for w in text.split(',')]
            name = 'keywords'
        elif mode == MODE_DATE:
            opts['date'] = text
            name = 'date'
        elif mode == MODE_USER:
            opts['user'] = [w.strip() for w in text.split(',')]
            name = 'user'
        elif mode >= MODE_FILEPATS:
            opts['pats'] = [w.strip() for w in text.split(',')]
            name = 'filepats'

        self.filterbar.get_button('custom').set_active(True)
        self.filter = 'custom'
        self.reload_log(**opts)

        # update menu item
        menu = self.menuitems[name]
        menu.handler_block_by_func(self.filter_handler)
        menu.set_active(True)
        menu.handler_unblock_by_func(self.filter_handler)

    def filter_handler(self, menu, type, *args):
        if not type == 'no_merges' and not menu.get_active():
            self.lastfilterinfo = (menu, type)
            return
        if type == 'branch':
            branch = args[0]
            combo = self.branchcombo
            model = combo.get_model()
            for row in model:
                if row[0] == branch:
                    if combo.get_active_text() == branch:
                        # need to activate 'branch' radio button if specified
                        # branch was already selected at drop-down list
                        self.filterbar.get_button('branch').set_active(True)
                    else:
                        combo.set_active_iter(row.iter)
                    break
        elif type == 'custom':
            from tortoisehg.hgtk import dialog
            desc = _("'%s' filter:") % menu.child.get_text()
            mode = args[0]
            text = dialog.entry_dialog(self, desc)
            if self.check_filter_text(text, mode):
                self.filterentry.set_text(text)
                self.filtercombo.set_active(mode)
                self.filter_entry_activated(self.filterentry,
                                            self.filtercombo)
            elif self.lastfilterinfo:
                # restore previously selected filter
                pmenu, ptype = self.lastfilterinfo
                if ptype == 'custom':
                    pmenu.handler_block_by_func(self.filter_handler)
                pmenu.set_active(True)
                if ptype == 'custom':
                    pmenu.handler_unblock_by_func(self.filter_handler)
        else:
            button = self.filterbar.get_button(type)
            if button:
                button.set_active(menu.get_active())

    def filter_selected(self, widget, type):
        if not type == 'no_merges' and not widget.get_active():
            return

        if type == 'branch':
            self.lastbranchrow = None
            self.select_branch(self.branchcombo)
            return

        menu = self.menuitems[type]
        menu.handler_block_by_func(self.filter_handler)
        menu.set_active(widget.get_active())
        menu.handler_unblock_by_func(self.filter_handler)

        if type == 'no_merges':
            self.no_merges = widget.get_active()
            self.reload_log()
            return

        self.filter = type
        self.filteropts = None
        self.reload_log()

    def update_hide_merges_button(self):
        button = self.filterbar.get_button('no_merges')
        menu = self.menuitems['no_merges']
        compatible = self.filter in ['all', 'branch', 'custom']
        if compatible:
            button.set_sensitive(True)
            menu.set_sensitive(True)
        else:
            button.set_active(False)
            button.set_sensitive(False)
            menu.set_active(False)
            menu.set_sensitive(False)
            self.no_merges = False

    def patch_selected(self, mqwidget, revid, patchname):
        if revid < 0:
            patchfile = os.path.join(self.repo.mq.path, patchname)
            self.currevid = self.lastrevid = None
            self.changeview.load_patch_details(patchfile)
        else:
            self.goto_rev(revid)

    def pbranch_selected(self, pbranchwidget, revid, patchname):
        'if revid < 0 then the patch is listed in .hg/pgraph but not in repo'
        self.stbar.set_text('')
        pf = tempfile.TemporaryFile()
        try:
            try:
                pf.writelines(pbranchwidget.pdiff(patchname))
            except (util.Abort, error.RepoError), e:
                self.stbar.set_text(str(e))
                return
            self.currevid = self.lastrevid = None
            pf.seek(0)
            self.changeview.load_patch_details_from_file_object(pf, patchname, isTemp=True)
        finally:
            pf.close()

    def repo_invalidated(self, widget):
        'Emitted from MQWidget and PBranchWidget'
        self.reload_log()

    def files_dropped(self, mqwidget, files, *args):
        self.import_clicked(None, thgimport.DEST_MQ, files)

    def prepare_display(self):
        'Called at end of display() method'
        self.ready = True
        root = self.repo.root
        os.chdir(root)  # for paths relative to repo root

        self.origtip = len(self.repo)
        self.graphview.set_property('branch-color', self.branch_color)

        style = self.repo.ui.config('tortoisehg', 'logtbarstyle', 'theme')
        if style == 'small':
            self.toolbar.set_icon_size(gtk.ICON_SIZE_MENU)
            self.toolbar.set_property('toolbar-style', gtk.TOOLBAR_ICONS)
        if style == 'large':
            self.toolbar.set_icon_size(gtk.ICON_SIZE_LARGE_TOOLBAR)
            self.toolbar.set_property('toolbar-style', gtk.TOOLBAR_BOTH)

        # ignore file patterns that imply repo root
        if len(self.pats) == 1 and self.pats[0] in (root, root+os.sep, ''):
            self.pats = []

        opts = self.opts
        if opts['filehist']:
            self.filterbar.get_button('custom').set_active(True)
            self.filter = 'custom'
            self.filtercombo.set_active(1)
            path = hglib.escapepath(opts['filehist'])
            self.filterentry.set_text(hglib.toutf(path))
            self.activate_filter(path, MODE_FILEPATS)
        elif self.pats:
            self.filterbar.get_button('custom').set_active(True)
            self.filter = 'custom'
            self.filtercombo.set_active(1)
            paths = [hglib.escapepath(p) for p in self.pats]
            self.filterentry.set_text(hglib.toutf(', '.join(paths)))
            self.activate_filter(', '.join(paths), MODE_FILEPATS)
        elif 'bundle' in opts:
            self.set_bundlefile(opts['bundle'])
            self.bundle_autoreject = True
        else:
            self.reload_log(**opts)

        self.filterbar.set_property('visible', self.show_filterbar)
        self.filterbar.set_no_show_all(True)
        self.syncbox.set_property('visible', self.show_syncbar)
        self.syncbox.set_no_show_all(True)

        columns = []
        for col in [c for c in self.column_order.split()]:
            if col == 'graph':
                vis = self.graphcol
            else:
                vis = self.showcol[col]
                self.graphview.set_property(col + '-column-visible', vis)
            if vis:
                columns.append(col)
            width = self.colwidths.get(col)
            if width:
                column = self.graphview.tvcolumns[col]
                column.set_fixed_width(width)
        self.graphview.set_columns(columns)

        self.cmd_set_sensitive('compact-graph', self.graphcol)
        self.cmd_set_sensitive('color-by-branch', self.graphcol)

        item = self.get_menuitem('use-proxy-server')
        if ui.ui().config('http_proxy', 'host'):
            item.set_sensitive(True)
            item.set_active(True)
        else:
            item.set_sensitive(False)

        # enable panels
        self.enable_mqpanel()
        self.enable_pbranchpanel()

    def get_proxy_args(self):
        item = self.get_menuitem('use-proxy-server')
        if item.get_property('sensitive') and not item.get_active():
            return ['--config', 'http_proxy.host=']
        else:
            return []

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
        settings = gdialog.GWindow.save_settings(self)
        settings['glog-vpane'] = self.vpaned.get_position()
        settings['glog-hpane'] = self.hpaned.get_position()
        if hasattr(self, 'mqpaned') and self.mqwidget.has_patch():
            curpos = self.mqpaned.get_position()
            settings['glog-mqpane'] = curpos or self.setting_mqhpos
            settings['glog-mqvis'] = bool(curpos)
        else:
            settings['glog-mqpane'] = self.setting_mqhpos
            settings['glog-mqvis'] = self.setting_mqvis
        if hasattr(self, 'pbranchpaned') and self.pbranchwidget.has_patch():
            curpos = self.pbranchpaned.get_position()
            settings['glog-pbranchpane'] = curpos or self.setting_pbranchhpos
            settings['glog-pbranchvis'] = bool(curpos)
        else:
            settings['glog-pbranchpane'] = self.setting_pbranchhpos
            settings['glog-pbranchvis'] = self.setting_pbranchvis
        settings['branch-color'] = self.graphview.get_property('branch-color')
        settings['show-output'] = self.showoutput
        settings['show-toolbar'] = self.show_toolbar
        settings['show-filterbar'] = self.show_filterbar
        settings['show-syncbar'] = self.show_syncbar
        settings['graphcol'] = self.graphcol
        settings['compactgraph'] = self.compactgraph
        for col in [col for col in COLS.split() if col != 'graph']:
            vis = self.graphview.get_property(col + '-column-visible')
            settings['glog-vis-'+col] = vis
        for col in COLS.split():
            column = self.graphview.tvcolumns[col]
            settings['glog-width-' + col] = column.get_width()
        settings['filter-mode'] = self.filtercombo.get_active()
        settings['column-order'] = self.column_order
        return settings

    def load_settings(self, settings):
        'Called at beginning of display() method'
        gdialog.GWindow.load_settings(self, settings)
        self.setting_vpos = settings.get('glog-vpane', -1)
        self.setting_hpos = settings.get('glog-hpane', -1)
        self.setting_mqhpos = settings.get('glog-mqpane', 140) or 140
        self.setting_mqvis = settings.get('glog-mqvis', False)
        self.setting_pbranchhpos = settings.get('glog-pbranchpane', 140) or 140
        self.setting_pbranchvis = settings.get('glog-pbranchvis', False)
        self.branch_color = settings.get('branch-color', False)
        self.showoutput = settings.get('show-output', False)
        self.show_toolbar = settings.get('show-toolbar', True)
        self.show_filterbar = settings.get('show-filterbar', True)
        self.show_syncbar = settings.get('show-syncbar', True)
        if self.repo.ui.configbool('tortoisehg', 'disable-syncbar'):
            self.show_syncbar = False
        self.graphcol = settings.get('graphcol', True)
        self.compactgraph = settings.get('compactgraph', False)
        self.showcol = {}
        for col in [col for col in COLS.split() if col != 'graph']:
            key = 'glog-vis-' + col
            self.showcol[col] = settings.get(key, col in DEFAULT_COLS)
        self.colwidths = {}
        for col in COLS.split():
            self.colwidths[col] = settings.get('glog-width-' + col)
        self.filter_mode = settings.get('filter-mode', 1)
        order = settings.get('column-order', COLS)
        order_list, def_list = order.split(), COLS.split()
        order_len, def_len = len(order_list), len(def_list)
        if order_len != def_len:
            # add newly added columns if exists
            added = set(def_list).difference(set(order_list))
            if added:
                order_list += list(added)
            # remove obsoleted columns if exists
            order_list = [c for c in order_list if c in def_list]
            order = ' '.join(order_list)
        self.column_order = order

    def show_toolbar_on_start(self):
        return self.show_toolbar

    def refresh_model(self):
        'Refresh data in the history model, without reloading graph'
        if self.graphview.model:
            self.graphview.model.refresh()

        # refresh MQ widget if exists
        if hasattr(self, 'mqwidget'):
            self.mqwidget.refresh()

        # refresh pbranch widget if exists
        if hasattr(self, 'pbranchwidget'):
            self.pbranchwidget.refresh()

        # force a redraw of the visible rows
        self.graphview.hide()
        self.graphview.show()

    def reload_log(self, **kwopts):
        'Send refresh event to treeview object'
        self.update_hide_merges_button()
        self.changeview.clear_cache()

        opts = {'date': None, 'no_merges':False, 'only_merges':False,
                'keyword':[], 'branch':None, 'pats':[], 'filehist':None,
                'revrange':[], 'revlist':[], 'noheads':False,
                'branch-view':False, 'rev':[], 'user':[]}
        if self.filteropts and not kwopts: opts = self.filteropts
        opts.update(kwopts)

        # handle strips, rebases, etc
        self.origtip = min(len(self.repo), self.origtip)
        if not self.bfile:
            self.npreviews = 0
        
        opts['branch-view'] = self.compactgraph
        opts['outgoing'] = self.outgoing
        opts['orig-tip'] = self.origtip
        opts['npreviews'] = self.npreviews
        opts['no_merges'] = self.no_merges

        self.cmd_set_sensitive('load-more', len(self.repo)>0)
        self.cmd_set_sensitive('load-all', len(self.repo)>0)
        self.sttool.set_enable('load', len(self.repo)>0)
        self.filterbar.get_button('ancestry').set_sensitive(False)
        self.menuitems['ancestry'].set_sensitive(False)
        pats = opts.get('pats', [])
        self.changeview.pats = pats
        self.pats = pats
        self.lastrevid = None

        def ftitle(filtername):
            t = self.get_title()
            if filtername is not None:
                t = t + ' - ' + filtername
            self.set_title(t)

        if self.filter != 'custom':
            self.filterentry.set_text('')

        graphcol = self.graphcol
        if self.no_merges:
            graphcol = False

        filterprefix = _('Filter') 
        filtertext = filterprefix + ': '
        if self.filter == 'branch':
            branch = opts.get('branch', None)
            self.graphview.refresh(graphcol, None, opts)
            ftitle(_('%s branch') % branch)
            filtertext += _("Branch '%s'") % branch
        elif self.filter == 'custom':
            npats = hglib.normpats(pats)
            if len(npats) == 1:
                kind, name = match._patsplit(npats[0], None)
                if kind == 'path' and not os.path.isdir(name):
                    ftitle(_('file patterns "%s"') % hglib.toutf(name))
                    opts['filehist'] = name
                    self.graphview.refresh(graphcol, [name], opts)
            if not opts.get('filehist'):
                ftitle('%s "%s"' % (self.filtercombo.get_active_text(),
                                    self.filterentry.get_text()))
                self.graphview.refresh(False, npats, opts)
            filtertext += self.filtercombo.get_active_text()
        elif self.filter == 'all':
            ftitle(None)
            self.graphview.refresh(graphcol, None, opts)
            filtertext = ''
        elif self.filter == 'only_merges':
            ftitle(_('merges'))
            opts['only_merges'] = True
            self.graphview.refresh(False, [], opts)
            filtertext += _('only Merges')
        elif self.filter == 'ancestry':
            ftitle(_('revision ancestry'))
            range = [self.currevid, 0]
            opts['noheads'] = True
            opts['revrange'] = range
            self.graphview.refresh(graphcol, None, opts)
            filtertext += _("Ancestry of %s") % self.currevid
        elif self.filter == 'tagged':
            ftitle(_('tagged revisions'))
            tagged = []
            for t, r in self.repo.tagslist():
                hr = self.repo[r].rev()
                if hr not in tagged:
                    tagged.insert(0, hr)
            opts['revlist'] = tagged
            self.graphview.refresh(False, [], opts)
            filtertext += _("Tagged Revisions")
        elif self.filter == 'parents':
            ftitle(_('working parents'))
            repo_parents = [x.rev() for x in self.repo.parents()]
            opts['revlist'] = [str(x) for x in repo_parents]
            self.graphview.refresh(False, [], opts)
            filtertext += _("Parents")
        elif self.filter == 'heads':
            ftitle(_('heads'))
            heads = hglib.getlivebheads(self.repo)
            opts['revlist'] = [str(x) for x in heads]
            self.graphview.refresh(False, [], opts)
            filtertext += _("Heads")

        nomergestext = _('no Merges')
        if self.no_merges:
            if filtertext:
                filtertext += ', %s' % nomergestext
            else:
                filtertext = '%s: %s' % (filterprefix, nomergestext)

        self.stbar.set_text(filtertext, name='filter')

        # refresh MQ widget if exists
        if hasattr(self, 'mqwidget'):
            self.mqwidget.refresh()
            # update status messages
            mq_text = None
            ntotal = self.mqwidget.get_num_patches()
            if ntotal > 0:
                ncount = self.mqwidget.get_num_applied()
                mq_text = ''
                if ncount > 0:
                    mq_text += _('Current patch: %s,  ') % \
                                 self.mqwidget.get_qtip_patchname()
                mq_text += _('%(count)d of %(total)d applied patches') % {
                             'count': ncount, 'total': ntotal}
            self.stbar.set_text(mq_text, name='mq')

        # refresh filterbar
        self.filterbar.refresh(hglib.getlivebranch(self.repo))

        # refresh pbranch widget if exists
        if hasattr(self, 'pbranchwidget'):
            self.pbranchwidget.refresh()

        # Remember options to next time reload_log is called
        self.filteropts = opts

    def tree_context_menu(self):
        m = gtklib.MenuBuilder()
        m.append(_('Visualize Change'), self.vdiff_change,
                 gtk.STOCK_JUSTIFY_FILL)
        m.append(_('Di_splay Change'), self.show_status)
        m.append(_('Diff to Local'), self.vdiff_local)
        m.append_sep()
        m.append(_('_Copy Hash'), self.copy_hash, gtk.STOCK_COPY)
        if self.bfile:
            if self.currevid >= len(self.repo) - self.npreviews:
                m.append_sep()
                m.append(_('Pull to Here'), self.pull_to,
                         gtk.STOCK_GOTO_BOTTOM)
            menu = m.build()
            menu.show_all()
            return menu

        if self.repo[self.currevid].node() in self.outgoing:
            m.append_sep()
            m.append(_('Push to Here'), self.push_to, gtk.STOCK_GOTO_TOP)
            m.append(_('Push this Branch'), self.push_branch, gtk.STOCK_GOTO_TOP)
        m.append_sep()
        m.append(_('_Update...'), self.checkout, 'menucheckout.ico')
        mmerge = m.append(_('_Merge with...'), self.domerge, 'menumerge.ico')
        mbackout = m.append(_('Backout...'), self.backout_rev, gtk.STOCK_UNDO)
        m.append(_('_Revert'), self.revert, gtk.STOCK_MEDIA_REWIND)
        m.append_sep()
        m.append_submenu(_('Export'), self.export_context_menu(), gtk.STOCK_GO_FORWARD)
        m.append_sep()
        m.append_submenu(_('Tag'), self.tags_context_menu(), gtk.STOCK_ITALIC)
        m.append_sep()

        # disable/enable menus as required
        parents = self.repo.parents()

        if len(parents) > 1:
            can_merge = False
            can_backout = False
        else:
            pctx = parents[0]
            cctx = self.repo[self.currevid]
            actx = cctx.ancestor(pctx)
            can_merge = actx != pctx or pctx.branch() != cctx.branch()
            can_backout = actx == cctx
        mmerge.set_sensitive(can_merge)
        mbackout.set_sensitive(can_backout)

        # need mq extension for strip command
        if 'mq' in self.exs:
            m.append_submenu(_('Mercurial Queues'), self.mq_context_menu(),
                             'menupatch.ico')

        # need transplant extension for transplant command
        if 'transplant' in self.exs:
            m.append(_('Transp_lant to Local'), self.transplant_rev,
                     gtk.STOCK_CONVERT)

        m.append_sep()
        m.append_submenu(_('Bisect'), self.bisect_context_menu(),
                         gtk.STOCK_FIND)
        menu = m.build()
        menu.show_all()
        return menu

    def export_context_menu(self):
        m = gtklib.MenuBuilder() 
        m.append(_('_Export Patch...'), self.export_patch, 'menupatch.ico')
        m.append(_('E_mail Patch...'), self.email_patch, gtk.STOCK_GOTO_LAST)
        m.append(_('_Bundle rev:tip...'), self.bundle_rev_to_tip,
                 'menurelocate.ico')
        m.append(_('_Archive...'), self.archive, gtk.STOCK_SAVE)
        return m.build()

    def tags_context_menu(self):
        m = gtklib.MenuBuilder() 
        m.append(_('Add/Remove _Tag...'), self.add_tag)
        if 'bookmarks' in self.exs:
            m.append(_('Add/Move/Remove B_ookmark...'), self.add_bookmark)
            m.append(_('Rename Bookmark...'), self.rename_bookmark,
                     gtk.STOCK_EDIT)
            if self.repo.ui.configbool('bookmarks', 'track.current'):
                m.append(_('Set Current Bookmark...'), self.current_bookmark,
                         gtk.STOCK_YES)
        return m.build()

    def mq_context_menu(self):
        m = gtklib.MenuBuilder() 
        mqimport = m.append(_('Import Revision to MQ'), self.qimport_rev,
                            'menuimport.ico')
        mstrip = m.append(_('Strip Revision...'), self.strip_rev,
                          'menudelete.ico')
        m.append_sep()

        try:
            ctx = self.repo[self.currevid]
            qbase = self.repo['qbase']
            actx = ctx.ancestor(qbase)
            if self.repo['qparent'] == ctx:
                mqimport.set_sensitive(True)
                mstrip.set_sensitive(False)
            elif actx == qbase or actx == ctx:
                # we're in the mq revision range or the mq
                # is a descendant of us
                mqimport.set_sensitive(False)
                mstrip.set_sensitive(False)
        except:
            pass

        return m.build()

    def bisect_context_menu(self):
        m = gtklib.MenuBuilder() 
        m.append(_('Reset'), self.bisect_reset, gtk.STOCK_CLEAR)
        m.append(_('Mark as Good'), self.bisect_good, gtk.STOCK_YES)
        m.append(_('Mark as Bad'), self.bisect_bad, gtk.STOCK_NO)
        m.append(_('Skip Testing'), self.bisect_skip, gtk.STOCK_MEDIA_FORWARD)
        return m.build()

    def restore_single_sel(self, widget, *args):
        self.tree.get_selection().set_mode(gtk.SELECTION_SINGLE)
        if self.origsel:
            self.tree.get_selection().select_path(self.origsel)
        self.revrange = None

    def tree_diff_context_menu(self):
        m = gtklib.MenuBuilder()
        m.append(_('_Diff with selected'), self.diff_revs)
        m.append(_('Visual Diff with selected'), self.vdiff_selected,
                 gtk.STOCK_JUSTIFY_FILL)
        if self.bfile:
            menu = m.build()
            menu.connect_after('selection-done', self.restore_single_sel)
            menu.show_all()
            return menu

        m.append_sep()
        m.append(_('Email from here to selected...'), self.email_revs,
                 gtk.STOCK_GOTO_LAST)
        m.append(_('Bundle from here to selected...'), self.bundle_revs,
                 'menurelocate.ico')
        m.append(_('Export Patches from here to selected...'),
                 self.export_revs, gtk.STOCK_GO_FORWARD)
        m.append_sep()
        mmerge = m.append(_('_Merge with...'), self.domerge, 'menumerge.ico')
        m.append_sep()
        
        # disable/enable menus as required
        parents = self.repo.parents()
        if len(parents) > 1:
            can_merge = False
        else:
            rev0, rev1 = self.revrange
            c0, c1 = self.repo[rev0], self.repo[rev1]
            can_merge = c0.branch() != c1.branch() or c0.ancestor(c1) != c1
        mmerge.set_sensitive(can_merge)

        # need transplant extension for transplant command
        if 'transplant' in self.exs:
            m.append(_('Transplant Revision range to local'),
                     self.transplant_revs, gtk.STOCK_CONVERT)

        # need rebase extension for rebase command
        if 'rebase' in self.exs:
            m.append(_('Rebase on top of selected'), self.rebase_selected,
                     gtk.STOCK_CUT)
        
        # need MQ extension for qimport command
        if 'mq' in self.exs:
            m.append(_('Import from here to selected to MQ'),
                     self.qimport_revs, 'menuimport.ico')

        m.append_sep()
        m.append(_('Select common ancestor revision'),
                 self.select_common_ancestor, gtk.STOCK_JUMP_TO)

        menu = m.build()
        menu.connect_after('selection-done', self.restore_single_sel)
        menu.show_all()
        return menu

    def get_body(self):
        self.connect('delete-event', self.delete)
        self.gorev_dialog = None
        self.limit = self.get_graphlimit(None)

        # prepare statusbar
        self.stbar = statusbar.StatusBar()
        self.stbar.append_field('mq')
        self.stbar.append_field('pbranch')
        self.stbar.append_field('filter')
        self.stbar.append_field('rev')

        ## add load buttons to statusbar
        self.sttool = gtklib.SlimToolbar(self.tooltips)
        self.stbar.append_widget(self.sttool)
        more = self.sttool.append_button(gtk.STOCK_GO_DOWN,
                           _('Load more Revisions'), group='load')
        more.connect('clicked', self.more_clicked)
        all = self.sttool.append_button(gtk.STOCK_GOTO_BOTTOM,
                          _('Load all Revisions'), group='load')
        all.connect('clicked', self.load_all_clicked)
        self.sttool.set_visible('load', not self.show_toolbar)

        # Allocate TreeView instance to use internally
        limit = self.limit
        if self.opts['limit']:
            limit = self.get_graphlimit(self.opts['limit'])
        self.graphview = LogTreeView(self.repo, limit, self.stbar)

        # dnd setup for TreeView
        targets = [('text/uri-list', 0, HIST_DND_URI_LIST)]
        self.graphview.drag_dest_set(gtk.DEST_DEFAULT_MOTION | \
             gtk.DEST_DEFAULT_DROP, targets, gtk.gdk.ACTION_MOVE)
        self.graphview.connect('drag-data-received', self.dnd_received,
                               DND_DEST_GRAPHVIEW)

        # Allocate ChangeSet instance to use internally
        self.changeview = changeset.ChangeSet(self.ui, self.repo, self.cwd, [],
                self.opts, self.stbar)
        self.changeview.display(False)
        self.changeview.glog_parent = self

        # Add extra toolbar buttons
        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)
        loadnext = self.make_toolbutton(gtk.STOCK_GO_DOWN,
            _('Load more'), self.more_clicked, tip=_('load more revisions'),
            name='load-more')
        loadall = self.make_toolbutton(gtk.STOCK_GOTO_BOTTOM,
            _('Load all'), self.load_all_clicked, tip=_('load all revisions'),
            name='load-all')

        tbar = self.changeview.get_tbbuttons()
        tbar += [sep, loadnext, loadall]
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

        refresh = syncbox.append_button(gtk.STOCK_REFRESH,
                        _('Reload revision history'), group='reload')
        syncbox.append_separator(group='reload')
        incoming = syncbox.append_button(gtk.STOCK_GO_DOWN,
                        _('Download and view incoming changesets'))
        apply = syncbox.append_button(gtk.STOCK_APPLY,
                        _('Accept changes from Bundle preview'),
                        group='bundle')
        reject = syncbox.append_button(gtk.STOCK_DIALOG_ERROR,
                        _('Reject changes from Bundle preview'),
                        group='bundle')
        pull = syncbox.append_button(gtk.STOCK_GOTO_BOTTOM,
                        _('Pull incoming changesets'))
        importbtn = syncbox.append_button('menuimport.ico',
                        _('Import patches'))
        syncbox.append_separator()
        outgoing = syncbox.append_button(gtk.STOCK_GO_UP,
                        _('Determine and mark outgoing changesets'))
        push = syncbox.append_button(gtk.STOCK_GOTO_TOP,
                        _('Push outgoing changesets'))
        email = syncbox.append_button(gtk.STOCK_GOTO_LAST,
                        _('Email outgoing changesets'))
        syncbox.append_separator(group='stop')
        stop = syncbox.append_button(gtk.STOCK_STOP,
                        _('Stop current transaction'), group='stop')

        syncbox.set_visible('reload', not self.show_toolbar)
        syncbox.set_enable('bundle', False)
        syncbox.set_enable('stop', False)

        self.syncbar_apply = apply
        self.syncbar_reject = reject
        self.stop_button = stop

        ## target path combobox
        urllist = gtk.ListStore(str, # path (utf-8)
                                str) # alias (utf-8)
        urlcombo = gtk.ComboBoxEntry(urllist, 0)
        cell = gtk.CellRendererText()
        urlcombo.pack_end(cell, False)
        urlcombo.add_attribute(cell, 'text', 1)
        self.urlcombo = urlcombo
        self.pathentry = urlcombo.get_child()
        syncbox.append_widget(urlcombo, expand=True)

        ## dnd setup for path entry
        self.pathentry.drag_dest_set(gtk.DEST_DEFAULT_MOTION | \
             gtk.DEST_DEFAULT_DROP, targets, gtk.gdk.ACTION_MOVE)
        self.pathentry.connect('drag-data-received', self.dnd_received,
                               DND_DEST_PATHENTRY)

        self.update_urllist()

        ## post pull drop-down list
        ppullbox = gtk.HBox()
        syncbox.append_widget(ppullbox)
        ppullbox.pack_start(gtk.Label(_('After Pull:')), False, False, 4)
        ppulldata = [('none', _('Nothing')), ('update', _('Update'))]
        ppull = self.repo.ui.config('tortoisehg', 'postpull', 'none')
        if 'fetch' in self.exs or 'fetch' == ppull:
            ppulldata.append(('fetch', _('Fetch')))
        if 'rebase' in self.exs or 'rebase' == ppull:
            ppulldata.append(('rebase', _('Rebase')))

        ppulllist = gtk.ListStore(str, # name
                                  str) # label (utf-8)
        ppullcombo = gtk.ComboBox(ppulllist)
        ppullbox.pack_start(ppullcombo, False, False)
        cell = gtk.CellRendererText()
        ppullcombo.pack_start(cell)
        ppullcombo.add_attribute(cell, 'text', 1)
        for name, label in ppulldata:
            ppulllist.append((name, label))
        self.ppullcombo = ppullcombo
        self.ppulldata = ppulldata
        self.ppullbox = ppullbox

        self.update_postpull(ppull)

        ## add conf button
        conf = syncbox.append_button(gtk.STOCK_PREFERENCES,
                        _('Configure aliases and after pull behavior'))

        ## connect syncbar buttons
        refresh.connect('clicked', self.refresh_clicked)
        incoming.connect('clicked', self.incoming_clicked)
        pull.connect('clicked', self.pull_clicked)
        importbtn.connect('clicked', self.import_clicked)
        outgoing.connect('clicked', self.outgoing_clicked)
        push.connect('clicked', self.push_clicked)
        apply.connect('clicked', self.apply_clicked)
        reject.connect('clicked', self.reject_clicked)
        conf.connect('clicked', self.conf_clicked)
        email.connect('clicked', self.email_clicked)
        stop.connect('clicked', self.stop_clicked)

        # filter bar
        self.filterbar = FilterBar(self.tooltips,
                                   self.filter_mode, 
                                   hglib.getlivebranch(self.repo),
                                   self.repo)
        filterbar = self.filterbar
        self.lastbranchrow = None
        self.lastfilterinfo = None
        self.filter_mode = filterbar.filter_mode
        self.filtercombo = filterbar.filtercombo
        self.filterentry = filterbar.entry
        self.branchcombo = filterbar.branchcombo
        self.entrycombo = filterbar.entrycombo

        fcon = self.filterbar.connect
        fsel = self.filter_selected
        fcon('all_toggled', fsel, 'all')
        fcon('tagged_toggled', fsel, 'tagged')
        fcon('ancestry_toggled', fsel, 'ancestry')
        fcon('parents_toggled', fsel, 'parents')
        fcon('heads_toggled', fsel, 'heads')
        fcon('merges_toggled', fsel, 'only_merges')
        fcon('hidemerges_toggled', fsel, 'no_merges')
        fcon('branches_toggled', fsel, 'branch')
        fcon('branchcombo_changed', self.select_branch)
        fcon('entry_activate', self.filter_entry_activated, self.filtercombo)
        fcon('entrycombo_changed', self.filter_entry_changed, self.filtercombo)

        midpane = gtk.VBox()
        midpane.pack_start(syncbox, False)
        midpane.pack_start(filterbar, False)
        midpane.pack_start(self.graphview)
        midpane.show_all()

        # pbranch widget
        if 'pbranch' in self.exs:
            # create PBranchWidget
            self.pbranchwidget = thgpbranch.PBranchWidget(
                self, self.repo, self.stbar, accelgroup, self.tooltips)
            self.pbranchwidget.connect('patch-selected', self.pbranch_selected)
            self.pbranchwidget.connect('repo-invalidated', self.repo_invalidated)

            def wrapframe(widget):
                frame = gtk.Frame()
                frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
                frame.add(widget)
                return frame
            self.pbranchpaned = gtk.HPaned()
            self.pbranchpaned.add1(wrapframe(self.pbranchwidget))
            self.pbranchpaned.add2(wrapframe(midpane))

            midpane = self.pbranchpaned

        # MQ widget
        if 'mq' in self.exs:
            # create MQWidget
            self.mqwidget = thgmq.MQWidget(self.repo,
                                           accelgroup, self.tooltips)
            self.mqwidget.connect('patch-selected', self.patch_selected)
            self.mqwidget.connect('repo-invalidated', self.repo_invalidated)
            self.mqwidget.connect('files-dropped', self.files_dropped)
            self.mqwidget.connect('close-mq', lambda *a: self.enable_mqpanel(False))

            def wrapframe(widget):
                frame = gtk.Frame()
                frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
                frame.add(widget)
                return frame
            self.mqpaned = gtk.HPaned()
            self.mqpaned.add1(wrapframe(self.mqwidget))
            self.mqpaned.add2(wrapframe(midpane))

            # register signal handler
            def notify(paned, gparam):
                if not hasattr(self, 'mqtb'):
                    return
                pos = paned.get_position()
                if self.cmd_get_active('mq'):
                    if pos < 140:
                        paned.set_position(140)
                else:
                    if pos != 0:
                        paned.set_position(0)
            self.mqpaned.connect('notify::position', notify)

            midpane = self.mqpaned

        # Add ChangeSet instance to bottom half of vpane
        self.changeview.graphview = self.graphview
        self.hpaned = self.changeview.get_body()

        self.vpaned = gtk.VPaned()
        self.vpaned.pack1(midpane, True, False)
        self.vpaned.pack2(self.hpaned)
        gtklib.idle_add_single_call(self.realize_settings)

        vbox = gtk.VBox()
        vbox.pack_start(self.vpaned, True, True)

        return vbox

    def get_extras(self):
        return self.stbar

    def refresh_on_marker_change(self, oldlen, oldmarkers, newmarkers):
        # Note that oldmarkers/newmarkers may be either dicts
        # (for add/remove bookmarks, which can also 'move'
        # bookmarks), or lists (everything else)
        self.repo.invalidate()
        self.changeview.clear_cache()
        if len(self.repo) != oldlen:
            self.reload_log()
        else:
            if newmarkers != oldmarkers:
                self.refresh_model()

    def refresh_on_current_marker_change(self, oldlen, oldmarkers,
                                         oldcurrent, newmarkers,
                                         newcurrent):
        self.repo.invalidate()
        self.changeview.clear_cache()
        if len(self.repo) != oldlen:
            self.reload_log()
        else:
            if newmarkers != oldmarkers or \
                oldcurrent != newcurrent:
                self.refresh_model()

    def apply_clicked(self, button):
        combo = self.ppullcombo
        list, iter = combo.get_model(), combo.get_active_iter()
        ppull, label = list[list.get_path(iter)]
        if ppull == 'fetch':
            cmd = ['fetch', '--message', 'merge']
            # load the fetch extension explicitly
            hglib.loadextension(self.ui, 'fetch')
        else:
            cmd = ['pull']
            if ppull == 'update':
                cmd.append('--update')
            elif ppull == 'rebase':
                cmd.append('--rebase')
                # load the rebase extension explicitly
                hglib.loadextension(self.ui, 'rebase')

        cmdline = ['hg'] + cmd + ['--', self.bfile]

        def callback(return_code, *args):
            self.remove_overlay('--rebase' in cmd)

        if not self.execute_command(cmdline, callback,
                    status=_('Applying bundle...'),
                    title=_('Applying bundle')):
            gdialog.Prompt(_('Cannot run now'),
                           _('Please try again after the previous '
                             'command has completed'), self).run()

    def remove_overlay(self, resettip):
        self.bfile = None
        self.npreviews = 0
        if isinstance(self.origurl, int):
            self.urlcombo.set_active(self.origurl)
        else:
            self.pathentry.set_text(self.origurl)
        self.repo = hg.repository(self.ui, path=self.repo.root)
        self.graphview.set_repo(self.repo, self.stbar)
        self.changeview.set_repo(self.repo)
        self.changeview.bfile = None
        if hasattr(self, 'mqwidget'):
            self.mqwidget.set_repo(self.repo)
            self.mqwidget.set_sensitive(True)
        if resettip:
            self.origtip = len(self.repo)
        self.reload_log()
        self.toolbar.remove(self.toolbar.get_nth_item(0))
        self.toolbar.remove(self.toolbar.get_nth_item(0))
        self.cmd_set_sensitive('accept', False)
        self.cmd_set_sensitive('reject', False)
        self.syncbox.set_enable('bundle', False)
        for w in self.incoming_disabled:
            w.set_sensitive(True)
        for cmd in self.incoming_disabled_cmds:
            self.cmd_set_sensitive(cmd, True)
        self.stbar.set_idle_text(None)

    def reject_clicked(self, button):
        self.remove_overlay(False)

    def incoming_clicked(self, toolbutton):
        def cleanup():
            try:
                shutil.rmtree(self.bundledir)
            except OSError:
                pass

        path = hglib.fromutf(self.pathentry.get_text()).strip()
        if not path:
            gdialog.Prompt(_('No remote path specified'),
                           _('Please enter or select a remote path'),
                           self).run()
            self.pathentry.grab_focus()
            return
        if path.startswith('p4://'):
            cmdline = ['hg', 'incoming', '--verbose', path]
            self.execute_command(cmdline, force=True)
            return
        if not self.bundledir:
            self.bundledir = tempfile.mkdtemp(prefix='thg-incoming-')
            atexit.register(cleanup)

        bfile = path
        for badchar in (':', '*', '\\', '?', '#'):
            bfile = bfile.replace(badchar, '')
        bfile = bfile.replace('/', '_')
        bfile = os.path.join(self.bundledir, bfile) + '.hg'
        cmdline = ['hg', 'incoming']
        if self.forcesync:
            cmdline += ['--force']
        cmdline += ['--bundle', bfile]
        cmdline += self.get_proxy_args()
        cmdline += [hglib.validate_synch_path(path, self.repo)]

        def callback(return_code, *args):
            if return_code == 0 and os.path.isfile(bfile):
                self.set_bundlefile(bfile)
                text = _('%d incoming changesets') % self.npreviews
            elif return_code is None:
                text = _('Aborted incoming')
            else:
                text = _('No incoming changesets')
            self.stbar.set_idle_text(text)

        if not self.execute_command(cmdline, callback,
                    status=_('Checking incoming changesets...'),
                    title=_('Incoming')):
            gdialog.Prompt(_('Cannot run now'),
                           _('Please try again after the previous '
                             'command has completed'), self).run()

    def set_bundlefile(self, bfile, **kwopts):
        self.origurl = self.urlcombo.get_active()
        if self.origurl == -1:
            self.origurl = self.pathentry.get_text()
        self.pathentry.set_text(bfile)

        # disable MQ panel
        if hasattr(self, 'mqwidget'):
            self.mqwidget.set_sensitive(False)

        # create apply/reject toolbar buttons
        apply = gtk.ToolButton(gtk.STOCK_APPLY)
        self.tooltips.set_tip(apply,
                          _('Accept incoming previewed changesets'))
        apply.set_label(_('Accept'))
        apply.show()

        reject = gtk.ToolButton(gtk.STOCK_DIALOG_ERROR)
        self.tooltips.set_tip(reject,
                           _('Reject incoming previewed changesets'))
        reject.set_label(_('Reject'))
        reject.show()

        apply.connect('clicked', self.apply_clicked)
        reject.connect('clicked', self.reject_clicked)

        self.toolbar.insert(reject, 0)
        self.toolbar.insert(apply, 0)
        
        self.cmd_set_sensitive('accept', True)
        self.cmd_set_sensitive('reject', True)

        cmds = ('incoming', 'outgoing', 'push', 'pull', 'email', 'refresh',
                'synchronize', 'mq', 'add-bundle')
        self.incoming_disabled_cmds = []
        for cmd in cmds:
            self.cmd_set_sensitive(cmd, False)
            self.incoming_disabled_cmds.append(cmd)

        ignore = (self.syncbar_apply, self.syncbar_reject, self.ppullbox,
                  self.stop_button)
        self.incoming_disabled = []
        def disable_child(w):
            if (w not in ignore) and w.get_property('sensitive'):
                w.set_sensitive(False)
                self.incoming_disabled.append(w)
        self.syncbox.foreach(disable_child)

        self.syncbox.set_enable('bundle', True)

        self.bfile = bfile
        oldtip = len(self.repo)
        try:
            self.repo = hg.repository(self.ui, path=bfile)
            self.graphview.set_repo(self.repo, self.stbar)
            self.changeview.set_repo(self.repo)
            self.changeview.bfile = bfile
            if hasattr(self, 'mqwidget'):
                self.mqwidget.set_repo(self.repo)
            self.npreviews = len(self.repo) - oldtip
            self.reload_log(**kwopts)

            self.stbar.set_idle_text(_('Bundle Preview'))
            self.bundle_autoreject = False
        except error.LookupError:
            self.remove_overlay(False)
            gtklib.idle_add_single_call(self.stbar.set_idle_text,
                   _('Failed to preview, a bundle file unrelated '
                     'to this repository'))
        except error.Abort:
            self.remove_overlay(False)
            gtklib.idle_add_single_call(self.stbar.set_idle_text,
                   _('Failed to preview, not a Mercurial bundle file'))

    def add_bundle_clicked(self, button):
        result = gtklib.NativeSaveFileDialogWrapper(
            title=_('Open Bundle'), open=True).run()
        if result:
            self.set_bundlefile(result)

    def pull_clicked(self, toolbutton):
        combo = self.ppullcombo
        list, iter = combo.get_model(), combo.get_active_iter()
        ppull, label = list[list.get_path(iter)]
        if ppull == 'fetch':
            cmd = ['fetch', '--message', 'merge']
            # load the fetch extension explicitly
            hglib.loadextension(self.ui, 'fetch')
        else:
            cmd = ['pull']
            if ppull == 'update':
                cmd.append('--update')
            elif ppull == 'rebase':
                cmd.append('--rebase')
                # load the rebase extension explicitly
                hglib.loadextension(self.ui, 'rebase')

        path = hglib.fromutf(self.pathentry.get_text()).strip()
        remote_path = hglib.validate_synch_path(path, self.repo)
        if not path:
            gdialog.Prompt(_('No remote path specified'),
                           _('Please enter or select a remote path'),
                           self).run()
            self.pathentry.grab_focus()
            return
        cmdline = ['hg'] + cmd + self.get_proxy_args() + ['--', remote_path]

        def callback(return_code, *args):
            if return_code == 0:
                self.repo.invalidate()
                self.changeview.clear_cache()
                if '--rebase' in cmd:
                    self.origtip = len(self.repo)
                    self.reload_log()
                    text = _('Finished pull with rebase')
                elif len(self.repo) > self.origtip:
                    self.reload_log()
                    text = _('Finished pull')
                else:
                    text = _('No changesets to pull')
            else:
                text = _('Aborted pull')
            self.stbar.set_idle_text(text)
        if not self.execute_command(cmdline, callback,
                    status=_('Pulling changesets...'),
                    title=_('Pull')):
            gdialog.Prompt(_('Cannot run now'),
                           _('Please try again after the previous '
                             'command has completed'), self).run()

    def outgoing_clicked(self, toolbutton):
        path = hglib.fromutf(self.pathentry.get_text()).strip()
        if not path:
            gdialog.Prompt(_('No remote path specified'),
                           _('Please enter or select a remote path'),
                           self).run()
            self.pathentry.grab_focus()
            return
        cmd = ['hg', 'outgoing']
        if self.forcesync:
            cmd += ['--force']
        if path.startswith('p4://'):
            # hg out -q p4://server/client output hashes (thanks Frank)
            cmd += ['--quiet', path]
        else:
            cmd += ['--quiet', '--template', '{node}\n']
            cmd += self.get_proxy_args()
            cmd += [hglib.validate_synch_path(path, self.repo)] 

        def callback(return_code, buffer, *args):
            if return_code == 0:
                outgoing = []
                for line in buffer.splitlines()[:-1]:
                    try:
                        node = self.repo[line].node()
                        outgoing.append(node)
                    except:
                        pass
                self.outgoing = outgoing
                self.reload_log()
                text = _('%d outgoing changesets') % len(outgoing)
            elif return_code is None:
                text = _('Aborted outgoing')
            else:
                text = _('No outgoing changesets')
            self.stbar.set_idle_text(text)
        if not self.execute_command(cmd, callback,
                    status=_('Checking outgoing changesets...'),
                    title=_('Outgoing')):
            gdialog.Prompt(_('Cannot run now'),
                           _('Please try again after the previous '
                             'command has completed'), self).run()

    def email_clicked(self, toolbutton):
        path = hglib.fromutf(self.pathentry.get_text()).strip()
        if not path:
            gdialog.Prompt(_('No repository selected'),
                           _('Select a peer repository to compare with'),
                           self).run()
            self.pathentry.grab_focus()
            return
        opts = ['--outgoing', path]
        dlg = hgemail.EmailDialog(self.repo.root, opts)
        self.show_dialog(dlg)

    def push_clicked(self, toolbutton):
        remote_path = self.validate_path()
        if not remote_path:
            return

        cmdline = ['hg', 'push'] + self.get_proxy_args()
        if self.forcesync:
            cmdline += ['--force']
        elif self.newbranch:
            cmdline += ['--new-branch']
        cmdline += ['--', remote_path]

        def callback(return_code, *args):
            if return_code == 0:
                if self.outgoing:
                    self.outgoing = []
                    self.reload_log()
                text = _('Finished push')
            else:
                text = _('Aborted push')
            self.stbar.set_idle_text(text)
        if not self.execute_command(cmdline, callback,
                    status=_('Pushing changesets...'),
                    title=_('Push')):
            gdialog.Prompt(_('Cannot run now'),
                           _('Please try again after the previous '
                             'command has completed'), self).run()

    def conf_clicked(self, *args):
        newpath = hglib.fromutf(self.pathentry.get_text()).strip()
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
        self.update_urllist()
        self.update_postpull()

    def stop_clicked(self, toolbutton):
        self.runner.stop()

    def import_clicked(self, widget, dest=thgimport.DEST_REPO, paths=None):
        oldlen = len(self.repo)
        enabled = hasattr(self, 'mqpaned')
        if enabled:
            oldnum = self.mqwidget.get_num_patches()
        def import_completed():
            hglib.invalidaterepo(self.repo)
            self.changeview.clear()
            if oldlen < len(self.repo):
                self.reload_log()
            if enabled and oldnum < self.mqwidget.get_num_patches():
                self.mqwidget.refresh()
                self.enable_mqpanel(enable=True)
        dialog = thgimport.ImportDialog(self.repo, dest, paths)
        dialog.set_notify_func(import_completed)
        self.show_dialog(dialog)

    def update_urllist(self):
        if self.bfile:
            return

        # save current selection & default path
        oldurl = self.pathentry.get_text()
        urllist = self.urlcombo.get_model()
        for path, alias in urllist:
            if alias == 'default':
                defurl = path
                break
        else:
            defurl = None

        # update URL list
        urllist.clear()
        new_defurl = None
        for alias, path in self.repo.ui.configitems('paths'):
            path = url.hidepassword(path)
            urllist.append((hglib.toutf(path), hglib.toutf(alias)))
            if alias == 'default':
                self.urlcombo.set_active(len(urllist) - 1)
                new_defurl = path

        # restore previous selection
        if oldurl and defurl == new_defurl:
            for row in urllist:
                path, alias = row
                if oldurl == path:
                    self.urlcombo.set_active_iter(row.iter)
                    break
            else:
                self.pathentry.set_text(oldurl)

    def update_postpull(self, ppull=None):
        if ppull is None:
            ppull = self.repo.ui.config('tortoisehg', 'postpull', 'none')
        for row in self.ppullcombo.get_model():
            name, label = row
            if name == ppull:
                self.ppullcombo.set_active_iter(row.iter)
                break

    def dnd_received(self, widget, context, x, y, sel, target, tm, dest):
        if target == HIST_DND_URI_LIST:
            paths = gtklib.normalize_dnd_paths(sel.data)
            if not paths:
                return
            if dest == DND_DEST_PATHENTRY:
                path = paths[0] # use only first path
                if os.path.isfile(path):
                    self.set_bundlefile(path)
                else:
                    self.pathentry.set_text(path)

                # HACK: I don't know why, but 'drag-data-received' signal
                # is emitted twice: the former has correct dropped path,
                # the latter has previously dropped (old) path.  To avoid
                # overwriting with old one, I had to block dnd signal
                # right after this signal handler is called.
                widget.handler_block_by_func(self.dnd_received)
                def after():
                    widget.handler_unblock_by_func(self.dnd_received)
                gtklib.idle_add_single_call(after)
            elif dest == DND_DEST_GRAPHVIEW:
                self.import_clicked(None, thgimport.DEST_REPO, paths)
            else:
                raise _('unknown dnd dest: %s') % dest

    def realize_settings(self):
        self.vpaned.set_position(self.setting_vpos)
        self.hpaned.set_position(self.setting_hpos)
        if hasattr(self, 'mqpaned') and self.mqtb.get_active():
            self.mqpaned.set_position(self.setting_mqhpos)
        if hasattr(self, 'pbranchpaned') and self.pbranchtb.get_active():
            self.pbranchpaned.set_position(self.setting_pbranchhpos)

    def thgdiff(self, treeview):
        'ctrl-d handler'
        self.vdiff_change(None, self.pats)

    def thgparent(self, treeview):
        'ctrl-p handler'
        parent = self.repo['.'].rev()
        self.graphview.set_revision_id(parent)

    def thgnavigate(self, treeview):
        'ctrl-g handler'
        self.show_goto_dialog()

    def select_branch(self, combo):
        row = combo.get_active()
        if row == 0:
            if self.lastbranchrow:
                combo.set_active(self.lastbranchrow)
        elif row != self.lastbranchrow:
            self.filter = 'branch'
            self.lastbranchrow = row
            self.filterbar.get_button('branch').set_active(True)
            self.filterbar.get_button('branch').set_sensitive(True)
            self.reload_log(branch=combo.get_model()[row][0])

            bname = combo.get_active_text() # utf8 encoded
            menu = self.menuitems.get('@' + bname)
            if menu:
                menu.handler_block_by_func(self.filter_handler)
                menu.set_active(True)
                menu.handler_unblock_by_func(self.filter_handler)

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

    def goto_prev_sel(self):
        if hasattr(self, 'prevrevid') and self.prevrevid:
            self.goto_rev(self.prevrevid)

    def strip_rev(self, menuitem):
        def strip_completed():
            hglib.invalidaterepo(self.repo)
            self.reload_log()
            self.changeview.clear()
        rev = self.currevid
        dialog = thgstrip.StripDialog(rev, self.graphview)
        dialog.set_notify_func(strip_completed)
        self.show_dialog(dialog)

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

        def refresh(*args):
            self.repo.invalidate()
            self.changeview.clear_cache()
            if len(self.repo) != oldlen:
                self.reload_log()
            if len(self.repo.parents()) != len(parents):
                # User auto-merged the backout
                def cinotify():
                    'User comitted the merge'
                    dlg.ready = False
                    dlg.hide()
                    self.reload_log()
                from tortoisehg.hgtk import commit
                dlg = commit.run(ui.ui())
                dlg.set_transient_for(self)
                dlg.set_modal(True)
                dlg.set_notify_func(cinotify)
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
        self.execute_command(cmdline, force=True)

    def vdiff_change(self, menuitem, pats=[]):
        if self.currevid is None:
            return
        rev = self.currevid
        opts = {'change':str(rev), 'bundle':self.bfile}
        parents = self.repo[rev].parents()
        if len(parents) == 2:
            if self.changeview.diff_other_parent():
                parent = parents[1].rev()
            else:
                parent = parents[0].rev()
            opts['rev'] = [str(parent), str(rev)]
        self._do_diff(pats, opts)

    def vdiff_local(self, menuitem):
        opts = {'rev':[str(self.currevid)], 'bundle':self.bfile}
        self._do_diff(self.pats, {'rev' : [str(self.currevid)]})

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

    def bundle_rev_to_tip(self, menuitem):
        try:
            parent = self.repo[self.currevid].parents()[0].rev()
        except (ValueError, error.LookupError):
            return
        self.bundle_revs(menuitem, parent)

    def bundle_revs(self, menuitem, base=None):
        data = dict(name=os.path.basename(self.repo.root))
        if base is None:
            revrange = list(self.revrange)
            revrange.sort()
            parent = self.repo[revrange[0]].parents()[0].rev()
            data.update(base=revrange[0], rev=revrange[1])
            filename = '%(name)s_rev%(base)s_to_rev%(rev)s.hg' % data
        else:
            parent = base
            data.update(base=self.currevid)
            filename = '%(name)s_rev%(base)s_to_tip.hg' % data
        # Special case for revision 0's parent.
        if parent == -1: parent = 'null'

        result = gtklib.NativeSaveFileDialogWrapper(title=_('Write bundle to'),
                                                    initial=self.repo.root,
                                                    filename=filename).run()
        if not result:
            return

        parent = str(parent)
        cmdline = ['hg', 'bundle', '--base', parent]
        data = dict(base=parent)
        if base is None:
            rev = str(revrange[1])
            cmdline += ['--rev', rev]
            data.update(rev=rev)
            status = _('Bundling from %(base)s to %(rev)s...') % data
        else:
            status = _('Bundling from %(base)s to tip...') % data
        cmdline.append('--')
        cmdline.append(result)

        def callback(return_code, *args):
            if return_code == 0:
                text = _('Finish bundling')
            elif return_code is None:
                text = _('Aborted bundling')
            else:
                text = _('Failed to bundle')
            self.stbar.set_idle_text(text)
        if not self.execute_command(cmdline, callback, status, _('Bundling')):
            gdialog.Prompt(_('Cannot run now'),
                           _('Please try again after the previous '
                             'command has completed'), self).run()

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
        def callback(return_code, *args):
            if return_code == 0:
                hglib.invalidaterepo(self.repo)
                self.reload_log()
                self.changeview.clear()
                self.enable_mqpanel()
                text = _('Finish importing')
            elif return_code is None:
                text = _('Aborted importing')
            else:
                text = _('Failed to import')
            self.stbar.set_idle_text(text)
        if not self.execute_command(cmdline, callback, title=_('Importing'),
                                    status=_('Importing to Patch Queue...')):
            gdialog.Prompt(_('Cannot run now'),
                           _('Please try again after the previous '
                             'command has completed'), self).run()

    def rebase_selected(self, menuitem):
        """Rebase revision on top of selection (1st on top of 2nd).""" 
        revs = self.revrange
        res = gdialog.Confirm(_('Confirm Rebase Revision'), [], self,
            _('Rebase revision %d on top of %d?') % (revs[0], revs[1])).run()
        if res != gtk.RESPONSE_YES:
            return
        cmdline = ['hg', 'rebase', '--source', str(revs[0]),
                   '--dest', str(revs[1])]
        self.execute_command(cmdline, force=True)
        hglib.invalidaterepo(self.repo)
        self.reload_log()
        self.changeview.clear()

    def transplant_rev(self, menuitem):
        """Transplant selection on top of current revision."""
        rev = str(self.currevid)
        self.transplant_revs(menuitem, rev)

    def transplant_revs(self, menuitem, rev=None):
        """Transplant revision range on top of current revision."""
        if rev is None:
            revs = list(self.revrange)
            revs.sort()
            rev = '%d:%d' % (revs[0], revs[1])
        cmdline = ['hg', 'transplant', rev]
        self.execute_command(cmdline, force=True)
        self.repo.invalidate()
        self.reload_log()
        self.changeview.clear()

    def get_rev_tag(self, rev, include=None, exclude=None):
        for tag in self.repo.nodetags(self.repo[rev].node()):
            if tag != 'tip' \
                    and ((not include) or (include and tag in include)) \
                    and ((not exclude) or (exclude and tag not in exclude)):
                return tag
        return ''

    def add_tag(self, menuitem):
        # save tag info for detecting new tags added
        bmarks = hglib.get_repo_bookmarks(self.repo) 
        oldtags = self.repo.tagslist()
        oldlen = len(self.repo)
        rev = str(self.currevid)
        tag = self.get_rev_tag(rev, exclude=bmarks)

        def refresh(*args):
            self.refresh_on_marker_change(oldlen, oldtags,
                                          self.repo.tagslist())

        dialog = tagadd.TagAddDialog(self.repo, tag, rev)
        dialog.connect('destroy', refresh)
        self.show_dialog(dialog)

    def add_bookmark(self, menuitem):
        # save bookmark info for detecting new bookmarks added
        # since we can now move bookmarks, need to store
        # the associated changesets as well
        oldbookmarks = hglib.get_repo_bookmarks(self.repo, values=True)
        oldlen = len(self.repo)
        rev = str(self.currevid)
        bmark = self.get_rev_tag(rev, include=oldbookmarks)

        def refresh(*args):
            self.refresh_on_marker_change(oldlen, oldbookmarks,
                                          hglib.get_repo_bookmarks(self.repo,
                                                                   values=True))

        dialog = bookmark.BookmarkDialog(self.repo, bookmark.TYPE_ADDREMOVE,
                                         bmark, rev)
        dialog.connect('destroy', refresh)
        self.show_dialog(dialog)

    def rename_bookmark(self, menuitem):
        # save bookmark info for detecting bookmarks renamed
        oldbookmarks = hglib.get_repo_bookmarks(self.repo) 
        oldlen = len(self.repo)
        rev = str(self.currevid)
        bmark = self.get_rev_tag(rev, include=oldbookmarks)

        def refresh(*args):
            self.refresh_on_marker_change(oldlen, oldbookmarks,
                                          hglib.get_repo_bookmarks(self.repo))

        dialog = bookmark.BookmarkDialog(self.repo, bookmark.TYPE_RENAME,
                                         bmark, rev)
        dialog.connect('destroy', refresh)
        self.show_dialog(dialog)
        
    def current_bookmark(self, menuitem):
        # save current bookmark info for detecting current bookmark changed
        bookmarks = extensions.find('bookmarks')
        # Note that the dialog shouldn't change the repo len, or # of bookmarks,
        # etc, but check in case they've been modified by something else...
        oldbookmarks = hglib.get_repo_bookmarks(self.repo)
        oldlen = len(self.repo)
        oldcurrent = hglib.get_repo_bookmarkcurrent(self.repo)
        rev = str(self.currevid)
        bmark = self.get_rev_tag(rev, include=oldbookmarks)

        def refresh(*args):
            self.refresh_on_current_marker_change(oldlen, oldbookmarks, oldcurrent,
                                                  hglib.get_repo_bookmarks(self.repo),
                                                  hglib.get_repo_bookmarkcurrent(self.repo))

        dialog = bookmark.BookmarkDialog(self.repo, bookmark.TYPE_CURRENT,
                                         bmark, rev)
        dialog.connect('destroy', refresh)
        self.show_dialog(dialog)

    def bisect_reset(self, menuitem):
        commands.bisect(ui=self.ui,
                        repo=self.repo,
                        good=False,
                        bad=False,
                        skip=False,
                        reset=True)

    def run_bisect_step(self, cmd):
        '''run one bisect step and scroll to the new working copy parent'''
        self.execute_command(cmd, force=True)
        self.refresh_model()
        wcpar = [x.rev() for x in self.repo.parents()]
        # unless something weird happened, wc has one parent
        if len(wcpar) == 1:
            self.graphview.scroll_to_revision(wcpar[0])

    def bisect_good(self, menuitem):
        cmd = ['hg', 'bisect', '--good', str(self.currevid)]
        self.run_bisect_step(cmd)

    def bisect_bad(self, menuitem):
        cmd = ['hg', 'bisect', '--bad', str(self.currevid)]
        self.run_bisect_step(cmd)

    def bisect_skip(self, menuitem):
        cmd = ['hg', 'bisect', '--skip', str(self.currevid)]
        self.run_bisect_step(cmd)

    def show_status(self, menuitem):
        rev = self.currevid
        statopts = self.merge_opts(commands.table['^status|st'][1],
                ('include', 'exclude', 'git'))
        if self.changeview.diff_other_parent():
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

    def validate_path(self):
        original_path = hglib.fromutf(self.pathentry.get_text()).strip()
        remote_path = hglib.validate_synch_path(original_path, self.repo)
        if not remote_path:
            gdialog.Prompt(_('No remote path specified'),
                           _('Please enter or select a remote path'),
                           self).run()
            self.pathentry.grab_focus()
            return None
        else:
            confirm_push = False
            if not hg.islocal(remote_path):
                if self.forcesync:
                    title = _('Confirm Forced Push to Remote Repository')
                    text = _('Forced push to remote repository\n%s\n'
                             '(creating new heads in remote if needed)?') % original_path
                    buttontext = _('Forced &Push')
                elif self.newbranch:
                    title = _('Confirm Push of New Branches to Remote Repository')
                    text = _('Push to remote repository\n%s\n'
                             '(creating new branches in remote if needed)?') % original_path
                    buttontext = _('&Push')
                    confirm_push = True
                else:
                    title = _('Confirm Push to remote Repository')
                    text = _('Push to remote repository\n%s\n?') % original_path
                    buttontext = _('&Push')
                    confirm_push = True
            elif self.forcesync:
                title = _('Confirm Forced Push')
                text = _('Forced push to repository\n%s\n'
                         '(creating new heads if needed)?') % original_path
                buttontext = _('Forced &Push')
                confirm_push = True
            
            if confirm_push:
                dlg = gdialog.CustomPrompt(title, text,
                    None, (buttontext, _('&Cancel')), default=1, esc=1)
                if dlg.run() != 0:
                    return None
                else:
                    return remote_path
            else:
                return remote_path    

    def push_branch(self, menuitem):
        self.push_to(menuitem, branch=self.repo[self.currevid].branch())

    def push_to(self, menuitem, branch=None):
        remote_path = self.validate_path()
        if not remote_path:
            return
        
        node = self.repo[self.currevid].node()
        rev = str(self.currevid)
        if branch:
            cmdline = ['hg', 'push', '--new-branch', '--branch', branch]
        else:
            cmdline = ['hg', 'push', '--rev', rev]
            if self.forcesync:
                cmdline += ['--force']
            elif self.newbranch:
                cmdline += ['--new-branch']
        cmdline += ['--', remote_path]

        def callback(return_code, *args):
            if return_code == 0:
                text = _('Finished push to revision %s') % rev
                if branch:
                    remain = []
                    for n in self.outgoing:
                        if self.repo[n].branch() != branch:
                            remain.append(n)
                    self.outgoing = remain
                    self.reload_log()
                    text = _('Finished pushing branch %s') % branch
                elif self.outgoing:
                    ancestors = set([self.repo[node].rev()])
                    while ancestors:
                        n = self.repo[ancestors.pop()]
                        try:
                            d = self.outgoing.index(n.node())
                        except ValueError:
                            continue
                        del self.outgoing[d]
                        for p in n.parents():
                            ancestors.add(p.rev())
                    self.reload_log()
            else:
                text = _('Aborted push')
            self.stbar.set_idle_text(text)
        if branch:
            status = _('Pushing branch %s...') % branch
        else:
            status = _('Pushing changesets to revision %s...') % rev
        if not self.execute_command(cmdline, callback, status=status,
                    title=_('Push to %s') % rev):
            gdialog.Prompt(_('Cannot run now'),
                           _('Please try again after the previous '
                             'command has completed'), self).run()

    def pull_to(self, menuitem):
        rev = str(self.currevid)
        cmdline = ['hg', 'pull']
        if self.forcesync:
            cmdline += ['--force']
        cmdline += ['--rev', rev, '--', self.bfile]

        def callback(return_code, *args):
            if return_code == 0:
                curtip = len(hg.repository(self.ui, self.repo.root))
                self.repo = hg.repository(self.ui, path=self.bfile)
                self.graphview.set_repo(self.repo, self.stbar)
                self.changeview.set_repo(self.repo)
                if hasattr(self, 'mqwidget'):
                    self.mqwidget.set_repo(self.repo)
                self.npreviews = len(self.repo) - curtip
                if self.npreviews == 0:
                    self.remove_overlay(False)
                else:
                    self.reload_log()
                text = _('Finished pull to revision %s') % rev
            else:
                text = _('Aborted pull')
            self.stbar.set_idle_text(text)
        if not self.execute_command(cmdline, callback,
                    status=_('Pulling changesets to revision %s...') % rev,
                    title=_('Pull to %s') % rev):
            gdialog.Prompt(_('Cannot run now'),
                           _('Please try again after the previous '
                             'command has completed'), self).run()

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
            # In case new export args are added in the future, merge the
            # hg defaults
            exportOpts= self.merge_opts(commands.table['^export'][1], ())
            exportOpts['output'] = result
            def dohgexport():
                commands.export(self.ui,self.repo,str(rev),**exportOpts)
            success, outtext = self._hg_call_wrapper("Export",dohgexport,False)

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
        self.changeview.clear_cache()
        newparents = [x.node() for x in self.repo.parents()]
        if not oldparents == newparents:
            self.refresh_model()

    def domerge(self, menuitem):
        if self.revrange:
            rev0, rev1 = self.revrange
        else:
            rev0, rev1 = self.repo['.'].rev(), self.currevid
        dlg = merge.MergeDialog(rev0, rev1)
        def merge_notify(oldparents, repolen, func):
            hglib.invalidaterepo(self.repo)
            self.changeview.clear_cache()
            if len(self.repo) != repolen:
                self.reload_log()
            elif not oldparents == self.repo.parents():
                self.refresh_model()
            # update arguments for notify func
            oldparents = self.repo.parents()
            dlg.set_notify_func(func, oldparents, repolen, func)
        args = [self.repo.parents(), len(self.repo), merge_notify]
        dlg.set_notify_func(merge_notify, *args)
        merge_notify(*args) # could have immediately switched parents
        self.show_dialog(dlg)

    def archive(self, menuitem):
        rev = self.currevid
        parents = [x.node() for x in self.repo.parents()]
        dlg = archive.ArchiveDialog(rev)
        self.show_dialog(dlg)

    def select_common_ancestor(self, menuitem):
        rev1, rev2 = self.revrange
        changelog = self.repo.changelog
        lookup = self.repo.lookup
        ancestor = changelog.ancestor(lookup(rev1), lookup(rev2))
        rev = changelog.rev(ancestor)
        self.goto_rev(rev)
        self.origsel = None

    def thgrefresh(self, window):
        self.refresh_clicked()

    def refresh_clicked(self, widget=None, reset=False):
        if reset:
            self.stbar.set_idle_text(None)
            self.outgoing = []
            self.origtip = len(self.repo)
        self.refreshui()
        self.update_urllist()
        self.reload_log()
        return True

    def enable_mqpanel(self, enable=None):
        if not hasattr(self, 'mqpaned'):
            return
        if enable is None:
            enable = self.setting_mqvis and self.mqwidget.has_patch()

        # set the state of MQ toolbutton
        self.cmd_handler_block_by_func('mq', self.mq_clicked)
        self.cmd_set_active('mq', enable)
        self.cmd_handler_unblock_by_func('mq', self.mq_clicked)
        self.cmd_set_sensitive('mq', self.mqwidget.has_mq())

        # show/hide MQ pane
        oldpos = self.mqpaned.get_position()
        self.mqpaned.set_position(enable and self.setting_mqhpos or 0)
        if not enable and oldpos:
            self.setting_mqhpos = oldpos

    def mq_clicked(self, widget, *args):
        self.enable_mqpanel(widget.get_active())

    def enable_pbranchpanel(self, enable=None):
        if not hasattr(self, 'pbranchpaned'):
            return
        if enable is None:
            enable = self.setting_pbranchvis and self.pbranchwidget.has_patch()
        oldpos = self.pbranchpaned.get_position()
        self.pbranchpaned.set_position(enable and self.setting_pbranchhpos or 0)
        if not enable and oldpos:
            self.setting_pbranchhpos = oldpos

        # set the state of PBranch toolbutton
        if hasattr(self, 'pbranchtb'):
            self.pbranchtb.handler_block_by_func(self.pbranch_clicked)
            self.cmd_set_active('pbranch', enable)
            self.pbranchtb.handler_unblock_by_func(self.pbranch_clicked)
            self.cmd_set_sensitive('pbranch', self.pbranchwidget.has_pbranch())

    def pbranch_clicked(self, widget, data=None):
        self.enable_pbranchpanel(widget.get_active())

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

    def tree_popup_menu(self, treeview, button=0, time=0):
        try:
            self.repo.parents()
        except error.Abort, e:
            self.stbar.set_text(_('Refresh required'))
            return True
        menu = self.tree_context_menu()
        menu.popup(None, None, None, button, time)
        return True

    def tree_popup_menu_diff(self, treeview, button=0, time=0):
        try:
            self.repo.parents()
        except error.Abort, e:
            self.stbar.set_text(_('Refresh required'))
            return True
        menu = self.tree_diff_context_menu()
        menu.popup(None, None, None, button, time)
        return True

    def tree_row_act(self, tree, path, column):
        self.vdiff_change(None, self.pats)
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

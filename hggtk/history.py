#
# history.py - Changelog dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import subprocess
import sys
import time

import pygtk
pygtk.require('2.0')
import gtk
import gobject
import pango

from mercurial.i18n import _
from mercurial.node import *
from mercurial import cmdutil, util, ui, hg, commands, patch
from hgext import extdiff
from shlib import shell_notify
from gdialog import *
from hgcmd import CmdDialog
from update import UpdateDialog
from merge import MergeDialog
from vis import treemodel
from vis.treeview import TreeView


class GLog(GDialog):
    """GTK+ based dialog for displaying repository logs
    """
    def get_title(self):
        title = os.path.basename(self.repo.root) + ' log ' 
        if self.opts['rev']:
            title += '--rev ' + ':'.join(self.opts['rev'])
        if self.pats != ['']:
            title += '{search} ' + ' '.join(self.pats)
        return title

    def get_icon(self):
        return 'menulog.ico'

    def parse_opts(self):
        # Disable quiet to get full log info
        self.ui.quiet = False

    def get_tbbuttons(self):
        tbuttons = [
                self.make_toolbutton(gtk.STOCK_REFRESH, 're_fresh',
                    self._refresh_clicked),
                gtk.SeparatorToolItem(),
             ]

        self.graph_toggle = gtk.ToggleToolButton(gtk.STOCK_CONVERT)
        self.graph_toggle.set_use_underline(True)
        self.graph_toggle.set_label('_show graph')
        self.graph_toggle.set_active(False)
        self.graph_toggle.connect('toggled', self._graph_toggled)
        tbuttons.append(self.graph_toggle)

        self.filterbutton = self.make_toolbutton(gtk.STOCK_INDEX, '_filter',
                    self._refresh_clicked, menu=self._filter_menu())
        tbuttons.append(self.filterbutton)
        tbuttons.append(gtk.SeparatorToolItem())
        return tbuttons

    def _more_clicked(self, button):
        self.graphview.next_revision_batch()

    def _load_all_clicked(self, button):
        self.graphview.load_all_revisions()
        self.nextbutton.set_sensitive(False)
        self.allbutton.set_sensitive(False)

    def revisions_loaded(self, graphview):
        '''Treeview reports log generator has exited'''
        self.nextbutton.set_sensitive(False)
        self.allbutton.set_sensitive(False)

    def _graph_toggled(self, togglebutton, data=None):
        if togglebutton.get_active():
            self.graph_col_enabled = True
            self.filterbutton.set_sensitive(False)
        else:
            self.graph_col_enabled = False
            self.filterbutton.set_sensitive(True)
        self.reload_log()

    def _filter_all(self, widget, data=None):
        if widget.get_active():
            self._filter = "all"
            self.reload_log()
            
    def _filter_tagged(self, widget, data=None):
        if widget.get_active():
            self._filter = "tagged"
            self.reload_log()
        
    def _filter_parents(self, widget, data=None):
        if widget.get_active():
            self._filter = "parents"
            self.reload_log()
            
    def _filter_heads(self, widget, data=None):
        if widget.get_active():
            self._filter = "heads"
            self.reload_log()

    def _filter_menu(self):
        menu = gtk.Menu()
        
        button = gtk.RadioMenuItem(None, "Show All Revisions")
        button.set_active(True)
        button.connect("toggled", self._filter_all)
        menu.append(button)
        
        button = gtk.RadioMenuItem(button, "Show Tagged Revisions")
        button.connect("toggled", self._filter_tagged)
        menu.append(button)
       
        button = gtk.RadioMenuItem(button, "Show Parent Revisions")
        button.connect("toggled", self._filter_parents)
        menu.append(button)
       
        button = gtk.RadioMenuItem(button, "Show Head Revisions")
        button.connect("toggled", self._filter_heads)
        menu.append(button)
       
        menu.show_all()
        return menu


    def prepare_display(self):
        self._last_rev = None
        self._filter = "all"


    def save_settings(self):
        settings = GDialog.save_settings(self)
        settings['glog'] = self._vpaned.get_position()
        return settings


    def load_settings(self, settings):
        GDialog.load_settings(self, settings)
        if settings:
            self._setting_vpos = settings['glog']
        else:
            self._setting_vpos = -1


    def _hg_log(self, rev, pats, verbose):
        def dohglog():
            self.restore_cwd()
            self.repo.dirstate.invalidate()
            commands.log(self.ui, self.repo, *pats, **self.opts)

        logtext = ''
        success = False
        saved_revs = self.opts['rev']
        saved_verbose = self.ui.verbose
        try:
            self.opts['rev'] = rev
            self.ui.verbose = verbose
            success, logtext = self._hg_call_wrapper('Log', dohglog, False)
        finally:
            self.opts['rev'] = saved_revs
            self.ui.verbose = saved_verbose
        return success, logtext

    def _get_tagged_rev(self):
        l = [hex(r) for t, r in self.repo.tagslist()]
        l.reverse()
        return l

    def reload_log(self):
        """Send refresh event to treeview object"""
        self.nextbutton.set_sensitive(True)
        self.allbutton.set_sensitive(True)
        if self.graph_col_enabled:
            self.graphview.refresh(None, None, self.opts)
        else:
            revs = []
            if self._filter == "all":
                revs = self.opts['rev']
            elif self._filter == "tagged":
                revs = self._get_tagged_rev()
            elif self._filter == "parents":
                repo_parents = [x.rev() for x in self.repo.workingctx().parents()]
                revs = [str(x) for x in repo_parents]
            elif self._filter == "heads":
                heads = [self.repo.changelog.rev(x) for x in self.repo.heads()]
                revs = [str(x) for x in heads]
            self.graphview.refresh(revs, self.pats, self.opts)

    def load_details(self, rev):
        parents = self.currow[treemodel.PARENTS]
        ctx = self.repo.changectx(rev)
        if not ctx:
            self.details_text.set_buffer(gtk.TextBuffer())
            return False

        buffer = gtk.TextBuffer()
        buff_iter = buffer.get_start_iter()
        buffer.create_tag('changeset', foreground='#000090',
                paragraph_background='#F0F0F0')
        buffer.create_tag('date', foreground='#000090',
                paragraph_background='#F0F0F0')
        buffer.create_tag('tag', foreground='#000090',
                paragraph_background='#F0F0F0')
        buffer.create_tag('files', foreground='#5C5C5C',
                paragraph_background='#F0F0F0')
        buffer.create_tag('parent', foreground='#000090',
                paragraph_background='#F0F0F0')
        
        parent_link = buffer.create_tag('parlink', foreground='#0000FF', 
                underline=pango.UNDERLINE_SINGLE,
                paragraph_background='#F0F0F0')
        parent_link.connect("event", self.parent_link_handler)
        
        date = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ctx.date()[0]))
        
        change = str(rev) + ':' + short(ctx.node())
        buffer.insert_with_tags_by_name(buff_iter,
                'changeset: ' + change + '\n', 'changeset')
        buffer.insert_with_tags_by_name(buff_iter,
                'user:      ' + ctx.user() + '\n', 'changeset')
        buffer.insert_with_tags_by_name(buff_iter,
                'date:      ' + date + '\n', 'date')

        for p in parents:
            change = str(p) + ':' + short(self.repo.changelog.node(p))
            buffer.insert_with_tags_by_name(buff_iter,
                    'parent:    ', 'parent')
            buffer.insert_with_tags_by_name(buff_iter,
                    change + '\n', 'parlink')

        buffer.insert_with_tags_by_name(buff_iter,
                'files:     ' + ' '.join(ctx.files()) + '\n', 'files')

        tags = ' '.join(ctx.tags())
        if tags:
            buffer.insert_with_tags_by_name(buff_iter,
                    'tags:      ' + tags + '\n', 'tag')

        log = util.fromlocal(ctx.description())
        buffer.insert(buff_iter, '\n' + log + '\n')
        self.details_text.set_buffer(buffer)
        return True

    def parent_link_handler(self, tag, widget, event, iter):
        text = self.get_link_text(tag, widget, event, iter)
        if not text:
            return
        linkrev = long(text.split(':')[0])
        self.graphview.set_revision_id(linkrev)
        self.graphview.scroll_to_revision(linkrev)

    def get_link_text(self, tag, widget, event, iter):
        """handle clicking on a link in a textview"""
        if event.type != gtk.gdk.BUTTON_RELEASE:
            return
        text_buffer = widget.get_buffer()
        beg = iter.copy()
        while not beg.begins_tag(tag):
            beg.backward_char()
        end = iter.copy()
        while not end.ends_tag(tag):
            end.forward_char()
        text = text_buffer.get_text(beg, end)
        return text
        
    def tree_context_menu(self):
        def create_menu(label, callback):
            menuitem = gtk.MenuItem(label, True)
            menuitem.connect('activate', callback)
            menuitem.set_border_width(1)
            return menuitem
            
        _menu = gtk.Menu()
        _menu.append(create_menu('di_splay', self._show_status))
        _menu.append(create_menu('_checkout', self._checkout))
        self._cmenu_merge = create_menu('_merge with', self._merge)
        _menu.append(self._cmenu_merge)
        _menu.append(create_menu('_export patch', self._export_patch))
        _menu.append(create_menu('e_mail patch', self._email_patch))
        _menu.append(create_menu('add/remove _tag', self._add_tag))
        _menu.show_all()
        return _menu
        

    def get_body(self):
        self._menu = self.tree_context_menu()

        self.tree_frame = gtk.Frame()
        self.tree_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)

        limit_opt = self.repo.ui.config('tortoisehg', 'graphlimit', '500')
        if limit_opt:
            try:
                limit = int(limit_opt)
            except ValueError:
                limit = 0
            if limit <= 0:
                limit = None
        else:
            limit = None

        self.graphview = TreeView(self.repo, limit)
        self.tree = self.graphview.treeview
        self.graphview.connect('revision-selected', self.selection_changed)
        self.graphview.connect('revisions-loaded', self.revisions_loaded)
        self.graphview.set_property('date-column-visible', True)

        self.tree.connect('button-release-event', self._tree_button_release)
        self.tree.connect('popup-menu', self._tree_popup_menu)
        self.tree.connect('row-activated', self._tree_row_act)
        #self.tree.modify_font(pango.FontDescription(self.fontlist))
        
        self.tips = gtk.Tooltips()

        hbox = gtk.HBox()
        hbox.pack_start(self.graphview, True, True, 0)
        vbox = gtk.VBox()
        self.nextbutton = gtk.ToolButton(gtk.STOCK_GO_DOWN)
        self.nextbutton.connect('clicked', self._more_clicked)
        self.nextbutton.set_tooltip(self.tips,
                'show next %d revisions' % limit)
        self.allbutton = gtk.ToolButton(gtk.STOCK_GOTO_BOTTOM)
        self.allbutton.connect('clicked', self._load_all_clicked)
        self.allbutton.set_tooltip(self.tips,
                'show all remaining revisions')
        vbox.pack_start(gtk.Label(''), True, True)
        vbox.pack_start(self.nextbutton, False, False)
        vbox.pack_start(self.allbutton, False, False)

        hbox.pack_start(vbox, False, False, 0)
        self.tree_frame.add(hbox)
        self.tree_frame.show_all()

        details_frame = gtk.Frame()
        details_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        details_frame.add(scroller)
        
        self.details_text = gtk.TextView()
        self.details_text.set_wrap_mode(gtk.WRAP_WORD)
        self.details_text.set_editable(False)
        self.details_text.modify_font(pango.FontDescription(self.fontcomment))
        scroller.add(self.details_text)

        self._vpaned = gtk.VPaned()
        self._vpaned.pack1(self.tree_frame, True, False)
        self._vpaned.pack2(details_frame, True, True)
        self._vpaned.set_position(self._setting_vpos)

        # Initialize graph selection toggle
        if self.graph_col_enabled:
            self.graph_toggle.set_active(True)
            self.filterbutton.set_sensitive(False)
        else:
            self.graph_toggle.set_active(False)
            self.filterbutton.set_sensitive(True)
        return self._vpaned


    def _add_tag(self, menuitem):
        from tagadd import TagAddDialog

        rev = self.currow[treemodel.REVID]
        parents = self.currow[treemodel.PARENTS]
        
        # save tag info for detecting new tags added
        oldtags = self.repo.tagslist()
        
        dialog = TagAddDialog(self.repo.root, rev=str(rev))
        dialog.run()
        dialog.hide()
        
        # refresh if new tags added
        self.repo.invalidate()
        newtags = self.repo.tagslist()
        if newtags != oldtags:
            self.reload_log()

                
    def _show_status(self, menuitem):
        from status import GStatus
        from gtools import cmdtable
        
        rev = self.currow[treemodel.REVID]
        parents = self.currow[treemodel.PARENTS]
        if len(parents) == 0:
            parents = [rev-1]

        for parent in parents:
            statopts = self.merge_opts(cmdtable['gstatus|gst'][1],
                    ('include', 'exclude', 'git'))
            statopts['rev'] = ['%u:%u' % (parent, rev)]
            statopts['modified'] = True
            statopts['added'] = True
            statopts['removed'] = True
            dialog = GStatus(self.ui, self.repo, self.cwd, [], statopts, False)
            dialog.display()
        return True


    def _export_patch(self, menuitem):
        rev = self.currow[treemodel.REVID]
        filename = "%s_rev%s.patch" % (os.path.basename(self.repo.root), rev)
        fd = NativeSaveFileDialogWrapper(Title = "Save patch to",
                                         InitialDir=self.repo.root,
                                         FileName=filename)
        result = fd.run()

        if result:
            # In case new export args are added in the future, merge the
            # hg defaults
            exportOpts= self.merge_opts(commands.table['^export'][1], ())
            exportOpts['output'] = result
            def dohgexport():
                commands.export(self.ui,self.repo,str(rev),**exportOpts)
            success, outtext = self._hg_call_wrapper("Export",dohgexport,False)

    def _email_patch(self, menuitem):
        from hgemail import EmailDialog
        rev = self.currow[treemodel.REVID]
        dlg = EmailDialog(self.repo.root, ['--rev', str(rev)])
        dlg.show_all()
        dlg.run()
        dlg.hide()

    def _checkout(self, menuitem):
        rev = self.currow[treemodel.REVID]
        parents0 = [x.node() for x in self.repo.workingctx().parents()]
        
        dialog = UpdateDialog(self.cwd, rev)
        dialog.set_transient_for(self)
        dialog.show_all()
        dialog.run()

        # FIXME: must remove transient explicitly to prevent history
        #        dialog from getting pushed behind other app windows
        dialog.set_transient_for(None)        
        dialog.hide()
        
        # FIXME: re-open repo to retrieve the new parent data
        root = self.repo.root
        del self.repo
        self.repo = hg.repository(ui.ui(), path=root)

        parents1 = [x.node() for x in self.repo.workingctx().parents()]
        if not parents0 == parents1:
            self.reload_log()

    def _merge(self, menuitem):
        rev = self.currow[treemodel.REVID]
        parents0 = [x.node() for x in self.repo.workingctx().parents()]
        node = short(self.repo.changelog.node(rev))
        dialog = MergeDialog(self.repo.root, self.cwd, node)
        dialog.set_transient_for(self)
        dialog.show_all()
        dialog.run()

        # FIXME: must remove transient explicitly to prevent history
        #        dialog sfrom getting pushed behind other app windows
        dialog.set_transient_for(None)
        dialog.hide()
        
        # FIXME: re-open repo to retrieve the new parent data
        root = self.repo.root
        del self.repo
        self.repo = hg.repository(ui.ui(), path=root)
        
        # if parents data has changed...
        parents1 = [x.node() for x in self.repo.workingctx().parents()]
        if not parents0 == parents1:
            msg = 'Launch commit tool for merge results?'
            if Confirm('Commit', [], self, msg).run() == gtk.RESPONSE_YES:
                # Spawn commit tool if merge was successful
                ct = self.repo.ui.config('tortoisehg', 'commit', 'internal')
                if ct == 'internal':
                    from commit import launch as commit_launch
                    commit_launch(self.repo.root, [], self.repo.root, False)
                else:
                    args = [self.hgpath, '--repository', self.repo.root, ct]
                    subprocess.Popen(args, shell=False)
            self.reload_log()

    def selection_changed(self, treeview):
        self.currow = self.graphview.get_revision()
        rev = self.currow[treemodel.REVID]
        if rev != self._last_rev:
            self._last_rev = rev
            self.load_details(rev)
        return False

    def _refresh_clicked(self, toolbutton, data=None):
        self.reload_log()
        return True

    def _tree_button_release(self, widget, event) :
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            self._tree_popup_menu(widget, event.button, event.time)
        return False


    def _tree_popup_menu(self, treeview, button=0, time=0) :
        selrev = self.currow[treemodel.REVID]
        
        # disable/enable menus as required
        parents = [self.repo.changelog.rev(x.node()) for x in
                   self.repo.workingctx().parents()]
        can_merge = selrev not in parents and \
                    len(self.repo.heads()) > 1 and \
                    len(parents) < 2
        self._cmenu_merge.set_sensitive(can_merge)

        # display the context menu
        self._menu.popup(None, None, None, button, time)
        return True


    def _tree_row_act(self, tree, path, column) :
        """Default action is the first entry in the context menu
        """
        self._menu.get_children()[0].activate()
        return True

def run(root='', cwd='', files=[], hgpath='hg', **opts):
    u = ui.ui()
    u.updateopts(debug=False, traceback=False)
    repo = hg.repository(u, path=root)

    cmdoptions = {
        'follow':False, 'follow-first':False, 'copies':False, 'keyword':[],
        'limit':0, 'rev':[], 'removed':False, 'no_merges':False, 'date':None,
        'only_merges':None, 'prune':[], 'git':False, 'verbose':False,
        'include':[], 'exclude':[]
    }

    dialog = GLog(u, repo, cwd, files, cmdoptions, True)
    dialog.hgpath = hgpath

    if files and files != [root]:
        dialog.graph_col_enabled = False
    else:
        dialog.graph_col_enabled = True
    
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    dialog.display()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or ''
    opts['files'] = [opts['root']]
    run(**opts)

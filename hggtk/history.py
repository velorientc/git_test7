#
# history.py - Changelog dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import threading
import StringIO
import sys
import shutil
import tempfile
import datetime
import cPickle

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

class GLog(GDialog):
    """GTK+ based dialog for displaying repository logs
    """

    # "Constants"
    block_count = 150


    def get_title(self):
        return os.path.basename(self.repo.root) + ' log ' + ':'.join(self.opts['rev']) + ' ' + ' '.join(self.pats)

    def get_icon(self):
        return 'menulog.ico'

    def parse_opts(self):
        # Disable quiet to get full log info
        self.ui.quiet = False


    def get_tbbuttons(self):
        return [
                self.make_toolbutton(gtk.STOCK_REFRESH, 're_fresh', self._refresh_clicked),
                gtk.SeparatorToolItem(),
                self.make_toolbutton(gtk.STOCK_INDEX, '_filter', self._refresh_clicked,
                        menu=self._filter_menu()),
                gtk.SeparatorToolItem()
             ]

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
        
        self._filter = "all"    # FIXME: not the best place to init variable

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
        self.refreshing = False
        self._last_rev = -999
        # If the log load failed, no reason to continue
        if not self.reload_log():
            raise util.Abort('could not load log')


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
        """Clear out the existing ListStore model and reload it from the repository. 
        """
        # If the last refresh is still being processed, then do nothing
        if self.refreshing:
            return False

        # Retrieve repo revision info
        self.repo.invalidate()
        repo_parents = [x.rev() for x in self.repo.workingctx().parents()]
        heads = [self.repo.changelog.rev(x) for x in self.repo.heads()]
        
        revs = []
        if self._filter == "all":
            revs = self.opts['rev']
        elif self._filter == "tagged":
            revs = self._get_tagged_rev()
        elif self._filter == "parents":
            revs = [str(x) for x in repo_parents]
        elif self._filter == "heads":
            revs = [str(x) for x in heads]
            
        # For long logs this is the slowest part, but given the current
        # Hg API doesn't allow it to be easily processed in chuncks
        success, logtext = self._hg_log(revs, self.pats, False)
        if not success:
            return False

        if not logtext:
            return True

        # Currently selected file
        iter = self.tree.get_selection().get_selected()[1]
        if iter:
            reselect = self.model[iter][0]
        else:
            reselect = None

        # Load the new data into the tree's model
        self.tree.hide()
        self.model.clear()
        
        # Generator that parses and inserts log entries
        def inserter(logtext):
            while logtext:
                blocks = logtext.strip('\n').split('\n\n', GLog.block_count)
                if len(blocks) > GLog.block_count:
                    logtext = blocks[GLog.block_count]
                    del blocks[GLog.block_count]
                else:
                    logtext = None
    
                for block in blocks:
                    # defaults
                    log = { 'user' : 'missing', 'summary' : '', 'tag' : '' }
                    lines = block.split('\n')
                    parents = []
                    tags = []
                    for line in lines:
                        line = util.fromlocal(line)
                        sep = line.index(':')
                        info = line[0:sep]
                        value = line[sep+1:].strip()
    
                        if info == 'changeset':
                            log['rev'] = value.split(':')[0]
                        elif info == 'parent':
                            parents.append(long(value.split(':')[0]))
                        elif info == 'tag':
                            tags.append(value)
                        else:
                            log[info] = value
    
                    if tags: log['tag'] = ','.join(tags)

                    rev = int(log['rev'])
                    is_parent = rev in repo_parents and gtk.STOCK_HOME or ''
                    is_head = rev in heads and gtk.STOCK_EXECUTE or ''
                    show_date = util.strdate(util.tolocal(log['date']),
                            '%a %b %d %H:%M:%S %Y', {})[0]
                    self.model.append((is_parent, is_head, 
                                       long(log['rev']),
                                       log['tag'], log['user'],
                                       log['summary'], log['date'],
                                       show_date,
                                       parents))
                yield logtext is not None


        # Insert entries during idle to improve response time, but run
        # the first batch synchronously to attempt the reselect below
        gen = inserter(logtext)
        self.refreshing = gen.next()

        # If insert didn't finish, setup idle processing for the remainder
        if self.refreshing:
            def doidle():
                self.refreshing = gen.next()
                return self.refreshing
            gobject.idle_add(doidle)

        selection = self.tree.get_selection()
        for row in self.model:
            if row[0] == reselect:
                selection.select_iter(row.iter)
                break
        else:
            self.tree.scroll_to_cell((0,))
            selection.select_path((0,))

        self.tree.show()
        self.tree.grab_focus()
        return True


    def load_details(self, rev, parents):
        save_removed = self.opts['removed'] 
        self.opts['removed'] = False
        success, logtext = self._hg_log(rev, [], True)
        self.opts['removed'] = save_removed

        if not success:
            self.details_text.set_buffer(gtk.TextBuffer())
            return False

        buffer = gtk.TextBuffer()
        buff_iter = buffer.get_start_iter()
        buffer.create_tag('changeset', foreground='#000090', paragraph_background='#F0F0F0')
        buffer.create_tag('date', foreground='#000090', paragraph_background='#F0F0F0')
        buffer.create_tag('tag', foreground='#000090', paragraph_background='#F0F0F0')
        buffer.create_tag('files', foreground='#5C5C5C', paragraph_background='#F0F0F0')
        if parents == 1:
            buffer.create_tag('parent', foreground='#900000', paragraph_background='#F0F0F0')
        elif parents == 2:
            buffer.create_tag('parent', foreground='#006400', paragraph_background='#F0F0F0')

        lines = logtext.split('\n')
        lines_iter = iter(lines)

        for line in lines_iter:
            line = util.fromlocal(line)
            if line.startswith('changeset:'):
                buffer.insert_with_tags_by_name(buff_iter, line + '\n', 'changeset')
            if line.startswith('date:'):
                buffer.insert_with_tags_by_name(buff_iter, line + '\n', 'date')
            elif line.startswith('parent:'):
                buffer.insert_with_tags_by_name(buff_iter, line + '\n', 'parent')
            elif line.startswith('files:'):
                buffer.insert_with_tags_by_name(buff_iter, line + '\n', 'files')
            elif line.startswith('tag:'):
                buffer.insert_with_tags_by_name(buff_iter, line + '\n', 'tag')
            elif line.startswith('description:'):
                buffer.insert(buff_iter, '\n')
                break;

        for line in lines_iter:
            line = util.fromlocal(line)
            buffer.insert(buff_iter, line + '\n')

        self.details_text.set_buffer(buffer)
        return True


    def _search_in_tree(self, model, column, key, iter, data):
        """Searches all fields shown in the tree when the user hits crtr+f,
        not just the ones that are set via tree.set_search_column.
        Case insensitive
        """
        key = key.lower()
        searchable = [x.lower() for x in (
                        str(model.get_value(iter,2)), #rev id (local)
                        model.get_value(iter,4), #author
                        model.get_value(iter,5), #summary
                        )]
        for field in searchable:
            if field.find(key) != -1:
                return False
        return True

    def make_parent(self, tvcolumn, cell, model, iter):
        stock = model.get_value(iter, 0)
        pb = self.tree.render_icon(stock, gtk.ICON_SIZE_MENU, None)
        cell.set_property('pixbuf', pb)
        return

    def make_head(self, tvcolumn, cell, model, iter):
        stock = model.get_value(iter, 1)
        pb = self.tree.render_icon(stock, gtk.ICON_SIZE_MENU, None)
        cell.set_property('pixbuf', pb)
        return
        
    def get_body(self):
        self._menu = gtk.Menu()
        self._menu.set_size_request(90, -1)
        menuitem = gtk.MenuItem('_status', True)
        menuitem.connect('activate', self._show_status)
        menuitem.set_border_width(1)
        self._menu.append(menuitem)
        menuitem = gtk.MenuItem("_export patch",True)
        menuitem.connect('activate',self._export_patch)
        menuitem.set_border_width(1)
        self._menu.append(menuitem)
        menuitem = gtk.MenuItem("e_mail patch",True)
        menuitem.connect('activate',self._email_patch)
        menuitem.set_border_width(1)
        self._menu.append(menuitem)
        menuitem = gtk.MenuItem('add _tag', True)
        menuitem.connect('activate', self._add_tag)
        menuitem.set_border_width(1)
        self._menu.append(menuitem)
        self._menu.show_all()

        self.model = gtk.ListStore(str, str, long, str, str, str, str, long, object)
        self.model.set_default_sort_func(self._sort_by_rev)

        self.tree = gtk.TreeView(self.model)
        self.tree.connect('button-release-event', self._tree_button_release)
        self.tree.connect('popup-menu', self._tree_popup_menu)
        self.tree.connect('row-activated', self._tree_row_act)
        self.tree.set_reorderable(False)
        self.tree.set_enable_search(True)
        self.tree.set_search_equal_func(self._search_in_tree,None)
        self.tree.get_selection().set_mode(gtk.SELECTION_SINGLE)
        self.tree.get_selection().connect('changed', self._tree_selection_changed)
        self.tree.set_rubber_banding(False)
        self.tree.modify_font(pango.FontDescription(self.fontlist))
        self.tree.set_rules_hint(True) 
        
        parent_cell = gtk.CellRendererPixbuf()
        head_cell = gtk.CellRendererPixbuf()
        tags_cell = gtk.CellRendererText()
        changeset_cell = gtk.CellRendererText()
        user_cell = gtk.CellRendererText()
        summary_cell = gtk.CellRendererText()
        date_cell = gtk.CellRendererText()
        
        col = 1
        
        col_status = gtk.TreeViewColumn('status')
        col_status.pack_start(parent_cell, False)
        col_status.pack_start(head_cell, False)
        col_status.set_cell_data_func(parent_cell, self.make_parent)
        col_status.set_cell_data_func(head_cell, self.make_head)
        
        col += 1
        col_rev = gtk.TreeViewColumn('rev', changeset_cell)
        col_rev.add_attribute(changeset_cell, 'text', col)
        col_rev.set_cell_data_func(changeset_cell, self._text_color)
        col_rev.set_sort_column_id(col)
        col_rev.set_resizable(False)
        
        col += 1
        col_tag = gtk.TreeViewColumn('tag', tags_cell)
        col_tag.add_attribute(tags_cell, 'text', col)
        col_tag.set_cell_data_func(tags_cell, self._text_color)
        col_tag.set_sort_column_id(col)
        col_tag.set_resizable(True)
        
        col += 1
        col_user = gtk.TreeViewColumn('user', user_cell)
        col_user.add_attribute(user_cell, 'text', col)
        col_user.set_cell_data_func(user_cell, self._text_color)
        col_user.set_sort_column_id(col)
        col_user.set_resizable(True)
        
        col += 1
        col_sum = gtk.TreeViewColumn('summary', summary_cell)
        col_sum.add_attribute(summary_cell, 'text', col)
        col_sum.set_cell_data_func(summary_cell, self._text_color)
        col_sum.set_sort_column_id(col)
        col_sum.set_resizable(True)

        col += 1
        col_date = gtk.TreeViewColumn('date', date_cell)
        col_date.add_attribute(date_cell, 'text', col)
        col_date.set_cell_data_func(date_cell, self._text_color)
        col_date.set_sort_column_id(col)
        col_date.set_resizable(True)

        self.tree.append_column(col_status)
        self.tree.append_column(col_rev)
        self.tree.append_column(col_tag)
        self.tree.append_column(col_user)
        self.tree.append_column(col_sum)
        self.tree.append_column(col_date)
        self.tree.set_headers_clickable(True)
        
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(self.tree)
        
        tree_frame = gtk.Frame()
        tree_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        tree_frame.add(scroller)

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
        self._vpaned.pack1(tree_frame, True, False)
        self._vpaned.pack2(details_frame, True, True)
        self._vpaned.set_position(self._setting_vpos)
        return self._vpaned


    def _sort_by_rev(self, model, iter1, iter2):
        lhs, rhs = (model.get_value(iter1, 2), model.get_value(iter2, 2))

        # GTK+ bug that calls sort before a full row is inserted causing values to be None.
        if None in (lhs, rhs) :
            return 0

        result = long(rhs) - long(lhs)
        return min(max(result, -1), 1)


    def _text_color(self, column, text_renderer, list, row_iter):
        parents = list[row_iter][8]
        if len(parents) == 2:
            text_renderer.set_property('foreground', '#006400')
        elif len(parents) == 1:
            text_renderer.set_property('foreground', '#900000')
        else:
            text_renderer.set_property('foreground', 'black')


    def _add_tag(self, menuitem):
        from tagadd import TagAddDialog

        row = self.model[self.tree.get_selection().get_selected()[1]]
        rev = long(row[2])
        parents = row[8]
        
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
        
        row = self.model[self.tree.get_selection().get_selected()[1]]
        rev = long(row[2])
        parents = row[8]
        if len(parents) == 0:
            parents = [rev-1]

        for parent in parents:
            statopts = self.merge_opts(cmdtable['gstatus|gst'][1], ('include', 'exclude', 'git'))
            statopts['rev'] = ['%u:%u' % (parent, rev)]
            statopts['modified'] = True
            statopts['added'] = True
            statopts['removed'] = True
            dialog = GStatus(self.ui, self.repo, self.cwd, [], statopts, False)
            dialog.display()
        return True


    def _export_patch(self, menuitem):
        row = self.model[self.tree.get_selection().get_selected()[1]]
        rev = long(row[2])
        filename = "%s_rev%s.patch" % (os.path.basename(self.repo.root), rev)
        fd = NativeSaveFileDialogWrapper(Title = "Save patch to", FileName=filename)
        result = fd.run()

        if result:
            # In case new export args are added in the future, merge the hg defaults
            exportOpts= self.merge_opts(commands.table['^export'][1], ())
            exportOpts['output'] = result
            def dohgexport():
                commands.export(self.ui,self.repo,str(rev),**exportOpts)
            success, outtext = self._hg_call_wrapper("Export",dohgexport,False)

    def _email_patch(self, menuitem):
        from hgemail import EmailDialog
        row = self.model[self.tree.get_selection().get_selected()[1]]
        rev = long(row[2])
        dlg = EmailDialog(self.repo.root, ['--rev', str(rev)])
        dlg.show_all()
        dlg.run()
        dlg.hide()

    def _tree_selection_changed(self, selection):
        ''' Update the details text '''
        if selection.count_selected_rows() == 0:
            return False
        rev = [str(x) for x in [self.model[selection.get_selected()[1]][2]]]
        if rev != self._last_rev:
            self._last_rev = rev
            parents = self.model[selection.get_selected()[1]][8]
            self.load_details(rev, len(parents))

        return False


    def _refresh_clicked(self, toolbutton, data=None):
        self.reload_log()
        return True


    def _tree_button_release(self, widget, event) :
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK | gtk.gdk.CONTROL_MASK)):
            self._tree_popup_menu(widget, event.button, event.time)
        return False


    def _tree_popup_menu(self, widget, button=0, time=0) :
        self._menu.popup(None, None, None, button, time)
        return True


    def _tree_row_act(self, tree, path, column) :
        """Default action is the first entry in the context menu
        """
        self._menu.get_children()[0].activate()
        return True

def run(root='', cwd='', files=[], **opts):
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
    
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    dialog.display()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or ''
    run(**opts)

#
# Data Mining dialog for TortoiseHg and Mercurial
#
# Copyright (C) 2008 Steve Borho <steve@borho.org>

import gtk
import gobject
import os
import pango
import Queue
import re
import threading
import time
from mercurial import hg, ui, util
from hglib import hgcmd_toq
from gdialog import *
from vis import treemodel
from vis.colormap import AnnotateColorMap, AnnotateColorSaturation
from vis.treeview import TreeView
import gtklib

class DataMineDialog(GDialog):
    COL_REVID = 0
    COL_TEXT = 1
    COL_TOOLTIP = 2
    COL_PATH = 3  # for grep models
    COL_COLOR = 3 # for annotate models

    def get_title(self):
        return 'DataMining - ' + os.path.basename(self.repo.root)

    def get_icon(self):
        return 'menulog.ico'

    def parse_opts(self):
        pass

    def get_tbbuttons(self):
        return [ self.make_toolbutton(gtk.STOCK_FIND, 'New Search', 
            self._search_clicked, tip='Open new search tab')
            ]

    def prepare_display(self):
        os.chdir(self.repo.root)

    def save_settings(self):
        settings = GDialog.save_settings(self)
        settings['datamine'] = ()
        return settings

    def load_settings(self, settings):
        GDialog.load_settings(self, settings)
        # settings['datamine']

    def get_body(self):
        """ Initialize the Dialog. """        
        self.grep_cmenu = self.grep_context_menu()
        self.ann_cmenu = self.annotate_context_menu()
        self.annotate_colormap = AnnotateColorSaturation()
        self.changedesc = {}
        self.revisions = {}
        self.filecurrev = {}
        self.newpagecount = 1
        vbox = gtk.VBox()
        notebook = gtk.Notebook()
        notebook.set_tab_pos(gtk.POS_TOP)
        notebook.set_scrollable(True)
        notebook.popup_enable()
        notebook.show()
        self.notebook = notebook
        vbox.pack_start(self.notebook, True, True, 2)

        self.stbar = gtklib.StatusBar()
        vbox.pack_start(self.stbar, False, False, 2)
        return vbox

    def grep_context_menu(self):
        _menu = gtk.Menu()
        _menu.append(create_menu('di_splay change', self._cmenu_display))
        _menu.append(create_menu('_annotate file', self._cmenu_annotate))
        _menu.append(create_menu('_file history', self._cmenu_file_log))
        _menu.show_all()
        return _menu

    def annotate_context_menu(self):
        _menu = gtk.Menu()
        _menu.append(create_menu('di_splay change', self._cmenu_display))
        _menu.show_all()
        return _menu

    def _cmenu_display(self, menuitem):
        from changeset import ChangeSet
        statopts = {'rev' : [self.currev] }
        dialog = ChangeSet(self.ui, self.repo, self.cwd, [], statopts, False)
        dialog.display()

    def _cmenu_annotate(self, menuitem):
        self.add_annotate_page(self.curpath, self.currev)

    def _cmenu_file_log(self, menuitem):
        from history import GLog
        dialog = GLog(self.ui, self.repo, self.cwd, [self.repo.root], {}, False)
        dialog.open_with_file(self.curpath, self.currev)
        dialog.display()

    def _grep_button_release(self, widget, event):
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            self._grep_popup_menu(widget, event.button, event.time)
        return False

    def _grep_popup_menu(self, treeview, button=0, time=0):
        self.grep_cmenu.popup(None, None, None, button, time)
        return True

    def _grep_row_act(self, tree, path, column):
        """Default action is the first entry in the context menu
        """
        self.grep_cmenu.get_children()[0].activate()
        return True

    def get_rev_desc(self, rev):
        if rev in self.changedesc:
            return self.changedesc[rev]
        ctx = self.repo.changectx(rev)
        author = util.shortuser(ctx.user())
        summary = ctx.description().replace('\0', '')
        summary = summary.split('\n')[0]
        date = time.strftime("%y-%m-%d %H:%M", time.gmtime(ctx.date()[0]))
        desc = author+'@'+str(rev)+' '+date+' "'+summary+'"'
        self.changedesc[rev] = desc
        return desc

    def _search_clicked(self, button, data):
        self.add_search_page()

    def add_search_page(self):
        frame = gtk.Frame()
        frame.set_border_width(10)
        vbox = gtk.VBox()

        hbox = gtk.HBox()
        hbox.pack_start(gtk.Label('Revision History Search'))
        search = gtk.Button('Search')
        close = gtk.Button('Close')
        hbox.pack_start(search, False, False)
        hbox.pack_start(close, False, False)
        vbox.pack_start(hbox, False, False)

        hbox = gtk.HBox()
        regexp = gtk.Entry()
        includes = gtk.Entry()
        excludes = gtk.Entry()
        hbox.pack_start(gtk.Label('Regexp:'), False, False, 4)
        hbox.pack_start(regexp, True, True, 4)
        hbox.pack_start(gtk.Label('Includes:'), False, False, 4)
        hbox.pack_start(includes, True, True, 4)
        hbox.pack_start(gtk.Label('Excludes:'), False, False, 4)
        hbox.pack_start(excludes, True, True, 4)
        self.tooltips.set_tip(regexp, 'Regular expression search pattern')
        self.tooltips.set_tip(includes, 'Comma separated list of'
                ' inclusion patterns.  By default, the entire repository'
                ' is searched.')
        self.tooltips.set_tip(excludes, 'Comma separated list of'
                ' exclusion patterns.  Exclusion patterns are applied'
                ' after inclusion patterns.')
        vbox.pack_start(hbox, False, False, 4)

        hbox = gtk.HBox()
        follow = gtk.CheckButton('Follow copies and renames')
        ignorecase = gtk.CheckButton('Ignore case')
        linenum = gtk.CheckButton('Show line numbers')
        showall = gtk.CheckButton('Show all matching revisions')
        hbox.pack_start(follow, False, False, 4)
        hbox.pack_start(ignorecase, False, False, 4)
        hbox.pack_start(linenum, False, False, 4)
        hbox.pack_start(showall, False, False, 4)
        vbox.pack_start(hbox, False, False, 4)

        treeview = gtk.TreeView()
        treeview.get_selection().set_mode(gtk.SELECTION_SINGLE)
        treeview.set_property('fixed-height-mode', True)
        treeview.connect("cursor-changed", self._grep_selection_changed)
        treeview.connect('button-release-event', self._grep_button_release)
        treeview.connect('popup-menu', self._grep_popup_menu)
        treeview.connect('row-activated', self._grep_row_act)

        results = gtk.ListStore(str, str, str, str)
        treeview.set_model(results)
        for title, width, col in (('Rev', 10, self.COL_REVID),
                ('File', 30, self.COL_PATH),
                ('Matches', 80, self.COL_TEXT)):
            cell = gtk.CellRendererText()
            cell.set_property("width-chars", width)
            cell.set_property("ellipsize", pango.ELLIPSIZE_END)
            cell.set_property("family", "Monospace")
            column = gtk.TreeViewColumn(title)
            column.set_resizable(True)
            column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            column.set_fixed_width(cell.get_size(treeview)[2])
            column.pack_start(cell, expand=True)
            column.add_attribute(cell, "text", col)
            treeview.append_column(column)
        if hasattr(treeview, 'set_tooltip_column'):
            treeview.set_tooltip_column(self.COL_TOOLTIP)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(treeview)
        vbox.pack_start(scroller, True, True)
        frame.add(vbox)
        frame.show_all()
        lbl = gtk.Label('Search %d' % self.newpagecount)
        self.newpagecount += 1
        num = self.notebook.append_page(frame, lbl)
        objs = (treeview.get_model(), frame, regexp, follow, ignorecase,
                excludes, includes, linenum, showall, search)
        search.connect('clicked', self.trigger_search, objs)
        close.connect('clicked', self.close_page)
        if hasattr(self.notebook, 'set_tab_reorderable'):
            self.notebook.set_tab_reorderable(frame, True)
        self.notebook.set_current_page(num)

    def trigger_search(self, button, objs):
        (model, frame, regexp, follow, ignorecase, 
                excludes, includes, linenum, showall, search) = objs
        re = regexp.get_text()
        if not re:
            Prompt('No regular expression given',
                    'You must provide a search expression', self).run()
            regexp.grab_focus()
            return
        
        q = Queue.Queue()
        args = [self.repo.root, q, 'grep']
        if follow.get_active():     args.append('--follow')
        if ignorecase.get_active(): args.append('--ignore-case')
        if linenum.get_active():    args.append('--line-number')
        if showall.get_active():    args.append('--all')
        incs = [x.strip() for x in includes.get_text().split(',')]
        excs = [x.strip() for x in excludes.get_text().split(',')]
        for i in incs:
            if i: args.extend(['-I', i])
        for x in excs:
            if x: args.extend(['-X', x])
        args.append(re)
        thread = threading.Thread(target=hgcmd_toq, args=args)
        thread.start()

        model.clear()
        search.set_sensitive(False)
        self.stbar.begin()
        self.stbar.set_status_text('hg ' + ' '.join(args[2:]))
        self.notebook.set_tab_label_text(frame, 'search "%s"' % re.split()[0])
        gobject.timeout_add(50, self.grep_wait, thread, q, model, search)

    def grep_wait(self, thread, q, model, search):
        """
        Handle all the messages currently in the queue (if any).
        """
        while q.qsize():
            line = q.get(0).rstrip('\r\n')
            try:
                (path, revid, text) = line.split(':', 2)
            except ValueError:
                continue
            tip = self.get_rev_desc(long(revid))
            model.append((revid, text, tip, path))
        if thread.isAlive():
            return True
        else:
            search.set_sensitive(True)
            self.stbar.end()
            return False

    def _grep_selection_changed(self, treeview):
        """
        Callback for when the user selects grep output.
        """
        (path, focus) = treeview.get_cursor()
        model = treeview.get_model()
        if path is not None and model is not None:
            iter = model.get_iter(path)
            self.currev = model[iter][self.COL_REVID]
            self.curpath = model[iter][self.COL_PATH]
            self.stbar.set_status_text(model[iter][self.COL_TOOLTIP])

    def close_page(self, button):
        '''Close page button has been pressed'''
        num = self.notebook.get_current_page()
        if num != -1 and self.notebook.get_n_pages() > 1:
            self.notebook.remove_page(num)

    def add_annotate_page(self, path, revid):
        '''
        Add new annotation page to notebook.  Start scan of
        file 'path' revision history, start annotate of supplied
        revision 'revid'.
        '''
        if revid == '.':
            parentctx = self.repo.workingctx().parents()
            rev = parentctx[0].rev()
            revid = str(rev)
        else:
            rev = long(revid)

        frame = gtk.Frame()
        frame.set_border_width(10)
        vbox = gtk.VBox()

        hbox = gtk.HBox()
        lbl = gtk.Label()
        hbox.pack_start(lbl, True, True)
        close = gtk.Button('Close')
        close.connect('clicked', self.close_page)
        hbox.pack_start(close, False, False)
        vbox.pack_start(hbox, False, False)

        # File log revision graph
        graphview = TreeView(self.repo, 5000, self.stbar)
        graphview.connect('revisions-loaded', self.revisions_loaded, rev)
        graphview.refresh(True, None, {'filehist':path, 'filerev':rev})
        graphview.set_property('rev-column-visible', True)

        # Annotation text tree view
        treeview = gtk.TreeView()
        treeview.get_selection().set_mode(gtk.SELECTION_SINGLE)
        treeview.set_property('fixed-height-mode', True)
        treeview.set_border_width(0)
        treeview.connect("cursor-changed", self._ann_selection_changed)
        treeview.connect('button-release-event', self._ann_button_release)
        treeview.connect('popup-menu', self._ann_popup_menu)
        treeview.connect('row-activated', self._ann_row_act)

        results = gtk.ListStore(str, str, str, str)
        treeview.set_model(results)
        for title, width, col in (('Rev', 10, self.COL_REVID),
                ('Matches', 80, self.COL_TEXT)):
            cell = gtk.CellRendererText()
            cell.set_property("width-chars", width)
            cell.set_property("ellipsize", pango.ELLIPSIZE_END)
            cell.set_property("family", "Monospace")
            column = gtk.TreeViewColumn(title)
            column.set_resizable(True)
            column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            column.set_fixed_width(cell.get_size(treeview)[2])
            column.pack_start(cell, expand=True)
            column.add_attribute(cell, "text", col)
            column.add_attribute(cell, "background", self.COL_COLOR)
            treeview.append_column(column)
        if hasattr(treeview, 'set_tooltip_column'):
            treeview.set_tooltip_column(self.COL_TOOLTIP)
        results.path = path
        results.rev = revid
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(treeview)

        vpaned = gtk.VPaned()
        vpaned.pack1(graphview, True, True)
        vpaned.pack2(scroller, True, True)
        vbox.pack_start(vpaned, True, True)

        frame.add(vbox)
        frame.show_all()
        num = self.notebook.append_page_menu(frame, 
                gtk.Label(os.path.basename(path) + '@' + revid),
                gtk.Label(path + '@' + revid))
        if hasattr(self.notebook, 'set_tab_reorderable'):
            self.notebook.set_tab_reorderable(frame, True)
        self.notebook.set_current_page(num)

        objs = (frame, treeview.get_model(), path)
        graphview.treeview.connect('row-activated', self.log_activate, objs)

    def log_activate(self, treeview, path, column, objs):
        model = treeview.get_model()
        iter = model.get_iter(path)
        rev = model.get_value(iter, treemodel.REVID)
        self.trigger_annotate(rev, objs)

    def revisions_loaded(self, graphview, rev):
        graphview.set_revision_id(rev)
        treeview = graphview.treeview
        path, column = treeview.get_cursor()
        treeview.row_activated(path, column)

    def trigger_annotate(self, rev, objs):
        '''
        User has selected a file revision to annotate.  Trigger a
        background thread to perform the annotation.  Disable the select
        button until this operation is complete.
        '''
        (frame, model, path) = objs
        q = Queue.Queue()
        args = [self.repo.root, q, 'annotate', '--rev', str(rev)]
        args.append(path)
        thread = threading.Thread(target=hgcmd_toq, args=args)
        thread.start()

        model.clear()
        self.stbar.begin()
        self.stbar.set_status_text('hg ' + ' '.join(args[2:]))
        path = os.path.basename(path)
        self.notebook.set_tab_label_text(frame, path+'@'+str(rev))
        gobject.timeout_add(50, self.annotate_wait, thread, q, model)

    def annotate_wait(self, thread, q, model):
        """
        Handle all the messages currently in the queue (if any).
        """
        basedate = self.repo.changectx(long(model.rev)).date()[0]
        while q.qsize():
            line = q.get(0).rstrip('\r\n')
            try:
                (revid, text) = line.split(':', 1)
            except ValueError:
                continue
            rowrev = long(revid)
            tip = self.get_rev_desc(rowrev)
            ctx = self.repo.changectx(rowrev)
            color = self.annotate_colormap.get_color(ctx, basedate)
            model.append((revid, text, tip, color))
        if thread.isAlive():
            return True
        else:
            self.stbar.end()
            return False

    def _ann_selection_changed(self, treeview):
        """
        User selected line of annotate output, describe revision
        responsible for this line in the status bar
        """
        (path, focus) = treeview.get_cursor()
        model = treeview.get_model()
        if path is not None and model is not None:
            iter = model.get_iter(path)
            self.currev = model[iter][self.COL_REVID]
            self.path = model.path
            self.stbar.set_status_text(model[iter][self.COL_TOOLTIP])

    def _ann_button_release(self, widget, event):
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            self._ann_popup_menu(widget, event.button, event.time)
        return False

    def _ann_popup_menu(self, treeview, button=0, time=0):
        self.ann_cmenu.popup(None, None, None, button, time)
        return True

    def _ann_row_act(self, tree, path, column):
        self.ann_cmenu.get_children()[0].activate()

    def make_toolbutton(self, stock, label, handler,
            userdata=None, menu=None, tip=None):
        if menu:
            tbutton = gtk.MenuToolButton(stock)
            tbutton.set_menu(menu)
        else:
            tbutton = gtk.ToolButton(stock)

        if tip:
            tbutton.set_tooltip(self.tooltips, tip)
        tbutton.set_use_underline(True)
        tbutton.set_label(label)
        tbutton.connect('clicked', handler, userdata)
        return tbutton

def create_menu(label, callback):
    menuitem = gtk.MenuItem(label, True)
    menuitem.connect('activate', callback)
    menuitem.set_border_width(1)
    return menuitem

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

    dialog = DataMineDialog(u, repo, cwd, files, cmdoptions, True)
    dialog.display()
    if len(files) > 1:
        for f in files:
            dialog.add_annotate_page(f, '.')
    elif files and not os.path.isdir(files[0]):
        dialog.add_annotate_page(files[0], '.')
    else:
        dialog.add_search_page()

    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or os.getcwd()
    run(**opts)

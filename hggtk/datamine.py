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
from hglib import Hg
from gdialog import *
from vis.colormap import AnnotateColorMap, AnnotateColorSaturation

class DataMineDialog(GDialog):
    COL_REVID = 0
    COL_TEXT = 1
    COL_TOOLTIP = 2
    COL_PATH = 3

    def get_title(self):
        return 'DataMining - ' + os.path.basename(self.repo.root)

    def get_icon(self):
        return 'menulog.ico'

    def parse_opts(self):
        # Disable quiet to get full log info
        self.ui.quiet = False

    def get_tbbuttons(self):
        return [ self.make_toolbutton(gtk.STOCK_FIND, 'New Search', 
            self._search_clicked, tip='Open new search tab')
            ]

    def prepare_display(self):
        pass

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
        vbox = gtk.VBox()
        notebook = gtk.Notebook()
        notebook.set_tab_pos(gtk.POS_LEFT)
        notebook.set_scrollable(True)
        notebook.popup_enable()
        notebook.show()
        self.notebook = notebook
        vbox.pack_start(self.notebook, True, True, 2)
        self.pbar = gtk.ProgressBar()
        vbox.pack_start(self.pbar, False, False, 2)
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
        from status import GStatus
        from gtools import cmdtable
        rev1 = long(self.currev)
        rev0 = self.repo.changelog.parentrevs(rev1)[0]
        statopts = self.merge_opts(cmdtable['gstatus|gst'][1],
                ('include', 'exclude', 'git'))
        statopts['rev'] = ['%u:%u' % (rev0, rev1)]
        statopts['modified'] = True
        statopts['added'] = True
        statopts['removed'] = True
        dialog = GStatus(self.ui, self.repo, self.cwd, [], statopts, False)
        dialog.display()

    def _cmenu_annotate(self, menuitem):
        self.add_annotate_page(self.curpath, self.currev)

    def _cmenu_file_log(self, menuitem):
        from history import GLog
        from gtools import cmdtable
        statopts = self.merge_opts(cmdtable['glog|ghistory'][1],
                ('include', 'exclude', 'git'))
        dialog = GLog(self.ui, self.repo, self.cwd, [self.repo.root],
                statopts, False)
        dialog.curfile = self.curpath
        dialog.display()

    def _grep_button_release(self, widget, event):
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            self._grep_popup_menu(widget, event.button, event.time)
        return False

    def _grep_popup_menu(self, treeview, button=0, time=0):
        self.grep_cmenu.popup(None, None, None, button, time)
        return True

    def _grep_row_act(self, tree, path, column) :
        """Default action is the first entry in the context menu
        """
        self.grep_cmenu.get_children()[0].activate()
        return True

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
        hbox.pack_start(gtk.Label('Regexp:'), False, False, 4)
        regexp = gtk.Entry()
        hbox.pack_start(regexp, True, True, 4)
        self.tooltips.set_tip(hbox, 'Regular expression')
        vbox.pack_start(hbox, False, False)

        table = gtk.Table(2, 2, False)
        follow = gtk.CheckButton('Follow copies and renames')
        ignorecase = gtk.CheckButton('Ignore case')
        linenum = gtk.CheckButton('Show line numbers')
        showall = gtk.CheckButton('Show all matching revisions')
        table.attach(follow, 0, 1, 0, 1, gtk.FILL, 0, 4, 3)
        table.attach(ignorecase, 0, 1, 1, 2, gtk.FILL, 0, 4, 3)
        table.attach(linenum, 1, 2, 0, 1, gtk.FILL, 0, 4, 3)
        table.attach(showall, 1, 2, 1, 2, gtk.FILL, 0, 4, 3)
        vbox.pack_start(table, False, False)

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
        num = self.notebook.append_page(frame, None)
        objs = (treeview, frame, regexp, follow, ignorecase,
                linenum, showall, search)
        search.connect('clicked', self.trigger_search, objs)
        close.connect('clicked', self.close_page)
        if hasattr(self.notebook, 'set_tab_reorderable'):
            self.notebook.set_tab_reorderable(frame, True)
        self.notebook.set_current_page(num)

    def trigger_search(self, button, objs):
        def thread_func(q, *args):
            hg = Hg(self.repo.root)
            out = hg.command(*args)
            for line in out.splitlines():
                q.put(line)

        (treeview, frame, regexp, follow, ignorecase, 
                linenum, showall, search) = objs
        re = regexp.get_text()
        if not re:
            Prompt('No regular expression given',
                    'You must provide a search expression', self).run()
            regexp.grab_focus()
            return
        
        q = Queue.Queue()
        args = [q, 'grep']
        if follow.get_active():     args.append('--follow')
        if ignorecase.get_active(): args.append('--ignore-case')
        if linenum.get_active():    args.append('--line-number')
        if showall.get_active():    args.append('--all')
        args.append(re)
        model = treeview.get_model()
        model.clear()

        self.pbar.set_fraction(0.0)
        thread = threading.Thread(target=thread_func, args=args)
        thread.start()
        gobject.timeout_add(50, self.grep_wait, thread, q, treeview, search)
        self.notebook.set_tab_label_text(frame, 'search "%s"' % re.split()[0])
        search.set_sensitive(False)

    def grep_wait(self, thread, q, treeview, search):
        """
        Handle all the messages currently in the queue (if any).
        """
        while q.qsize():
            line = q.get(0).rstrip('\r\n')
            try:
                (path, revid, text) = line.split(':', 2)
            except ValueError:
                continue
            rev = long(revid)
            ctx = self.repo.changectx(rev)
            author = util.shortuser(ctx.user())
            summary = ctx.description().replace('\0', '')
            summary = summary.split('\n')[0]
            date = time.strftime("%y-%m-%d %H:%M", time.gmtime(ctx.date()[0]))
            tip = author+'@'+revid+' '+date+' "'+summary+'"'
            model = treeview.get_model()
            model.append((revid, text, tip, path))
        if thread.isAlive():
            self.pbar.pulse()
            return True
        else:
            search.set_sensitive(True)
            self.pbar.set_fraction(1.0)
            return False

    def _grep_selection_changed(self, treeview):
        """callback for when the user selects grep output."""
        (path, focus) = treeview.get_cursor()
        model = treeview.get_model()
        if path is not None and model is not None:
            iter = model.get_iter(path)
            self.currev = model[iter][self.COL_REVID]
            self.curpath = model[iter][self.COL_PATH]

    def close_page(self, button):
        num = self.notebook.get_current_page()
        if num != -1:
            self.notebook.remove_page(num)

    def add_annotate_page(self, path, revid):
        frame = gtk.Frame()
        frame.set_border_width(10)
        vbox = gtk.VBox()

        hbox = gtk.HBox()
        hbox.pack_start(gtk.Label('File History Annotation'))
        select = gtk.Button('Select')
        close = gtk.Button('Close')
        hbox.pack_start(select, False, False)
        hbox.pack_start(close, False, False)
        vbox.pack_start(hbox, False, False)

        # TODO
        select.set_sensitive(False)
        revselect = revid

        follow = gtk.CheckButton('Follow copies and renames')
        vbox.pack_start(follow, False, False)

        treeview = gtk.TreeView()
        treeview.get_selection().set_mode(gtk.SELECTION_SINGLE)
        treeview.set_property('fixed-height-mode', True)
        treeview.set_border_width(0)
        treeview.connect("cursor-changed", self._ann_selection_changed)
        treeview.connect('button-release-event', self._ann_button_release)
        treeview.connect('popup-menu', self._ann_popup_menu)
        treeview.connect('row-activated', self._ann_row_act)

        results = gtk.ListStore(str, str, str)
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
            column.set_cell_data_func(cell, self.ann_text_color)
            treeview.append_column(column)
        if hasattr(treeview, 'set_tooltip_column'):
            treeview.set_tooltip_column(self.COL_TOOLTIP)
        results.path = path
        results.rev = revid
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(treeview)
        vbox.pack_start(scroller, True, True)
        frame.add(vbox)
        frame.show_all()
        num = self.notebook.append_page_menu(frame, 
                gtk.Label(os.path.basename(path) + '@' + revid),
                gtk.Label(path + '@' + revid))
        objs = (treeview, path, revselect, select, follow)
        select.connect('clicked', self.select_rev, objs)
        close.connect('clicked', self.close_page)
        if hasattr(self.notebook, 'set_tab_reorderable'):
            self.notebook.set_tab_reorderable(frame, True)
        self.notebook.set_current_page(num)
        self.select_rev(select, objs)

    def _ann_selection_changed(self, treeview):
        """callback for when the user selects grep output."""
        (path, focus) = treeview.get_cursor()
        model = treeview.get_model()
        if path is not None and model is not None:
            iter = model.get_iter(path)
            self.currev = model[iter][self.COL_REVID]
            self.path = model.path

    def ann_text_color(self, column, text_renderer, model, row_iter):
        row_rev = model[row_iter][self.COL_REVID]
        ctx = self.repo.changectx(row_rev)
        basedate = self.repo.changectx(long(model.rev)).date()[0]
        text_renderer.set_property('foreground', 
                self.annotate_colormap.get_color(ctx, basedate))
        text_renderer.set_property('background', 'black')

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

    def select_rev(self, button, objs):
        def thread_func(q, *args):
            hg = Hg(self.repo.root)
            out = hg.command(*args)
            for line in out.splitlines():
                q.put(line)

        (treeview, path, revselect, select, follow) = objs
        q = Queue.Queue()
        hgcmd = [q, 'annotate']
        if follow.get_active():     hgcmd.append('--follow')
        # TODO
        hgcmd.append('--rev')
        hgcmd.append(revselect)
        hgcmd.append(path)
        model = treeview.get_model()
        model.clear()

        self.pbar.set_fraction(0.0)
        thread = threading.Thread(target=thread_func, args=hgcmd)
        thread.start()
        gobject.timeout_add(50, self.annotate_wait, thread, q, treeview, select)
        select.set_sensitive(False)

    def annotate_wait(self, thread, q, treeview, select):
        """
        Handle all the messages currently in the queue (if any).
        """
        while q.qsize():
            line = q.get(0).rstrip('\r\n')
            try:
                (revid, text) = line.split(':', 1)
            except ValueError:
                continue
            rev = long(revid)
            ctx = self.repo.changectx(rev)
            author = util.shortuser(ctx.user())
            summary = ctx.description().replace('\0', '')
            summary = summary.split('\n')[0]
            date = time.strftime("%y-%m-%d %H:%M", time.gmtime(ctx.date()[0]))
            tip = author+'@'+revid+' '+date+' "'+summary+'"'
            model = treeview.get_model()
            model.append((revid, text, tip))
        if thread.isAlive():
            self.pbar.pulse()
            return True
        else:
            select.set_sensitive(True)
            self.pbar.set_fraction(1.0)
            return False

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

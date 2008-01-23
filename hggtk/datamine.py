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
from vis.colormap import AnnotateColorMap, AnnotateColorSaturation

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
        vbox = gtk.VBox()
        notebook = gtk.Notebook()
        notebook.set_tab_pos(gtk.POS_LEFT)
        notebook.set_scrollable(True)
        notebook.popup_enable()
        notebook.show()
        self.notebook = notebook
        vbox.pack_start(self.notebook, True, True, 2)
        hbox = gtk.HBox()
        self.revisiondesc = gtk.Label('')
        self.revisiondesc.set_alignment(0.0, 0.0)
        self.pbar = gtk.ProgressBar()
        hbox.pack_start(self.pbar, False, False, 2)
        hbox.pack_start(self.revisiondesc, True, True, 2)
        vbox.pack_start(hbox, False, False, 2)
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
        dialog.open_with_file(self.curpath)
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
        (treeview, frame, regexp, follow, ignorecase, 
                linenum, showall, search) = objs
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
        args.append(re)
        thread = threading.Thread(target=hgcmd_toq, args=args)
        thread.start()

        model = treeview.get_model()
        model.clear()
        self.pbar.set_fraction(0.0)
        search.set_sensitive(False)
        self.revisiondesc.set_text('hg ' + ' '.join(args[2:]))
        self.notebook.set_tab_label_text(frame, 'search "%s"' % re.split()[0])
        gobject.timeout_add(50, self.grep_wait, thread, q, model, search)

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
            self.pbar.pulse()
            return True
        else:
            search.set_sensitive(True)
            self.pbar.set_fraction(1.0)
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
            self.revisiondesc.set_text(model[iter][self.COL_TOOLTIP])

    def close_page(self, button):
        '''Close page button has been pressed'''
        num = self.notebook.get_current_page()
        if num != -1:
            self.notebook.remove_page(num)

    def add_annotate_page(self, path, revid):
        '''
        Add new annotation page to notebook.  Start scan of
        file 'path' revision history, start annotate of supplied
        revision 'revid'.
        '''
        frame = gtk.Frame()
        frame.set_border_width(10)
        vbox = gtk.VBox()

        hbox = gtk.HBox()
        lbl = gtk.Label()
        lbl.set_alignment(0.0, 0.0)
        hbox.pack_start(lbl)
        select = gtk.Button('Select')
        close = gtk.Button('Close')
        hbox.pack_start(select, False, False)
        hbox.pack_start(close, False, False)
        vbox.pack_start(hbox, False, False)

        rev = long(revid)
        hbox = gtk.HBox()
        revselect = gtk.HScale()
        revselect.set_digits(0)
        revselect.set_range(0, self.repo.changelog.count()-1)
        revselect.set_value(rev)
        revselect.connect('value-changed', self.rev_select_changed, path, lbl)
        hbox.pack_start(revselect, True, True)
        if path not in self.revisions:
            self.revisions[path] = []
            self.load_file_history(path, hbox)
        self.filecurrev[path] = rev
        lbl.set_text(path + ': ' + self.get_rev_desc(rev))

        next = gtk.ToolButton(gtk.STOCK_MEDIA_FORWARD)
        next.connect('clicked', self.next_rev, revselect, path)
        prev = gtk.ToolButton(gtk.STOCK_MEDIA_REWIND)
        prev.connect('clicked', self.prev_rev, revselect, path)
        hbox.pack_start(prev, False, False)
        hbox.pack_start(next, False, False)
        vbox.pack_start(hbox, False, False)

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
        vbox.pack_start(scroller, True, True)
        frame.add(vbox)
        frame.show_all()
        num = self.notebook.append_page_menu(frame, 
                gtk.Label(os.path.basename(path) + '@' + revid),
                gtk.Label(path + '@' + revid))
        objs = (frame, treeview.get_model(), path)
        select.connect('clicked', self.trigger_annotate, objs)
        close.connect('clicked', self.close_page)
        if hasattr(self.notebook, 'set_tab_reorderable'):
            self.notebook.set_tab_reorderable(frame, True)
        self.notebook.set_current_page(num)
        self.trigger_annotate(select, objs)

    def rev_select_changed(self, range, path, label):
        '''
        User has moved the revision timeline slider.  If it
        has hit apon (or passed) a revision that modifies this file,
        remember this revision as the 'current' for this file, and
        update the label at the top of the page.
        '''
        rev = long(range.get_value())
        if rev in self.revisions[path]:
            self.filecurrev[path] = rev
            label.set_text(path + ': ' + self.get_rev_desc(rev))
            return
        # Detect whether the user has passed one or more spots
        cur = self.filecurrev[path]
        revs = self.revisions[path]
        i = revs.index(cur)
        try:
            while i and rev >= revs[i-1]:
                i += -1
            while rev <= revs[i+1]:
                i += 1
        except IndexError:
            pass
        if revs[i] != cur:
            newrev = revs[i]
            self.filecurrev[path] = newrev
            label.set_text(path + ': ' + self.get_rev_desc(newrev))

    def load_file_history(self, path, hbox):
        '''
        When a new annotation page is opened, this function is
        to retrieve the revision history of the specified file.
        The revision slider on this page is frozen until this
        scan is completed.
        '''
        q = Queue.Queue()
        args = [self.repo.root, q, 'log', '--quiet', path]
        thread = threading.Thread(target=hgcmd_toq, args=args)
        thread.start()

        self.pbar.set_fraction(0.0)
        self.revisiondesc.set_text('hg ' + ' '.join(args[2:]))
        gobject.timeout_add(50, self.hist_wait, thread, q, path, hbox)
        hbox.set_sensitive(False)

    def hist_wait(self, thread, q, path, hbox):
        """
        Handle output from 'hg log -qf path'
        """
        while q.qsize():
            line = q.get(0).rstrip('\r\n')
            try:
                (revid, node) = line.split(':', 1)
            except ValueError:
                continue
            self.revisions[path].append(long(revid))
        if thread.isAlive():
            self.pbar.pulse()
            return True
        else:
            hbox.set_sensitive(True)
            self.pbar.set_fraction(1.0)
            return False

    def next_rev(self, button, revselect, path):
        '''
        User has pressed the 'next version' button on an annotate page.
        Move the slider to the next highest revision that is applicable
        for this file.
        '''
        cur = self.filecurrev[path]
        revs = self.revisions[path]
        i = revs.index(cur)
        if i > 0:
            revselect.set_value(revs[i-1])

    def prev_rev(self, button, revselect, path):
        '''
        User has pressed the 'prev version' button on an annotate page.
        Move the slider to the next lowest revision that is applicable
        for this file.
        '''
        cur = self.filecurrev[path]
        revs = self.revisions[path]
        i = revs.index(cur)
        if i < len(revs) - 1:
            revselect.set_value(revs[i+1])

    def _ann_selection_changed(self, treeview):
        """callback for when the user selects grep output."""
        (path, focus) = treeview.get_cursor()
        model = treeview.get_model()
        if path is not None and model is not None:
            iter = model.get_iter(path)
            self.currev = model[iter][self.COL_REVID]
            self.path = model.path
            self.revisiondesc.set_text(model[iter][self.COL_TOOLTIP])

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

    def trigger_annotate(self, button, objs):
        '''
        User has selected a file revision to annotate.  Trigger a
        background thread to perform the annotation.  Disable the select
        button until this operation is complete.
        '''
        (frame, model, path) = objs
        q = Queue.Queue()
        revid = str(self.filecurrev[path])
        args = [self.repo.root, q, 'annotate', '--rev']
        args.append(revid)
        args.append(path)
        thread = threading.Thread(target=hgcmd_toq, args=args)
        thread.start()

        model.clear()
        self.pbar.set_fraction(0.0)
        path = os.path.basename(path)
        self.notebook.set_tab_label_text(frame, path+'@'+revid)
        self.revisiondesc.set_text('hg ' + ' '.join(args[2:]))
        gobject.timeout_add(50, self.annotate_wait, thread, q, model, button)
        button.set_sensitive(False)

    def annotate_wait(self, thread, q, model, button):
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
            self.pbar.pulse()
            return True
        else:
            button.set_sensitive(True)
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
    #dialog.add_annotate_page('hggtk/history.py', '719')

    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or os.getcwd()
    run(**opts)

#
# Data Mining dialog for TortoiseHg and Mercurial
#
# Copyright (C) 2008 Steve Borho <steve@borho.org>

import gtk
import gobject
import os
import pango
import Queue
import threading

from mercurial import util

from thgutil.i18n import _
from thgutil.hglib import *
from thgutil import thread2

from hggtk.logview import treemodel
from hggtk.logview.colormap import AnnotateColorMap, AnnotateColorSaturation
from hggtk.logview.treeview import TreeView as LogTreeView

from hggtk import gtklib, gdialog, changeset

class DataMineDialog(gdialog.GDialog):
    COL_REVID = 0
    COL_TEXT = 1
    COL_TOOLTIP = 2
    COL_PATH = 3
    COL_COLOR = 4
    COL_USER = 5
    COL_LINENUM = 6

    def get_title(self):
        return _('DataMining') + ' - ' + toutf(os.path.basename(self.repo.root))

    def get_icon(self):
        return 'menurepobrowse.ico'

    def parse_opts(self):
        pass

    def get_tbbuttons(self):
        self.stop_button = self.make_toolbutton(gtk.STOCK_STOP, _('Stop'),
                self.stop_current_search,
                tip=_('Stop operation on current tab'))
        return [
            self.make_toolbutton(gtk.STOCK_FIND, _('New Search'),
                self.search_clicked,
                tip=_('Open new search tab')),
            self.stop_button
            ]

    def prepare_display(self):
        root = self.repo.root
        cf = []
        for f in self.pats:
            if os.path.isfile(f):
                cf.append(util.canonpath(root, self.cwd, f))
            elif os.path.isdir(f):
                gdialog.Prompt(_('Invalid path'),
                       _('Cannot annotate directory: %s') % f, None).run()
        for f in cf:
            self.add_annotate_page(f, '.')
        if not self.notebook.get_n_pages():
            self.add_search_page()
        os.chdir(root)

    def save_settings(self):
        settings = gdialog.GDialog.save_settings(self)
        return settings

    def load_settings(self, settings):
        gdialog.GDialog.load_settings(self, settings)
        self.connect('thg-close', self.close_current_page)
        self.tabwidth = gettabwidth(self.ui)

    def get_body(self):
        """ Initialize the Dialog. """
        self.grep_cmenu = self.grep_context_menu()
        self.changedesc = {}
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
        self.stbar.sttext.set_property('use-markup', True)
        vbox.pack_start(self.stbar, False, False, 2)
        self.stop_button.set_sensitive(False)
        return vbox

    def _destroying(self, gtkobj):
        self.stop_all_searches()
        gdialog.GDialog._destroying(self, gtkobj)

    def ann_header_context_menu(self, treeview):
        menu = gtk.Menu()
        button = gtk.CheckMenuItem(_('Filename'))
        button.connect('toggled', self.toggle_annatate_columns, treeview, 2)
        menu.append(button)
        button = gtk.CheckMenuItem(_('User'))
        button.connect('toggled', self.toggle_annatate_columns, treeview, 3)
        menu.append(button)
        menu.show_all()
        return menu

    def grep_context_menu(self):
        menu = gtk.Menu()
        menu.append(create_menu(_('di_splay change'), self.cmenu_display))
        menu.append(create_menu(_('_annotate file'), self.cmenu_annotate))
        menu.append(create_menu(_('_file history'), self.cmenu_file_log))
        menu.show_all()
        return menu

    def annotate_context_menu(self, objs):
        menu = gtk.Menu()
        menu.append(create_menu(_('_zoom to change'), self.cmenu_zoom, objs))
        menu.append(create_menu(_('di_splay change'), self.cmenu_display))
        menu.append(create_menu(_('_annotate parent'),
            self.annotate_parent, objs))
        menu.show_all()
        return menu

    def annotate_parent(self, menuitem, objs):
        if not self.currev:
            return
        parent = self.repo[self.currev].parents()[0].rev()
        self.trigger_annotate(parent, objs)

    def cmenu_zoom(self, menuitem, objs):
        (frame, treeview, path, graphview) = objs
        graphview.scroll_to_revision(int(self.currev))
        graphview.set_revision_id(int(self.currev))

    def cmenu_display(self, menuitem):
        statopts = {'rev' : [self.currev] }
        dlg = changeset.ChangeSet(self.ui, self.repo, self.cwd, [], statopts)
        dlg.display()

    def cmenu_annotate(self, menuitem):
        self.add_annotate_page(self.curpath, self.currev)

    def cmenu_file_log(self, menuitem):
        from hggtk import history
        dlg = history.GLog(self.ui, self.repo, self.cwd, [self.repo.root], {})
        dlg.open_with_file(self.curpath)
        dlg.display()

    def grep_button_release(self, widget, event):
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            self.grep_popup_menu(widget, event.button, event.time)
        return False

    def grep_popup_menu(self, treeview, button=0, time=0):
        self.grep_cmenu.popup(None, None, None, button, time)
        return True

    def grep_thgdiff(self, treeview):
        self._do_diff([], {'change' : self.currev}, modal=True)

    def grep_row_act(self, tree, path, column):
        'Default action is the first entry in the context menu'
        self.grep_cmenu.get_children()[0].activate()
        return True

    def get_rev_desc(self, rev):
        if rev in self.changedesc:
            return self.changedesc[rev]
        ctx = self.repo[rev]
        author = util.shortuser(ctx.user())
        summary = ctx.description().replace('\0', '')
        summary = toutf(summary.split('\n')[0])
        summary = gtklib.markup_escape_text(summary)
        date = displaytime(ctx.date())
        desc = toutf(author+'@'+str(rev)+' '+date+' "') + summary + '"'
        author = toutf(author)
        self.changedesc[rev] = (desc, author)
        return (desc, author)

    def search_clicked(self, button, data):
        self.add_search_page()

    def create_tab_close_button(self):
        button = gtk.Button()
        iconBox = gtk.HBox(False, 0)
        image = gtk.Image()
        image.set_from_stock(gtk.STOCK_CLOSE, gtk.ICON_SIZE_MENU)
        gtk.Button.set_relief(button, gtk.RELIEF_NONE)
        settings = gtk.Widget.get_settings(button)
        (w,h) = gtk.icon_size_lookup_for_settings(settings, gtk.ICON_SIZE_MENU)
        gtk.Widget.set_size_request(button, w + 4, h + 4)
        image.show()
        iconBox.pack_start(image, True, False, 0)
        button.add(iconBox)
        iconBox.show()
        return button

    def add_search_page(self):
        frame = gtk.Frame()
        frame.set_border_width(10)
        vbox = gtk.VBox()

        search_hbox = gtk.HBox()
        regexp = gtk.Entry()
        includes = gtk.Entry()
        if self.cwd.startswith(self.repo.root):
            includes.set_text(util.canonpath(self.repo.root, self.cwd, '.'))
        excludes = gtk.Entry()
        search = gtk.Button(_('Search'))
        search_hbox.pack_start(gtk.Label(_('Regexp:')), False, False, 4)
        search_hbox.pack_start(regexp, True, True, 4)
        search_hbox.pack_start(gtk.Label(_('Includes:')), False, False, 4)
        search_hbox.pack_start(includes, True, True, 4)
        search_hbox.pack_start(gtk.Label(_('Excludes:')), False, False, 4)
        search_hbox.pack_start(excludes, True, True, 4)
        search_hbox.pack_start(search, False, False)
        self.tooltips.set_tip(search, _('Start this search'))
        self.tooltips.set_tip(regexp, _('Regular expression search pattern'))
        self.tooltips.set_tip(includes, _('Comma separated list of'
                ' inclusion patterns.  By default, the entire repository'
                ' is searched.'))
        self.tooltips.set_tip(excludes, _('Comma separated list of'
                ' exclusion patterns.  Exclusion patterns are applied'
                ' after inclusion patterns.'))
        vbox.pack_start(search_hbox, False, False, 4)

        hbox = gtk.HBox()
        follow = gtk.CheckButton(_('Follow copies and renames'))
        ignorecase = gtk.CheckButton(_('Ignore case'))
        linenum = gtk.CheckButton(_('Show line numbers'))
        showall = gtk.CheckButton(_('Show all matching revisions'))
        hbox.pack_start(follow, False, False, 4)
        hbox.pack_start(ignorecase, False, False, 4)
        hbox.pack_start(linenum, False, False, 4)
        hbox.pack_start(showall, False, False, 4)
        vbox.pack_start(hbox, False, False, 4)

        treeview = gtk.TreeView()
        treeview.get_selection().set_mode(gtk.SELECTION_SINGLE)
        treeview.set_rules_hint(True)
        treeview.set_property('fixed-height-mode', True)
        treeview.connect("cursor-changed", self.grep_selection_changed)
        treeview.connect('button-release-event', self.grep_button_release)
        treeview.connect('popup-menu', self.grep_popup_menu)
        treeview.connect('row-activated', self.grep_row_act)

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)
        mod = gtklib.get_thg_modifier()
        key, modifier = gtk.accelerator_parse(mod+'d')
        treeview.add_accelerator('thg-diff', accelgroup, key,
                        modifier, gtk.ACCEL_VISIBLE)
        treeview.connect('thg-diff', self.grep_thgdiff)

        results = gtk.ListStore(str, str, str, str)
        treeview.set_model(results)
        treeview.set_search_equal_func(self.search_in_grep)
        for title, width, col, emode in (
                (_('Rev'), 10, self.COL_REVID, pango.ELLIPSIZE_NONE),
                (_('File'), 25, self.COL_PATH, pango.ELLIPSIZE_START),
                (_('Matches'), 80, self.COL_TEXT, pango.ELLIPSIZE_END)):
            cell = gtk.CellRendererText()
            cell.set_property('width-chars', width)
            cell.set_property('ellipsize', emode)
            cell.set_property('family', 'Monospace')
            column = gtk.TreeViewColumn(title)
            column.set_resizable(True)
            column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            column.set_fixed_width(cell.get_size(treeview)[2])
            column.pack_start(cell, expand=True)
            column.add_attribute(cell, 'text', col)
            treeview.append_column(column)
        if hasattr(treeview, 'set_tooltip_column'):
            treeview.set_tooltip_column(self.COL_TOOLTIP)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(treeview)
        vbox.pack_start(scroller, True, True)
        frame.add(vbox)
        frame.show_all()

        hbox = gtk.HBox()
        lbl = gtk.Label(_('Search %d') % self.newpagecount)
        close = self.create_tab_close_button()
        close.connect('clicked', self.close_page, frame)
        hbox.pack_start(lbl, True, True, 2)
        hbox.pack_start(close, False, False)
        hbox.show_all()
        num = self.notebook.append_page(frame, hbox)

        self.newpagecount += 1
        objs = (treeview.get_model(), frame, regexp, follow, ignorecase,
                excludes, includes, linenum, showall, search_hbox)
        # Clicking 'search' or hitting Enter in any text entry triggers search
        search.connect('clicked', self.trigger_search, objs)
        regexp.connect('activate', self.trigger_search, objs)
        includes.connect('activate', self.trigger_search, objs)
        excludes.connect('activate', self.trigger_search, objs)
        # Includes/excludes must disable following copies
        objs = (includes, excludes, follow)
        includes.connect('changed', self.update_following_possible, objs)
        excludes.connect('changed', self.update_following_possible, objs)

        if hasattr(self.notebook, 'set_tab_reorderable'):
            self.notebook.set_tab_reorderable(frame, True)
        self.notebook.set_current_page(num)
        regexp.grab_focus()

    def search_in_grep(self, model, column, key, iter):
        """Searches all fields shown in the tree when the user hits crtr+f,
        not just the ones that are set via tree.set_search_column.
        Case insensitive
        """
        key = key.lower()
        for col in (self.COL_PATH, self.COL_TEXT):
            if key in model.get_value(iter, col).lower():
                return False
        return True

    def trigger_search(self, button, objs):
        (model, frame, regexp, follow, ignorecase,
                excludes, includes, linenum, showall, search_hbox) = objs
        retext = regexp.get_text()
        if not retext:
            gdialog.Prompt(_('No regular expression given'),
                   _('You must provide a search expression'), self).run()
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
        args.append(retext)
        thread = thread2.Thread(target=hgcmd_toq, args=args)
        thread.start()
        frame._mythread = thread
        self.stop_button.set_sensitive(True)

        model.clear()
        search_hbox.set_sensitive(False)
        self.stbar.begin()
        self.stbar.set_status_text('hg ' + ' '.join(args[2:]))

        hbox = gtk.HBox()
        lbl = gtk.Label(_('Search "%s"') % retext.split()[0])
        close = self.create_tab_close_button()
        close.connect('clicked', self.close_page, frame)
        hbox.pack_start(lbl, True, True, 2)
        hbox.pack_start(close, False, False)
        hbox.show_all()
        self.notebook.set_tab_label(frame, hbox)

        gobject.timeout_add(50, self.grep_wait, thread, q, model,
                search_hbox, regexp, frame)

    def grep_wait(self, thread, q, model, search_hbox, regexp, frame):
        """
        Handle all the messages currently in the queue (if any).
        """
        while q.qsize():
            line = q.get(0).rstrip('\r\n')
            try:
                (path, revid, text) = line.split(':', 2)
            except ValueError:
                continue
            tip, user = self.get_rev_desc(long(revid))
            if self.tabwidth:
                text = text.expandtabs(self.tabwidth)
            model.append((revid, toutf(text[:512]), tip, toutf(path)))
        if thread.isAlive():
            return True
        else:
            if threading.activeCount() == 1:
                self.stop_button.set_sensitive(False)
            frame._mythread = None
            search_hbox.set_sensitive(True)
            regexp.grab_focus()
            self.stbar.end()
            return False

    def grep_selection_changed(self, treeview):
        """
        Callback for when the user selects grep output.
        """
        (path, focus) = treeview.get_cursor()
        model = treeview.get_model()
        if path is not None and model is not None:
            paths = model.get_iter(path)
            self.currev = model[paths][self.COL_REVID]
            self.curpath = fromutf(model[paths][self.COL_PATH])
            self.stbar.set_status_text(toutf(model[paths][self.COL_TOOLTIP]))

    def close_current_page(self, window):
        num = self.notebook.get_current_page()
        if num != -1 and self.notebook.get_n_pages():
            self.notebook.remove_page(num)
            self.emit_stop_by_name('thg-close')

    def stop_current_search(self, button, widget):
        num = self.notebook.get_current_page()
        frame = self.notebook.get_nth_page(num)
        self.stop_search(frame)

    def stop_all_searches(self):
        for num in xrange(self.notebook.get_n_pages()):
            frame = self.notebook.get_nth_page(num)
            self.stop_search(frame)

    def stop_search(self, frame):
        if getattr(frame, '_mythread', None):
            frame._mythread.terminate()
            frame._mythread.join()
            frame._mythread = None

    def close_page(self, button, widget):
        '''Close page button has been pressed'''
        num = self.notebook.page_num(widget)
        if num != -1 and self.notebook.get_n_pages() > 1:
            self.notebook.remove_page(num)

    def add_header_context_menu(self, col, menu):
        lb = gtk.Label(col.get_title())
        lb.show()
        col.set_widget(lb)
        wgt = lb.get_parent()
        while wgt:
            if type(wgt) == gtk.Button:
                wgt.connect("button-press-event",
                        self.tree_header_button_press, menu)
                break
            wgt = wgt.get_parent()

    def tree_header_button_press(self, widget, event, menu):
        if event.button == 3:
            menu.popup(None, None, None, event.button, event.time)
            return True
        return False

    def update_following_possible(self, widget, objs):
        (includes, excludes, follow) = objs
        allow = not includes.get_text() and not excludes.get_text()
        if not allow:
            follow.set_active(False)
        follow.set_sensitive(allow)

    def add_annotate_page(self, path, revid):
        '''
        Add new annotation page to notebook.  Start scan of
        file 'path' revision history, start annotate of supplied
        revision 'revid'.
        '''
        if revid == '.':
            ctx = self.repo.parents()[0]
            try:
                fctx = ctx.filectx(path)
            except LookupError:
                gdialog.Prompt(_('File is unrevisioned'),
                       _('Unable to annotate ') + path, self).run()
                return
            rev = fctx.filelog().linkrev(fctx.filerev())
            revid = str(rev)
        else:
            rev = long(revid)

        frame = gtk.Frame()
        frame.set_border_width(10)
        vbox = gtk.VBox()

        # File log revision graph
        graphview = LogTreeView(self.repo, 5000, self.stbar)
        graphview.connect('revisions-loaded', self.revisions_loaded, rev)
        graphview.refresh(True, None, {'filehist':path, 'filerev':rev})
        graphview.set_property('rev-column-visible', True)
        graphview.set_property('date-column-visible', True)

        hbox = gtk.HBox()
        followlabel = gtk.Label('')
        follow = gtk.Button(_('Follow'))
        follow.connect('clicked', self.follow_rename)
        follow.hide()
        follow.set_sensitive(False)
        hbox.pack_start(gtk.Label(''), True, True)
        hbox.pack_start(followlabel, False, False)
        hbox.pack_start(follow, False, False)

        # Annotation text tree view
        treeview = gtk.TreeView()
        treeview.get_selection().set_mode(gtk.SELECTION_SINGLE)
        treeview.set_property('fixed-height-mode', True)
        treeview.set_border_width(0)

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)
        mod = gtklib.get_thg_modifier()
        key, modifier = gtk.accelerator_parse(mod+'d')
        treeview.add_accelerator('thg-diff', accelgroup, key,
                        modifier, gtk.ACCEL_VISIBLE)
        treeview.connect('thg-diff', self.annotate_thgdiff)

        results = gtk.ListStore(str, str, str, str, str, str, str)
        treeview.set_model(results)
        treeview.set_search_equal_func(self.search_in_file)

        context_menu = self.ann_header_context_menu(treeview)
        for title, width, col, emode, visible in (
                (_('Line'), 8, self.COL_LINENUM, pango.ELLIPSIZE_NONE, True),
                (_('Rev'), 10, self.COL_REVID, pango.ELLIPSIZE_NONE, True),
                (_('File'), 15, self.COL_PATH, pango.ELLIPSIZE_START, False),
                (_('User'), 15, self.COL_USER, pango.ELLIPSIZE_END, False),
                (_('Source'), 80, self.COL_TEXT, pango.ELLIPSIZE_END, True)):
            cell = gtk.CellRendererText()
            cell.set_property('width-chars', width)
            cell.set_property('ellipsize', emode)
            cell.set_property('family', 'Monospace')
            column = gtk.TreeViewColumn(title)
            column.set_resizable(True)
            column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            column.set_fixed_width(cell.get_size(treeview)[2])
            column.pack_start(cell, expand=True)
            column.add_attribute(cell, 'text', col)
            column.add_attribute(cell, 'background', self.COL_COLOR)
            column.set_visible(visible)
            treeview.append_column(column)
            self.add_header_context_menu(column, context_menu)
        treeview.set_headers_clickable(True)
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
        vbox.pack_start(hbox, False, False)
        frame.add(vbox)
        frame.show_all()

        hbox = gtk.HBox()
        lbl = gtk.Label(toutf(os.path.basename(path) + '@' + revid))
        close = self.create_tab_close_button()
        close.connect('clicked', self.close_page, frame)
        hbox.pack_start(lbl, True, True, 2)
        hbox.pack_start(close, False, False)
        hbox.show_all()
        num = self.notebook.append_page_menu(frame,
                hbox, gtk.Label(toutf(path + '@' + revid)))

        if hasattr(self.notebook, 'set_tab_reorderable'):
            self.notebook.set_tab_reorderable(frame, True)
        self.notebook.set_current_page(num)

        graphview.connect('revision-selected', self.log_selection_changed,
                path, followlabel, follow)

        objs = (frame, treeview, path, graphview)
        graphview.treeview.connect('row-activated', self.log_activate, objs)
        graphview.treeview.connect('button-release-event',
                self.ann_button_release, objs)
        graphview.treeview.connect('popup-menu', self.ann_popup_menu, objs)

        treeview.connect("cursor-changed", self.ann_selection_changed)
        treeview.connect('button-release-event', self.ann_button_release, objs)
        treeview.connect('popup-menu', self.ann_popup_menu, objs)
        treeview.connect('row-activated', self.ann_row_act, objs)

    def search_in_file(self, model, column, key, iter):
        """Searches all fields shown in the tree when the user hits crtr+f,
        not just the ones that are set via tree.set_search_column.
        Case insensitive
        """
        key = key.lower()
        for col in (self.COL_USER, self.COL_TEXT):
            if key in model.get_value(iter, col).lower():
                return False
        return True

    def annotate_thgdiff(self, treeview):
        self._do_diff([], {'change' : self.currev}, modal=True)

    def toggle_annatate_columns(self, button, treeview, col):
        b = button.get_active()
        treeview.get_column(col).set_visible(b)

    def log_selection_changed(self, graphview, path, label, button):
        row = graphview.get_revision()
        rev = row[treemodel.REVID]
        self.currev = str(rev)
        ctx = self.repo[rev]
        filectx = ctx.filectx(path)
        info = filectx.renamed()
        if info:
            (rpath, node) = info
            fl = self.repo.file(rpath)
            frev = fl.linkrev(fl.rev(node))
            button.set_label(toutf('%s@%s' % (rpath, frev)))
            button.show()
            button.set_sensitive(True)
            label.set_text(_('Follow Rename:'))
        else:
            button.hide()
            button.set_sensitive(False)
            label.set_text('')

    def follow_rename(self, button):
        path, rev = button.get_label().rsplit('@', 1)
        self.add_annotate_page(path, rev)

    def log_activate(self, treeview, path, column, objs):
        model = treeview.get_model()
        logiter = model.get_iter(path)
        rev = model.get_value(logiter, treemodel.REVID)
        self.trigger_annotate(rev, objs)

    def revisions_loaded(self, graphview, rev):
        graphview.set_revision_id(rev)
        treeview = graphview.treeview
        path, column = treeview.get_cursor()
        # It's possible that the requested change was not found in the
        # file's filelog history.  In that case, no row will be
        # selected.
        if path != None and column != None:
            treeview.row_activated(path, column)

    def trigger_annotate(self, rev, objs):
        '''
        User has selected a file revision to annotate.  Trigger a
        background thread to perform the annotation.  Disable the select
        button until this operation is complete.
        '''
        (frame, treeview, path, graphview) = objs
        q = Queue.Queue()
        args = [self.repo.root, q, 'annotate', '--follow', '--number',
                '--rev', str(rev), path]
        thread = thread2.Thread(target=hgcmd_toq, args=args)
        thread.start()
        frame._mythread = thread
        self.stop_button.set_sensitive(True)

        # date of selected revision
        ctx = self.repo[long(rev)]
        curdate = ctx.date()[0]
        # date of initial revision
        fctx = self.repo.filectx(path, fileid=0)
        basedate = fctx.date()[0]
        agedays = (curdate - basedate) / (24 * 60 * 60)
        colormap = AnnotateColorSaturation(agedays)

        model, rows = treeview.get_selection().get_selected_rows()
        model.clear()
        self.stbar.begin()
        self.stbar.set_status_text(toutf('hg ' + ' '.join(args[2:])))

        hbox = gtk.HBox()
        lbl = gtk.Label(toutf(os.path.basename(path) + '@' + str(rev)))
        close = self.create_tab_close_button()
        close.connect('clicked', self.close_page, frame)
        hbox.pack_start(lbl, True, True, 2)
        hbox.pack_start(close, False, False)
        hbox.show_all()
        self.notebook.set_tab_label(frame, hbox)

        gobject.timeout_add(50, self.annotate_wait, thread, q, treeview,
                curdate, colormap, frame, rows)

    def annotate_wait(self, thread, q, tview, curdate, colormap, frame, rows):
        """
        Handle all the messages currently in the queue (if any).
        """
        model = tview.get_model()
        while q.qsize():
            line = q.get(0).rstrip('\r\n')
            try:
                (revpath, text) = line.split(':', 1)
                revid, path = revpath.lstrip().split(' ', 1)
                rowrev = long(revid)
            except ValueError:
                continue
            tip, user = self.get_rev_desc(rowrev)
            ctx = self.repo[rowrev]
            color = colormap.get_color(ctx, curdate)
            if self.tabwidth:
                text = text.expandtabs(self.tabwidth)
            model.append((revid, toutf(text[:512]), tip, toutf(path.strip()),
                    color, user, len(model)+1))
        if thread.isAlive():
            return True
        else:
            if threading.activeCount() == 1:
                self.stop_button.set_sensitive(False)
            if rows:
                tview.get_selection().select_path(rows[0])
                tview.scroll_to_cell(rows[0], use_align=True, row_align=0.5)
                tview.grab_focus()
            frame._mythread = None
            self.stbar.end()
            return False

    def ann_selection_changed(self, treeview):
        """
        User selected line of annotate output, describe revision
        responsible for this line in the status bar
        """
        (path, focus) = treeview.get_cursor()
        model = treeview.get_model()
        if path is not None and model is not None:
            anniter = model.get_iter(path)
            self.currev = model[anniter][self.COL_REVID]
            self.path = model.path
            self.stbar.set_status_text(model[anniter][self.COL_TOOLTIP])

    def ann_button_release(self, widget, event, objs):
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            self.ann_popup_menu(widget, event.button, event.time, objs)
        return False

    def ann_popup_menu(self, treeview, button, time, objs):
        ann_cmenu = self.annotate_context_menu(objs)
        ann_cmenu.popup(None, None, None, button, time)
        return True

    def ann_row_act(self, tree, path, column, objs):
        ann_cmenu = self.annotate_context_menu(objs)
        ann_cmenu.get_children()[0].activate()


def create_menu(label, callback, *args):
    menuitem = gtk.MenuItem(label, True)
    menuitem.connect('activate', callback, *args)
    menuitem.set_border_width(1)
    return menuitem

def run(ui, *pats, **opts):
    cmdoptions = {
        'follow':False, 'follow-first':False, 'copies':False, 'keyword':[],
        'limit':0, 'rev':[], 'removed':False, 'no_merges':False, 'date':None,
        'only_merges':None, 'prune':[], 'git':False, 'verbose':False,
        'include':[], 'exclude':[]
    }
    return DataMineDialog(ui, None, None, pats, cmdoptions)

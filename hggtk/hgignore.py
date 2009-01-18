#
# hgignore.py - TortoiseHg's dialog for editing .hgignore
#
# Copyright (C) 2008-2009 Steve Borho <steve@borho.org>
#

import os
import gtk
from dialog import *
from shlib import shell_notify
from mercurial import hg, ui, match

class HgIgnoreDialog(gtk.Window):
    """ Edit a reposiory .hgignore file """
    def __init__(self, root='', fileglob=''):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        self.root = root
        self.set_title('Ignore mask for ' + os.path.basename(root))
        self.set_default_size(630, 400)

        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()

        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)
        self._btn_close = self._toolbutton(gtk.STOCK_CLOSE, 'Close',
                self._close_clicked, 'Close Window')

        tbuttons = [
                self._toolbutton(gtk.STOCK_REFRESH,
                    'Refresh',
                    self._refresh_clicked,
                    tip='Reload hgignore'),
                sep,
                self._btn_close
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        mainvbox = gtk.VBox()
        self.add(mainvbox)
        mainvbox.pack_start(self.tbar, False, False, 2)

        hbox = gtk.HBox()
        lbl = gtk.Label('Glob:')
        lbl.set_property("width-chars", 7)
        lbl.set_alignment(1.0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        glob_entry = gtk.Entry()
        hbox.pack_start(glob_entry, True, True, 4)
        glob_button = gtk.Button('add')
        hbox.pack_start(glob_button, False, False, 4)
        glob_button.connect('clicked', self.add_glob, glob_entry)
        glob_entry.connect('activate', self.add_glob, glob_entry)
        glob_entry.set_text(fileglob)
        self.glob_entry = glob_entry
        mainvbox.pack_start(hbox, False, False)

        hbox = gtk.HBox()
        lbl = gtk.Label('Regexp:')
        lbl.set_property("width-chars", 7)
        lbl.set_alignment(1.0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        regexp_entry = gtk.Entry()
        hbox.pack_start(regexp_entry, True, True, 4)
        regexp_button = gtk.Button('add')
        hbox.pack_start(regexp_button, False, False, 4)
        regexp_button.connect('clicked', self.add_regexp, regexp_entry)
        regexp_entry.connect('activate', self.add_regexp, regexp_entry)
        mainvbox.pack_start(hbox, False, False)

        hbox = gtk.HBox()
        frame = gtk.Frame('Filters')
        hbox.pack_start(frame, True, True, 4)
        pattree = gtk.TreeView()
        pattree.connect('button-press-event', self.tree_button_press)
        pattree.set_reorderable(False)
        sel = pattree.get_selection()
        sel.set_mode(gtk.SELECTION_SINGLE)
        sel.connect("changed", self.pattern_rowchanged)
        col = gtk.TreeViewColumn('Patterns', gtk.CellRendererText(), text=0)
        pattree.append_column(col) 
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.set_border_width(4)
        scrolledwindow.add(pattree)
        pattree.set_headers_visible(False)
        self.pattree = pattree
        frame.add(scrolledwindow)

        frame = gtk.Frame('Unknown Files')
        hbox.pack_start(frame, True, True, 4)
        unknowntree = gtk.TreeView()
        sel = unknowntree.get_selection()
        sel.connect("changed", self.unknown_rowchanged)
        col = gtk.TreeViewColumn('Files', gtk.CellRendererText(), text=0)
        unknowntree.append_column(col) 
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.set_border_width(4)
        scrolledwindow.add(unknowntree)
        model = gtk.ListStore(str)
        unknowntree.set_model(model)
        unknowntree.set_headers_visible(False)
        self.unkmodel = model
        frame.add(scrolledwindow)

        mainvbox.pack_start(hbox, True, True)

        glob_entry.grab_focus()
        self.connect('map_event', self._on_window_map_event)

    def tree_button_press(self, widget, event):
        if event.button != 3:
            return False
        if event.state & (gtk.gdk.SHIFT_MASK | gtk.gdk.CONTROL_MASK):
            return False

        path = widget.get_path_at_pos(int(event.x), int(event.y))[0]
        selection = widget.get_selection()
        rows = selection.get_selected_rows()
        if path[0] not in rows[1]:
            selection.unselect_all()
            selection.select_path(path[0])

        menu = gtk.Menu()
        menuitem = gtk.MenuItem('Remove', True)
        menuitem.connect('activate', self.remove_ignore_line, path[0])
        menuitem.set_border_width(1)
        menu.append(menuitem)
        menu.show_all()
        menu.popup(None, None, None, 0, 0)
        return True

    def remove_ignore_line(self, menuitem, linenum):
        model = self.pattree.get_model()
        del model[linenum]
        del self.ignorelines[linenum]
        self.write_ignore_lines()
        self.refresh()

    def pattern_rowchanged(self, sel):
        model, iter = sel.get_selected()
        if not iter:
            return

    def unknown_rowchanged(self, sel):
        model, iter = sel.get_selected()
        if not iter:
            return
        self.glob_entry.set_text(model[iter][0])

    def add_glob(self, widget, glob_entry):
        newglob = glob_entry.get_text()
        self.ignorelines.append('glob:' + newglob)
        self.write_ignore_lines()
        self.refresh()

    def add_regexp(self, widget, regexp_entry):
        newregexp = regexp_entry.get_text()
        self.ignorelines.append('regexp:' + newregexp)
        self.write_ignore_lines()
        self.refresh()

    def _on_window_map_event(self, event, param):
        self.refresh()

    def _refresh_clicked(self, togglebutton, data=None):
        self.refresh()

    def refresh(self):
        try: repo = hg.repository(ui.ui(), path=self.root)
        except: gtk.main_quit()
        matcher = match.always(repo.root, repo.root)
        changes = repo.dirstate.status(matcher, ignored=False, clean=False, unknown=True)
        (lookup, modified, added, removed, deleted, unknown, ignored, clean) = changes
        self.unkmodel.clear()
        for u in unknown:
            self.unkmodel.append([u])
        try:
            l = open(repo.wjoin('.hgignore'), 'rb').readlines()
            self.doseoln = l[0].endswith('\r\n')
        except IOError, ValueError:
            self.doseoln = os.name == 'nt'
            l = []

        model = gtk.ListStore(str)
        self.ignorelines = []
        for line in l:
            model.append([line.strip()])
            self.ignorelines.append(line.strip())
        self.pattree.set_model(model)
        self.repo = repo

    def write_ignore_lines(self):
        if self.doseoln:
            out = [line + '\r\n' for line in self.ignorelines]
        else:
            out = [line + '\n' for line in self.ignorelines]
        try:
            f = open(self.repo.wjoin('.hgignore'), 'wb')
            f.writelines(out)
            f.close()
        except IOError:
            pass
        shell_notify(self.repo.wjoin('.hgignore'))

    def _close_clicked(self, toolbutton, data=None):
        self.destroy()

    def _toolbutton(self, stock, label, handler, tip):
        tbutton = gtk.ToolButton(stock)
        tbutton.set_label(label)
        tbutton.set_tooltip(self.tips, tip)
        tbutton.connect('clicked', handler)
        return tbutton
        
def run(root='', **opts):
    dialog = HgIgnoreDialog(root)
    dialog.show_all()
    dialog.connect('destroy', gtk.main_quit)
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import hglib
    opts = {'root' : hglib.rootpath()}
    run(**opts)

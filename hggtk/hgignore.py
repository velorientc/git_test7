#
# hgignore.py - TortoiseHg's dialog for editing .hgignore
#
# Copyright (C) 2008-2009 Steve Borho <steve@borho.org>
#

import os
import gtk
from dialog import *
from shlib import shell_notify
from hglib import fromutf, toutf
from mercurial import hg, ui, match

class HgIgnoreDialog(gtk.Window):
    'Edit a reposiory .hgignore file'
    def __init__(self, root='', fileglob=''):
        'Initialize the Dialog'
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        self.root = root
        self.set_title('Ignore filter for ' + os.path.basename(root))
        self.set_default_size(630, 400)
        self.notify_func = None

        mainvbox = gtk.VBox()

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
        glob_entry.set_text(toutf(fileglob))
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
        pattree.set_reorderable(False)
        sel = pattree.get_selection()
        sel.set_mode(gtk.SELECTION_SINGLE)
        col = gtk.TreeViewColumn('Patterns', gtk.CellRendererText(), text=0)
        pattree.append_column(col) 
        pattree.set_headers_visible(False)
        self.pattree = pattree
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.set_border_width(4)
        scrolledwindow.add(pattree)
        vbox = gtk.VBox()
        vbox.pack_start(scrolledwindow, True, True, 2)
        bhbox = gtk.HBox()
        remove = gtk.Button("Remove Selected")
        remove.connect("pressed", self.remove_pressed, sel)
        remove.set_sensitive(False)
        bhbox.pack_start(remove, False, False, 2)
        vbox.pack_start(bhbox, False, False, 2)
        frame.add(vbox)

        frame = gtk.Frame('Unknown Files')
        hbox.pack_start(frame, True, True, 4)
        unknowntree = gtk.TreeView()
        col = gtk.TreeViewColumn('Files', gtk.CellRendererText(), text=0)
        unknowntree.append_column(col) 
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.set_border_width(4)
        scrolledwindow.add(unknowntree)
        model = gtk.ListStore(str, str)
        unknowntree.set_model(model)
        unknowntree.set_headers_visible(False)
        self.unkmodel = model
        vbox = gtk.VBox()
        vbox.pack_start(scrolledwindow, True, True, 2)
        bhbox = gtk.HBox()
        refresh = gtk.Button("Refresh")
        refresh.connect("pressed", self.refresh_clicked, sel)
        bhbox.pack_start(refresh, False, False, 2)
        vbox.pack_start(bhbox, False, False, 2)
        frame.add(vbox)

        mainvbox.pack_start(hbox, True, True)
        self.add(mainvbox)

        glob_entry.grab_focus()
        pattree.get_selection().connect('changed', self.pattree_rowchanged, remove)
        unknowntree.get_selection().connect('changed', self.unknown_rowchanged)
        self.connect('map_event', self.on_window_map_event)

    def remove_pressed(self, widget, selection):
        model, rows = selection.get_selected_rows()
        del model[rows[0]]
        del self.ignorelines[rows[0][0]]
        self.write_ignore_lines()
        self.refresh()

    def pattree_rowchanged(self, sel, remove):
        model, paths = sel.get_selected()
        sensitive = paths and True or False
        remove.set_sensitive(sensitive)

    def unknown_rowchanged(self, sel):
        model, paths = sel.get_selected()
        if not paths:
            return
        self.glob_entry.set_text(model[paths][0])

    def add_glob(self, widget, glob_entry):
        newglob = fromutf(glob_entry.get_text())
        self.ignorelines.append('glob:' + newglob)
        self.write_ignore_lines()
        self.refresh()

    def add_regexp(self, widget, regexp_entry):
        newregexp = regexp_entry.get_text()
        self.ignorelines.append('regexp:' + newregexp)
        self.write_ignore_lines()
        self.refresh()

    def on_window_map_event(self, event, param):
        self.refresh()

    def refresh_clicked(self, togglebutton, data=None):
        self.refresh()

    def set_notify_func(self, func):
        self.notify_func = func

    def refresh(self):
        try: repo = hg.repository(ui.ui(), path=self.root)
        except: gtk.main_quit()
        matcher = match.always(repo.root, repo.root)
        changes = repo.dirstate.status(matcher, ignored=False, clean=False,
                                       unknown=True)
        (lookup, modified, added, removed,
         deleted, unknown, ignored, clean) = changes
        self.unkmodel.clear()
        for u in unknown:
            self.unkmodel.append([toutf(u), u])
        try:
            l = open(repo.wjoin('.hgignore'), 'rb').readlines()
            self.doseoln = l[0].endswith('\r\n')
        except (IOError, ValueError):
            self.doseoln = os.name == 'nt'
            l = []

        model = gtk.ListStore(str)
        self.ignorelines = []
        for line in l:
            model.append([toutf(line.strip())])
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
        if self.notify_func: self.notify_func()
        
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

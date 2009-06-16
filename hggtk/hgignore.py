#
# hgignore.py - TortoiseHg's dialog for editing .hgignore
#
# Copyright (C) 2008-2009 Steve Borho <steve@borho.org>
#

import os
import gtk
import gobject

from mercurial import hg, ui, match

from thgutil.i18n import _
from thgutil import shlib, hglib, paths

from hggtk import gtklib

class HgIgnoreDialog(gtk.Window):
    'Edit a reposiory .hgignore file'
    def __init__(self, fileglob='', *pats):
        'Initialize the Dialog'
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        gtklib.set_tortoise_icon(self, 'ignore.ico')
        gtklib.set_tortoise_keys(self)

        self.root = paths.find_root()
        self.set_title(_('Ignore filter for ') + hglib.toutf(os.path.basename(self.root)))
        self.set_default_size(630, 400)
        self.notify_func = None

        mainvbox = gtk.VBox()

        hbox = gtk.HBox()
        lbl = gtk.Label(_('Glob:'))
        lbl.set_property('width-chars', 9)
        lbl.set_alignment(1.0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        glob_entry = gtk.Entry()
        hbox.pack_start(glob_entry, True, True, 4)
        glob_button = gtk.Button(_('Add'))
        hbox.pack_start(glob_button, False, False, 4)
        glob_button.connect('clicked', self.add_glob, glob_entry)
        glob_entry.connect('activate', self.add_glob, glob_entry)
        glob_entry.set_text(hglib.toutf(fileglob))
        self.glob_entry = glob_entry
        mainvbox.pack_start(hbox, False, False)

        hbox = gtk.HBox()
        lbl = gtk.Label(_('Regexp:'))
        lbl.set_property('width-chars', 9)
        lbl.set_alignment(1.0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        regexp_entry = gtk.Entry()
        hbox.pack_start(regexp_entry, True, True, 4)
        regexp_button = gtk.Button(_('Add'))
        hbox.pack_start(regexp_button, False, False, 4)
        regexp_button.connect('clicked', self.add_regexp, regexp_entry)
        regexp_entry.connect('activate', self.add_regexp, regexp_entry)
        mainvbox.pack_start(hbox, False, False)
        mainvbox.set_border_width(2)

        try: repo = hg.repository(ui.ui(), path=self.root)
        except: self.destroy()
        ignorefiles = [repo.wjoin('.hgignore')]
        for name, value in repo.ui.configitems('ui'):
            if name == 'ignore' or name.startswith('ignore.'):
                ignorefiles.append(os.path.expanduser(value))

        if len(ignorefiles) > 1:
            combo = gtk.combo_box_new_text()
            for f in ignorefiles:
                combo.append_text(hglib.toutf(f))
            combo.set_active(0)
            combo.connect('changed', self.fileselect)
            mainvbox.pack_start(combo, False, False, 4)
        self.ignorefile = ignorefiles[0]

        hbox = gtk.HBox()
        frame = gtk.Frame(_('Filters'))
        hbox.pack_start(frame, True, True, 4)
        pattree = gtk.TreeView()
        pattree.set_enable_search(False)
        pattree.set_reorderable(False)
        sel = pattree.get_selection()
        sel.set_mode(gtk.SELECTION_SINGLE)
        col = gtk.TreeViewColumn(_('Patterns'), gtk.CellRendererText(), text=0)
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
        remove = gtk.Button(_('Remove Selected'))
        remove.connect('pressed', self.remove_pressed, sel)
        remove.set_sensitive(False)
        bhbox.pack_start(remove, False, False, 2)
        vbox.pack_start(bhbox, False, False, 2)
        vbox.set_border_width(2)
        frame.add(vbox)

        frame = gtk.Frame(_('Unknown Files'))
        hbox.pack_start(frame, True, True, 4)
        unknowntree = gtk.TreeView()
        unknowntree.set_search_equal_func(self.unknown_search)
        col = gtk.TreeViewColumn(_('Files'), gtk.CellRendererText(), text=0)
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
        refresh = gtk.Button(_('Refresh'))
        refresh.connect('pressed', self.refresh_clicked, sel)
        self.connect('thg-refresh', self.thgrefresh)
        bhbox.pack_start(refresh, False, False, 2)
        vbox.pack_start(bhbox, False, False, 2)
        vbox.set_border_width(2)
        frame.add(vbox)

        mainvbox.pack_start(hbox, True, True)
        self.add(mainvbox)

        glob_entry.grab_focus()
        pattree.get_selection().connect('changed', self.pattree_rowchanged, remove)
        unknowntree.get_selection().connect('changed', self.unknown_rowchanged)
        gobject.idle_add(self.refresh)

    def fileselect(self, combo):
        'select another ignore file'
        self.ignorefile = hglib.fromutf(combo.get_active_text())
        self.refresh()

    def unknown_search(self, model, column, key, iter):
        'case insensitive filename search'
        key = key.lower()
        if key in model.get_value(iter, 0).lower():
            return False
        return True

    def remove_pressed(self, widget, selection):
        model, rows = selection.get_selected_rows()
        del model[rows[0]]
        del self.ignorelines[rows[0][0]]
        self.write_ignore_lines()
        self.refresh()

    def pattree_rowchanged(self, sel, remove):
        model, ppaths = sel.get_selected()
        sensitive = ppaths and True or False
        remove.set_sensitive(sensitive)

    def unknown_rowchanged(self, sel):
        model, upaths = sel.get_selected()
        if not upaths:
            return
        self.glob_entry.set_text(model[upaths][0])

    def add_glob(self, widget, glob_entry):
        newglob = hglib.fromutf(glob_entry.get_text())
        if newglob == '':
            return
        self.ignorelines.append('glob:' + newglob)
        self.write_ignore_lines()
        self.refresh()

    def add_regexp(self, widget, regexp_entry):
        newregexp = hglib.fromutf(regexp_entry.get_text())
        if newregexp == '':
            return
        self.ignorelines.append('regexp:' + newregexp)
        self.write_ignore_lines()
        self.refresh()

    def thgrefresh(self, window):
        self.refresh()

    def refresh_clicked(self, togglebutton, data=None):
        self.refresh()

    def set_notify_func(self, func):
        self.notify_func = func

    def refresh(self):
        try: repo = hg.repository(ui.ui(), path=self.root)
        except: self.destroy()
        matcher = match.always(repo.root, repo.root)
        changes = repo.dirstate.status(matcher, ignored=False, clean=False,
                                       unknown=True)
        (lookup, modified, added, removed,
         deleted, unknown, ignored, clean) = changes
        self.unkmodel.clear()
        for u in unknown:
            self.unkmodel.append([hglib.toutf(u), u])
        try:
            l = open(self.ignorefile, 'rb').readlines()
            self.doseoln = l[0].endswith('\r\n')
        except (IOError, ValueError, IndexError):
            self.doseoln = os.name == 'nt'
            l = []

        model = gtk.ListStore(str)
        self.ignorelines = []
        for line in l:
            model.append([hglib.toutf(line.strip())])
            self.ignorelines.append(line.strip())
        self.pattree.set_model(model)
        self.repo = repo

    def write_ignore_lines(self):
        if self.doseoln:
            out = [line + '\r\n' for line in self.ignorelines]
        else:
            out = [line + '\n' for line in self.ignorelines]
        try:
            f = open(self.ignorefile, 'wb')
            f.writelines(out)
            f.close()
        except IOError:
            pass
        shlib.shell_notify([self.ignorefile])
        if self.notify_func:
            self.notify_func()

def run(_ui, *pats, **opts):
    if pats and pats[0].endswith('.hgignore'):
        pats = []
    return HgIgnoreDialog(*pats)

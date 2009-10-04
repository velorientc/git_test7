# hgignore.py - TortoiseHg's dialog for editing .hgignore
#
# Copyright 2008 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject
import re

from mercurial import hg, ui, match, util

from tortoisehg.util.i18n import _
from tortoisehg.util import shlib, hglib, paths

from tortoisehg.hgtk import gtklib, gdialog

class HgIgnoreDialog(gtk.Window):
    'Edit a reposiory .hgignore file'
    def __init__(self, fileglob='', *pats):
        'Initialize the Dialog'
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        gtklib.set_tortoise_icon(self, 'ignore.ico')
        gtklib.set_tortoise_keys(self)

        self.root = paths.find_root()
        base = os.path.basename(self.root)
        self.set_title(_('Ignore filter for ') + hglib.toutf(base))
        self.set_default_size(630, 400)
        self.notify_func = None

        # vbox for dialog main
        mainvbox = gtk.VBox()
        self.add(mainvbox)
        mainvbox.set_border_width(2)

        ## hbox for glob entry
        hbox = gtk.HBox()
        mainvbox.pack_start(hbox, False, False)
        lbl = gtk.Label(_('Glob:'))
        hbox.pack_start(lbl, False, False, 4)
        lbl.set_property('width-chars', 9)
        lbl.set_alignment(1.0, 0.5)
        glob_entry = gtk.Entry()
        hbox.pack_start(glob_entry, True, True, 4)
        glob_button = gtk.Button(_('Add'))
        hbox.pack_start(glob_button, False, False, 4)
        glob_button.connect('clicked', self.add_glob, glob_entry)
        glob_entry.connect('activate', self.add_glob, glob_entry)
        glob_entry.set_text(hglib.toutf(fileglob))
        self.glob_entry = glob_entry

        ## hbox for regexp entry
        hbox = gtk.HBox()
        mainvbox.pack_start(hbox, False, False)
        lbl = gtk.Label(_('Regexp:'))
        hbox.pack_start(lbl, False, False, 4)
        lbl.set_property('width-chars', 9)
        lbl.set_alignment(1.0, 0.5)
        regexp_entry = gtk.Entry()
        hbox.pack_start(regexp_entry, True, True, 4)
        regexp_button = gtk.Button(_('Add'))
        hbox.pack_start(regexp_button, False, False, 4)
        regexp_button.connect('clicked', self.add_regexp, regexp_entry)
        regexp_entry.connect('activate', self.add_regexp, regexp_entry)

        try: repo = hg.repository(ui.ui(), path=self.root)
        except: self.destroy()
        ignorefiles = [repo.wjoin('.hgignore')]
        for name, value in repo.ui.configitems('ui'):
            if name == 'ignore' or name.startswith('ignore.'):
                ignorefiles.append(os.path.expanduser(value))

        ## ignore file combo (if need)
        if len(ignorefiles) > 1:
            combo = gtk.combo_box_new_text()
            mainvbox.pack_start(combo, False, False, 4)
            for f in ignorefiles:
                combo.append_text(hglib.toutf(f))
            combo.set_active(0)
            combo.connect('changed', self.fileselect)
        self.ignorefile = ignorefiles[0]

        ## hbox for filter & unknown list
        hbox = gtk.HBox()
        mainvbox.pack_start(hbox, True, True)

        ### frame for filter list & button
        frame = gtk.Frame(_('Filters'))
        hbox.pack_start(frame, True, True, 4)
        vbox = gtk.VBox()
        frame.add(vbox)
        vbox.set_border_width(2)

        #### filter list
        scrolledwindow = gtk.ScrolledWindow()
        vbox.pack_start(scrolledwindow, True, True, 2)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.set_border_width(4)
        pattree = gtk.TreeView()
        scrolledwindow.add(pattree)
        pattree.set_enable_search(False)
        pattree.set_reorderable(False)
        sel = pattree.get_selection()
        sel.set_mode(gtk.SELECTION_SINGLE)
        col = gtk.TreeViewColumn(_('Patterns'), gtk.CellRendererText(), text=0)
        pattree.append_column(col)
        pattree.set_headers_visible(False)
        self.pattree = pattree

        #### remove button
        bhbox = gtk.HBox()
        vbox.pack_start(bhbox, False, False, 2)
        remove = gtk.Button(_('Remove Selected'))
        bhbox.pack_start(remove, False, False, 2)
        remove.connect('pressed', self.remove_pressed, sel)
        remove.set_sensitive(False)

        ### frame for unknown file list & button
        frame = gtk.Frame(_('Unknown Files'))
        hbox.pack_start(frame, True, True, 4)
        vbox = gtk.VBox()
        frame.add(vbox)
        vbox.set_border_width(2)

        #### unknown file list
        scrolledwindow = gtk.ScrolledWindow()
        vbox.pack_start(scrolledwindow, True, True, 2)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.set_border_width(4)
        unknowntree = gtk.TreeView()
        scrolledwindow.add(unknowntree)
        unknowntree.set_search_equal_func(self.unknown_search)
        col = gtk.TreeViewColumn(_('Files'), gtk.CellRendererText(), text=0)
        unknowntree.append_column(col)
        model = gtk.ListStore(str, str)
        unknowntree.set_model(model)
        unknowntree.set_headers_visible(False)
        self.unkmodel = model

        #### refresh button
        bhbox = gtk.HBox()
        vbox.pack_start(bhbox, False, False, 2)
        refresh = gtk.Button(_('Refresh'))
        bhbox.pack_start(refresh, False, False, 2)
        refresh.connect('pressed', self.refresh_clicked, sel)
        self.connect('thg-refresh', self.thgrefresh)

        # prepare to show
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
        newglob = 'glob:' + newglob
        try:
            match.match(self.root, '', [], [newglob])
        except util.Abort, inst:
            gdialog.Prompt(_('Invalid glob expression'), str(inst),
                           self).run()
            return
        self.ignorelines.append(newglob)
        self.write_ignore_lines()
        glob_entry.set_text('')
        self.refresh()

    def add_regexp(self, widget, regexp_entry):
        newregexp = hglib.fromutf(regexp_entry.get_text())
        if newregexp == '':
            return
        try:
            match.match(self.root, '', [], ['relre:' + newregexp])
            re.compile(newregexp)
        except (util.Abort, re.error), inst:
            gdialog.Prompt(_('Invalid regexp expression'), str(inst),
                           self).run()
            return
        self.ignorelines.append('relre:' + newregexp)
        self.write_ignore_lines()
        regexp_entry.set_text('')
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

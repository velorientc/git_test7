# browse.py - TortoiseHg's repository browser
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject
import pango

from mercurial import hg, ui, cmdutil

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths, shlib, menuthg
from tortoisehg.util.hglib import RepoError

from tortoisehg.hgtk import hgcmd, gtklib, gdialog

folderxpm = [
    "17 16 7 1",
    "  c #000000",
    ". c #808000",
    "X c yellow",
    "o c #808080",
    "O c #c0c0c0",
    "+ c white",
    "@ c None",
    "@@@@@@@@@@@@@@@@@",
    "@@@@@@@@@@@@@@@@@",
    "@@+XXXX.@@@@@@@@@",
    "@+OOOOOO.@@@@@@@@",
    "@+OXOXOXOXOXOXO. ",
    "@+XOXOXOXOXOXOX. ",
    "@+OXOXOXOXOXOXO. ",
    "@+XOXOXOXOXOXOX. ",
    "@+OXOXOXOXOXOXO. ",
    "@+XOXOXOXOXOXOX. ",
    "@+OXOXOXOXOXOXO. ",
    "@+XOXOXOXOXOXOX. ",
    "@+OOOOOOOOOOOOO. ",
    "@                ",
    "@@@@@@@@@@@@@@@@@",
    "@@@@@@@@@@@@@@@@@"
    ]
folderpb = gtk.gdk.pixbuf_new_from_xpm_data(folderxpm)

filexpm = [
    "12 12 3 1",
    "  c #000000",
    ". c #ffff04",
    "X c #b2c0dc",
    "X        XXX",
    "X ...... XXX",
    "X ......   X",
    "X .    ... X",
    "X ........ X",
    "X .   .... X",
    "X ........ X",
    "X .     .. X",
    "X ........ X",
    "X .     .. X",
    "X ........ X",
    "X          X"
    ]
filepb = gtk.gdk.pixbuf_new_from_xpm_data(filexpm)

class dirnode(object):
    def __init__(self):
        self.subdirs = {}
        self.files = []
        self.statuses = set()
    def addfile(self, filename, st):
        self.files.append((filename, st))
        self.addstatus(st)
    def addsubdir(self, dirname):
        self.subdirs[dirname] = dirnode()
    def addstatus(self, st):
        self.statuses.add(st)

class BrowsePane(gtk.TreeView):
    'Dialog for browsing repo.status() output'
    def __init__(self, repo):
        gtk.TreeView.__init__(self)
        self.repo = repo
        self.menu = menuthg.menuThg()
        fm = gtk.ListStore(str,  # canonical path
                           bool, # Checked
                           str,  # basename-UTF8
                           bool, # M
                           bool, # A
                           bool, # R
                           bool, # !
                           bool, # ?
                           bool, # I
                           bool, # C
                           bool) # isfile
        self.set_model(fm)

        self.set_headers_visible(False)
        self.set_reorderable(True)
        self.connect('popup-menu', self.popupmenu)
        self.connect('button-release-event', self.buttonrelease)
        self.connect('row-activated', self.rowactivated)
        self.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        self.set_reorderable(False)
        self.set_enable_search(True)
        if hasattr(self, 'set_rubber_banding'):
            self.set_rubber_banding(True)
        fontlist = repo.ui.config('gtools', 'fontlist', 'MS UI Gothic 9')
        self.modify_font(pango.FontDescription(fontlist))

        col = gtk.TreeViewColumn(_('status'))
        self.append_column(col)

        iconw, iconh = gtk.icon_size_lookup(gtk.ICON_SIZE_SMALL_TOOLBAR)
        def packpixmap(ico, id):
            iconpath = paths.get_tortoise_icon(ico)
            if iconpath == None:
                raise (_("could not open icon file '%s' (check install)") % ico)
            pm = gtk.gdk.pixbuf_new_from_file_at_size(iconpath, iconw, iconh)
            cell = gtk.CellRendererPixbuf()
            cell.set_property('pixbuf', pm)
            col.pack_start(cell, expand=False)
            col.add_attribute(cell, 'visible', id)

        #packpixmap('filemodify.ico', 3) # this icon does not load for me
        packpixmap('menucommit.ico', 3) # M
        packpixmap('fileadd.ico', 4)    # A
        packpixmap('filedelete.ico', 5) # R
        packpixmap('detect_rename.ico', 6) # missing
        packpixmap('menublame.ico', 7) # unknown
        #packpixmap('ignore.ico', 8) # ignored
        #packpixmap('hg.ico', 9) # clean

        def cell_seticon(column, cell, model, iter):
            isfile = model.get_value(iter, 10)
            pixbuf = isfile and filepb or folderpb
            cell.set_property('pixbuf', pixbuf)

        col = gtk.TreeViewColumn(_('type'))
        cell = gtk.CellRendererPixbuf()
        col.pack_start(cell, expand=False)
        col.set_cell_data_func(cell, cell_seticon)
        self.append_column(col)

        col = gtk.TreeViewColumn(_('path'), gtk.CellRendererText(), text=2)
        self.append_column(col)

    def split(self, filename):
        'Split a filename into a list of directories and the basename'
        dirs = []
        path, basename = os.path.split(filename)
        while path:
            path, piece = os.path.split(path)
            dirs.append(piece)
        dirs.reverse()
        return dirs, basename

    def refresh(self, pats=[], filetypes='CI?'):
        repo = self.repo
        hglib.invalidaterepo(repo)
        status = ([],)*7
        try:
            matcher = cmdutil.match(repo, pats)
            st = repo.status(match=matcher,
                             clean='C' in filetypes,
                             ignored='I' in filetypes,
                             unknown='?' in filetypes)
        except IOError:
            pass
        filelist = []
        # concatenate status output into a single list, then sort on filename
        for l, s in ( (st[0], 'M'), (st[1], 'A'), (st[2], 'R'), (st[3], '!'),
                      (st[4], '?'), (st[5], 'I'), (st[6], 'C') ):
            for m in l:
                filelist.append([ m, s ])
        filelist.sort()

        def buildrow(name, stset, isfile):
            dirs, basename = self.split(name)
            row = [ name, False, hglib.toutf(basename),
                     'M' in stset, 'A' in stset, 'R' in stset,
                     '!' in stset, '?' in stset, 'I' in stset,
                     'C' in stset, isfile ]
            return row

        # Build tree data structure
        modelroot = dirnode()
        for name, filestatus in filelist:
            dirs, basename = self.split(name)
            curdir = modelroot
            for dir in dirs:
                if dir not in curdir.subdirs:
                    curdir.addsubdir(dir)
                curdir.addstatus(filestatus)
                curdir = curdir.subdirs[dir]
            curdir.addfile(name, filestatus)

        model = self.get_model()
        self.set_model(None) # disable updates while we fill the model
        model.clear()
        model.append(buildrow('..', '', False))
        def adddir(node):
            # insert subdirectories at this level (recursive)
            for dname, dirnode in node.subdirs.iteritems():
                model.append(buildrow(dname, dirnode.statuses, False))
            # insert files at this level
            for fname, st in node.files:
                model.append(buildrow(fname, st, True))
        adddir(modelroot)
        self.set_model(model)

    def popupmenu(self, browse):
        model, tpaths = browse.get_selection().get_selected_rows()
        if not tpaths:
            return
        files = [model[p][0] for p in tpaths if model[p][10]]
        menus = self.menu.get_commands(self.repo, self.repo.root, files)
        # see nautilus extension for usage info
        for menu_info in menus:
            print menu_info

    def buttonrelease(self, browse, event):
        if event.button != 3:
            return False
        self.popupmenu(browse)
        return True

    def rowactivated(self, browse, path, column):
        model, tpaths = browse.get_selection().get_selected_rows()
        if not tpaths:
            return
        if len(tpaths) == 1 and not model[tpaths[0]][10]:
            print 'cd', model[tpaths[0]][0]
        else:
            files = [model[p][0] for p in tpaths and model[p][10]]
            print files, 'activated'

class BrowseDialog(gtk.Dialog):
    'Wrapper application for BrowsePane'
    def __init__(self, command, pats):
        gtk.Dialog.__init__(self)
        gtklib.set_tortoise_icon(self, 'hg.ico')
        gtklib.set_tortoise_keys(self)
        self.set_has_separator(False)
        self.set_default_size(400, 500)
        self.connect('response', self.dialog_response)
        repo = hg.repository(ui.ui(), path=paths.find_root())
        self.set_title(_('%s - browser') % hglib.get_reponame(repo))

        browse = BrowsePane(repo)
        entry = gtk.Entry()
        entry.set_text(repo.root)
        self.vbox.pack_start(entry, False, True)

        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller.add(browse)
        self.vbox.pack_start(scroller, True, True)
        self.show_all()
        self.browse = browse
        gobject.idle_add(self.refresh)

    def refresh(self):
        self.browse.refresh()

    def dialog_response(self, dialog, response):
        return True

def run(ui, *pats, **opts):
    pats = hglib.canonpaths(pats)
    if opts.get('canonpats'):
        pats = list(pats) + opts['canonpats']
    return BrowseDialog(opts.get('alias'), pats)

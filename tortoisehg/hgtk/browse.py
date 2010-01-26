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

from mercurial import hg, ui, cmdutil, error

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths, shlib, menuthg

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
    def __init__(self, callback):
        gtk.TreeView.__init__(self)
        self.callback = callback
        self.cachedroot = None
        self.menu = menuthg.menuThg(internal=True)
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

        col = gtk.TreeViewColumn(_('status'))
        self.append_column(col)

        def packpixmap(name, id):
            pixbuf = gtklib.get_icon_pixbuf(name)
            cell = gtk.CellRendererPixbuf()
            cell.set_property('pixbuf', pixbuf)
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

    def chdir(self, cwd):
        'change to a new directory'
        # disable updates while we refill the model
        self.cwd = cwd
        model = self.get_model()
        self.set_model(None)
        model.clear()
        try:
            self._chdir(model, cwd)
        except Exception, e:
            # report to status bar
            pass
        self.set_model(model)

    def _chdir(self, model, cwd):
        def buildrow(name, stset, isfile):
            dirs, basename = self.split(name)
            row = [ name, False, hglib.toutf(basename),
                     'M' in stset, 'A' in stset, 'R' in stset,
                     '!' in stset, '?' in stset, 'I' in stset,
                     'C' in stset, isfile ]
            return row

        def adddir(node):
            for dname, dirnode in node.subdirs.iteritems():
                model.append(buildrow(dname, dirnode.statuses, False))
            for fname, st in node.files:
                model.append(buildrow(fname, st, True))

        drive, tail = os.path.splitdrive(cwd)
        if cwd != '/' or (drive and tail):
            model.append(buildrow('..', '', False))

        root = paths.find_root(cwd)
        if root and self.cachedroot != root:
            self.cacherepo(root)

        if root:
            node = self.cachedmodel
            relpath = cwd[len(root)+len(os.sep):]
            dirs, basename = self.split(relpath)
            for dname in dirs:
                node = node.subdirs[dname]
            if basename:
                node = node.subdirs[basename]
            adddir(node)
            self.currepo = self.cachedrepo
        else:
            try:
                for name in os.listdir(cwd):
                    isfile = os.path.isfile(os.path.join(cwd, name))
                    model.append(buildrow(name, '', isfile))
            except OSError:
                # report to status bar
                pass
            self.currepo = None


    def cacherepo(self, root, pats=[], filetypes='CI?'):
        status = ([],)*7
        try:
            repo = hg.repository(ui.ui(), path=root)
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

        self.cachedmodel = modelroot
        self.cachedroot = root
        self.cachedrepo = repo

    def popupmenu(self, browse):
        model, tpaths = browse.get_selection().get_selected_rows()
        if tpaths:
            cpaths = [model[p][0] for p in tpaths]
            files = [os.path.join(self.cwd, p) for p in cpaths]
            if self.currepo:
                repo = self.currepo
                menus = self.menu.get_commands(repo, self.cwd, files)
            else:
                menus = self.menu.get_norepo_commands(None, cpaths)
                hgdir = os.path.join(self.cwd, cpaths[0], '.hg')
                if os.path.isdir(hgdir):
                    try:
                        root = os.path.join(self.cwd, cpaths[0])
                        repo = hg.repository(ui.ui(), path=root)
                        menus = self.menu.get_commands(repo, self.cwd, files)
                    except error.RepoError:
                        pass
        else:
            files = []
            if self.currepo:
                repo = self.currepo
                menus = self.menu.get_commands(repo, self.cwd, files)
            else:
                menus = self.menu.get_norepo_commands(None, files)

        def rundialog(item, hgcmd):
            import sys
            # Spawn background process and exit
            if hasattr(sys, "frozen"):
                args = [sys.argv[0], hgcmd] + files
            else:
                args = [sys.executable] + [sys.argv[0], hgcmd] + files
            if os.name == 'nt':
                args = ['"%s"' % arg for arg in args]
            oldcwd = os.getcwd()
            try:
                os.chdir(self.cwd)
                os.spawnv(os.P_NOWAIT, sys.executable, args)
            finally:
                os.chdir(oldcwd)

        def build(menus):
            m = gtklib.MenuBuilder()
            for info in menus:
                if info.isSep():
                    m.append_sep()
                elif info.isSubmenu():
                    m.append_submenu(info.menutext, icon=info.icon,
                                     submenu=build(info.get_menus()))
                elif info.state:
                    # TODO: do something with info.helptext
                    m.append(info.menutext, rundialog, info.icon,
                             args=[info.hgcmd])
            return m.build()

        menu = build(menus)
        menu.show_all()
        menu.popup(None, None, None, 0, 0)


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
            self.callback(model[tpaths[0]][0])
        else:
            files = [model[p][0] for p in tpaths if model[p][10]]
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

        entry = gtk.Entry()
        self.vbox.pack_start(entry, False, True)

        def newfolder_notify(newfolder):
            curpath = entry.get_text()
            newpath = os.path.join(curpath, newfolder)
            newpath = hglib.toutf(os.path.abspath(newpath))
            root = paths.find_root(newpath)
            if root:
                self.set_title(root + ' - ' + _('browser'))
            else:
                self.set_title(_('browser'))
            entry.set_text(newpath)
            browse.chdir(newpath)

        browse = BrowsePane(newfolder_notify)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller.add(browse)
        self.vbox.pack_start(scroller, True, True)
        self.show_all()

        cwd = hglib.toutf(os.getcwd())
        entry.connect('activate', self.entry_activated, browse)
        entry.set_text(cwd)
        browse.chdir(cwd)

    def entry_activated(self, entry, browse):
        browse.chdir(entry.get_text())

    def dialog_response(self, dialog, response):
        return True

def run(ui, *pats, **opts):
    pats = hglib.canonpaths(pats)
    if opts.get('canonpats'):
        pats = list(pats) + opts['canonpats']
    return BrowseDialog(opts.get('alias'), pats)

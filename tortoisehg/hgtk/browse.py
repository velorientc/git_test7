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
from tortoisehg.util import hglib, paths, shlib
from tortoisehg.util.hglib import RepoError

from tortoisehg.hgtk import hgcmd, gtklib, gdialog

class BrowseDialog(gtk.Dialog):
    'Dialog for performing quick dirstate operations'
    def __init__(self, command, pats):
        gtk.Dialog.__init__(self)
        gtklib.set_tortoise_icon(self, 'hg.ico')
        gtklib.set_tortoise_keys(self)
        self.set_has_separator(False)
        self.set_default_size(400, 500)
        self.connect('response', self.dialog_response)
        repo = hg.repository(ui.ui(), path=paths.find_root())
        browse = BrowsePane(repo)

        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller.add(browse)
        self.vbox.pack_start(scroller)
        self.show_all()
        self.browse = browse
        gobject.idle_add(self.refresh)

    def refresh(self):
        self.browse.refresh()

    def dialog_response(self, dialog, response):
        return True

class BrowsePane(gtk.TreeView):
    'Dialog for browsing repo.status() output'
    def __init__(self, repo):
        gtk.TreeView.__init__(self)
        fm = gtk.TreeStore(str,  # Path
                           bool, # Checked
                           str,  # Path-UTF8
                           str)  # Status
        self.set_model(fm)
        self.set_reorderable(True)
        if hasattr(self, 'set_rubber_banding'):
            self.set_rubber_banding(True)
        fontlist = repo.ui.config('gtools', 'fontlist', 'MS UI Gothic 9')
        self.modify_font(pango.FontDescription(fontlist))
        col = gtk.TreeViewColumn(_('status'), gtk.CellRendererText(), text=3)
        self.append_column(col)
        col = gtk.TreeViewColumn(_('path'), gtk.CellRendererText(), text=2)
        self.append_column(col)
        self.repo = repo

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
        files = []
        # concatenate status output into a single list, then sort on filename
        for l, s in ( (st[0], 'M'), (st[1], 'A'), (st[2], 'R'), (st[3], '!'),
                      (st[4], '?'), (st[5], 'I'), (st[6], 'C') ):
            for m in l:
                files.append([ m, s ])
        files.sort()

        # Build tree data structure
        modelroot = ({}, [], set())
        for name, filestatus in files:
            dirs, basename = self.split(name)
            curdir = modelroot
            for dir in dirs:
                if dir not in curdir[0]:
                    curdir[0][dir] = ({}, [], set())
                curdir[2].add(filestatus)
                curdir = curdir[0][dir]
            curdir[1].append((basename, filestatus))
            curdir[2].add(filestatus)

        model = self.get_model()
        model.clear()
        def adddir(name, dirmodel, iter):
            dirdict, files, dirstatus = dirmodel
            # insert subdirectories at this level (recursive)
            for dname, nextmodel in dirdict.iteritems():
                statuslist = list(nextmodel[2])
                st = ''.join(statuslist)
                row = [dname, False, hglib.toutf(dname), st]
                piter = model.append(iter, row)
                adddir(dname, nextmodel, piter)
            # insert files at this level
            for fname, st in files:
                row = [fname, False, hglib.toutf(fname), st]
                model.append(iter, row)

        # insert directory tree into TreeModel
        adddir('root', modelroot, model.get_iter_root())


def run(ui, *pats, **opts):
    pats = hglib.canonpaths(pats)
    if opts.get('canonpats'):
        pats = list(pats) + opts['canonpats']
    return BrowseDialog(opts.get('alias'), pats)

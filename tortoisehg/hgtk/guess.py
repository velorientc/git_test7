# guess.py - TortoiseHg's dialogs for detecting copies and renames
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import sys
import gtk
import gobject
import pango
import cStringIO
import Queue

from mercurial import hg, ui, mdiff, cmdutil, match, util

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, shlib, paths, thread2, settings

from tortoisehg.hgtk import gtklib

# This function and some key bits below borrowed ruthelessly from
# Peter Arrenbrecht <peter.arrenbrecht@gmail.com>
# Thanks!
def findmoves(repo, added, removed, threshold):
    '''find renamed files -- yields (before, after, score) tuples'''
    ctx = repo['.']
    for r in removed:
        rr = ctx.filectx(r).data()
        for a in added:
            aa = repo.wread(a)
            if aa == rr:
                yield r, a, 1.0
                break

class DetectRenameDialog(gtk.Window):
    'Detect renames after they occur'
    def __init__(self):
        'Initialize the Dialog'
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        gtklib.set_tortoise_icon(self, 'detect_rename.ico')
        gtklib.set_tortoise_keys(self)

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except hglib.RepoError:
            gobject.idle_add(self.destroy)
            return
        self.repo = repo
        self.notify_func = None
        reponame = hglib.get_reponame(repo)
        self.set_title(_('Detect Copies/Renames in %s') % reponame)
        self.settings = settings.Settings('guess')
        dims = self.settings.get_value('dims', (800, 600))
        self.set_default_size(dims[0], dims[1])

        # vbox for dialog main & status bar
        mainvbox = gtk.VBox()
        self.add(mainvbox)

        # vsplit for top & diff
        self.vpaned = gtk.VPaned()
        mainvbox.pack_start(self.vpaned, True, True, 2)
        pos = self.settings.get_value('vpaned', None)
        if pos: self.vpaned.set_position(pos)

        # vbox for top contents
        topvbox = gtk.VBox()
        self.vpaned.pack1(topvbox, True, False)

        # frame for simularity
        frame = gtk.Frame(_('Minimum Simularity Percentage'))
        topvbox.pack_start(frame, False, False, 2)

        #$ simularity slider
        self.adjustment = gtk.Adjustment(50, 0, 100, 1)
        value = self.settings.get_value('percent', None)
        if value: self.adjustment.set_value(value)
        hscale = gtk.HScale(self.adjustment)
        frame.add(hscale)

        # horizontal splitter for unknown & candidate
        self.hpaned = gtk.HPaned()
        topvbox.pack_start(self.hpaned, True, True, 2)
        pos = self.settings.get_value('hpaned', None)
        if pos: self.hpaned.set_position(pos)

        #$ frame for unknown list
        unknownframe = gtk.Frame(_('Unrevisioned Files'))
        self.hpaned.pack1(unknownframe, True, True)

        #$$ vbox for unknown list & rename/copy buttons
        unkvbox = gtk.VBox()
        unknownframe.add(unkvbox)

        #$$$ scroll window for unknown list
        scroller = gtk.ScrolledWindow()
        unkvbox.pack_start(scroller, True, True, 2)
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

        #$$$$ unknown list
        unkmodel = gtk.ListStore(str, # path
                                 str) # path (utf-8)
        self.unktree = gtk.TreeView(unkmodel)
        scroller.add(self.unktree)
        self.unktree.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        cell = gtk.CellRendererText()
        cell.set_property("ellipsize", pango.ELLIPSIZE_START)

        col = gtk.TreeViewColumn('File', cell, text=1)
        self.unktree.append_column(col)
        self.unktree.set_enable_search(True)
        self.unktree.set_headers_visible(False)

        #$$$ hbox for rename/copy buttons
        btnhbox = gtk.HBox()
        unkvbox.pack_start(btnhbox, False, False, 2)

        #$$$$ rename/copy buttons in unknown frame
        fr = gtk.Button(_('Find Renames'))
        fr.set_sensitive(False)
        btnhbox.pack_start(fr, False, False, 2)
        fc = gtk.Button(_('Find Copies'))
        fc.set_sensitive(False)
        btnhbox.pack_start(fc, False, False, 2)

        #$ frame for candidate list
        candidateframe = gtk.Frame(_('Candidate Matches'))
        self.hpaned.pack2(candidateframe, True, True)

        #$$ vbox for candidate list & accept button
        canvbox = gtk.VBox()
        candidateframe.add(canvbox)

        #$$$ scroll window for candidate list
        scroller = gtk.ScrolledWindow()
        canvbox.pack_start(scroller, True, True, 2)
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

        #$$$$ candidate list
        canmodel = gtk.ListStore(str,  # source
                                 str,  # source (utf-8)
                                 str,  # dest
                                 str,  # dest (utf-8)
                                 str,  # percent
                                 bool) # sensitive
        self.cantree = gtk.TreeView(canmodel)
        scroller.add(self.cantree)
        self.cantree.set_rules_hint(True)
        self.cantree.set_reorderable(False)
        self.cantree.set_enable_search(False)
        self.cantree.get_selection().set_mode(gtk.SELECTION_MULTIPLE)

        cell = gtk.CellRendererText()
        cell.set_property('width-chars', 30)
        cell.set_property('ellipsize', pango.ELLIPSIZE_START)
        col = gtk.TreeViewColumn(_('Source'), cell, text=1, sensitive=5)
        col.set_resizable(True)
        self.cantree.append_column(col)

        cell = gtk.CellRendererText()
        cell.set_property('width-chars', 30)
        cell.set_property('ellipsize', pango.ELLIPSIZE_START)
        col = gtk.TreeViewColumn(_('Dest'), cell, text=3, sensitive=5)
        col.set_resizable(True)
        self.cantree.append_column(col)

        cell = gtk.CellRendererText()
        cell.set_property('width-chars', 5)
        cell.set_property('ellipsize', pango.ELLIPSIZE_NONE)
        col = gtk.TreeViewColumn('%', cell, text=4, sensitive=5)
        col.set_resizable(True)
        self.cantree.append_column(col)

        #$$$ hbox for accept button
        btnhbox = gtk.HBox()
        canvbox.pack_start(btnhbox, False, False, 2)

        #$$$$ accept button in candidate frame
        ac = gtk.Button(_('Accept Match'))
        btnhbox.pack_start(ac, False, False, 2)
        ac.set_sensitive(False)

        # frame for diff
        diffframe = gtk.Frame(_('Differences from Source to Dest'))
        self.vpaned.pack2(diffframe)
        diffframe.set_shadow_type(gtk.SHADOW_ETCHED_IN)

        #$ scroll window for diff
        scroller = gtk.ScrolledWindow()
        diffframe.add(scroller)
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

        #$$ text view for diff
        buf = gtk.TextBuffer()
        buf.create_tag('removed', foreground='#900000')
        buf.create_tag('added', foreground='#006400')
        buf.create_tag('position', foreground='#FF8000')
        buf.create_tag('header', foreground='#000090')
        diffview = gtk.TextView(buf)
        scroller.add(diffview)
        diffview.modify_font(pango.FontDescription('monospace'))
        diffview.set_wrap_mode(gtk.WRAP_NONE)
        diffview.set_editable(False)

        # status bar
        self.stbar = gtklib.StatusBar()
        mainvbox.pack_start(self.stbar, False, False, 2)

        # register signal handlers
        args = (self.unktree, self.cantree, self.adjustment, self.stbar)
        fc.connect('pressed', self.find_copies, *args)
        fr.connect('pressed', self.find_renames, *args)
        ac.connect('pressed', self.accept_match, *args)

        self.unktree.get_selection().connect('changed',
                      self.unknown_sel_change, fr, fc)
        self.cantree.connect('row-activated',
                      self.candidate_row_act, self.unktree, self.stbar)
        self.cantree.get_selection().connect('changed', self.show_diff, buf, ac)
        self.connect('delete-event', self.save_settings,
                self.settings, self.hpaned, self.vpaned, self.adjustment)
        gobject.idle_add(self.refresh, unkmodel)

    def set_notify_func(self, func):
        self.notify_func = func

    def refresh(self, unkmodel):
        q = Queue.Queue()
        unkmodel.clear()
        thread = thread2.Thread(target=self.unknown_thread,
                args=(self.repo.root, q))
        thread.start()
        gobject.timeout_add(50, self.unknown_wait, thread, q, unkmodel)

    def unknown_thread(self, root, q):
        matcher = match.always(self.repo.root, self.repo.root)
        status = self.repo.status(node1=self.repo.dirstate.parents()[0],
                                  node2=None, match=matcher, ignored=False,
                                  clean=False, unknown=True)
        (modified, added, removed, deleted, unknown, ignored, clean) = status
        for u in unknown:
            q.put( u )
        for a in added:
            if not self.repo.dirstate.copied(a):
                q.put( a )

    def unknown_wait(self, thread, q, unkmodel):
        while q.qsize():
            wfile = q.get(0)
            unkmodel.append( [wfile, hglib.toutf(wfile)] )
        return thread.isAlive()

    def save_settings(self, w, event, settings, hpaned, vpaned, adjustment):
        self.settings.set_value('vpaned', vpaned.get_position())
        self.settings.set_value('hpaned', hpaned.get_position())
        self.settings.set_value('percent', adjustment.get_value())
        rect = self.get_allocation()
        self.settings.set_value('dims', (rect.width, rect.height))
        self.settings.write()

    def find_renames(self, widget, unktree, cantree, adj, stbar):
        'User pressed "find renames" button'
        canmodel = self.cantree.get_model()
        canmodel.clear()
        umodel, upaths = self.unktree.get_selection().get_selected_rows()
        if not upaths:
            return
        tgts = [ umodel[p][0] for p in upaths ]
        q = Queue.Queue()
        thread = thread2.Thread(target=self.search_thread,
                args=(self.repo.root, q, tgts, self.adjustment))
        thread.start()
        stbar.begin()
        stbar.set_status_text(_('finding source of ') + ', '.join(tgts))
        gobject.timeout_add(50, self.search_wait, thread, q, canmodel, stbar)

    def search_thread(self, root, q, tgts, adj):
        srcs = []
        audit_path = util.path_auditor(self.repo.root)
        m = cmdutil.match(self.repo)
        for abs in self.repo.walk(m):
            target = self.repo.wjoin(abs)
            good = True
            try:
                audit_path(abs)
            except:
                good = False
            status = self.repo.dirstate[abs]
            if (not good or not util.lexists(target)
                or (os.path.isdir(target) and not os.path.islink(target))):
                srcs.append(abs)
            elif not self.adjustment and status == 'n':
                # looking for copies, so any revisioned file is a
                # potential source (yes, this will be expensive)
                # Added and removed files are not considered as copy
                # sources.
                srcs.append(abs)
        if self.adjustment:
            simularity = self.adjustment.get_value() / 100.0;
            gen = cmdutil.findrenames
        else:
            simularity = 1.0
            gen = findmoves
        for old, new, score in gen(self.repo, tgts, srcs, simularity):
            q.put( [old, new, '%d%%' % (score*100)] )

    def search_wait(self, thread, q, canmodel, stbar):
        while q.qsize():
            source, dest, sim = q.get(0)
            canmodel.append( [source, hglib.toutf(source), dest, hglib.toutf(dest), sim, True] )
        if thread.isAlive():
            return True
        else:
            stbar.end()
            return False

    def find_copies(self, widget, unktree, cantree, adj, stbar):
        'User pressed "find copies" button'
        # call rename function with simularity = 100%
        self.find_renames(widget, self.unktree, self.cantree, None, stbar)

    def accept_match(self, widget, unktree, cantree, adj, stbar):
        'User pressed "accept match" button'
        canmodel, upaths = self.cantree.get_selection().get_selected_rows()
        for path in upaths:
            row = canmodel[path]
            src, usrc, dest, udest, percent, sensitive = row
            if not sensitive:
                continue
            if not os.path.exists(self.repo.wjoin(src)):
                # Mark missing rename source as removed
                self.repo.remove([src])
            self.repo.copy(src, dest)
            shlib.shell_notify([self.repo.wjoin(src), self.repo.wjoin(dest)])
            if self.notify_func:
                self.notify_func()
            # Mark all rows with this target file as non-sensitive
            for row in canmodel:
                if row[2] == dest:
                    row[5] = False
        self.refresh(self.unktree.get_model())

    def candidate_row_act(self, cantree, path, column, unktree, stbar):
        'User activated row of candidate list'
        self.accept_match(self.cantree, self.unktree, self.cantree, None, stbar)

    def unknown_sel_change(self, selection, fr, fc):
        'User selected a row in the unknown tree'
        model, upaths = selection.get_selected_rows()
        sensitive = upaths and True or False
        fr.set_sensitive(sensitive)
        fc.set_sensitive(sensitive)

    def show_diff(self, selection, buf, ac):
        'User selected a row in the candidate tree'
        model, cpaths = selection.get_selected_rows()
        sensitive = cpaths and True or False
        ac.set_sensitive(sensitive)

        buf.set_text('')
        bufiter = buf.get_start_iter()
        for path in cpaths:
            row = model[path]
            src, usrc, dest, udest, percent, sensitive = row
            if not sensitive:
                continue
            ctx = self.repo['.']
            aa = self.repo.wread(dest)
            rr = ctx.filectx(src).data()
            opts = mdiff.defaultopts
            difftext = mdiff.unidiff(rr, '', aa, '', src, dest, None, opts=opts)
            if not difftext:
                l = _('== %s and %s have identical contents ==\n\n') % (src, dest)
                buf.insert(bufiter, l)
                continue
            difflines = difftext.splitlines(True)
            for line in difflines:
                line = hglib.toutf(line)
                if line.startswith('---') or line.startswith('+++'):
                    buf.insert_with_tags_by_name(bufiter, line, 'header')
                elif line.startswith('-'):
                    line = hglib.diffexpand(line)
                    buf.insert_with_tags_by_name(bufiter, line, 'removed')
                elif line.startswith('+'):
                    line = hglib.diffexpand(line)
                    buf.insert_with_tags_by_name(bufiter, line, 'added')
                elif line.startswith('@@'):
                    buf.insert_with_tags_by_name(bufiter, line, 'position')
                else:
                    line = hglib.diffexpand(line)
                    buf.insert(bufiter, line)

def run(ui, *pats, **opts):
    return DetectRenameDialog()

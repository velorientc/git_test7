#
# guess.py - TortoiseHg's dialogs for detecting copies and renames
#
# Copyright (C) 2009 Steve Borho <steve@borho.org>
#

import os
import sys
import gtk
import gobject
import pango
import cStringIO
import Queue

from mercurial import hg, ui, mdiff, cmdutil, match, util

from thgutil.i18n import _
from thgutil.hglib import toutf, fromutf, diffexpand, RepoError
from thgutil import shlib, paths, thread2, settings

from hggtk import gtklib

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

        self.root = paths.find_root()
        self.notify_func = None
        path = toutf(os.path.basename(self.root))
        self.set_title(_('Detect Copies/Renames in ') + path)
        self._settings = settings.Settings('guess')
        dims = self._settings.get_value('dims', (800, 600))
        self.set_default_size(dims[0], dims[1])

        adjustment = gtk.Adjustment(50, 0, 100, 1)
        value = self._settings.get_value('percent', None)
        if value: adjustment.set_value(value)
        hscale = gtk.HScale(adjustment)
        frame = gtk.Frame(_('Minimum Simularity Percentage'))
        frame.add(hscale)
        topvbox = gtk.VBox()
        topvbox.pack_start(frame, False, False, 2)

        unkmodel = gtk.ListStore(str, str)
        unknowntree = gtk.TreeView(unkmodel)
        unknowntree.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        cell = gtk.CellRendererText()
        cell.set_property("ellipsize", pango.ELLIPSIZE_START)
        col = gtk.TreeViewColumn('File', cell, text=1)
        unknowntree.append_column(col)
        unknowntree.set_enable_search(True)
        unknowntree.set_headers_visible(False)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(unknowntree)

        vbox = gtk.VBox()
        vbox.pack_start(scroller, True, True, 2)
        fr = gtk.Button(_('Find Renames'))
        fc = gtk.Button(_('Find Copies'))
        hbox = gtk.HBox()
        hbox.pack_start(fr, False, False, 2)
        hbox.pack_start(fc, False, False, 2)
        vbox.pack_start(hbox, False, False, 2)
        fr.set_sensitive(False)
        fc.set_sensitive(False)

        unknownframe = gtk.Frame(_('Unrevisioned Files'))
        unknownframe.add(vbox)

        # source, dest, percent match, sensitive
        cmodel = gtk.ListStore(str, str, str, str, str, bool)
        ctree = gtk.TreeView(cmodel)
        ctree.set_rules_hint(True)
        ctree.set_reorderable(False)
        ctree.set_enable_search(False)
        ctree.get_selection().set_mode(gtk.SELECTION_MULTIPLE)

        cell = gtk.CellRendererText()
        cell.set_property('width-chars', 30)
        cell.set_property('ellipsize', pango.ELLIPSIZE_START)
        col = gtk.TreeViewColumn(_('Source'), cell, text=1, sensitive=5)
        col.set_resizable(True)
        ctree.append_column(col)

        cell = gtk.CellRendererText()
        cell.set_property('width-chars', 30)
        cell.set_property('ellipsize', pango.ELLIPSIZE_START)
        col = gtk.TreeViewColumn(_('Dest'), cell, text=3, sensitive=5)
        col.set_resizable(True)
        ctree.append_column(col)

        cell = gtk.CellRendererText()
        cell.set_property('width-chars', 5)
        cell.set_property('ellipsize', pango.ELLIPSIZE_NONE)
        col = gtk.TreeViewColumn('%', cell, text=4, sensitive=5)
        col.set_resizable(True)
        ctree.append_column(col)

        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(ctree)

        stbar = gtklib.StatusBar()
        vbox = gtk.VBox()
        vbox.pack_start(scroller, True, True, 2)
        ac = gtk.Button(_('Accept Match'))
        hbox = gtk.HBox()
        hbox.pack_start(ac, False, False, 2)
        vbox.pack_start(hbox, False, False, 2)
        ac.set_sensitive(False)

        candidateframe = gtk.Frame(_('Candidate Matches'))
        candidateframe.add(vbox)

        hpaned = gtk.HPaned()
        hpaned.pack1(unknownframe, True, True)
        hpaned.pack2(candidateframe, True, True)
        pos = self._settings.get_value('hpaned', None)
        if pos: hpaned.set_position(pos)

        topvbox.pack_start(hpaned, True, True, 2)

        diffframe = gtk.Frame(_('Differences from Source to Dest'))
        diffframe.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        diffframe.add(scroller)

        buf = gtk.TextBuffer()
        buf.create_tag('removed', foreground='#900000')
        buf.create_tag('added', foreground='#006400')
        buf.create_tag('position', foreground='#FF8000')
        buf.create_tag('header', foreground='#000090')

        diffview = gtk.TextView(buf)
        diffview.modify_font(pango.FontDescription('monospace'))
        diffview.set_wrap_mode(gtk.WRAP_NONE)
        diffview.set_editable(False)
        scroller.add(diffview)

        vpaned = gtk.VPaned()
        vpaned.pack1(topvbox, True, False)
        vpaned.pack2(diffframe)
        pos = self._settings.get_value('vpaned', None)
        if pos: vpaned.set_position(pos)

        vbox = gtk.VBox()
        vbox.pack_start(vpaned, True, True, 2)
        vbox.pack_start(stbar, False, False, 2)
        self.add(vbox)

        args = (unknowntree, ctree, adjustment, stbar)
        fc.connect('pressed', self.find_copies, *args)
        fr.connect('pressed', self.find_renames, *args)
        ac.connect('pressed', self.accept_match, *args)

        unknowntree.get_selection().connect('changed',
                      self.unknown_sel_change, fr, fc)
        ctree.connect('row-activated',
                      self.candidate_row_act, unknowntree, stbar)
        ctree.get_selection().connect('changed', self.show_diff, buf, ac)
        self.connect('delete-event', self.save_settings,
                settings, hpaned, vpaned, adjustment)
        gobject.idle_add(self.refresh, unkmodel)

    def set_notify_func(self, func):
        self.notify_func = func

    def refresh(self, unkmodel):
        q = Queue.Queue()
        unkmodel.clear()
        thread = thread2.Thread(target=self.unknown_thread,
                args=(self.root, q))
        thread.start()
        gobject.timeout_add(50, self.unknown_wait, thread, q, unkmodel)

    def unknown_thread(self, root, q):
        try:
            repo = hg.repository(ui.ui(), root)
        except RepoError:
            return
        matcher = match.always(repo.root, repo.root)
        status = repo.status(node1=repo.dirstate.parents()[0], node2=None,
                match=matcher, ignored=False, clean=False, unknown=True)
        (modified, added, removed, deleted, unknown, ignored, clean) = status
        for u in unknown:
            q.put( u )
        for a in added:
            if not repo.dirstate.copied(a):
                q.put( a )

    def unknown_wait(self, thread, q, unkmodel):
        while q.qsize():
            wfile = q.get(0)
            unkmodel.append( [wfile, toutf(wfile)] )
        return thread.isAlive()

    def save_settings(self, w, event, settings, hpaned, vpaned, adjustment):
        self._settings.set_value('vpaned', vpaned.get_position())
        self._settings.set_value('hpaned', hpaned.get_position())
        self._settings.set_value('percent', adjustment.get_value())
        rect = self.get_allocation()
        self._settings.set_value('dims', (rect.width, rect.height))
        self._settings.write()

    def find_renames(self, widget, unktree, ctree, adj, stbar):
        'User pressed "find renames" button'
        cmodel = ctree.get_model()
        cmodel.clear()
        umodel, upaths = unktree.get_selection().get_selected_rows()
        if not upaths:
            return
        tgts = [ umodel[p][0] for p in upaths ]
        q = Queue.Queue()
        thread = thread2.Thread(target=self.search_thread,
                args=(self.root, q, tgts, adj))
        thread.start()
        stbar.begin()
        stbar.set_status_text(_('finding source of ') + ', '.join(tgts))
        gobject.timeout_add(50, self.search_wait, thread, q, cmodel, stbar)

    def search_thread(self, root, q, tgts, adj):
        try:
            repo = hg.repository(ui.ui(), root)
        except RepoError:
            return
        srcs = []
        audit_path = util.path_auditor(repo.root)
        m = cmdutil.match(repo)
        for abs in repo.walk(m):
            target = repo.wjoin(abs)
            good = True
            try:
                audit_path(abs)
            except:
                good = False
            status = repo.dirstate[abs]
            if (not good or not util.lexists(target)
                or (os.path.isdir(target) and not os.path.islink(target))):
                srcs.append(abs)
            elif not adj and status == 'n':
                # looking for copies, so any revisioned file is a
                # potential source (yes, this will be expensive)
                # Added and removed files are not considered as copy
                # sources.
                srcs.append(abs)
        if adj:
            simularity = adj.get_value() / 100.0;
            gen = cmdutil.findrenames
        else:
            simularity = 1.0
            gen = findmoves
        for old, new, score in gen(repo, tgts, srcs, simularity):
            q.put( [old, new, '%d%%' % (score*100)] )

    def search_wait(self, thread, q, cmodel, stbar):
        while q.qsize():
            source, dest, sim = q.get(0)
            cmodel.append( [source, toutf(source), dest, toutf(dest), sim, True] )
        if thread.isAlive():
            return True
        else:
            stbar.end()
            return False

    def find_copies(self, widget, unktree, ctree, adj, stbar):
        'User pressed "find copies" button'
        # call rename function with simularity = 100%
        self.find_renames(widget, unktree, ctree, None, stbar)

    def accept_match(self, widget, unktree, ctree, adj, stbar):
        'User pressed "accept match" button'
        try:
            repo = hg.repository(ui.ui(), self.root)
        except RepoError:
            return
        cmodel, upaths = ctree.get_selection().get_selected_rows()
        for path in upaths:
            row = cmodel[path]
            src, usrc, dest, udest, percent, sensitive = row
            if not sensitive:
                continue
            if not os.path.exists(repo.wjoin(src)):
                # Mark missing rename source as removed
                repo.remove([src])
            repo.copy(src, dest)
            shlib.shell_notify([repo.wjoin(src), repo.wjoin(dest)])
            if self.notify_func:
                self.notify_func()
            # Mark all rows with this target file as non-sensitive
            for row in cmodel:
                if row[2] == dest:
                    row[5] = False
        self.refresh(unktree.get_model())

    def candidate_row_act(self, ctree, path, column, unktree, stbar):
        'User activated row of candidate list'
        self.accept_match(ctree, unktree, ctree, None, stbar)

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

        try:
            repo = hg.repository(ui.ui(), self.root)
        except RepoError:
            return

        buf.set_text('')
        bufiter = buf.get_start_iter()
        for path in cpaths:
            row = model[path]
            src, usrc, dest, udest, percent, sensitive = row
            if not sensitive:
                continue
            ctx = repo['.']
            aa = repo.wread(dest)
            rr = ctx.filectx(src).data()
            opts = mdiff.defaultopts
            difftext = mdiff.unidiff(rr, '', aa, '', src, dest, None, opts=opts)
            if not difftext:
                l = _('== %s and %s have identical contents ==\n\n') % (src, dest)
                buf.insert(bufiter, l)
                continue
            difflines = difftext.splitlines(True)
            for line in difflines:
                line = toutf(line)
                if line.startswith('---') or line.startswith('+++'):
                    buf.insert_with_tags_by_name(bufiter, line, 'header')
                elif line.startswith('-'):
                    line = diffexpand(line)
                    buf.insert_with_tags_by_name(bufiter, line, 'removed')
                elif line.startswith('+'):
                    line = diffexpand(line)
                    buf.insert_with_tags_by_name(bufiter, line, 'added')
                elif line.startswith('@@'):
                    buf.insert_with_tags_by_name(bufiter, line, 'position')
                else:
                    line = diffexpand(line)
                    buf.insert(bufiter, line)

def run(ui, *pats, **opts):
    return DetectRenameDialog()

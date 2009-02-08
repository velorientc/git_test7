#
# rename.py - TortoiseHg's dialogs for handling renames
#
# Copyright (C) 2009 Steve Borho <steve@borho.org>
#

import os
import sys
import gtk
import gobject
import pango
import cStringIO
import shlib
import Queue
import threading, thread2
from dialog import error_dialog
from mercurial import hg, ui, mdiff, cmdutil, match, util
from hglib import toutf, diffexpand
import gtklib
try:
    from mercurial.repo import RepoError
except ImportError:
    from mercurial.error import RepoError

# This function and some key bits below borrowed ruthelessly from
# Peter Arrenbrecht <peter.arrenbrecht@gmail.com>
# Thanks!
def findmoves(repo, added, removed, threshold):
    '''find renamed files -- yields (before, after, score) tuples'''
    ctx = repo['.']
    for r in removed:
        rr = ctx.filectx(r).data()
        bestname, bestscore = None, threshold
        for a in added:
            aa = repo.wread(a)
            if aa == rr:
                yield r, a, 1.0
                break

class DetectRenameDialog(gtk.Window):
    'Detect renames after they occur'
    def __init__(self, root=''):
        'Initialize the Dialog'
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        self.root = root
        self.notify_func = None
        self.set_title('Detect Copies/Renames in %s' % os.path.basename(root))
        settings = shlib.Settings('rename')
        dims = settings.get_value('dims', (800, 600))
        self.set_default_size(dims[0], dims[1])

        adjustment = gtk.Adjustment(50, 0, 100, 1)
        value = settings.get_value('percent', None)
        if value: adjustment.set_value(value)
        hscale = gtk.HScale(adjustment)
        frame = gtk.Frame('Minimum Simularity Percentage')
        frame.add(hscale)
        topvbox = gtk.VBox()
        topvbox.pack_start(frame, False, False, 2)

        unkmodel = gtk.ListStore(str)
        unknowntree = gtk.TreeView(unkmodel)
        unknowntree.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        cell = gtk.CellRendererText()
        cell.set_property("ellipsize", pango.ELLIPSIZE_START)
        col = gtk.TreeViewColumn('File', cell, text=0)
        unknowntree.append_column(col)
        unknowntree.set_enable_search(True)
        unknowntree.set_headers_visible(False)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(unknowntree)

        vbox = gtk.VBox()
        vbox.pack_start(scroller, True, True, 2)
        fr = gtk.Button('Find Renames')
        fc = gtk.Button('Find Copies')
        hbox = gtk.HBox()
        hbox.pack_start(fr, False, False, 2)
        hbox.pack_start(fc, False, False, 2)
        vbox.pack_start(hbox, False, False, 2)
        fr.set_sensitive(False)
        fc.set_sensitive(False)

        unknownframe = gtk.Frame('Unrevisioned Files')
        unknownframe.add(vbox)

        # source, dest, percent match, sensitive
        cmodel = gtk.ListStore(str, str, str, bool)
        ctree = gtk.TreeView(cmodel)
        ctree.set_rules_hint(True)
        ctree.set_reorderable(False)
        ctree.set_enable_search(True)
        ctree.get_selection().set_mode(gtk.SELECTION_MULTIPLE)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 30)
        cell.set_property("ellipsize", pango.ELLIPSIZE_START)
        col = gtk.TreeViewColumn('Source', cell, text=0, sensitive=3)
        col.set_resizable(True)
        ctree.append_column(col)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 30)
        cell.set_property("ellipsize", pango.ELLIPSIZE_START)
        col = gtk.TreeViewColumn('Dest', cell, text=1, sensitive=3)
        col.set_resizable(True)
        ctree.append_column(col)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 5)
        cell.set_property("ellipsize", pango.ELLIPSIZE_NONE)
        col = gtk.TreeViewColumn('%', cell, text=2, sensitive=3)
        col.set_resizable(True)
        ctree.append_column(col)

        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(ctree)

        stbar = gtklib.StatusBar()
        vbox = gtk.VBox()
        vbox.pack_start(scroller, True, True, 2)
        ac = gtk.Button('Accept Match')
        hbox = gtk.HBox()
        hbox.pack_start(ac, False, False, 2)
        vbox.pack_start(hbox, False, False, 2)
        ac.set_sensitive(False)

        candidateframe = gtk.Frame('Candidate Matches')
        candidateframe.add(vbox)

        hpaned = gtk.HPaned()
        hpaned.pack1(unknownframe, True, True)
        hpaned.pack2(candidateframe, True, True)
        pos = settings.get_value('hpaned', None)
        if pos: hpaned.set_position(pos)

        topvbox.pack_start(hpaned, True, True, 2)

        diffframe = gtk.Frame('Differences from Source to Dest')
        diffframe.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        diffframe.add(scroller)
        
        buffer = gtk.TextBuffer()
        buffer.create_tag('removed', foreground='#900000')
        buffer.create_tag('added', foreground='#006400')
        buffer.create_tag('position', foreground='#FF8000')
        buffer.create_tag('header', foreground='#000090')

        diffview = gtk.TextView(buffer)
        diffview.modify_font(pango.FontDescription('monospace'))
        diffview.set_wrap_mode(gtk.WRAP_NONE)
        diffview.set_editable(False)
        scroller.add(diffview)

        vpaned = gtk.VPaned()
        vpaned.pack1(topvbox, True, False)
        vpaned.pack2(diffframe)
        pos = settings.get_value('vpaned', None)
        if pos: vpaned.set_position(pos)

        vbox = gtk.VBox()
        vbox.pack_start(vpaned, True, True, 2)
        vbox.pack_start(stbar, False, False, 2)
        self.add(vbox)

        args = (unknowntree, ctree, adjustment, stbar)
        fc.connect('pressed', self.find_copies, *args)
        fr.connect('pressed', self.find_renames, *args)
        ac.connect('pressed', self.accept_match, *args)

        unknowntree.get_selection().connect('changed', self.unknown_sel_change, fr, fc)
        ctree.connect('row-activated', self.candidate_row_act, unknowntree, stbar)
        ctree.get_selection().connect('changed', self.show_diff, buffer, ac)
        self.connect('map_event', self.on_window_map_event, unkmodel)
        self.connect('delete-event', self.save_settings,
                settings, hpaned, vpaned, adjustment)

    def set_notify_func(self, func):
        self.notify_func = func

    def on_window_map_event(self, event, param, unkmodel):
        self.refresh(unkmodel)

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
            unkmodel.append( [q.get(0)] )
        return thread.isAlive()

    def save_settings(self, w, event, settings, hpaned, vpaned, adjustment):
        settings.set_value('vpaned', vpaned.get_position())
        settings.set_value('hpaned', hpaned.get_position())
        settings.set_value('percent', adjustment.get_value())
        rect = self.get_allocation()
        settings.set_value('dims', (rect.width, rect.height))
        settings.write()

    def find_renames(self, widget, unktree, ctree, adj, stbar):
        'User pressed "find renames" button'
        cmodel = ctree.get_model()
        cmodel.clear()
        umodel, paths = unktree.get_selection().get_selected_rows()
        if not paths:
            return
        tgts = [ umodel[p][0] for p in paths ]
        q = Queue.Queue()
        thread = thread2.Thread(target=self.search_thread,
                args=(self.root, q, tgts, adj))
        thread.start()
        stbar.begin()
        stbar.set_status_text('finding source of ' + ', '.join(tgts))
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
            q.put( [old, new, '%d%%' % (score*100), True] )

    def search_wait(self, thread, q, cmodel, stbar):
        while q.qsize():
            cmodel.append( q.get(0) )
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
        cmodel, paths = ctree.get_selection().get_selected_rows()
        for path in paths:
            row = cmodel[path]
            src, dest, percent, sensitive = row
            if not sensitive:
                continue
            if not os.path.exists(repo.wjoin(src)):
                # Mark missing rename source as removed
                repo.remove([src])
            repo.copy(src, dest)
            shlib.shell_notify([src, dest])
            if self.notify_func:
                self.notify_func()
            # Mark all rows with this target file as non-sensitive
            for row in cmodel:
                if row[1] == dest:
                    row[3] = False
        self.refresh(unktree.get_model())

    def candidate_row_act(self, ctree, path, column, unktree, stbar):
        'User activated row of candidate list'
        self.accept_match(ctree, unktree, ctree, None, stbar)

    def unknown_sel_change(self, selection, fr, fc):
        'User selected a row in the unknown tree'
        model, paths = selection.get_selected_rows()
        sensitive = paths and True or False
        fr.set_sensitive(sensitive)
        fc.set_sensitive(sensitive)

    def show_diff(self, selection, buffer, ac):
        'User selected a row in the candidate tree'
        model, paths = selection.get_selected_rows()
        sensitive = paths and True or False
        ac.set_sensitive(sensitive)

        try:
            repo = hg.repository(ui.ui(), self.root)
        except RepoError:
            return

        buffer.set_text('')
        iter = buffer.get_start_iter()
        for path in paths:
            row = model[path]
            src, dest, percent, sensitive = row
            if not sensitive:
                continue
            ctx = repo['.']
            aa = repo.wread(dest)
            rr = ctx.filectx(src).data()
            opts = mdiff.defaultopts
            difftext = mdiff.unidiff(rr, '', aa, '', src, dest, None, opts=opts)
            if not difftext:
                l = '== %s and %s have identical contents ==\n\n' % (src, dest)
                buffer.insert(iter, l)
                continue
            difflines = difftext.splitlines(True)
            for line in difflines:
                line = toutf(line)
                if line.startswith('---') or line.startswith('+++'):
                    buffer.insert_with_tags_by_name(iter, line, 'header')
                elif line.startswith('-'):
                    line = diffexpand(line)
                    buffer.insert_with_tags_by_name(iter, line, 'removed')
                elif line.startswith('+'):
                    line = diffexpand(line)
                    buffer.insert_with_tags_by_name(iter, line, 'added')
                elif line.startswith('@@'):
                    buffer.insert_with_tags_by_name(iter, line, 'position')
                else:
                    line = diffexpand(line)
                    buffer.insert(iter, line)

def run(fname='', target='', detect=True, root='', **opts):
    if detect:
        dialog = DetectRenameDialog(root)
        dialog.show_all()
        dialog.connect('destroy', gtk.main_quit)
    else:
        from dialog import entry_dialog
        title = 'Rename ' + fname
        dialog = entry_dialog(None, title, True, target or fname, rename_resp)
        dialog.orig = fname
        dialog.show_all()
        dialog.connect('destroy', gtk.main_quit)
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

def rename_resp(dialog, response):
    if response != gtk.RESPONSE_OK:
        gtk.main_quit()
        return
    try:
        import hglib
        root = hglib.rootpath()
        repo = hg.repository(ui.ui(), root)
    except ImportError, RepoError:
        gtk.main_quit()
        return

    new_name = dialog.entry.get_text()
    opts = {}
    opts['force'] = False # Checkbox? Nah.
    opts['after'] = False
    opts['dry_run'] = False

    saved = sys.stderr
    errors = cStringIO.StringIO()
    quit = False
    try:
        sys.stderr = errors
        repo.ui.pushbuffer()
        try:
            commands.rename(repo.ui, repo, dialog.orig, new_name, **opts)
            quit = True
        except util.Abort, inst:
            error_dialog(None, 'rename error', str(inst))
            quit = False
    finally:
        sys.stderr = saved
        textout = errors.getvalue() + repo.ui.popbuffer() 
        errors.close()
        if len(textout) > 1:
            error_dialog(None, 'rename error', textout)
        elif quit:
            gtk.main_quit()

if __name__ == "__main__":
    opts = {'fname' : sys.argv[1]}
    if '--detect' in sys.argv:
        import hglib
        opts['root'] = hglib.rootpath()
        opts['detect'] = True
    elif len(sys.argv) == 3:
        opts['target'] = sys.argv[2]
    run(**opts)

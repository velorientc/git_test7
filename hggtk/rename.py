#
# rename.py - TortoiseHg's dialogs for handling renames
#
# Copyright (C) 2009 Steve Borho <steve@borho.org>
#

import os
import sys
import gtk
import pango
import cStringIO
import shlib
from dialog import error_dialog
from mercurial import hg, ui, cmdutil, match, util
try:
    from mercurial.repo import RepoError
except ImportError:
    from mercurial.error import RepoError

class DetectRenameDialog(gtk.Window):
    'Detect renames after they occur'
    def __init__(self, root=''):
        'Initialize the Dialog'
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        self.root = root
        self.set_title('Detect Copies/Renames in %s' % os.path.basename(root))
        self.settings = shlib.Settings('rename')
        dims = self.settings.get_value('dims', (800, 600))
        self.set_default_size(dims[0], dims[1])

        adjustment = gtk.Adjustment(50, 0, 100, 1)
        value = self.settings.get_value('percent', None)
        if value: adjustment.set_value(value)
        hscale = gtk.HScale(adjustment)
        frame = gtk.Frame('Minimum Simularity Percentage')
        frame.add(hscale)
        topvbox = gtk.VBox()
        topvbox.pack_start(frame, False, False, 2)

        unkmodel = gtk.ListStore(str)
        unknowntree = gtk.TreeView(unkmodel)
        col = gtk.TreeViewColumn('File', gtk.CellRendererText(), text=0)
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
        hbox.pack_start(fr, True, True, 2)
        hbox.pack_start(fc, True, True, 2)
        vbox.pack_start(hbox, False, False, 2)

        unknownframe = gtk.Frame('Unrevisioned Files')
        unknownframe.add(vbox)

        # source, dest, percent match, sensitive
        cmodel = gtk.ListStore(str, str, str, bool)
        ctree = gtk.TreeView(cmodel)
        ctree.set_rules_hint(True)
        ctree.set_reorderable(False)
        ctree.set_enable_search(True)
        ctree.connect('cursor-changed', self.show_diff)
        sel = ctree.get_selection()
        sel.set_mode(gtk.SELECTION_SINGLE)
        col = gtk.TreeViewColumn('Source', gtk.CellRendererText(),
                text=0, sensitive=3)
        col.set_resizable(True)
        ctree.append_column(col)
        col = gtk.TreeViewColumn('Dest', gtk.CellRendererText(),
                text=1, sensitive=3)
        col.set_resizable(True)
        ctree.append_column(col)
        col = gtk.TreeViewColumn('%', gtk.CellRendererText(),
                text=2, sensitive=3)
        col.set_resizable(True)
        ctree.append_column(col)
        ctree.connect('row-activated', self.candidate_row_act, unknowntree)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(ctree)

        vbox = gtk.VBox()
        vbox.pack_start(scroller, True, True, 2)
        ac = gtk.Button('Accept Match')
        fc.connect('pressed', self.find_copies, unknowntree, ctree)
        fr.connect('pressed', self.find_renames, unknowntree, ctree)
        ac.connect('pressed', self.accept_match, unknowntree, ctree)
        hbox = gtk.HBox()
        hbox.pack_start(ac, False, False, 2)
        vbox.pack_start(hbox, False, False, 2)

        candidateframe = gtk.Frame('Candidate Matches')
        candidateframe.add(vbox)

        hpaned = gtk.HPaned()
        hpaned.pack1(unknownframe, True, True)
        hpaned.pack2(candidateframe, True, True)
        pos = self.settings.get_value('hpaned', None)
        if pos: hpaned.set_position(pos)

        topvbox.pack_start(hpaned, True, True, 2)

        diffframe = gtk.Frame('Differences from Source to Dest')
        diffframe.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        diffframe.add(scroller)
        
        self.diffbuf = gtk.TextBuffer()
        diffview = gtk.TextView(self.diffbuf)
        diffview.set_wrap_mode(gtk.WRAP_NONE)
        diffview.set_editable(False)
        scroller.add(diffview)

        vpaned = gtk.VPaned()
        vpaned.pack1(topvbox, True, False)
        vpaned.pack2(diffframe)
        pos = self.settings.get_value('vpaned', None)
        if pos: vpaned.set_position(pos)

        self.add(vpaned)
        self.connect('map_event', self.on_window_map_event, unkmodel, cmodel)
        self.connect('delete-event', self.save_settings,
                hpaned, vpaned, adjustment)

    def on_window_map_event(self, event, param, unkmodel, cmodel):
        self.refresh(unkmodel, cmodel)

    def refresh(self, unkmodel, cmodel):
        try:
            repo = hg.repository(ui.ui(), self.root)
        except RepoError:
            return

        matcher = match.always(repo.root, repo.root)
        self.status = repo.status(node1=repo.dirstate.parents()[0], node2=None,
                match=matcher, ignored=False, clean=False, unknown=True)
        #(modified, added, removed, deleted, unknown, ignored, clean) = status
        unkmodel.clear()
        for u in self.status[4]:
            unkmodel.append( [u] )
        cmodel.clear()

    def save_settings(self, widget, event, hpaned, vpaned, adjustment):
        self.settings.set_value('vpaned', vpaned.get_position())
        self.settings.set_value('hpaned', hpaned.get_position())
        self.settings.set_value('percent', adjustment.get_value())
        rect = self.get_allocation()
        self.settings.set_value('dims', (rect.width, rect.height))
        self.settings.write()

    def find_renames(self, widget, unktree, ctree):
        'User pressed "find renames" button'
        # Fake a rename find operation
        cmodel = ctree.get_model()
        cmodel.clear()
        umodel, paths = unktree.get_selection().get_selected_rows()
        if not paths: return
        u = umodel[paths[0]][0]
        for d in self.status[3]:
            cmodel.append( [d, u, '10', True] )

    def find_copies(self, widget, unktree, ctree):
        'User pressed "find copies" button'
        pass

    def accept_match(self, widget, unktree, ctree):
        'User pressed "accept match" button'
        cmodel, paths = ctree.get_selection().get_selected_rows()
        for path in paths:
            row = cmodel[path]
            src, dest, percent, sensitive = row
            if not sensitive: continue
            print 'hg copy --after', src, dest
            if src in self.status[3]:
                print 'hg rm', src
            # Mark all rows with this target file as non-sensitive
            for row in cmodel:
                if row[1] == dest:
                    row[3] = False

    def candidate_row_act(self, ctree, path, column, unktree):
        'User activated row of candidate list'
        self.accept_match(ctree, unktree, ctree)

    def show_diff(self, tree):
        'User selected a row in the candidate tree'
        model, paths = tree.get_selection().get_selected_rows()
        for path in paths:
            row = model[path]
            src, dest, percent, sensitive = row
            if sensitive:
                print 'show diffs from', src, 'to', dest
                if src in self.status[3]:
                    print src, 'must be resurrected'


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

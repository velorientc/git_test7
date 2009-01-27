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
        self.set_default_size(610, 400)
        self.settings = shlib.Settings('rename')
        self.connect('delete-event', self.save_settings)

        self.adjustment = gtk.Adjustment(50, 0, 100, 1)
        value = self.settings.get_value('percent', None)
        if value:
            self.adjustment.set_value(value)
        hscale = gtk.HScale(self.adjustment)
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
        fr.connect('pressed', self.find_renames, unknowntree)
        fc = gtk.Button('Find Copies')
        fc.connect('pressed', self.find_copies, unknowntree)
        hbox = gtk.HBox()
        hbox.pack_start(fr, True, True, 2)
        hbox.pack_start(fc, True, True, 2)
        vbox.pack_start(hbox, False, False, 2)

        unknownframe = gtk.Frame('Unrevisioned Files')
        unknownframe.add(vbox)

        # source, dest, percent match
        cmodel = gtk.ListStore(str, str, str)
        ctree = gtk.TreeView(cmodel)
        col = gtk.TreeViewColumn('Source', gtk.CellRendererText(), text=0)
        col.set_resizable(True)
        ctree.append_column(col)
        col = gtk.TreeViewColumn('Dest', gtk.CellRendererText(), text=1)
        col.set_resizable(True)
        ctree.append_column(col)
        col = gtk.TreeViewColumn('%', gtk.CellRendererText(), text=2)
        col.set_resizable(True)
        ctree.append_column(col)
        ctree.connect('row-activated', self.candidate_row_act)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(ctree)

        vbox = gtk.VBox()
        vbox.pack_start(scroller, True, True, 2)
        ac = gtk.Button('Accept Match')
        fr.connect('pressed', self.accept_match, ctree)
        hbox = gtk.HBox()
        hbox.pack_start(ac, False, False, 2)
        vbox.pack_start(hbox, False, False, 2)

        candidateframe = gtk.Frame('Candidate Matches')
        candidateframe.add(vbox)

        self.hpaned = gtk.HPaned()
        self.hpaned.pack1(unknownframe, True, True)
        self.hpaned.pack2(candidateframe, True, True)
        pos = self.settings.get_value('hpaned', None)
        if pos:
            self.hpaned.set_position(pos)

        topvbox.pack_start(self.hpaned, True, True, 2)

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

        self.vpaned = gtk.VPaned()
        self.vpaned.pack1(topvbox, True, False)
        self.vpaned.pack2(diffframe)
        pos = self.settings.get_value('vpaned', None)
        if pos:
            self.vpaned.set_position(pos)

        self.add(self.vpaned)
        self.connect('map_event', self.on_window_map_event)

    def on_window_map_event(self, event, param):
        try:
            repo = hg.repository(ui.ui(), self.root)
        except RepoError:
            return

        matcher = match.always(repo.root, repo.root)
        self.status = repo.status(node1=repo.dirstate.parents()[0], node2=None,
                match=matcher, ignored=False, clean=True, unknown=True)
        #(modified, added, removed, deleted, unknown, ignored, clean) = status

    def save_settings(self, widget, event):
        self.settings.set_value('vpaned', self.vpaned.get_position())
        self.settings.set_value('hpaned', self.hpaned.get_position())
        self.settings.set_value('percent', self.adjustment.get_value())
        self.settings.write()

    def find_renames(self, widget, unktree):
        'User pressed "find renames" button'
        pass

    def find_copies(self, widget, unktree):
        'User pressed "find copies" button'
        pass

    def accept_match(self, widget, ctree):
        'User pressed "accept match" button'
        pass

    def candidate_row_act(self, tree, path, column):
        'User activated row of candidate list'
        pass # accept copy or rename

    def adj_changed(self, adj):
        newvalue = adj.get_value()

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

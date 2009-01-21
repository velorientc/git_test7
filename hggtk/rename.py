#
# rename.py - TortoiseHg's dialogs for handling renames
#
# Copyright (C) 2009 Steve Borho <steve@borho.org>
#

import os
import sys
import gtk
from shlib import shell_notify
from mercurial import hg, ui, commands, match
from mercurial.repo import RepoError

class DetectRenameDialog(gtk.Window):
    """ Detect renames after they occur """
    def __init__(self, root=''):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        self.root = root
        self.set_title('Detect Renames in %s' + os.path.basename(root))

        adjustment = gtk.Adjustment(50, 0, 100, 1)
        adjustment.connect('value-changed', self._adj_changed)
        hscale = gtk.HScale(adjustment)
        self.add(mainvbox)

    def _adj_changed(self, adj):
        print adj.get_value()

def run(fname='', **opts):
    from dialog import entry_dialog
    title = 'Rename ' + fname
    dialog = entry_dialog(None, title, True, fname, rename_resp)
    dialog.orig = fname
    dialog.show_all()
    dialog.connect('destroy', gtk.main_quit)
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

def rename_resp(dialog, response):
    if response != gtk.RESPONSE_OK:
        print 'no response'
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

    # Sigh, some errors go to stdout, which is regrettable
    repo.ui.pushbuffer()
    commands.rename(repo.ui, repo, dialog.orig, new_name, **opts)
    out = repo.ui.popbuffer()
    if out:
        from dialog import error_dialog
        dialog = error_dialog(None, 'rename error', out)
        dialog.run()
    gtk.main_quit()

if __name__ == "__main__":
    opts = {'fname' : sys.argv[1]}
    run(**opts)

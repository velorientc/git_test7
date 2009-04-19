#
# rename.py - TortoiseHg's dialogs for handling renames
#
# Copyright (C) 2009 Steve Borho <steve@borho.org>
#

import os
import sys
import gtk
import cStringIO
from dialog import error_dialog
from mercurial.i18n import _
from mercurial import hg, ui, util, commands
from hglib import toutf, fromutf, rootpath, RepoError
import gtklib

def run(ui, *pats, **opts):
    fname, target = '', ''
    try:
        fname = pats[0]
        target = pats[1]
    except IndexError:
        pass
    from dialog import entry_dialog
    fname = util.normpath(fname)
    if target:
        target = toutf(util.normpath(target))
    else:
        target = toutf(fname)
    title = 'Rename ' + toutf(fname)
    dialog = entry_dialog(None, title, True, target, rename_resp)
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
        root = rootpath()
        repo = hg.repository(ui.ui(), root)
    except (ImportError, RepoError):
        gtk.main_quit()
        return

    new_name = fromutf(dialog.entry.get_text())
    opts = {}
    opts['force'] = False # Checkbox? Nah.
    opts['after'] = False
    opts['dry_run'] = False

    saved = sys.stderr
    errors = cStringIO.StringIO()
    toquit = False
    try:
        sys.stderr = errors
        repo.ui.pushbuffer()
        repo.ui.quiet = True
        try:
            commands.rename(repo.ui, repo, dialog.orig, new_name, **opts)
            toquit = True
        except (util.Abort, RepoError), inst:
            error_dialog(None, _('rename error'), str(inst))
            toquit = False
    finally:
        sys.stderr = saved
        textout = errors.getvalue() + repo.ui.popbuffer() 
        errors.close()
        if len(textout) > 1:
            error_dialog(None, _('rename error'), textout)
        elif toquit:
            gtk.main_quit()

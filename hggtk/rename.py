#
# rename.py - TortoiseHg's dialogs for handling renames
#
# Copyright (C) 2009 Steve Borho <steve@borho.org>
#

import sys
import gtk
import cStringIO

from mercurial import hg, ui, util, commands

from thgutil.i18n import _
from thgutil import hglib, paths

from hggtk import dialog

def run(ui, *pats, **opts):
    fname, target = '', ''
    try:
        fname = pats[0]
        target = pats[1]
    except IndexError:
        pass
    fname = util.normpath(fname)
    if target:
        target = hglib.toutf(util.normpath(target))
    else:
        target = hglib.toutf(fname)
    title = 'Rename ' + hglib.toutf(fname)
    dlg = dialog.entry_dialog(None, title, True, target, rename_resp)
    dlg.orig = fname
    return dlg

def rename_resp(dlg, response):
    if response != gtk.RESPONSE_OK:
        dlg.destroy()
        return
    try:
        root = paths.find_root()
        repo = hg.repository(ui.ui(), root)
    except (ImportError, hglib.RepoError):
        dlg.destroy()
        return

    new_name = hglib.fromutf(dlg.entry.get_text())
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
            commands.rename(repo.ui, repo, dlg.orig, new_name, **opts)
            toquit = True
        except (util.Abort, hglib.RepoError), inst:
            dlg.error_dialog(None, _('rename error'), str(inst))
            toquit = False
    finally:
        sys.stderr = saved
        textout = errors.getvalue() + repo.ui.popbuffer()
        errors.close()
        if len(textout) > 1:
            dlg.error_dialog(None, _('rename error'), textout)
        elif toquit:
            dlg.destroy()

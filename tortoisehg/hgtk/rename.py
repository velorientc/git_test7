# rename.py - TortoiseHg's dialogs for handling renames
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import sys
import gtk
import cStringIO
import shutil

from mercurial import hg, ui, util, commands, error

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths

from tortoisehg.hgtk import dialog, gdialog

def run(ui, *pats, **opts):
    fname, target = '', ''
    cwd = os.getcwd()
    root = paths.find_root(cwd)
    try:
        fname = util.canonpath(root, cwd, pats[0])
        target = util.canonpath(root, cwd, pats[1])
    except util.Abort, e:
        return gdialog.Prompt(_('Invalid path'), str(e), None)
    except IndexError:
        pass
    os.chdir(root)
    fname = util.normpath(fname)
    if target:
        target = hglib.toutf(util.normpath(target))
    else:
        target = hglib.toutf(fname)
    title = _('Rename ') + hglib.toutf(fname)
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
    except (ImportError, error.RepoError):
        dlg.destroy()
        return

    new_name = hglib.fromutf(dlg.entry.get_text())
    opts = {}
    opts['force'] = False # Checkbox? Nah.
    opts['after'] = True
    opts['dry_run'] = False

    saved = sys.stderr
    errors = cStringIO.StringIO()
    toquit = False
    try:
        sys.stderr = errors
        repo.ui.pushbuffer()
        repo.ui.quiet = True
        try:
            new_name = util.canonpath(root, root, new_name)
            targetdir = os.path.dirname(new_name) or '.'
            if dlg.orig.lower() == new_name.lower() and os.path.isdir(dlg.orig):
                os.rename(dlg.orig, new_name)
            else:
                if not os.path.isdir(targetdir):
                    os.makedirs(targetdir)
                shutil.move(dlg.orig, new_name)
            commands.rename(repo.ui, repo, dlg.orig, new_name, **opts)
            toquit = True
        except (OSError, IOError, util.Abort, error.RepoError), inst:
            dialog.error_dialog(None, _('rename error'), str(inst))
            toquit = False
    finally:
        sys.stderr = saved
        textout = errors.getvalue() + repo.ui.popbuffer()
        errors.close()
        if len(textout) > 1:
            dialog.error_dialog(None, _('rename error'), textout)
        elif toquit:
            dlg.destroy()

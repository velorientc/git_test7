# update.py - TortoiseHg's dialog for updating repo
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject

from mercurial import hg, ui

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths

from tortoisehg.hgtk import hgcmd, gtklib

_branch_tip_ = _('= Current Branch Tip =')

class UpdateDialog(gtk.Dialog):
    """ Dialog to update Mercurial repo """
    def __init__(self, rev=None):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self, title=_('Update'),
                            buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
        gtklib.set_tortoise_icon(self, 'menucheckout.ico')
        gtklib.set_tortoise_keys(self)
        self.set_resizable(False)
        self.set_has_separator(False)

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except hglib.RepoError:
            gobject.idle_add(self.destroy)
            return

        reponame = hglib.toutf(os.path.basename(repo.root))
        self.set_title(_('Update - %s') % reponame)

        # add update button
        updatebtn = gtk.Button(_('Update'))
        self.action_area.pack_end(updatebtn)

        # revision label & combobox
        hbox = gtk.HBox()
        lbl = gtk.Label(_('Update to:'))
        hbox.pack_start(lbl, False, False, 2)
        combo = gtk.combo_box_entry_new_text()
        entry = combo.child
        entry.set_width_chars(38)
        hbox.pack_start(combo, True, True, 2)
        self.vbox.pack_start(hbox, False, False, 4)

        # fill list of combo
        if rev != None:
            combo.append_text(str(rev))
        else:
            combo.append_text(_branch_tip_)
        combo.set_active(0)
        for b in repo.branchtags():
            combo.append_text(b)
        tags = list(repo.tags())
        tags.sort()
        tags.reverse()
        for t in tags:
            combo.append_text(t)

        # option
        overwrite = gtk.CheckButton(_('Overwrite local changes (--clean)'))
        self.vbox.pack_start(overwrite, False, False, 4)
        self.overwrite = overwrite

        # set signal handlers
        handler = lambda b: self.update(updatebtn, combo, repo)
        updatebtn.connect('clicked', handler)
        entry.connect('activate', handler)

        # prepare to show
        updatebtn.grab_focus()

    def update(self, button, combo, repo):
        overwrite = self.overwrite.get_active()
        rev = combo.get_active_text()

        cmdline = ['hg', 'update', '--verbose']
        if rev != _branch_tip_:
            cmdline.append('--rev')
            cmdline.append(rev)
        if overwrite:
            cmdline.append('--clean')
        else:
            cmdline.append('--check')
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.run()
        dlg.hide()
        if hasattr(self, 'notify_func'):
            self.notify_func(self.notify_args)
        if dlg.returncode == 0:
            self.destroy()

    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = args

def run(ui, *pats, **opts):
    return UpdateDialog(opts.get('rev'))

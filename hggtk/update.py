#
# update.py - TortoiseHg's dialog for updating repo
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import gtk
import gobject

from mercurial import hg, ui

from thgutil.i18n import _
from thgutil import hglib, paths

from hggtk import hgcmd, gtklib

_branch_tip_ = _('= Current Branch Tip =')

class UpdateDialog(gtk.Window):
    """ Dialog to update Mercurial repo """
    def __init__(self, rev=None):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        gtklib.set_tortoise_icon(self, 'menucheckout.ico')
        gtklib.set_tortoise_keys(self)

        self.set_default_size(350, 120)
        self.notify_func = None

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except hglib.RepoError:
            gobject.idle_add(self.destroy)
            return

        title = _('Update - %s') % hglib.toutf(os.path.basename(repo.root))
        self.set_title(title)

        vbox = gtk.VBox()
        self.add(vbox)

        hbox = gtk.HBox()
        lbl = gtk.Label(_('Update to:'))
        hbox.pack_start(lbl, False, False, 2)

        # revisions combo box
        combo = gtk.combo_box_new_text()
        hbox.pack_start(combo, True, True, 2)
        vbox.pack_start(hbox, False, False, 10)
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

        self.overwrite = gtk.CheckButton(_('Overwrite local changes (--clean)'))
        vbox.pack_start(self.overwrite, False, False, 10)

        hbbox = gtk.HButtonBox()
        hbbox.set_layout(gtk.BUTTONBOX_END)
        vbox.pack_start(hbbox, False, False, 2)
        close = gtk.Button(_('Close'))
        close.connect('clicked', lambda x: self.destroy())

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)
        key, modifier = gtk.accelerator_parse('Escape')
        close.add_accelerator('clicked', accelgroup, key, 0,
                gtk.ACCEL_VISIBLE)
        hbbox.add(close)

        update = gtk.Button(_('Update'))
        update.connect('clicked', self.update, combo, repo)
        mod = gtklib.get_thg_modifier()
        key, modifier = gtk.accelerator_parse(mod+'Return')
        update.add_accelerator('clicked', accelgroup, key, modifier,
                gtk.ACCEL_VISIBLE)
        hbbox.add(update)
        update.grab_focus()

    def update(self, button, combo, repo):
        overwrite = self.overwrite.get_active()
        rev = combo.get_active_text()

        cmdline = ['hg', 'update', '--verbose']
        if rev != _branch_tip_:
            cmdline.append('--rev')
            cmdline.append(rev)
        if overwrite:
            cmdline.append('--clean')
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.run()
        dlg.hide()
        if self.notify_func:
            self.notify_func(self.notify_args)
        if dlg.returncode == 0:
            self.destroy()

    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = args

def run(ui, *pats, **opts):
    return UpdateDialog(opts.get('rev'))

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

BRANCH_TIP = _('= Current Branch Tip =')

MODE_NORMAL   = 'normal'
MODE_UPDATING = 'updating'

class UpdateDialog(gtk.Dialog):
    """ Dialog to update Mercurial repo """
    def __init__(self, rev=None):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self)
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

        # add dialog buttons
        self.updatebtn = gtk.Button(_('Update'))
        self.updatebtn.connect('clicked', lambda b: self.update(repo))
        self.action_area.pack_end(self.updatebtn)
        self.closebtn = self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)

        # revision label & combobox
        self.revhbox = hbox = gtk.HBox()
        lbl = gtk.Label(_('Update to:'))
        hbox.pack_start(lbl, False, False, 2)
        self.revcombo = combo = gtk.combo_box_entry_new_text()
        entry = combo.child
        entry.connect('activate', lambda b: self.update(repo))
        entry.set_width_chars(38)
        hbox.pack_start(combo, True, True, 2)
        self.vbox.pack_start(hbox, False, False, 4)

        # fill list of combo
        if rev != None:
            combo.append_text(str(rev))
        else:
            combo.append_text(BRANCH_TIP)
        combo.set_active(0)
        for b in repo.branchtags():
            combo.append_text(b)
        tags = list(repo.tags())
        tags.sort()
        tags.reverse()
        for t in tags:
            combo.append_text(t)

        # option
        self.optclean = gtk.CheckButton(_('Overwrite local changes (--clean)'))
        self.vbox.pack_start(self.optclean, False, False, 4)

        # prepare to show
        self.updatebtn.grab_focus()
        gobject.idle_add(self.after_init)

    def after_init(self):
        self.cancelbtn = self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        self.cancelbtn.hide()

    def switch_to(self, mode):
        if mode == MODE_NORMAL:
            normal = True
        elif mode == MODE_UPDATING:
            normal = False
            self.cancelbtn.grab_focus()
        else:
            raise _('unknown mode name: %s') % mode
        updating = not normal

        self.revhbox.set_sensitive(normal)
        self.optclean.set_sensitive(normal)
        self.updatebtn.set_property('visible', normal)
        self.closebtn.set_property('visible', normal)
        self.cancelbtn.set_property('visible', updating)

    def update(self, repo):
        clean = self.optclean.get_active()
        rev = self.revcombo.get_active_text()

        cmdline = ['hg', 'update', '--verbose']
        if rev != BRANCH_TIP:
            cmdline.append('--rev')
            cmdline.append(rev)
        if clean:
            cmdline.append('--clean')
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

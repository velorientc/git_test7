# p4pending.py - Display pending p4 changelists, created by perfarce extension
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject

from mercurial import error

from tortoisehg.util.i18n import _
from tortoisehg.hgtk import gtklib, gdialog, cslist


class PerforcePending(gdialog.GDialog):
    'Dialog for selecting a revision'
    def __init__(self, repo, pending, graphview):
        gdialog.GDialog.__init__(self, resizable=True)
        self.repo = repo
        self.graphview = graphview
        self.pending = pending

    def get_icon(self):
        return 'menulog.ico'

    def get_title(self, reponame):
        return _('Pending Perforce Changelists - %s') % reponame

    def get_defsize(self):
        return (500, 380)

    def get_body(self, vbox):
        # layout table
        self.table = table = gtklib.LayoutTable()
        vbox.pack_start(table, True, True, 2)

        ## changelist combo
        clcombo = gtk.combo_box_new_text()
        clcombo.connect('changed', self.changelist_selected)
        table.add_row(_('Changelist:'), clcombo)

        ## changeset list
        self.cslist = cslist.ChangesetList()
        self.cslist.set_activatable_enable(True)
        self.cslist.connect('item-activated', self.item_activated)
        table.add_row(None, self.cslist, padding=False,
                      yopt=gtk.FILL|gtk.EXPAND)

        ### fill combo list
        for changelist in self.pending:
            clcombo.append_text(changelist)
        clcombo.set_active(0)

    def item_activated(self, cslist, hash, *args):
        try:
            rev = self.repo[hash].rev()
        except error.LookupError:
            return
        if self.graphview:
            self.graphview.set_revision_id(rev)

    def get_buttons(self):
        return [('submit', _('Submit'), gtk.RESPONSE_OK),
                ('revert', _('Revert'), gtk.RESPONSE_CANCEL),
                ('close', gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)]

    def get_default_button(self):
        return 'submit'

    def get_action_map(self):
        return {gtk.RESPONSE_OK: self.submit,
                gtk.RESPONSE_CANCEL: self.revert}

    def changelist_selected(self, combo):
        'User has selected a changelist, fill cslist'
        curcl = combo.get_active_text()
        revs = [self.repo[hash] for hash in self.pending[curcl]]
        self.cslist.clear()
        self.cslist.update(revs, self.repo)
        sensitive = not curcl.endswith('(submitted)')
        self.buttons['submit'].set_property('sensitive', sensitive)
        self.buttons['revert'].set_property('sensitive', sensitive)
        self.curcl = curcl

    def switch_to(self, normal, working, cmd):
        self.table.set_sensitive(normal)
        self.buttons['submit'].set_property('visible', normal)
        self.buttons['revert'].set_property('visible', normal)
        self.buttons['close'].set_property('visible', normal)
        if normal:
            self.buttons['close'].grab_focus()

    def command_done(self, returncode, useraborted, *args):
        if returncode == 0:
            self.cmd.set_result(_('Finished'), style='ok')
        elif useraborted:
            self.cmd.set_result(_('Canceled'), style='error')
        else:
            self.cmd.set_result(_('Failed'), style='error')

    def submit(self):
        assert(self.curcl.endswith('(pending)'))
        cmdline = ['hg', 'p4submit', '--verbose', self.curcl[:-10]]
        self.execute_command(cmdline)

    def revert(self):
        assert(self.curcl.endswith('(pending)'))
        cmdline = ['hg', 'p4revert', '--verbose', self.curcl[:-10]]
        self.execute_command(cmdline)

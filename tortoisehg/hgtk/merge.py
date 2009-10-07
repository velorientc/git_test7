# merge.py - TortoiseHg's dialog for merging revisions
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

from tortoisehg.hgtk import changesetinfo, gtklib, commit, gdialog, hgcmd

class MergeDialog(gtk.Dialog):
    """ Dialog to merge revisions of a Mercurial repo """
    def __init__(self, rev=None):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self)
        gtklib.set_tortoise_icon(self, 'menumerge.ico')
        gtklib.set_tortoise_keys(self)
        self.set_default_size(350, 120)
        self.set_has_separator(False)
        self.notify_func = None

        if not rev:
            gdialog.Prompt(_('Unable to merge'),
                           _('Must supply a target revision'), self).run()
            gobject.idle_add(self.destroy)
            return

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except hglib.RepoError:
            gobject.idle_add(self.destroy)
            return
        self.set_title(_('Merging in %s') % hglib.get_reponame(repo))

        frame = gtk.Frame(_('Merge target (other)'))
        self.otherrev, desc = changesetinfo.changesetinfo(repo, rev, True)
        frame.add(desc)
        frame.set_border_width(5)
        self.vbox.pack_start(frame, False, False)

        frame = gtk.Frame(_('Current revision (local)'))
        self.localrev, desc = changesetinfo.changesetinfo(repo, '.', True)
        frame.add(desc)
        frame.set_border_width(5)
        self.vbox.pack_start(frame, False, False)

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)
        mod = gtklib.get_thg_modifier()

        self.closebtn = gtk.Button(_('Close'))
        self.closebtn.connect('clicked', lambda x: self.destroy())
        self.undobtn = gtk.Button(_('Undo'))
        self.undobtn.set_sensitive(False)
        self.commitbtn = gtk.Button(_('Commit'))
        self.commitbtn.set_sensitive(False)
        self.mergebtn = gtk.Button(_('Merge'))

        self.action_area.add(self.mergebtn)
        self.action_area.add(self.commitbtn)
        self.action_area.add(self.undobtn)
        self.action_area.add(self.closebtn)

        vlist = gtk.ListStore(str, bool)
        combo = gtk.ComboBoxEntry(vlist, 0)
        self.mergetool = combo
        combo.set_row_separator_func(lambda model, path: model[path][1])
        combo.child.set_width_chars(8)
        lbl = gtk.Label(_('Merge tool:'))
        lbl.set_alignment(1, 0.5)
        self.action_area.add(lbl)
        self.action_area.add(combo)
        vlist.append(('', False))
        for tool in hglib.mergetools(repo.ui):
            vlist.append((hglib.toutf(tool), False))

        self.mergebtn.connect('clicked', lambda b: self.domerge())
        self.commitbtn.connect('clicked', lambda b: self.docommit())
        self.undobtn.connect('clicked', lambda b: self.doundo())
        self.mergebtn.grab_focus()

    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = args

    def domerge(self):
        cmdline = ['hg', 'merge', '--rev', self.otherrev]
        tool = hglib.fromutf(self.mergetool.child.get_text())
        if tool:
            oldmergeenv = os.environ.get('HGMERGE')
            os.environ['HGMERGE'] = tool
        dlg = hgcmd.CmdDialog(cmdline, False)
        dlg.run()
        dlg.hide()
        repo = hg.repository(ui.ui(), path=paths.find_root())
        if len(repo.parents()) == 1:
            return
        if tool:
            if oldmergeenv:
                os.environ['HGMERGE'] = oldmergeenv
            else:
                del os.environ['HGMERGE']
        if self.notify_func:
            self.notify_func(self.notify_args)
        self.mergetool.set_sensitive(False)
        self.mergebtn.set_sensitive(False)
        self.undobtn.set_sensitive(True)
        self.commitbtn.set_sensitive(True)
        self.commitbtn.grab_focus()

    def docommit(self):
        dlg = commit.run(ui.ui())
        dlg.set_transient_for(self)
        dlg.set_modal(True)
        dlg.set_notify_func(self.commit_notify, dlg)
        dlg.display()

    def commit_notify(self, dlg):
        # refresh the log tool
        if self.notify_func:
            self.notify_func(self.notify_args)
        # hide merge dialog
        self.hide()
        # hide commit tool
        dlg.ready = False  # disables refresh
        dlg.hide()
        gobject.timeout_add(50, self.destroy)

    def doundo(self):
        response = gdialog.Confirm(_('Confirm undo merge'), [], self,
                       _('Clean checkout of original revision?')).run()
        if response != gtk.RESPONSE_YES:
            return
        cmdline = ['hg', 'update', '--rev', self.localrev, '--clean']
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.run()
        dlg.hide()
        if self.notify_func:
            self.notify_func(self.notify_args)
        self.mergetool.set_sensitive(True)
        self.mergebtn.set_sensitive(True)
        self.mergebtn.grab_focus()
        self.undobtn.set_sensitive(False)
        self.commitbtn.set_sensitive(False)

def run(ui, *pats, **opts):
    return MergeDialog(opts.get('rev'))

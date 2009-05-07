#
# merge.py - TortoiseHg's dialog for merging revisions
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import gtk
import gobject
import re
import sys

from mercurial.node import short, nullrev
from mercurial.hgweb import webutil
from mercurial.i18n import _
from mercurial import util, hg, ui

import gdialog
import hgcmd
import shlib
import hglib

class MergeDialog(gtk.Window):
    """ Dialog to merge revisions of a Mercurial repo """
    def __init__(self, rev=None):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        shlib.set_tortoise_icon(self, 'menumerge.ico')
        shlib.set_tortoise_keys(self)
        self.notify_func = None

        if not rev:
            gdialog.Prompt(_('Unable to merge'),
                           _('Must supply a target revision'), self).run()
            gobject.idle_add(self.destroy)
            return

        try:
            repo = hg.repository(ui.ui(), path=hglib.rootpath())
        except hglib.RepoError:
            gobject.idle_add(self.destroy)
            return

        title = _("Merging in ") + hglib.toutf(os.path.basename(repo.root))
        self.set_title(title)
        self.set_default_size(350, 120)

        vbox = gtk.VBox()
        self.add(vbox)

        frame = gtk.Frame(_('Merge target (other)'))
        lbl = gtk.Label()
        other, desc = self.revdesc(repo, rev)
        lbl.set_markup(desc)
        lbl.set_alignment(0, 0)
        frame.add(lbl)
        frame.set_border_width(5)
        vbox.pack_start(frame, False, False, 2)

        frame = gtk.Frame(_('Current revision (local)'))
        lbl = gtk.Label()
        local, desc = self.revdesc(repo, '.')
        lbl.set_markup(desc)
        lbl.set_alignment(0, 0)
        frame.add(lbl)
        frame.set_border_width(5)
        vbox.pack_start(frame, False, False, 2)

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)
        mod = shlib.get_thg_modifier()

        hbbox = gtk.HButtonBox()
        hbbox.set_layout(gtk.BUTTONBOX_END)
        vbox.pack_start(hbbox, False, False, 2)

        close = gtk.Button(_('Close'))
        close.connect('clicked', lambda x: self.destroy())
        key, modifier = gtk.accelerator_parse('Escape')
        close.add_accelerator('clicked', accelgroup, key, 0,
                gtk.ACCEL_VISIBLE)
        hbbox.add(close)

        undo = gtk.Button(_('Undo'))
        hbbox.add(undo)
        undo.set_sensitive(False)

        commit = gtk.Button(_('Commit'))
        hbbox.add(commit)
        commit.set_sensitive(False)

        merge = gtk.Button(_('Merge'))
        key, modifier = gtk.accelerator_parse(mod+'Return')
        merge.add_accelerator('clicked', accelgroup, key, modifier,
                gtk.ACCEL_VISIBLE)
        hbbox.add(merge)
        merge.grab_focus()

        undo.connect('clicked', self.undo, local, merge, commit)
        merge.connect('clicked', self.merge, other, commit, undo)
        commit.connect('clicked', self.commit)

    def revdesc(self, repo, revid):
        ctx = repo.changectx(revid)
        revstr = str(ctx.rev())
        summary = ctx.description().replace('\0', '')
        summary = summary.split('\n')[0]
        escape = gobject.markup_escape_text
        desc =  '<b>rev</b>\t\t: %s\n' % escape(revstr)
        desc += '<b>summary</b>\t: %s\n' % escape(summary[:80])
        desc += '<b>user</b>\t\t: %s\n' % escape(ctx.user())
        desc += '<b>date</b>\t\t: %s\n' % escape(hglib.displaytime(ctx.date()))
        node = repo.lookup(revid)
        tags = repo.nodetags(node)
        desc += '<b>branch</b>\t: ' + escape(ctx.branch())
        if tags:
            desc += '\n<b>tags</b>\t\t: ' + escape(', '.join(tags))
        if node not in repo.heads():
            desc += '\n<b>Not a head revision!</b>'
        return revstr, hglib.toutf(desc)

    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = args

    def merge(self, button, other, commit, undo):
        cmdline = ['hg', 'merge', '--rev', other]
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.run()
        dlg.hide()
        if self.notify_func:
            self.notify_func(self.notify_args)
        button.set_sensitive(False)
        undo.set_sensitive(True)
        commit.set_sensitive(True)
        commit.grab_focus()

    def commit(self, button):
        import commit
        dlg = commit.run(ui.ui())
        dlg.set_modal(True)
        dlg.set_notify_func(self.notify_func, self.notify_args)
        dlg.display()

    def undo(self, button, local, merge, commit):
        response = gdialog.Confirm(_('undo merge'), [], self,
                       _('Clean checkout of original revision?')).run()
        if response != gtk.RESPONSE_YES:
            return
        cmdline = ['hg', 'update', '--rev', local, '--clean']
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.run()
        dlg.hide()
        if self.notify_func:
            self.notify_func(self.notify_args)
        button.set_sensitive(False)
        commit.set_sensitive(False)
        merge.set_sensitive(True)
        merge.grab_focus()

def run(ui, *pats, **opts):
    return MergeDialog(opts.get('rev'))

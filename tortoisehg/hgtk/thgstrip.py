# thgstrip.py - strip dialog for TortoiseHg
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject
import pango

from mercurial import hg, ui
from mercurial.node import nullrev

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths

from tortoisehg.hgtk import hgcmd, gtklib, gdialog
from tortoisehg.hgtk import changesetinfo as csinfo

MODE_NORMAL  = 'normal'
MODE_WORKING = 'working'

class StripDialog(gtk.Dialog):
    """ Dialog to strip changesets """

    def __init__(self, rev=None, *pats):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self)
        gtklib.set_tortoise_icon(self, 'menudelete.ico')
        gtklib.set_tortoise_keys(self)
        self.set_resizable(False)
        self.set_has_separator(False)
        self.connect('response', self.dialog_response)
        self.timeout_queue = []

        # buttons
        self.stripbtn = self.add_button(_('Strip'), gtk.RESPONSE_OK)
        self.closebtn = self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except hglib.RepoError:
            gobject.idle_add(self.destroy)
            return
        self.repo = repo
        self.set_title(_('Strip - %s') % hglib.get_reponame(repo))

        if len(pats) > 0:
            rev = pats[0]
        elif rev is None:
            rev = 'tip'
        self.prevrev = rev = str(rev)

        # layout table
        self.table = table = gtklib.LayoutTable()
        self.vbox.pack_start(table, True, True, 2)

        ## target revision combo
        self.revcombo = gtk.combo_box_entry_new_text()
        table.add_row(_('Strip:'), self.revcombo)
        self.revcombo.connect('changed', lambda c: self.update_on_timeout())
        reventry = self.revcombo.child
        reventry.set_text(rev)
        reventry.set_width_chars(32)
        reventry.connect('activate', lambda b: self.response(gtk.RESPONSE_OK))

        ## result label
        self.resultlbl = gtk.Label()
        self.resultlbl.set_alignment(0, 0.5)

        ## view option
        self.compactopt = gtk.CheckButton(_('Use compact view'))
        table.add_row(_('Result:'), self.resultlbl, self.compactopt,
                      padding=False, expand=0)

        ## result changesets
        self.resuleview = rview = gtk.ScrolledWindow()
        table.add_row(None, self.resuleview, padding=False)
        rview.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        rview.set_size_request(400, 180)
        rview.size_request()

        self.resultbox = gtk.VBox()
        rview.add_with_viewport(self.resultbox)

        ## preview status
        self.pstatbox = gtk.HBox()
        table.add_row(None, self.pstatbox, padding=False)
        self.pstatlbl = gtk.Label()
        self.pstatbox.pack_start(self.pstatlbl, False, False, 2)
        self.pstatlbl.set_alignment(0, 0.5)
        self.pstatlbl.set_size_request(-1, 24)
        self.pstatlbl.size_request()
        self.allbtn = gtk.Button(_('Show all')) # add later
        self.allbtn.connect('clicked',
                lambda b: self.preview_changesets(nocheck=True, limit=False))

        # prepare to show
        self.preview_changesets(nocheck=True)
        self.stripbtn.grab_focus()
        gobject.idle_add(self.after_init)

    def after_init(self):
        # add 'Show all' button
        self.pstatbox.pack_start(self.allbtn, False, False, 4)

        # CmdWidget
        self.cmd = hgcmd.CmdWidget()
        self.cmd.show_all()
        self.cmd.hide()
        self.vbox.pack_start(self.cmd, True, True, 6)

        # abort button
        self.abortbtn = self.add_button(_('Abort'), gtk.RESPONSE_CANCEL)
        self.abortbtn.hide()

    def set_notify_func(self, func, *args, **kargs):
        self.notify_func = func
        self.notify_args = args
        self.notify_kargs = kargs

    def preview_changesets(self, nocheck=False, limit=True):
        revstr = self.revcombo.get_active_text()
        if len(revstr) == 0 or (not nocheck and self.prevrev == revstr):
            return
        self.prevrev = revstr
        # enumerate all descendants
        # borrowed from 'strip' function in 'mercurial/repair.py'
        cl = self.repo.changelog
        try:
            striprev = self.repo[revstr].rev()
        except (hglib.RepoError, hglib.LookupError):
            return
        if striprev is None:
            return
        tostrip = [striprev,]
        for r in xrange(striprev + 1, len(cl)):
            parents = cl.parentrevs(r)
            if parents[0] in tostrip or parents[1] in tostrip:
                tostrip.append(r)

        # update changeset preview
        for child in self.resultbox.get_children():
            self.resultbox.remove(child)
        showrevs = limit and tostrip[:50] or tostrip
        for rev in showrevs:
            r, info = csinfo.changesetinfo(self.repo, rev)
            self.resultbox.pack_start(info, False, False, 2)
            if not rev == tostrip[-1]:
                self.resultbox.pack_start(gtk.HSeparator())
        self.resultbox.show_all()

        # update info label
        numstrip = len(tostrip)
        self.resultlbl.set_markup(_('<span weight="bold">%s changesets</span>'
                                    ' will be stripped') % numstrip)

        # update preview status
        if numstrip > len(showrevs):
            text = _('Displaying %(count)d of %(total)d changesets') \
                        % dict(count=len(showrevs), total=numstrip)
            self.allbtn.show()
        else:
            text = _('Displaying all changesets')
            self.allbtn.hide()
        self.pstatlbl.set_text(text)

    def dialog_response(self, dialog, response_id):
        def abort():
            self.cmd.stop()
            self.cmd.show_log()
            self.switch_to(MODE_NORMAL, cmd=False)
        # Strip button
        if response_id == gtk.RESPONSE_OK:
            self.strip()
        # Close button or dialog closing by the user
        elif response_id in (gtk.RESPONSE_CLOSE, gtk.RESPONSE_DELETE_EVENT):
            if self.cmd.is_alive():
                ret = gdialog.Confirm(_('Confirm Abort'), [], self,
                                      _('Do you want to abort?')).run()
                if ret == gtk.RESPONSE_YES:
                    abort()
            else:
                self.destroy()
                return # close dialog
        # Abort button
        elif response_id == gtk.RESPONSE_CANCEL:
            abort()
        else:
            raise _('unexpected response id: %s') % response_id

        self.run() # don't close dialog

    def update_on_timeout(self):
        def timeout(id):
            if self.timeout_queue[-1] == id[0]:
                self.preview_changesets()
                self.timeout_queue = []
            return False # don't repeat
        event_id = [None]
        event_id[0] = gobject.timeout_add(600, timeout, event_id)
        self.timeout_queue.append(event_id[0])

    def switch_to(self, mode, cmd=True):
        if mode == MODE_NORMAL:
            normal = True
            self.closebtn.grab_focus()
        elif mode == MODE_WORKING:
            normal = False
            self.abortbtn.grab_focus()
        else:
            raise _('unknown mode name: %s') % mode
        working = not normal

        self.table.set_sensitive(normal)
        self.stripbtn.set_property('visible', normal)
        self.closebtn.set_property('visible', normal)
        if cmd:
            self.cmd.set_property('visible', working)
        self.abortbtn.set_property('visible', working)

    def strip(self):
        revstr = self.revcombo.get_active_text()
        cmdline = ['hg', 'strip', '--verbose', revstr]
        def cmd_done(returncode, useraborted):
            self.switch_to(MODE_NORMAL, cmd=False)
            if returncode == 0:
                if hasattr(self, 'notify_func'):
                    self.notify_func(*self.notify_args, **self.notify_kargs)
                if not self.cmd.is_show_log():
                    self.response(gtk.RESPONSE_CLOSE)
                self.cmd.set_result(_('Stripped successfully'), style='ok')
            elif useraborted:
                self.cmd.set_result(_('Canceled stripping'), style='error')
            else:
                self.cmd.set_result(_('Failed to strip'), style='error')
        self.switch_to(MODE_WORKING)
        self.cmd.execute(cmdline, cmd_done)

def run(ui, *pats, **opts):
    return StripDialog(None, *pats)

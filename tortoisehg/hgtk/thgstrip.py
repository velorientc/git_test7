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
        rev = str(rev)
        self.currev = None
        self.curnum = None

        # layout table
        self.table = table = gtklib.LayoutTable()
        self.vbox.pack_start(table, True, True, 2)

        ## target revision combo
        self.revcombo = gtk.combo_box_entry_new_text()
        table.add_row(_('Strip:'), self.revcombo)
        self.revcombo.connect('changed', lambda c: self.preview(queue=True))
        reventry = self.revcombo.child
        reventry.set_text(rev)
        reventry.set_width_chars(32)
        reventry.connect('activate', lambda b: self.response(gtk.RESPONSE_OK))

        def createlabel():
            label = gtk.Label()
            label.set_alignment(0, 0.5)
            label.set_size_request(-1, 24)
            label.size_request()
            return label

        ## result label
        self.resultlbl = createlabel()
        table.add_row(_('Preview:'), self.resultlbl, padding=False)

        ## preview box
        pframe = gtk.Frame()
        table.add_row(None, pframe, padding=False)
        pframe.set_shadow_type(gtk.SHADOW_IN)
        pbox = gtk.VBox()
        pframe.add(pbox)

        ### preview status box
        self.pstatbox = gtk.HBox()
        pbox.pack_start(self.pstatbox, True, True)
        pbox.pack_start(gtk.HSeparator(), True, True, 2)

        #### status label
        self.pstatlbl = createlabel()
        self.pstatbox.pack_start(self.pstatlbl, False, False, 2)

        #### show all button
        self.allbtn = gtk.Button(_('Show all')) # add later
        self.allbtn.connect('clicked',
                lambda b: self.preview(limit=False))

        #### preview option
        self.compactopt = gtk.CheckButton(_('Use compact view'))
        self.pstatbox.pack_end(self.compactopt, False, False, 2)

        ### changeset view
        rview = gtk.ScrolledWindow()
        pbox.add(rview)
        rview.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        rview.set_size_request(400, 180)
        rview.size_request()
        self.resultbox = gtk.VBox()
        rview.add_with_viewport(self.resultbox)
        rview.child.set_shadow_type(gtk.SHADOW_NONE)

        # prepare to show
        self.preview()
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

    def preview(self, limit=True, queue=False):
        def clear_preview():
            for child in self.resultbox.get_children():
                self.resultbox.remove(child)
        def update_info(num=None):
            if num is None:
                info = '<span weight="bold" foreground="#880000">%s</span>' \
                            % _('Unknown revision!')
            else:
                info = _('<span weight="bold">%s changesets</span> will'
                         ' be stripped') % num
            self.resultlbl.set_markup(info)
        def update_stat(show=None, total=None):
            if show is None or total is None:
                all = False
                stat = _('No changesets to display')
            else:
                all = show == total
                if all:
                    stat = _('Displaying all changesets')
                else:
                    stat = _('Displaying %(count)d of %(total)d changesets') \
                                % dict(count=show, total=total)
            self.pstatlbl.set_text(stat)
            return all

        # check revision
        rev = self.get_rev()
        if rev is None:
            clear_preview()
            update_info()
            update_stat()
            self.timeout_queue = []
            self.currev = None
            return
        elif limit and self.currev == rev: # is already shown?
            update_info(self.curnum)
            return
        elif queue: # queueing if need
            def timeout(eid):
                if self.timeout_queue and self.timeout_queue[-1] == eid[0]:
                    self.preview()
                    self.timeout_queue = []
                return False # don't repeat
            event_id = [None]
            event_id[0] = gobject.timeout_add(600, timeout, event_id)
            self.timeout_queue.append(event_id[0])
            return
        self.currev = rev

        # enumerate all descendants
        # borrowed from strip() in 'mercurial/repair.py'
        cl = self.repo.changelog
        tostrip = [rev,]
        for r in xrange(rev + 1, len(cl)):
            parents = cl.parentrevs(r)
            if parents[0] in tostrip or parents[1] in tostrip:
                tostrip.append(r)
        self.curnum = numtotal = len(tostrip)

        LIM = 50
        def add_csinfo(revnum):
            info = csinfo.changesetinfo(self.repo, revnum)[1]
            self.resultbox.pack_start(info, False, False, 2)
        def add_sep():
            self.resultbox.pack_start(gtk.HSeparator())
        def add_snip():
            snipbox = gtk.HBox()
            self.resultbox.pack_start(snipbox, False, False, 4)
            spacer = gtk.Label()
            snipbox.pack_start(spacer, False, False)
            spacer.set_width_chars(24)
            sniplbl = gtk.Label()
            snipbox.pack_start(sniplbl, False, False)
            sniplbl.set_markup('<span size="large" weight="heavy"'
                               ' font_family="monospace">...</span>')
            sniplbl.set_angle(90)
            snipbox.pack_start(gtk.Label())

        # update changeset preview
        if limit and numtotal > LIM:
            toshow, lastrev = tostrip[:LIM-1], tostrip[LIM-1:][-1]
        else:
            toshow, lastrev = tostrip, None
        numshow = len(toshow) + (lastrev and 1 or 0)
        clear_preview()
        for r in toshow:
            add_csinfo(r)
            if not r == toshow[-1]: # no need to append to the last
                add_sep()
        if lastrev:
            add_snip()
            add_csinfo(lastrev)
        self.resultbox.show_all()

        # update info label
        update_info(numtotal)

        # update preview status & button
        all = update_stat(numshow, numtotal)
        self.allbtn.set_property('visible', not all)

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

    def get_rev(self):
        """ Return integer revision number or None """
        revstr = self.revcombo.get_active_text()
        if len(revstr) == 0:
            return None
        try:
            revnum = self.repo[revstr].rev()
        except (hglib.RepoError, hglib.LookupError):
            return None
        return revnum

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

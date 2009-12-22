# thgstrip.py - strip dialog for TortoiseHg
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import re
import os
import gtk
import gobject
import pango

from mercurial import hg, ui, error
from mercurial.node import nullrev

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths

from tortoisehg.hgtk import csinfo, hgcmd, gtklib, gdialog, cslist

MODE_NORMAL  = 'normal'
MODE_WORKING = 'working'

class StripDialog(gtk.Dialog):
    """ Dialog to strip changesets """

    def __init__(self, rev=None, *pats):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self)
        gtklib.set_tortoise_icon(self, 'menudelete.ico')
        gtklib.set_tortoise_keys(self)
        self.set_default_size(480, 360)
        self.set_has_separator(False)

        # buttons
        self.stripbtn = self.add_button(_('Strip'), gtk.RESPONSE_OK)
        self.closebtn = self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except error.RepoError:
            gtklib.idle_add_single_call(self.destroy)
            return
        self.repo = repo
        self.set_title(_('Strip - %s') % hglib.get_reponame(repo))

        if len(pats) > 0:
            rev = pats[0]
        elif rev is None:
            rev = 'tip'
        rev = str(rev)

        # layout table
        self.table = table = gtklib.LayoutTable()
        self.vbox.pack_start(table, True, True, 2)

        ## target revision combo
        self.revcombo = gtk.combo_box_entry_new_text()
        table.add_row(_('Strip:'), self.revcombo)
        reventry = self.revcombo.child
        reventry.set_width_chars(32)

        ### fill combo list
        self.revcombo.append_text(rev)
        self.revcombo.set_active(0)
        dblist = repo.ui.config('tortoisehg', 'deadbranch', '')
        deadbranches = [ x.strip() for x in dblist.split(',') ]
        for name in repo.branchtags().keys():
            if name not in deadbranches:
                self.revcombo.append_text(name)

        tags = list(repo.tags())
        tags.sort()
        tags.reverse()
        for tag in tags:
            self.revcombo.append_text(tag)

        def createlabel():
            label = gtk.Label()
            label.set_alignment(0, 0.5)
            label.set_size_request(-1, 24)
            label.size_request()
            return label

        ## result label
        self.resultlbl = createlabel()
        table.add_row(_('Preview:'), self.resultlbl, padding=False)

        ## changeset list
        self.cslist = cslist.ChangesetList()
        table.add_row(None, self.cslist, padding=False,
                      yopt=gtk.FILL|gtk.EXPAND)

        ## options
        self.expander = gtk.Expander(_('Options:'))
        self.expander.connect('notify::expanded', self.options_expanded)

        ### force option (fixed)
        self.forceopt = gtk.CheckButton(_('Discard local changes, no backup'
                                          ' (-f/--force)'))
        table.add_row(self.expander, self.forceopt)

        # signal handlers
        self.connect('response', self.dialog_response)
        reventry.connect('activate', lambda b: self.response(gtk.RESPONSE_OK))
        self.revcombo.connect('changed', lambda c: self.preview(queue=True))
        self.cslist.connect('list-updated', self.preview_updated)

        # prepare to show
        self.preview()
        self.stripbtn.grab_focus()
        gtklib.idle_add_single_call(self.after_init)

    def after_init(self):
        # backup types (foldable)
        self.butable = gtklib.LayoutTable()
        self.vbox.pack_start(self.butable, False, False)
        def add_type(desc):
            group = hasattr(self, 'buopt_all') and self.buopt_all or None
            radio = gtk.RadioButton(group, desc)
            self.butable.add_row(None, radio, ypad=0)
            return radio
        self.buopt_all = add_type(_('Backup all (default)'))
        self.buopt_part = add_type(_('Backup unrelated changesets'
                                     ' (-b/--backup)'))
        self.buopt_none = add_type(_('No backup (-n/--nobackup)'))

        # layout group
        layout = gtklib.LayoutGroup()
        layout.add(self.table, self.butable, force=True)

        # CmdWidget
        self.cmd = hgcmd.CmdWidget()
        self.cmd.show_all()
        self.cmd.hide()
        self.vbox.pack_start(self.cmd, False, False, 6)

        # abort button
        self.abortbtn = self.add_button(_('Abort'), gtk.RESPONSE_CANCEL)
        self.abortbtn.hide()

    def set_notify_func(self, func, *args, **kargs):
        self.notify_func = func
        self.notify_args = args
        self.notify_kargs = kargs

    def preview(self, limit=True, queue=False, force=False):
        # check revision
        rev = self.get_rev()
        if rev is None:
            self.cslist.clear()
            return

        # enumerate all descendants
        # borrowed from strip() in 'mercurial/repair.py'
        cl = self.repo.changelog
        tostrip = [rev,]
        for r in xrange(rev + 1, len(cl)):
            parents = cl.parentrevs(r)
            if parents[0] in tostrip or parents[1] in tostrip:
                tostrip.append(r)

        # update preview
        self.cslist.update(tostrip, self.repo, limit, queue)

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

    def options_expanded(self, expander, *args):
        if expander.get_expanded():
            self.butable.show_all()
        else:
            self.butable.hide()

    def preview_updated(self, cslist, total, *args):
        if total is None:
            info = gtklib.markup(_('Unknown revision!'),
                                 weight='bold', color=gtklib.DRED)
        else:
            inner = gtklib.markup(_('%s changesets') % total, weight='bold')
            info = _('%s will be stripped') % inner
        self.resultlbl.set_markup(info)
        self.stripbtn.set_sensitive(bool(total))

    def get_rev(self):
        """ Return integer revision number or None """
        revstr = self.revcombo.get_active_text()
        if revstr is None or len(revstr) == 0:
            return None
        try:
            revnum = self.repo[revstr].rev()
        except (error.RepoError, error.LookupError):
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
        self.butable.set_sensitive(normal)
        self.stripbtn.set_property('visible', normal)
        self.closebtn.set_property('visible', normal)
        if cmd:
            self.cmd.set_property('visible', working)
        self.abortbtn.set_property('visible', working)

    def strip(self):
        def isclean():
            '''whether WD is changed'''
            wc = self.repo[None]
            return not (wc.modified() or wc.added() or wc.removed())
        revstr = self.revcombo.get_active_text()
        cmdline = ['hg', 'strip', '--verbose', revstr]

        # local changes
        if self.forceopt.get_active():
            cmdline.append('--force')
        else:
            if not isclean():
                ret = gdialog.CustomPrompt(_('Confirm Strip'),
                              _('Detected uncommitted local changes.\nDo'
                                ' you want to discard them and continue?'),
                              self, (_('&Yes (--force)'), _('&No')),
                              default=1, esc=1).run()
                if ret == 0:
                    cmdline.append('--force')
                else:
                    return

        # backup options
        if self.buopt_part.get_active():
            cmdline.append('--backup')
        elif self.buopt_none.get_active():
            cmdline.append('--nobackup')

        def cmd_done(returncode, useraborted):
            self.switch_to(MODE_NORMAL, cmd=False)
            if returncode == 0:
                if hasattr(self, 'notify_func'):
                    self.notify_func(*self.notify_args, **self.notify_kargs)
                self.cmd.set_result(_('Stripped successfully'), style='ok')
                self.after_strip()
            elif useraborted:
                self.cmd.set_result(_('Canceled stripping'), style='error')
            else:
                self.cmd.set_result(_('Failed to strip'), style='error')
        self.switch_to(MODE_WORKING)
        self.cmd.execute(cmdline, cmd_done)

    def after_strip(self):
        if self.buopt_none.get_active():
            self.response(gtk.RESPONSE_CLOSE)
        root = self.repo.root
        bakdir = os.path.join(root, r'.hg\strip-backup')
        escaped = bakdir.replace('\\', '\\\\')
        buf = self.cmd.log.buffer
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter())
        m = re.search(escaped + r'\\[0-9abcdef]{12}-backup', text, re.I)
        if m:
            def open_bakdir():
                gtklib.NativeFileManager(bakdir).run()
            # backup bundle label & button
            self.bubox = gtk.HBox()
            self.vbox.pack_start(self.bubox, True, True, 2)
            self.bulabel = gtk.Label(_('Saved at: %s') % m.group(0))
            self.bubox.pack_start(self.bulabel, True, True, 8)
            self.bulabel.set_alignment(0, 0.5)
            self.bulabel.set_selectable(True)
            self.bubtn = gtk.Button(_('Open...'))
            self.bubox.pack_start(self.bubtn, False, False, 2)
            self.bubtn.connect('clicked', lambda b: open_bakdir())
            self.bubox.show_all()

def run(ui, *pats, **opts):
    return StripDialog(None, *pats)

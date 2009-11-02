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

from mercurial import hg, ui
from mercurial.node import nullrev

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths

from tortoisehg.hgtk import csinfo, hgcmd, gtklib, gdialog

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
            gtklib.idle_add_single_call(self.destroy)
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
        reventry = self.revcombo.child
        reventry.set_width_chars(32)
        reventry.connect('activate', lambda b: self.response(gtk.RESPONSE_OK))

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

        ## preview box
        pframe = gtk.Frame()
        table.add_row(None, pframe, padding=False)
        pframe.set_shadow_type(gtk.SHADOW_IN)
        pbox = gtk.VBox()
        pframe.add(pbox)

        ### preview status box
        self.pstatbox = gtk.HBox()
        pbox.pack_start(self.pstatbox)
        pbox.pack_start(gtk.HSeparator(), False, False, 2)

        #### status label
        self.pstatlbl = createlabel()
        self.pstatbox.pack_start(self.pstatlbl, False, False, 2)

        #### show all button
        self.allbtn = gtk.Button(_('Show all')) # add later

        #### preview option
        self.compactopt = gtk.CheckButton(_('Use compact view'))
        self.pstatbox.pack_end(self.compactopt, False, False, 2)
        self.compactopt.connect('toggled', self.compact_toggled)

        ### changeset view
        rview = gtk.ScrolledWindow()
        pbox.add(rview)
        rview.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        rview.set_size_request(400, 180)
        rview.size_request()
        self.resultbox = gtk.VBox()
        rview.add_with_viewport(self.resultbox)
        rview.child.set_shadow_type(gtk.SHADOW_NONE)
        self.resultbox.set_border_width(4)

        ## options
        self.expander = gtk.Expander(_('Options:'))
        self.expander.connect('notify::expanded', self.options_expanded)

        ### force option (fixed)
        self.forceopt = gtk.CheckButton(_('Discard local changes, no backup'
                                          ' (-f/--force)'))
        table.add_row(self.expander, self.forceopt)

        # signal handlers
        self.revcombo.connect('changed', lambda c: self.preview(queue=True))
        self.allbtn.connect('clicked', lambda b: self.preview(limit=False))

        # csetinfo factory
        self.factory = csinfo.factory(repo, withupdate=True)
        self.lstyle = csinfo.labelstyle(contents=('%(revnum)s:',
                             ' %(branch)s', ' %(tags)s', ' %(summary)s'))
        self.pstyle = csinfo.panelstyle()

        # prepare to show
        self.preview()
        self.stripbtn.grab_focus()
        gtklib.idle_add_single_call(self.after_init)

    def after_init(self):
        # add 'Show all' button
        self.pstatbox.pack_start(self.allbtn, False, False, 4)

        # backup types (foldable)
        self.butable = gtklib.LayoutTable()
        self.vbox.pack_start(self.butable, True, True)
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
        self.vbox.pack_start(self.cmd, True, True, 6)

        # abort button
        self.abortbtn = self.add_button(_('Abort'), gtk.RESPONSE_CANCEL)
        self.abortbtn.hide()

    def set_notify_func(self, func, *args, **kargs):
        self.notify_func = func
        self.notify_args = args
        self.notify_kargs = kargs

    def preview(self, limit=True, queue=False, force=False):
        def clear_preview():
            self.resultbox.foreach(lambda c: c.parent.remove(c))
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
        elif not force and limit and self.currev == rev: # is already shown?
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

        LIM = 100
        compactview = self.compactopt.get_active()
        style = compactview and self.lstyle or self.pstyle
        def add_csinfo(revnum):
            info = self.factory(revnum, style)
            if info.parent:
                info.parent.remove(info)
            self.resultbox.pack_start(info, False, False, 2)
        def add_sep():
            if not compactview:
                self.resultbox.pack_start(gtk.HSeparator(), False, False)
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

    def options_expanded(self, expander, *args):
        if expander.get_expanded():
            self.butable.show_all()
        else:
            self.butable.hide()

    def compact_toggled(self, checkbtn):
        self.preview(force=True)

    def get_rev(self):
        """ Return integer revision number or None """
        revstr = self.revcombo.get_active_text()
        if revstr is None or len(revstr) == 0:
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

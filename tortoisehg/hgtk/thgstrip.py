# thgstrip.py - strip dialog for TortoiseHg
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import re
import os
import gtk

from mercurial import error

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib

from tortoisehg.hgtk import gtklib, gdialog, cslist

class StripDialog(gdialog.GDialog):
    """ Dialog to strip changesets """

    def __init__(self, rev=None, graphview=None, *pats):
        gdialog.GDialog.__init__(self, resizable=True)
        self.set_after_done(False)

        if len(pats) > 0:
            rev = pats[0]
        elif rev is None:
            rev = 'tip'
        self.initrev = str(rev)
        self.graphview = graphview

    ### Start of Overriding Section ###

    def get_title(self, reponame):
        return _('Strip - %s') % reponame

    def get_icon(self):
        return 'menudelete.ico'

    def get_defsize(self):
        return (500, 380)

    def get_body(self, vbox):
        # layout table
        self.table = table = gtklib.LayoutTable()
        vbox.pack_start(table, True, True, 2)

        ## target revision combo
        self.revcombo = gtk.combo_box_entry_new_text()
        table.add_row(_('Strip:'), self.revcombo)
        reventry = self.revcombo.child
        reventry.set_width_chars(32)

        ### fill combo list
        self.revcombo.append_text(self.initrev)
        self.revcombo.set_active(0)
        for name in hglib.getlivebranch(self.repo):
            self.revcombo.append_text(name)

        tags = list(self.repo.tags())
        tags.sort()
        tags.reverse()
        for tag in tags:
            self.revcombo.append_text(hglib.toutf(tag))

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
        self.cslist.set_activatable_enable(True)
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
        reventry.connect('activate', lambda b: self.response(gtk.RESPONSE_OK))
        self.revcombo.connect('changed', lambda c: self.preview(queue=True))
        self.cslist.connect('list-updated', self.preview_updated)
        self.cslist.connect('item-activated', self.item_activated)

        # prepare to show
        self.preview()

    def get_extras(self, vbox):
        # backup types (foldable)
        self.butable = gtklib.LayoutTable()
        vbox.pack_start(self.butable, False, False)
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

    def get_buttons(self):
        return [('strip', _('Strip'), gtk.RESPONSE_OK),
                ('close', gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)]

    def get_default_button(self):
        return 'strip'

    def get_action_map(self):
        return {gtk.RESPONSE_OK: self.strip}

    def switch_to(self, normal, working, cmd):
        self.table.set_sensitive(normal)
        self.butable.set_sensitive(normal)
        self.buttons['strip'].set_property('visible', normal)
        self.buttons['close'].set_property('visible', normal)
        if normal:
            self.buttons['close'].grab_focus()

    def command_done(self, returncode, useraborted, *args):
        if returncode == 0:
            self.cmd.set_result(_('Stripped successfully'), style='ok')
            self.after_strip()
        elif useraborted:
            self.cmd.set_result(_('Canceled stripping'), style='error')
        else:
            self.cmd.set_result(_('Failed to strip'), style='error')

    ### End of Overriding Section ###

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
        self.buttons['strip'].set_sensitive(bool(total))

    def item_activated(self, cslist, rev, *args):
        if self.graphview:
            self.graphview.set_revision_id(int(rev))

    def get_rev(self):
        """ Return integer revision number or None """
        revstr = self.revcombo.get_active_text()
        if revstr is None or len(revstr) == 0:
            return None
        if isinstance(revstr, basestring):
            revstr = hglib.fromutf(revstr)
        try:
            revnum = self.repo[revstr].rev()
        except (error.RepoError, error.LookupError):
            return None
        return revnum

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

        # start strip
        self.execute_command(cmdline)

    def after_strip(self):
        if self.buopt_none.get_active():
            self.response(gtk.RESPONSE_CLOSE)
            return
        # clear changeset list
        self.revcombo.child.set_text('')
        # show backup dir
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
            self.vbox.pack_start(self.bubox, False, False, 2)
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

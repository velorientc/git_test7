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

from tortoisehg.hgtk import hgcmd, gtklib, gdialog

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
        self.connect('response', self.dialog_response)
        self.connect('delete-event', self.delete_event)

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
            self.repo = repo
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

        # layout table
        self.table = table = gtk.Table(1, 2)
        self.vbox.pack_start(table, True, True, 2)
        # copy from 'thgconfig.py'
        def addrow(text, widget, expand=True):
            label = gtk.Label(text)
            label.set_alignment(1, 0.5)
            row = table.get_property('n-rows')
            table.set_property('n-rows', row + 1)
            table.attach(label, 0, 1, row, row + 1, gtk.FILL, 0, 4, 2)
            if not expand:
                hbox = gtk.HBox()
                hbox.pack_start(widget, False, False)
                hbox.pack_start(gtk.Label(''))
                widget = hbox
            table.attach(widget, 1, 2, row, row + 1, gtk.FILL|gtk.EXPAND, 0, 4, 2)

        # revision label & combobox
        self.revcombo = combo = gtk.combo_box_entry_new_text()
        entry = combo.child
        entry.connect('activate', lambda b: self.update(repo))
        entry.set_width_chars(38)
        addrow(_('Update to:'), self.revcombo, expand=False)

        # fill list of combo
        if rev != None:
            combo.append_text(str(rev))
        else:
            combo.append_text(repo.dirstate.branch())
        combo.set_active(0)
        for b in repo.branchtags():
            combo.append_text(b)
        tags = list(repo.tags())
        tags.sort()
        tags.reverse()
        for t in tags:
            combo.append_text(t)

        # summary of current revision
        label = gtk.Label('<current revision>')
        hb = gtk.HBox()
        hb.pack_start(label, False, False)
        addrow('Current:', hb, expand=False)
        self.current_rev_label = label

        # summary of new revision
        label = gtk.Label('<new revision>')
        hb = gtk.HBox()
        hb.pack_start(label, False, False)
        addrow('New:', hb, expand=False)
        self.new_rev_label = label

        self.update_revisions()

        # options
        self.opt_buttons = []
        group = gtk.RadioButton(None, _('Allow merge with local changes (default)'))
        addrow(_('Options:'), group, expand=False)
        self.opt_buttons.append(group)

        btn = gtk.RadioButton(group, _('Abort if local changes found (-c/--check)'))
        addrow('', btn, expand=False)
        self.opt_buttons.append(btn)
        self.opt_check = btn

        btn = gtk.RadioButton(group, _('Discard local changes, no backup (-C/--clean)'))
        addrow('', btn, expand=False)
        self.opt_buttons.append(btn)
        self.opt_clean = btn

        self.revcombo.connect('changed', lambda b: self.update_revisions())

        # prepare to show
        self.updatebtn.grab_focus()
        gobject.idle_add(self.after_init)

    def after_init(self):
        # CmdWidget
        self.cmd = hgcmd.CmdWidget()
        self.cmd.show_all()
        self.cmd.hide()
        self.vbox.pack_start(self.cmd, True, True, 6)

        # cancel button
        self.cancelbtn = gtk.Button(_('Cancel'))
        self.cancelbtn.connect('clicked', self.cancel_clicked)
        self.action_area.pack_end(self.cancelbtn)

    def dialog_response(self, dialog, response_id):
        if not self.cmd.is_alive():
            self.destroy()

    def delete_event(self, dialog, event):
        if self.cmd.is_alive():
            ret = gdialog.Confirm(_('Confirm Cancel'), [], self,
                                  _('Do you want to cancel updating?')).run()
            if ret == gtk.RESPONSE_YES:
                self.cancel_clicked(self.cancelbtn)
            return True
        self.destroy()

    def cancel_clicked(self, button):
        self.cmd.stop()
        self.cmd.show_log()
        self.switch_to(MODE_NORMAL, cmd=False)

    def switch_to(self, mode, cmd=True):
        if mode == MODE_NORMAL:
            normal = True
            self.closebtn.grab_focus()
            for btn in self.opt_buttons:
                btn.set_sensitive(True)
        elif mode == MODE_UPDATING:
            normal = False
            self.cancelbtn.grab_focus()
            for btn in self.opt_buttons:
                btn.set_sensitive(False)
        else:
            raise _('unknown mode name: %s') % mode
        updating = not normal

        self.table.set_sensitive(normal)
        self.updatebtn.set_property('visible', normal)
        self.closebtn.set_property('visible', normal)
        if cmd:
            self.cmd.set_property('visible', updating)
        self.cancelbtn.set_property('visible', updating)

    def update_revisions(self):
        def setlabel(label, ctx):
            revision = str(ctx.rev())
            hash = str(ctx)
            summary = gtklib.markup_escape_text(hglib.toutf(
                                ctx.description().split('\n')[0]))
            face = 'monospace'
            size = '9000'

            format = '<span face="%s" size="%s">%s (%s) </span>'
            t = format % (face, size, revision, hash)

            branch = ctx.branch()
            if branch != 'default':
                format = '<span color="%s" background="%s"> %s </span> '
                t += format % ('black', '#aaffaa', branch)

            tags = self.repo.nodetags(ctx.node())
            format = '<span color="%s" background="%s"> %s </span> '
            for tag in tags:
                t += format % ('black', '#ffffaa', tag)

            t += summary
            label.set_markup(t)
        
        setlabel(self.current_rev_label, self.repo['.'])
        newrev = self.revcombo.get_active_text()
        setlabel(self.new_rev_label, self.repo[newrev])

    def update(self, repo):
        self.switch_to(MODE_UPDATING)

        cmdline = ['hg', 'update', '--verbose']
        rev = self.revcombo.get_active_text()
        cmdline.append('--rev')
        cmdline.append(rev)
        if self.opt_check.get_active():
            cmdline.append('--check')
        elif self.opt_clean.get_active():
            cmdline.append('--clean')

        def cmd_done(returncode):
            self.switch_to(MODE_NORMAL, cmd=False)
            if hasattr(self, 'notify_func'):
                self.notify_func(self.notify_args)
            if returncode == 0 and not self.cmd.is_show_log():
                self.destroy()
        self.cmd.execute(cmdline, cmd_done)

    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = args

def run(ui, *pats, **opts):
    return UpdateDialog(opts.get('rev'))

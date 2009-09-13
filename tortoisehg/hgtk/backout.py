# backout.py - TortoiseHg's dialog for backing out changeset
#
# Copyright 2008 TK Soh <teekaysoh@gmail.com>
# Copyright 2008 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import gobject
import pango

from mercurial import hg, ui

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths, i18n, settings

from tortoisehg.hgtk import changesetinfo, gtklib, hgcmd, gdialog

keep = i18n.keepgettext()

class BackoutDialog(gtk.Dialog):
    """ Backout effect of a changeset """
    def __init__(self, rev=None):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self, title=_('Backout changeset - %s') % rev,
                          buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
        gtklib.set_tortoise_icon(self, 'menurevert.ico')
        gtklib.set_tortoise_keys(self)
        self.set_has_separator(False)
        self.set_default_size(600, 400)
        self.connect('response', self.dialog_response)

        # add Backout button
        backoutbutton = gtk.Button(_('Backout'))
        backoutbutton.connect('clicked', self.backout, rev)
        self.action_area.pack_end(backoutbutton)

        # persistent settings
        self.settings = settings.Settings('backout')

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except hglib.RepoError:
            gobject.idle_add(self.destroy)
            return

        # message
        self.msgset = keep._('Backed out changeset: ')
        self.msgset['id'] += rev
        self.msgset['str'] += rev

        # changeset info
        frame = gtk.Frame(_('Changeset Description'))
        frame.set_border_width(4)
        revid, desc = changesetinfo.changesetinfo(repo, rev)
        frame.add(desc)
        self.vbox.pack_start(frame, False, False, 2)

        # backout commit message
        frame = gtk.Frame(_('Backout commit message'))
        frame.set_border_width(4)
        msgvbox = gtk.VBox()
        msgvbox.set_border_width(4)
        frame.add(msgvbox)
        self.vbox.pack_start(frame, True, True, 2)

        ## message text area
        self.logview = gtk.TextView(buffer=None)
        self.logview.set_editable(True)
        self.logview.modify_font(pango.FontDescription('Monospace'))
        self.buf = self.logview.get_buffer()
        self.buf.set_text(self.msgset['str'])
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.add(self.logview)
        msgvbox.pack_start(scrolledwindow)

        ## tooltips
        self.tips = gtk.Tooltips()
        self.tips.set_tip(frame,
                _('Commit message text for new changeset that reverses the'
                '  effect of the change being backed out.'))

        ## use English backout message option
        self.eng_msg = gtk.CheckButton(_('Use English backout message'))
        self.eng_msg.connect('toggled', self.eng_msg_toggled)
        msgvbox.pack_start(self.eng_msg, False, False)

        # prepare to show
        self.load_settings()
        backoutbutton.grab_focus()

    def load_settings(self):
        checked = self.settings.get_value('english', False, True)
        self.eng_msg.set_active(checked)

    def store_settings(self):
        checked = self.eng_msg.get_active()
        self.settings.set_value('english', checked)
        self.settings.write()

    def dialog_response(self, dialog, response_id):
        self.store_settings()
        if response_id == gtk.RESPONSE_CLOSE \
                or response_id == gtk.RESPONSE_DELETE_EVENT:
            self.destroy()

    def eng_msg_toggled(self, checkbutton):
        start, end = self.buf.get_bounds()
        msg = self.buf.get_text(start, end)
        state = checkbutton.get_active()
        origmsg = (state and self.msgset['str'] or self.msgset['id'])
        if msg != origmsg:
            res = gdialog.Confirm(_('Confirm Discard Message'),
                    [], self, _('Discard current backout message?')).run()
            if res != gtk.RESPONSE_YES:
                checkbutton.handler_block_by_func(self.eng_msg_toggled)
                checkbutton.set_active(not state)
                checkbutton.handler_unblock_by_func(self.eng_msg_toggled)
                return
        newmsg = (state and self.msgset['id'] or self.msgset['str'])
        self.buf.set_text(newmsg)

    def backout(self, button, revstr):
        start, end = self.buf.get_bounds()
        msg = self.buf.get_text(start, end)
        cmdline = ['hg', 'backout', '--rev', revstr, '--message', hglib.fromutf(msg)]
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        if dlg.returncode == 0:
            self.destroy()

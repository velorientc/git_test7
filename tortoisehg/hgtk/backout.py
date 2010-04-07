# backout.py - TortoiseHg's dialog for backing out changeset
#
# Copyright 2008 TK Soh <teekaysoh@gmail.com>
# Copyright 2008 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import pango

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, i18n

from tortoisehg.hgtk import csinfo, gdialog, gtklib

keep = i18n.keepgettext()

class BackoutDialog(gdialog.GDialog):
    """ Backout effect of a changeset """
    def __init__(self, rev=None):
        gdialog.GDialog.__init__(self, resizable=True)
        self.rev = rev

    ### Start of Overriding Section ###

    def get_title(self, reponame):
        return _('Backout changeset - %s') % self.rev

    def get_icon(self):
        return 'menurevert.ico'

    def get_defsize(self):
        return (600, 400)

    def get_setting_name(self):
        return 'backout'

    def get_body(self, vbox):
        # message
        self.msgset = keep._('Backed out changeset: ')
        self.msgset['id'] += self.rev
        self.msgset['str'] += self.rev

        # changeset info
        style = csinfo.panelstyle(label=_('Changeset Description'),
                                  margin=4, padding=2)
        self.csetframe = csinfo.create(self.repo, self.rev, style, withupdate=True)
        vbox.pack_start(self.csetframe, False, False, 2)

        # backout commit message
        frame = gtk.Frame(_('Backout commit message'))
        frame.set_border_width(4)
        msgvbox = gtk.VBox()
        msgvbox.set_border_width(4)
        frame.add(msgvbox)
        vbox.pack_start(frame, True, True, 2)
        self.cmsgframe = frame

        ## message text area
        self.logview = gtk.TextView(buffer=None)
        self.logview.set_editable(True)
        fontcomment = hglib.getfontconfig()['fontcomment']
        self.logview.modify_font(pango.FontDescription(fontcomment))
        self.buf = self.logview.get_buffer()
        self.buf.set_text(self.msgset['str'])
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.add(self.logview)
        msgvbox.pack_start(scrolledwindow)

        ## tooltips
        self.tips = gtklib.Tooltips()
        self.tips.set_tip(frame,
                _('Commit message text for new changeset that reverses the'
                '  effect of the change being backed out.'))

        hbox = gtk.HBox()

        ## use English backout message option
        self.eng_msg = gtk.CheckButton(_('Use English backout message'))
        self.eng_msg.connect('toggled', self.eng_msg_toggled)
        hbox.pack_start(self.eng_msg, False, False)

        ## merge after backout
        self.merge_button = gtk.CheckButton(
                _('Merge with old dirstate parent after backout'))
        hbox.pack_start(self.merge_button, False, False, 4)
        msgvbox.pack_start(hbox, False, False)

    def get_buttons(self):
        return [('backout', _('Backout'), gtk.RESPONSE_OK),
                ('close', gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)]

    def get_default_button(self):
        return 'backout'

    def get_action_map(self):
        return {gtk.RESPONSE_OK: self.backout}

    def switch_to(self, normal, *args):
        self.csetframe.set_sensitive(normal)
        self.cmsgframe.set_sensitive(normal)
        self.buttons['backout'].set_property('visible', normal)
        self.buttons['close'].set_property('visible', normal)
        if normal:
            self.buttons['close'].grab_focus()

    def command_done(self, returncode, useraborted, *args):
        if returncode == 0:
            self.cmd.set_result(_('Backed out successfully'), style='ok')
        elif useraborted:
            self.cmd.set_result(_('Canceled backout'), style='error')
        else:
            self.cmd.set_result(_('Failed to backout'), style='error')

    def load_settings(self):
        checked = self.settings.get_value('english', False, True)
        self.eng_msg.set_active(checked)
        checked = self.settings.get_value('merge', True, True)
        self.merge_button.set_active(checked)

    def store_settings(self):
        checked = self.eng_msg.get_active()
        self.settings.set_value('english', checked)
        checked = self.merge_button.get_active()
        self.settings.set_value('merge', checked)
        self.settings.write()

    ### End of Overriding Section ###

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

    def backout(self):
        # prepare command line
        start, end = self.buf.get_bounds()
        msg = self.buf.get_text(start, end)
        cmdline = ['hg', 'backout', '--rev', self.rev]
        if self.merge_button.get_active():
            cmdline += ['--merge']
        cmdline += ['--message', hglib.fromutf(msg)]

        # start backing out
        self.execute_command(cmdline)

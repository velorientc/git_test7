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

from tortoisehg.hgtk import csinfo, gtklib, hgcmd, gdialog

keep = i18n.keepgettext()

MODE_NORMAL  = 'normal'
MODE_WORKING = 'working'

class BackoutDialog(gtk.Dialog):
    """ Backout effect of a changeset """
    def __init__(self, rev=None):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self, title=_('Backout changeset - %s') % rev)
        gtklib.set_tortoise_icon(self, 'menurevert.ico')
        gtklib.set_tortoise_keys(self)
        self.set_has_separator(False)
        self.set_default_size(600, 400)
        self.connect('response', self.dialog_response)
        self.rev = rev

        # add Backout button
        self.backoutbtn = self.add_button(_('Backout'), gtk.RESPONSE_OK)
        self.closebtn = self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)

        # persistent settings
        self.settings = settings.Settings('backout')

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except hglib.RepoError:
            gtklib.idle_add_single_call(self.destroy)
            return

        # message
        self.msgset = keep._('Backed out changeset: ')
        self.msgset['id'] += rev
        self.msgset['str'] += rev

        # changeset info
        style = csinfo.panelstyle(label=_('Changeset Description'),
                                  margin=4, padding=2)
        self.csetframe = csinfo.create(repo, rev, style, withupdate=True)
        self.vbox.pack_start(self.csetframe, False, False, 2)

        # backout commit message
        frame = gtk.Frame(_('Backout commit message'))
        frame.set_border_width(4)
        msgvbox = gtk.VBox()
        msgvbox.set_border_width(4)
        frame.add(msgvbox)
        self.vbox.pack_start(frame, True, True, 2)
        self.cmsgframe = frame

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

        # prepare to show
        self.load_settings()
        self.backoutbtn.grab_focus()
        gtklib.idle_add_single_call(self.after_init)

    def after_init(self):
        # CmdWidget
        self.cmd = hgcmd.CmdWidget()
        self.cmd.show_all()
        self.cmd.hide()
        self.vbox.pack_start(self.cmd, False, False, 6)

        # abort button
        self.abortbtn = self.add_button(_('Abort'), gtk.RESPONSE_CANCEL)
        self.abortbtn.hide()

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

    def dialog_response(self, dialog, response_id):
        def abort():
            self.cmd.stop()
            self.cmd.show_log()
            self.switch_to(MODE_NORMAL, cmd=False)
        # Backout button
        if response_id == gtk.RESPONSE_OK:
            self.backout()
        # Close button or dialog closing by the user
        elif response_id in (gtk.RESPONSE_CLOSE, gtk.RESPONSE_DELETE_EVENT):
            if self.cmd.is_alive():
                ret = gdialog.Confirm(_('Confirm Abort'), [], self,
                                      _('Do you want to abort?')).run()
                if ret == gtk.RESPONSE_YES:
                    abort()
            else:
                self.store_settings()
                self.destroy()
                return # close dialog
        # Abort button
        elif response_id == gtk.RESPONSE_CANCEL:
            abort()
        else:
            raise _('unexpected response id: %s') % response_id

        self.run() # don't close dialog

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

        self.csetframe.set_sensitive(normal)
        self.cmsgframe.set_sensitive(normal)
        self.backoutbtn.set_property('visible', normal)
        self.closebtn.set_property('visible', normal)
        if cmd:
            self.cmd.set_property('visible', working)
        self.abortbtn.set_property('visible', working)

    def backout(self):
        start, end = self.buf.get_bounds()
        msg = self.buf.get_text(start, end)
        cmdline = ['hg', 'backout', '--rev', self.rev]
        if self.merge_button.get_active():
            cmdline += ['--merge']
        cmdline += ['--message', hglib.fromutf(msg)]

        def cmd_done(returncode, useraborted):
            self.switch_to(MODE_NORMAL, cmd=False)
            if returncode == 0:
                if not self.cmd.is_show_log():
                    self.response(gtk.RESPONSE_CLOSE)
                self.cmd.set_result(_('Backed out successfully'), style='ok')
            elif useraborted:
                self.cmd.set_result(_('Canceled backout'), style='error')
            else:
                self.cmd.set_result(_('Failed to backout'), style='error')
        self.switch_to(MODE_WORKING)
        self.cmd.execute(cmdline, cmd_done)

# gorev.py - TortoiseHg's dialog for selecting a revision
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject

from mercurial import error

from tortoisehg.util.i18n import _
from tortoisehg.hgtk import gtklib, gdialog


class GotoRevDialog(gtk.Dialog):
    'Dialog for selecting a revision'
    def __init__(self, gotofunc):
        super(GotoRevDialog, self).__init__(flags=gtk.DIALOG_MODAL)
        gtklib.set_tortoise_icon(self, 'menulog.ico')
        gtklib.set_tortoise_keys(self)
        self.set_has_separator(False)

        self._btn_goto = gtk.Button(_('Select'))
        self._btn_goto.connect('clicked', self._btn_goto_clicked)
        self.action_area.pack_end(self._btn_goto)

        self.set_title(_('Select Revision'))

        self.gotofunc = gotofunc

        self.tips = gtk.Tooltips()

        hbox = gtk.HBox()
        self.revEntry = gtk.Entry()
        self.revEntry.connect('activate', self._btn_goto_clicked)
        hbox.pack_start(self.revEntry, True, True, 4)
        eventbox = gtk.EventBox()
        eventbox.add(hbox)
        self.tips.set_tip(
            eventbox, _('revision number, changeset ID, branch or tag'))
        self.vbox.pack_start(eventbox, False, False, 4)

        self.revEntry.grab_focus()

        self.show_all()

    def _btn_goto_clicked(self, button, data=None):
        try:
            revision = self.revEntry.get_text()
            if self.gotofunc:
                self.gotofunc(revision)
            self.revEntry.set_text('')
            self.hide()
        except error.LookupError, e:
            gdialog.Prompt(_('Ambiguous Revision'), str(e), self).run()
            self.revEntry.grab_focus()
            return
        except error.RepoError, e:
            gdialog.Prompt(_('Invalid Revision'), str(e), self).run()
            self.revEntry.grab_focus()
            return

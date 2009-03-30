#
# bugreport.py - Bug report dialog for TortoiseHg
#
# Copyright (C) 2009 Steve Borho <steve@borho.org>
#

import pygtk
import gtk
import pango

from mercurial.i18n import _
from hglib import toutf, fromutf, rootpath, diffexpand
from gdialog import *
from dialog import entry_dialog

class BugReport(GDialog):
    """GTK+ based dialog for displaying traceback info to the user in a
    cut-paste friendly manner.  And include a number of useful bit of
    information like version numbers, etc.
    """

    def get_title(self):
        return _('TortoiseHg Bug Report')

    def get_icon(self):
        return 'menudelete.ico'

    def get_body(self):
        textview = gtk.TextView()
        textview.set_wrap_mode(gtk.WRAP_NONE)
        textview.set_editable(False)
        textview.modify_font(pango.FontDescription(self.fontlist))
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(textview)
        vbox = gtk.VBox()
        vbox.pack_start(scroller, True, True, 2)
        hbbox = gtk.HButtonBox()
        hbbox.set_layout(gtk.BUTTONBOX_END)
        vbox.pack_start(hbbox, False, False, 2)
        close = gtk.Button(_('Close'))
        close.connect('clicked', gtk.main_quit)
        hbbox.add(close)

        from about import hgversion
        import shlib
        text = _('\n\nPlease report this bug to'
                ' http://bitbucket.org/tortoisehg/stable/issues\n')
        text += _('Mercurial version (%s).  TortoiseHg version (%s)\n') % (
                hgversion, shlib.version())
        text += _('Command: %s\n') % (self.opts['cmd'])
        text += self.opts['error']
        textview.get_buffer().set_text(text)
        return vbox


def run(**opts):
    dialog = BugReport(ui.ui(), None, None, None, opts, True)
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    dialog.display()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    opts = {}
    opts['cmd'] = 'command'
    opts['error'] = 'test error'
    run(**opts)

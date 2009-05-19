#
# bugreport.py - Bug report dialog for TortoiseHg
#
# Copyright (C) 2009 Steve Borho <steve@borho.org>
#

import os
import gtk
import pango

from mercurial import extensions
from thgutil.i18n import _
from thgutil import shlib
from hggtk.gdialog import GDialog
from hggtk.about import hgversion

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
        scroller.set_shadow_type(gtk.SHADOW_IN)
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(textview)
        scroller.set_border_width(5)
        vbox = gtk.VBox()
        vbox.pack_start(scroller, True, True, 2)
        hbbox = gtk.HButtonBox()
        hbbox.set_layout(gtk.BUTTONBOX_END)
        vbox.pack_start(hbbox, False, False, 2)
        close = gtk.Button(_('Close'))
        close.connect('clicked', gtk.main_quit)
        hbbox.add(close)

        text = _('\n** Please report this bug to'
                ' tortoisehg-discuss@lists.sourceforge.net or'
                ' http://bitbucket.org/tortoisehg/stable/issues\n')
        text += _('** Mercurial version (%s).  TortoiseHg version (%s)\n') % (
                hgversion, shlib.version())
        text += _('** Command: %s\n') % (self.opts['cmd'])
        text += _('** CWD: %s\n') % os.getcwd()
        extlist = [x[0] for x in extensions.extensions()]
        text += _('** Extensions loaded: %s\n') % ', '.join(extlist)
        text += self.opts['error']
        textview.get_buffer().set_text(text)
        return vbox

def run(_ui, *pats, **opts):
    return BugReport(_ui, None, None, None, opts)

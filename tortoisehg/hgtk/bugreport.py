# bugreport.py - Bug report dialog for TortoiseHg
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import pango

from mercurial import extensions
from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, version
from tortoisehg.hgtk import gdialog, gtklib

class BugReport(gdialog.GDialog):
    """GTK+ based dialog for displaying traceback info to the user in a
    cut-paste friendly manner.  And include a number of useful bit of
    information like version numbers, etc.
    """

    __error_text__ = None

    def get_title(self):
        return _('TortoiseHg Bug Report')

    def get_icon(self):
        return 'menudelete.ico'

    def get_body(self):
        textview = gtk.TextView()
        textview.set_wrap_mode(gtk.WRAP_NONE)
        textview.set_editable(False)
        textview.modify_font(pango.FontDescription(self.fontdiff))
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
        save = gtk.Button(_('Save as..'))
        save.connect('clicked', self.save_report_clicked)
        hbbox.add(save)
        close = gtk.Button(_('Close'))
        close.connect('clicked', gtk.main_quit)
        hbbox.add(close)
        textview.get_buffer().set_text(self.get_error_text())
        return vbox

    def get_error_text(self):
        if self.__error_text__ == None:
            text = '{{{\n#!python\n' # Wrap in Bitbucket wiki preformat markers
            text += _('** Please report this bug to'
                    ' http://bitbucket.org/tortoisehg/stable/issues or'
                    ' tortoisehg-discuss@lists.sourceforge.net\n')
            text += '** Mercurial version (%s).  TortoiseHg version (%s)\n' % (
                    hglib.hgversion, version.version())
            text += '** Command: %s\n' % (self.opts['cmd'])
            text += '** CWD: %s\n' % os.getcwd()
            extlist = [x[0] for x in extensions.extensions()]
            text += '** Extensions loaded: %s\n' % ', '.join(extlist)
            text += self.opts['error']
            text += '\n}}}'
            self.__error_text__ = text
        return self.__error_text__ 

    def save_report_clicked(self, button):
        result = gtklib.NativeSaveFileDialogWrapper(
                        title=_('Save error report to')).run()

        if result:
            fd = file(result, 'w')
            fd.write(self.get_error_text())
            fd.close()

def run(_ui, *pats, **opts):
    return BugReport(_ui, None, None, None, opts)

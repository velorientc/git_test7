# about.py - TortoiseHg About dialog
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import sys
import gtk

from tortoisehg.util.i18n import _
from tortoisehg.util import version, paths, hglib, shlib

from tortoisehg.hgtk import gtklib, hgtk

def url_handler(dialog, link, user_data):
    shlib.browse_url(link)

gtk.about_dialog_set_url_hook(url_handler, None)

def make_version(tuple):
    vers = ".".join([str(x) for x in tuple])
    return vers

class AboutDialog(gtk.AboutDialog):
    def __init__(self):
        super(AboutDialog, self).__init__()
        gtklib.set_tortoise_keys(self)

        lib_versions = ', '.join([
                "Mercurial-%s" % hglib.hgversion,
                "Python-%s" % make_version(sys.version_info[0:3]),
                "PyGTK-%s" % make_version(gtk.pygtk_version),
                "GTK-%s" % make_version(gtk.gtk_version),
            ])

        comment = _("Several icons are courtesy of the TortoiseSVN project")

        self.set_website("http://tortoisehg.org")
        self.set_name("TortoiseHg")
        self.set_version(_("(version %s)") % version.version())
        if hasattr(self, 'set_wrap_license'):
            self.set_wrap_license(False)
        self.set_copyright(_("Copyright 2009 Steve Borho and others"))

        thg_logo = paths.get_tortoise_icon('thg_logo_92x50.png')
        thg_icon = paths.get_tortoise_icon('thg_logo.ico')
        try:
            license_file = paths.get_license_path()
            if license_file.endswith('.gz'):
                import gzip
                lic = gzip.open(license_file, 'rb').read()
            else:
                lic = open(license_file, 'rb').read()
            self.set_license(lic)
        except (ImportError, IOError):
            license = hgtk.shortlicense.splitlines()[1:]
            self.set_license('\n'.join(license))

        self.set_comments(_("with %s") % lib_versions + "\n\n" + comment)
        if thg_logo:
            self.set_logo(gtk.gdk.pixbuf_new_from_file(thg_logo))
        if thg_icon:
            self.set_icon_from_file(thg_icon)
        self.connect('response', self.response)

    def response(self, widget, respid):
        self.destroy()

def run(_ui, *pats, **opts):
    return AboutDialog()

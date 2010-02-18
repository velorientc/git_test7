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
import urllib2

from tortoisehg.util.i18n import _
from tortoisehg.util import version, paths, hglib, shlib

from tortoisehg.hgtk import gtklib, hgtk

_verurl = 'http://tortoisehg.bitbucket.org/curversion.txt'

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

        newver = (0,0,0)
        upgradeurl = 'http://tortoisehg.org'
        try:
            f = urllib2.urlopen(_verurl).read().splitlines()
            newver = tuple([int(p) for p in f[0].split('.')])
            upgradeurl = f[1] # generic download URL
            platform = sys.platform
            if platform == 'win32':
                from win32process import IsWow64Process as IsX64
                platform = IsX64() and 'x64' or 'x86'
            # linux2 for Linux, darwin for OSX
            for line in f[2:]:
                p, url = line.split(':')
                if platform == p:
                    upgradeurl = url.strip()
                    break
        except:
            pass
        ver = version.version()
        if '+' in ver:
            ver = ver[:ver.index('+')]
        try:
            curver = tuple([int(p) for p in ver.split('.')])
        except:
            curver = (0,0,0)
        if newver > curver:
            comment = _('A new version of TortoiseHg is ready for download!')
            self.set_website(upgradeurl)
        else:
            self.set_website('http://tortoisehg.org')

        self.set_name("TortoiseHg")
        self.set_version(_("(version %s)") % version.version())
        if hasattr(self, 'set_wrap_license'):
            self.set_wrap_license(False)
        self.set_copyright(_("Copyright 2008-2010 Steve Borho and others"))

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

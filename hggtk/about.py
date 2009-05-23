#
# TortoiseHg About dialog
#
# Copyright (C) 2007-9 TK Soh <teekaysoh@gmail.com>
#

import os
import sys
import gtk
import threading

from thgutil.i18n import _
from thgutil import version, paths, hglib

from hggtk import gtklib, hgtk

def browse_url(url):
    def start_browser():
        if os.name == 'nt':
            import win32api, win32con
            win32api.ShellExecute(0, "open", url, None, "",
                win32con.SW_SHOW)
        else:
            import gconf
            client = gconf.client_get_default()
            browser = client.get_string(
                    '/desktop/gnome/url-handlers/http/command') + '&'
            os.system(browser % url)
    threading.Thread(target=start_browser).start()

def url_handler(dialog, link, user_data):
    browse_url(link)

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

        self.set_website("http://bitbucket.org/tortoisehg/stable/")
        self.set_name("TortoiseHg")
        self.set_version("(version %s)" % version.version())
        if hasattr(self, 'set_wrap_license'):
            self.set_wrap_license(True)
        self.set_copyright("Copyright 2009 TK Soh and others")

        thg_logo = paths.get_tortoise_icon('thg_logo_92x50.png')
        thg_icon = paths.get_tortoise_icon('thg_logo.ico')
        try:
            license_file = paths.get_license_path()
            self.set_license(file(license_file).read())
        except IOError:
            license = hgtk.shortlicense.splitlines()[1:]
            self.set_license('\n'.join(license))

        self.set_comments("with " + lib_versions + "\n\n" + comment)
        self.set_logo(gtk.gdk.pixbuf_new_from_file(thg_logo))
        self.set_icon_from_file(thg_icon)
        self.connect('response', self.response)

    def response(self, widget, respid):
        self.destroy()

def run(_ui, *pats, **opts):
    return AboutDialog()

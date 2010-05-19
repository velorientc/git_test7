# about.py - About dialog for TortoiseHg
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
# Copyright 2010 Johan Samyn <johan.samyn@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.
"""
TortoiseHg About dialog - PyQt4 version
"""

import os, sys, urllib2

from PyQt4.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, Qt
from PyQt4.QtGui import QIcon, QPixmap, QDialog

from tortoisehg.hgqt.i18n import _
from tortoisehg.util import version, hglib, shlib, paths

def make_version(tuple):
    vers = ".".join([str(x) for x in tuple])
    return vers

try:
    from tortoisehg.hgqt.about_ui import Ui_AboutDialog
except ImportError:
    from PyQt4 import uic
    Ui_AboutDialog = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'about.ui'))[0]

class AboutDialog(QDialog):
    """Dialog for showing info about TortoiseHg"""

    _upgradeurl = ''

    def __init__(self, parent=None):
        super(AboutDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._qui = Ui_AboutDialog()
        self._qui.setupUi(self)

        iconfile = paths.get_tortoise_icon('thg_logo.ico')
        icon = QIcon()
        icon.addPixmap(QPixmap(iconfile), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)
        self.setWindowTitle(_('About TortoiseHg'))

        thglogofile = paths.get_tortoise_icon('thg_logo_92x50.png')
        self._qui.logo_label.setPixmap(QPixmap(thglogofile))

        thgv = (_('version %s') % version.version())
        libv = (_('with Mercurial-%s, Python-%s, PyQt-%s, Qt-%s') % \
              (hglib.hgversion, make_version(sys.version_info[0:3]),
              PYQT_VERSION_STR, QT_VERSION_STR))
        nvl = hglib.fromunicode(self._qui.name_version_libs_label.text())
        nvl = nvl.replace('*version_string*', thgv)
        nvl = nvl.replace('*libs_string*', libv)
        self._qui.name_version_libs_label.setText(nvl)

        self._qui.copyright_label.setText(_('Copyright 2008-2010 Steve Borho and others'))
        self._qui.courtesy_label.setText(
              _('Several icons are courtesy of the TortoiseSVN project'))

        _verurl = 'http://tortoisehg.bitbucket.org/curversion.txt'
        newver = (0,0,0)
        self._upgradeurl = 'http://tortoisehg.org'
        try:
            f = urllib2.urlopen(_verurl).read().splitlines()
            newver = tuple([int(p) for p in f[0].split('.')])
            self._upgradeurl = f[1] # generic download URL
            platform = sys.platform
            if platform == 'win32':
                from win32process import IsWow64Process as IsX64
                platform = IsX64() and 'x64' or 'x86'
            # linux2 for Linux, darwin for OSX
            for line in f[2:]:
                p, url = line.split(':')
                if platform == p:
                    self._upgradeurl = url.strip()
                    break
        except:
            pass
        try:
            curver = tuple([int(p) for p in thgv.split('.')])
        except:
            curver = (0,0,0)
        if newver > curver:
            self._qui.download_label.setText(
                  _('A new version of TortoiseHg is ready for download!'))
        else:
            self._qui.download_label.setText('')
        dlurl = hglib.fromunicode(self._qui.download_url_label.text())
        dlurl = dlurl.replace('http://thg-download-url', self._upgradeurl)
        self._qui.download_url_label.setText(dlurl)
        
        self._qui.license_button.setText(_('&License'))
        self._qui.close_button.setText(_('&Close'))

    def actionVisitDownloadSite(self):
        shlib.browse_url(self._upgradeurl)

    def actionShowLicense(self):
        from tortoisehg.hgqt import license
        ld = license.LicenseDialog(self)
        ld.show()


def run(ui, *pats, **opts):
    return AboutDialog()

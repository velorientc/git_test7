# license.py - license dialog for TortoiseHg
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
# Copyright 2010 Johan Samyn <johan.samyn@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.
"""
TortoiseHg License dialog - PyQt4 version
"""

from PyQt4.QtCore import Qt
from PyQt4.QtGui import QDialog, QIcon, QPixmap

from tortoisehg.hgqt.i18n import _
from tortoisehg.util import paths

try:
    from tortoisehg.hgqt.license_ui import Ui_LicenseDialog
except ImportError:
    from PyQt4 import uic
    Ui_LicenseDialog = uic.loadUiType(os.path.join(os.path.dirname(__file__),
																						'license.ui'))[0]

class LicenseDialog(QDialog):
    """Dialog for showing the TortoiseHg license"""
    def __init__(self, parent=None):
        super(LicenseDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._qui = Ui_LicenseDialog()
        self._qui.setupUi(self)
        iconfile = paths.get_tortoise_icon('thg_logo.ico')
        icon = QIcon()
        icon.addPixmap(QPixmap(iconfile), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)
        self.setWindowTitle(_('License'))
        try:
            lic = open(paths.get_license_path(), 'rb').read()
            self._qui.licenseText.setPlainText(lic)
        except (IOError):
            pass

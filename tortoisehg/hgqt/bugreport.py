# bugreport.py - Report Python tracebacks to the user
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os
import sys

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import SIGNAL, SLOT, QSettings, Qt

from mercurial import extensions
from tortoisehg.util import hglib, version
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib

class BugReport(QtGui.QDialog):

    def __init__(self, opts, parent=None):
        super(BugReport, self).__init__(parent)

        self.text = self.gettext(opts)

        layout = QtGui.QVBoxLayout()

        tb = QtGui.QTextBrowser()
        tb.document().setDefaultStyleSheet(qtlib.thgstylesheet)
        msg = hglib.tounicode(self.text)
        msg = QtCore.Qt.escape(msg)
        tb.setHtml('<span>' + msg + '</span>')
        tb.setWordWrapMode(QtGui.QTextOption.NoWrap)
        layout.addWidget(tb)

        # dialog buttons
        BB = QtGui.QDialogButtonBox
        bb = QtGui.QDialogButtonBox(BB.Ok|BB.Save)
        self.connect(bb, SIGNAL("accepted()"), self, SLOT("accept()"))
        self.connect(bb.button(BB.Save), SIGNAL("clicked()"), self.save)
        bb.button(BB.Ok).setDefault(True)
        layout.addWidget(bb)

        self.setLayout(layout)
        self.setWindowTitle(_('TortoiseHg Bug Report'))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.resize(650, 400)
        self._readsettings()

    def gettext(self, opts):
        text = '{{{\n#!python\n' # Wrap in Bitbucket wiki preformat markers
        text += _('** Please report this bug to'
                ' http://bitbucket.org/tortoisehg/stable/issues\n')
        text += '** Mercurial version (%s).  TortoiseHg version (%s)\n' % (
                hglib.hgversion, version.version())
        text += '** Command: %s\n' % (opts.get('cmd', 'N/A'))
        text += '** CWD: %s\n' % os.getcwd()
        extlist = [x[0] for x in extensions.extensions()]
        text += '** Extensions loaded: %s\n' % ', '.join(extlist)
        text += '** Python version: %s\n' % sys.version.replace('\n', '')
        if os.name == 'nt':
            text += self.getarch()
        text += opts.get('error', 'N/A')
        text += '\n}}}'
        return text

    def getarch(self):
        text = '** Windows version: %s\n' % str(sys.getwindowsversion())
        arch = 'unknown (failed to import win32api)'
        try:
            import win32api
            arch = 'unknown'
            archval = win32api.GetNativeSystemInfo()[0]
            if archval == 9:
                arch = 'x64'
            elif archval == 0:
                arch = 'x86'
        except (ImportError, AttributeError):
            pass
        text += '** Processor architecture: %s\n' % arch
        return text

    def save(self):
        try:
            fd = QtGui.QFileDialog(self)
            fname = fd.getSaveFileName(self,
                        _('Save error report to'),
                        os.path.join(os.getcwd(), 'bugreport.txt'),
                        _('Text files (*.txt)'))
            if fname:
                open(fname, 'wb').write(self.text)
        except (EnvironmentError), e:
            QMessageBox.critical(self, _('Error writing file'), str(e))

    def accept(self):
        self._writesettings()
        super(BugReport, self).accept()

    def reject(self):
        self._writesettings()
        super(BugReport, self).reject()

    def _readsettings(self):
        s = QSettings()
        self.restoreGeometry(s.value('bugreport/geom').toByteArray())

    def _writesettings(self):
        s = QSettings()
        s.setValue('bugreport/geom', self.saveGeometry())

def run(ui, *pats, **opts):
    return BugReport(opts)

if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    form = BugReport({'cmd':'cmd', 'error':'error'})
    form.show()
    app.exec_()

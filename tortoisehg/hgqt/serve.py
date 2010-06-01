# serve.py - TortoiseHg dialog to start web server
#
# Copyright 2010 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import sys, os, httplib, socket
from PyQt4.QtCore import Qt, pyqtSlot
from PyQt4.QtGui import QDialog, QSystemTrayIcon
from mercurial import extensions, hgweb, util
from tortoisehg.hgqt import cmdui, qtlib
from tortoisehg.hgqt.i18n import _

try:
    from tortoisehg.hgqt.ui_serve import Ui_ServeDialog
except ImportError:
    from PyQt4 import uic
    Ui_ServeDialog = uic.loadUiType(os.path.join(os.path.dirname(__file__),
                                                 'serve.ui'))[0]

class ServeDialog(QDialog):
    """Dialog for serving repositories via web"""
    def __init__(self, parent=None):
        super(ServeDialog, self).__init__(parent)
        self.setWindowFlags((self.windowFlags() | Qt.WindowMinimizeButtonHint)
                            & ~Qt.WindowContextHelpButtonHint)
        # TODO: choose appropriate icon
        self.setWindowIcon(qtlib.geticon('proxy'))

        self._qui = Ui_ServeDialog()
        self._qui.setupUi(self)

        self._initcmd()
        self._initactions()
        # TODO: webconf tab (multi-repo support)
        self._updateform()

    def _initcmd(self):
        self._cmd = cmdui.Widget()
        # TODO: forget old logs?
        self._log_edit = self._cmd.core.output_text
        self._qui.details_tabs.addTab(self._log_edit, _('Log'))
        self._cmd.hide()
        self._cmd.commandStarted.connect(self._updateform)
        self._cmd.commandFinished.connect(self._updateform)

    def _initactions(self):
        self._qui.start_button.clicked.connect(self.start)
        self._qui.stop_button.clicked.connect(self.stop)

    @pyqtSlot()
    def _updateform(self):
        """update form availability and status text"""
        self._updatestatus()
        self._qui.start_button.setEnabled(not self.isstarted())
        self._qui.stop_button.setEnabled(self.isstarted())
        self._qui.settings_button.setEnabled(not self.isstarted())
        self._qui.port_edit.setEnabled(not self.isstarted())

    def _updatestatus(self):
        def statustext():
            if self.isstarted():
                # TODO: escape special chars
                link = '<a href="%s">%s</a>' % (self.rooturl, self.rooturl)
                return _('Running at %s') % link
            else:
                return _('Stopped')

        self._qui.status_edit.setText(statustext())

    @pyqtSlot()
    def start(self):
        """Start web server"""
        if self.isstarted():
            return

        _setupwrapper()
        self._cmd.run(['serve', '--port', str(self.port)])

    @pyqtSlot()
    def stop(self):
        """Stop web server"""
        if not self.isstarted():
            return

        self._cmd.cancel()
        self._fake_request()
        # TODO: sometimes it doesn't release the port

    def _fake_request(self):
        """Send fake request for server to run python code"""
        TIMEOUT = 0.5  # [sec]
        conn = httplib.HTTPConnection('localhost:%d' % self.port)
        origtimeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(TIMEOUT)
        try:
            conn.request('GET', '/')
            res = conn.getresponse()
            res.read()
        except (socket.error, httplib.HTTPException):
            pass
        finally:
            socket.setdefaulttimeout(origtimeout)
            conn.close()

    def reject(self):
        self.stop()
        super(ServeDialog, self).reject()

    def isstarted(self):
        """Is the web server running?"""
        return self._cmd.core.is_running()

    @property
    def rooturl(self):
        """Returns the root URL of the web server"""
        # TODO: scheme, hostname ?
        return 'http://localhost:%d' % self.port

    @property
    def port(self):
        """Port number of the web server"""
        return int(self._qui.port_edit.value())

    def keyPressEvent(self, event):
        if self.isstarted() and event.key() == Qt.Key_Escape:
            self.stop()
            return

        return super(ServeDialog, self).keyPressEvent(event)

    def closeEvent(self, event):
        if self.isstarted():
            self._minimizetotray()
            event.ignore()
            return

        return super(ServeDialog, self).closeEvent(event)

    @util.propertycache
    def _trayicon(self):
        icon = QSystemTrayIcon(self.windowIcon(), parent=self)
        icon.activated.connect(self._restorefromtray)
        icon.setToolTip(self.windowTitle())
        # TODO: context menu
        return icon

    # TODO: minimize to tray by minimize button

    @pyqtSlot()
    def _minimizetotray(self):
        self._trayicon.show()
        self.hide()

    @pyqtSlot()
    def _restorefromtray(self):
        self._trayicon.hide()
        self.show()

    @pyqtSlot()
    def on_settings_button_clicked(self):
        from tortoisehg.hgqt import settings
        settings.SettingsDialog(parent=self, focus='web.name').exec_()

def _create_server(orig, ui, app):
    """wrapper for hgweb.server.create_server to be interruptable"""
    server = orig(ui, app)
    server.accesslog = ui
    server.errorlog = ui  # TODO: ui.warn
    server._serving = False

    def serve_forever(orig):
        server._serving = True
        while server._serving:
            server.handle_request()

    def handle_error(orig, request, client_address):
        type = sys.exc_info()[0]
        if issubclass(type, KeyboardInterrupt):
            server._serving = False
        else:
            orig(request, client_address)

    extensions.wrapfunction(server, 'serve_forever', serve_forever)
    extensions.wrapfunction(server, 'handle_error', handle_error)
    return server

_setupwrapper_done = False
def _setupwrapper():
    """Wrap hgweb.server.create_server to get along with thg"""
    global _setupwrapper_done
    if not _setupwrapper_done:
        extensions.wrapfunction(hgweb.server, 'create_server',
                                _create_server)
        _setupwrapper_done = True

def run(ui, *pats, **opts):
    # TODO: handle --web-conf
    dlg = ServeDialog()
    dlg.start()
    return dlg

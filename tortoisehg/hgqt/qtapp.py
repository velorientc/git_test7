# qtapp.py - utility to start Qt application
#
# Copyright 2008 Steve Borho <steve@borho.org>
# Copyright 2008 TK Soh <teekaysoh@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gc, os, sys, traceback

from PyQt4.QtCore import *
from PyQt4.QtGui import QApplication
from PyQt4.QtNetwork import QLocalServer, QLocalSocket

from mercurial import error, util

from tortoisehg.hgqt.i18n import _
from tortoisehg.util import hglib, i18n
from tortoisehg.util import version as thgversion
from tortoisehg.hgqt import bugreport, qtlib, thgrepo, workbench

try:
    from thginithook import thginithook
except ImportError:
    thginithook = None

# {exception class: message}
# It doesn't check the hierarchy of exception classes for simplicity.
_recoverableexc = {
    error.RepoLookupError: _('Try refreshing your repository.'),
    error.RevlogError:     _('Try refreshing your repository.'),
    error.ParseError: _('Error string "%(arg0)s" at %(arg1)s<br>Please '
                        '<a href="#edit:%(arg1)s">edit</a> your config'),
    error.ConfigError: _('Configuration Error: "%(arg0)s",<br>Please '
                         '<a href="#fix:%(arg0)s">fix</a> your config'),
    error.Abort: _('Operation aborted:<br><br>%(arg0)s.'),
    error.LockUnavailable: _('Repository is locked'),
    }

def earlyExceptionMsgBox(e):
    """Show message for recoverable error before the QApplication is started"""
    opts = {}
    opts['cmd'] = ' '.join(sys.argv[1:])
    opts['values'] = e
    opts['error'] = traceback.format_exc()
    opts['nofork'] = True
    errstring = _recoverableexc[e.__class__]
    if not QApplication.instance():
        main = QApplication(sys.argv)
    dlg = bugreport.ExceptionMsgBox(hglib.tounicode(str(e)), errstring, opts)
    dlg.exec_()

def earlyBugReport(e):
    """Show generic errors before the QApplication is started"""
    opts = {}
    opts['cmd'] = ' '.join(sys.argv[1:])
    opts['error'] = traceback.format_exc()
    if not QApplication.instance():
        main = QApplication(sys.argv)
    dlg = bugreport.BugReport(opts)
    dlg.exec_()

class ExceptionCatcher(QObject):
    """Catch unhandled exception raised inside Qt event loop"""

    _exceptionOccured = pyqtSignal(object, object, object)

    def __init__(self, ui, mainapp, parent=None):
        super(ExceptionCatcher, self).__init__(parent)
        self._ui = ui
        self._mainapp = mainapp
        self.errors = []

        # can be emitted by another thread; postpones it until next
        # eventloop of main (GUI) thread.
        self._exceptionOccured.connect(self.putexception,
                                       Qt.QueuedConnection)

        self._ui.debug('setting up excepthook\n')
        self._origexcepthook = sys.excepthook
        sys.excepthook = self.ehook

    def release(self):
        if not self._origexcepthook:
            return
        self._ui.debug('restoring excepthook\n')
        sys.excepthook = self._origexcepthook
        self._origexcepthook = None

    def ehook(self, etype, evalue, tracebackobj):
        'Will be called by any thread, on any unhandled exception'
        if self._ui.debugflag:
            elist = traceback.format_exception(etype, evalue, tracebackobj)
            self._ui.debug(''.join(elist))
        self._exceptionOccured.emit(etype, evalue, tracebackobj)
        # not thread-safe to touch self.errors here

    @pyqtSlot(object, object, object)
    def putexception(self, etype, evalue, tracebackobj):
        'Enque exception info and display it later; run in main thread'
        if not self.errors:
            QTimer.singleShot(10, self.excepthandler)
        self.errors.append((etype, evalue, tracebackobj))

    @pyqtSlot()
    def excepthandler(self):
        'Display exception info; run in main (GUI) thread'
        try:
            try:
                self._showexceptiondialog()
            except:
                # make sure to quit mainloop first, so that it never leave
                # zombie process.
                self._mainapp.exit(1)
                self._printexception()
        finally:
            self.errors = []

    def _showexceptiondialog(self):
        opts = {}
        opts['cmd'] = ' '.join(sys.argv[1:])
        opts['error'] = ''.join(''.join(traceback.format_exception(*args))
                                for args in self.errors)
        etype, evalue = self.errors[0][:2]
        if (len(set(e[0] for e in self.errors)) == 1
            and etype in _recoverableexc):
            opts['values'] = evalue
            errstr = _recoverableexc[etype]
            if etype is error.Abort and evalue.hint:
                errstr = u''.join([errstr, u'<br><b>', _('hint:'),
                                   u'</b> %(arg1)s'])
                opts['values'] = [str(evalue), evalue.hint]
            dlg = bugreport.ExceptionMsgBox(hglib.tounicode(str(evalue)),
                                            errstr, opts,
                                            parent=self._mainapp.activeWindow())
        elif etype is KeyboardInterrupt:
            if qtlib.QuestionMsgBox(_('Keyboard interrupt'),
                                    _('Close this application?')):
                QApplication.quit()
            else:
                self.errors = []
                return
        else:
            dlg = bugreport.BugReport(opts, parent=self._mainapp.activeWindow())
        dlg.exec_()

    def _printexception(self):
        for args in self.errors:
            traceback.print_exception(*args)


class GarbageCollector(QObject):
    '''
    Disable automatic garbage collection and instead collect manually
    every INTERVAL milliseconds.

    This is done to ensure that garbage collection only happens in the GUI
    thread, as otherwise Qt can crash.
    '''

    INTERVAL = 5000

    def __init__(self, ui, parent):
        QObject.__init__(self, parent)
        self._ui = ui

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)

        self.threshold = gc.get_threshold()
        gc.disable()
        self.timer.start(self.INTERVAL)
        #gc.set_debug(gc.DEBUG_SAVEALL)

    def check(self):
        l0, l1, l2 = gc.get_count()
        if l0 > self.threshold[0]:
            num = gc.collect(0)
            self._ui.debug('GarbageCollector.check: %d %d %d\n' % (l0, l1, l2))
            self._ui.debug('collected gen 0, found %d unreachable\n' % num)
            if l1 > self.threshold[1]:
                num = gc.collect(1)
                self._ui.debug('collected gen 1, found %d unreachable\n' % num)
                if l2 > self.threshold[2]:
                    num = gc.collect(2)
                    self._ui.debug('collected gen 2, found %d unreachable\n'
                                   % num)

    def debug_cycles(self):
        gc.collect()
        for obj in gc.garbage:
            self._ui.debug('%s, %r, %s\n' % (obj, obj, type(obj)))


def allowSetForegroundWindow(processid=-1):
    """Allow a given process to set the foreground window"""
    # processid = -1 means ASFW_ANY (i.e. allow any process)
    if os.name == 'nt':
        # on windows we must explicitly allow bringing the main window to
        # the foreground. To do so we must use ctypes
        try:
            from ctypes import windll
            windll.user32.AllowSetForegroundWindow(processid)
        except ImportError:
            pass

def connectToExistingWorkbench(root=None):
    """
    Connect and send data to an existing workbench server

    For the connection to be successful, the server must loopback the data
    that we send to it.

    Normally the data that is sent will be a repository root path, but we can
    also send "echo" to check that the connection works (i.e. that there is a
    server)
    """
    if root:
        data = root
    else:
        data = '[echo]'
    socket = QLocalSocket()
    socket.connectToServer(QApplication.applicationName() + '-' + util.getuser(),
        QIODevice.ReadWrite)
    if socket.waitForConnected(10000):
        # Momentarily let any process set the foreground window
        # The server process with revoke this permission as soon as it gets
        # the request
        allowSetForegroundWindow()
        socket.write(QByteArray(data))
        socket.flush()
        socket.waitForReadyRead(10000)
        reply = socket.readAll()
        if data == reply:
            return True
    return False


class QtRunner(QObject):
    """Run Qt app and hold its windows

    NOTE: This object will be instantiated before QApplication, it means
    there's a limitation on Qt's event handling. See
    http://doc.qt.nokia.com/4.6/threads-qobject.html#per-thread-event-loop
    """

    def __init__(self):
        super(QtRunner, self).__init__()
        self._ui = None
        self._mainapp = None
        self._exccatcher = None
        self._server = None
        self._repomanager = None
        self._workbench = None
        self._dialogs = {}  # dlg: reporoot

    def __call__(self, dlgfunc, ui, *args, **opts):
        if self._mainapp:
            self._opendialog(dlgfunc, args, opts)
            return

        QSettings.setDefaultFormat(QSettings.IniFormat)

        self._ui = ui
        self._mainapp = QApplication(sys.argv)
        self._exccatcher = ExceptionCatcher(ui, self._mainapp, self)
        self._gc = GarbageCollector(ui, self)
        # default org is used by QSettings
        self._mainapp.setApplicationName('TortoiseHgQt')
        self._mainapp.setOrganizationName('TortoiseHg')
        self._mainapp.setOrganizationDomain('tortoisehg.org')
        self._mainapp.setApplicationVersion(thgversion.version())
        self._fixlibrarypaths()
        self._installtranslator()
        qtlib.setup_font_substitutions()
        qtlib.fix_application_font()
        qtlib.configstyles(ui)
        qtlib.initfontcache(ui)
        self._mainapp.setWindowIcon(qtlib.geticon('thg-logo'))

        self._repomanager = thgrepo.RepoManager(ui, self)

        dlg, reporoot = self._createdialog(dlgfunc, args, opts)
        try:
            if dlg:
                dlg.show()
                dlg.raise_()
            else:
                return -1

            if thginithook is not None:
                thginithook()

            return self._mainapp.exec_()
        finally:
            if reporoot:
                self._repomanager.releaseRepoAgent(reporoot)
            if self._server:
                self._server.close()
            self._exccatcher.release()
            self._mainapp = self._ui = None

    def _fixlibrarypaths(self):
        # make sure to use the bundled Qt plugins to avoid ABI incompatibility
        # http://qt-project.org/doc/qt-4.8/deployment-windows.html#qt-plugins
        if os.name == 'nt' and getattr(sys, 'frozen', False):
            self._mainapp.setLibraryPaths([self._mainapp.applicationDirPath()])

    def _installtranslator(self):
        if not i18n.language:
            return
        t = QTranslator(self._mainapp)
        t.load('qt_' + i18n.language, qtlib.gettranslationpath())
        self._mainapp.installTranslator(t)

    def _createdialog(self, dlgfunc, args, opts):
        assert self._ui and self._repomanager
        reporoot = None
        try:
            args = list(args)
            if 'repository' in opts:
                repoagent = self._repomanager.openRepoAgent(
                    hglib.tounicode(opts['repository']))
                reporoot = repoagent.rootPath()
                args.insert(0, repoagent)
            return dlgfunc(self._ui, *args, **opts), reporoot
        except error.RepoError, inst:
            qtlib.WarningMsgBox(_('Repository Error'),
                                hglib.tounicode(str(inst)))
        except error.Abort, inst:
            qtlib.WarningMsgBox(_('Abort'),
                                hglib.tounicode(str(inst)),
                                hglib.tounicode(inst.hint or ''))
        if reporoot:
            self._repomanager.releaseRepoAgent(reporoot)
        return None, None

    def _opendialog(self, dlgfunc, args, opts):
        dlg, reporoot = self._createdialog(dlgfunc, args, opts)
        if not dlg:
            return

        self._dialogs[dlg] = reporoot  # avoid garbage collection
        if hasattr(dlg, 'finished') and hasattr(dlg.finished, 'connect'):
            dlg.finished.connect(dlg.deleteLater)
        # NOTE: Somehow `destroyed` signal doesn't emit the original obj.
        # So we cannot write `dlg.destroyed.connect(self._forgetdialog)`.
        dlg.destroyed.connect(lambda: self._forgetdialog(dlg))
        dlg.show()

    def _forgetdialog(self, dlg):
        """forget the dialog to be garbage collectable"""
        assert dlg in self._dialogs
        reporoot = self._dialogs.pop(dlg)
        if reporoot:
            self._repomanager.releaseRepoAgent(reporoot)

    def createWorkbench(self):
        """Create Workbench window and keep single reference"""
        assert self._ui and self._mainapp and self._repomanager
        assert not self._workbench
        self._workbench = workbench.Workbench(self._ui, self._repomanager)
        return self._workbench

    def showRepoInWorkbench(self, uroot, rev=-1):
        """Show the specified repository in Workbench"""
        assert self._mainapp
        if not self._workbench:
            self.createWorkbench()
            assert self._workbench

        wb = self._workbench
        wb.show()
        wb.activateWindow()
        wb.raise_()
        wb.showRepo(uroot)
        if rev != -1:
            wb.goto(hglib.fromunicode(uroot), rev)

    def createWorkbenchServer(self):
        assert self._mainapp
        assert not self._server
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._handleNewConnection)
        self._server.listen(self._mainapp.applicationName() + '-' + util.getuser())

    @pyqtSlot()
    def _handleNewConnection(self):
        socket = self._server.nextPendingConnection()
        if socket:
            socket.waitForReadyRead(10000)
            root = str(socket.readAll())
            if root and root != '[echo]':
                self.showRepoInWorkbench(hglib.tounicode(root))

                # Bring the workbench window to the front
                # This assumes that the client process has
                # called allowSetForegroundWindow(-1) right before
                # sending the request
                wb = self._workbench
                wb.setWindowState(wb.windowState() & ~Qt.WindowMinimized
                                  | Qt.WindowActive)
                wb.show()
                wb.raise_()
                wb.activateWindow()
                # Revoke the blanket permission to set the foreground window
                allowSetForegroundWindow(os.getpid())

            socket.write(QByteArray(root))
            socket.flush()

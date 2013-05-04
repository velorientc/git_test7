# qtapp.py - utility to start Qt application
#
# Copyright 2008 Steve Borho <steve@borho.org>
# Copyright 2008 TK Soh <teekaysoh@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gc, os, sys, traceback, zlib

from PyQt4.QtCore import *
from PyQt4.QtGui import QApplication

from mercurial import error

from tortoisehg.hgqt.i18n import _
from tortoisehg.util import hglib, i18n
from tortoisehg.util import version as thgversion
from tortoisehg.hgqt import bugreport, qtlib

try:
    from thginithook import thginithook
except ImportError:
    thginithook = None

def earlyExceptionMsgBox(e):
    """Show message for recoverable error before the QApplication is started"""
    opts = {}
    opts['cmd'] = ' '.join(sys.argv[1:])
    opts['values'] = e
    opts['error'] = traceback.format_exc()
    opts['nofork'] = True
    errstring = _('Error string "%(arg0)s" at %(arg1)s<br>Please '
                  '<a href="#edit:%(arg1)s">edit</a> your config')
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

class GarbageCollector(QObject):
    '''
    Disable automatic garbage collection and instead collect manually
    every INTERVAL milliseconds.

    This is done to ensure that garbage collection only happens in the GUI
    thread, as otherwise Qt can crash.
    '''

    INTERVAL = 5000

    def __init__(self, parent, debug=False):
        QObject.__init__(self, parent)
        self.debug = debug

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
            if self.debug:
                print 'GarbageCollector.check:', l0, l1, l2
                print 'collected gen 0, found', num, 'unreachable'
            if l1 > self.threshold[1]:
                num = gc.collect(1)
                if self.debug:
                    print 'collected gen 1, found', num, 'unreachable'
                if l2 > self.threshold[2]:
                    num = gc.collect(2)
                    if self.debug:
                        print 'collected gen 2, found', num, 'unreachable'

    def debug_cycles(self):
        gc.collect()
        for obj in gc.garbage:
            print (obj, repr(obj), type(obj))

class QtRunner(QObject):
    """Run Qt app and hold its windows

    NOTE: This object will be instantiated before QApplication, it means
    there's a limitation on Qt's event handling. See
    http://doc.qt.nokia.com/4.6/threads-qobject.html#per-thread-event-loop
    """

    _exceptionOccured = pyqtSignal(object, object, object)

    # {exception class: message}
    # It doesn't check the hierarchy of exception classes for simplicity.
    _recoverableexc = {
        error.RepoLookupError: _('Try refreshing your repository.'),
        zlib.error:            _('Try refreshing your repository.'),
        error.ParseError: _('Error string "%(arg0)s" at %(arg1)s<br>Please '
                            '<a href="#edit:%(arg1)s">edit</a> your config'),
        error.ConfigError: _('Configuration Error: "%(arg0)s",<br>Please '
                             '<a href="#fix:%(arg0)s">fix</a> your config'),
        error.Abort: _('Operation aborted:<br><br>%(arg0)s.'),
        error.LockUnavailable: _('Repository is locked'),
        }

    def __init__(self):
        super(QtRunner, self).__init__()
        gc.disable()
        self.debug = 'THGDEBUG' in os.environ
        self._mainapp = None
        self._dialogs = []
        self.errors = []
        sys.excepthook = lambda t, v, o: self.ehook(t, v, o)

        # can be emitted by another thread; postpones it until next
        # eventloop of main (GUI) thread.
        self._exceptionOccured.connect(self.putexception,
                                       Qt.QueuedConnection)

    def ehook(self, etype, evalue, tracebackobj):
        'Will be called by any thread, on any unhandled exception'
        elist = traceback.format_exception(etype, evalue, tracebackobj)
        if 'THGDEBUG' in os.environ:
            sys.stderr.write(''.join(elist))
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
            and etype in self._recoverableexc):
            opts['values'] = evalue
            errstr = self._recoverableexc[etype]
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

    def __call__(self, dlgfunc, ui, *args, **opts):
        if self._mainapp:
            self._opendialog(dlgfunc, ui, *args, **opts)
            return

        QSettings.setDefaultFormat(QSettings.IniFormat)

        self._mainapp = QApplication(sys.argv)
        self._gc = GarbageCollector(self, self.debug)
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

        if 'repository' in opts:
            try:
                # Ensure we can open the repository before opening any
                # dialog windows.  Since thgrepo instances are cached, this
                # is not wasted.
                from tortoisehg.hgqt import thgrepo
                thgrepo.repository(ui, opts['repository'])
            except error.RepoError, e:
                qtlib.WarningMsgBox(_('Repository Error'),
                                    hglib.tounicode(str(e)))
                return
        dlg = dlgfunc(ui, *args, **opts)
        if dlg:
            dlg.show()
            dlg.raise_()
        else:
            return -1

        if thginithook is not None:
            thginithook()

        try:
            return self._mainapp.exec_()
        finally:
            self._mainapp = None

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

    def _opendialog(self, dlgfunc, ui, *args, **opts):
        dlg = dlgfunc(ui, *args, **opts)
        if not dlg:
            return

        self._dialogs.append(dlg)  # avoid garbage collection
        if hasattr(dlg, 'finished') and hasattr(dlg.finished, 'connect'):
            dlg.finished.connect(dlg.deleteLater)
        # NOTE: Somehow `destroyed` signal doesn't emit the original obj.
        # So we cannot write `dlg.destroyed.connect(self._forgetdialog)`.
        dlg.destroyed.connect(lambda: self._forgetdialog(dlg))
        dlg.show()

    def _forgetdialog(self, dlg):
        """forget the dialog to be garbage collectable"""
        assert dlg in self._dialogs
        self._dialogs.remove(dlg)

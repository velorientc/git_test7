# cmdcore.py - run Mercurial commands in a separate thread or process
#
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os, sys, time

from PyQt4.QtCore import QIODevice, QObject, QProcess, QString
from PyQt4.QtCore import pyqtSignal, pyqtSlot

from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import thread

def _findhgexe():
    exepath = None
    if hasattr(sys, 'frozen'):
        progdir = paths.get_prog_root()
        exe = os.path.join(progdir, 'hg.exe')
        if os.path.exists(exe):
            exepath = exe
    if not exepath:
        exepath = paths.find_in_path('hg')
    return exepath

# TODO: provide CmdThread-compatible interface
class CmdProc(QObject):
    'Run mercurial command in separate process'

    started = pyqtSignal()
    commandFinished = pyqtSignal(int)
    outputReceived = pyqtSignal(QString, QString)

    def __init__(self, queue, rawoutlines, parent=None):
        super(CmdProc, self).__init__(parent)
        self.queue = queue
        self.rawoutlines = rawoutlines
        self.abortbyuser = False

        self._proc = proc = QProcess(self)
        proc.started.connect(self.started)
        proc.finished.connect(self._finished)
        proc.readyReadStandardOutput.connect(self._stdout)
        proc.readyReadStandardError.connect(self._stderr)
        proc.error.connect(self._handleerror)

    def start(self, cmdline, display):
        del self.rawoutlines[:]
        if display:
            cmd = '%% hg %s\n' % display
        else:
            cmd = '%% hg %s\n' % _prettifycmdline(cmdline)
        self.outputReceived.emit(cmd, 'control')
        self._proc.start(_findhgexe(), cmdline, QIODevice.ReadOnly)

    def abort(self):
        if not self.isRunning():
            return
        self._proc.close()
        self.abortbyuser = True

    def isRunning(self):
        return self._proc.state() != QProcess.NotRunning

    @pyqtSlot(int)
    def _finished(self, ret):
        if ret:
            msg = _('[command returned code %d %%s]') % int(ret)
        else:
            msg = _('[command completed successfully %s]')
        msg = msg % time.asctime() + '\n'
        self.outputReceived.emit(msg, 'control')
        if ret == 0 and self.queue:
            self.start(self.queue.pop(0), '')
        else:
            del self.queue[:]
            # TODO: self.extproc = None
            self.commandFinished.emit(ret)

    def _handleerror(self, error):
        if error == QProcess.FailedToStart:
            self.outputReceived.emit(_('failed to start command\n'),
                                     'ui.error')
            self._finished(-1)
        elif error != QProcess.Crashed:
            self.outputReceived.emit(_('error while running command\n'),
                                     'ui.error')

    def _stdout(self):
        data = self._proc.readAllStandardOutput().data()
        self.rawoutlines.append(data)
        self.outputReceived.emit(hglib.tounicode(data), '')

    def _stderr(self):
        data = self._proc.readAllStandardError().data()
        self.outputReceived.emit(hglib.tounicode(data), 'ui.error')


def _quotecmdarg(arg):
    # only for display; no use to construct command string for os.system()
    if not arg or ' ' in arg or '\\' in arg or '"' in arg:
        return '"%s"' % arg.replace('"', '\\"')
    else:
        return arg

def _prettifycmdline(cmdline):
    r"""Build pretty command-line string for display

    >>> _prettifycmdline(['--repository', 'foo', 'status'])
    'status'
    >>> _prettifycmdline(['--cwd', 'foo', 'resolve', '--', '--repository'])
    'resolve -- --repository'
    >>> _prettifycmdline(['log', 'foo\\bar', '', 'foo bar', 'foo"bar'])
    'log "foo\\bar" "" "foo bar" "foo\\"bar"'
    """
    try:
        argcount = cmdline.index('--')
    except ValueError:
        argcount = len(cmdline)
    printables = []
    pos = 0
    while pos < argcount:
        if cmdline[pos] in ('-R', '--repository', '--cwd'):
            pos += 2
        else:
            printables.append(cmdline[pos])
            pos += 1
    printables.extend(cmdline[argcount:])

    return ' '.join(_quotecmdarg(e) for e in printables)

class Core(QObject):
    """Core functionality for running Mercurial command.
    Do not attempt to instantiate and use this directly.
    """

    commandStarted = pyqtSignal()
    commandFinished = pyqtSignal(int)
    commandCanceling = pyqtSignal()

    output = pyqtSignal(QString, QString)
    progress = pyqtSignal(QString, object, QString, QString, object)

    def __init__(self, logWindow, parent):
        super(Core, self).__init__(parent)

        self.thread = None
        self.extproc = None
        self.stbar = None
        self.queue = []
        self.rawoutlines = []
        self.display = None
        self.useproc = False
        if logWindow:
            # TODO: move logWindow back to cmdui
            from tortoisehg.hgqt import cmdui, qscilib
            self.outputLog = cmdui.LogWidget()
            self.outputLog.installEventFilter(qscilib.KeyPressInterceptor(self))
            self.output.connect(self.outputLog.appendLog)

    ### Public Methods ###

    def run(self, cmdline, *cmdlines, **opts):
        '''Execute or queue Mercurial command'''
        self.display = opts.get('display')
        self.useproc = opts.get('useproc', False)
        self.queue.append(cmdline)
        if len(cmdlines):
            self.queue.extend(cmdlines)
        if self.useproc:
            self.runproc()
        elif not self.running():
            self.runNext()

    def cancel(self):
        '''Cancel running Mercurial command'''
        if self.running():
            try:
                if self.extproc:
                    self.extproc.abort()
                elif self.thread:
                    self.thread.abort()
            except AttributeError:
                pass
            self.commandCanceling.emit()

    def setStbar(self, stbar):
        self.stbar = stbar

    def running(self):
        try:
            if self.extproc:
                return self.extproc.isRunning()
            elif self.thread:
                # keep "running" until just before emitting commandFinished.
                # thread.isRunning() is cleared earlier than onThreadFinished,
                # because inter-thread signal is queued.
                return True
        except AttributeError:
            pass
        return False

    def rawoutput(self):
        return ''.join(self.rawoutlines)

    ### Private Method ###

    def runproc(self):
        self.extproc = CmdProc(self.queue, self.rawoutlines, self)
        self.extproc.started.connect(self.onCommandStarted)
        self.extproc.commandFinished.connect(self.commandFinished)
        self.extproc.outputReceived.connect(self.output)
        self.extproc.start(self.queue.pop(0), self.display)

    def runNext(self):
        if not self.queue:
            return False

        cmdline = self.queue.pop(0)

        display = self.display or _prettifycmdline(cmdline)
        self.thread = thread.CmdThread(cmdline, display, self.parent())
        self.thread.started.connect(self.onCommandStarted)
        self.thread.commandFinished.connect(self.onThreadFinished)

        self.thread.outputReceived.connect(self.output)
        self.thread.progressReceived.connect(self.progress)
        if self.stbar:
            self.thread.progressReceived.connect(self.stbar.progress)

        self.thread.start()
        return True

    def clearOutput(self):
        if hasattr(self, 'outputLog'):
            self.outputLog.clear()

    ### Signal Handlers ###

    @pyqtSlot()
    def onCommandStarted(self):
        if self.stbar:
            self.stbar.showMessage(_('Running...'))

        self.commandStarted.emit()

    @pyqtSlot(int)
    def onThreadFinished(self, ret):
        if self.stbar:
            error = False
            if ret is None:
                self.stbar.clear()
                if self.thread.abortbyuser:
                    status = _('Terminated by user')
                else:
                    status = _('Terminated')
            elif ret == 0:
                status = _('Finished')
            else:
                status = _('Failed!')
                error = True
            self.stbar.showMessage(status, error)

        self.display = None
        self.thread.setParent(None)  # assist gc
        if ret == 0 and self.runNext():
            return # run next command
        else:
            self.queue = []
            text = self.thread.rawoutput.join('')
            self.thread = None
            self.rawoutlines = [hglib.fromunicode(text, 'replace')]

        self.commandFinished.emit(ret)

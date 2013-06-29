# cmdcore.py - run Mercurial commands in a separate thread or process
#
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os, sys, time

from PyQt4.QtCore import QIODevice, QObject, QProcess, QString, QStringList
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

class CmdProc(QObject):
    'Run mercurial command in separate process'

    started = pyqtSignal()
    commandFinished = pyqtSignal(int)
    outputReceived = pyqtSignal(QString, QString)

    # progress is not supported but needed to be a worker class
    progressReceived = pyqtSignal(QString, object, QString, QString, object)

    def __init__(self, cmdline, parent=None):
        super(CmdProc, self).__init__(parent)
        self.cmdline = cmdline
        self.abortbyuser = False
        self.rawoutput = QStringList()

        self._proc = proc = QProcess(self)
        proc.started.connect(self.started)
        proc.finished.connect(self._finished)
        proc.readyReadStandardOutput.connect(self._stdout)
        proc.readyReadStandardError.connect(self._stderr)
        proc.error.connect(self._handleerror)

    def start(self):
        self._proc.start(_findhgexe(), self.cmdline, QIODevice.ReadOnly)

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
        self.rawoutput.append(hglib.tounicode(data))
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

        self._worker = None
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
        if not self.running():
            self.runNext()

    def cancel(self):
        '''Cancel running Mercurial command'''
        if self.running():
            if self._worker:
                self._worker.abort()
            self.commandCanceling.emit()

    def setStbar(self, stbar):
        self.stbar = stbar

    def running(self):
        # keep "running" until just before emitting commandFinished. if worker
        # is QThread, isRunning() is cleared earlier than onCommandFinished,
        # because inter-thread signal is queued.
        return bool(self._worker)

    def rawoutput(self):
        return ''.join(self.rawoutlines)

    ### Private Method ###

    def runNext(self):
        if not self.queue:
            return False

        cmdline = self.queue.pop(0)

        if not self.display:
            self.display = _prettifycmdline(cmdline)
        if self.useproc:
            self._worker = CmdProc(cmdline, self)
        else:
            self._worker = thread.CmdThread(cmdline, self.parent())
        self._worker.started.connect(self.onCommandStarted)
        self._worker.commandFinished.connect(self.onCommandFinished)

        self._worker.outputReceived.connect(self.output)
        self._worker.progressReceived.connect(self.progress)
        if self.stbar:
            self._worker.progressReceived.connect(self.stbar.progress)

        self._worker.start()
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
        cmd = '%% hg %s\n' % self.display
        self.output.emit(hglib.tounicode(cmd), 'control')

    @pyqtSlot(int)
    def onCommandFinished(self, ret):
        if self.stbar:
            error = False
            if ret is None:
                self.stbar.clear()
                if self._worker.abortbyuser:
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
        self._worker.setParent(None)  # assist gc
        if ret == 0 and self.runNext():
            return # run next command
        else:
            self.queue = []
            text = self._worker.rawoutput.join('')
            self._worker = None
            self.rawoutlines = [hglib.fromunicode(text, 'replace')]

        self.commandFinished.emit(ret)

# docklog.py - Log dock widget for the TortoiseHg Workbench
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import glob, os, shlex

from mercurial import util

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui
from tortoisehg.util import hglib

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qsci import QsciScintilla

class _LogWidgetForConsole(cmdui.LogWidget):
    """Wrapped LogWidget for ConsoleWidget"""

    returnPressed = pyqtSignal(unicode)
    """Return key pressed when cursor is on prompt line"""

    _prompt = '% '

    def __init__(self, parent=None):
        super(_LogWidgetForConsole, self).__init__(parent)
        self._prompt_marker = self.markerDefine(QsciScintilla.Background)
        self.setMarkerBackgroundColor(QColor('#e8f3fe'), self._prompt_marker)
        self.cursorPositionChanged.connect(self._updatePrompt)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._cursoronpromptline():
                self.returnPressed.emit(self.commandText())
            return
        super(_LogWidgetForConsole, self).keyPressEvent(event)

    def setPrompt(self, text):
        if text == self._prompt:
            return
        self.clearPrompt()
        self._prompt = text
        self.openPrompt()

    @pyqtSlot()
    def openPrompt(self):
        """Show prompt line and enable user input"""
        self.closePrompt()
        self.markerAdd(self.lines() - 1, self._prompt_marker)
        self.append(self._prompt)
        self.setCursorPosition(self.lines() - 1, len(self._prompt))
        self.setReadOnly(False)

        # make sure the prompt line is visible. Because QsciScintilla may
        # delay line wrapping, setCursorPosition() doesn't always scrolls
        # to the correct position.
        # http://www.scintilla.org/ScintillaDoc.html#LineWrapping
        self.SCN_PAINTED.connect(self._scrollCaretOnPainted)

    @pyqtSlot()
    def _scrollCaretOnPainted(self):
        self.SCN_PAINTED.disconnect(self._scrollCaretOnPainted)
        self.SendScintilla(self.SCI_SCROLLCARET)

    def _findPromptLine(self):
        return self.markerFindPrevious(self.lines() - 1,
                                       1 << self._prompt_marker)

    @pyqtSlot()
    def closePrompt(self):
        """Disable user input"""
        line = self._findPromptLine()
        if line >= 0:
            if self.commandText():
                self._setmarker((line,), 'control')
            self.markerDelete(line, self._prompt_marker)
        self._newline()
        self.setCursorPosition(self.lines() - 1, 0)
        self.setReadOnly(True)

    @pyqtSlot()
    def clearPrompt(self):
        """Clear prompt line and subsequent text"""
        line = self._findPromptLine()
        if line < 0:
            return
        self.markerDelete(line)
        lastline = self.lines() - 1
        self.setSelection(line, 0, lastline, len(self.text(lastline)))
        self.removeSelectedText()

    @pyqtSlot(int, int)
    def _updatePrompt(self, line, pos):
        """Update availability of user input"""
        if self.markersAtLine(line) & (1 << self._prompt_marker):
            self.setReadOnly(False)
            self._ensurePrompt(line)
        else:
            self.setReadOnly(True)

    def _ensurePrompt(self, line):
        """Insert prompt string if not available"""
        s = unicode(self.text(line))
        if s.startswith(self._prompt):
            return
        for i, c in enumerate(self._prompt):
            if s[i:i + 1] != c:
                self.insertAt(self._prompt[i:], line, i)
                break
        self.setCursorPosition(line, len(self.text(line)))

    def commandText(self):
        """Return the current command text"""
        l = self._findPromptLine()
        if l >= 0:
            return unicode(self.text(l))[len(self._prompt):].rstrip('\n')
        else:
            return ''

    def setCommandText(self, text):
        """Replace the current command text; subsequent text is also removed"""
        line = self._findPromptLine()
        if line < 0:
            return
        self._ensurePrompt(line)
        lastline = self.lines() - 1
        self.setSelection(line, len(self._prompt),
                          lastline, len(self.text(lastline)))
        self.removeSelectedText()
        self.insert(text)
        self.setCursorPosition(line, len(self.text(line)))

    def _newline(self):
        if self.text(self.lines() - 1):
            self.append('\n')

    def _cursoronpromptline(self):
        line = self.getCursorPosition()[0]
        return self.markersAtLine(line) & (1 << self._prompt_marker)

class _ConsoleCmdTable(dict):
    """Command table for ConsoleWidget"""
    _cmdfuncprefix = '_cmd_'

    def __call__(self, func):
        if not func.__name__.startswith(self._cmdfuncprefix):
            raise ValueError('bad command function name %s' % func.__name__)
        self[func.__name__[len(self._cmdfuncprefix):]] = func
        return func

class ConsoleWidget(QWidget):
    """Console to run hg/thg command and show output"""
    closeRequested = pyqtSignal()

    progressReceived = pyqtSignal(QString, object, QString, QString,
                                  object, object)
    """Emitted when progress received

    Args: topic, pos, item, unit, total, reporoot
    """

    _cmdtable = _ConsoleCmdTable()

    # TODO: command history and completion

    def __init__(self, parent=None):
        super(ConsoleWidget, self).__init__(parent)
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self._initlogwidget()
        self.setFocusProxy(self._logwidget)
        self.setRepository(None)
        self.openPrompt()
        self.suppressPrompt = False

    def _initlogwidget(self):
        self._logwidget = _LogWidgetForConsole(self)
        self._logwidget.returnPressed.connect(self._runcommand)
        self.layout().addWidget(self._logwidget)

        # compatibility methods with LogWidget
        for name in ('openPrompt', 'closePrompt', 'clear'):
            setattr(self, name, getattr(self._logwidget, name))

    @util.propertycache
    def _cmdcore(self):
        cmdcore = cmdui.Core(False, self)
        cmdcore.output.connect(self._logwidget.appendLog)
        cmdcore.commandStarted.connect(self.closePrompt)
        cmdcore.commandFinished.connect(self.openPrompt)
        cmdcore.progress.connect(self._emitProgress)
        return cmdcore

    @util.propertycache
    def _extproc(self):
        extproc = QProcess(self)
        extproc.started.connect(self.closePrompt)
        extproc.finished.connect(self.openPrompt)

        def handleerror(error):
            msgmap = {
                QProcess.FailedToStart: _('failed to run command\n'),
                QProcess.Crashed: _('crashed\n')}
            if extproc.state() == QProcess.NotRunning:
                self._logwidget.closePrompt()
            self._logwidget.appendLog(
                msgmap.get(error, _('error while running command\n')),
                'ui.error')
            if extproc.state() == QProcess.NotRunning:
                self._logwidget.openPrompt()
        extproc.error.connect(handleerror)

        def put(bytes, label=None):
            self._logwidget.appendLog(hglib.tounicode(bytes.data()), label)
        extproc.readyReadStandardOutput.connect(
            lambda: put(extproc.readAllStandardOutput()))
        extproc.readyReadStandardError.connect(
            lambda: put(extproc.readAllStandardError(), 'ui.error'))

        return extproc

    @pyqtSlot(unicode, str)
    def appendLog(self, msg, label):
        """Append log text from another cmdui"""
        self._logwidget.clearPrompt()
        try:
            self._logwidget.appendLog(msg, label)
        finally:
            if not self.suppressPrompt:
                self.openPrompt()

    @pyqtSlot(object)
    def setRepository(self, repo):
        """Change the current working repository"""
        self._repo = repo
        self._logwidget.setPrompt('%s%% ' % (repo and repo.displayname or ''))

    @property
    def cwd(self):
        """Return the current working directory"""
        return self._repo and self._repo.root or os.getcwd()

    @pyqtSlot(unicode, object, unicode, unicode, object)
    def _emitProgress(self, *args):
        self.progressReceived.emit(
            *(args + (self._repo and self._repo.root or None,)))

    @pyqtSlot(unicode)
    def _runcommand(self, cmdline):
        try:
            args = list(self._parsecmdline(cmdline))
        except ValueError, e:
            self.closePrompt()
            self._logwidget.appendLog(unicode(e) + '\n', 'ui.error')
            self.openPrompt()
            return
        if not args:
            self.openPrompt()
            return
        cmd = args.pop(0)
        try:
            self._cmdtable[cmd](self, args)
        except KeyError:
            return self._runextcommand(cmdline)

    def _parsecmdline(self, cmdline):
        """Split command line string to imitate a unix shell"""
        try:
            args = shlex.split(hglib.fromunicode(cmdline))
        except ValueError, e:
            raise ValueError(_('command parse error: %s') % e)
        for e in args:
            e = util.expandpath(e)
            if util.any(c in e for c in '*?[]'):
                expanded = glob.glob(os.path.join(self.cwd, e))
                if not expanded:
                    raise ValueError(_('no matches found: %s')
                                     % hglib.tounicode(e))
                for p in expanded:
                    yield p
            else:
                yield e

    def _runextcommand(self, cmdline):
        self._extproc.setWorkingDirectory(hglib.tounicode(self.cwd))
        self._extproc.start(cmdline, QIODevice.ReadOnly)

    @_cmdtable
    def _cmd_hg(self, args):
        self.closePrompt()
        if self._repo:
            args = ['--cwd', self._repo.root] + args
        self._cmdcore.run(args)

    @_cmdtable
    def _cmd_thg(self, args):
        from tortoisehg.hgqt import run
        self.closePrompt()
        try:
            if self._repo:
                args = ['-R', self._repo.root] + args
            # TODO: show errors
            run.dispatch(args)
        finally:
            self.openPrompt()

    @_cmdtable
    def _cmd_clear(self, args):
        self.clear()
        self.openPrompt()

    @_cmdtable
    def _cmd_cls(self, args):
        self.clear()
        self.openPrompt()

    @_cmdtable
    def _cmd_exit(self, args):
        self.clear()
        self.openPrompt()
        self.closeRequested.emit()

class LogDockWidget(QDockWidget):
    visibilityChanged = pyqtSignal(bool)

    def __init__(self, parent=None):
        super(LogDockWidget, self).__init__(parent)

        self.setFeatures(QDockWidget.DockWidgetClosable |
                         QDockWidget.DockWidgetMovable  |
                         QDockWidget.DockWidgetFloatable)
        self.setWindowTitle(_('Output Log'))
        # Not enabled until we have a way to make it configurable
        #self.setWindowFlags(Qt.Drawer)

        self.logte = ConsoleWidget(self)
        self.logte.closeRequested.connect(self.close)
        self.setWidget(self.logte)
        for name in ('setRepository', 'progressReceived'):
            setattr(self, name, getattr(self.logte, name))

        self.visibilityChanged.connect(
            lambda visible: visible and self.logte.setFocus())

    @pyqtSlot()
    def clear(self):
        self.logte.clear()

    @pyqtSlot(QString, QString)
    def output(self, msg, label):
        self.logte.appendLog(msg, label)

    @pyqtSlot()
    def beginSuppressPrompt(self):
        self.logte.suppressPrompt = True

    @pyqtSlot()
    def endSuppressPrompt(self):
        self.logte.suppressPrompt = False
        self.logte.openPrompt()

    def showEvent(self, event):
        self.visibilityChanged.emit(True)

    def setVisible(self, visible):
        super(LogDockWidget, self).setVisible(visible)
        if visible:
            self.raise_()

    def hideEvent(self, event):
        self.visibilityChanged.emit(False)

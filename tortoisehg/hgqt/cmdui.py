# cmdui.py - A widget to execute Mercurial command for TortoiseHg
#
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os, glob, shlex

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qsci import QsciScintilla

from mercurial import util

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _, localgettext
from tortoisehg.hgqt import qtlib, thread

local = localgettext()

def startProgress(topic, status):
    topic, item, pos, total, unit = topic, '...', status, None, ''
    return (topic, pos, item, unit, total)

def stopProgress(topic):
    topic, item, pos, total, unit = topic, '', None, None, ''
    return (topic, pos, item, unit, total)

class ProgressMonitor(QWidget):
    'Progress bar for use in workbench status bar'
    def __init__(self, topic, parent):
        super(ProgressMonitor, self).__init__(parent=parent)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(*(0,)*4)
        self.setLayout(hbox)
        self.idle = False

        self.pbar = QProgressBar()
        self.pbar.setTextVisible(False)
        self.pbar.setMinimum(0)
        hbox.addWidget(self.pbar)

        self.topic = QLabel(topic)
        hbox.addWidget(self.topic, 0)

        self.status = QLabel()
        hbox.addWidget(self.status, 1)

        self.pbar.setMaximum(100)
        self.pbar.reset()
        self.status.setText('')

    def clear(self):
        self.pbar.setMinimum(0)
        self.pbar.setMaximum(100)
        self.pbar.setValue(100)
        self.status.setText('')
        self.idle = True

    def setcounts(self, cur, max):
        self.pbar.setMaximum(max)
        self.pbar.setValue(cur)

    def unknown(self):
        self.pbar.setMinimum(0)
        self.pbar.setMaximum(0)


class ThgStatusBar(QStatusBar):
    def __init__(self, parent=None):
        QStatusBar.__init__(self, parent=parent)
        self.topics = {}
        self.lbl = QLabel()
        self.addWidget(self.lbl)

    @pyqtSlot(unicode)
    def showMessage(self, ustr):
        self.lbl.setText(ustr)

    def clear(self):
        keys = self.topics.keys()
        for key in keys:
            pm = self.topics[key]
            self.removeWidget(pm)
            del self.topics[key]

    @pyqtSlot(QString, object, QString, QString, object)
    def progress(self, topic, pos, item, unit, total, root=None):
        'Progress signal received from repowidget'
        # topic is current operation
        # pos is the current numeric position (revision, bytes)
        # item is a non-numeric marker of current position (current file)
        # unit is a string label
        # total is the highest expected pos
        #
        # All topics should be marked closed by setting pos to None
        if root:
            key = (root, topic)
        else:
            key = topic
        if pos is None or (not pos and not total):
            if key in self.topics:
                pm = self.topics[key]
                self.removeWidget(pm)
                del self.topics[key]
            return
        if key not in self.topics:
            pm = ProgressMonitor(topic, self)
            pm.setMaximumHeight(self.lbl.sizeHint().height())
            self.addWidget(pm)
            self.topics[key] = pm
        else:
            pm = self.topics[key]
        if total:
            fmt = '%s / %s ' % (unicode(pos), unicode(total))
            if unit:
                fmt += unit
            pm.status.setText(fmt)
            pm.setcounts(pos, total)
        else:
            if item:
                item = item[-30:]
            pm.status.setText('%s %s' % (unicode(pos), item))
            pm.unknown()


class Core(QObject):
    """Core functionality for running Mercurial command.
    Do not attempt to instantiate and use this directly.
    """

    commandStarted = pyqtSignal()
    commandFinished = pyqtSignal(int)
    commandCanceling = pyqtSignal()

    output = pyqtSignal(QString, QString)
    progress = pyqtSignal(QString, object, QString, QString, object)

    def __init__(self, useInternal, parent):
        super(Core, self).__init__()

        self.thread = None
        self.stbar = None
        self.queue = []
        self.display = None
        self.internallog = useInternal
        self.parent = parent
        if useInternal:
            self.output_text = LogWidget()

    ### Public Methods ###

    def run(self, cmdline, *cmdlines, **opts):
        '''Execute or queue Mercurial command'''
        self.display = opts.get('display')
        self.queue.append(cmdline)
        if len(cmdlines):
            self.queue.extend(cmdlines)
        if not self.is_running():
            self.run_next()

    def cancel(self):
        '''Cancel running Mercurial command'''
        if self.is_running():
            self.thread.abort()
            self.commandCanceling.emit()

    def set_stbar(self, stbar):
        self.stbar = stbar

    def is_running(self):
        return bool(self.thread and self.thread.isRunning())

    def get_rawoutput(self):
        if self.thread:
            return hglib.fromunicode(self.thread.rawoutput.join(''))
        else:
            return ''

    ### Private Method ###

    def run_next(self):
        try:
            cmdline = self.queue.pop(0)
            self.thread = thread.CmdThread(cmdline, self.display, self.parent)
        except IndexError:
            return False

        self.thread.started.connect(self.command_started)
        self.thread.commandFinished.connect(self.command_finished)

        self.thread.outputReceived.connect(self.output)
        self.thread.progressReceived.connect(self.progress)

        if self.internallog:
            self.thread.outputReceived.connect(self.output_text.appendLog)
        if self.stbar:
            self.thread.progressReceived.connect(self.stbar.progress)

        self.thread.start()
        return True

    def clear_output(self):
        if self.internallog:
            self.output_text.clear()

    ### Signal Handlers ###

    @pyqtSlot()
    def command_started(self):
        if self.stbar:
            self.stbar.showMessage(_('Running...'))

        self.commandStarted.emit()

    @pyqtSlot(int)
    def command_finished(self, ret):
        if self.stbar:
            if ret is None:
                self.stbar.clear()
                if self.thread.abortbyuser:
                    status = _('Terminated by user')
                else:
                    status = _('Terminated')
            else:
                status = _('Finished')
            self.stbar.showMessage(status)

        self.display = None
        if ret == 0 and self.run_next():
            return # run next command

        self.commandFinished.emit(ret)

    @pyqtSlot()
    def command_canceling(self):
        if self.stbar:
            self.stbar.showMessage(_('Canceling...'))
            self.stbar.clear()

        self.commandCanceling.emit()


class LogWidget(QsciScintilla):
    """Output log viewer"""
    def __init__(self, parent=None):
        super(LogWidget, self).__init__(parent)
        self.setReadOnly(True)
        self.setUtf8(True)
        self.setMarginWidth(1, 0)
        self._initfont()
        self._initmarkers()

    def _initfont(self):
        from mercurial import ui  # XXX workaround to pass fake ui obj
        tf = qtlib.getfont(ui.ui(), 'fontlog')
        tf.changed.connect(lambda f: self.setFont(f))
        self.setFont(tf.font())

    def _initmarkers(self):
        self._markers = {}
        for l in ('ui.error', 'control'):
            self._markers[l] = m = self.markerDefine(QsciScintilla.Background)
            c = QColor(qtlib.getbgcoloreffect(l))
            if c.isValid():
                self.setMarkerBackgroundColor(c, m)
            # NOTE: self.setMarkerForegroundColor() doesn't take effect,
            # because it's a *Background* marker.

    @pyqtSlot(unicode, str)
    def appendLog(self, msg, label):
        """Append log text to the last line; scrolls down to there"""
        self.append(msg)
        self._setmarker(xrange(self.lines() - unicode(msg).count('\n') - 1,
                               self.lines() - 1), label)
        self.setCursorPosition(self.lines() - 1, 0)

    def _setmarker(self, lines, label):
        for m in self._markersforlabel(label):
            for i in lines:
                self.markerAdd(i, m)

    def _markersforlabel(self, label):
        return iter(self._markers[l] for l in str(label).split()
                    if l in self._markers)

class _LogWidgetForConsole(LogWidget):
    """Wrapped LogWidget for ConsoleWidget"""
    returnPressed = pyqtSignal(unicode)

    _prompt = '% '

    def __init__(self, parent=None):
        super(_LogWidgetForConsole, self).__init__(parent)
        self._prompt_marker = self.markerDefine(QsciScintilla.Background)
        self.setMarkerBackgroundColor(QColor('#e8f3fe'), self._prompt_marker)
        self.cursorPositionChanged.connect(self._updatePrompt)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
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

    @pyqtSlot()
    def closePrompt(self):
        """Disable user input"""
        if self.commandText():
            self._setmarker((self.lines() - 1,), 'control')
        self.markerDelete(self.lines() - 1, self._prompt_marker)
        self._newline()
        self.setCursorPosition(self.lines() - 1, 0)
        self.setReadOnly(True)

    @pyqtSlot()
    def clearPrompt(self):
        """Clear prompt line"""
        line = self.lines() - 1
        if not (self.markersAtLine(line) & (1 << self._prompt_marker)):
            return
        self.markerDelete(line)
        self.setSelection(line, 0, line, self.lineLength(line))
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
        self.setCursorPosition(line, self.lineLength(line))

    def commandText(self):
        """Return the current command text"""
        l = self.lines() - 1
        if self.markersAtLine(l) & (1 << self._prompt_marker):
            return self.text(l)[len(self._prompt):]
        else:
            return ''

    def _newline(self):
        if self.lineLength(self.lines() - 1) > 0:
            self.append('\n')

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

    progressReceived = pyqtSignal(unicode, object, unicode, unicode,
                                  object, unicode)
    """Emitted when progress received

    Args: topic, pos, item, unit, total, reporoot
    """

    _cmdtable = _ConsoleCmdTable()

    # TODO: support arbitrary shell commands
    # TODO: command history and completion

    def __init__(self, parent=None):
        super(ConsoleWidget, self).__init__(parent)
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self._initlogwidget()
        self.setFocusProxy(self._logwidget)
        self.setRepository(None)
        self.openPrompt()

    def _initlogwidget(self):
        self._logwidget = _LogWidgetForConsole(self)
        self._logwidget.returnPressed.connect(self._runcommand)
        self.layout().addWidget(self._logwidget)

        # compatibility methods with LogWidget
        for name in ('openPrompt', 'closePrompt', 'clear'):
            setattr(self, name, getattr(self._logwidget, name))

    @util.propertycache
    def _cmdcore(self):
        cmdcore = Core(useInternal=False, parent=self)
        cmdcore.output.connect(self._logwidget.appendLog)
        cmdcore.commandStarted.connect(self.closePrompt)
        cmdcore.commandFinished.connect(self.openPrompt)
        cmdcore.progress.connect(self._emitProgress)
        return cmdcore

    @pyqtSlot(unicode, str)
    def appendLog(self, msg, label):
        """Append log text from another cmdui"""
        self._logwidget.clearPrompt()
        try:
            self._logwidget.appendLog(msg, label)
        finally:
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
            self.closePrompt()
            self._logwidget.appendLog(_('command not found: %s\n')
                                      % hglib.tounicode(cmd), 'ui.error')
            self.openPrompt()

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

    @_cmdtable
    def _cmd_hg(self, args):
        if self._repo:
            args = ['-R', self._repo.root] + args
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
    def _cmd_exit(self, args):
        self.clear()
        self.openPrompt()
        self.closeRequested.emit()


class Widget(QWidget):
    """An embeddable widget for running Mercurial command"""

    commandStarted = pyqtSignal()
    commandFinished = pyqtSignal(int)
    commandCanceling = pyqtSignal()

    output = pyqtSignal(QString, QString)
    progress = pyqtSignal(QString, object, QString, QString, object)
    makeLogVisible = pyqtSignal(bool)

    def __init__(self, useInternal=True, parent=None):
        super(Widget, self).__init__()

        self.internallog = useInternal
        self.core = Core(useInternal, parent)
        self.core.commandStarted.connect(self.commandStarted)
        self.core.commandFinished.connect(self.command_finished)
        self.core.commandCanceling.connect(self.commandCanceling)
        self.core.output.connect(self.output)
        self.core.progress.connect(self.progress)
        if not useInternal:
            return

        vbox = QVBoxLayout()
        vbox.setSpacing(4)
        vbox.setContentsMargins(*(1,)*4)

        # command output area
        self.core.output_text.setHidden(True)
        vbox.addWidget(self.core.output_text, 1)

        ## status and progress labels
        self.stbar = ThgStatusBar()
        self.stbar.setSizeGripEnabled(False)
        self.core.set_stbar(self.stbar)
        vbox.addWidget(self.stbar)

        # widget setting
        self.setLayout(vbox)

    ### Public Methods ###

    def run(self, cmdline, *args, **opts):
        self.core.run(cmdline, *args, **opts)

    def cancel(self):
        self.core.cancel()

    def show_output(self, visible):
        if self.internallog:
            self.core.output_text.setShown(visible)

    def is_show_output(self):
        if self.internallog:
            return self.core.output_text.isVisible()
        else:
            return False

    ### Signal Handler ###

    @pyqtSlot(int)
    def command_finished(self, ret):
        if ret == -1:
            self.makeLogVisible.emit(True)
            self.show_output(True)
        self.commandFinished.emit(ret)

class Dialog(QDialog):
    """A dialog for running random Mercurial command"""

    commandStarted = pyqtSignal()
    commandFinished = pyqtSignal(int)
    commandCanceling = pyqtSignal()

    def __init__(self, cmdline, parent=None, finishfunc=None):
        super(Dialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.finishfunc = finishfunc

        self.core = Core(True, self)
        self.core.commandStarted.connect(self.commandStarted)
        self.core.commandFinished.connect(self.command_finished)
        self.core.commandCanceling.connect(self.commandCanceling)

        vbox = QVBoxLayout()
        vbox.setSpacing(4)
        vbox.setContentsMargins(*(1,)*4)

        # command output area
        vbox.addWidget(self.core.output_text, 1)

        ## status and progress labels
        self.stbar = ThgStatusBar()
        self.stbar.setSizeGripEnabled(False)
        self.core.set_stbar(self.stbar)
        vbox.addWidget(self.stbar)

        # bottom buttons
        buttons = QDialogButtonBox()
        self.cancel_btn = buttons.addButton(QDialogButtonBox.Cancel)
        self.cancel_btn.clicked.connect(self.cancel_clicked)
        self.close_btn = buttons.addButton(QDialogButtonBox.Close)
        self.close_btn.clicked.connect(self.reject)
        self.detail_btn = buttons.addButton(_('Detail'),
                                            QDialogButtonBox.ResetRole)
        self.detail_btn.setAutoDefault(False)
        self.detail_btn.setCheckable(True)
        self.detail_btn.setChecked(True)
        self.detail_btn.toggled.connect(self.show_output)
        vbox.addWidget(buttons)

        self.setLayout(vbox)
        self.setWindowTitle(_('TortoiseHg Command Dialog'))
        self.resize(540, 420)

        # prepare to show
        self.close_btn.setHidden(True)

        # start command
        self.core.run(cmdline)

    def show_output(self, visible):
        """show/hide command output"""
        self.core.output_text.setVisible(visible)
        self.detail_btn.setChecked(visible)

        # workaround to adjust only window height
        self.setMinimumWidth(self.width())
        self.adjustSize()
        self.setMinimumWidth(0)

    ### Private Method ###

    def reject(self):
        if self.core.is_running():
            ret = QMessageBox.question(self, _('Confirm Exit'), _('Mercurial'
                        ' command is still running.\nAre you sure you want'
                        ' to terminate?'), QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No)
            if ret == QMessageBox.Yes:
                self.cancel_clicked()

            # don't close dialog
            return

        # close dialog
        if self.core.thread.ret == 0:
            self.accept()  # means command successfully finished
        else:
            super(Dialog, self).reject()

    ### Signal Handlers ###

    @pyqtSlot()
    def cancel_clicked(self):
        self.core.cancel()

    @pyqtSlot(int)
    def command_finished(self, ret):
        self.cancel_btn.setHidden(True)
        self.close_btn.setShown(True)
        self.close_btn.setFocus()
        if self.finishfunc:
            self.finishfunc()

    @pyqtSlot()
    def command_canceling(self):
        self.cancel_btn.setDisabled(True)

class Runner(QObject):
    """A component for running Mercurial command without UI

    This command runner doesn't show any UI element unless it gets a warning
    or an error while the command is running.  Once an error or a warning is
    received, it pops-up a small dialog which contains the command log.
    """

    commandStarted = pyqtSignal()
    commandFinished = pyqtSignal(int)
    commandCanceling = pyqtSignal()

    output = pyqtSignal(QString, QString)
    progress = pyqtSignal(QString, object, QString, QString, object)
    makeLogVisible = pyqtSignal(bool)

    def __init__(self, title=_('TortoiseHg'), useInternal=True, parent=None):
        super(Runner, self).__init__()

        self.internallog = useInternal
        self.title = title
        self.parent = parent

        self.core = Core(useInternal, parent)
        self.core.commandStarted.connect(self.commandStarted)
        self.core.commandFinished.connect(self.command_finished)
        self.core.commandCanceling.connect(self.commandCanceling)

        self.core.output.connect(self.output)
        self.core.progress.connect(self.progress)

        if useInternal:
            self.core.output_text.setMinimumSize(460, 320)

    ### Public Methods ###

    def run(self, cmdline, *args, **opts):
        self.core.run(cmdline, *args, **opts)

    def cancel(self):
        self.core.cancel()

    def show_output(self, visible=True):
        if not self.internallog:
            return
        if not hasattr(self, 'dlg'):
            self.dlg = QDialog(self.parent)
            self.dlg.setWindowTitle(self.title)
            flags = self.dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint
            self.dlg.setWindowFlags(flags)
            box = QVBoxLayout()
            box.setContentsMargins(*(0,)*4)
            box.addWidget(self.core.output_text)
            self.dlg.setLayout(box)
        self.dlg.setVisible(visible)

    ### Signal Handler ###

    @pyqtSlot(int)
    def command_finished(self, ret):
        if ret != 0:
            self.makeLogVisible.emit(True)
            self.show_output()
        self.commandFinished.emit(ret)

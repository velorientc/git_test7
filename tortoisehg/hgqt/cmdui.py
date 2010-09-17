# cmdui.py - A widget to execute Mercurial command for TortoiseHg
#
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

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
        # All topics should be marked closed by setting pos to None

        if not topic:
            # special progress report, close all pbars for repo
            for key in self.topics:
                if root is None or key[0] == root:
                    pm = self.topics[key]
                    self.removeWidget(pm)
                    del self.topics[key]
            return

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
            fmt = '%s / %s ' % (str(pos), str(total))
            if unit:
                fmt += unit
            pm.status.setText(fmt)
            pm.setcounts(pos, total)
        else:
            if item:
                item = item[-30:]
            pm.status.setText('%s %s' % (str(pos), item))
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
            self.output_text = QPlainTextEdit()
            self.output_text.setReadOnly(True)
            self.output_text.setMaximumBlockCount(1024)
            self.output_text.setWordWrapMode(QTextOption.NoWrap)

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
            self.thread.outputReceived.connect(self.output_received)
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

        # Emit 'close all progress bars' signal
        self.progress.emit('', None, '', '', None)
        self.commandFinished.emit(ret)

    @pyqtSlot()
    def command_canceling(self):
        if self.stbar:
            self.stbar.showMessage(_('Canceling...'))
            self.stbar.clear()

        self.commandCanceling.emit()

    @pyqtSlot(QString, QString)
    def output_received(self, msg, label):
        msg = Qt.escape(msg)
        style = qtlib.geteffect(label)
        msg = msg.replace('\n', '<br />')
        cursor = self.output_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml('<font style="%s">%s</font>' % (style, msg))
        max = self.output_text.verticalScrollBar().maximum()
        self.output_text.verticalScrollBar().setSliderPosition(max)


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

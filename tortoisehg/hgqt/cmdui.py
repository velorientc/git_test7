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

class ProgressMonitor(QWidget):

    def __init__(self):
        super(ProgressMonitor, self).__init__()

        # main layout box
        vbox = QVBoxLayout()
        vbox.setContentsMargins(*(0,)*4)
        self.setLayout(vbox)

        ## status layout box
        hbox = QHBoxLayout()
        hbox.setContentsMargins(*(0,)*4)
        vbox.addLayout(hbox)

        self.status_label = QLabel()
        hbox.addWidget(self.status_label, 1)

        self.prog_label = QLabel()
        hbox.addWidget(self.prog_label, 0, Qt.AlignRight)

        ## progressbar
        self.pbar = QProgressBar()
        self.pbar.setTextVisible(False)
        self.pbar.setMinimum(0)
        vbox.addWidget(self.pbar)

        # prepare to show
        self.clear_progress()

    ### Public Methods ###

    def clear_progress(self):
        self.pbar.setMaximum(100)
        self.pbar.reset()
        self.status_label.setText('')
        self.prog_label.setText('')
        self.inprogress = False

    def fillup_progress(self):
        """stick progress to full"""
        self.clear_progress()
        self.pbar.setValue(self.pbar.maximum())

    def unknown_progress(self):
        self.pbar.setMinimum(0)
        self.pbar.setMaximum(0)

    def set_text(self, text):
        self.status_label.setText(text)

class Core(QObject):
    """Core functionality for running Mercurial command.
    Do not attempt to instantiate and use this directly.
    """

    commandStarted = pyqtSignal()
    commandFinished = pyqtSignal(thread.DataWrapper)
    commandCanceling = pyqtSignal()
    progress = pyqtSignal(thread.DataWrapper)

    def __init__(self, logwidget=None):
        super(Core, self).__init__()

        self.thread = None
        self.output_text = QTextBrowser()
        self.output_text.document().setDefaultStyleSheet(qtlib.thgstylesheet)
        self.pmon = None
        self.queue = []
        self.log = logwidget

    ### Public Methods ###

    def run(self, cmdline, *cmdlines):
        '''Execute or queue Mercurial command'''
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

    def set_pmon(self, pmon):
        self.pmon = pmon

    def is_running(self):
        return bool(self.thread and self.thread.isRunning())

    ### Private Method ###

    def run_next(self):
        try:
            cmdline = self.queue.pop(0)
            self.thread = thread.CmdThread(cmdline)
        except IndexError:
            return False

        self.thread.started.connect(self.command_started)
        self.thread.commandFinished.connect(self.command_finished)
        self.thread.outputReceived.connect(self.output_received)
        self.thread.errorReceived.connect(self.error_received)
        if self.log:
            self.thread.progressReceived.connect(self.fwdprogress)
        elif self.pmon:
            self.thread.progressReceived.connect(self.progress_received)
        self.thread.start()

        return True

    def append_output(self, msg, style=''):
        msg = msg.replace('\n', '<br />')
        self.output_text.insertHtml('<font style="%s">%s</font>' % (style, msg))
        max = self.output_text.verticalScrollBar().maximum()
        self.output_text.verticalScrollBar().setSliderPosition(max)

    def clear_output(self):
        self.output_text.clear()

    ### Signal Handlers ###

    def command_started(self):
        if self.pmon:
            self.pmon.set_text(_('Running...'))
            self.pmon.unknown_progress()

        self.commandStarted.emit()

    def command_finished(self, wrapper):
        ret = wrapper.data

        if self.pmon:
            if ret is None:
                self.pmon.clear_progress()
            if self.pmon.pbar.maximum() == 0:  # busy indicator
                if ret == 0:  # finished successfully
                    self.pmon.fillup_progress()
                else:
                    self.pmon.clear_progress()
            if ret is None:
                if self.thread.abortbyuser:
                    status = _('Terminated by user')
                else:
                    status = _('Terminated')
            else:
                status = _('Finished')
            self.pmon.set_text(status)

        if ret == 0 and self.run_next():
            return # run next command

        self.commandFinished.emit(wrapper)

    def command_canceling(self):
        if self.pmon:
            self.pmon.set_text(_('Canceling...'))
            self.pmon.unknown_progress()

        self.commandCanceling.emit()

    def output_received(self, wrapper):
        msg, label = wrapper.data
        msg = hglib.tounicode(msg)
        msg = Qt.escape(msg)
        style = qtlib.geteffect(label)
        if self.log:
            self.log.logMessage(msg, style)
        else:
            self.append_output(msg, style)

    def error_received(self, wrapper):
        msg, label = wrapper.data
        msg = hglib.tounicode(msg)
        msg = Qt.escape(msg)
        style = qtlib.geteffect(label)
        if self.log:
            self.log.logMessage(msg, style)
        else:
            self.append_output(msg, style)

    def fwdprogress(self, wrapper):
        topic, item, pos, total, unit = wrapper.data
        if self.thread.isFinished():
            self.progress.emit(thread.DataWrapper((topic, None, '', '', None)))
        else:
            self.progress.emit(wrapper)

    def progress_received(self, wrapper):
        if self.thread.isFinished():
            self.pmon.clear_progress()
            return

        counting = False
        topic, item, pos, total, unit = wrapper.data
        if pos is None:
            self.pmon.clear_progress()
            return
        if total is None:
            count = '%d' % pos
            counting = True
        else:
            self.pmon.pbar.setMaximum(total)
            self.pmon.pbar.setValue(pos)
            count = '%d / %d' % (pos, total)
        if unit:
            count += ' ' + unit
        self.pmon.prog_label.setText(hglib.tounicode(count))
        if item:
            status = '%s: %s' % (topic, item)
        else:
            status = local._('Status: %s') % topic
        self.pmon.status_label.setText(hglib.tounicode(status))
        self.pmon.inprogress = True

        if not self.pmon.inprogress or counting:
            # use indeterminate mode
            self.pmon.pbar.setMinimum(0)

class Widget(QWidget):
    """An embeddable widget for running Mercurial command"""

    commandStarted = pyqtSignal()
    commandFinished = pyqtSignal(thread.DataWrapper)
    commandCanceling = pyqtSignal()

    def __init__(self, logwidget=None):
        super(Widget, self).__init__()

        self.core = Core(logwidget)
        self.core.commandStarted.connect(lambda: self.commandStarted.emit())
        self.core.commandFinished.connect(lambda w: self.commandFinished.emit(w))
        self.core.commandCanceling.connect(lambda: self.commandCanceling.emit())
        if logwidget:
            self.core.progress.connect(logwidget.progress)
            return

        # main layout grid
        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setContentsMargins(*(1,)*4)

        ## status and progress labels
        self.pmon = ProgressMonitor()
        self.core.set_pmon(self.pmon)
        grid.addWidget(self.pmon, 0, 0)

        # command output area
        grid.addWidget(self.core.output_text, 1, 0, 5, 0)
        grid.setRowStretch(1, 1)

        # widget setting
        self.setLayout(grid)

        # prepare to show
        self.core.output_text.setHidden(True)

    ### Public Methods ###

    def run(self, cmdline, *args):
        self.core.run(cmdline, *args)

    def cancel(self):
        self.core.cancel()

    def show_output(self, visible):
        if self.core.log:
            return
        self.core.output_text.setShown(visible)

    def is_show_output(self):
        return self.core.output_text.isVisible()

class Dialog(QDialog):
    """A dialog for running random Mercurial command"""

    commandStarted = pyqtSignal()
    commandFinished = pyqtSignal(thread.DataWrapper)
    commandCanceling = pyqtSignal()

    def __init__(self, cmdline, parent=None, finishfunc=None):
        super(Dialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.finishfunc = finishfunc

        self.core = Core()
        self.core.commandFinished.connect(self.command_finished)
        self.core.commandCanceling.connect(lambda: self.commandCanceling.emit())

        # main layout grid
        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setContentsMargins(*(7,)*4)

        ## status and progress labels
        self.pmon = ProgressMonitor()
        self.core.set_pmon(self.pmon)
        grid.addWidget(self.pmon, 0, 0)

        # command output area
        grid.addWidget(self.core.output_text, 1, 0, 5, 0)
        grid.setRowStretch(1, 1)

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
        grid.addWidget(buttons, 7, 0)

        self.setLayout(grid)
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

    def cancel_clicked(self):
        self.core.cancel()

    def command_finished(self, wrapper):
        self.cancel_btn.setHidden(True)
        self.close_btn.setShown(True)
        self.close_btn.setFocus()
        if self.finishfunc:
            self.finishfunc()

    def command_canceling(self):
        self.cancel_btn.setDisabled(True)

class Runner(QObject):
    """A component for running Mercurial command without UI

    This command runner doesn't show any UI element unless it gets a warning
    or an error while the command is running.  Once an error or a warning is
    received, it pops-up a small dialog which contains the command log.
    """

    commandStarted = pyqtSignal()
    commandFinished = pyqtSignal(thread.DataWrapper)
    commandCanceling = pyqtSignal()

    def __init__(self, title=_('TortoiseHg'), parent=None):
        super(Runner, self).__init__()

        self.title = title
        self.parent = parent

        self.core = Core()
        self.core.commandStarted.connect(lambda: self.commandStarted.emit())
        self.core.commandFinished.connect(self.command_finished)
        self.core.commandCanceling.connect(lambda: self.commandCanceling.emit())

        self.core.output_text.setMinimumSize(460, 320)

    ### Public Methods ###

    def run(self, cmdline, *args):
        self.core.run(cmdline, *args)

    def cancel(self):
        self.core.cancel()

    def show_output(self, visible=True):
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

    def command_finished(self, wrapper):
        if wrapper.data != 0:
            self.show_output()
        self.commandFinished.emit(wrapper)

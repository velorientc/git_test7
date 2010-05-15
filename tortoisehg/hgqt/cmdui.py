# cmdui.py - A widget to execute Mercurial command for TortoiseHg
#
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import Qt, QObject, pyqtSignal
from PyQt4.QtGui import QDialog, QDialogButtonBox, QLabel, QProgressBar
from PyQt4.QtGui import QTextBrowser, QHBoxLayout, QGridLayout, QMessageBox
from PyQt4.QtGui import QWidget, QVBoxLayout

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

    def __init__(self):
        super(Core, self).__init__()

        self.thread = None
        self.output_text = QTextBrowser()
        self.output_text.document().setDefaultStyleSheet(qtlib.thgstylesheet)
        self.pmon = None

    ### Public Methods ###

    def run(self, cmdline):
        '''Execute Mercurial command'''
        self.thread = thread.CmdThread(cmdline)
        self.thread.started.connect(self.command_started)
        self.thread.commandFinished.connect(self.command_finished)
        self.thread.outputReceived.connect(self.output_received)
        self.thread.errorReceived.connect(self.error_received)
        if hasattr(self, 'pmon'):
            self.thread.progressReceived.connect(self.progress_received)
        self.thread.start()

    def cancel(self):
        '''Cancel running Mercurial command'''
        self.thread.abort()
        self.commandCanceling.emit()

    def set_pmon(self, pmon):
        self.pmon = pmon

    def is_running(self):
        return self.thread.isRunning()

    ### Private Method ###

    def append_output(self, msg, style=''):
        msg = msg.replace('\n', '<br />')
        self.output_text.insertHtml('<font style="%s">%s</font>' % (style, msg))
        max = self.output_text.verticalScrollBar().maximum()
        self.output_text.verticalScrollBar().setSliderPosition(max)

    ### Signal Handlers ###

    def command_started(self):
        if hasattr(self, 'pmon'):
            self.pmon.set_text(_('Running...'))
            self.pmon.unknown_progress()

        self.commandStarted.emit()

    def command_finished(self, wrapper):
        if hasattr(self, 'pmon'):
            ret = wrapper.data
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

        self.commandFinished.emit(wrapper)

    def command_canceling(self):
        if hasattr(self, 'pmon'):
            self.pmon.set_text(_('Canceling...'))
            self.pmon.unknown_progress()

        self.commandCanceling.emit()

    def output_received(self, wrapper):
        msg, label = wrapper.data
        msg = hglib.tounicode(msg)
        msg = Qt.escape(msg)
        style = qtlib.geteffect(label)
        self.append_output(msg, style)

    def error_received(self, wrapper):
        msg, label = wrapper.data
        msg = hglib.tounicode(msg)
        msg = Qt.escape(msg)
        style = qtlib.geteffect(label)
        self.append_output(msg, style)

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

    def __init__(self):
        super(Widget, self).__init__()

        self.core = Core()
        self.core.commandStarted.connect(lambda: self.commandStarted.emit())
        self.core.commandFinished.connect(lambda w: self.commandFinished.emit(w))
        self.core.commandCanceling.connect(lambda: self.commandCanceling.emit())

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

    def run(self, cmdline):
        self.core.run(cmdline)

    def cancel(self):
        self.core.cancel()

    def show_output(self, visible):
        self.core.output_text.setShown(visible)

    def is_show_output(self):
        return self.core.output_text.isVisible()

class Dialog(QDialog):
    """A dialog for running random Mercurial command"""

    commandStarted = pyqtSignal()
    commandFinished = pyqtSignal(thread.DataWrapper)
    commandCanceling = pyqtSignal()

    def __init__(self, cmdline, parent=None):
        super(Dialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

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

    def command_canceling(self):
        self.cancel_btn.setDisabled(True)

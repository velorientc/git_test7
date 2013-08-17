# cmdui.py - A widget to execute Mercurial command for TortoiseHg
#
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qsci import QsciScintilla

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _, localgettext
from tortoisehg.hgqt import qtlib, qscilib

from tortoisehg.hgqt.cmdcore import Core

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
        super(ProgressMonitor, self).__init__(parent)

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
        # cur and max may exceed INT_MAX, which confuses QProgressBar
        assert max != 0
        self.pbar.setMaximum(100)
        self.pbar.setValue(int(cur * 100 / max))

    def unknown(self):
        self.pbar.setMinimum(0)
        self.pbar.setMaximum(0)


class ThgStatusBar(QStatusBar):
    linkActivated = pyqtSignal(QString)

    def __init__(self, parent=None):
        QStatusBar.__init__(self, parent)
        self.topics = {}
        self.lbl = QLabel()
        self.lbl.linkActivated.connect(self.linkActivated)
        self.addWidget(self.lbl)
        self.setStyleSheet('QStatusBar::item { border: none }')

    @pyqtSlot(unicode)
    def showMessage(self, ustr, error=False):
        self.lbl.setText(ustr)
        if error:
            self.lbl.setStyleSheet('QLabel { color: red }')
        else:
            self.lbl.setStyleSheet('')

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


class LogWidget(QsciScintilla):
    """Output log viewer"""

    def __init__(self, parent=None):
        super(LogWidget, self).__init__(parent)
        self.setReadOnly(True)
        self.setUtf8(True)
        self.setMarginWidth(1, 0)
        self.setWrapMode(QsciScintilla.WrapCharacter)
        self._initfont()
        self._initmarkers()
        qscilib.unbindConflictedKeys(self)

    def _initfont(self):
        tf = qtlib.getfont('fontoutputlog')
        tf.changed.connect(self.forwardFont)
        self.setFont(tf.font())

    @pyqtSlot(QFont)
    def forwardFont(self, font):
        self.setFont(font)

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


class Widget(QWidget):
    """An embeddable widget for running Mercurial command"""

    commandStarted = pyqtSignal()
    commandFinished = pyqtSignal(int)
    commandCanceling = pyqtSignal()

    output = pyqtSignal(QString, QString)
    progress = pyqtSignal(QString, object, QString, QString, object)
    makeLogVisible = pyqtSignal(bool)

    def __init__(self, logWindow, statusBar, parent):
        super(Widget, self).__init__(parent)

        self.core = Core(logWindow, self)
        self.core.commandStarted.connect(self.commandStarted)
        self.core.commandFinished.connect(self.onCommandFinished)
        self.core.commandCanceling.connect(self.commandCanceling)
        self.core.output.connect(self.output)
        self.core.progress.connect(self.progress)
        if not logWindow:
            return

        vbox = QVBoxLayout()
        vbox.setSpacing(4)
        vbox.setContentsMargins(*(1,)*4)
        self.setLayout(vbox)

        # command output area
        self.core.outputLog.setHidden(True)
        self.layout().addWidget(self.core.outputLog, 1)

        if statusBar:
            ## status and progress labels
            self.stbar = ThgStatusBar()
            self.stbar.setSizeGripEnabled(False)
            self.core.setStbar(self.stbar)
            self.layout().addWidget(self.stbar)

    ### Public Methods ###

    def run(self, cmdline, *args, **opts):
        self.core.run(cmdline, *args, **opts)

    def cancel(self):
        self.core.cancel()

    def setShowOutput(self, visible):
        if hasattr(self.core, 'outputLog'):
            self.core.outputLog.setShown(visible)

    def outputShown(self):
        if hasattr(self.core, 'outputLog'):
            return self.core.outputLog.isVisible()
        else:
            return False

    ### Signal Handler ###

    @pyqtSlot(int)
    def onCommandFinished(self, ret):
        if ret == -1:
            self.makeLogVisible.emit(True)
            self.setShowOutput(True)
        self.commandFinished.emit(ret)

class Dialog(QDialog):
    """A dialog for running random Mercurial command"""

    def __init__(self, cmdline, parent=None):
        super(Dialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.core = Core(True, self)
        self.core.commandFinished.connect(self.onCommandFinished)

        vbox = QVBoxLayout()
        vbox.setSpacing(4)
        vbox.setContentsMargins(5, 5, 5, 5)

        # command output area
        vbox.addWidget(self.core.outputLog, 1)

        ## status and progress labels
        self.stbar = ThgStatusBar()
        self.stbar.setSizeGripEnabled(False)
        self.core.setStbar(self.stbar)
        vbox.addWidget(self.stbar)

        # bottom buttons
        buttons = QDialogButtonBox()
        self.cancelBtn = buttons.addButton(QDialogButtonBox.Cancel)
        self.cancelBtn.clicked.connect(self.core.cancel)
        self.core.commandCanceling.connect(self.commandCanceling)

        self.closeBtn = buttons.addButton(QDialogButtonBox.Close)
        self.closeBtn.setHidden(True)
        self.closeBtn.clicked.connect(self.reject)

        self.detailBtn = buttons.addButton(_('Detail'),
                                            QDialogButtonBox.ResetRole)
        self.detailBtn.setAutoDefault(False)
        self.detailBtn.setCheckable(True)
        self.detailBtn.setChecked(True)
        self.detailBtn.toggled.connect(self.setShowOutput)
        vbox.addWidget(buttons)

        self.setLayout(vbox)
        self.setWindowTitle(_('TortoiseHg Command Dialog'))
        self.resize(540, 420)

        # start command
        self.core.run(cmdline)

    def setShowOutput(self, visible):
        """show/hide command output"""
        self.core.outputLog.setVisible(visible)
        self.detailBtn.setChecked(visible)

        # workaround to adjust only window height
        self.setMinimumWidth(self.width())
        self.adjustSize()
        self.setMinimumWidth(0)

    ### Private Method ###

    def reject(self):
        if self.core.running():
            ret = QMessageBox.question(self, _('Confirm Exit'),
                        _('Mercurial command is still running.\n'
                          'Are you sure you want to terminate?'),
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No)
            if ret == QMessageBox.Yes:
                self.core.cancel()
            # don't close dialog
            return

        # close dialog
        if self.returnCode == 0:
            self.accept()  # means command successfully finished
        else:
            super(Dialog, self).reject()

    @pyqtSlot()
    def commandCanceling(self):
        self.cancelBtn.setDisabled(True)

    @pyqtSlot(int)
    def onCommandFinished(self, ret):
        self.returnCode = ret
        self.cancelBtn.setHidden(True)
        self.closeBtn.setShown(True)
        self.closeBtn.setFocus()

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

    def __init__(self, logWindow, parent):
        super(Runner, self).__init__(parent)
        self.title = _('TortoiseHg')
        self.core = Core(logWindow, parent)
        self.core.commandStarted.connect(self.commandStarted)
        self.core.commandFinished.connect(self.onCommandFinished)
        self.core.commandCanceling.connect(self.commandCanceling)
        self.core.output.connect(self.output)
        self.core.progress.connect(self.progress)

    ### Public Methods ###

    def setTitle(self, title):
        self.title = title

    def run(self, cmdline, *args, **opts):
        self.core.run(cmdline, *args, **opts)

    def running(self):
        return self.core.running()

    def cancel(self):
        self.core.cancel()

    def outputShown(self):
        if hasattr(self, 'dlg'):
            return self.dlg.isVisible()
        else:
            return False

    def setShowOutput(self, visible=True):
        if not hasattr(self.core, 'outputLog'):
            return
        if not hasattr(self, 'dlg'):
            self.dlg = dlg = QDialog(self.parent())
            dlg.setWindowTitle(self.title)
            dlg.setWindowFlags(Qt.Dialog)
            dlg.setLayout(QVBoxLayout())
            dlg.layout().addWidget(self.core.outputLog)
            self.core.outputLog.setMinimumSize(460, 320)
        self.dlg.setVisible(visible)

    ### Signal Handler ###

    @pyqtSlot(int)
    def onCommandFinished(self, ret):
        if ret != 0:
            self.makeLogVisible.emit(True)
            self.setShowOutput(True)
        self.commandFinished.emit(ret)

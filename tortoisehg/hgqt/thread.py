# thread.py - A seprated thread to run Mercurial command
#
# Copyright 2009 Steve Borho <steve@borho.org>
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import Queue
import time
import urllib2

from PyQt4.QtCore import SIGNAL, pyqtSignal, QObject, QThread
from PyQt4.QtGui import QMessageBox, QInputDialog, QLineEdit

from mercurial import ui, util, error, dispatch

from tortoisehg.util import thread2, hglib
from tortoisehg.hgqt.i18n import _, localgettext

local = localgettext()

SIG_OUTPUT = SIGNAL('output(PyQt_PyObject)')
SIG_ERROR = SIGNAL('error(PyQt_PyObject)')
SIG_INTERACT = SIGNAL('interact(PyQt_PyObject)')
SIG_PROGRESS = SIGNAL('progress(PyQt_PyObject)')

class QtUi(ui.ui):
    def __init__(self, src=None, responseq=None):
        super(QtUi, self).__init__(src)

        if src:
            self.sig = src.sig
            self.responseq = src.responseq
        else:
            self.sig = QObject() # dummy object to emit signals
            self.responseq = responseq

        self.setconfig('ui', 'interactive', 'on')
        self.setconfig('progress', 'disable', 'True')

    def write(self, *args, **opts):
        if self._buffers:
            self._buffers[-1].extend([str(a) for a in args])
        else:
            for a in args:
                data = DataWrapper((str(a), opts.get('label', '')))
                self.sig.emit(SIG_OUTPUT, data)

    def write_err(self, *args, **opts):
        for a in args:
            data = DataWrapper(str(a))
            self.sig.emit(SIG_ERROR, data)

    def label(self, msg, label):
        return msg

    def flush(self):
        pass

    def prompt(self, msg, choices=None, default='y'):
        if not self.interactive(): return default
        try:
            # emit SIG_INTERACT signal
            data = DataWrapper((msg, False, choices, None))
            self.sig.emit(SIG_INTERACT, data)
            # await response
            r = self.responseq.get(True)
            if r is None:
                raise EOFError
            if not r:
                return default
            if choices:
                # return char for Mercurial 1.3
                choice = choices[r]
                return choice[choice.index('&')+1].lower()
            return r
        except EOFError:
            raise util.Abort(local._('response expected'))

    def promptchoice(self, msg, choices, default=0):
        if not self.interactive(): return default
        try:
            # emit SIG_INTERACT signal
            data = DataWrapper((msg, False, choices, default))
            self.sig.emit(SIG_INTERACT, data)
            # await response
            r = self.responseq.get(True)
            if r is None:
                raise EOFError
            return r
        except EOFError:
            raise util.Abort(local._('response expected'))

    def getpass(self, prompt=_('password: '), default=None):
        # emit SIG_INTERACT signal
        data = DataWrapper((prompt, True, None, default))
        self.sig.emit(SIG_INTERACT, data)
        # await response
        r = self.responseq.get(True)
        if r is None:
            raise util.Abort(local._('response expected'))
        return r

    def progress(self, topic, pos, item='', unit='', total=None):
        data = DataWrapper((topic, item, pos, total, unit))
        self.sig.emit(SIG_PROGRESS, data)

class DataWrapper(QObject):
    def __init__(self, data):
        super(DataWrapper, self).__init__(None)
        self.data = data

class CmdThread(QThread):
    """Run an Mercurial command in a background thread, implies output
    is being sent to a rendered text buffer interactively and requests
    for feedback from Mercurial can be handled by the user via dialog
    windows.
    """
    # (msg=str, label=str) [wrapped]
    outputReceived = pyqtSignal(DataWrapper)

    # msg=str [wrapped]
    errorReceived = pyqtSignal(DataWrapper)

    # (msg=str, password=bool, choices=tuple, default=str) [wrapped]
    # password: whether should be masked by asterisk chars
    # choices:  tuple of choice strings
    interactReceived = pyqtSignal(DataWrapper)

    # (topic=str, item=str, pos=int, total=int, unit=str) [wrapped]
    progressReceived = pyqtSignal(DataWrapper)

    # result=int or None [wrapped]
    # result: None - command is incomplete, possibly exited with exception
    #         0 - command is finished successfully
    #         others - return code of command
    commandFinished = pyqtSignal(DataWrapper)

    def __init__(self, cmdline, parent=None):
        super(QThread, self).__init__(None)

        self.cmdline = cmdline
        self.parent = parent
        self.ret = None
        self.abortbyuser = False
        self.responseq = Queue.Queue()
        self.ui = QtUi(responseq=self.responseq)

        # Re-emit all ui.sig's signals to CmdThread (self).
        # QSignalMapper doesn't help for this since our SIGNAL
        # parameters contain 'PyQt_PyObject' types.
        for name, sig in ((SIG_OUTPUT, self.outputReceived),
                          (SIG_ERROR, self.errorReceived),
                          (SIG_INTERACT, self.interactReceived),
                          (SIG_PROGRESS, self.progressReceived)):
            def repeater(sig): # hide 'sig' local variable name
                return lambda data: sig.emit(data)
            self.connect(self.ui.sig, name, repeater(sig))

        self.finished.connect(self.thread_finished)
        self.interactReceived.connect(self.interact_handler)

    def abort(self):
        if self.isRunning() and hasattr(self, 'thread_id'):
            self.abortbyuser = True
            thread2._async_raise(self.thread_id, KeyboardInterrupt)

    def thread_finished(self):
        self.commandFinished.emit(DataWrapper(self.ret))

    def interact_handler(self, wrapper):
        prompt, password, choices, default = wrapper.data
        prompt = hglib.tounicode(prompt)
        if choices:
            dlg = QMessageBox(QMessageBox.Question,
                        _('TortoiseHg Prompt'), prompt,
                        QMessageBox.Yes | QMessageBox.Cancel, self.parent)
            dlg.setDefaultButton(QMessageBox.Cancel)
            rmap = {}
            for index, choice in enumerate(choices):
                button = dlg.addButton(hglib.tounicode(choice),
                                       QMessageBox.ActionRole)
                rmap[id(button)] = index
            dlg.exec_()
            button = dlg.clickedButton()
            if button is 0:
                result = default
            else:
                result = rmap[id(button)]
            self.responseq.put(result)
        else:
            mode = password and QLineEdit.Password \
                             or QLineEdit.Normal
            text, ok = QInputDialog().getText(self.parent,
                            _('TortoiseHg Prompt'), prompt, mode)
            self.responseq.put(ok and text or None)

    def run(self):
        # save thread id in order to terminate by KeyboardInterrupt
        self.thread_id = int(QThread.currentThreadId())

        try:
            for k, v in self.ui.configitems('defaults'):
                self.ui.setconfig('defaults', k, '')
            self.ret = dispatch._dispatch(self.ui, self.cmdline) or 0
        except util.Abort, e:
            self.ui.write_err(local._('abort: ') + str(e) + '\n')
        except (error.RepoError, urllib2.HTTPError), e:
            self.ui.write_err(str(e) + '\n')
        except (Exception, OSError, IOError), e:
            self.ui.write_err(str(e) + '\n')
        except KeyboardInterrupt:
            pass

        if self.ret is None:
            if self.abortbyuser:
                msg = _('[command terminated by user %s]')
            else:
                msg = _('[command interrupted %s]')
        elif self.ret:
            msg = _('[command returned code %d %%s]') % int(ret)
        else:
            msg = _('[command completed successfully %s]')
        self.ui.write(msg % time.asctime() + '\n', label='control')

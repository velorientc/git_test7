# thread.py - A seprated thread to run Mercurial command
#
# Copyright 2009 Steve Borho <steve@borho.org>
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import Queue
import time
import urllib2

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import ui, util, error, dispatch

from tortoisehg.util import thread2, hglib
from tortoisehg.hgqt.i18n import _, localgettext
from tortoisehg.hgqt import qtlib

local = localgettext()

class DataWrapper(object):
    def __init__(self, data):
        self.data = data

class UiSignal(QObject):
    writeSignal = pyqtSignal(DataWrapper)
    errorSignal = pyqtSignal(DataWrapper)
    interactSignal = pyqtSignal(DataWrapper)
    progressSignal = pyqtSignal(DataWrapper)
    def __init__(self):
        QObject.__init__(self)

class QtUi(ui.ui):
    def __init__(self, src=None, responseq=None):
        super(QtUi, self).__init__(src)

        if src:
            self.sig = src.sig
            self.responseq = src.responseq
        else:
            self.sig = UiSignal()
            self.responseq = responseq

        self.setconfig('ui', 'interactive', 'on')
        self.setconfig('progress', 'disable', 'True')
        os.environ['TERM'] = 'dumb'
        qtlib.configstyles(self)

    def write(self, *args, **opts):
        if self._buffers:
            self._buffers[-1].extend([str(a) for a in args])
        else:
            wrapper = DataWrapper((''.join(args), opts.get('label', '')))
            self.sig.writeSignal.emit(wrapper)

    def write_err(self, *args, **opts):
        for a in args:
            data = DataWrapper((str(a), opts.get('label', 'ui.error')))
            self.sig.errorSignal.emit(data)

    def label(self, msg, label):
        return msg

    def flush(self):
        pass

    def prompt(self, msg, choices=None, default='y'):
        if not self.interactive(): return default
        try:
            data = DataWrapper((msg, False, choices, None))
            self.sig.interactSignal.emit(data)
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
            data = DataWrapper((msg, False, choices, default))
            self.sig.interactSignal.emit(data)
            # await response
            r = self.responseq.get(True)
            if r is None:
                raise EOFError
            return r
        except EOFError:
            raise util.Abort(local._('response expected'))

    def getpass(self, prompt=_('password: '), default=None):
        data = DataWrapper((prompt, True, None, default))
        self.sig.interactSignal.emit(data)
        # await response
        r = self.responseq.get(True)
        if r is None:
            raise util.Abort(local._('response expected'))
        return r

    def progress(self, topic, pos, item='', unit='', total=None):
        data = DataWrapper((topic, item, pos, total, unit))
        self.sig.progressSignal.emit(data)


class CmdThread(QThread):
    """Run an Mercurial command in a background thread, implies output
    is being sent to a rendered text buffer interactively and requests
    for feedback from Mercurial can be handled by the user via dialog
    windows.
    """
    # (msg=str, label=str) [wrapped]
    outputReceived = pyqtSignal(DataWrapper)

    # (msg=str, label=str) [wrapped]
    errorReceived = pyqtSignal(DataWrapper)

    # (topic=str, item=str, pos=int, total=int, unit=str) [wrapped]
    progressReceived = pyqtSignal(DataWrapper)

    # result=int or None [wrapped]
    # result: None - command is incomplete, possibly exited with exception
    #         0 - command is finished successfully
    #         others - return code of command
    commandFinished = pyqtSignal(DataWrapper)

    def __init__(self, cmdline, parent=None):
        super(CmdThread, self).__init__()

        self.cmdline = cmdline
        self.parent = parent
        self.ret = None
        self.abortbyuser = False
        self.responseq = Queue.Queue()
        self.rawoutput = []

        self.finished.connect(self.thread_finished)

    def abort(self):
        if self.isRunning() and hasattr(self, 'thread_id'):
            self.abortbyuser = True
            thread2._async_raise(self.thread_id, KeyboardInterrupt)

    def thread_finished(self):
        self.commandFinished.emit(DataWrapper(self.ret))

    def output_handler(self, wrapper):
        self.rawoutput.append(wrapper.data[0])
        self.outputReceived.emit(wrapper)

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
            text, ok = QInputDialog.getText(self.parent,
                            _('TortoiseHg Prompt'), prompt, mode)
            self.responseq.put(ok and text or None)

    def run(self):
        # save thread id in order to terminate by KeyboardInterrupt
        self.thread_id = int(QThread.currentThreadId())

        ui = QtUi(responseq=self.responseq)
        ui.sig.writeSignal.connect(self.output_handler)
        ui.sig.errorSignal.connect(self.errorReceived)
        ui.sig.interactSignal.connect(self.interact_handler)
        ui.sig.progressSignal.connect(self.progressReceived)

        try:
            for k, v in ui.configitems('defaults'):
                ui.setconfig('defaults', k, '')
            self.ret = dispatch._dispatch(ui, self.cmdline) or 0
        except util.Abort, e:
            ui.write_err(local._('abort: ') + str(e) + '\n')
        except (error.RepoError, urllib2.HTTPError), e:
            ui.write_err(str(e) + '\n')
        except (Exception, OSError, IOError), e:
            ui.write_err(str(e) + '\n')
        except KeyboardInterrupt:
            pass

        if self.ret is None:
            if self.abortbyuser:
                msg = _('[command terminated by user %s]')
            else:
                msg = _('[command interrupted %s]')
        elif self.ret:
            msg = _('[command returned code %d %%s]') % int(self.ret)
        else:
            msg = _('[command completed successfully %s]')
        w = DataWrapper((msg % time.asctime() + '\n', 'control'))
        self.outputReceived.emit(w)

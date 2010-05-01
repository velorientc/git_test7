# hgthread.py - Gtk UI class TortoiseHg
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import Queue
import time
import urllib2

from mercurial import ui, util, error

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, thread2

from tortoisehg.hgtk import dialog, gdialog

class GtkUi(ui.ui):
    '''
    PyGtk enabled mercurial.ui subclass.  All this code will be running
    in a background thread, so it cannot directly call into Gtk.
    Instead, it places output and dialog requests onto queues for the
    main thread to pickup.
    '''
    def __init__(self, src=None, outputq=None, errorq=None, dialogq=None,
            responseq=None, progressq=None):
        super(GtkUi, self).__init__(src)
        if src:
            self.outputq = src.outputq
            self.errorq = src.errorq
            self.dialogq = src.dialogq
            self.responseq = src.responseq
            self.progressq = src.progressq
        else:
            self.outputq = outputq
            self.errorq = errorq
            self.dialogq = dialogq
            self.responseq = responseq
            self.progressq = progressq
        self.setconfig('ui', 'interactive', 'on')
        self.setconfig('progress', 'disable', 'True')

    def write(self, *args, **opts):
        if hglib.uiwrite(self, args):
            for a in args:
                self.outputq.put(str(a))

    def write_err(self, *args, **opts):
        for a in args:
            self.errorq.put(str(a))

    def flush(self):
        pass

    def prompt(self, msg, choices=None, default="y"):
        if not self.interactive(): return default
        try:
            # send request to main thread, await response
            self.dialogq.put( (msg, True, choices, None) )
            r = self.responseq.get(True)
            if r is None:
                raise EOFError
            if not r:
                return default
            if choices:
                # return char for Mercurial 1.3
                choice = choices[r]
                return choice[choice.index("&")+1].lower()
            return r
        except EOFError:
            raise util.Abort(_('response expected'))

    def promptchoice(self, msg, choices, default=0):
        if not self.interactive(): return default
        try:
            # send request to main thread, await response
            self.dialogq.put( (msg, True, choices, default) )
            r = self.responseq.get(True)
            if r is None:
                raise EOFError
            return r
        except EOFError:
            raise util.Abort(_('response expected'))

    def getpass(self, prompt=None, default=None):
        # send request to main thread, await response
        self.dialogq.put( (prompt or _('password: '), False, None, default) )
        r = self.responseq.get(True)
        if r is None:
            raise util.Abort(_('response expected'))
        return r

    def progress(self, topic, pos, item='', unit='', total=None):
        self.progressq.put( (topic, item, pos, total, unit) )


class HgThread(thread2.Thread):
    '''
    Run an hg command in a background thread, implies output is being
    sent to a rendered text buffer interactively and requests for
    feedback from Mercurial can be handled by the user via dialog
    windows.
    '''
    def __init__(self, args=[], postfunc=None, parent=None):
        self.outputq = Queue.Queue()
        self.errorq = Queue.Queue()
        self.dialogq = Queue.Queue()
        self.responseq = Queue.Queue()
        self.progressq = Queue.Queue()
        self.ui = GtkUi(None, self.outputq, self.errorq, self.dialogq,
                        self.responseq, self.progressq)
        self.args = args
        self.ret = None
        self.postfunc = postfunc
        self.parent = parent
        thread2.Thread.__init__(self)

    def getqueue(self):
        return self.outputq

    def geterrqueue(self):
        return self.errorq

    def getprogqueue(self):
        return self.progressq

    def return_code(self):
        '''
        None - command is incomplete, possibly exited with exception
        0    - command returned successfully
               else an error was returned
        '''
        return self.ret

    def process_dialogs(self):
        '''Polled every 10ms to serve dialogs for the background thread'''
        try:
            (prompt, visible, choices, default) = self.dialogq.get_nowait()
            if choices:
                dlg = gdialog.CustomPrompt('Hg Prompt', prompt,
                        self.parent, choices, default)
                dlg.connect('response', self.prompt_response)
                dlg.show_all()
            else:
                dlg = dialog.entry_dialog(self.parent, prompt,
                        visible, default, self.dialog_response)
        except Queue.Empty:
            pass

    def prompt_response(self, dialog, response_id):
        dialog.destroy()
        if response_id == gtk.RESPONSE_DELETE_EVENT:
            self.responseq.put(None)
        else:
            self.responseq.put(response_id)

    def dialog_response(self, dialog, response_id):
        if response_id == gtk.RESPONSE_OK:
            text = dialog.entry.get_text()
        else:
            text = None
        dialog.destroy()
        self.responseq.put(text)

    def run(self):
        try:
            for k, v in self.ui.configitems('defaults'):
                self.ui.setconfig('defaults', k, '')
            ret = hglib.dispatch._dispatch(self.ui, self.args)
            if ret:
                self.ui.write(_('[command returned code %d ') % int(ret))
            else:
                self.ui.write(_('[command completed successfully '))
            self.ui.write(time.asctime() + ']\n')
            self.ret = ret or 0
            if self.postfunc:
                self.postfunc(ret)
        except util.Abort, e:
            self.ui.write_err(_('abort: ') + str(e) + '\n')
        except (error.RepoError, urllib2.HTTPError), e:
            self.ui.write_err(str(e) + '\n')
        except (Exception, OSError, IOError), e:
            self.ui.write_err(str(e) + '\n')

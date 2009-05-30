#
# Gtk UI class TortoiseHg
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import gtk
import Queue
import urllib2

from mercurial import ui, util

from thgutil.i18n import _
from thgutil import hglib, thread2

from hggtk import dialog, gdialog

class GtkUi(ui.ui):
    '''
    PyGtk enabled mercurial.ui subclass.  All this code will be running
    in a background thread, so it cannot directly call into Gtk.
    Instead, it places output and dialog requests onto queues for the
    main thread to pickup.
    '''
    def __init__(self, src=None, outputq=None, errorq=None, dialogq=None,
            responseq=None, parentui=None):
        if parentui:
            # Mercurial 1.2
            super(GtkUi, self).__init__(parentui=parentui)
            src = parentui
        else:
            # Mercurial 1.3
            super(GtkUi, self).__init__(src)
        if src:
            self.outputq = src.outputq
            self.errorq = src.errorq
            self.dialogq = src.dialogq
            self.responseq = src.responseq
        else:
            self.outputq = outputq
            self.errorq = errorq
            self.dialogq = dialogq
            self.responseq = responseq
        self.setconfig('ui', 'interactive', 'on')

    def write(self, *args):
        if hglib.uiwrite(self, args):
            for a in args:
                self.outputq.put(str(a))

    def write_err(self, *args):
        for a in args:
            self.errorq.put(str(a))

    def flush(self):
        pass

    def prompt(self, msg, choices=None, default="y"):
        import re
        if not hglib.calliffunc(self.interactive): return default
        if isinstance(choices, str):
            pat = choices
            choices = None
        else:
            pat = None
        while True:
            try:
                # send request to main thread, await response
                self.dialogq.put( (msg, True, choices, default) )
                r = self.responseq.get(True)
                if r is None:
                    raise EOFError
                if not r:
                    return default
                if not pat or re.match(pat, r):
                    return r
                else:
                    self.write(_('unrecognized response\n'))
            except EOFError:
                raise util.Abort(_('response expected'))

    def getpass(self, prompt=None, default=None):
        # send request to main thread, await response
        self.dialogq.put( (prompt or _('password: '), False, None, default) )
        r = self.responseq.get(True)
        if r is None:
            raise util.Abort(_('response expected'))
        return r


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
        self.ui = GtkUi(None, self.outputq, self.errorq, self.dialogq,
                        self.responseq)
        self.args = args
        self.ret = None
        self.postfunc = postfunc
        self.parent = parent
        thread2.Thread.__init__(self)

    def getqueue(self):
        return self.outputq

    def geterrqueue(self):
        return self.errorq

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
            raise util.Abort('No response')
        else:
            self.responseq.put(chr(response_id))

    def dialog_response(self, dialog, response_id):
        if response_id == gtk.RESPONSE_OK:
            text = dialog.entry.get_text()
        else:
            text = None
        dialog.destroy()
        self.responseq.put(text)

    def run(self):
        try:
            ret = None
            if hasattr(self.ui, 'copy'):
                # Mercurial 1.3
                ret = hglib.dispatch._dispatch(self.ui, self.args)
            else:
                # Mercurial 1.2
                # Some commands create repositories, and thus must create
                # new ui() instances.  For those, we monkey-patch ui.ui()
                # as briefly as possible.
                origui = None
                if self.args[0] in ('clone', 'init'):
                    origui = ui.ui
                    ui.ui = GtkUi
                try:
                    ret = hglib.thgdispatch(self.ui, None, self.args)
                finally:
                    if origui:
                        ui.ui = origui
            if ret:
                self.ui.write(_('[command returned code %d]\n') % int(ret))
            else:
                self.ui.write(_('[command completed successfully]\n'))
            self.ret = ret or 0
            if self.postfunc:
                self.postfunc(ret)
        except (hglib.RepoError, urllib2.HTTPError, util.Abort), e:
            self.ui.write_err(str(e) + '\n')
        except Exception, e:
            self.ui.write_err(str(e) + '\n')
        except hglib.WinIOError, e:
            self.ui.write_err(str(e) + '\n')

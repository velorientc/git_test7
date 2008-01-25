import gtk
import os.path
import traceback
import threading
import Queue
from mercurial import hg, ui, util, extensions
from mercurial.node import *
from mercurial.i18n import _
from dialog import entry_dialog

try:
    try:
        from mercurial import demandimport
    except:
        from mercurial.commands import demandimport # pre 0.9.5
    demandimport.disable()

    try:
        # Mercurail 0.9.4
        from mercurial.cmdutil import parse
    except:
        try:
            # Mercurail <= 0.9.3
            from mercurial.commands import parse
        except:
            # Mercurail 0.9.5
            from mercurial.dispatch import _parse as parse
finally:
    demandimport.enable()

keyword_module = None
def detect_keyword():
    '''
    The keyword extension has difficulty predicting when it needs to
    intercept data output from various commands when the mercurial
    libraries are used by python applications.  Recent versions offer a
    hook that applications can call to register commands about to be
    executed (as a replacement for sys.argv[]).
    '''
    global keyword_module
    if keyword_module is not None:
        return keyword_module
    for name, module in extensions.extensions():
        if name == 'keyword':
            if hasattr(module, 'externalcmdhook'):
                keyword_module = module
            break
    else:
        keyword_module = False
    return keyword_module

def rootpath(path=None):
    """ find Mercurial's repo root of path """
    if not path:
        path = os.getcwd()
    p = os.path.isdir(path) and path or os.path.dirname(path)
    while not os.path.isdir(os.path.join(p, ".hg")):
        oldp = p
        p = os.path.dirname(p)
        if p == oldp:
            return ''
    return p


class GtkUi(ui.ui):
    '''
    PyGtk enabled mercurial.ui subclass.  All this code will be running
    in a background thread, so it cannot directly call into Gtk.
    Instead, it places output and dialog requests onto queues for the
    main thread to pickup.
    '''
    def __init__(self, outputq, dialogq, responseq):
        ui.ui.__init__(self)
        self.outputq = outputq
        self.dialogq = dialogq
        self.responseq = responseq

    def write(self, *args):
        if self.buffers:
            self.buffers[-1].extend([str(a) for a in args])
        else:
            for a in args:
                self.outputq.put(str(a))

    def write_err(self, *args):
        for a in args:
            self.outputq.put('*** ' + str(a))

    def flush(self):
        pass

    def prompt(self, msg, pat=None, default="y"):
        import re
        if not self.interactive: return default
        while True:
            try:
                # send request to main thread, await response
                self.dialogq.put( (msg, True, default) )
                r = self.responseq.get(True)
                if not r:
                    return default
                if not pat or re.match(pat, r):
                    return r
                else:
                    self.write(_("unrecognized response\n"))
            except EOFError:
                raise util.Abort(_('response expected'))

    def getpass(self, prompt=None, default=None):
        # send request to main thread, await response
        self.dialogq.put( (prompt or _('password: '), False, default) )
        r = self.responseq.get(True)
        return p

    def print_exc(self):
        traceback.print_exc()
        return True

class HgThread(threading.Thread):
    '''
    Run an hg command in a background thread, implies output is being
    sent to a rendered text buffer interactively and requests for
    feedback from Mercurial can be handled by the user via dialog
    windows.
    '''
    def __init__(self, args=[], postfunc=None):
        self.path = rootpath()
        self.outputq = Queue.Queue()
        self.dialogq = Queue.Queue()
        self.responseq = Queue.Queue()
        self.ui = GtkUi(self.outputq, self.dialogq, self.responseq)
        self.args = args
        self.ret = None
        self.postfunc = postfunc
        threading.Thread.__init__(self)

    def getqueue(self):
        return self.outputq

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
            (prompt, visible, default) = self.dialogq.get_nowait()
            self.dlg = entry_dialog(prompt, visible, default,
                    self.dialog_response)
        except Queue.Empty:
            pass

    def dialog_response(self, widget, response_id):
        if response_id == gtk.RESPONSE_OK:
            text = self.dlg.entry.get_text()
        else:
            text = None
        self.dlg.destroy()
        self.responseq.put(text)

    def run(self):
        try:
            self.ui.readconfig(os.path.join(self.path, ".hg", "hgrc"))
            c, func, args, opts, cmdoptions = parse(self.ui, self.args)
            self.ui.updateopts(opts["verbose"], opts["debug"], opts["quiet"],
                    not opts["noninteractive"], opts["traceback"])

            kw = detect_keyword()
            if kw: kw.externalcmdhook(c, *args, **cmdoptions)

            repo = hg.repository(self.ui, path=self.path)
            repo.ui = self.ui
            ret = func(self.ui, repo, *args, **cmdoptions)

            if ret:
                self.ui.write('[command returned code %d]\n' % int(ret))
            else:
                self.ui.write('[command completed successfully]\n')

            self.ret = ret or 0
            if self.postfunc:
                self.postfunc(ret)
        except hg.RepoError, e:
            self.ui.write_err(str(e))
        except util.Abort, e:
            self.ui.write_err(str(e))
            if self.ui.traceback:
                self.ui.print_exc()
        except Exception, e:
            self.ui.write_err(str(e))
            self.ui.print_exc()


def hgcmd_toq(path, q, *cmdargs, **options):
    '''
    Run an hg command in a background thread, pipe all output to a Queue
    object.  Assumes command is completely noninteractive.
    '''
    class Qui(ui.ui):
        def __init__(self):
            ui.ui.__init__(self)

        def write(self, *args):
            if self.buffers:
                self.buffers[-1].extend([str(a) for a in args])
            else:
                for a in args:
                    q.put(str(a))
    u = Qui()
    u.readconfig(os.path.join(path, ".hg", "hgrc"))
    c, func, args, opts, cmdoptions = parse(ui, list(cmdargs))
    cmdoptions.update(options)
    u.updateopts(opts["verbose"], opts["debug"], opts["quiet"],
                 not opts["noninteractive"], opts["traceback"])

    kw = detect_keyword()
    if kw: kw.externalcmdhook(c, *args, **cmdoptions)

    repo = hg.repository(u, path=path)
    return func(u, repo, *args, **cmdoptions)

import gtk
import os.path
import traceback
import threading
import Queue
from mercurial import hg, ui, util, commands, dispatch, cmdutil
from mercurial.node import *
from mercurial.i18n import _
from dialog import entry_dialog

try:
    try:
        commands.demandimport.disable()
    except:
        pass    # 0.9.5 has demandimport removed
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
    try:
        commands.demandimport.enable()
    except:
        pass     # 0.9.5 has demandimport removed

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

class Hg:
    def __init__(self, path=''):
        self.u = ui.ui()
        self.path = path
        self.root = rootpath(path)
        self.repo = hg.repository(self.u, path=self.root)
       
    def command(self, cmd, files=[], options={}):
        absfiles = [os.path.join(self.root, x) for x in files]
        self.repo.ui.pushbuffer()
        c, func, args, opts, cmdoptions = parse(self.repo.ui, [cmd])
        cmdoptions.update(options)
        func(self.repo.ui, self.repo, *absfiles, **cmdoptions)
        outtext = self.repo.ui.popbuffer()
        return outtext
        
    def status(self, files=[], list_clean=False):
        files, matchfn, anypats = cmdutil.matchpats(self.repo, files)
        status = [n for n in self.repo.status(files=files, list_clean=list_clean)]    
        return status
        
    def abspath(self, files):
        return [os.path.join(self.root, x) for x in files]

class GtkUi(ui.ui):
    outputq = Queue.Queue()
    dialoglock = threading.Lock()
    dialogq = Queue.Queue()
    responseq = Queue.Queue()

    '''PyGtk enabled mercurial.ui subclass'''
    def __init__(self, verbose=False, debug=False, quiet=False,
                 interactive=True, traceback=False, report_untrusted=True,
                 parentui=None):
        super(GtkUi, self).__init__(verbose, debug, quiet, interactive,
                traceback, report_untrusted, parentui)
        # Override a few settings
        self.verbose = True

    def isatty(self):
        # lies, damn lies, and marketing
        return True

    def write(self, *args):
        for a in args:
            self.outputq.put(str(a))

    def write_err(self, *args):
        for a in args:
            self.outputq.put('*** ' + str(a))

    def flush(self):
        pass

    def prompt(self, msg, pat=None, default="y"):
        '''generic PyGtk prompt dialog'''
        import re
        if not self.interactive: return default
        while True:
            try:
                # send request to main thread, await response
                self.dialoglock.acquire()
                self.dialogq.put( (msg, True, default) )
                r = self.responseq.get(True)
                self.dialoglock.release()
                if not r:
                    return default
                if not pat or re.match(pat, r):
                    return r
                else:
                    self.write(_("unrecognized response\n"))
            except EOFError:
                raise util.Abort(_('response expected'))

    def getpass(self, prompt=None, default=None):
        '''generic PyGtk password prompt dialog'''
        # send request to main thread, await response
        self.dialoglock.acquire()
        self.dialogq.put( (prompt or _('password: '), False, default) )
        r = self.responseq.get(True)
        self.dialoglock.release()
        return p

    def print_exc(self):
        traceback.print_exc()
        return True

class HgThread(threading.Thread):
    savedui = None
    instances = 0

    def __init__(self, args=[], postfunc=None):
        self.ui = GtkUi()
        self.args = args
        self.ret = None
        self.postfunc = postfunc
        threading.Thread.__init__(self)

    def command(self, cmd, files=[], options={}):
        '''Convenience function for setting command line arguments'''
        args = [cmd]
        for k in options.keys():
            args += [k, options[k]]
        self.args = args + files

    def getqueue(self):
        return GtkUi.outputq

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
            (prompt, visible, default) = GtkUi.dialogq.get_nowait()
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
        GtkUi.responseq.put(text)

    def run(self):
        if HgThread.instances == 0 and not hasattr(ui.ui, 'outputq'):
            # Monkey patch our GUI ui subclass into place
            HgThread.savedui = ui.ui
            ui.ui = GtkUi
        HgThread.instances += 1
        try:
            ret = dispatch._dispatch(self.ui, self.args)
            if ret:
                self.ui.write('command returned code %d.\n' % int(ret))
            else:
                self.ui.write('command completed successfully.\n')
            self.ret = ret or 0
            if self.postfunc:
                self.postfunc(ret)
        except hg.RepoError, e:
            self.ui.write_err(e)
        except util.Abort, e:
            self.ui.write_err(e)
            if self.ui.traceback:
                self.ui.print_exc()
        except Exception, e:
            self.ui.write_err(e)
            self.ui.print_exc()
        finally:
            HgThread.instances += -1
            if HgThread.instances == 0 and HgThread.savedui:
                # Undo monkey patch
                ui.ui = HgThread.savedui
                HgThread.savedui = None

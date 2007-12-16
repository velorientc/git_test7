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
    queue = Queue.Queue()

    '''PyGtk enabled mercurial.ui subclass'''
    def __init__(self, verbose=False, debug=False, quiet=False,
                 interactive=True, traceback=False, report_untrusted=True,
                 parentui=None):
        super(GtkUi, self).__init__(verbose, debug, quiet, interactive,
                traceback, report_untrusted, parentui)
        # Override a few settings
        self.interactive = True
        self.verbose = True

    def isatty(self):
        # lies, damn lies, and marketing
        return True

    def write(self, *args):
        for a in args:
            self.queue.put(str(a))

    def write_err(self, *args):
        for a in args:
            self.queue.put('Error: ' + str(a))

    def flush(self):
        pass

    def prompt(self, msg, pat=None, default="y", matchflags=0):
        '''generic PyGtk prompt dialog'''
        try:
            # Show text entry dialog with msg prompt
            r = entry_dialog(msg, default=default)
            if not pat or re.match(pat, r, matchflags):
                return r
            else:
                self.write(_("unrecognized response\n"))
        except:
            raise util.Abort(_('response expected'))

    def getpass(self, prompt=None, default=None):
        '''generic PyGtk password prompt dialog'''
        return entry_dialog(prompt or _('password: '),
                visible=False, default=default)

    def print_exc(self):
        traceback.print_exc()
        return True

class HgThread(threading.Thread):
    def __init__(self, args = []):
        self.ui = GtkUi()
        self.args = args
        threading.Thread.__init__(self)

    def command(self, cmd, files=[], options={}):
        '''Convenience function for setting command line arguments'''
        args = [cmd]
        for k in options.keys():
            args += [k, options[k]]
        self.args = args + files

    def getqueue(self):
        return GtkUi.queue

    def run(self):
        # Monkey patch our GUI ui subclass into place
        savedui = ui.ui
        ui.ui = GtkUi
        try:
            dispatch._dispatch(self.ui, self.args)
        except hg.RepoError, e:
            self.ui.write(e)
        except util.Abort, e:
            self.ui.write_err(e)
            if self.ui.traceback:
                self.ui.print_exc()
        except Exception, e:
            self.ui.write_err(e)
            self.ui.print_exc()
        finally:
            # Undo monkey patch
            ui.ui = savedui

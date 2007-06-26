import os.path
from mercurial import hg, ui, cmdutil, commands
from mercurial.node import *

try:
    commands.demandimport.disable()
    try:
        # Mercurail 0.9.4
        from mercurial.cmdutil import parse
    except:
        # Mercurail <= 0.9.3
        from mercurial.commands import parse
finally:
    commands.demandimport.enable()

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


import os.path
from mercurial import hg, ui, cmdutil, commands
from mercurial.node import *

def rootpath(path):
    """ find Mercurial's repo root of path """
    p = os.path.isdir(path) and path or os.path.dirname(path)
    while not os.path.isdir(os.path.join(p, ".hg")):
        oldp = p
        p = os.path.dirname(p)
        if p == oldp:
            return ''
    return p

class Hg:
    def __init__(self, path=''):
        self.path = path
        self.u = ui.ui()
        self.repo = hg.repository(self.u, path=rootpath(path))
        self.root = self.repo.root
       
    def command(self, cmd, files=[], options={}):
        absfiles = [os.path.join(self.root, x) for x in files]
        self.repo.ui.pushbuffer()
        c, func, args, opts, cmdoptions = commands.parse(self.repo.ui, [cmd])
        cmdoptions.update(options)
        func(self.repo.ui, self.repo, *absfiles, **cmdoptions)
        outtext = self.repo.ui.popbuffer()
        return outtext
        
    def status(self, files=[], list_clean=False):
        files, matchfn, anypats = cmdutil.matchpats(self.repo, files)
        status = [n for n in self.repo.status(files=files, list_clean=list_clean)]    
        return status
        

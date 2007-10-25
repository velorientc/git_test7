#
# status.py - status dialog for TortoiseHg
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

from mercurial import ui, hg
import gtools

def run(root='', files=[]):
    u = ui.ui()
    u.updateopts(debug=False, traceback=False)
    repo = hg.repository(u, path=root)

    cmdoptions = {
        'all':False, 'clean':False, 'ignored':False, 'modified':True,
        'added':True, 'removed':True, 'deleted':True, 'unknown':False, 'rev':[],
        'exclude':[], 'include':[], 'debug':True,'verbose':True
    }
    
    gtools.gstatus(u, repo, *files, **cmdoptions)

if __name__ == "__main__":
    import sys
    path = len(sys.argv) > 1 and sys.argv[1] or ''
    run(path)

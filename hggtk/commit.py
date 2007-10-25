#
# commit.py - commit dialog for TortoiseHg
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
        'user':'', 'date':'',
        'modified':True, 'added':True, 'removed':True, 'deleted':True,
        'unknown':False, 'ignored':False, 
        'exclude':[], 'include':[],
    }
    
    gtools.gcommit(u, repo, *files, **cmdoptions)

if __name__ == "__main__":
    import sys
    path = len(sys.argv) > 1 and sys.argv[1] or ''
    run(path)

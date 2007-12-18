#
# commit.py - commit dialog for TortoiseHg
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

from mercurial import ui, hg
import gtools

def run(root='', files=[], cwd='', **opts):
    # If no files or directories were selected, take current dir
    # TODO: Not clear if this is best; user may expect repo wide
    if not files and cwd:
        files = [cwd]

    u = ui.ui()
    u.updateopts(debug=False, traceback=False)
    repo = hg.repository(u, path=root)

    cmdoptions = {
        'user':'', 'date':'',
        'modified':True, 'added':True, 'removed':True, 'deleted':True,
        'unknown':False, 'ignored':False, 
        'exclude':[], 'include':[],
        'check': False, 'git':False, 'logfile':'', 'addremove':False,
    }
    
    gtools.gcommit(u, repo, *files, **cmdoptions)

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or ''
    run(**opts)

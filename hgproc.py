#
# front-end for TortoiseHg dialogs
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import sys
from mercurial import ui
from tortoise.thgutil import find_path, get_prog_root, shellquote

if not sys.stdin.isatty():
    try:
        import win32traceutil
        
        # FIXME: quick workaround traceback caused by missing "closed" 
        # attribute in win32trace.
        from mercurial import ui
        def write_err(self, *args):
            for a in args:
                sys.stderr.write(str(a))
        ui.ui.write_err = write_err

        os.environ['PATH'] = "%s;%s" % (get_prog_root(), os.environ['PATH'])
    except ImportError:
        pass
    except pywintypes.error:
        pass

# Map hgproc commands to dialog modules in hggtk/
from hggtk import commit, status, addremove, tagadd, tags, history, merge
from hggtk import diff, revisions, update, serve, clone, synch, hgcmd
_dialogs = { 'commit' : commit,    'status' : status,    'revert' : status,
             'add'    : addremove, 'remove' : addremove, 'tag'    : tagadd,
             'tags'   : tags,      'log'    : history,   'history': history,
             'diff'   : diff,      'merge'  : merge,     'tip'    : revisions,
             'parents': revisions, 'heads'  : revisions, 'update' : update,
             'clone'  : clone,     'serve'  : serve,     'synch'  : synch}

def get_list_from_file(filename):
    fd = open(filename, "r")
    lines = [ x.replace("\n", "") for x in fd.readlines() ]
    fd.close()
    return lines

def get_option(args):
    import getopt
    long_opt_list = ('command=', 'exepath=', 'listfile=', 'title=',
                      'root=', 'cwd=', 'notify', 'deletelistfile')
    opts, args = getopt.getopt(args, "c:e:l:ndt:R:", long_opt_list)
    # Set default options
    options = {}
    options['hgcmd'] = 'help'
    options['hgpath'] = find_path('hg') or 'hg'
    options['cwd'] = os.getcwd()
    options['files'] = []
    listfile = None
    delfile = False
    
    for o, a in opts:
        if o in ("-c", "--command"):
            options['hgcmd'] = a
        elif o in ("-l", "--listfile"):
            listfile = a
        elif o in ("-d", "--deletelistfile"):
            delfile = True
        elif o in ("-e", "--exepath"):
            options['hgpath'] = a
        elif o in ("-n", "--notify"):
            options['notify'] = True
        elif o in ("-t", "--title"):
            options['title'] = a
        elif o in ("-R", "--root"):
            options['root'] = a
        elif o in ("--cwd"):
            options['cwd'] = a

    if listfile:
        options['files'] = get_list_from_file(listfile)
        if delfile:
            os.unlink(listfile)

    return (options, args)

def parse(args):
    option, args = get_option(args)
    
    cmdline = [option['hgpath'], option['hgcmd']] 
    if option.has_key('root'):
        cmdline.append('--repository')
        cmdline.append(option['root'])
    cmdline.extend(args)
    cmdline.extend(option['files'])
    option['cmdline'] = cmdline

    # Failsafe choice for merge tool
    if os.environ.get('HGMERGE', None):
        pass
    elif ui.ui().config('ui', 'merge', None):
        pass
    else:
        path = find_path('simplemerge') or 'simplemerge'
        os.environ['HGMERGE'] = '%s -L my -L other' % shellquote(path)
        print "override HGMERGE =", os.environ['HGMERGE']

    global _dialogs
    dialog = _dialogs.get(option['hgcmd'], hgcmd)
    dialog.run(**option)


def run_trapped(args):
    try:
        dlg = parse(sys.argv[1:])
    except:
        import traceback
        from hggtk.dialog import error_dialog
        tr = traceback.format_exc()
        print tr
        error_dialog("Error executing hgproc", tr)

if __name__=='__main__':
    #dlg = parse(['-c', 'help', '--', '-v'])
    #dlg = parse(['-c', 'log', '--root', 'c:\hg\h1', '--', '-l1'])
    #dlg = parse(['-c', 'status', '--root', 'c:\hg\h1', ])
    #dlg = parse(['-c', 'add', '--root', 'c:\hg\h1', '--listfile', 'c:\\hg\\h1\\f1', '--notify'])
    #dlg = parse(['-c', 'rollback', '--root', 'c:\\hg\\h1'])
    print "hgproc sys.argv =", sys.argv
    dlg = run_trapped(sys.argv[1:])

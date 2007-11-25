#
# front-end for TortoiseHg dialogs
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

try:
    import win32traceutil
    trace = True
    
    # FIXME: quick workaround traceback caused by missing "closed" 
    # attribute in win32trace.
    from mercurial import ui
    def write_err(self, *args):
        for a in args:
            sys.stderr.write(str(a))
    ui.ui.write_err = write_err
except pywintypes.error:
    trace = False

import os
import sys
import getopt
from tortoise import thgutil

os.environ['PATH'] = "%s;%s" % (thgutil.get_prog_root(), os.environ['PATH'])
hg_executable = thgutil.find_path("hg")
if trace: print "hgproc: hg_executable = %s" % hg_executable

def get_option(args):
    long_opt_list =  ['command=', 'exepath=', 'listfile=', 'title=',
                      'root=', 'cwd=', 'notify', 'deletelistfile']
    opts, args = getopt.getopt(args, "c:e:l:ndt:R:", long_opt_list)
    options = {'hgcmd': 'help', 'hgpath': 'hg'}
    
    for o, a in opts:
        if o in ("-c", "--command"):
            options['hgcmd'] = a
        elif o in ("-l", "--listfile"):
            options['listfile'] = a
        elif o in ("-e", "--exepath"):
            options['hgpath'] = a
        elif o in ("-n", "--notify"):
            options['notify'] = True
        elif o in ("-t", "--title"):
            options['title'] = a
        elif o in ("-d", "--deletelistfile"):
            options['rmlistfile'] = True
        elif o in ("-R", "--root"):
            options['root'] = a
        elif o in ("--cwd"):
            options['cwd'] = a

    return (options, args)

def get_list_from_file(filename):
    fd = open(filename, "r")
    lines = [ x.replace("\n", "") for x in fd.readlines() ]
    fd.close()
    return lines
    
def parse(args):
    option, args = get_option(args)
    
    filelist = []
    if option.has_key('listfile'):
        filelist = get_list_from_file(option['listfile'])
    if option.has_key('rmlistfile'):
        os.unlink(option['listfile'])
        
    cmdline = "hg %s" % option['hgcmd']
    if option.has_key('root'):
        cmdline += " --repository %s" % thgutil.shellquote(option['root'])
    if args:
        cmdline += " %s" % " ".join([(x) for x in args])
    if filelist:
        cmdline += " %s" % " ".join([thgutil.shellquote(x) for x in filelist])

    if option['hgcmd'] == 'commit':
        import hggtk.commit
        if not filelist:
            filelist = [option['cwd']]
        return hggtk.commit.run(root=option['root'], files=filelist)
    elif option['hgcmd'] in ('status', 'revert'):
        import hggtk.status
        return hggtk.status.run(root=option['root'], files=filelist)
    elif option['hgcmd'] in ('add', 'remove'):
        import hggtk.addremove
        return hggtk.addremove.run(option['hgcmd'],
                                   root=option['root'],
                                   files=filelist)
    elif option['hgcmd'] == 'tag':
        import hggtk.tagadd
        return hggtk.tagadd.run(root=option['root'])
    elif option['hgcmd'] == 'tags':
        import hggtk.tags
        return hggtk.tags.run(root=option['root'])
    elif option['hgcmd'] in ('log', 'history'):
        import hggtk.history
        return hggtk.history.run(root=option['root'], files=filelist)
    elif option['hgcmd'] == 'diff':
        import hggtk.diff
        return hggtk.diff.run(root=option['root'], files=filelist)
    elif option['hgcmd'] == 'merge':
        from mercurial import ui
        import hggtk.merge
        uimerge = ui.ui().config('ui', 'merge', None)
        hgmerge = os.environ.get('HGMERGE', None)
        if uimerge:
            print "ui.merge = %s" % uimerge
        elif hgmerge:
            print "HGMERGE = %s" % os.environ['HGMERGE']
        else:
            app_path = thgutil.find_path("simplemerge", thgutil.get_prog_root(), '.EXE;.BAT')
            os.environ['HGMERGE'] = ('%s -L my -L other' % thgutil.shellquote(app_path))
            print "HGMERGE = %s" % os.environ['HGMERGE']
        return hggtk.merge.run(root=option['root'])
    elif option['hgcmd'] in ('tip', 'parents', 'heads'):
        import hggtk.revisions
        return hggtk.revisions.run(root=option['root'], page=option['hgcmd'])
    elif option['hgcmd'] == 'update':
        import hggtk.update
        return hggtk.update.run(cwd=option['cwd'])
    elif option['hgcmd'] == 'clone':
        import hggtk.clone
        return hggtk.clone.run(cwd=option['cwd'], repos=filelist)
    else:
        import hggtk.cmd
        return hggtk.cmd.run(cmdline)
    
def run_trapped(args):
    try:
        dlg = parse(sys.argv[1:])
    except:
        import traceback
        from hggtk.dialog import error_dialog
        error_dialog("Error executing hgproc", traceback.format_exc())

if __name__=='__main__':
    #dlg = parse(['-c', 'help', '--', '-v'])
    #dlg = parse(['-c', 'log', '--root', 'c:\hg\h1', '--', '-l1'])
    #dlg = parse(['-c', 'status', '--root', 'c:\hg\h1', ])
    #dlg = parse(['-c', 'add', '--root', 'c:\hg\h1', '--listfile', 'c:\\hg\\h1\\f1', '--notify'])
    #dlg = parse(['-c', 'rollback', '--root', 'c:\\hg\\h1'])
    if trace: print "args=", sys.argv
    dlg = run_trapped(sys.argv[1:])

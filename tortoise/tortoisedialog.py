#
# front-end for TortoiseHg dialogs
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import sys
import getopt
import thgutil
from pywin.framework import dlgappcore, app

class TortoiseHgDialogApp(dlgappcore.DialogApp):
    def __init__(self):
        dlgappcore.DialogApp.__init__(self)
        
    def CreateDialog(self):
        return parse(sys.argv)

app.AppBuilder = TortoiseHgDialogApp()

def get_option(args):
    long_opt_list =  ['command=', 'exepath=', 'listfile=', 'title=',
                      'root=', 'notify', 'deletelistfile']
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

    return (options, args)

def get_list_from_file(filename):
    fd = open(filename, "r")
    lines = [ x.replace("\n", "") for x in fd.readlines() ]
    fd.close()
    return lines
    
def parse(args):
    try:
        option, args = get_option(args)
    except getopt.GetoptError, inst:
        print inst
        sys.exit(1)
    
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
                
    opt = {}
    if option.has_key('title'):
        opt['title'] = option['title']
    elif option.has_key('root'):
        opt['title'] = "hg %s - %s" % (option['hgcmd'], option['root'])
    else:
        opt['title'] = "hg %s" % option['hgcmd']

    cmd_notify = ('add', 'revert', 'merge', 'rollback')
    if option.has_key('notify') or option['hgcmd'] in cmd_notify:
        if filelist:
            opt['notify_list'] = filelist
        elif option.has_key('root'):
            opt['notify_list'] = [ option['root'] ]
    
    if option['hgcmd'] == 'commit':
        import commitdialog
        if not filelist:
            filelist = [option['root']]
        return commitdialog.SimpleCommitDialog(files=filelist)
    elif option['hgcmd'] == 'update':
        import updatedialog
        if not filelist:
            filelist = [option['root']]
        return updatedialog.UpdateDialog(path=filelist[0])
    if option['hgcmd'] == 'status':
        import statusdialog
        return statusdialog.status_dialog(option['root'], files=filelist)
    else:
        import gpopen
        return gpopen.PopenDialog(cmdline, **opt)
    
if __name__=='__main__':
    #dlg = parse(['-c', 'help', '--', '-v'])
    #dlg = parse(['-c', 'log', '--root', 'c:\hg\h1', '--', '-l1'])
    #dlg = parse(['-c', 'status', '--root', 'c:\hg\h1', ])
    #dlg = parse(['-c', 'add', '--root', 'c:\hg\h1', '--listfile', 'c:\\hg\\h1\\f1', '--notify'])
    dlg = parse(['-c', 'rollback', '--root', 'c:\\hg\\h1'])
    dlg.CreateWindow()

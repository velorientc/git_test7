#
# Execute a Mercurial (Hg) command and show it's output on an MFC dialog.
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import subprocess
import threading
import win32ui
from pywin.framework import dlgappcore, app
from pywin.mfc.dialog import Dialog
import win32con
import win32api
import win32gui
import os, re, sys
import getopt
import thgutil

dlgStatic = 130
dlgEdit = 129
dlgButton = 128

dlg_EDIT1 = 1001

def get_option(args):
    long_opt_list =  ['command=', 'exepath=', 'listfile=', 'title=',
                      'root=', 'notify', 'deletelistfile']
    opts, args = getopt.getopt(args, "c:e:l:ndt:R:", long_opt_list)
    options = dict({'hgcmd': 'help', 'hgpath': 'hg'} )
    
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
        
    #cmdline = option['hgpath']
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

    #run(cmdline, **opt)
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
    else:
        return PopenDialog(cmdline, **opt)
                         
    if option.has_key('notify'):
        for f in filelist:
            dir = os.path.isdir(f) and f or os.path.dirname(f)
            thgutil.shell_notify(os.path.abspath(dir))

            
class TortoiseHgDialogApp(dlgappcore.DialogApp):
    def __init__(self):
        dlgappcore.DialogApp.__init__(self)
        
    def CreateDialog(self):
        return parse(sys.argv)
        #return PopenDialog(['hg'] + sys.argv, 'Mercurial')

app.AppBuilder = TortoiseHgDialogApp()

class ResizableEditDialog(Dialog): 
    def __init__(self, title="hg", tmpl=None):
        self.title = title
        if tmpl is None:
            tmpl = dlg_template()
        Dialog.__init__(self, tmpl)

    def OnInitDialog(self): 
        rc = Dialog.OnInitDialog(self)
        self.HookMessage(self.OnSize, win32con.WM_SIZE)

        if self.title:
            self.SetWindowText(self.title)
        self.outtext = self.GetDlgItem(dlg_EDIT1)
        self.outtext.SetReadOnly()
        self.outtext.LimitText(10000000)    # enough to hald the log output?
 
        # set output window to use fixed font
        self.font = win32ui.CreateFont({'name': "Courier New", 'height': 14})
        self.outtext.SetFont(self.font);

    def write(self, msg):
        # convert LF to CRLF for binary output
        msg = re.sub(r'(?<!\r)\n', r'\r\n', msg)
        self.outtext.ReplaceSel(msg)

    def PreDoModal(self):
        #sys.stdout = sys.stderr = self
        pass

    def OnCreate(self, msg):
        print "Oncreate: ", msg
        rect = self.GetClientRect()
        print "dlg client rect = ", rect
 
    def _do_size(self, cx, cy, repaint=1):
        # resize the textbox.
        ctrl = self.GetDlgItem(dlg_EDIT1)
        l, t, r, b = ctrl.GetWindowRect()
        l, t = self.ScreenToClient( (l,t) )
        r, b = self.ScreenToClient( (r,b) )
        ctrl.MoveWindow((l, t, cx-6, cy-40), repaint)
        
        # relocate the button.
        ctrl = self.GetDlgItem(win32con.IDOK)
        l, t, r, b = ctrl.GetWindowRect()
        l, t = self.ScreenToClient( (l,t) )
        r, b = self.ScreenToClient( (r,b) )
        w = r - l
        h = b - t
        ctrl.MoveWindow(( l, cy-4-h, r, cy-4), repaint)

    def OnSize(self, message):
        hwnd, msg, wparam, lparam, time, point = message        
        x = win32api.LOWORD(lparam)
        y = win32api.HIWORD(lparam)
        self._do_size(x,y)
        return 1

def dlg_template(w=300, h=300):
    style = (win32con.DS_MODALFRAME | 
             win32con.WS_POPUP | 
             win32con.WS_VISIBLE | 
             win32con.WS_CAPTION | 
             win32con.WS_SYSMENU |
             win32con.WS_THICKFRAME |  # we can resize the dialog window
             win32con.DS_SETFONT)

    cs = win32con.WS_CHILD | win32con.WS_VISIBLE 
    s = win32con.WS_TABSTOP | cs 
      
    dlg = [["PyWin32", (0, 0, w, h), style, None, (8, "MS Sans Serif")],] 
    dlg.append([dlgEdit, "", dlg_EDIT1, (3, 3, w-6, h - 23),
                    s | win32con.SS_LEFT
                      | win32con.WS_BORDER
                      | win32con.ES_MULTILINE
                      | win32con.WS_VSCROLL
                      | win32con.WS_HSCROLL
                      | win32con.ES_WANTRETURN
               ])
    bw, bh = 50, 15
    dlg.append([dlgButton, "OK", win32con.IDOK, (3, h -bh -2, bw, bh),
                    s | win32con.BS_PUSHBUTTON]) 

    return dlg

class PopenDialog(ResizableEditDialog):
    def __init__(self, cmd, title=None, tmpl=None):
        self.cmdline = cmd
        ResizableEditDialog.__init__(self, title, tmpl)
        
    def OnInitDialog(self):
        rc = ResizableEditDialog.OnInitDialog(self)
        self.ok_btn = self.GetDlgItem(win32con.IDOK)
        self.thread1 = threading.Thread(target=self.run_program)
        self.thread1.start()

    def run_program(self):
        pop = subprocess.Popen(self.cmdline, 
                               shell=True,
                               stderr=subprocess.STDOUT,
                               stdout=subprocess.PIPE,
                               stdin=subprocess.PIPE)

        bytes = 0
        print "popen begin"
        self.ok_btn.EnableWindow(False) # disable OK button
        try:
            line = 0
            blocksize = 1024
            while pop.poll() == None:
                if line < 100:
                    out = pop.stdout.readline()
                    line += 1
                else:
                    out = pop.stdout.read(blocksize)
                    if blocksize < 1024 * 50:
                        blocksize *= 2
                bytes += len(out)
                self.write(out)
            out = pop.stdout.read()
            bytes += len(out)
            self.write(out)
        except IOError:
            pass

        self.ok_btn.EnableWindow(True) # enable OK button
        print "popen end: bytes = ", bytes

def run(cmd, modal=False, title='Mercurial'):
    tmpl = dlg_template(300, 250)
    gui = PopenDialog(cmd, title, tmpl)
    if modal:
        gui.DoModal()
    else:
        gui.CreateWindow()
    
if __name__=='__main__':
    #dlg = parse(['-c', 'help', '--', '-v'])
    #dlg = parse(['-c', 'log', '--root', 'c:\hg\h1', '--', '-l1'])
    dlg = parse(['-c', 'commit', '--root', 'c:\hg\h1', '--', '-l1'])
    dlg.CreateWindow()

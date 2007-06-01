#
# Execute a Mercurial (Hg) command and show it's output on an MFC dialog.
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import subprocess
import threading
import win32ui
from pywin.framework.dlgappcore import AppDialog
import win32con
import win32api
import win32gui
import re
import thgutil
import os

dlgStatic = 130
dlgEdit = 129
dlgButton = 128

dlg_EDIT1 = 1001

class ResizableEditDialog(AppDialog): 
    def __init__(self, title="hg", tmpl=None):
        self.title = title
        if tmpl is None:
            tmpl = dlg_template()
        AppDialog.__init__(self, tmpl)

    def OnInitDialog(self): 
        rc = AppDialog.OnInitDialog(self)
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
    def __init__(self, cmd, title=None, tmpl=None, notify_list=[]):
        self.cmdline = cmd
        ResizableEditDialog.__init__(self, title, tmpl)
        self.notify_list = notify_list

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

        self._do_notify()
        self.ok_btn.EnableWindow(True) # enable OK button
        print "popen end: bytes = ", bytes

    def _do_notify(self):
        if not self.notify_list:
            return
        
        for f in self.notify_list:
            dir = os.path.isdir(f) and f or os.path.dirname(f)
            thgutil.shell_notify(dir)
        
def run(cmd, modal=False, title='Mercurial'):
    tmpl = dlg_template(300, 250)
    gui = PopenDialog(cmd, title, tmpl, notify_list=["c:\\hg\\h1\\f1"])
    if modal:
        gui.DoModal()
    else:
        gui.CreateWindow()
    
if __name__=='__main__':
    run('hg help -v')

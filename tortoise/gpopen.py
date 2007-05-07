#
# Execute a Mercurial (Hg) command and show it's output on an MFC dialog.
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import subprocess
import threading
import win32ui
from pywin.mfc.dialog import Dialog
import win32con
import win32api
import win32gui

dlgStatic = 130
dlgEdit = 129
dlgButton = 128

dlg_EDIT1 = 1001

class ResizableEditDialog(Dialog): 
    def OnInitDialog(self, title='Mercurial'): 
        rc = Dialog.OnInitDialog(self)
        self.HookMessage(self.OnSize, win32con.WM_SIZE)

        self.SetWindowText(title)
        self.outtext = self.GetDlgItem(dlg_EDIT1)
        self.outtext.SetReadOnly()
        ctrl = self.GetDlgItem(dlg_EDIT1)
        l, t, r, b = ctrl.GetWindowRect()
        l, t, r, b = self.ScreenToClient( (l, t, r, b ) )
        print "create: edit rect =", l, t, r, b 
 
        # set output window to use fixed font
        self.font = win32ui.CreateFont({'name': "Courier New", 'height': 14})
        self.outtext.SetFont(self.font);

    def write(self, msg):
        self.outtext.ReplaceSel(msg)

    def OnCreate(self, msg):
        print "Oncreate: ", msg
        rect = self.GetClientRect()
        print "dlg client rect = ", rect
 
    def _do_size(self, cx, cy, repaint = 1):
        print "cx = %d, cy = %d" % (cx, cy)
        
        # resize the textbox.
        ctrl = self.GetDlgItem(dlg_EDIT1)
        l, t, r, b = ctrl.GetWindowRect()
        l, t = self.ScreenToClient( (l,t) )
        r, b = self.ScreenToClient( (r,b) )
        print "resize: edit rect =", l, t, r, b 
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
    dlg.append([dlgButton,"OK", win32con.IDOK, (3, h -bh -2, bw, bh),
                    s | win32con.BS_PUSHBUTTON]) 

    return dlg
      
class OutputDialog:
    def __init__(self, title='Mercurial'):
        # create and dialog to show out from hg commands
        self.dlg = Dialog(win32ui.IDD_LARGE_EDIT)
        self.dlg.CreateWindow()
        self.dlg.SetWindowText(title)
        
        self.outtext = self.dlg.GetDlgItem(win32ui.IDC_EDIT1)
        self.outtext.SetReadOnly()

        # set output window to use fixed font
        self.font = win32ui.CreateFont({'name': "Courier New", 'height': 14})
        self.outtext.SetFont(self.font);

    def write(self, msg):
        self.outtext.ReplaceSel(msg)
    
class PopenThread:
    def __init__(self, cmd, gui=None):
        self.gui = gui or OutputDialog()

        # Set up the thread to do execute hg command
        self.running = 1
        self.cmdline = cmd
        self.thread1 = threading.Thread(target=self.run_program)
        self.thread1.start()

    def run_program(self):
        pop = subprocess.Popen(self.cmdline, 
                               shell=True,
                               stderr=subprocess.STDOUT,
                               stdout=subprocess.PIPE,
                               stdin=subprocess.PIPE)

        try:
            print "checking popen"
            while pop.poll() == None:
                print "reading pop"
                out = pop.stdout.readline()
                self.out_text(out)
            print "popen closed"
            out = pop.stdout.read()
            self.out_text(out)
        except IOError:
            pass
        
        print "done runProgram"

    def out_text(self, msg):
        if msg:
            self.gui.write(msg)

def run(cmd):
    tmpl = dlg_template(300, 250)
    gui = ResizableEditDialog(tmpl)
    gui.CreateWindow()

    PopenThread(cmd, gui=gui)
    
if __name__ == "__main__":
    #gui = OutputDialog("Hg help")
    run(['C:\Python24\Scripts\hg.bat', 'help'])
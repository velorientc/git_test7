#
# Execute a Mercurial (Hg) command and show it's output on an MFC dialog.
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import subprocess
import threading
import win32ui
from pywin.mfc.dialog import Dialog
        
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

if __name__ == "__main__":
    #gui = OutputDialog("Hg help")
    PopenThread(['C:\Python24\Scripts\hg.bat', 'help'], gui=None)
# Creates a task-bar icon.  Run from Python.exe to see the
# messages printed.

from win32api import *
from win32gui import *
import win32ui
import win32pipe
import win32con
import pywintypes
import sys, os

from thgutil import thread2
from win32 import rpcserver

APP_TITLE = "TortoiseHg RPC server"

class MainWindow:
    def __init__(self):
        msg_TaskbarRestart = RegisterWindowMessage("TaskbarCreated");
        message_map = {
                msg_TaskbarRestart: self.OnRestart,
                win32con.WM_DESTROY: self.OnDestroy,
                win32con.WM_COMMAND: self.OnCommand,
                win32con.WM_USER+20 : self.OnTaskbarNotify,
        }
        # Register the Window class.
        wc = WNDCLASS()
        hinst = wc.hInstance = GetModuleHandle(None)
        wc.lpszClassName = "THgRpcServer"
        wc.style = win32con.CS_VREDRAW | win32con.CS_HREDRAW;
        wc.hCursor = LoadCursor( 0, win32con.IDC_ARROW )
        wc.hbrBackground = win32con.COLOR_WINDOW
        wc.lpfnWndProc = message_map # could also specify a wndproc.
        classAtom = RegisterClass(wc)
        # Create the Window.
        style = win32con.WS_OVERLAPPED | win32con.WS_SYSMENU
        self.hwnd = CreateWindow( classAtom, APP_TITLE, style, \
                0, 0, win32con.CW_USEDEFAULT, win32con.CW_USEDEFAULT, \
                0, 0, hinst, None)
        UpdateWindow(self.hwnd)
        self._DoCreateIcons()

    def _DoCreateIcons(self):
        # Try and find a custom icon
        hinst =  GetModuleHandle(None)
        from thgutil.paths import get_tortoise_icon
        iconPathName = get_tortoise_icon("hg.ico")
        if os.path.isfile(iconPathName):
            icon_flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
            hicon = LoadImage(hinst, iconPathName, win32con.IMAGE_ICON, 0, 0, icon_flags)
        else:
            print "Can't find a Python icon file - using default"
            hicon = LoadIcon(0, win32con.IDI_APPLICATION)

        flags = NIF_ICON | NIF_MESSAGE | NIF_TIP
        nid = (self.hwnd, 0, flags, win32con.WM_USER+20, hicon, APP_TITLE)
        try:
            Shell_NotifyIcon(NIM_ADD, nid)
        except error:
            # This is common when windows is starting, and this code is hit
            # before the taskbar has been created.
            print "Failed to add the taskbar icon - is explorer running?"
            # but keep running anyway - when explorer starts, we get the
            # TaskbarCreated message.

        # start namepipe server for hg status
        self.start_pipe_server()

    def OnRestart(self, hwnd, msg, wparam, lparam):
        self._DoCreateIcons()

    def OnDestroy(self, hwnd, msg, wparam, lparam):
        nid = (self.hwnd, 0)
        Shell_NotifyIcon(NIM_DELETE, nid)
        PostQuitMessage(0) # Terminate the app.

    def OnTaskbarNotify(self, hwnd, msg, wparam, lparam):
        if lparam==win32con.WM_RBUTTONUP or lparam==win32con.WM_LBUTTONUP:
            menu = CreatePopupMenu()
            AppendMenu(menu, win32con.MF_STRING, 1023, 'Options...')
            AppendMenu(menu, win32con.MF_SEPARATOR, 0, '')
            AppendMenu(menu, win32con.MF_STRING, 1025, 'Exit' )
            pos = GetCursorPos()
            # See http://msdn.microsoft.com/library/default.asp?url=/library/en-us/winui/menus_0hdi.asp
            SetForegroundWindow(self.hwnd)
            TrackPopupMenu(menu, win32con.TPM_LEFTALIGN, pos[0], pos[1], 0, self.hwnd, None)
            PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
        return 1

    def OnCommand(self, hwnd, msg, wparam, lparam):
        id = LOWORD(wparam)
        if id == 1023:
            # place holder for options dialog
            msg = "TortoiseHG options dialog in construction"
            win32ui.MessageBox(msg, 'TortoiseHG options...', win32con.MB_OK)
        elif id == 1025:
            self.exit_application()
        else:
            print "Unknown command -", id

    def exit_application(self):
        if self.stop_pipe_server():
            DestroyWindow(self.hwnd)
            print "Goodbye"
    
    def stop_pipe_server(self):
        print "Stopping pipe server..."
        if not self.pipethread.isAlive():
            return True

        # Try the nice way first
        self.svc.SvcStop()

        max_try = 10
        cnt = 1
        while cnt <= max_try and self.pipethread.isAlive():
            print "testing pipe [try %d] ..." % cnt
            try:
                self.pipethread.terminate()
                win32pipe.CallNamedPipe(rpcserver.PIPENAME, '',
                        rpcserver.PIPEBUFSIZE, 0)
            except:
                pass
            cnt += 1
            
        if self.pipethread.isAlive():
            print "WARNING: unable to stop server after %d trys." % max_try
            return False
        else:
            return True


    def start_pipe_server(self):
        def servepipe():
            self.svc = rpcserver.PipeServer()
            self.svc.SvcDoRun()

        self.pipethread = thread2.Thread(target=servepipe)
        self.pipethread.start()

def main():
    w=MainWindow()
    PumpMessages()

if __name__=='__main__':
    main()

# Creates a task-bar icon.  Run from Python.exe to see the
# messages printed.

import gc
import os
import sys
import time
import threading
import Queue

from win32api import *
from win32gui import *

import win32pipe
import win32con
import win32event
import win32file
import winerror
import pywintypes

from mercurial import demandimport
demandimport.ignore.append('win32com.shell')
demandimport.enable()
from mercurial import ui
from thgutil import thread2, paths, shlib

if hasattr(sys, "frozen"):
    sys.stdout.closed = True
    sys.stderr.closed = True

APP_TITLE = "TortoiseHg RPC server"

SHOWLOG_CMD = 1023
EXIT_CMD = 1025

def SetIcon(hwnd, name):
    # Try and find a custom icon
    hinst =  GetModuleHandle(None)
    from thgutil.paths import get_tortoise_icon
    iconPathName = get_tortoise_icon("hgB.ico")
    if iconPathName and os.path.isfile(iconPathName):
        icon_flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
        hicon = LoadImage(hinst, iconPathName, win32con.IMAGE_ICON, 0, 0, icon_flags)
    else:
        print "Can't find a Python icon file - using default"
        hicon = LoadIcon(0, win32con.IDI_APPLICATION)

    flags = NIF_ICON | NIF_MESSAGE | NIF_TIP
    nid = (hwnd, 0, flags, win32con.WM_USER+20, hicon, APP_TITLE)
    try:
        Shell_NotifyIcon(NIM_ADD, nid)
    except error:
        # This is common when windows is starting, and this code is hit
        # before the taskbar has been created.
        print "Failed to add the taskbar icon - is explorer running?"
        # but keep running anyway - when explorer starts, we get the
        # TaskbarCreated message.

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
        self.guithread = None
        self._DoCreateIcons()

    def _DoCreateIcons(self):
        SetIcon(self.hwnd, "hg.ico")
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
            AppendMenu(menu, win32con.MF_STRING, SHOWLOG_CMD, 'Options...')
            AppendMenu(menu, win32con.MF_SEPARATOR, 0, '')
            AppendMenu(menu, win32con.MF_STRING, EXIT_CMD, 'Exit' )
            pos = GetCursorPos()
            # See http://msdn.microsoft.com/library/default.asp?url=/library/en-us/winui/menus_0hdi.asp
            SetForegroundWindow(self.hwnd)
            TrackPopupMenu(menu, win32con.TPM_LEFTALIGN, pos[0], pos[1], 0, self.hwnd, None)
            PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
        return 1

    def OnCommand(self, hwnd, msg, wparam, lparam):
        id = LOWORD(wparam)
        if id == SHOWLOG_CMD:
            if not self.guithread or not self.guithread.isAlive():
                self.launchgui()
            else:
                print "TortoiseHG options dialog already running"
        elif id == EXIT_CMD:
            self.exit_application()
        else:
            print "Unknown command -", id

    def exit_application(self):
        if self.stop_pipe_server():
            DestroyWindow(self.hwnd)
        if self.guithread and self.guithread.isAlive():
            import gobject
            gobject.idle_add(self.dialog.destroy)
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
                win32pipe.CallNamedPipe(PIPENAME, '', PIPEBUFSIZE, 0)
            except:
                pass
            cnt += 1
            
        if self.pipethread.isAlive():
            print "WARNING: unable to stop server after %d trys." % max_try
            return False
        else:
            return True

    def launchgui(self):
        def launch():
            import gtk
            from hggtk import taskbarui, hgtk
            dlg = taskbarui.TaskBarUI(logger.getqueue(), requests)
            dlg.show_all()
            dlg.connect('destroy', gtk.main_quit)
            self.dialog = dlg
            gtk.gdk.threads_init()
            gtk.gdk.threads_enter()
            gtk.main()
            gtk.gdk.threads_leave()
            logger.reset()

        self.guithread = thread2.Thread(target=launch)
        self.guithread.start()

    def start_pipe_server(self):
        def servepipe():
            self.svc = PipeServer()
            self.svc.SvcDoRun()

        self.pipethread = thread2.Thread(target=servepipe)
        self.pipethread.start()


PIPENAME = r"\\.\pipe\TortoiseHgRpcServer-bc0c27107423-"
PIPENAME += GetUserName()

PIPEBUFSIZE = 4096

class Logger():
    def __init__(self):
        self.q = None

    def getqueue(self):
        self.q = Queue.Queue()
        return self.q

    def reset(self):
        self.q = None

    def msg(self, msg):
        ts = '[%s] ' % time.strftime('%c')
        if self.q:
            self.q.put(ts + msg)
            print 'L' + ts + msg
        else:
            print ts + msg

logger = Logger()

def getrepos(batch):
    roots = set()
    notifypaths = set()
    for path in batch:
        r = paths.find_root(path)
        if r is None:
            for n in os.listdir(path):
                r = paths.find_root(os.path.join(path, n))
                if (r is not None):
                    roots.add(r)
                    notifypaths.add(r)
        else:
            roots.add(r);
            notifypaths.add(path)
    return roots, notifypaths

def update_batch(batch):
    '''updates thgstatus for all paths in batch'''
    roots, notifypaths = getrepos(batch)
    if roots:
        _ui = ui.ui();
        failedroots = set()
        for r in sorted(roots):
            try:
                shlib.update_thgstatus(_ui, r, wait=False)
                shlib.shell_notify([r])
                logger.msg('Updated ' + r)
            except IOError:
                print "IOError on updating %s (check permissions)" % r
                logger.msg('Failed updating %s (check permissions)' % r)
                failedroots.add(r)
        notifypaths -= failedroots
        if notifypaths:
            time.sleep(2)
            shlib.shell_notify(list(notifypaths))
            logger.msg('Shell notified')

requests = Queue.Queue(0)

def update(args):
    batch = []
    r = args[0]
    print "got update request %s (first in batch)" % r
    batch.append(r)
    print "wait a bit for additional requests..."
    time.sleep(0.2)
    deferred_requests = []
    try:
        while True:
            req = requests.get_nowait()
            s = req.split('|')
            cmd, args = s[0], s[1:]
            if cmd == 'update':
                print "got update request %s" % req
                batch.append(args[0])
            else:
                deferred_requests.append(req)
    except Queue.Empty:
        pass
    for req in deferred_requests:
        requests.put(req)
    msg = "processing batch with %i update requests"
    print msg % len(batch)
    update_batch(batch)

def remove(args):
    path = args[0]
    logger.msg('Removing ' + path)
    roots, notifypaths = getrepos([path])
    if roots:
        for r in sorted(roots):
            try:
                os.remove(os.path.join(r, '.hg', 'thgstatus'))
            except OSError:
                pass
        if notifypaths:
            shlib.shell_notify(list(notifypaths))

def dispatch(req, cmd, args):
    print "dispatch(%s)" % req
    if cmd == 'update':
        update(args)
    elif cmd == 'remove':
        remove(args)
    else:
        logger.msg("Error: unknown request '%s'" % req)

class Updater(threading.Thread):
    def run(self):
        while True:
            req = requests.get()
            s = req.split('|')
            cmd, args = s[0], s[1:]
            if cmd == 'terminate':
                logger.msg('Updater thread terminating')
                return
            dispatch(req, cmd, args)
            gc.collect()

Updater().start()

class PipeServer:
    def __init__(self):
        # Create an event which we will use to wait on.
        # The "service stop" request will set this event.
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        
        # We need to use overlapped IO for this, so we dont block when
        # waiting for a client to connect.  This is the only effective way
        # to handle either a client connection, or a service stop request.
        self.overlapped = pywintypes.OVERLAPPED()
        
        # And create an event to be used in the OVERLAPPED object.
        self.overlapped.hEvent = win32event.CreateEvent(None,0,0,None)

    def SvcStop(self):
        print 'PipeServer thread terminating'
        win32event.SetEvent(self.hWaitStop)
        requests.put('terminate')

    def SvcDoRun(self):
        # We create our named pipe.
        pipeName = PIPENAME
        openMode = win32pipe.PIPE_ACCESS_DUPLEX | win32file.FILE_FLAG_OVERLAPPED
        pipeMode = win32pipe.PIPE_TYPE_MESSAGE

        # When running as a service, we must use special security for the pipe
        sa = pywintypes.SECURITY_ATTRIBUTES()
        # Say we do have a DACL, and it is empty
        # (ie, allow full access!)
        sa.SetSecurityDescriptorDacl ( 1, None, 0 )

        pipeHandle = win32pipe.CreateNamedPipe(pipeName,
            openMode,
            pipeMode,
            win32pipe.PIPE_UNLIMITED_INSTANCES,
            0, 0, 6000, # default buffers, and 6 second timeout.
            sa)

        # Loop accepting and processing connections
        while True:
            try:
                hr = win32pipe.ConnectNamedPipe(pipeHandle, self.overlapped)
            except pywintypes.error, inst:
                print "Error connecting pipe: ", inst
                pipeHandle.Close()
                break

            if hr==winerror.ERROR_PIPE_CONNECTED:
                # Client is fast, and already connected - signal event
                win32event.SetEvent(self.overlapped.hEvent)
            # Wait for either a connection, or a service stop request.
            timeout = win32event.INFINITE
            waitHandles = self.hWaitStop, self.overlapped.hEvent
            rc = win32event.WaitForMultipleObjects(waitHandles, 0, timeout)
            if rc==win32event.WAIT_OBJECT_0:
                # Stop event
                return
            else:
                # read pipe and process request
                try:
                    hr, data = win32file.ReadFile(pipeHandle, PIPEBUFSIZE)
                    if not data:
                        raise SystemExit  # signal by dispatch terminate
                    win32pipe.DisconnectNamedPipe(pipeHandle)
                except win32file.error:
                    # Client disconnected without sending data
                    # or before reading the response.
                    # Thats OK - just get the next connection
                    continue

                try:
                    requests.put(data)
                except SystemExit:
                    raise SystemExit # interrupted by thread2.terminate()
                except:
                    import traceback
                    print "WARNING: something went wrong in requests.put"
                    print traceback.format_exc()
                    status = "ERROR" 
        # Clean up when we exit
        self.SvcStop()

def main():
    w=MainWindow()
    PumpMessages()

if __name__=='__main__':
    main()

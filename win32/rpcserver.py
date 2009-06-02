import os
import win32api
import win32con

from win32com.shell import shell, shellcon
import _winreg

from mercurial import ui

from thgutil import paths, shlib

import sys
import time
import Queue
import threading

import win32event
import win32pipe
import win32file
import pywintypes
import winerror


PIPENAME = r"\\.\pipe\TortoiseHgRpcServer-bc0c27107423-"
PIPENAME += win32api.GetUserName()

PIPEBUFSIZE = 4096

logq = Queue.Queue(0)
def logmsg(msg):
    if logq.qsize() < 100:
        ts = '[%s] ' % time.strftime('%c')
        logq.put(ts + msg)

def update_batch(batch):
    '''updates thgstatus for all paths in batch'''
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
    if roots:
        _ui = ui.ui();
        for r in sorted(roots):
            logmsg('Updating ' + r)
            shlib.update_thgstatus(_ui, r, wait=False)
        if notifypaths:
            time.sleep(2)
            shlib.shell_notify(list(notifypaths))
            logmsg('Shell notified')

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

def dispatch(req, cmd, args):
    if cmd == 'update':
        update(args)
    else:
        logmsg("Error: unknown request '%s'" % req)

class Updater(threading.Thread):
    def run(self):
        while True:
            req = requests.get()
            s = req.split('|')
            cmd, args = s[0], s[1:]
            if cmd is 'terminate':
                logmsg('Updater thread terminating')
                return
            dispatch(req, cmd, args)

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

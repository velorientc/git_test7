import os
import win32api
import win32con
from win32com.shell import shell, shellcon
import _winreg
from mercurial import hg, cmdutil, util
from mercurial import repo as _repo
from thgutil import paths, shlib
import sys
import win32serviceutil
import win32service
import win32event
import win32pipe
import win32file
import pywintypes
import winerror

PIPENAME = "\\\\.\\pipe\\PyPipeService"
PIPEBUFSIZE = 4096

# FIXME: quick workaround traceback caused by missing "closed" 
# attribute in win32trace.
from mercurial import ui
def write_err(self, *args):
    for a in args:
        sys.stderr.write(str(a))
ui.ui.write_err = write_err

def update_thgstatus(path):
    print "update_thgstatus(%s)" % path
    root = paths.find_root(path)
    _ui = ui.ui();
    if root is not None:
        shlib.update_thgstatus(_ui, root, wait=False)
        shlib.shell_notify([path])
        print "updated repo %s" % root
    else:
        roots = []
        for f in os.listdir(path):
            r = paths.find_root(os.path.join(path, f))
            if r is not None:
                roots.append(r)
        for r in roots:
            shlib.update_thgstatus(_ui, r, wait=False)
            shlib.shell_notify([r])
            print "updated repo %s" % r
    print "update_thgstatus(%s) finished." % path

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
        while 1:
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
                break
            else:
                # read pipe and process request
                try:
                    hr, data = win32file.ReadFile(pipeHandle, PIPEBUFSIZE)
                    message = "Processed %d bytes: '%s'" % (len(data), data)
                    print (message)

                    if not data:
                        raise SystemExit  # signal by dispatch terminate

                    win32pipe.DisconnectNamedPipe(pipeHandle)
                except win32file.error:
                    # Client disconnected without sending data
                    # or before reading the response.
                    # Thats OK - just get the next connection
                    continue
                        
                try:
                    update_thgstatus(data)
                except SystemExit:
                    raise SystemExit # interrupted by thread2.terminate()
                except:
                    import traceback
                    print "WARNING: something went wrong in get_hg_state()"
                    print traceback.format_exc()
                    status = "ERROR" 

if __name__ == '__main__':
    import sys
    if '--server' in sys.argv:
        svc = PipeServer()
        svc.SvcDoRun()
    elif '--client' in sys.argv:
        for x in sys.argv[1:]:
            if x.startswith('-'):
                continue
            path = os.path.abspath(x)
            try:
                status = win32pipe.CallNamedPipe(PIPENAME, path, PIPEBUFSIZE, 0)
            except pywintypes.error, inst:
                print "can't access named pipe '%s'" % PIPENAME
                sys.exit()
            print "%s = %s" % (path, status)
    else:
        print "usage:\n%s [--server|--client]" % sys.argv[0]
        


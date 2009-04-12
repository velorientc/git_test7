import os
import win32api
import win32con
from win32com.shell import shell, shellcon
import _winreg
from mercurial import hg, cmdutil, util
from mercurial import repo as _repo
import thgutil
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

# file/directory status
UNCHANGED = "unchanged"
ADDED = "added"
MODIFIED = "modified"
UNKNOWN = "unknown"
NOT_IN_REPO = "n/a"

# file status cache
CACHE_TIMEOUT = 5000
overlay_cache = {}
cache_tick_count = 0
cache_root = None
cache_pdir = None

# some misc constants
S_OK = 0
S_FALSE = 1

def add_dirs(list):
    dirs = set()
    for f in list:
        dir = os.path.dirname(f)
        if dir in dirs:
            continue
        while dir:
            dirs.add(dir)
            dir = os.path.dirname(dir)
    list.extend(dirs)

def get_hg_state(upath):
    """
    Get the state of a given path in source control.
    """
    global overlay_cache, cache_tick_count
    global cache_root, cache_pdir
    
    #print "called: _get_state(%s)" % path
    tc = win32api.GetTickCount()
    
    try:
        # handle some Asian charsets
        path = upath.encode('mbcs')
    except:
        path = upath

    print "get_hg_state: path =", path
    if not path:
        return UNKNOWN

    # check if path is cached
    pdir = os.path.dirname(path)
    if cache_pdir == pdir and overlay_cache:
        if tc - cache_tick_count < CACHE_TIMEOUT:
            try:
                status = overlay_cache[path]
            except:
                status = UNKNOWN
            print "%s: %s (cached)" % (path, status)
            return status
        else:
            print "Timed out!!"
            overlay_cache.clear()

    # path is a drive
    if path.endswith(":\\"):
        overlay_cache[path] = UNKNOWN
        return NOT_IN_REPO

    # open repo
    if cache_pdir == pdir:
        root = cache_root
    else:
        print "find new root"
        cache_pdir = pdir
        cache_root = root = thgutil.find_root(pdir)
    print "_get_state: root = ", root
    if root is None:
        print "_get_state: not in repo"
        overlay_cache = {None : None}
        cache_tick_count = win32api.GetTickCount()
        return NOT_IN_REPO

    try:
        tc1 = win32api.GetTickCount()
        repo = hg.repository(ui.ui(), path=root)
        print "hg.repository() took %d ticks" % (win32api.GetTickCount() - tc1)

        # check if to display overlay icons in this repo
        global_opts = ui.ui().configlist('tortoisehg', 'overlayicons', [])
        repo_opts = repo.ui.configlist('tortoisehg', 'overlayicons', [])
        
        print "%s: global overlayicons = " % path, global_opts
        print "%s: repo overlayicons = " % path, repo_opts
        is_netdrive =  thgutil.netdrive_status(path) is not None
        if (is_netdrive and 'localdisks' in global_opts) \
                or 'False' in repo_opts:
            print "%s: overlayicons disabled" % path
            overlay_cache = {None : None}
            cache_tick_count = win32api.GetTickCount()
            return NOT_IN_REPO
    except _repo.RepoError:
        # We aren't in a working tree
        print "%s: not in repo" % dir
        overlay_cache[path] = UNKNOWN
        return NOT_IN_REPO

    # get file status
    tc1 = win32api.GetTickCount()

    modified, added, removed, deleted = [], [], [], []
    unknown, ignored, clean = [], [], []
    files = []
    try:
        matcher = cmdutil.match(repo, [pdir])
        modified, added, removed, deleted, unknown, ignored, clean = \
                repo.status(match=matcher, ignored=True, 
                        clean=True, unknown=True)

        # add directory status to list
        for grp in (clean,modified,added,removed,deleted,ignored,unknown):
            add_dirs(grp)
    except util.Abort, inst:
        print "abort: %s" % inst
        print "treat as unknown : %s" % path
        return UNKNOWN
    
    print "status() took %d ticks" % (win32api.GetTickCount() - tc1)
            
    # cached file info
    tc = win32api.GetTickCount()
    overlay_cache = {}
    for grp, st in (
            (ignored, UNKNOWN),
            (unknown, UNKNOWN),                
            (clean, UNCHANGED),
            (added, ADDED),
            (removed, MODIFIED),
            (deleted, MODIFIED),
            (modified, MODIFIED)):
        for f in grp:
            fpath = os.path.join(repo.root, os.path.normpath(f))
            overlay_cache[fpath] = st

    if path in overlay_cache:
        status = overlay_cache[path]
    else:
        status = overlay_cache[path] = UNKNOWN
    print "%s: %s" % (path, status)
    cache_tick_count = win32api.GetTickCount()
    return status

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

                    try:
                        data = data.decode('mbcs')
                    except:
                        pass
                        
                    try:
                        status = get_hg_state(data)
                    except SystemExit:
                        raise SystemExit # interrupted by thread2.terminate()
                    except:
                        import traceback
                        print "WARNING: something went wrong in get_hg_state()"
                        print traceback.format_exc()
                        status = "ERROR"

                    win32file.WriteFile(pipeHandle, status)
                    
                    # And disconnect from the client.
                    win32pipe.DisconnectNamedPipe(pipeHandle)
                except win32file.error:
                    # Client disconnected without sending data
                    # or before reading the response.
                    # Thats OK - just get the next connection
                    continue

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
        


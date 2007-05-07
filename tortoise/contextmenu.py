# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Jelmer Vernooij <jelmer@samba.org>
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>

import os
import pythoncom
from win32com.shell import shell, shellcon
import win32con
import win32process
import win32event
import win32ui
import win32gui
import win32gui_struct
import win32api
import _winreg
from mercurial import hg, ui, repo
import re
import gpopen

GUI_SHELL = 'guishell'

S_OK = 0
S_FALSE = 1

_quotere = None
def shellquote(s):
    global _quotere
    if _quotere is None:
        _quotere = re.compile(r'(\\*)("|\\$)')
    return '"%s"' % _quotere.sub(r'\1\1\\\2', s)
    return "'%s'" % s.replace("'", "'\\''")

def find_path(pgmname):
    """ return first executable found in search path """
    ospath = os.environ['PATH'].split(os.pathsep)
    pathext = os.environ.get('PATHEXT', '.COM;.EXE;.BAT;.CMD')
    pathext = pathext.lower().split(os.pathsep)

    for path in ospath:
        for ext in pathext:
            ppath = os.path.join(path, pgmname + ext)
            if os.path.exists(ppath):
                return ppath

    return None

def find_root(path):
    p = os.path.isdir(path) and path or os.path.dirname(path)
    while not os.path.isdir(os.path.join(p, ".hg")):
        oldp = p
        p = os.path.dirname(p)
        if p == oldp:
            return None
    return p

def get_clone_repo_name(dir, repo_name):
    dest_clone = os.path.join(dir, repo_name)
    if os.path.exists(dest_clone):
        dest_clone = os.path.join(dir, "Clone of " + repo_name)

    i = 2
    while os.path.exists(dest_clone):
        dest_clone = os.path.join(dir, "Clone of (%s) %s" % (i, repo_name))
        i += 1
    return dest_clone

def run_program(appName, cmdline):
    # subprocess.Popen() would create a terminal (cmd.exe) window when 
    # making calls to hg, we use CreateProcess() coupled with 
    # CREATE_NO_WINDOW flag to suppress the terminal window

    print "run_program: %s, %s" % (appName, cmdline)
    flags = win32con.CREATE_NO_WINDOW
    startupInfo = win32process.STARTUPINFO()
    
    handlers = win32process.CreateProcess(appName, 
                                            cmdline,
                                            None,
                                            None,
                                            1,
                                            flags,
                                            os.environ,
                                            os.getcwd(),
                                            startupInfo)
    hProcess, hThread, PId, TId = handlers
    win32event.WaitForSingleObject(hProcess, 500)
    exitcode = win32process.GetExitCodeProcess(hProcess)
    if exitcode < 0:
        msg = "Error when starting external command: \n%s " % cmdline
        title = "Mercurial"
        win32ui.MessageBox(msg, title, 
                           win32con.MB_OK|win32con.MB_ICONERROR)   

"""Windows shell extension that adds context menu items to Mercurial repository"""
class ContextMenuExtension:
    _reg_progid_ = "Mercurial.ShellExtension.ContextMenu"
    _reg_desc_ = "Mercurial Shell Extension"
    _reg_clsid_ = "{EEE9936B-73ED-4D45-80C9-AF918354F885}"
    _com_interfaces_ = [shell.IID_IShellExtInit, shell.IID_IContextMenu]
    _public_methods_ = [
        "Initialize", # From IShellExtInit
        "QueryContextMenu", "InvokeCommand", "GetCommandString" # IContextMenu
        ]

    registry_keys = [
        (_winreg.HKEY_CLASSES_ROOT, r"*\shellex\ContextMenuHandlers\TortoiseHg"),
        (_winreg.HKEY_CLASSES_ROOT, r"Directory\Background\shellex\ContextMenuHandlers\TortoiseHg"),
        (_winreg.HKEY_CLASSES_ROOT, r"Directory\shellex\ContextMenuHandlers\TortoiseHg"),
        (_winreg.HKEY_CLASSES_ROOT, r"Folder\shellex\ContextMenuHandlers\TortoiseHg"),
        ]

    def __init__(self):
        print "ContextMenuExtension: __init__ called"
        self._folder = None
        self._filenames = []
        self._handlers = {}

    def Initialize(self, folder, dataobj, hkey):
        print "Initialize: cwd = ", os.getcwd()
        if folder:
            self._folder = shell.SHGetPathFromIDList(folder)
            print "folder = ", self._folder

        if dataobj:
            format_etc = win32con.CF_HDROP, None, 1, -1, pythoncom.TYMED_HGLOBAL
            sm = dataobj.GetData(format_etc)
            num_files = shell.DragQueryFile(sm.data_handle, -1)
            for i in range(num_files):
                self._filenames.append(shell.DragQueryFile(sm.data_handle, i))

    def QueryContextMenu(self, hMenu, indexMenu, idCmdFirst, idCmdLast, uFlags):
        if uFlags & shellcon.CMF_DEFAULTONLY:
            return 0

        # only support Overlays In Explorer
        print "QueryContextMenu: checking if in explorer"
        modname = win32api.GetModuleFileName(win32api.GetModuleHandle(None))
        print "modname = %s" % modname
        if not modname.endswith("\\explorer.exe"):
            print "QueryContextMenu: not in explorer"
            return 0 

        # As we are a context menu handler, we can ignore verbs.
        self._handlers = {}
        if self._folder and self._filenames:
            commands = self._get_commands_dragdrop()
        else:
            commands = self._get_commands()
        if len(commands) > 0:
            # a brutal hack to detect if we are the first menu to go on to the 
            # context menu. If we are not the first, then add a menu separator
            # The number '30000' is just a guess based on my observation
            print "idCmdFirst = ", idCmdFirst
            if idCmdFirst >= 30000:
                win32gui.InsertMenu(hMenu, indexMenu,
                                    win32con.MF_SEPARATOR|win32con.MF_BYPOSITION,
                                    0, None)
                indexMenu += 1
            
            # create submenu with Hg commands
            submenu = win32gui.CreatePopupMenu()
            for id, menu_info in enumerate(commands):
                fstate = win32con.MF_BYCOMMAND
                enabled = True
                if len(menu_info) == 0:
                    win32gui.InsertMenu(submenu, id, 
                                        win32con.MF_BYPOSITION|win32con.MF_SEPARATOR, 
                                        0, None)
                    continue
                elif len(menu_info) == 4:
                    text, help_text, command, enabled = menu_info
                else:
                    text, help_text, command = menu_info

                if not enabled:
                    fstate |= win32con.MF_GRAYED
                
                item, extras = win32gui_struct.PackMENUITEMINFO(
                            text=text,
                            fState=fstate,
                            wID=idCmdFirst + id)
                win32gui.InsertMenuItem(submenu, id, 1, item)
                self._handlers[id] = (help_text, command)

            # add Hg submenu to context menu
            item, extras = win32gui_struct.PackMENUITEMINFO(text="TortoiseHg",
                                                            hSubMenu=submenu)
            win32gui.InsertMenuItem(hMenu, indexMenu, 1, item)
            indexMenu += 1

            # menu separator
            win32gui.InsertMenu(hMenu, indexMenu,
                                win32con.MF_SEPARATOR|win32con.MF_BYPOSITION,
                                0, None)
            indexMenu += 1

        # Return the number of commands we added
        return len(commands)

    def _get_commands_dragdrop(self):
        """
        Get a list of commands valid for the current selection.

        Each command is a tuple containing (display text, handler).
        """
        
        print "_get_commands_dragdrop() on %s" % ", ".join(self._filenames)        

        # we can only accept dropping one item
        if len(self._filenames) > 1:
            return []

        def _open_repo(path):
            u = ui.ui()
            root = find_root(path)
            if root:
                try:
                    repo = hg.repository(u, path=root)
                    return repo
                except repo.RepoError:
                    pass

            return None

        # open repo
        drag_repo = None
        drop_repo = None
        
        print "drag = %s" % self._filenames[0]
        print "drop = %s" % self._folder
        
        drag_path = self._filenames[0]
        drag_repo = _open_repo(drag_path)
        if not drag_repo:
            return []
        if drag_repo and drag_repo.root != drag_path:
            return []   # dragged item must be a hg repo root directory
        print "drag root = %s" % drag_repo.root

        drop_repo = _open_repo(self._folder)

        print "_get_commands_dragdrop(): adding hg commands"
        
        result = []
        result.append((_("Create Clone"), 
                       _("Create clone here from source"),
                       self._clone_here))

        if drop_repo:
            print "_get_commands_dragdrop(): drop zone is a hg repo too"
            print "drop root = %s" % drag_repo.root
            result.append((_("Push to"), 
                           _("Push source into the repo here"),
                           self._push_here))
        return result
        
    def _get_commands(self):
        """
        Get a list of commands valid for the current selection.

        Each command is a tuple containing (display text, handler).
        """
        
        print "_get_commands() on %s" % ", ".join(self._filenames)        

        # open repo
        tree = None
        u = ui.ui()
        rpath = self._folder or self._filenames[0]
        root = find_root(rpath)
        if root is None:
            print "%s: not in repo" % rpath
            return []

        print "file = %s\nroot = %s" % (rpath, root)
        
        try:
            tree = hg.repository(u, path=root)
        except repo.RepoError:
            print "%s: can't repo" % dir
            return []

        print "_get_commands(): adding hg commands"
        
        result = []
        if tree is not None:
            # commit tool - enabled by extensions.qct
            status = not u.config("extensions", "qct") is None
            result.append((_("Commit tool"), 
                           _("commit changes with GUI tool"),
                           self._commit,
                           status))

            # hgk - enabled by extensions.hgk
            status = not u.config("extensions", "hgk") is None
            result.append((_("View"),
                           _("View history with GUI tool"),
                           self._view,
                           status))

            # diff tool - enabled by extensions.extdiff +  extdiff.cmd.vdiff
            status = not u.config("extensions", "extdiff") is None and \
                     u.config("extdiff", "cmd.vdiff")
            result.append((_("Visual diff"),
                           _("View changes using GUI diff tool"),
                           self._vdiff,
                           status))
                           
            result.append([])   # separator
            
            # Mercurial standard commands
            result.append((_("Status"),
                           _("Repository status"),
                           self._status))
            result.append((_("Diff"),
                           _("View changes"),
                           self._diff))
            result.append((_("Add"),
                           _("Add files to Hg repository"),
                           self._add))

            result.append([])   # separator

            result.append((_("Revert"),
                           _("Revert file status"),
                           self._revert))
            result.append((_("Rollback"),
                           _("Rollback the last transaction"),
                           self._rollback))

            result.append([])   # separator

            result.append((_("Tip"),
                           _("Show latest (tip) revision info"),
                           self._tip))
            result.append((_("Heads"),
                           _("Show all repository head changesets"),
                           self._heads))
            result.append((_("Parents"),
                           _("Show working directory's parent revisions"),
                           self._parents))
            result.append((_("Log"),
                           _("Show revision history"),
                           self._log))

            result.append([])   # separator

            result.append((_("Pull"),
                           _("Pull from default repository"),
                           self._pull))
            result.append((_("Push"),
                           _("Push to default repository"),
                           self._pull))

            result.append([])   # separator

            result.append((_("Help"),
                           _("Basic Mercurial help text"),
                           self._help))
        return result

    def InvokeCommand(self, ci):
        mask, hwnd, verb, params, dir, nShow, hotkey, hicon = ci
        if verb >> 16:
            # This is a textual verb invocation... not supported.
            return S_FALSE
        if verb not in self._handlers:
            raise Exception("Unsupported command id %i!" % verb)
        self._handlers[verb][1](hwnd)

    def GetCommandString(self, cmd, uFlags):
        if uFlags & shellcon.GCS_VALIDATEA or uFlags & shellcon.GCS_VALIDATEW:
            if cmd in self._handlers:
                return S_OK
            return S_FALSE
        if uFlags & shellcon.GCS_VERBA or uFlags & shellcon.GCS_VERBW:
            return S_FALSE
        if uFlags & shellcon.GCS_HELPTEXTA or uFlags & shellcon.GCS_HELPTEXTW:
            # The win32com.shell implementation encodes the resultant
            # string into the correct encoding depending on the flags.
            return self._handlers[cmd][0]
        return S_FALSE

    def _commit(self, parent_window):
        hgpath = find_path('hg')
        if hgpath:
            targets = self._filenames or [self._folder]
            root = find_root(targets[0])
            cmd = "%s --repository %s qct" % (hgpath, shellquote(root))
            run_program(hgpath, cmd)

    def _vdiff(self, parent_window):
        hgpath = find_path('hg')
        if hgpath:
            targets = self._filenames or [self._folder]
            root = find_root(targets[0])
            quoted_files = [shellquote(s) for s in targets]
            cmd = "%s --repository %s vdiff %s" % (hgpath, 
                    shellquote(root), " ".join(quoted_files))
            run_program(hgpath, cmd)

    def _view(self, parent_window):
        hgpath = find_path('hg')
        if hgpath:
            targets = self._filenames or [self._folder]
            root = find_root(targets[0])
            cmd = "%s --repository %s view" % (hgpath, shellquote(root))
            run_program(hgpath, cmd)

    def _clone_here(self, parent_window):
        src = self._filenames[0]
        dest = self._folder
        msg = "Create clone for %s in %s?" % (src, dest)
        title = "Mercurial: clone"
        rv = win32ui.MessageBox(msg, title, win32con.MB_OKCANCEL)
        if rv == 2:
            return

        exepath = find_path(GUI_SHELL)
        if exepath:
            repo_name = os.path.basename(src)
            dest_clone = get_clone_repo_name(dest, repo_name)
            cmdline = "%s hg --verbose clone %s %s" % (
                            exepath, 
                            shellquote(src),
                            shellquote(dest_clone))
            run_program(exepath, cmdline)
            

    def _push_here(self, parent_window):
        src = self._filenames[0]
        dest = self._folder
        msg = "Push changes from %s into %s?" % (src, dest)
        title = "Mercurial: push"
        rv = win32ui.MessageBox(msg, title, win32con.MB_OKCANCEL)
        if rv == 2:
            return

        exepath = find_path(GUI_SHELL)
        if exepath:
            cmdline = "%s hg --verbose --repository %s push %s" % (
                            exepath, 
                            shellquote(src),
                            shellquote(dest))
            run_program(exepath, cmdline)

    def _status(self, parent_window):
        self._run_program_with_guishell('status')

    def _pull(self, parent_window):
        self._run_program_with_guishell('pull', True)

    def _push(self, parent_window):
        self._run_program_with_guishell('push', True)

    def _add(self, parent_window):
        self._run_program_with_guishell('add')
            
    def _revert(self, parent_window):
        targets = self._filenames or [self._folder]
        msg = "Confirm reverting: %s" % ", ".join(targets)
        title = "Mercurial: revert"
        rv = win32ui.MessageBox(msg, title, win32con.MB_OKCANCEL)
        if rv == 1:
            self._run_program_with_guishell('revert')
 
    def _tip(self, parent_window):
        self._run_program_with_guishell('tip', True)

    def _parents(self, parent_window):
        self._run_program_with_guishell('parent', True)

    def _heads(self, parent_window):
        self._run_program_with_guishell('heads', True)

    def _log(self, parent_window):
        self._run_program_with_guishell('log', True)

    def _diff(self, parent_window):
        self._run_program_with_guishell('diff')

    def _rollback(self, parent_window):
        targets = self._filenames or [self._folder]
        root = find_root(targets[0])
        msg = "Confirm rollback: %s" % root
        title = "Mercurial: rollback"
        rv = win32ui.MessageBox(msg, title, win32con.MB_OKCANCEL)
        if rv == 1:
            self._run_program_with_guishell('rollback', True)

    def _run_program_with_guishell(self, hgcmd, noargs=False):
        exepath = find_path(GUI_SHELL)
        if exepath:
            targets = self._filenames or [self._folder]
            root = find_root(targets[0])
            quoted_files = []
            if noargs == False:
                quoted_files = [shellquote(s) for s in targets]
            cmdline = "%s hg --repository %s --verbose %s %s" % (
                            exepath, 
                            shellquote(root),
                            hgcmd,
                            " ".join(quoted_files))
            run_program(exepath, cmdline)

    def _help(self, parent_window):
        gpopen.run(['hg', 'help', '--verbose'])

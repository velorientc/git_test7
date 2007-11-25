# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Jelmer Vernooij <jelmer@samba.org>
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

import os
import tempfile
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
from thgutil import *

S_OK = 0
S_FALSE = 1

def open_dialog(cmd, cmdopts='', cwd=None, root=None, filelist=[], title=None, notify=False):
    app_path = find_path("hgproc", get_prog_root(), '.EXE;.BAT')
    print "proc app = ", app_path

    if filelist:
        fd, tmpfile = tempfile.mkstemp(prefix="tortoisehg_filelist_")
        os.write(fd, "\n".join(filelist))
        os.close(fd)

    # start gpopen
    gpopts = "--command %s" % cmd
    if root:
        gpopts += " --root %s" % shellquote(root)
    if filelist:
        gpopts += " --listfile %s --deletelistfile" % (shellquote(tmpfile))
    if notify:
        gpopts += " --notify"
    if title:
        gpopts += " --title %s" % shellquote(title)
    if cwd:
        gpopts += " --cwd %s" % shellquote(cwd)

    cmdline = '%s %s -- %s' % (shellquote(app_path), gpopts, cmdopts)

    try:
        run_program(cmdline)
    except win32api.error, details:
        win32ui.MessageBox("Error executing command - %s" % (details), "gpopen")
    print "open_dialog: done"

def get_clone_repo_name(dir, repo_name):
    dest_clone = os.path.join(dir, repo_name)
    if os.path.exists(dest_clone):
        dest_clone = os.path.join(dir, "Clone of " + repo_name)

    i = 2
    while os.path.exists(dest_clone):
        dest_clone = os.path.join(dir, "Clone of (%s) %s" % (i, repo_name))
        i += 1
    return dest_clone

def run_program(cmdline):
    print "run_program: %s" % (cmdline)

    import subprocess
    pop = subprocess.Popen(cmdline, 
                           shell=False,
                           creationflags=win32con.CREATE_NO_WINDOW,
                           stderr=subprocess.STDOUT,
                           stdout=subprocess.PIPE,
                           stdin=subprocess.PIPE)
    print "run_program: done"
    
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
        (_winreg.HKEY_CLASSES_ROOT, r"Directory\shellex\DragDropHandlers\TortoiseHg"),
        (_winreg.HKEY_CLASSES_ROOT, r"Folder\shellex\DragDropHandlers\TortoiseHg"),
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

    def create_submenu(self, commands, idCmd, idCmdFirst):
        menu = win32gui.CreatePopupMenu()
        for menu_info in commands:
            fstate = win32con.MF_BYCOMMAND
            if len(menu_info) == 0:
                win32gui.InsertMenu(menu, idCmd, 
                        win32con.MF_BYPOSITION|win32con.MF_SEPARATOR, 
                        idCmdFirst + idCmd, None)
                idCmd += 1
                continue
            elif len(menu_info) == 2:
                text, subcommands = menu_info
                submenu, idCmd = self.create_submenu(subcommands, idCmd, idCmdFirst)
                item, _ = win32gui_struct.PackMENUITEMINFO(
                        text=text, hSubMenu=submenu, wID=idCmdFirst + idCmd)
                win32gui.InsertMenuItem(menu, idCmdFirst + idCmd, True, item)
                self._handlers[idCmd] = ("", lambda x,y: 0)
                idCmd += 1
                continue
            elif len(menu_info) == 4:
                text, help_text, command, enabled = menu_info
                if not enabled: fstate |= win32con.MF_GRAYED
            elif len(menu_info) == 3:
                text, help_text, command = menu_info
                
            item, _ = win32gui_struct.PackMENUITEMINFO(
                        text=text, fState=fstate, wID=idCmdFirst + idCmd)
            win32gui.InsertMenuItem(menu, idCmdFirst+idCmd, True, item)
            self._handlers[idCmd] = (help_text, command)
            idCmd += 1
        return (menu, idCmd)

    def QueryContextMenu(self, hMenu, indexMenu, idCmdFirst, idCmdLast, uFlags):
        if uFlags & shellcon.CMF_DEFAULTONLY:
            return 0

        # only support Overlays In Explorer
        print "QueryContextMenu: checking if in explorer"
        modname = win32api.GetModuleFileName(win32api.GetModuleHandle(None))
        print "modname = %s" % modname
        if not modname.lower().endswith("\\explorer.exe"):
            print "QueryContextMenu: not in explorer"
            return 0 

        # As we are a context menu handler, we can ignore verbs.
        self._handlers = {}
        if self._folder and self._filenames:
            commands = self._get_commands_dragdrop()
        else:
            commands = self._get_commands()
        idCmd = 0
        if len(commands) > 0:
            # a brutal hack to detect if we are the first menu to go on to the 
            # context menu. If we are not the first, then add a menu separator
            # The number '30000' is just a guess based on my observation
            print "idCmdFirst = ", idCmdFirst
            if idCmdFirst >= 30000:
                win32gui.InsertMenu(hMenu, indexMenu,
                                    win32con.MF_SEPARATOR|win32con.MF_BYPOSITION,
                                    idCmdFirst+idCmd, None)
                indexMenu += 1
                idCmd += 1
            
            # create submenus with Hg commands
            submenu, idCmd = self.create_submenu(commands, idCmd, idCmdFirst)

            # add Hg submenus to context menu
            opt = {'text': "TortoiseHg", 'hSubMenu': submenu, 'wID': idCmdFirst+idCmd}
            icon_path = get_icon_path("tortoise", "hg.ico")
            print "icon path =", icon_path
            if icon_path:
                opt['hbmpChecked'] = opt['hbmpUnchecked'] = \
                                     icon_to_bitmap(icon_path, type="MENUCHECK")
            item, extras = win32gui_struct.PackMENUITEMINFO(**opt)
            win32gui.InsertMenuItem(hMenu, indexMenu, True, item)
            
            # a submenu item need a (dummay) handler too 
            self._handlers[idCmd] = ("", lambda x,y: 0)
            
            indexMenu += 1
            idCmd += 1

            # menu separator
            win32gui.InsertMenu(hMenu, indexMenu,
                                win32con.MF_SEPARATOR|win32con.MF_BYPOSITION,
                                idCmdFirst+idCmd, None)
            indexMenu += 1
            idCmd += 1

        # Return total number of menus & submenus we've added
        return idCmd

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
            result.append((_("Pull from"), 
                           _("Pull new change from dragged repo"),
                           self._pull_here))
            result.append((_("Incoming"), 
                           _("show new changesets found in source"),
                           self._incoming_here))
            result.append((_("Outgoing"), 
                           _("show changesets not found in destination"),
                           self._outgoing_here))
        return result
        
    def _get_commands(self):
        """
        Get a list of commands valid for the current selection.

        Each command is a tuple containing (display text, handler).
        """
        
        print "_get_commands() on %s" % ", ".join(self._filenames)        

        # open repo
        result = []
        tree = None
        u = ui.ui()
        rpath = self._folder or self._filenames[0]
        root = find_root(rpath)
        if root is None:
            print "%s: not in repo" % rpath
            result.append((_("Create repo here"),
                           _("create a new repository in this directory"),
                           self._init))
            result.append((_("Clone a repository"),
                           _("clone a repository"),
                           self._clone))
            return result

        print "file = %s\nroot = %s" % (rpath, root)
        
        try:
            tree = hg.repository(u, path=root)
        except repo.RepoError:
            print "%s: can't open repo" % dir
            return []

        print "_get_commands(): adding hg commands"
        
        if tree is not None:
            # Visual Diff (any extdiff command)
            result.append((_("Visual diff"),
                           _("View changes using GUI diff tool"),
                           self._vdiff))
                           
            # Commit (qct, gcommit, or internal)
            result.append((_("Commit"), 
                           _("Commit changes with GUI tool"),
                           self._commit))

            # Working directory status (gstatus, internal)
            result.append((_("Status"),
                           _("Repository status"),
                           self._status))

            # Mercurial standard commands
            result.append((_("Diff"),
                           _("View changes"),
                           self._diff))
            result.append((_("Add"),
                           _("Add files to Hg repository"),
                           self._add))
            result.append((_("Remove"),
                           _("Remove selected files on the next commit"),
                           self._remove))
            result.append((_("Revert"),
                           _("Revert selected files"),
                           self._revert))

            result.append([])   # separator

            result.append((_("Rollback"),
                           _("Rollback the last transaction"),
                           self._rollback))
            result.append((_("Update"),
                           _("update working directory"),
                           self._update))
            result.append((_("Merge"),
                           _("merge working directory with another revision"),
                           self._merge))

            result.append([])   # separator

            # Visual history (hgk, hgview, glog, or internal)
            result.append((_("View history"),
                           _("View history with GUI tool"),
                           self._view))

            result.append((_("Current revision status..."),
                           _("Show various revision info"),
                           self._tip))

            result.append([])   # separator

            result.append((_("View Tags"),
                           _("list repository tags"),
                           self._show_tags))
            result.append((_("Add Tag"),
                           _("add a tag for the current or given revision"),
                           self._add_tag))

            result.append([])   # separator

            result.append((_("Clone a repository"),
                           _("Clone a repository"),
                           self._clone))
            result.append((_("Pull"),
                           _("Pull from default repository"),
                           self._pull))
            result.append((_("Push"),
                           _("Push to default repository"),
                           self._push))
            result.append((_("Incoming"),
                           _("show new changesets found in source"),
                           self._incoming))
            result.append((_("Outgoing"),
                           _("show changesets not found in destination"),
                           self._outgoing))

            result.append([])   # separator

            # Optionally add an Options submenu
            c = ui.ui().config('tortoisehg', 'hgconfig', None)
            if c in ['1', 'yes', 'True']:
                config = []
                config.append((_("Username"),
                    _("Configure username"),
                    self._uname))
                config.append((_("Paths"),
                    _("Configure remote paths"),
                    self._paths))
                config.append((_("Web"),
                    _("Configure repository web data"),
                    self._web))
                result.append((_("Options"), config))
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
        '''[tortoisehg] commit = [qct | gcommit | internal]'''
        ct = ui.ui().config('tortoisehg', 'commit', 'internal')
        if ct == 'internal':
            self._commit_simple(parent_window)
            return
        hgpath = find_path('hg')
        if hgpath:
            targets = self._filenames or [self._folder]
            root = find_root(targets[0])
            cmd = "%s --repository %s %s" % \
                    (shellquote(hgpath), shellquote(root), ct)
            run_program(cmd)

    def _uname(self, parent_window):
        hgpath = find_path('hg')
        if not hgpath: return
        targets = self._filenames or [self._folder]
        root = find_root(targets[0])
        cmd = "%s --repository %s config username" % (shellquote(hgpath), 
                shellquote(root))
        run_program(cmd)

    def _paths(self, parent_window):
        hgpath = find_path('hg')
        if not hgpath: return
        targets = self._filenames or [self._folder]
        root = find_root(targets[0])
        cmd = "%s --repository %s config paths" % (shellquote(hgpath), 
                shellquote(root))
        run_program(cmd)

    def _web(self, parent_window):
        hgpath = find_path('hg')
        if not hgpath: return
        targets = self._filenames or [self._folder]
        root = find_root(targets[0])
        cmd = "%s --repository %s config web" % (shellquote(hgpath), 
                shellquote(root))
        run_program(cmd)

    def _vdiff(self, parent_window):
        '''[tortoisehg] vdiff = <any extdiff command>'''
        diff = ui.ui().config('tortoisehg', 'vdiff', None)
        if not diff:
            msg = "You must configure tortoisehg.vdiff in your Mercurial.ini"
            title = "Visual Diff Not Configured"
            win32ui.MessageBox(msg, title, win32con.MB_OK|win32con.MB_ICONERROR)
            return
        hgpath = find_path('hg')
        if hgpath:
            targets = self._filenames or [self._folder]
            root = find_root(targets[0])
            quoted_files = [shellquote(s) for s in targets]
            cmd = "%s --repository %s %s %s" %  \
                (shellquote(hgpath), shellquote(root),
                   diff, " ".join(quoted_files))
            run_program(cmd)

    def _view(self, parent_window):
        '''[tortoisehg] view = [hgk | hgvew | glog | internal]'''
        view = ui.ui().config('tortoisehg', 'view', 'internal')
        targets = self._filenames or [self._folder]
        root = find_root(targets[0])
        if view == 'internal':
            self._log(parent_window)
        elif view == 'hgview':
            hgviewpath = find_path('hgview')
            cmd = "%s --repository=%s" % \
                    (shellquote(hgviewpath), shellquote(root))
            if len(self._filenames) == 1:
                cmd += " --file=%s" % shellquote(self._filenames[0])
            run_program(cmd)
        else:
            hgpath = find_path('hg')
            if not hgpath: return
            if view == 'hgk':
                cmd = "%s --repository %s view" % \
                        (shellquote(hgpath), shellquote(root))
                run_program(cmd)
            elif view == 'glog':
                quoted_files = [shellquote(s) for s in targets]
                cmd = "%s --repository %s glog %s" % \
                        (shellquote(hgpath), shellquote(root),
                         " ".join(quoted_files))
                run_program(cmd)
            else:
                msg = "History viewer %s not recognized" % view
                title = "Unknown history tool"
                win32ui.MessageBox(msg, title, win32con.MB_OK|win32con.MB_ICONERROR)

    def _clone_here(self, parent_window):
        src = self._filenames[0]
        dest = self._folder
        repo_name = os.path.basename(src)
        dest_clone = get_clone_repo_name(dest, repo_name)
        cmdopts = "--verbose"
        repos = [src, dest_clone]
        open_dialog('clone', cmdopts, cwd=dest, filelist=repos)

    def _push_here(self, parent_window):
        src = self._filenames[0]
        dest = self._folder
        msg = "Push changes from %s into %s?" % (src, dest)
        title = "Mercurial: push"
        rv = win32ui.MessageBox(msg, title, win32con.MB_OKCANCEL)
        if rv == 2:
            return

        cmdopts = "--verbose"
        open_dialog('push', cmdopts, root=src, filelist=[dest])

    def _pull_here(self, parent_window):
        src = self._filenames[0]
        dest = self._folder
        msg = "Pull changes from %s?" % (src)
        title = "Mercurial: pull"
        rv = win32ui.MessageBox(msg, title, win32con.MB_OKCANCEL)
        if rv == 2:
            return

        cmdopts = "--verbose"
        open_dialog('pull', cmdopts, root=src, filelist=[dest])

    def _incoming_here(self, parent_window):
        src = self._filenames[0]
        dest = self._folder
        cmdopts = "--verbose"
        open_dialog('incoming', cmdopts, root=src, filelist=[dest])

    def _outgoing_here(self, parent_window):
        src = self._filenames[0]
        dest = self._folder
        cmdopts = "--verbose"
        open_dialog('outgoing', cmdopts, root=src, filelist=[dest])

    def _init(self, parent_window):
        dest = self._folder or self._filenames[0]
        msg = "Create Hg repository in %s?" % (dest)
        title = "Mercurial: init"
        rv = win32ui.MessageBox(msg, title, win32con.MB_OKCANCEL)
        if rv == 2:
            return
        try:
            hg.repository(ui.ui(), dest, create=1)
        except:
            msg = "Error creating repo"
            win32ui.MessageBox(msg, title, 
                               win32con.MB_OK|win32con.MB_ICONERROR)
            
    def _status(self, parent_window):
        '''[tortoisehg] status = [gstatus | internal]'''
        stat = ui.ui().config('tortoisehg', 'status', 'internal')
        if stat == 'internal':
            self._run_dialog('status')
        elif stat == 'gstatus':
            targets = self._filenames or [self._folder]
            root = find_root(targets[0])
            quoted_files = [shellquote(s) for s in targets]
            hgpath = find_path('hg')
            cmd = "%s --repository %s gstatus %s" % \
                    (shellquote(hgpath), shellquote(root),
                     " ".join(quoted_files))
            run_program(cmd)
        else:
            msg = "Status viewer %s not recognized" % stat
            title = "Unknown status tool"
            win32ui.MessageBox(msg, title, win32con.MB_OK|win32con.MB_ICONERROR)

    def _clone(self, parent_window):
        self._run_dialog('clone', True)

    def _pull(self, parent_window):
        self._run_dialog('pull', True)

    def _push(self, parent_window):
        self._run_dialog('push', True)

    def _incoming(self, parent_window):
        self._run_dialog('incoming', True)

    def _outgoing(self, parent_window):
        self._run_dialog('outgoing', True)

    def _add(self, parent_window):
        self._run_dialog('add', modal=True)

    def _remove(self, parent_window):
        self._run_dialog('remove')

    def _revert(self, parent_window):
        self._run_dialog('status')

    def _tip(self, parent_window):
        self._run_dialog('tip', True)

    def _parents(self, parent_window):
        self._run_dialog('parents', True)

    def _heads(self, parent_window):
        self._run_dialog('heads', True)

    def _log(self, parent_window):
        self._run_dialog('log', verbose=False)

    def _show_tags(self, parent_window):
        self._run_dialog('tags', True, verbose=False)

    def _add_tag(self, parent_window):
        self._run_dialog('tag', True, verbose=False)

    def _diff(self, parent_window):
        self._run_dialog('diff')

    def _merge(self, parent_window):
        self._run_dialog('merge', noargs=True)

    def _rollback(self, parent_window):
        targets = self._filenames or [self._folder]
        root = find_root(targets[0])
        msg = "Confirm rollback: %s" % root
        title = "Mercurial: rollback"
        rv = win32ui.MessageBox(msg, title, win32con.MB_OKCANCEL)
        if rv == 1:
            self._run_dialog('rollback', noargs=True)

    def _commit_simple(self, parent_window):
        self._run_dialog('commit')

    def _update(self, parent_window):
        self._run_dialog('update', noargs=True)

    def _run_dialog(self, hgcmd, noargs=False, verbose=True, modal=False):
        if self._folder:
            cwd = self._folder
        elif self._filenames:
            f = self._filenames[0]
            cwd = os.path.isdir(f) and f or os.path.dirname(f)
        else:
            win32ui.MessageBox("Can't get cwd!", 'Hg ERROR', 
                   win32con.MB_OK|win32con.MB_ICONERROR)
            return

        targets = self._filenames or [self._folder]
        root = find_root(targets[0])
        filelist = []
        if noargs == False:
            filelist = targets
        cmdopts = "%s" % (verbose and "--verbose" or "")
        print "_run_program_dialog: cmdopts = ", cmdopts
        title = "Hg %s" % hgcmd
        open_dialog(hgcmd, cmdopts, cwd=cwd, root=root, filelist=filelist)

    def _help(self, parent_window):
        open_dialog('help', '--verbose')

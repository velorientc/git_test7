# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Jelmer Vernooij <jelmer@samba.org>
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>

import os.path
import pythoncom
from win32com.shell import shell, shellcon
import win32con
import win32gui
import win32gui_struct
import win32api
import _winreg
import re

S_OK = 0
S_FALSE = 1

_quotere = None
def _shellquote(s):
    global _quotere
    if _quotere is None:
        _quotere = re.compile(r'(\\*)("|\\$)')
    return '"%s"' % _quotere.sub(r'\1\1\\\2', s)
    return "'%s'" % s.replace("'", "'\\''")

"""Windows shell extension that adds context menu items to Bazaar branches."""
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
        self._filenames = []
        self._handlers = {}

    def Initialize(self, folder, dataobj, hkey):
        format_etc = win32con.CF_HDROP, None, 1, -1, pythoncom.TYMED_HGLOBAL
        sm = dataobj.GetData(format_etc)
        num_files = shell.DragQueryFile(sm.data_handle, -1)
        self._filenames = []
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
        commands = self._get_commands()
        if len(commands) > 0:
            # menu separator
            win32gui.InsertMenu(hMenu, indexMenu,
                                win32con.MF_SEPARATOR|win32con.MF_BYPOSITION,
                                0, None)
            
            # create submenu with Hg commands
            submenu = win32gui.CreatePopupMenu()
            for id, (text, help_text, command) in enumerate(commands):
                item, extras = win32gui_struct.PackMENUITEMINFO(text=text,
                            wID=idCmdFirst + id)
                win32gui.InsertMenuItem(submenu, id, 1, item)
                self._handlers[id] = (help_text, command)

            # add Hg submenu to context menu
            indexMenu += 1
            item, extras = win32gui_struct.PackMENUITEMINFO(text="TortoiseHg",
                                                            hSubMenu=submenu)
            win32gui.InsertMenuItem(hMenu, indexMenu, 1, item)

            # menu separator
            indexMenu += 1
            win32gui.InsertMenu(hMenu, indexMenu,
                                win32con.MF_SEPARATOR|win32con.MF_BYPOSITION,
                                0, None)
            indexMenu += 1

        # Return the number of commands we added
        return len(commands)

    def _get_commands(self):
        """
        Get a list of commands valid for the current selection.

        Each command is a tuple containing (display text, handler).
        """
        
        print "_get_commands() on %s" ", ".join(self._filenames)

        from mercurial import hg, ui, repo
        
        tree = None

        # open repo
        path = self._filenames[0]
        if os.path.isdir(path):
            dir, filename = path, ''
        else:
            dir, filename = os.path.split(path)

        os.chdir(dir)
        u = ui.ui()
        try:
            tree = hg.repository(u, path='')
        except repo.RepoError:
            print "%s: not in repo" % dir
            return []

        print "_get_commands(): adding hg commands"
        
        result = []
        if tree is not None:
            result.append((_("Commit"), 
                           _("Commit changes to the branch"),
                           self._commit))
        if tree is not None:
            result.append((_("Diff"),
                           _("View changes made in the local tree"),
                           self._diff))
        if tree is not None:
            result.append((_("View"),
                           _("View history"),
                           self._view))

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

    def _find_path(self, pgmname):
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

    def _run_program(self, appName, cmdline):
        # subprocess.Popen() would create a terminal (cmd.exe) window when 
        # making calls to hg, we use CreateProcess() coupled with 
        # CREATE_NO_WINDOW flag to suppress the terminal window
        
        import win32process, win32con, os
        
        flags = win32con.CREATE_NO_WINDOW
        startupInfo = win32process.STARTUPINFO()
        
        h1, h2, i1, i2 = win32process.CreateProcess(appName, 
                                                    cmdline,
                                                    None,
                                                    None,
                                                    1,
                                                    flags,
                                                    os.environ,
                                                    os.getcwd(),
                                                    startupInfo)
        
    def _checkout(self, parent_window):
        import checkout
        dialog = checkout.CheckoutDialog(self._filenames[0])
        dialog.run()
        dialog.destroy()

    def _commit(self, parent_window):
        import os, subprocess

        print "_commit() on %s" % ", ".join(self._filenames)
        
        hgpath = self._find_path('hg')
        if hgpath:
            cmd = "%s qct" % hgpath
            self._run_program(hgpath, cmd)
            print "started 'hg qct'"

    def _diff(self, parent_window):
        import os, subprocess

        print "_diff() on %s" % ", ".join(self._filenames)
        
        hgpath = self._find_path('hg')
        if hgpath:
            quoted_files = [_shellquote(s) for s in self._filenames]
            cmd = "%s extdiff %s" % (hgpath, " ".join(quoted_files))
            self._run_program(hgpath, cmd)
            print "started %s" % cmd

    def _view(self, parent_window):
        import os, subprocess
        
        print "_view() on %s" % ", ".join(self._filenames)
        
        hgpath = self._find_path('hg')
        if hgpath:
            cmd = "%s view" % hgpath
            self._run_program(hgpath, cmd)
            print "started 'hg view'"


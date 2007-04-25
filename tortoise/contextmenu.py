# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Jelmer Vernooij <jelmer@samba.org>
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>

import os.path
import pythoncom
from win32com.shell import shell, shellcon
import win32con
import win32gui
import win32gui_struct
import _winreg

S_OK = 0
S_FALSE = 1

"""Windows shell extension that adds context menu items to Bazaar branches."""
class ContextMenuExtension:
    _reg_progid_ = "Bazaar.ShellExtension.ContextMenu"
    _reg_desc_ = "Bazaar Shell Extension"
    _reg_clsid_ = "{EEE9936B-73ED-4D45-80C9-AF918354F885}"
    _com_interfaces_ = [shell.IID_IShellExtInit, shell.IID_IContextMenu]
    _public_methods_ = [
        "Initialize", # From IShellExtInit
        "QueryContextMenu", "InvokeCommand", "GetCommandString" # IContextMenu
        ]

    registry_keys = [
        (_winreg.HKEY_CLASSES_ROOT, r"*\shellex\ContextMenuHandlers\TortoiseBzr"),
        (_winreg.HKEY_CLASSES_ROOT, r"Directory\Background\shellex\ContextMenuHandlers\TortoiseBzr"),
        (_winreg.HKEY_CLASSES_ROOT, r"Directory\shellex\ContextMenuHandlers\TortoiseBzr"),
        (_winreg.HKEY_CLASSES_ROOT, r"Folder\shellex\ContextMenuHandlers\TortoiseBzr"),
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

        # As we are a context menu handler, we can ignore verbs.
        self._handlers = {}
        commands = self._get_commands()
        if len(commands) > 0:
            win32gui.InsertMenu(hMenu, indexMenu,
                                win32con.MF_SEPARATOR|win32con.MF_BYPOSITION,
                                0, None)
            indexMenu += 1
            for id, (text, help_text, command) in enumerate(commands):
                item, extras = win32gui_struct.PackMENUITEMINFO(text=text,
                            wID=idCmdFirst + id)
                win32gui.InsertMenuItem(hMenu, indexMenu + id, 1, item)
                self._handlers[id] = (help_text, command)

            indexMenu += len(commands)
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
        ospath = os.environ['PATH']
        plist = []
        for path in ospath.split(';'):
            for ext in ['exe', 'bat', 'cmd']:
                ppath = os.path.join(path, "%s.%s" % (pgmname, ext))
                #print "checking path: %s" % ppath
                if os.path.exists(ppath):
                    plist.append(ppath)

        if plist:
            #print "path found: %s" % ", ".join(plist)
            return plist[0]
        else:
            return None

        
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
            subprocess.Popen(['hg', 'qct'])
            print "popened 'hg qct'"

    def _diff(self, parent_window):
        import os, subprocess

        print "_commit() on %s" % ", ".join(self._filenames)
        
        hgpath = self._find_path('hg')
        if hgpath:
            subprocess.Popen([hgpath, 'extdiff', '.'])
            print "popened 'hg extdiff'"

    def _view(self, parent_window):
        import os, subprocess
        
        print "_view() on %s" % ", ".join(self._filenames)
        
        hgpath = self._find_path('hg')
        if hgpath:
            subprocess.Popen([hgpath, 'view'])
            print "popened 'hg view'"


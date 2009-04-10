# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Jelmer Vernooij <jelmer@samba.org>
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

import os
import sys
import tempfile
import pythoncom
import subprocess
from win32com.shell import shell, shellcon
import win32con
import win32process
import win32event
import win32ui
import win32gui
import win32gui_struct
import win32api
import _winreg
from mercurial import util
from thgutil import *
import menuthg

try:
    from mercurial.error import RepoError
except ImportError:
    from mercurial.repo import RepoError

debugging = False

try:
    import _winreg
    try:
        hkey = _winreg.OpenKey(_winreg.HKEY_CURRENT_USER,
                           r"Software\TortoiseHg", 0,
                           _winreg.KEY_ALL_ACCESS)
        val = _winreg.QueryValueEx(hkey, 'ContextMenuDebug')[0]
        if val in ('1', 'True'):
            debugging = True
    except EnvironmentError:
        pass
except ImportError:
    pass

if debugging:
    import win32traceutil
    def debugf(str, args=None):
        if args: print str % args
        else:    print str
else:
    def debugf(str, args=None):
        pass

appfiltered = False
try:
    try:
        # This will fail on windows < NT
        proc = win32api.GetCurrentProcess()
        app = win32process.GetModuleFileNameEx(proc, 0)
    except:
        app = win32api.GetModuleFileName(0)
    app = str(os.path.basename(app)).lower()

    if not app.startswith('tortoisehg'):
        from _winreg import HKEY_CURRENT_USER, OpenKey, QueryValueEx
        hkey = OpenKey(HKEY_CURRENT_USER, r"Software\TortoiseHg")
        filter = str(QueryValueEx(hkey, 'ShellApps')[0])
        for f in filter.split(','):
            f = f.strip().lower()
            if f == '*':
                break
            elif f == app:
                break
        else:
            debugf("app %s filtered, does not match %s", (app, filter))
            appfiltered = True
except (ImportError, EnvironmentError):
    pass

S_OK = 0
S_FALSE = 1
ThgMenuName = 'TortoiseHG'

"""Windows shell extension that adds context menu items to Mercurial repository"""
class ContextMenuExtension(menuthg.menuThg):
    _reg_progid_ = "Mercurial.ShellExtension.ContextMenu"
    _reg_desc_ = "Mercurial Shell Extension"
    _reg_clsid_ = "{EEE9936B-73ED-4D45-80C9-AF918354F885}"
    _com_interfaces_ = [shell.IID_IShellExtInit, shell.IID_IContextMenu]
    _public_methods_ = [
        "Initialize", # From IShellExtInit
        "QueryContextMenu", "InvokeCommand", "GetCommandString" # IContextMenu
        ]

    registry_keys = [
        (_winreg.HKEY_CLASSES_ROOT,
         r"*\shellex\ContextMenuHandlers\TortoiseHg", 
         [(None, _reg_clsid_)]),
        (_winreg.HKEY_CLASSES_ROOT,
         r"Directory\Background\shellex\ContextMenuHandlers\TortoiseHg",
         [(None, _reg_clsid_)]),
        (_winreg.HKEY_CLASSES_ROOT,
         r"Directory\shellex\ContextMenuHandlers\TortoiseHg",
         [(None, _reg_clsid_)]),
        (_winreg.HKEY_CLASSES_ROOT,
         r"Folder\shellex\ContextMenuHandlers\TortoiseHg",
         [(None, _reg_clsid_)]),
        (_winreg.HKEY_CLASSES_ROOT,
         r"Directory\shellex\DragDropHandlers\TortoiseHg",
         [(None, _reg_clsid_)]),
        (_winreg.HKEY_CLASSES_ROOT,
         r"Folder\shellex\DragDropHandlers\TortoiseHg",
         [(None, _reg_clsid_)]),
        ]

    def __init__(self):
        self.folder = None
        self.fnames = []
        self.menuitems = {}
        menuthg.menuThg.__init__(self)

    def Initialize(self, folder, dataobj, hkey):
        if appfiltered: return
        if folder:
            self.folder = shell.SHGetPathFromIDList(folder)

        if dataobj:
            format_etc = win32con.CF_HDROP, None, 1, -1, pythoncom.TYMED_HGLOBAL
            sm = dataobj.GetData(format_etc)
            num_files = shell.DragQueryFile(sm.data_handle, -1)
            for i in range(num_files):
                self.fnames.append(shell.DragQueryFile(sm.data_handle, i))

    def _create_menu(self, parent, menus, pos, idCmd, idCmdFirst):
        for menu_info in menus:
            if menu_info.isSep():
                win32gui.InsertMenu(parent, pos, 
                        win32con.MF_BYPOSITION|win32con.MF_SEPARATOR, 
                        idCmdFirst + idCmd, None)
            elif menu_info.isSubmenu():
                submenu = win32gui.CreatePopupMenu()
                idCmd = self._create_menu(submenu, menu_info.get_menus(), 0,
                        idCmd, idCmdFirst)
                opt = {
                    'text' : menu_info.menutext,
                    'wID' : idCmdFirst + idCmd,
                    'hSubMenu' : submenu, 
                }

                if menu_info.icon:
                    icon_path = get_icon_path("tortoise", menu_info.icon)
                    opt['hbmpChecked'] = opt['hbmpUnchecked'] = \
                            icon_to_bitmap(icon_path)
                
                item, _ = win32gui_struct.PackMENUITEMINFO(**opt)
                win32gui.InsertMenuItem(parent, pos, True, item)
                self.menuitems[idCmd] = ("", "")
            else:
                fstate = win32con.MF_BYCOMMAND
                if menu_info.state is False:
                    fstate |= win32con.MF_GRAYED
                
                opt = {
                    'text' : menu_info.menutext,
                    'fState' : fstate,
                    'wID' : idCmdFirst + idCmd,
                }

                if menu_info.icon:
                    icon_path = get_icon_path("tortoise", menu_info.icon)
                    opt['hbmpChecked'] = opt['hbmpUnchecked'] = \
                            icon_to_bitmap(icon_path)
                
                item, _ = win32gui_struct.PackMENUITEMINFO(**opt)
                win32gui.InsertMenuItem(parent, pos, True, item)
                self.menuitems[idCmd] = (menu_info.helptext, menu_info.hgcmd)
            idCmd += 1
            pos += 1
        return idCmd

    def QueryContextMenu(self, hMenu, indexMenu, idCmdFirst, idCmdLast, uFlags):
        if appfiltered:
            return 0
        if uFlags & shellcon.CMF_DEFAULTONLY:
            return 0

        # skip if TortoiseHG menus have already been added
        for i in range(win32gui.GetMenuItemCount(hMenu)):
            item, extra = win32gui_struct.EmptyMENUITEMINFO()
            win32gui.GetMenuItemInfo(hMenu, i, True, item)
            info = win32gui_struct.UnpackMENUITEMINFO(item)
            # debugf("UnpackMENUINFO(%d):" + str(info), i)
            if info[7] == ThgMenuName:
                debugf("TortoiseHG menu already exists!")
                return 0

        thgmenu = []

        # a brutal hack to detect if we are the first menu to go on to the 
        # context menu. If we are not the first, then add a menu separator
        # The number '30000' is just a guess based on my observation
        debugf("idCmdFirst = " + str(idCmdFirst))
        if idCmdFirst >= 30000:
            thgmenu.append(menuthg.TortoiseMenuSep())
        # As we are a context menu handler, we can ignore verbs.

        if self.folder:
            cwd = self.folder
        elif self.fnames:
            f = self.fnames[0]
            if len(self.fnames) == 1 and os.path.isdir(f):
                cwd = f
                self.fnames = []
            else:
                cwd = os.path.dirname(f)
        else:
            debugf('No cwd found')
            cwd = ''

        self.menuitems = {}
        if self.folder and self.fnames:
            # get menus with drag-n-drop support
            thgmenu += self.get_commands_dragdrop(self.fnames, self.folder)
            repo = menuthg.open_repo(self.folder)
        else:
            # get menus for hg menu
            repo = menuthg.open_repo(cwd)
            if repo:
                thgmenu += self.get_commands(repo, cwd, self.fnames)
            else:
                thgmenu += self.get_norepo_commands(cwd, self.fnames)
  
        self.cwd = cwd
        self.repo = repo
        idCmd = self._create_menu(hMenu, thgmenu, indexMenu, 0, idCmdFirst)
        # Return total number of menus & submenus we've added
        return idCmd

    def InvokeCommand(self, ci):
        mask, hwnd, verb, params, dir, nShow, hotkey, hicon = ci
        if verb >> 16:
            # This is a textual verb invocation... not supported.
            return S_FALSE
        if verb not in self.menuitems:
            raise Exception("Unsupported command id %i!" % verb)
        self.run_dialog(self.menuitems[verb][1])

    def GetCommandString(self, cmd, uFlags):
        if uFlags & shellcon.GCS_VALIDATEA or uFlags & shellcon.GCS_VALIDATEW:
            if cmd in self.menuitems:
                return S_OK
            return S_FALSE
        if uFlags & shellcon.GCS_VERBA or uFlags & shellcon.GCS_VERBW:
            return S_FALSE
        if uFlags & shellcon.GCS_HELPTEXTA or uFlags & shellcon.GCS_HELPTEXTW:
            # The win32com.shell implementation encodes the resultant
            # string into the correct encoding depending on the flags.
            return self.menuitems[cmd][0]
        return S_FALSE

    def run_dialog(self, hgcmd):
        cwd = self.cwd
        if self.repo:
            # Convert filenames to be relative to cwd
            files = []
            cwd_rel = cwd[len(self.repo.root+os.sep):]
            for f in self.fnames:
                try:
                    cpath = util.canonpath(self.repo.root, cwd, f)
                    if cpath.startswith(cwd_rel):
                        if cwd_rel:
                            cpath = cpath[len(cwd_rel+os.sep):]
                        files.append(cpath)
                    else:
                        files.append(f)
                except util.Abort: # canonpath will abort on .hg/ paths
                    pass
            self.fnames = files

        cmdline = None
        exepath = os.path.join(get_prog_root(), 'hgtk.exe')
        if os.path.exists(exepath):
            cmdline = ['hgtk.exe', hgcmd]
        elif not hasattr(sys, 'frozen'):
            pypath = os.path.join(get_prog_root(), 'hgtk')
            pyexe = os.path.join(sys.exec_prefix, 'python.exe')
            if os.path.exists(pypath) and os.path.exists(pyexe):
                cmdline = [pyexe, pypath, hgcmd]
        if not cmdline:
            win32ui.MessageBox('Unable to find ' + pypath, 'run_dialog')
            return
        if self.fnames:
            cmdline += ['--listfile', '-']
        try:
            debugf("run_dialog: cmdline = " + str(cmdline))
            debugf("run_dialog: fnames = " + str(self.fnames))
            proc = subprocess.Popen(cmdline,
                           shell=False,
                           cwd=cwd,
                           creationflags=win32con.CREATE_NO_WINDOW,
                           stderr=subprocess.STDOUT,
                           stdout=subprocess.PIPE,
                           stdin=subprocess.PIPE)
            if self.fnames:
                proc.stdin.write('\n'.join(self.fnames))
                proc.stdin.close()
        except win32api.error, details:
            win32ui.MessageBox('Error executing - ' + details, 'run_dialog')

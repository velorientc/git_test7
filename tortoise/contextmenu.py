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

from dialog import info_dialog

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
        import bzrlib.builtins
        import bzrlib.errors

        tree = None
        try:
            tree, relative_files = bzrlib.builtins.internal_tree_files(self._filenames)
        except bzrlib.errors.NotBranchError:
            pass
        except bzrlib.errors.FileInWrongBranch:
            # We have no commands that are valid for multiple branches.
            return []

        result = []
        if len(self._filenames) == 1 and tree is None and os.path.isdir(self._filenames[0]):
            result.append((_("Bzr Checkout"), _("Checkout a bazaar branch"), self._checkout))
        if tree is not None:
            result.append((_("Commit"), _("Commit changes to the branch"), self._commit))
        if tree is not None and len(self._filenames) == 1:
            result.append((_("Diff"), _("View changes made in the local tree"), self._diff))
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

    def _checkout(self, parent_window):
        import checkout
        dialog = checkout.CheckoutDialog(self._filenames[0])
        dialog.run()
        dialog.destroy()

    def _commit(self, parent_window):
        import bzrlib.builtins

        # Note that we don't catch the exceptions; we shouldn't be in here
        # if we aren't in a tree.
        tree, relative_files = bzrlib.builtins.internal_tree_files(self._filenames)

        import commit
        import gtk
        # Note that the commit dialog only handles a single item to
        # commit at the moment...
        dialog = commit.CommitDialog(tree, tree.basedir, False, relative_files)
        if not dialog.delta.has_changed():
            info_dialog(_("Commit"), _("No changes found!"))
        else:
            dialog.run()
            dialog.destroy()

    def _diff(self, parent_window):
        import bzrlib.builtins

        # Note that we don't catch the exceptions; we shouldn't be in here
        # if we aren't in a tree.
        tree, relative_files = bzrlib.builtins.internal_tree_files(self._filenames)
        assert len(relative_files) == 1

        import diff
        import gtk

        # Note that the commit dialog only handles a single item to
        # commit at the moment...
        window = diff.DiffWindow()
        window.set_diff("changes", tree, tree.basis_tree())
        if relative_files[0] != "":
            window.set_file(relative_files[0])
        window.connect("destroy", lambda widgit: gtk.main_quit())
        window.show()
        gtk.main()


# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>

import os.path
from win32com.shell import shell, shellcon
import _winreg

UNCHANGED = "unchanged"
ADDED = "added"
MODIFIED = "modified"
UNKNOWN = "unknown"
NOT_IN_TREE = "not in tree"
CONTROL_FILE = "control file"

class IconOverlayExtension(object):
    """
    Class to implement icon overlays for source controlled files.

    Displays a different icon based on version control status.

    NOTE: The system allocates only 15 slots in _total_ for all
        icon overlays; we (will) use 6, tortoisecvs uses 7... not a good
        recipe for a happy system.
    """
    _com_interfaces_ = [shell.IID_IShellIconOverlayIdentifier]
    _public_methods_ = [
        "GetOverlayInfo", "GetPriority", "IsMemberOf"
        ]

    def GetOverlayInfo(self):
        icon = os.path.join(os.path.dirname(__file__), "..", "icons", "status", self.icon)
        return (icon, 0, shellcon.ISIOI_ICONFILE)

    def GetPriority(self):
        return 0

    def _get_state(self, path):
        """
        Get the state of a given path in source control.
        """
        import bzrlib.workingtree
        import bzrlib.errors
        try:
            tree, relpath = bzrlib.workingtree.WorkingTree.open_containing(path)
        except bzrlib.errors.NotBranchError:
            # We aren't in a working tree
            return NOT_IN_TREE

        # Ideally, we'd use tree.changes_from, but unfortunately this is
        # recusive for directories, so we calculate changes ourselves.
        if tree.is_control_filename(relpath):
            return CONTROL_FILE

        file_id = tree.path2id(relpath)
        if file_id is None:
            # This is an unknown file...
            return UNKNOWN

        # Get information about the path from the old tree
        old = tree.basis_tree()
        old.lock_read()
        try:
            try:
                entry = old.inventory[file_id]
            except bzrlib.errors.NoSuchId:
                # This is an added entry...
                return ADDED

            if entry.kind != "file":
                # TODO: For directories, we want to find out if
                # the contents of the directories have changed...
                return UNCHANGED

            old_size = entry.text_size
            old_sha1 = entry.text_sha1
        finally:
            old.unlock()

        # Look in the new tree to see if has changed...
        tree.lock_read()
        try:
            if tree.get_file_size(file_id) != old_size or tree.get_file_sha1(file_id) != old_sha1:
                # This file has been modified
                return MODIFIED
        finally:
            tree.unlock()

        # This file has unchanged.
        return UNCHANGED

    def IsMemberOf(self, path, attrib):
        S_OK = 0
        S_FALSE = 1
        if self._get_state(path) == self.state:
            return S_OK
        return S_FALSE

def make_icon_overlay(name, icon, state, clsid):
    """
    Make an icon overlay COM class.

    Used to create different COM server classes for highlighting the
    files with different source controlled states (eg: unchanged, 
    modified, ...).
    """
    classname = "%sOverlay" % name
    prog_id = "Bazaar.ShellExtension.%s" % classname
    desc = "Bazaar icon overlay shell extension for %s files" % name.lower()
    reg = [
        (_winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\%s" % name) ]
    cls = type(
            classname,
            (IconOverlayExtension, ),
            dict(_reg_clsid_=clsid, _reg_progid_=prog_id, _reg_desc_=desc, registry_keys=reg, icon=icon, state=state))

    _overlay_classes.append(cls)
    # We need to register the class as global, as pythoncom will
    # create an instance of it.
    globals()[classname] = cls

_overlay_classes = []
make_icon_overlay("Unchanged", "unchanged.ico", UNCHANGED, "{00FEE959-5773-424B-88AC-A01BFC8E4555}")
make_icon_overlay("Added", "added.ico", ADDED, "{8447DB75-5875-4BA8-9F38-A727DAA484A0}")
make_icon_overlay("Changed", "changed.ico", MODIFIED, "{102C6A24-5F38-4186-B64A-237011809FAB}")
make_icon_overlay("Unknown", "unknown.ico", UNKNOWN, "{A8AFEA16-5F0C-4BE2-A64B-80C41C50D911}")

def get_overlay_classes():
    """
    Get a list of all registerable icon overlay classes
    """
    return _overlay_classes

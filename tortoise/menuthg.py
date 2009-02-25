# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Jelmer Vernooij <jelmer@samba.org>
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

import os
#import tempfile
from mercurial import hg
from thgutil import *
from mercurial import ui
from mercurial.i18n import _

try:
    from mercurial.error import RepoError
except ImportError:
    from mercurial.repo import RepoError


class TortoiseMenu(object):

    def __init__(self, menutext, helptext, hgcmd, icon=None, state=True):
        self.menutext = menutext
        self.helptext = helptext
        self.hgcmd = hgcmd
        self.state = state
        self.icon = icon

    def isSubmenu(self):
        return False

    def isSep(self):
        return False


class TortoiseSubmenu(TortoiseMenu):

    def __init__(self, menutext, helptext, menus=[], icon=None):
        TortoiseMenu.__init__(self, menutext, helptext, None, icon)
        self.menus = menus[:]

    def add_menu(self, menutext, helptext, hgcmd, icon=None, state=True):
        self.menus.append(TortoiseMenu(menutext, helptext,
                hgcmd, icon, state))

    def add_sep(self):
        self.menus.append(TortoiseMenuSep())

    def get_menus(self):
        return self.menus

    def append(self, entry):
        self.menus.append(entry)

    def isSubmenu(self):
        return True


class TortoiseMenuSep(object):

    def isSubmenu(self):
        return False

    def isSep(self):
        return True

    
def open_repo(path):
    root = find_root(path)
    if root:
        try:
            repo = hg.repository(ui.ui(), path=root)
            return repo
        except RepoError:
            pass

    return None


class menuThg:
    """shell extension that adds context menu items"""

    def __init__(self):
        self.name = "TortoiseHG"

    def get_commands_dragdrop(self, srcfiles, destfolder):
        """
        Get a list of commands valid for the current selection.

        Commands are instances of TortoiseMenu, TortoiseMenuSep or TortoiseMenu
        """

        # we can only accept dropping one item
        if len(srcfiles) > 1:
            return []

        # open repo
        drag_repo = None
        drop_repo = None

        drag_path = self.srcfiles[0]
        drag_repo = open_repo(drag_path)
        if not drag_repo:
            return []
        if drag_repo and drag_repo.root != drag_path:
            return []   # dragged item must be a hg repo root directory

        drop_repo = open_repo(self._folder)

        thgmenu = []
        thgmenu.append(TortoiseMenu(_("Create Clone"),
                  _("Create clone here from source"),
                  'clone', icon="menuclone.ico"))

        if drop_repo:
            thgmenu.append(TortoiseMenu(_("Synchronize"),
                     _("Synchronize with dragged repository"),
                     'synch', icon="menusynch.py"))
        return thgmenu

    def get_norepo_commands(self, cwd, files):
        thgmenu = []
        menu = TortoiseSubmenu(self.name, "Mercurial", [], icon="hg.ico")
        menu.append(TortoiseMenu(_("Clone a Repository"),
                  _("clone a repository"),
                  'clone', icon="menuclone.ico"))
        menu.append(TortoiseMenu(_("Create Repository Here"),
                  _("create a new repository in this directory"),
                  'init', icon="menucreaterepos.ico"))
        menu.append(TortoiseMenu(_("Global Settings"),
                  _("Configure user wide settings"),
                  'userconfig', icon="settings_user.ico"))
        menu.append(TortoiseMenuSep())
        menu.append(TortoiseMenu(_("About"), _("About TortoiseHg"),
                  'about', icon="menuabout.ico"))
        thgmenu.append(menu)
        thgmenu.append(TortoiseMenuSep())
        return thgmenu

    def get_commands(self, repo, cwd, files):
        """
        Get a list of commands valid for the current selection.

        Commands are instances of TortoiseMenu, TortoiseMenuSep or TortoiseMenu
        """
        thgmenu = []
        thgmenu.append(TortoiseMenu(_("HG Commit..."),
                     _("Commit changes in repository"),
                     'commit', icon="menucommit.ico"))

        menu = TortoiseSubmenu(self.name, "Mercurial", [], icon="hg.ico")
        canannotate = len(files) > 0
        hashgignore = False
        for f in files:
            if not os.path.isfile(f):
                canannotate = False
            if f.endswith('.hgignore'):
                hashgignore = True

        if hashgignore: # needs ico
            menu.append(TortoiseMenu(_("Edit Ignore Filter"),
                      _("Edit repository ignore filter"),
                      'hgignore', icon="general.ico"))

        menu.append(TortoiseMenu(_("View File Status"),
                  _("Repository status"),
                  'status', icon="menushowchanged.ico"))

        menu.append(TortoiseMenu(_("Shelve Changes"),
                  _("Shelve or unshelve repository changes"),
                  'shelve', icon="general.ico")) # needs ico

        # Visual Diff (any extdiff command)
        has_vdiff = repo.ui.config('tortoisehg', 'vdiff', '') != ''
        if has_vdiff:
            menu.append(TortoiseMenu(_("Visual Diff"),
                      _("View changes using GUI diff tool"),
                      'vdiff', icon="TortoiseMerge.ico"))

        if len(files) == 0: # needs ico
            menu.append(TortoiseMenu(_("Guess Renames"),
                      _("Detect renames and copies"),
                      'guess', icon="general.ico"))
        elif len(files) == 1: # needs ico
            menu.append(TortoiseMenu(_("Rename File"),
                      _("Rename file or directory"),
                      'rename', icon="general.ico"))

        if len(files):
            menu.append(TortoiseMenu(_("Add Files"),
                      _("Add files to Hg repository"),
                      'add', icon="menuadd.ico"))
            menu.append(TortoiseMenu(_("Remove Files"),
                      _("Remove selected files on the next commit"),
                      'remove', icon="menudelete.ico"))
            menu.append(TortoiseMenu(_("Undo Changes"),
                      _("Revert selected files"),
                      'revert', icon="menurevert.ico"))

        # we can only annotate file but not directories
        if canannotate:
            menu.append(TortoiseMenu(_("Annotate Files"),
                      _("show changeset information per file line"),
                      'datamine', icon="menublame.ico"))

        menu.append(TortoiseMenuSep())
        menu.append(TortoiseMenu(_("Update To Revision"),
                  _("update working directory"),
                  'update', icon="menucheckout.ico"))

        if len(repo.changectx(None).parents()) < 2:
            menu.append(TortoiseMenu(_("Merge Revisions"),
                  _("merge working directory with another revision"),
                  'merge', icon="menumerge.ico"))

        inmerge = len(repo.changectx(None).parents()) > 1
        if inmerge:
            menu.append(TortoiseMenu(_("Undo Merge"),
                  _("Undo merge by updating to revision"),
                  'merge', icon="menuunmerge.ico"))

        menu.append(TortoiseMenuSep())

        menu.append(TortoiseMenu(_("View Changelog"),
                  _("View revision history"),
                  'history', icon="menulog.ico"))

        if len(files) == 0:
            menu.append(TortoiseMenu(_("Search Repository"),
                      _("Search revisions of files for a text pattern"),
                      'datamine', icon="menurepobrowse.ico"))

            menu.append(TortoiseMenuSep())

            menu.append(TortoiseMenu(_("Synchronize..."),
                      _("Synchronize with remote repository"),
                      'synch', icon="menusynch.ico"))
            menu.append(TortoiseMenu(_("Recovery..."),
                      _("General repair and recovery of repository"),
                      'recovery', icon="general.ico"))
            menu.append(TortoiseMenu(_("Web Server"),
                      _("start web server for this repository"),
                      'serve', icon="proxy.ico"))

        menu.append(TortoiseMenuSep())
        menu.append(TortoiseMenu(_("Create Clone"),
                  _("Clone a repository here"),
                  'clone', icon="menuclone.ico"))
        if repo.root != cwd:
            menu.append(TortoiseMenu(_("Create Repository Here"),
                  _("create a new repository in this directory"),
                  'init', icon="menucreaterepos.ico"))

        # config settings menu
        menu.append(TortoiseMenuSep())
        optmenu = TortoiseSubmenu(_("Settings"), '',
                  icon="menusettings.ico")
        optmenu.add_menu(_("Global"),
                  _("Configure user wide settings"),
                  'userconfig', icon="settings_user.ico")
        optmenu.add_menu(_("Repository"),
                  _("Configure settings local to this repository"),
                  'repoconfig', icon="settings_repo.ico")
        menu.append(optmenu)

        # add common menu items
        menu.append(TortoiseMenuSep())
        menu.append(TortoiseMenu(_("About"), _("About TortoiseHg"),
                  'about', icon="menuabout.ico"))

        thgmenu.append(menu)
        thgmenu.append(TortoiseMenuSep())
        return thgmenu

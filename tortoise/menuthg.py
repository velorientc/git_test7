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

    def __init__(self, menutext, helptext, handler, icon=None, state=True):
        self.menutext = menutext
        self.helptext = helptext
        self.handler = handler
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

    def add_menu(self, menutext, helptext, handler, icon=None, state=True):
        self.menus.append(TortoiseMenu(menutext, helptext,
                handler, icon, state))

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
        self.handlers = self
        self.name = "TortoiseHG"

    def get_commands_dragdrop(self, srcfiles, destfolder):
        """
        Get a list of commands valid for the current selection.

        Commands are instances of TortoiseMenu, TortoiseMenuSep or TortoiseMenu
        """

        try:
            print "_get_commands_dragdrop() on %s" % ", ".join(files)
        except:
            print "_get_commands_dragdrop() on some files"

        # we can only accept dropping one item
        if len(srcfiles) > 1:
            return []

        # open repo
        drag_repo = None
        drop_repo = None

        print "drag = %s" % self.srcfiles[0]
        print "drop = %s" % self.destfolder

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
                  self.handlers._clone_here, icon="menuclone.ico"))

        if drop_repo:
            thgmenu.append(TortoiseMenu(_("Synchronize"),
                     _("Synchronize with dragged repository"),
                     self.handlers._synch_here, icon="menusynch.py"))
        return thgmenu

    def get_commands(self, files):
        """
        Get a list of commands valid for the current selection.

        Commands are instances of TortoiseMenu, TortoiseMenuSep or TortoiseMenu
        """
        try:
            print "_get_commands() on %s" % ", ".join(files)
        except:
            print "_get_commands() on some files"

        # open repo
        if type(files) != list:
            files = [files]
        if not files:
            return []
        rpath = files[0]
        repo = open_repo(rpath)

        thgmenu = []

        if repo:
            thgmenu.append(TortoiseMenu(_("HG Commit..."),
                      _("Commit changes in repository"),
                      self.handlers._commit, icon="menucommit.ico"))

        menu = TortoiseSubmenu(self.name, "Mercurial", [], icon="hg.ico")

        if repo is None:
            menu.append(TortoiseMenu(_("Clone a Repository"),
                      _("clone a repository"),
                      self.handlers._clone, icon="menuclone.ico"))
            menu.append(TortoiseMenu(_("Create Repository Here"),
                      _("create a new repository in this directory"),
                      self.handlers._init, icon="menucreaterepos.ico",
                      state=os.path.isdir(rpath)))
        else:

            for f in files:
                if f.endswith('.hgignore'):
                    menu.append(TortoiseMenu(_("Edit Ignore Filter"),
                              _("Edit repository ignore filter"),
                              self.handlers._hgignore, icon="general.ico")) # needs ico
                    break
 
            menu.append(TortoiseMenu(_("View File Status"),
                      _("Repository status"),
                      self.handlers._status, icon="menushowchanged.ico"))

            menu.append(TortoiseMenu(_("Shelve Changes"),
                      _("Shelve or unshelve repository changes"),
                      self.handlers._shelve, icon="general.ico")) # needs ico

            # Visual Diff (any extdiff command)
            has_vdiff = repo.ui.config('tortoisehg', 'vdiff', '') != ''
            menu.append(TortoiseMenu(_("Visual Diff"),
                      _("View changes using GUI diff tool"),
                      self.handlers._vdiff, icon="TortoiseMerge.ico",
                      state=has_vdiff))

            if len(files) == 0:
                menu.append(TortoiseMenu(_("Guess Renames"),
                       _("Detect renames and copies"),
                       self.handlers._guess_rename, icon="general.ico")) # needs ico
            elif len(files) == 1:
                menu.append(TortoiseMenu(_("Rename File"),
                       _("Rename file or directory"),
                       self.handlers._rename, icon="general.ico")) # needs ico

            menu.append(TortoiseMenu(_("Add Files"),
                      _("Add files to Hg repository"),
                      self.handlers._add, icon="menuadd.ico"))
            menu.append(TortoiseMenu(_("Remove Files"),
                      _("Remove selected files on the next commit"),
                      self.handlers._remove, icon="menudelete.ico"))
            menu.append(TortoiseMenu(_("Undo Changes"),
                      _("Revert selected files"),
                      self.handlers._revert, icon="menurevert.ico"))

            # we can only annotate file but not directories
            annotatible = len(files) > 0
            for f in files:
                if not os.path.isfile(f):
                    annotatible = False
                    break
            menu.append(TortoiseMenu(_("Annotate Files"),
                      _("show changeset information per file line"),
                      self.handlers._annotate, icon="menublame.ico",
                      state=annotatible))

            menu.append(TortoiseMenuSep())
            menu.append(TortoiseMenu(_("Update To Revision"),
                      _("update working directory"),
                      self.handlers._update, icon="menucheckout.ico"))

            can_merge = len(repo.heads()) > 1 and \
                      len(repo.changectx(None).parents()) < 2
            menu.append(TortoiseMenu(_("Merge Revisions"),
                      _("merge working directory with another revision"),
                      self.handlers._merge, icon="menumerge.ico",
                      state=can_merge))

            in_merge = len(repo.changectx(None).parents()) > 1
            menu.append(TortoiseMenu(_("Undo Merge"),
                      _("Undo merge by updating to revision"),
                      self.handlers._merge, icon="menuunmerge.ico",
                      state=in_merge))

            menu.append(TortoiseMenuSep())

            menu.append(TortoiseMenu(_("View Changelog"),
                      _("View revision history"),
                      self.handlers._history, icon="menulog.ico"))

            menu.append(TortoiseMenu(_("Search Repository"),
                      _("Search revisions of files for a text pattern"),
                      self.handlers._grep, icon="menurepobrowse.ico"))

            if repo.ui.config('tortoisehg', 'view'):
                menu.append(TortoiseMenu(_("Revision Graph"),
                          _("View history with DAG graph"),
                          self.handlers._view, icon="menurevisiongraph.ico"))

            menu.append(TortoiseMenuSep())

            menu.append(TortoiseMenu(_("Synchronize..."),
                      _("Synchronize with remote repository"),
                      self.handlers._synch, icon="menusynch.ico"))
            menu.append(TortoiseMenu(_("Recovery..."),
                      _("General repair and recovery of repository"),
                      self.handlers._recovery, icon="general.ico"))
            menu.append(TortoiseMenu(_("Web Server"),
                      _("start web server for this repository"),
                      self.handlers._serve, icon="proxy.ico"))

            menu.append(TortoiseMenuSep())
            menu.append(TortoiseMenu(_("Create Clone"),
                      _("Clone a repository here"),
                      self.handlers._clone, icon="menuclone.ico"))
            can_init = repo.root != rpath and os.path.isdir(rpath)
            menu.append(TortoiseMenu(_("Create Repository Here"),
                      _("create a new repository in this directory"),
                      self.handlers._init, icon="menucreaterepos.ico",
                      state=can_init))

        # config settings menu
        menu.append(TortoiseMenuSep())
        optmenu = TortoiseSubmenu(_("Settings"), '',
                  icon="menusettings.ico")
        optmenu.add_menu(_("Global"),
                  _("Configure user wide settings"),
                  self.handlers._config_user, icon="settings_user.ico")
        if repo:
            optmenu.add_menu(_("Repository"),
                      _("Configure settings local to this repository"),
                      self.handlers._config_repo,
                      icon="settings_repo.ico")
        menu.append(optmenu)

        # add common menu items
        menu.append(TortoiseMenuSep())
        menu.append(TortoiseMenu(_("About"), _("About TortoiseHg"),
                  self.handlers._about, icon="menuabout.ico"))

        thgmenu.append(menu)
        thgmenu.append(TortoiseMenuSep())
        return thgmenu


# Published under the GNU GPL, v2 or later.
# Copyright (C) 2007 Jelmer Vernooij <jelmer@samba.org>
# Copyright (C) 2007 Henry Ludemann <misc@hl.id.au>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

import os

from mercurial import hg, ui, node

from i18n import _
import cachethg
import paths
import hglib

promoted = []
try:
    from _winreg import HKEY_CURRENT_USER, OpenKey, QueryValueEx
    try:
        hkey = OpenKey(HKEY_CURRENT_USER, r"Software\TortoiseHg")
        pl = QueryValueEx(hkey, 'PromotedItems')[0]
        for item in pl.split(','):
            item = item.strip()
            if item: promoted.append(str(item))
    except EnvironmentError:
        promoted = ['commit']
except ImportError:
    # fallback method for non-win32 platforms
    u = ui.ui()
    pl = u.config('tortoisehg', 'promoteditems', 'commit')
    for item in pl.split(','):
        item = item.strip()
        if item: promoted.append(str(item))

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

    hgcmd = '----'

    def isSubmenu(self):
        return False

    def isSep(self):
        return True


class thg_menu(object):

    def __init__(self, ui, name = "TortoiseHG"):
        self.menus = [[]]
        self.ui = ui
        self.name = name
        self.sep = [False]

    def add_menu(self, menutext, helptext, hgcmd, icon=None, state=True):
        global promoted
        if hgcmd in promoted:
            pos = 0
        else:
            pos = 1
        while len(self.menus) <= pos: #add Submenu
            self.menus.append([])
            self.sep.append(False)
        if self.sep[pos]:
            self.sep[pos] = False
            self.menus[pos].append(TortoiseMenuSep())
        self.menus[pos].append(TortoiseMenu(
                  menutext, helptext, hgcmd, icon, state))

    def add_sep(self):
        self.sep = [True for _s in self.sep]


    def get(self):
        menu = self.menus[0][:]
        for submenu in self.menus[1:]:
            menu.append(TortoiseSubmenu(self.name, 'Mercurial', submenu, "hg.ico"))
        menu.append(TortoiseMenuSep())
        return menu

    def __iter__(self):
        return iter(self.get())


def open_repo(path):
    root = paths.find_root(path)
    if root:
        try:
            repo = hg.repository(ui.ui(), path=root)
            return repo
        except hglib.RepoError:
            pass
        except StandardError, e:
            print "error while opening repo %s:" % path
            print e

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

        drag_path = srcfiles[0]
        drag_repo = open_repo(drag_path)
        if not drag_repo:
            return []
        if drag_repo and drag_repo.root != drag_path:
            return []   # dragged item must be a hg repo root directory

        drop_repo = open_repo(destfolder)

        menu = thg_menu(drag_repo.ui, self.name)
        menu.add_menu(_("Create Clone"),
                  _("Create clone here from source"),
                  'clone', icon="menuclone.ico")

        if drop_repo:
            menu.add_menu(_("Synchronize"),
                     _("Synchronize with dragged repository"),
                     'synch', icon="menusynch.py")
        return menu

    def get_norepo_commands(self, cwd, files):
        menu = thg_menu(ui.ui(), self.name)
        menu.add_menu(_("Clone a Repository"),
                  _("clone a repository"),
                  'clone', icon="menuclone.ico")
        menu.add_menu(_("Create Repository Here"),
                  _("create a new repository in this directory"),
                  'init', icon="menucreaterepos.ico")
        menu.add_menu(_("Global Settings"),
                  _("Configure user wide settings"),
                  'userconfig', icon="settings_user.ico")
        menu.add_sep()
        menu.add_menu(_("About"), _("About TortoiseHg"),
                  'about', icon="menuabout.ico")
        menu.add_sep()
        return menu

    def get_commands(self, repo, cwd, files):
        """
        Get a list of commands valid for the current selection.

        Commands are instances of TortoiseMenu, TortoiseMenuSep or TortoiseMenu
        """
        states = set()
        onlyfiles = len(files) > 0
        hashgignore = False
        for f in files:
            if not os.path.isfile(f):
                onlyfiles = False
            if f.endswith('.hgignore'):
                hashgignore = True
            states.update(cachethg.get_states(f, repo))
        if not files:
            states.update(cachethg.get_states(cwd, repo))
            if cachethg.ROOT in states and len(states) == 1:
                states.add(cachethg.MODIFIED)

        changed = bool(states & set([cachethg.ADDED, cachethg.MODIFIED]))
        modified = cachethg.MODIFIED in states
        clean = cachethg.UNCHANGED in states
        tracked = changed or modified or clean
        new = bool(states & set([cachethg.UNKNOWN, cachethg.IGNORED]))

        menu = thg_menu(repo.ui, self.name)
        if changed or cachethg.UNKNOWN in states or 'qtip' in repo['.'].tags():
            menu.add_menu(_("HG Commit..."),
                      _("Commit changes in repository"),
                      'commit', icon="menucommit.ico")

        if hashgignore or new and len(states) == 1:
            menu.add_menu(_("Edit Ignore Filter"),
                      _("Edit repository ignore filter"),
                      'hgignore', icon="ignore.ico")

        if changed or cachethg.UNKNOWN in states:
            menu.add_menu(_("View File Status"),
                      _("Repository status"),
                      'status', icon="menushowchanged.ico")

        if modified:
            menu.add_menu(_("Shelve Changes"),
                  _("Shelve or unshelve repository changes"),
                  'shelve', icon="shelve.ico")

        # Visual Diff (any extdiff command)
        has_vdiff = repo.ui.config('tortoisehg', 'vdiff', 'vdiff') != ''
        if has_vdiff and modified:
            menu.add_menu(_("Visual Diff"),
                      _("View changes using GUI diff tool"),
                      'vdiff', icon="TortoiseMerge.ico")

        if len(files) == 0 and cachethg.UNKNOWN in states:
            menu.add_menu(_("Guess Renames"),
                      _("Detect renames and copies"),
                      'guess', icon="detect_rename.ico")
        elif len(files) == 1 and tracked: # needs ico
            menu.add_menu(_("Rename File"),
                      _("Rename file or directory"),
                      'rename', icon="general.ico")

        if files and new:
            menu.add_menu(_("Add Files"),
                      _("Add files to Hg repository"),
                      'add', icon="menuadd.ico")
        if files and tracked:
            menu.add_menu(_("Remove Files"),
                      _("Remove selected files on the next commit"),
                      'remove', icon="menudelete.ico")
        if files and changed:
            menu.add_menu(_("Revert Changes"),
                      _("Revert selected files"),
                      'revert', icon="menurevert.ico")

        # we can only annotate file but not directories
        if onlyfiles and tracked:
            menu.add_menu(_("Annotate Files"),
                      _("show changeset information per file line"),
                      'datamine', icon="menublame.ico")

        menu.add_sep()

        if tracked:
            menu.add_menu(_("View Changelog"),
                  _("View revision history"),
                  'history', icon="menulog.ico")

        if len(files) == 0:
            menu.add_sep()
            menu.add_menu(_("Search History"),
                      _("Search revisions of files for a text pattern"),
                      'datamine', icon="menurepobrowse.ico")

            menu.add_sep()

            menu.add_menu(_("Synchronize..."),
                      _("Synchronize with remote repository"),
                      'synch', icon="menusynch.ico")
            menu.add_menu(_("Recovery..."),
                      _("General repair and recovery of repository"),
                      'recovery', icon="general.ico")
            menu.add_menu(_("Web Server"),
                      _("start web server for this repository"),
                      'serve', icon="proxy.ico")

            menu.add_sep()
            menu.add_menu(_("Create Clone"),
                      _("Clone a repository here"),
                      'clone', icon="menuclone.ico")
            if repo.root != cwd:
                menu.add_menu(_("Create Repository Here"),
                      _("create a new repository in this directory"),
                      'init', icon="menucreaterepos.ico")

            # config settings menu
            menu.add_sep()
            menu.add_menu(_("Global Settings"),
                      _("Configure user wide settings"),
                      'userconfig', icon="settings_user.ico")
            menu.add_menu(_("Repository Settings"),
                      _("Configure settings local to this repository"),
                      'repoconfig', icon="settings_repo.ico")

        # add common menu items
        menu.add_sep()
        menu.add_menu(_("About"), _("About TortoiseHg"),
                  'about', icon="menuabout.ico")

        menu.add_sep()
        return menu

# menuthg.py - TortoiseHg shell extension menu
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import hg, ui, node

from tortoisehg.util.i18n import _ as gettext
from tortoisehg.util import cachethg, paths, hglib

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
        promoted = ['commit', 'log']
except ImportError:
    # fallback method for non-win32 platforms
    u = ui.ui()
    pl = u.config('tortoisehg', 'promoteditems', 'commit')
    for item in pl.split(','):
        item = item.strip()
        if item: promoted.append(str(item))

def _(msgid):
    return {'id': msgid, 'str': gettext(msgid)}

thgcmenu = {
    'commit':     { 'label': _('Commit...'),
                    'help':  _('Commit changes in repository'),
                    'icon':  'menucommit.ico'},
    'init':       { 'label': _('Create Repository Here'),
                    'help':  _('Create a new repository'),
                    'icon':  'menucreaterepos.ico'},
    'clone':      { 'label': _('Clone...'),
                    'help':  _('Create clone here from source'),
                    'icon': 'menuclone.ico'},
    'status':     { 'label': _('File Status'),
                    'help':  _('Repository status & changes'),
                    'icon':  'menushowchanged.ico'},
    'shelve':     { 'label': _('Shelve Changes'),
                    'help':  _('Shelve or unshelve file changes'),
                    'icon':  'shelve.ico'},
    'add':        { 'label': _('Add Files...'),
                    'help':  _('Add files to version control'),
                    'icon':  'menuadd.ico'},
    'revert':     { 'label': _('Revert Files...'),
                    'help':  _('Revert file changes'),
                    'icon':  'menurevert.ico'},
    'forget':     { 'label': _('Forget Files...'),
                    'help':  _('Remove files from version control'),
                    'icon':  'menurevert.ico'},
    'remove':     { 'label': _('Remove Files...'),
                    'help':  _('Remove files from version control'),
                    'icon':  'menudelete.ico'},
    'rename':     { 'label': _('Rename File'),
                    'help':  _('Rename file or directory'),
                    'icon':  'general.ico'},
    'log':        { 'label': _('Repository Explorer'),
                    'help':  _('View change history in repository'),
                    'icon':  'menulog.ico'},
    'synch':      { 'label': _('Synchronize'),
                    'help':  _('Synchronize with remote repository'),
                    'icon':  'menusynch.ico'},
    'serve':      { 'label': _('Web Server'),
                    'help':  _('Start web server for this repository'),
                    'icon':  'proxy.ico'},
    'update':     { 'label': _('Update...'),
                    'help':  _('Update working directory'),
                    'icon':  'menucheckout.ico'},
    'recover':    { 'label': _('Recovery...'),
                    'help':  _('Repair and recovery of repository'),
                    'icon':  'general.ico'},
    'thgstatus':  { 'label': _('Update Icons'),
                    'help':  _('Update icons for this repository'),
                    'icon':  'refresh_overlays.ico'},
    'userconf':   { 'label': _('Global Settings'),
                    'help':  _('Configure user wide settings'),
                    'icon':  'settings_user.ico'},
    'repoconf':   { 'label': _('Repository Settings'),
                    'help':  _('Configure repository settings'),
                    'icon':  'settings_repo.ico'},
    'about':      { 'label': _('About TortoiseHg'),
                    'help':  _('Show About Dialog'),
                    'icon':  'menuabout.ico'},
    'datamine':   { 'label': _('Annotate Files'),
                    'help':  _('Changeset information per file line'),
                    'icon':  'menublame.ico'},
    'vdiff':      { 'label': _('Visual Diff'),
                    'help':  _('View changes using GUI diff tool'),
                    'icon':  'TortoiseMerge.ico'},
    'hgignore':   { 'label': _('Edit Ignore Filter'),
                    'help':  _('Edit repository ignore filter'),
                    'icon':  'ignore.ico'},
    'guess':      { 'label': _('Guess Renames'),
                    'help':  _('Detect renames and copies'),
                    'icon':  'detect_rename.ico'},
    'grep':       { 'label': _('Search History'),
                    'help':  _('Search file revisions for patterns'),
                    'icon':  'menurepobrowse.ico'},
    'dndsynch':   { 'label': _('DnD Synchronize'),
                    'help':  _('Synchronize with dragged repository'),
                    'icon':  'menusynch.ico'}}

class TortoiseMenu(object):

    def __init__(self, menutext, helptext, hgcmd, icon=None, state=True):
        self.menutext = menutext
        self.helptext = helptext
        self.hgcmd = hgcmd
        self.icon = icon
        self.state = state

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

    def add_menu(self, hgcmd, icon=None, state=True):
        global promoted, thgcmenu
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
        self.menus[pos].append(TortoiseMenu(thgcmenu[hgcmd]['label']['str'],
                thgcmenu[hgcmd]['help']['str'], hgcmd, thgcmenu[hgcmd]['icon'], state))

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
        menu.add_menu('clone')

        if drop_repo:
            menu.add_menu('dndsynch')
        return menu

    def get_norepo_commands(self, cwd, files):
        menu = thg_menu(ui.ui(), self.name)
        menu.add_menu('clone')
        menu.add_menu('init')
        menu.add_menu('userconf')
        menu.add_sep()
        menu.add_menu('about')
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
            menu.add_menu('commit')
        if hashgignore or new and len(states) == 1:
            menu.add_menu('hgignore')
        if changed or cachethg.UNKNOWN in states:
            menu.add_menu('status')
        if modified:
            menu.add_menu('shelve')

        # Visual Diff (any extdiff command)
        has_vdiff = repo.ui.config('tortoisehg', 'vdiff', 'vdiff') != ''
        if has_vdiff and modified:
            menu.add_menu('vdiff')

        if len(files) == 0 and cachethg.UNKNOWN in states:
            menu.add_menu('guess')
        elif len(files) == 1 and tracked: # needs ico
            menu.add_menu('rename')

        if files and new:
            menu.add_menu('add')
        if files and tracked:
            menu.add_menu('remove')
        if files and changed:
            menu.add_menu('revert')

        # we can only annotate file but not directories
        if onlyfiles and tracked:
            menu.add_menu('datamine')

        menu.add_sep()

        if tracked:
            menu.add_menu('log')

        if len(files) == 0:
            menu.add_sep()
            menu.add_menu('grep')
            menu.add_sep()
            menu.add_menu('synch')
            menu.add_menu('recover')
            menu.add_menu('serve')
            menu.add_sep()
            menu.add_menu('clone')
            if repo.root != cwd:
                menu.add_menu('init')
            menu.add_sep()
            menu.add_menu('userconf')
            menu.add_menu('repoconf')

        # add common menu items
        menu.add_sep()
        menu.add_menu('about')

        menu.add_sep()
        return menu

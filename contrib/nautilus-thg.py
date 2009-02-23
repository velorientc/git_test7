# TortoiseHg plugin for Nautilus
#
# Copyright (C) 2007-9 Steve Borho
#
# Stolen mercilessly from nautilus-bzr, thanks guys
# Copyright (C) 2006 Jeff Bailey
# Copyright (C) 2006 Wouter van Heyst
# Copyright (C) 2006 Jelmer Vernooij
#
# Published under the GNU GPL

import gtk
import gobject
import os
import nautilus
import subprocess
import sys
import tempfile
import urllib

try:
    from mercurial import hg, ui, match, util
except ImportError:
    # workaround to use user's local python libs
    userlib = os.path.expanduser('~/lib/python')
    if os.path.exists(userlib) and userlib not in sys.path:
        sys.path.append(userlib)
    from mercurial import hg, ui, match, util
try:
    from mercurial.error import RepoError
except ImportError:
    from mercurial.repo import RepoError
from mercurial.node import short

TORTOISEHG_PATH = '~/tools/tortoisehg-dev'
nofilecmds = 'about serve synch repoconfig userconfig merge unmerge'.split()
nocachecmds = 'about serve repoconfig userconfig'.split()

class HgExtension(nautilus.MenuProvider,
                  nautilus.ColumnProvider,
                  nautilus.InfoProvider,
                  nautilus.PropertyPageProvider):

    def __init__(self):
        self.cacherepo = None
        self.cacheroot = None

        # check if nautilus-thg.py is a symlink first
        pfile = __file__
        if pfile.endswith('.pyc'):
            pfile = pfile[:-1]
        path = os.path.dirname(os.path.realpath(pfile))
        thgpath = os.path.normpath(os.path.join(path, '..'))
        testpath = os.path.join(thgpath, 'tortoise')
        if os.path.isdir(testpath):
            if thgpath not in sys.path:
                sys.path.insert(0, thgpath)
        else:
            # try environment or hard-coded path
            thgpath = os.environ.get('TORTOISEHG_PATH', TORTOISEHG_PATH)
            thgpath = os.path.normpath(os.path.expanduser(thgpath))
            if os.path.exists(thgpath) and thgpath not in sys.path:
                sys.path.insert(0, thgpath)
        # else assume tortoise is already in PYTHONPATH
        try:
            import tortoise.thgutil
            import tortoise.menuthg
        except ImportError, e:
            # if thgutil is not found, then repository cannot be found
            # if menuthg is not found, you have an older version in sys.path
            print e
            self.menu = None
            return

        self.env = os.environ
        self.env['PYTHONPATH'] = ':'.join(sys.path)
        self.env['TORTOISEHG_PATH'] = thgpath
        self.env['THG_ICON_PATH'] = os.path.join(thgpath, 'icons')

        self.hgproc = os.path.join(thgpath, 'hgproc.py')
        self.ipath = os.path.join(thgpath, 'icons', 'tortoise')
        self.menu = tortoise.menuthg.menuThg()

    def icon(self, iname):
        return os.path.join(self.ipath, iname)

    def get_path_for_vfs_file(self, vfs_file):
        if vfs_file.get_uri_scheme() != 'file':
            return None
        return urllib.unquote(vfs_file.get_uri()[7:])

    def get_repo_for_path(self, path):
        '''
        Find mercurial repository for vfs_file
        Returns hg.repo
        '''
        p = os.path.isdir(path) and path or os.path.dirname(path)
        while not os.path.isdir(os.path.join(p, ".hg")):
            oldp = p
            p = os.path.dirname(p)
            if p == oldp:
                return None

        if p == self.cacheroot:
            return self.cacherepo
        # Keep one repo cached
        try:
            self.cacheroot = p
            self.cacherepo = hg.repository(ui.ui(), path=p)
            return self.cacherepo
        except RepoError:
            self.cacheroot = None
            self.cacherepo = None
            return None

#start dialogs
    def run_dialog(self, menuitem, hgcmd):
        '''
        hgcmd - hgproc subcommand
        '''
        cwd = self.cwd
        repo = self.get_repo_for_path(cwd)

        if hgcmd == 'vdiff':
            diffcmd = repo.ui.config('tortoisehg', 'vdiff', None)
            if diffcmd is None:
                hgcmd = 'diff'
            else:
                cmdline = ['hg', diffcmd]
                cmdline.extend(self.files)
                subprocess.Popen(cmdline, shell=False, env=self.env, cwd=cwd)
                return

        cmdopts  = [sys.executable, self.hgproc]
        cmdopts += ['--command', hgcmd]

        if hgcmd not in nofilecmds and self.files:
            # Use temporary file to store file list (avoid shell command
            # line limitations)
            fd, tmpfile = tempfile.mkstemp(prefix="tortoisehg_filelist_")
            os.write(fd, "\n".join(self.files))
            os.close(fd)
            cmdopts += ['--listfile', tmpfile, '--deletelistfile']

        subprocess.Popen(cmdopts, cwd=cwd, env=self.env, shell=False)

        if hgcmd not in nocachecmds:
            # Remove cached repo object, dirstate may change
            self.cacherepo = None
            self.cacheroot = None

    def buildMenu(self, vfs_files, bg):
        '''Build menu'''
        self.pos = 0
        self.files = []
        files = [self.get_path_for_vfs_file(f) for f in vfs_files]
        if bg:
            cwd = files[0]
            files = []
            repo = self.get_repo_for_path(cwd)
        else:
            f = files[0]
            cwd = os.path.isdir(f) and f or os.path.dirname(f)
            repo = self.get_repo_for_path(cwd)
        if repo:
            menus = self.menu.get_commands(repo, cwd, files)
            for f in files:
                self.files.append(util.canonpath(repo.root, cwd, f))
        else:
            menus = self.menu.get_norepo_commands(cwd, files)
        self.cwd = cwd
        return self._buildMenu(menus)

    def _buildMenu(self, menus):
        '''Build menu'''
        items = []
        for menu_info in menus:
            idstr = 'HgNautilus::%02d' % self.pos
            self.pos += 1
            if menu_info.isSep():
                # can not insert a separator till now
                pass
            elif menu_info.isSubmenu():
                if nautilus.__dict__.get('Menu'):
                    item = nautilus.MenuItem(idstr, menu_info.menutext,
                            menu_info.helptext)
                    submenu = nautilus.Menu()
                    item.set_submenu(submenu)
                    for subitem in self._buildMenu(menu_info.get_menus()):
                        submenu.append_item(subitem)
                    items.append(item)
                else: #submenu not suported
                    for subitem in self._buildMenu(menu_info.get_menus()):
                        items.append(subitem)
            else:
                if menu_info.state:
                    item = nautilus.MenuItem(idstr,
                                 menu_info.menutext,
                                 menu_info.helptext,
                                 self.icon(menu_info.icon))
                    item.connect('activate', self.run_dialog, menu_info.hgcmd)
                    items.append(item)
        return items

    def get_background_items(self, window, vfs_file):
        '''Build context menu for current directory'''
        if vfs_file and self.menu:
            return self.buildMenu([vfs_file], True)

    def get_file_items(self, window, vfs_files):
        '''Build context menu for selected files/directories'''
        if vfs_files and self.menu:
            return self.buildMenu(vfs_files, False)

    def get_columns(self):
        return nautilus.Column("HgNautilus::80hg_status",
                               "hg_status",
                               "HG Status",
                               "Version control status"),

    def _get_file_status(self, repo, localpath):
        emblem = None
        status = '?'

        # This is not what the API is optimized for, but this appears
        # to work efficiently enough
        matcher = match.always(repo.root, localpath)
        changes = repo.dirstate.status(matcher, True, True, True)
        (lookup, modified, added, removed, deleted, unknown,
                ignored, clean) = changes

        if localpath in clean:
            emblem = 'default'
            status = 'clean'
        elif localpath in modified:
            emblem = 'cvs-modified'
            status = 'modified'
        elif localpath in added:
            emblem = 'cvs-aded'
            status = 'added'
        elif localpath in unknown:
            emblem = 'new'
            status = 'unrevisioned'
        elif localpath in ignored:
            status = 'ignored'
        elif localpath in deleted:
            # Should be hard to reach this state
            emblem = 'stockmail-priority-high'
            status = 'deleted'
        return emblem, status


    def update_file_info(self, file):
        '''Return emblem and hg status for this file'''
        path = self.get_path_for_vfs_file(file)
        if path is None or file.is_directory():
            return
        repo = self.get_repo_for_path(path)
        if repo is None:
            return
        localpath = path[len(repo.root)+1:]
        emblem, status = self._get_file_status(repo, localpath)
        if emblem is not None:
            file.add_emblem(emblem)
        file.add_string_attribute('hg_status', status)

    # property page borrowed from http://www.gnome.org/~gpoo/hg/nautilus-hg/
    def __add_row(self, row, label_item, label_value):
        label = gtk.Label(label_item)
        label.set_use_markup(True)
        label.set_alignment(1, 0)
        self.table.attach(label, 0, 1, row, row + 1, gtk.FILL, gtk.FILL, 0, 0)
        label.show()

        label = gtk.Label(label_value)
        label.set_use_markup(True)
        label.set_alignment(0, 1)
        label.show()
        self.table.attach(label, 1, 2, row, row + 1, gtk.FILL, 0, 0, 0)

    def get_property_pages(self, vfs_files):
        if len(vfs_files) != 1:
            return
        file = vfs_files[0]
        path = self.get_path_for_vfs_file(file)
        if path is None or file.is_directory():
            return
        repo = self.get_repo_for_path(path)
        if repo is None:
            return
        localpath = path[len(repo.root)+1:]
        emblem, status = self._get_file_status(repo, localpath)

        # Get the information from Mercurial
        ctx = repo.changectx(None).parents()[0]
        try:
            fctx = ctx.filectx(localpath)
            rev = fctx.filelog().linkrev(fctx.filerev())
        except:
            rev = ctx.rev()
        ctx = repo.changectx(rev)
        node = short(ctx.node())
        date = util.datestr(ctx.date(), '%Y-%m-%d %H:%M:%S %1%2')
        parents = '\n'.join([short(p.node()) for p in ctx.parents()])
        description = ctx.description()
        user = ctx.user()
        user = gobject.markup_escape_text(user)
        tags = ', '.join(ctx.tags())
        branch = ctx.branch()

        self.property_label = gtk.Label('Mercurial')

        self.table = gtk.Table(7, 2, False)
        self.table.set_border_width(5)
        self.table.set_row_spacings(5)
        self.table.set_col_spacings(5)

        self.__add_row(0, '<b>Status</b>:', status)
        self.__add_row(1, '<b>Last-Commit-Revision</b>:', str(rev))
        self.__add_row(2, '<b>Last-Commit-Description</b>:', description)
        self.__add_row(3, '<b>Last-Commit-Date</b>:', date)
        self.__add_row(4, '<b>Last-Commit-User</b>:', user)
        if tags:
            self.__add_row(5, '<b>Tags</b>:', tags)
        if branch != 'default':
            self.__add_row(6, '<b>Branch</b>:', branch)

        self.table.show()
        return nautilus.PropertyPage("MercurialPropertyPage::status",
                                     self.property_label, self.table),

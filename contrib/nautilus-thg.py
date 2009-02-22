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
            import tortoise.menuthg
        except ImportError:
            print 'unable to import tortoise.menuthg'
            self.menu = None
            return

        self.env = os.environ
        self.env['PYTHONPATH'] = ':'.join(sys.path)
        self.env['TORTOISEHG_PATH'] = thgpath
        self.env['THG_ICON_PATH'] = os.path.join(thgpath, 'icons')

        self.hgproc = os.path.join(thgpath, 'hgproc.py')
        self.ipath = os.path.join(thgpath, 'icons', 'tortoise')
        self.menu = tortoise.menuthg.menuThg()
        self.menu.handlers = self

    def icon(self, iname):
        return os.path.join(self.ipath, iname)

    def get_path_for_vfs_file(self, vfs_file):
        if vfs_file.get_uri_scheme() != 'file':
            return None
        return urllib.unquote(vfs_file.get_uri()[7:])

    def clear_cached_repo(self):
        self.cacheroot = None
        self.cacherepo = None

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
    def _about(self, window, info):
        self._run_dialog('about', filelist=False)

    def _add(self, window, vfs_files):
        self._run_dialog('add')
        self.clear_cached_repo()

    def _clone(self, window, info):
        self._run_dialog('clone')

    def _commit(self, window, vfs_files):
        self._run_dialog('commit')
        self.clear_cached_repo()

    def _datamine(self, window, vfs_files):
        self._run_dialog('datamine')

    def _diff(self, window, vfs_files):
        path = self.files[0]
        if path is None:
            return
        repo = self.get_repo_for_path(path)
        if repo is None:
            return
        diffcmd = repo.ui.config('tortoisehg', 'vdiff', None)
        if diffcmd is None:
            self._run_dialog('diff')
        else:
            cmdline = ['hg', diffcmd]
            cwd = os.path.isdir(path) and path or os.path.dirname(path)
            paths = [self.get_path_for_vfs_file(f) for f in vfs_files]
            subprocess.Popen(cmdline+paths, shell=False, env=self.env, cwd=cwd)

    def _history(self, window, info):
        self._run_dialog('history')
        self.clear_cached_repo()

    def _init(self, window, info):
        self._run_dialog('init')

    def _recovery(self, window, info):
        self._run_dialog('recovery')
        self.clear_cached_repo()

    def _revert(self, window, vfs_files):
        self._run_dialog('revert')
        self.clear_cached_repo()

    def _serve(self, window, info):
        self._run_dialog('serve', filelist=False)

    def _status(self, window, info):
        self._run_dialog('status')

    def _synch(self, window, info):
        self._run_dialog('synch', filelist=False)
        self.clear_cached_repo()

    def _config_repo(self, window, info):
        self._run_dialog('config')

    def _config_user(self, window, info):
        self._run_dialog('config', filelist=False)

    def _unmerge(self, window, info):
        self._run_dialog('checkout', filelist=False,
                extras=['--', '--clean', str(self.rev0)])
        self.clear_cached_repo()

    def _shelve(self, window, info):
        self._run_dialog('shelve')

    _vdiff=_diff

    def _rename(self, window, info):
        self._run_dialog('rename')

    def _remove(self, window, info):
        self._run_dialog('status')

    def _annotate(self, window, info):
        self._run_dialog('datamine')

    def _update(self, window, info):
        print "not supported" # will be replaced

    def _merge(self, window, info):
        print "not supported" # will be replaced

    def _grep(self, window, info):
        self._run_dialog('datamine')

    def _run_dialog(self, hgcmd, filelist=True, extras=[]):
        '''
        hgcmd - hgproc subcommand
        filelist  - bool for whether to generate file list for hgproc
        '''
        paths = self.files
        if paths[0] is None:
            return

        path = paths[0]
        repo = self.get_repo_for_path(path)
        cwd = os.path.isdir(path) and path or os.path.dirname(path)

        if repo is not None:
            root = repo.root
        else:
            root = cwd

        cmdopts  = [sys.executable, self.hgproc]
        cmdopts += ['--root', root]
        cmdopts += ['--cwd', cwd]
        cmdopts += ['--command', hgcmd]

        if filelist:
            # Use temporary file to store file list (avoid shell command
            # line limitations)
            fd, tmpfile = tempfile.mkstemp(prefix="tortoisehg_filelist_")
            os.write(fd, "\n".join(paths))
            os.close(fd)
            cmdopts += ['--listfile', tmpfile, '--deletelistfile']
        cmdopts.extend(extras)

        subprocess.Popen(cmdopts, cwd=cwd, env=self.env, shell=False)

        # Remove cached repo object, dirstate may change
        self.cacherepo = None
        self.cacheroot = None

    def buildMenu(self, menuf, vfsfile):
        '''Build menu'''

        self.files = [self.get_path_for_vfs_file(f) for f in vfsfile]
        return self._buildMenu(menuf(self.files))

    def _buildMenu(self, menus, pos=0):
        '''Build menu'''

        items = []
        for menu_info in menus:
            pos += 1
            idstr = 'HgNautilus::%02d' % pos
            if menu_info.isSep():
               #can not insert a separator till now
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
                    for subitem in self._buildMenu(menu_info.get_menus(), pos):
                        items.append(subitem)
                        pos+= 1
            else:
                if menu_info.state:
                    item = nautilus.MenuItem(idstr,
                                 menu_info.menutext,
                                 menu_info.helptext,
                                 self.icon(menu_info.icon))
                    item.connect('activate', menu_info.handler, '')
                    items.append(item)
        return items

    def get_background_items(self, window, vfs_file):
        '''Build context menu for current directory'''
        if vfs_file and self.menu:
            return self.buildMenu(self.menu.get_commands, [vfs_file])

    def get_file_items(self, window, vfs_files):
        '''Build context menu for selected files/directories'''
        if vfs_files and self.menu:
            return self.buildMenu(self.menu.get_commands, vfs_files)

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

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
import nautilus

try:
    from mercurial import demandimport
except ImportError:
    # workaround to use user's local python libs
    userlib = os.path.expanduser('~/lib/python')
    if os.path.exists(userlib) and userlib not in sys.path:
        sys.path.append(userlib)
    from mercurial import demandimport
demandimport.enable()

import os
import subprocess
import sys
import urllib

from mercurial import hg, ui, match, util
from mercurial.node import short

nofilecmds = 'about serve synch repoconfig userconfig merge unmerge'.split()
nocachecmds = 'about serve repoconfig userconfig'.split()


class HgExtension(nautilus.MenuProvider,
                  nautilus.ColumnProvider,
                  nautilus.InfoProvider,
                  nautilus.PropertyPageProvider):

    def __init__(self):
        self.cacherepo = None
        self.cacheroot = None
        self.scanStack = []

        # check if nautilus-thg.py is a symlink first
        pfile = __file__
        if pfile.endswith('.pyc'):
            pfile = pfile[:-1]
        path = os.path.dirname(os.path.dirname(os.path.realpath(pfile)))
        thgpath = os.path.normpath(path)
        testpath = os.path.join(thgpath, 'thgutil')
        if os.path.isdir(testpath) and thgpath not in sys.path:
            sys.path.insert(0, thgpath)

        # else assume thgutil is already in PYTHONPATH
        try:
            from thgutil import paths, debugthg, menuthg
        except ImportError, e:
            print e
            self.menu = None
            return

        self.hgtk = paths.find_in_path('hgtk')
        self.menu = menuthg.menuThg()

        global debugf
        if debugthg.debug('N'):
            debugf = debugthg.debugf
        else:
            debugf = debugthg.debugf_No

    def icon(self, iname):
        from thgutil import paths
        return paths.get_tortoise_icon(iname)

    def get_path_for_vfs_file(self, vfs_file):
        if vfs_file.is_gone() or vfs_file.get_uri_scheme() != 'file':
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
        from thgutil import hglib
        # Keep one repo cached
        try:
            self.cacheroot = p
            self.cacherepo = hg.repository(ui.ui(), path=p)
            return self.cacherepo
        except hglib.RepoError:
            self.cacheroot = None
            self.cacherepo = None
            return None
        except StandardError, e:
            debugf(e)
            return None

    def run_dialog(self, menuitem, hgtkcmd, cwd = None):
        '''
        hgtkcmd - hgtk subcommand
        '''
        if cwd: #bg
            self.files = []
        else:
            cwd = self.cwd
        repo = self.get_repo_for_path(cwd)

        cmdopts = [sys.executable, self.hgtk, hgtkcmd]

        if hgtkcmd not in nofilecmds and self.files:
            pipe = subprocess.PIPE
            cmdopts += ['--listfile', '-']
        else:
            pipe = None

        proc = subprocess.Popen(cmdopts, cwd=cwd, stdin=pipe, shell=False)
        if pipe:
            proc.stdin.write('\n'.join(self.files))
            proc.stdin.close()

        if hgtkcmd not in nocachecmds:
            # Remove cached repo object, dirstate may change
            self.cacherepo = None
            self.cacheroot = None

    def buildMenu(self, vfs_files, bg):
        '''Build menu'''
        self.pos = 0
        self.files = []
        files =  []
        for vfs_file in vfs_files:
            f = self.get_path_for_vfs_file(vfs_file)
            if f:
                files.append(f)
        if not files:
            return
        if bg or len(files) == 1 and vfs_files[0].is_directory():
            cwd = files[0]
            files = []
        else:
            cwd = os.path.dirname(files[0])
        repo = self.get_repo_for_path(cwd)
        if repo:
            menus = self.menu.get_commands(repo, cwd, files)
            if cwd == repo.root:
                cwd_rel = ''
            else:
                cwd_rel = cwd[len(repo.root+os.sep):] + os.sep
            for f in files:
                try:
                    cpath = util.canonpath(repo.root, cwd, f)
                    if cpath.startswith(cwd_rel):
                        cpath = cpath[len(cwd_rel):]
                        self.files.append(cpath)
                    else:
                        self.files.append(f)
                except util.Abort: # canonpath will abort on .hg/ paths
                    pass
        else:
            menus = self.menu.get_norepo_commands(cwd, files)
        self.cwd = cwd
        return self._buildMenu(menus)

    def _buildMenu(self, menus):
        '''Build one level of a menu'''
        items = []
	if self.files:
            passcwd = None
        else: #bg
            passcwd = self.cwd
        for menu_info in menus:
            idstr = 'HgNautilus::%02d%s' % (self.pos, menu_info.hgcmd)
            self.pos += 1
            if menu_info.isSep():
                # can not insert a separator till now
                pass
            elif menu_info.isSubmenu():
                if hasattr(nautilus, 'Menu'):
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
                    item.connect('activate', self.run_dialog, menu_info.hgcmd,
                            passcwd)
                    items.append(item)
        return items

    def get_background_items(self, window, vfs_file):
        '''Build context menu for current directory'''
        if vfs_file and self.menu:
            return self.buildMenu([vfs_file], True)
        else:
            self.files = []

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
        from thgutil import cachethg
        cachestate = cachethg.get_state(localpath, repo)
        cache2state = {cachethg.UNCHANGED: ('default', 'clean'),
                       cachethg.ADDED: ('cvs-added', 'added'),
                       cachethg.MODIFIED: ('cvs-modified', 'modified'),
                       cachethg.UNKNOWN: ('new', 'unrevisioned'),
                       cachethg.IGNORED: (None, 'ignored'),
                       cachethg.NOT_IN_REPO: (None, ''),
                       cachethg.ROOT: ('generic', 'root'),
                       cachethg.UNRESOLVED: ('cvs-confilict', 'unresolved')}
        emblem, status = cache2state.get(cachestate, (None, '?'))
        return emblem, status

    def update_file_info(self, file):
        '''Queue file for emblem and hg status update'''
        self.scanStack.append(file)
        if len(self.scanStack) == 1:
            gobject.idle_add(self.fileinfo_on_idle)

    def fileinfo_on_idle(self):
        '''Update emblem and hg status for files when there is time'''
        if not self.scanStack:
            return False
        vfs_file = self.scanStack.pop()
        path = self.get_path_for_vfs_file(vfs_file)
        if not path:
            return True
        emblem, status = self._get_file_status(self.cacherepo, path)
        if emblem is not None:
            vfs_file.add_emblem(emblem)
        vfs_file.add_string_attribute('hg_status', status)
        return True

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
        emblem, status = self._get_file_status(repo, path)

        # Get the information from Mercurial
        ctx = repo['.']
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

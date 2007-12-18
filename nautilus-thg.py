# Trivial Mercurial plugin for Nautilus
#
# Copyright (C) 2007 Steve Borho
#
# Stolen mercilessly from nautilus-bzr, thanks guys
# Copyright (C) 2006 Jeff Bailey
# Copyright (C) 2006 Wouter van Heyst
# Copyright (C) 2006 Jelmer Vernooij
#
# Published under the GNU GPL

import gconf
from mercurial import hg, ui, util, repo
import nautilus
import os
import subprocess
import sys
import tempfile
import urllib

THG_PATH = '~/tools/tortoisehg-dev'
TERMINAL_KEY = '/desktop/gnome/applications/terminal/exec'

class HgExtension(nautilus.MenuProvider,
                  nautilus.ColumnProvider,
                  nautilus.InfoProvider):

    def __init__(self):
        self.cacherepo = None
        self.cacheroot = None
        self.client = gconf.client_get_default()
        thgpath = os.environ.get('THG_PATH', os.path.expanduser(THG_PATH))
        self.hgproc = os.path.join(thgpath, 'hgproc.py')
        self.ipath = os.path.join(thgpath, 'icons', 'tortoise')

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
        except repo.RepoError:
            self.cacheroot = None
            self.cacherepo = None
            return None

    def _open_terminal_cb(self, window, vfs_file):
        path = self.get_path_for_vfs_file(vfs_file)
        if path is None:
            return
        os.chdir(path)
        terminal = self.client.get_string(TERMINAL_KEY)
        os.system('%s &' % terminal)

    def _add_cb(self, window, vfs_files):
        self._run_dialog('add', vfs_files)

    def _clone_cb(self, window, vfs_file):
        self._run_dialog('clone', [vfs_file])

    def _commit_cb(self, window, vfs_files):
        path = self.get_path_for_vfs_file(vfs_files[0])
        if path is None:
            return
        repo = self.get_repo_for_path(path)
        if repo is None:
            return
        if repo.ui.config('tortoisehg', 'commit') == 'qct':
            cwd = os.path.isdir(path) and path or os.path.dirname(path)
            subprocess.Popen(['hg', 'qct'], cwd=cwd, shell=False)
        else:
            self._run_dialog('commit', vfs_files)

    def _diff_cb(self, window, vfs_files):
        path = self.get_path_for_vfs_file(vfs_files[0])
        if path is None:
            return
        repo = self.get_repo_for_path(path)
        if repo is None:
            return
        diffcmd = repo.ui.config('tortoisehg', 'vdiff', None)
        if diffcmd is None:
            self._run_dialog('diff', vfs_files)
        else:
            cmdline = ['hg', diffcmd]
            cwd = os.path.isdir(path) and path or os.path.dirname(path)
            paths = [self.get_path_for_vfs_file(f) for f in vfs_files]
            subprocess.Popen(cmdline + paths, shell=False, cwd=cwd)

    def _history_cb(self, window, vfs_files):
        self._run_dialog('history', vfs_files)

    def _init_cb(self, window, vfs_file):
        self._run_dialog('init', [vfs_file])

    def _merge_cb(self, window, vfs_file):
        self._run_dialog('merge', [vfs_file])

    def _paths_cb(self, window, vfs_file):
        path = self.get_path_for_vfs_file(vfs_file)
        if path is None:
            return
        cwd = os.path.isdir(path) and path or os.path.dirname(path)
        subprocess.Popen(['hg', 'config', 'paths'], cwd=cwd, shell=False)

    def _revert_cb(self, window, vfs_files):
        self._run_dialog('revert', vfs_files)

    def _serve_cb(self, window, vfs_file):
        self._run_dialog('serve', [vfs_file])

    def _status_cb(self, window, vfs_file):
        self._run_dialog('status', [vfs_file])

    def _sync_cb(self, window, vfs_file):
        self._run_dialog('synch', [vfs_file])

    def _uname_cb(self, window, vfs_file):
        path = self.get_path_for_vfs_file(vfs_file)
        if path is None:
            return
        cwd = os.path.isdir(path) and path or os.path.dirname(path)
        subprocess.Popen(['hg', 'config', 'uname'], cwd=cwd, shell=False)

    def _update_cb(self, window, vfs_file):
        self._run_dialog('update', [vfs_file])

    def _view_cb(self, window, vfs_file):
        path = self.get_path_for_vfs_file(vfs_file)
        if path is None:
            return
        repo = self.get_repo_for_path(path)
        if repo is None:
            return
        cwd = os.path.isdir(path) and path or os.path.dirname(path)
        viewcmd = repo.ui.config('tortoisehg', 'view', 'hgk')
        if viewcmd == 'hgview':
            subprocess.Popen(['hgview'], shell=False, cwd=cwd)
        else:
            subprocess.Popen(['hg', 'view'], shell=False, cwd=cwd)

    def _web_cb(self, window, vfs_file):
        path = self.get_path_for_vfs_file(vfs_file)
        if path is None:
            return
        cwd = os.path.isdir(path) and path or os.path.dirname(path)
        subprocess.Popen(['hg', 'config', 'web'], cwd=cwd, shell=False)

    def _run_dialog(self, hgcmd, vfs_files):
        '''
        hgcmd - hgproc subcommand
        vfs_files - directory, or list of selected files
        '''
        paths = [self.get_path_for_vfs_file(f) for f in vfs_files]
        if paths[0] is None:
            return

        path = paths[0]
        repo = self.get_repo_for_path(path)
        cwd = os.path.isdir(path) and path or os.path.dirname(path)

        # Use temporary file to store file list (avoid shell command
        # line limitations)
        fd, tmpfile = tempfile.mkstemp(prefix="tortoisehg_filelist_")
        os.write(fd, "\n".join(paths))
        os.close(fd)

        cmdopts  = [sys.executable, self.hgproc]
        cmdopts += ['--root', repo.root]
        cmdopts += ['--cwd', cwd]
        cmdopts += ['--listfile', tmpfile, '--deletelistfile']
        cmdopts += ['--command', hgcmd]
        subprocess.Popen(cmdopts, cwd=cwd, shell=False)

        # Remove cached repo object, dirstate may change
        self.cacherepo = None
        self.cacheroot = None

    def get_background_items(self, window, vfs_file):
        '''Build context menu for current directory'''
        items = []
        path = self.get_path_for_vfs_file(vfs_file)
        if path is None:
            return
        repo = self.get_repo_for_path(path)
        if repo is None:
            item = nautilus.MenuItem('HgNautilus::newtree',
                                 'Create New Repository',
                                 'Make directory versioned',
                                 self.icon('menucreaterepos.ico'))
            item.connect('activate', self._init_cb, vfs_file)
            items.append(item)
            item = nautilus.MenuItem('HgNautilus::clone',
                                 'Create Clone',
                                 'Create clone here from source',
                                 self.icon('menuclone.ico'))
            item.connect('activate', self._clone_cb, vfs_file)
            items.append(item)
            item = nautilus.MenuItem('HgNautilus::terminal',
                                 'Open Terminal Here',
                                 'Open terminal in current directory')
            item.connect('activate', self._open_terminal_cb, vfs_file)
            items.append(item)
            return items

        item = nautilus.MenuItem('HgNautilus::commit',
                             'Commit',
                             'Commit changes',
                             self.icon('menucommit.ico'))
        item.connect('activate', self._commit_cb, [vfs_file])
        items.append(item)

        item = nautilus.MenuItem('HgNautilus::status',
                             'Show Status',
                             'Show Repository Status',
                             self.icon('menushowchanged.ico'))
        item.connect('activate', self._status_cb, vfs_file)
        items.append(item)

        item = nautilus.MenuItem('HgNautilus::diff',
                             'Visual Diff',
                             'Show Changes',
                             self.icon('menudiff.ico'))
        item.connect('activate', self._diff_cb, [vfs_file])
        items.append(item)

        item = nautilus.MenuItem('HgNautilus::log',
                             'View Changelog',
                             'Show revision history',
                             self.icon('menulog.ico'))
        item.connect('activate', self._history_cb, [vfs_file])
        items.append(item)

        item = nautilus.MenuItem('HgNautilus::dag',
                             'Revision Graph',
                             'Show revision DAG',
                             self.icon('menurevisiongraph.ico'))
        item.connect('activate', self._view_cb, vfs_file)
        items.append(item)

        item = nautilus.MenuItem('HgNautilus::update',
                             'Checkout Revision',
                             'Checkout revision',
                             self.icon('menucheckout.ico'))
        item.connect('activate', self._update_cb, vfs_file)
        items.append(item)

        item = nautilus.MenuItem('HgNautilus::merge',
                             'Merge Revisions',
                             'Merge with another revision',
                             self.icon('menumerge.ico'))
        item.connect('activate', self._merge_cb, vfs_file)
        items.append(item)

        item = nautilus.MenuItem('HgNautilus::sync',
                             'Synchronize',
                             'Sync with another repository',
                             self.icon('menusynch.ico'))
        item.connect('activate', self._sync_cb, vfs_file)
        items.append(item)

        item = nautilus.MenuItem('HgNautilus::serve',
                             'Web Server',
                             'Start internal web server',
                             self.icon('proxy.ico'))
        item.connect('activate', self._serve_cb, vfs_file)
        items.append(item)

        # add hg-config dialogs
        if repo.ui.config('tortoisehg', 'hgconfig') in ('1', 'True', 'yes'):
            item = nautilus.MenuItem('HgNautilus::uname',
                                 'Config Username',
                                 'Configure Mercurial username')
            item.connect('activate', self._uname_cb, vfs_file)
            items.append(item)
            item = nautilus.MenuItem('HgNautilus::web',
                                 'Config Web Server',
                                 'Configure web server')
            item.connect('activate', self._web_cb, vfs_file)
            items.append(item)
            item = nautilus.MenuItem('HgNautilus::paths',
                                 'Config Paths',
                                 'Configure peer repository paths')
            item.connect('activate', self._paths_cb, vfs_file)
            items.append(item)

        item = nautilus.MenuItem('HgNautilus::terminal',
                             'Open Terminal Here',
                             'Open terminal in current directory')
        item.connect('activate', self._open_terminal_cb, vfs_file)
        items.append(item)
        return items

    def get_file_items(self, window, vfs_files):
        '''Build context menu for selected files'''
        items = []
        if not vfs_files:
            return items

        vfs_file = vfs_files[0]
        path = self.get_path_for_vfs_file(vfs_file)
        repo = self.get_repo_for_path(path)
        if repo is None:
            if not vfs_file.is_directory():
                return items

            # Menu for unrevisioned subdirectory
            name = vfs_files[0].get_name()
            item = nautilus.MenuItem('HgNautilus::newtree',
                                 'Make directory versioned',
                                 'Create Repository in %s' % name,
                                 self.icon('menucreaterepos.ico'))
            item.connect('activate', self._init_cb, vfs_file)
            items.append(item)
            item = nautilus.MenuItem('HgNautilus::clone',
                                 'Create clone from source',
                                 'Create Clone in %s' % name,
                                 self.icon('menuclone.ico'))
            item.connect('activate', self._clone_cb, vfs_file)
            items.append(item)
            item = nautilus.MenuItem('HgNautilus::terminal',
                                 'Open Terminal Here',
                                 'Open Terminal in %s' % name)
            item.connect('activate', self._open_terminal_cb, vfs_file)
            items.append(item)
            return items

        localpaths = []
        for vfs_file in vfs_files:
            path = self.get_path_for_vfs_file(vfs_file)
            if path is None:
                continue
            localpath = path[len(repo.root)+1:]
            localpaths.append(localpath)

        changes = repo.dirstate.status(localpaths, util.always, True, True)
        (lookup, modified, added, removed, deleted, unknown,
                ignored, clean) = changes

        # Add menu items based on states list
        if unknown:
            item = nautilus.MenuItem('HgNautilus::add',
                                 'Add Files',
                                 'Add unversioned files',
                                 self.icon('menuadd.ico'))
            item.connect('activate', self._add_cb, vfs_files)
            items.append(item)

        if modified or added or removed or deleted or unknown:
            item = nautilus.MenuItem('HgNautilus::commit',
                                 'Commit Files',
                                 'Commit changes',
                                 self.icon('menucommit.ico'))
            item.connect('activate', self._commit_cb, vfs_files)
            items.append(item)
            item = nautilus.MenuItem('HgNautilus::revert',
                                 'Undo Changes',
                                 'Revert changes to files',
                                 self.icon('menurevert.ico'))
            item.connect('activate', self._revert_cb, vfs_files)
            items.append(item)

        if modified or clean:
            item = nautilus.MenuItem('HgNautilus::log',
                                 'File Changelog',
                                 'Show file revision history',
                                 self.icon('menulog.ico'))
            item.connect('activate', self._history_cb, vfs_files)
            items.append(item)

        if modified:
            item = nautilus.MenuItem('HgNautilus::diff',
                                 'File Diffs',
                                 'Show file changes',
                                 self.icon('menudiff.ico'))
            item.connect('activate', self._diff_cb, vfs_files)
            items.append(item)

        return items

    def get_columns(self):
        return nautilus.Column("HgNautilus::hg_status",
                               "hg_status",
                               "HG Status",
                               "Version control status"),

    def update_file_info(self, file):
        '''Return emblem and hg status for this file'''
        path = self.get_path_for_vfs_file(file)
        if path is None or file.is_directory():
            return
        repo = self.get_repo_for_path(path)
        if repo is None:
            return

        emblem = None
        status = '?'

        # This is not what the API is optimized for, but this appears
        # to work efficiently enough
        localpath = path[len(repo.root)+1:]
        changes = repo.dirstate.status([localpath], util.always, True, True)
        (lookup, modified, added, removed, deleted, unknown,
                ignored, clean) = changes

        if localpath in clean:
            emblem = 'default'
            status = 'clean'
        elif localpath in modified:
            emblem = 'cvs-modified'
            status = 'modified'
        elif localpath in added:
            emblem = 'cvs-added'
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

        if emblem is not None:
            file.add_emblem(emblem)
        file.add_string_attribute('hg_status', status)

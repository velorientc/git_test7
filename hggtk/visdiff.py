# visdiff.py - launch external visual diff tools
#
# Copyright 2009 Steve Borho
#
# Based on extdiff extension for Mercurial
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

import gtk
import gobject
from mercurial.i18n import _
from mercurial.node import short
from mercurial import hg, ui, cmdutil, util, commands
from gdialog import Prompt
from hglib import RepoError, rootpath
import os, shlex, subprocess, shutil, tempfile
import shlib

try:
    import win32con
    openflags = win32con.CREATE_NO_WINDOW
except ImportError:
    openflags = 0

def snapshot_node(repo, files, node, tmproot):
    '''snapshot files as of some revision'''
    dirname = os.path.basename(repo.root)
    if dirname == "":
        dirname = "root"
    dirname = '%s.%s' % (dirname, short(node))
    base = os.path.join(tmproot, dirname)
    os.mkdir(base)
    ctx = repo[node]
    for fn in files:
        wfn = util.pconvert(fn)
        if not wfn in ctx:
            # skipping new file after a merge ?
            continue
        dest = os.path.join(base, wfn)
        destdir = os.path.dirname(dest)
        if not os.path.isdir(destdir):
            os.makedirs(destdir)
        data = repo.wwritedata(wfn, ctx[wfn].data())
        open(dest, 'wb').write(data)
    return dirname

class FileSelectionDialog(gtk.Dialog):
    'Dialog for selecting visual diff candidates'
    def __init__(self, pats, opts):
        'Initialize the Dialog'
        gtk.Dialog.__init__(self)
        self.set_title('Visual Diffs')
        shlib.set_tortoise_icon(self, 'menushowchanged.ico')
        self.set_default_size(400, 150)

        lbl = gtk.Label(_('Temporary files are removed when this dialog'
            ' is closed'))
        self.vbox.pack_start(lbl, False, False, 2)

        scroller = gtk.ScrolledWindow()
        scroller.set_shadow_type(gtk.SHADOW_IN)
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        model = gtk.ListStore(str, str)
        treeview = gtk.TreeView(model)
        treeview.get_selection().set_mode(gtk.SELECTION_SINGLE)
        scroller.add(treeview)
        self.vbox.pack_start(scroller, True, True, 2)

        settings = shlib.Settings('visdiff')
        single = settings.get_value('launchsingle', False)
        check = gtk.CheckButton(_('Always launch single files'))
        check.set_active(single)
        self.vbox.pack_start(check, False, False, 2)
        self.singlecheck = check

        treeview.connect('row-activated', self.rowactivated)
        treeview.set_headers_visible(False)
        treeview.set_property('enable-grid-lines', True)
        treeview.set_enable_search(False)

        cell = gtk.CellRendererText()
        stcol = gtk.TreeViewColumn('Status', cell)
        stcol.set_resizable(True)
        stcol.add_attribute(cell, 'text', 0)
        treeview.append_column(stcol)

        cell = gtk.CellRendererText()
        fcol = gtk.TreeViewColumn('Filename', cell)
        fcol.set_resizable(True)
        fcol.add_attribute(cell, 'text', 1)
        treeview.append_column(fcol)

        try:
            repo = hg.repository(ui.ui(), path=rootpath())
            self.diffpath, self.diffopts = self.readtool(repo.ui)
            if self.diffpath:
                self.find_files(repo, pats, opts, model)
            else:
                Prompt(_('No visual diff tool'), 
                       _('No visual diff tool has been configured'), None).run()
        except RepoError:
            pass

    def readtool(self, ui):
        vdiff = ui.config('tortoisehg', 'vdiff', 'vdiff')
        if not vdiff:
            return '', None
        for cmd, path in ui.configitems('extdiff'):
            if cmd.startswith('cmd.'):
                cmd = cmd[4:]
                if cmd != vdiff:
                    continue
                if not path:
                    path = cmd
                diffopts = ui.config('extdiff', 'opts.' + cmd, '')
                diffopts = diffopts and [diffopts] or []
                return path, diffopts
            elif cmd == vdiff:
                # command = path opts
                if path:
                    diffopts = shlex.split(path)
                    path = diffopts.pop(0)
                else:
                    path, diffopts = cmd, []
                return path, diffopts
        return '', None

    def find_files(self, repo, pats, opts, model):
        revs = opts.get('rev')
        change = opts.get('change')

        if change:
            title = _('changeset ') + str(change)
            node2 = repo.lookup(change)
            node1 = repo[node2].parents()[0].node()
        else:
            if revs:
                title = _('revision(s) ') + str(revs[0])
            else:
                title = _('working changes')
            node1, node2 = cmdutil.revpair(repo, revs)

        title = _('Visual Diffs - ') + title
        if pats:
            title += ' filtered'
        self.set_title(title)

        matcher = cmdutil.match(repo, pats, opts)
        modified, added, removed = repo.status(node1, node2, matcher)[:3]
        if not (modified or added or removed):
            Prompt(_('No file changes'), 
                   _('There are no file changes to view'), self).run()
            # GTK+ locks up if this is done immediately here
            gobject.idle_add(self.destroy)
            return

        tmproot = tempfile.mkdtemp(prefix='extdiff.')
        self.connect('destroy', self.delete_tmproot, tmproot)
        dir2 = ''
        dir2root = ''
        # Always make a copy of node1
        dir1 = snapshot_node(repo, modified + removed, node1, tmproot)

        # If node2 in not the wc or there is >1 change, copy it
        if node2:
            dir2 = snapshot_node(repo, modified + added, node2, tmproot)
        else:
            # This lets the diff tool open the changed file directly
            dir2root = repo.root

        self.dirs = (dir1, dir2, dir2root, tmproot)

        for m in modified:
            model.append(['M', m])
        for a in added:
            model.append(['A', a])
        for r in removed:
            model.append(['R', r])
        if len(model) == 1 and self.singlecheck.get_active():
            self.launch(*model[0])

    def delete_tmproot(self, _, tmproot):
        settings = shlib.Settings('visdiff')
        settings.set_value('launchsingle', self.singlecheck.get_active())
        settings.write()
        shutil.rmtree(tmproot)

    def rowactivated(self, tree, path, column):
        selection = tree.get_selection()
        if selection.count_selected_rows() != 1:
            return False
        model, paths = selection.get_selected_rows()
        self.launch(*model[paths[0]])

    def launch(self, st, fname):
        dir1, dir2, dir2root, tmproot = self.dirs
        if st == 'A':
            dir1 = os.devnull
            dir2 = os.path.join(dir2root, dir2, util.localpath(fname))
        elif st == 'R':
            dir1 = os.path.join(dir1, util.localpath(fname))
            dir2 = os.devnull
        else:
            dir1 = os.path.join(dir1, util.localpath(fname))
            dir2 = os.path.join(dir2root, dir2, util.localpath(fname))
        cmdline = [self.diffpath] + self.diffopts + [dir1, dir2]
        subprocess.Popen(cmdline, shell=False, cwd=tmproot,
                       creationflags=openflags,
                       stderr=subprocess.PIPE,
                       stdout=subprocess.PIPE,
                       stdin=subprocess.PIPE)

def run(pats, **opts):
    dialog = FileSelectionDialog(pats, opts)
    dialog.connect('destroy', gtk.main_quit)
    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

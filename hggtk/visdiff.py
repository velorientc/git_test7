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
import os
import shlex
import subprocess
import shutil
import tempfile

from mercurial import hg, ui, cmdutil, util

from thgutil.i18n import _
from thgutil import hglib, settings, paths

from hggtk import gdialog, gtklib

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
    dirname = '%s.%s' % (dirname, str(repo[node]))
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
    def __init__(self, canonpats, opts):
        'Initialize the Dialog'
        gtk.Dialog.__init__(self)
        gtklib.set_tortoise_icon(self, 'menushowchanged.ico')
        gtklib.set_tortoise_keys(self)

        self.set_title(_('Visual Diffs'))
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
        treeview.set_search_equal_func(self.search_filelist)
        scroller.add(treeview)
        self.vbox.pack_start(scroller, True, True, 2)

        hbox = gtk.HBox()
        self.vbox.pack_start(hbox, False, False, 2)
        vsettings = settings.Settings('visdiff')
        single = vsettings.get_value('launchsingle', False)
        check = gtk.CheckButton(_('Always launch single files'))
        check.set_active(single)
        hbox.pack_start(check, True, True, 2)
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
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except hglib.RepoError:
            # hgtk should catch this earlier
            gdialog.Prompt(_('No repository'),
                   _('No repository found here'), None).run()
            return

        tools = readtools(repo.ui)
        preferred = repo.ui.config('tortoisehg', 'vdiff', 'vdiff')
        if preferred and preferred in tools:
            if len(tools) > 1:
                lbl = gtk.Label(_('Select diff tool'))
                combo = gtk.combo_box_new_text()
                for i, name in enumerate(tools.iterkeys()):
                    combo.append_text(name)
                    if name == preferred:
                        defrow = i
                combo.connect('changed', self.toolselect, tools)
                combo.set_active(defrow)
                hbox.pack_start(lbl, False, False, 2)
                hbox.pack_start(combo, False, False, 2)
            else:
                self.diffpath, self.diffopts = tools[preferred]
            cwd = os.getcwd()
            try:
                os.chdir(repo.root)
                self.find_files(repo, canonpats, opts, model)
            finally:
                os.chdir(cwd)
        else:
            gdialog.Prompt(_('No visual diff tool'),
                   _('No visual diff tool has been configured'), None).run()

    def search_filelist(self, model, column, key, iter):
        'case insensitive filename search'
        key = key.lower()
        if key in model.get_value(iter, 1).lower():
            return False
        return True

    def toolselect(self, combo, tools):
        sel = combo.get_active_text()
        if sel in tools:
            self.diffpath, self.diffopts = tools[sel]

    def find_files(self, repo, pats, opts, model):
        revs = opts.get('rev')
        change = opts.get('change')

        if change:
            title = _('changeset ') + str(change)
            node2 = repo.lookup(change)
            node1 = repo[node2].parents()[0].node()
        else:
            if revs:
                title = _('revision(s) ') + ' to '.join(revs)
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
            gdialog.Prompt(_('No file changes'),
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
            model.append(['M', hglib.toutf(m)])
        for a in added:
            model.append(['A', hglib.toutf(a)])
        for r in removed:
            model.append(['R', hglib.toutf(r)])
        if len(model) == 1 and self.singlecheck.get_active():
            self.launch(*model[0])

    def delete_tmproot(self, _, tmproot):
        vsettings = settings.Settings('visdiff')
        vsettings.set_value('launchsingle', self.singlecheck.get_active())
        vsettings.write()
        shutil.rmtree(tmproot)

    def rowactivated(self, tree, path, column):
        selection = tree.get_selection()
        if selection.count_selected_rows() != 1:
            return False
        model, paths = selection.get_selected_rows()
        self.launch(*model[paths[0]])

    def launch(self, st, fname):
        fname = hglib.fromutf(fname)
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
        if os.name == 'nt':
            cmdline = ('%s %s %s %s' %
                   (util.shellquote(self.diffpath), ' '.join(self.diffopts),
                    util.shellquote(dir1), util.shellquote(dir2)))
        else:
            cmdline = [self.diffpath] + self.diffopts + [dir1, dir2]
        try:
            subprocess.Popen(cmdline, shell=False, cwd=tmproot,
                       creationflags=openflags,
                       stderr=subprocess.PIPE,
                       stdout=subprocess.PIPE,
                       stdin=subprocess.PIPE)
        except Exception, e:
            gdialog.Prompt(_('Tool launch failure'),
                    _('%s : %s') % (self.diffpath, str(e)), None).run()

def readtools(ui):
    tools = {}
    for cmd, path in ui.configitems('extdiff'):
        if cmd.startswith('cmd.'):
            cmd = cmd[4:]
            if not path:
                path = cmd
            diffopts = ui.config('extdiff', 'opts.' + cmd, '')
            diffopts = diffopts and [diffopts] or []
            tools[cmd] = [path, diffopts]
        elif cmd.startswith('opts.'):
            continue
        else:
            # command = path opts
            if path:
                diffopts = shlex.split(path)
                path = diffopts.pop(0)
            else:
                path, diffopts = cmd, []
            tools[cmd] = [path, diffopts]
    return tools

def run(ui, *pats, **opts):
    root = paths.find_root()
    canonpats = []
    for f in pats:
        canonpats.append(util.canonpath(root, os.getcwd(), f))
    return FileSelectionDialog(canonpats, opts)

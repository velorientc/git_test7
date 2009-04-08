# visdiff.py - launch external visual diff tools
#
# Copyright 2009 Steve Borho
#
# Based on extdiff extension for Mercurial
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

import gtk
from mercurial.i18n import _
from mercurial.node import short
from mercurial import cmdutil, util, commands
from gdialog import Prompt
import os, shlex, subprocess, shutil, tempfile
import shlib

try:
    import win32con
    openflags = win32con.CREATE_NO_WINDOW
except ImportError:
    openflags = 0

diffpath, diffopts = None, None

class FileSelectionDialog(gtk.Dialog):
    'Dialog for selecting visual diff candidates'
    def __init__(self, title, modified, added, removed,
            dir1, dir2, dir2root, tmproot):
        'Initialize the Dialog'
        gtk.Dialog.__init__(self)
        shlib.set_tortoise_icon(self, 'menushowchanged.ico')
        self.set_title('Visual Diffs - ' + title)
        self.diffs = (dir1, dir2, dir2root, tmproot)
        self.set_default_size(400, 150)

        scroller = gtk.ScrolledWindow()
        scroller.set_shadow_type(gtk.SHADOW_IN)
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        model = gtk.ListStore(str, str)
        treeview = gtk.TreeView(model)
        treeview.get_selection().set_mode(gtk.SELECTION_SINGLE)
        scroller.add(treeview)
        self.vbox.pack_start(scroller, True, True)

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

        for m in modified:
            treeview.get_model().append(['M', m])
        for a in added:
            treeview.get_model().append(['A', a])
        for r in removed:
            treeview.get_model().append(['R', r])

    def rowactivated(self, tree, path, column):
        global diffpath, diffopts
        selection = tree.get_selection()
        if selection.count_selected_rows() != 1:
            return False
        model, paths = selection.get_selected_rows()
        st, fname = model[paths[0]]
        dir1, dir2, dir2root, tmproot = self.diffs
        if st == 'A':
            dir1 = os.devnull
            dir2 = os.path.join(dir2root, dir2, util.localpath(fname))
        elif st == 'R':
            dir1 = os.path.join(dir1, util.localpath(fname))
            dir2 = os.devnull
        else:
            dir1 = os.path.join(dir1, util.localpath(fname))
            dir2 = os.path.join(dir2root, dir2, util.localpath(fname))
        cmdline = [diffpath] + diffopts + [dir1, dir2]
        subprocess.Popen(cmdline, shell=False, cwd=tmproot,
                       creationflags=openflags,
                       stderr=subprocess.PIPE,
                       stdout=subprocess.PIPE,
                       stdin=subprocess.PIPE)

def showfiles(title, modified, removed, added, dir1, dir2, dir2root, tmproot):
    '''open a treeview dialog to allow user to select files'''
    dialog = FileSelectionDialog(title, modified, added, removed,
            dir1, dir2, dir2root, tmproot)
    dialog.show_all()
    dialog.connect('destroy', gtk.main_quit)
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

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

def visualdiff(repo, pats, opts):
    global diffpath, diffopts
    if diffpath is None:
        diffpath, diffopts = init(repo.ui)
    if not diffpath:
        Prompt(_('No visual diff tool'), 
               _('No tool has been configured'), None).run()
        return

    revs = opts.get('rev')
    change = opts.get('change')

    if change:
        title = _('changeset ') + str(change)
        node2 = repo.lookup(change)
        node1 = repo[node2].parents()[0].node()
    else:
        if revs:
            title = _('revision(s) ') + str(revs)
        else:
            title = _('working changes')
        node1, node2 = cmdutil.revpair(repo, revs)

    matcher = cmdutil.match(repo, pats, opts)
    modified, added, removed = repo.status(node1, node2, matcher)[:3]
    if not (modified or added or removed):
        Prompt(_('No files to diff'), _('No modified files'), None).run()
        return

    tmproot = tempfile.mkdtemp(prefix='extdiff.')
    dir2 = ''
    try:
        # Always make a copy of node1
        dir1 = snapshot_node(repo, modified + removed, node1, tmproot)
        changes = len(modified) + len(removed) + len(added)

        # If node2 in not the wc or there is >1 change, copy it
        if node2:
            dir2 = snapshot_node(repo, modified + added, node2, tmproot)
        else:
            # This lets the diff tool open the changed file directly
            dir2root = repo.root

        # If only one change, diff the files instead of the directories
        if changes == 1 :
            if len(modified):
                dir1 = os.path.join(dir1, util.localpath(modified[0]))
                dir2 = os.path.join(dir2root, dir2, util.localpath(modified[0]))
            elif len(removed) :
                dir1 = os.path.join(dir1, util.localpath(removed[0]))
                dir2 = os.devnull
            else:
                dir1 = os.devnull
                dir2 = os.path.join(dir2root, dir2, util.localpath(added[0]))
            cmdline = [diffpath] + diffopts + [dir1, dir2]
            subprocess.Popen(cmdline, shell=False, cwd=tmproot,
                           creationflags=openflags,
                           stderr=subprocess.PIPE,
                           stdout=subprocess.PIPE,
                           stdin=subprocess.PIPE).wait()
        else:
            showfiles(title, modified, removed, added,
                    dir1, dir2, dir2root, tmproot)
    finally:
        shutil.rmtree(tmproot)

def init(ui):
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

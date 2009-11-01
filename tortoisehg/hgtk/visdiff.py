# visdiff.py - launch external visual diff tools
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import gobject
import os
import shlex
import subprocess
import shutil
import tempfile
import re

from mercurial import hg, ui, cmdutil, util
from mercurial.node import short, nullid

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, settings, paths

from tortoisehg.hgtk import gdialog, gtklib

try:
    import win32con
    openflags = win32con.CREATE_NO_WINDOW
except ImportError:
    openflags = 0

def snapshot(repo, files, node, tmproot):
    '''snapshot files as of some revision'''
    dirname = os.path.basename(repo.root)
    if dirname == "":
        dirname = "root"
    if node is not None:
        dirname = '%s.%s' % (dirname, short(node))
    base = os.path.join(tmproot, dirname)
    os.mkdir(base)
    ctx = repo[node]
    for fn in files:
        wfn = util.pconvert(fn)
        if not wfn in ctx:
            # File doesn't exist; could be a bogus modify
            continue
        dest = os.path.join(base, wfn)
        destdir = os.path.dirname(dest)
        if not os.path.isdir(destdir):
            os.makedirs(destdir)
        data = repo.wwritedata(wfn, ctx[wfn].data())
        f = open(dest, 'wb')
        f.write(data)
        f.close()
    return dirname

class FileSelectionDialog(gtk.Dialog):
    'Dialog for selecting visual diff candidates'
    def __init__(self, canonpats, opts):
        'Initialize the Dialog'
        gtk.Dialog.__init__(self, title=_('Visual Diffs'))
        gtklib.set_tortoise_icon(self, 'menushowchanged.ico')
        gtklib.set_tortoise_keys(self)

        self.set_default_size(400, 150)
        self.set_has_separator(False)
        self.tmproot = None

        lbl = gtk.Label(_('Temporary files are removed when this dialog'
            ' is closed'))
        self.vbox.pack_start(lbl, False, False, 2)

        scroller = gtk.ScrolledWindow()
        scroller.set_shadow_type(gtk.SHADOW_IN)
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        treeview = gtk.TreeView()
        self.treeview = treeview
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

        try:
            path = opts.get('bundle') or paths.find_root()
            repo = hg.repository(ui.ui(), path=path)
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
                model = self.find_files(repo, canonpats, opts, treeview)
                do3way = model.get_n_columns() == 3
                treeview.set_model(model)
                cell = gtk.CellRendererText()
                stcol = gtk.TreeViewColumn('Status 1', cell)
                stcol.set_resizable(True)
                stcol.add_attribute(cell, 'text', 0)
                treeview.append_column(stcol)
                if do3way:
                    cell = gtk.CellRendererText()
                    stcol = gtk.TreeViewColumn('Status 2', cell)
                    stcol.set_resizable(True)
                    stcol.add_attribute(cell, 'text', 1)
                    treeview.append_column(stcol)
                cell = gtk.CellRendererText()
                fcol = gtk.TreeViewColumn('Filename', cell)
                fcol.set_resizable(True)
                fcol.add_attribute(cell, 'text', do3way and 2 or 1)
                treeview.append_column(fcol)
                if len(model) == 1 and self.singlecheck.get_active():
                    self.launch(*model[0])
            finally:
                os.chdir(cwd)
        else:
            gdialog.Prompt(_('No visual diff tool'),
                   _('No visual diff tool has been configured'), None).run()
            from tortoisehg.hgtk import thgconfig
            dlg = thgconfig.ConfigDialog(False)
            dlg.show_all()
            dlg.focus_field('tortoisehg.vdiff')
            dlg.run()
            dlg.hide()
            gtklib.idle_add_single_call(self.destroy)

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

    def find_files(self, repo, pats, opts, treeview):

        revs = opts.get('rev')
        change = opts.get('change')
        do3way = '$parent2' in ''.join(self.diffopts)

        if change and (do3way or not revs):
            title = _('changeset ') + str(change)
            node2 = repo.lookup(change)
            node1a, node1b = repo.changelog.parents(node2)
        else:
            node1a, node2 = cmdutil.revpair(repo, revs)
            if not revs:
                title = _('working changes')
                node1b = repo.dirstate.parents()[1]
            else:
                title = _('revisions ') + ' to '.join(revs)
                node1b = nullid

        # Disable 3-way merge if there is only one parent
        if node1b == nullid:
            do3way = False

        title = _('Visual Diffs - ') + title
        if pats:
            title += ' filtered'
        self.set_title(title)

        matcher = cmdutil.match(repo, pats, opts)
        mod_a, add_a, rem_a = map(set, repo.status(node1a, node2, matcher)[:3])
        if do3way:
            mod_b, add_b, rem_b = map(set, repo.status(node1b, node2, matcher)[:3])
        else:
            mod_b, add_b, rem_b = set(), set(), set()
        modadd = mod_a | add_a | mod_b | add_b
        common = modadd | rem_a | rem_b
        if not common:
            gdialog.Prompt(_('No file changes'),
                   _('There are no file changes to view'), self).run()
            # GTK+ locks up if this is done immediately here
            gtklib.idle_add_single_call(self.destroy)
            return

        tmproot = tempfile.mkdtemp(prefix='extdiff.')
        self.connect('response', self.response)
        self.tmproot = tmproot

        # Always make a copy of node1a (and node1b, if applicable)
        dir1a_files = mod_a | rem_a | ((mod_b | add_b) - add_a)
        dir1a = snapshot(repo, dir1a_files, node1a, tmproot)
        if do3way:
            dir1b_files = mod_b | rem_b | ((mod_a | add_a) - add_b)
            dir1b = snapshot(repo, dir1b_files, node1b, tmproot)
        else:
            dir1b = None

        # If node2 in not the wc or there is >1 change, copy it
        dir2root = ''
        if node2:
            dir2 = snapshot(repo, modadd, node2, tmproot)
        elif len(common) > 1:
            #we only actually need to get the files to copy back to the working
            #dir in this case (because the other cases are: diffing 2 revisions
            #or single file -- in which case the file is already directly passed
            #to the diff tool).
            dir2 = snapshot(repo, modadd, None, tmproot)
        else:
            # This lets the diff tool open the changed file directly
            dir2 = ''
            dir2root = repo.root

        self.dirs = (dir1a, dir1b, dir2, dir2root, tmproot)

        def get_status(file, mod, add, rem):
            if file in mod:
                return 'M'
            if file in add:
                return 'A'
            if file in rem:
                return 'R'
            return ' '

        if do3way:
            model = gtk.ListStore(str, str, str)
            for f in common:
                model.append([get_status(f, mod_a, add_a, rem_a),
                              get_status(f, mod_b, add_b, rem_b),
                              hglib.toutf(f)])
        else:
            model = gtk.ListStore(str, str)
            for f in common:
                model.append([get_status(f, mod_a, add_a, rem_a),
                              hglib.toutf(f)])
        return model

    def response(self, window, resp):
        self.should_live()

    def should_live(self):
        vsettings = settings.Settings('visdiff')
        vsettings.set_value('launchsingle', self.singlecheck.get_active())
        vsettings.write()
        while self.tmproot:
            try:
                shutil.rmtree(self.tmproot)
                return False
            except (IOError, OSError), e:
                resp = gdialog.CustomPrompt(_('Unable to delete temp files'),
                    _('Close diff tools and try again, or quit to leak files?'),
                    self, (_('Try &Again'), _('&Quit')), 1).run()
                if resp == 0:
                    continue
                else:
                    return False
        return False

    def rowactivated(self, tree, path, column):
        selection = tree.get_selection()
        if selection.count_selected_rows() != 1:
            return False
        model, paths = selection.get_selected_rows()
        self.launch(*model[paths[0]])

    def launch(self, st1, st2, fname=None):
        if not fname:
            fname = st2
            st2 = None
        fname = hglib.fromutf(fname)
        dir1a, dir1b, dir2, dir2root, tmproot = self.dirs

        if st1 == 'A' or st2 == 'R':
            dir1a = os.devnull
        else:
            dir1a = os.path.join(dir1a, util.localpath(fname))
        if st2:
            if st2 == 'A' or st1 == 'R':
                dir1b = os.devnull
            else:
                dir1b = os.path.join(dir1b, util.localpath(fname))
        if st1 == 'R' or st2 == 'R':
            dir2 = os.devnull
        else:
            dir2 = os.path.join(dir2root, dir2, util.localpath(fname))

        # Function to quote file/dir names in the argument string
        # When not operating in 3-way mode, an empty string is returned for parent2
        replace = dict(parent=dir1a, parent1=dir1a, parent2=dir1b, child=dir2)
        def quote(match):
            key = match.group()[1:]
            if not st2 and key == 'parent2':
                return ''
            return util.shellquote(replace[key])

        # Match parent2 first, so 'parent1?' will match both parent1 and parent
        args = ' '.join(self.diffopts)
        regex = '\$(parent2|parent1?|child)'
        if not st2 and not re.search(regex, args):
            args += ' $parent1 $child'
        args = re.sub(regex, quote, args)
        cmdline = util.shellquote(self.diffpath) + ' ' + args

        if os.name == 'nt':
            cmdline = '"%s"' % cmdline
        try:
            subprocess.Popen(cmdline, shell=True, cwd=tmproot,
                       creationflags=openflags,
                       stderr=subprocess.PIPE,
                       stdout=subprocess.PIPE,
                       stdin=subprocess.PIPE)
        except (OSError, EnvironmentError), e:
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

def rawextdiff(ui, *pats, **opts):
    'launch raw extdiff command, block until finish'
    from hgext import extdiff
    try:
        path = opts.get('bundle') or paths.find_root()
        repo = hg.repository(ui, path=path)
    except hglib.RepoError:
        # hgtk should catch this earlier
        ui.warn(_('No repository found here') + '\n')
        return
    tools = readtools(ui)
    preferred = ui.config('tortoisehg', 'vdiff', 'vdiff')
    try:
        diffcmd, diffopts = tools[preferred]
    except KeyError:
        ui.warn(_('Extdiff command not recognized\n'))
        return
    pats = hglib.canonpaths(pats)

    # if both --change and --rev is given, remove --rev in 3-way mode,
    # and --change in normal mode
    if opts.get('change') and opts.get('rev'):
        if '$parent2' in ''.join(diffopts):
            del opts['rev']
        else:
            del opts['change']

    try:
        ret = extdiff.dodiff(ui, repo, diffcmd, diffopts, pats, opts)
    except OSError, e:
        ui.warn(str(e) + '\n')
        return
    if ret == 0:
        gdialog.Prompt(_('No file changes'),
                      _('There are no file changes to view'), None).run()

def run(ui, *pats, **opts):
    if ui.configbool('tortoisehg', 'vdiffnowin'):
        import sys
        # Spawn background process and exit
        if hasattr(sys, "frozen"):
            args = [sys.argv[0]]
        else:
            args = [sys.executable] + [sys.argv[0]]
        args.extend(['vdiff', '--nofork', '--raw'])
        revs = opts.get('rev', [])
        change = opts.get('change')
        if change:
            args.extend(['--change', str(change)])
        for r in revs:
            args.extend(['--rev', str(r)])
        bfile = opts.get('bundle')
        if bfile:
            args.extend(['--bundle', bfile])
        args.extend(pats)
        args.extend(opts.get('canonpats', []))
        if os.name == 'nt':
            args = ['"%s"' % arg for arg in args]
        oldcwd = os.getcwd()
        root = paths.find_root(oldcwd)
        try:
            os.chdir(root)
            os.spawnv(os.P_NOWAIT, sys.executable, args)
        finally:
            os.chdir(oldcwd)
        return None
    else:
        pats = hglib.canonpaths(pats)
        if opts.get('canonpats'):
            pats = list(pats) + opts['canonpats']
        return FileSelectionDialog(pats, opts)

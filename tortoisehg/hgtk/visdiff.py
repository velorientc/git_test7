# visdiff.py - launch external visual diff tools
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import gobject
import os
import subprocess
import shutil
import tempfile
import re

from mercurial import hg, ui, cmdutil, util, error
from mercurial.node import short, nullid

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, settings, paths

from tortoisehg.hgtk import gdialog, gtklib

try:
    import win32con
    openflags = win32con.CREATE_NO_WINDOW
except ImportError:
    openflags = 0

def snapshot(repo, files, ctx, tmproot):
    '''snapshot files as of some revision'''
    dirname = os.path.basename(repo.root) or 'root'
    if ctx.rev() is not None:
        dirname = '%s.%s' % (dirname, str(ctx))
    base = os.path.join(tmproot, dirname)
    os.mkdir(base)
    fns_and_mtime = []
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
        if ctx.rev() is None:
            fns_and_mtime.append((dest, repo.wjoin(fn), os.path.getmtime(dest)))
        else:
            # TODO: Mark file read-only to help diff tools
            pass
    return base, fns_and_mtime


def parserevs(repo, opts):
    revs = opts.get('rev')
    change = opts.get('change')

    ctx1b = None
    if change:
        ctx2 = repo[change]
        p = ctx2.parents()
        if len(p) > 1:
            ctx1a, ctx1b = p
        else:
            ctx1a = p[0]
    else:
        n1, n2 = cmdutil.revpair(repo, revs)
        ctx1a, ctx2 = repo[n1], repo[n2]
        p = ctx2.parents()
        if not revs and len(p) > 1:
            ctx1b = p[1]
    return ctx1a, ctx1b, ctx2


def selecttool(ui):
    tools = hglib.difftools(ui)
    preferred = ui.config('tortoisehg', 'vdiff', 'vdiff')
    try:
        if preferred not in tools:
            # arbitrary choice
            preferred = tools.keys()[0]
        return tools[preferred]
    except IndexError, KeyError:
        ui.warn(_('No diff tool found\n'))
    return None


def visualdiff(ui, repo, pats, opts):
    ctx1a, ctx1b, ctx2 = parserevs(repo, opts)

    tool = selecttool(repo.ui)
    if tool is None:
        ui.warn(_('No diff tool found.  Aborting.\n'))
        return 0
    diffcmd, diffopts, mergeopts = tool

    # Disable 3-way merge if there is only one parent or no tool support
    do3way = bool(mergeopts) and ctx1b is not None
    if do3way:
        args = ' '.join(mergeopts)
    else:
        args = ' '.join(diffopts)

    m = cmdutil.match(repo, pats, opts)
    n2 = ctx2.node()
    mod_a, add_a, rem_a = map(set, repo.status(ctx1a.node(), n2, m)[:3])
    if do3way:
        mod_b, add_b, rem_b = map(set, repo.status(ctx1b.node(), n2, m)[:3])
    else:
        mod_b, add_b, rem_b = set(), set(), set()
    MA = mod_a | add_a | mod_b | add_b
    MAR = MA | rem_a | rem_b
    if not MAR:
       return 0

    fns_and_mtime = []
    tmproot = tempfile.mkdtemp(prefix='visualdiff.')
    try:
        # Always make a copy of ctx1a (and ctx1b, if applicable)
        files = mod_a | rem_a | ((mod_b | add_b) - add_a)
        dir1a = snapshot(repo, files, ctx1a, tmproot)[0]
        if do3way:
            files = mod_b | rem_b | ((mod_a | add_a) - add_b)
            dir1b = snapshot(repo, files, ctx1b, tmproot)[0]
        else:
            dir1b = None

        if ctx2.rev() is not None:
            # If ctx2 is not the working copy, create a snapshot for it
            dir2 = snapshot(repo, MA, ctx2, tmproot)[0]
        elif len(MAR) == 1:
            # This lets the diff tool open the changed file directly
            dir2 = repo.root
        else:
            # Create a snapshot, record mtime to detect mods made by
            # diff tool
            dir2, fns_and_mtime = snapshot(repo, MA, ctx2, tmproot)

        # If only one change, diff the files instead of the directories
        # Handle bogus modifies correctly by checking if the files exist
        if len(MAR) == 1:
            lfile = util.localpath(MAR.pop())
            dir1a = os.path.join(dir1a, lfile)
            if not os.path.isfile(os.path.join(tmproot, dir1a)):
                dir1a = os.devnull
            if do3way:
                dir1b = os.path.join(dir1b, lfile)
                if not os.path.isfile(os.path.join(tmproot, dir1b)):
                    dir1b = os.devnull
            dir2 = os.path.join(dir2, lfile)

        # Function to quote file/dir names in the argument string.
        # When not operating in 3-way mode, an empty string is
        # returned for parent2
        replace = dict(parent=dir1a, parent1=dir1a, parent2=dir1b, child=dir2)
        def quote(match):
            key = match.group()[1:]
            if not do3way and key == 'parent2':
                return ''
            return util.shellquote(replace[key])

        # Match parent2 first, so 'parent1?' will match both parent1 and parent
        regex = '\$(parent2|parent1?|child)'
        if not do3way and not re.search(regex, args):
            args += ' $parent1 $child'
        args = re.sub(regex, quote, args)
        cmdline = util.shellquote(diffcmd) + ' ' + args
        cmdline = util.quotecommand(cmdline)

        ui.debug('running %r\n' % (cmdline))
        try:
            subprocess.Popen(cmdline, shell=True,
                             creationflags=openflags,
                             stderr=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             stdin=subprocess.PIPE).communicate()
        except (OSError, EnvironmentError), e:
            ui.warn(_('Tool launch failure: %s\n') % str(e))
            return 0

        # detect if changes were made to mirrored working files
        for copy_fn, working_fn, mtime in fns_and_mtime:
            if os.path.getmtime(copy_fn) != mtime:
                # TODO: Prompt dialog, yes or no, once
                ui.debug('file changed while diffing. '
                         'Overwriting: %s (src: %s)\n' % (working_fn, copy_fn))
                util.copyfile(copy_fn, working_fn)
        return 1
    finally:
        ui.note(_('cleaning up temp directory\n'))
        shutil.rmtree(tmproot)

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
        except error.RepoError:
            # hgtk should catch this earlier
            gdialog.Prompt(_('No repository'),
                   _('No repository found here'), None).run()
            return

        tools = hglib.difftools(repo.ui)
        preferred = repo.ui.config('tortoisehg', 'vdiff', 'vdiff')
        if preferred and preferred in tools:
            self.diffpath, self.diffopts, self.mergeopts = tools[preferred]
            if len(tools) > 1:
                lbl = gtk.Label(_('Select diff tool'))
                combo = gtk.combo_box_new_text()
                for i, name in enumerate(tools.iterkeys()):
                    combo.append_text(name)
                    if name == preferred:
                        defrow = i
                combo.set_active(defrow)
                combo.connect('changed', self.toolselect, tools)
                hbox.pack_start(lbl, False, False, 2)
                hbox.pack_start(combo, False, False, 2)

            cwd = os.getcwd()
            try:
                os.chdir(repo.root)
                model = self.find_files(repo, canonpats, opts)
            finally:
                os.chdir(cwd)

            treeview.set_model(model)
            do3way = model.get_n_columns() == 3
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
        'user selected a tool from the tool combo'
        sel = combo.get_active_text()
        if sel in tools:
            self.diffpath, self.diffopts, self.mergeopts = tools[sel]
        # TODO: Toggle display based on self.mergeopts

    def find_files(self, repo, pats, opts):
        ctx1a, ctx1b, ctx2 = parserevs(repo, opts)

        do3way = bool(self.mergeopts) and ctx1b is not None

        if ctx2.rev() is None:
            title = _('working changes')
        elif ctx1a == ctx2.parents()[0]:
            title = _('changeset ') + str(ctx2.rev())
        else:
            title = _('revisions %d to %d') % (ctx1a.rev(), ctx2.rev())
        title = _('Visual Diffs - ') + title
        if pats:
            title += _(' filtered')
        self.set_title(title)

        m = cmdutil.match(repo, pats, opts)
        n2 = ctx2.node()
        mod_a, add_a, rem_a = map(set, repo.status(ctx1a.node(), n2, m)[:3])
        if do3way:
            mod_b, add_b, rem_b = map(set, repo.status(ctx1b.node(), n2, m)[:3])
        else:
            mod_b, add_b, rem_b = set(), set(), set()
        MA = mod_a | add_a | mod_b | add_b
        MAR = MA | rem_a | rem_b
        if not MAR:
            gdialog.Prompt(_('No file changes'),
                   _('There are no file changes to view'), self).run()
            # GTK+ locks up if destroy() is called directly here
            gtklib.idle_add_single_call(self.destroy)
            return gtk.ListStore(str, str)

        tmproot = tempfile.mkdtemp(prefix='visualdiff.')
        self.connect('response', self.response)
        self.tmproot = tmproot

        # Always make a copy of node1a (and node1b, if applicable)
        files = mod_a | rem_a | ((mod_b | add_b) - add_a)
        dir1a = snapshot(repo, files, ctx1a, tmproot)[0]
        if do3way:
            files = mod_b | rem_b | ((mod_a | add_a) - add_b)
            dir1b = snapshot(repo, files, ctx1b, tmproot)[0]
        else:
            dir1b = None

        # If ctx2 is the working copy, use it directly
        if ctx2.rev() is None:
            dir2 = repo.root
        else:
            dir2 = snapshot(repo, MA, ctx2, tmproot)[0]

        self.dirs = (dir1a, dir1b, dir2, tmproot)

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
            for f in MAR:
                model.append([get_status(f, mod_a, add_a, rem_a),
                              get_status(f, mod_b, add_b, rem_b),
                              hglib.toutf(f)])
        else:
            model = gtk.ListStore(str, str)
            for f in MAR:
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
        do3way = bool(fname) and self.mergeopts
        if not fname:
            fname = st2
            st2 = None
        fname = hglib.fromutf(fname)
        dir1a, dir1b, dir2, tmproot = self.dirs

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
            dir2 = os.path.join(dir2, util.localpath(fname))

        # Function to quote file/dir names in the argument string When
        # not operating in 3-way mode, an empty string is returned for
        # parent2
        replace = dict(parent=dir1a, parent1=dir1a, parent2=dir1b, child=dir2)
        def quote(match):
            key = match.group()[1:]
            if not st2 and key == 'parent2':
                return ''
            return util.shellquote(replace[key])

        # Match parent2 first, so 'parent1?' will match both parent1 and parent
        args = do3way and self.mergeopts or self.diffopts
        args = ' '.join(args)
        regex = '\$(parent2|parent1?|child)'
        if not st2 and not re.search(regex, args):
            args += ' $parent1 $child'
        args = re.sub(regex, quote, args)
        cmdline = util.shellquote(self.diffpath) + ' ' + args
        cmdline = util.quotecommand(cmdline)
        try:
            subprocess.Popen(cmdline, shell=True,
                       creationflags=openflags,
                       stderr=subprocess.PIPE,
                       stdout=subprocess.PIPE,
                       stdin=subprocess.PIPE)
        except (OSError, EnvironmentError), e:
            gdialog.Prompt(_('Tool launch failure'),
                    _('%s : %s') % (self.diffpath, str(e)), None).run()

def rawextdiff(ui, *pats, **opts):
    'launch raw extdiff command, block until finish'
    from hgext import extdiff
    try:
        path = opts.get('bundle') or paths.find_root()
        repo = hg.repository(ui, path=path)
    except error.RepoError:
        # hgtk should catch this earlier
        ui.warn(_('No repository found here') + '\n')
        return
    pats = hglib.canonpaths(pats)
    try:
        ret = visualdiff(ui, repo, pats, opts)
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

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
import stat
import shutil
import threading
import tempfile
import re

from mercurial import hg, ui, cmdutil, util, error

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
        elif os.name != 'nt':
            # Make file read/only, to indicate it's static (archival) nature
            os.chmod(dest, stat.S_IREAD)
    return base, fns_and_mtime


def besttool(ui, tools):
    'Select preferred or highest priority tool from dictionary'
    preferred = ui.config('tortoisehg', 'vdiff') or ui.config('ui', 'merge')
    if preferred and preferred in tools:
        return preferred
    pris = []
    for t in tools.keys():
        p = int(ui.config('merge-tools', t + '.priority', 0))
        pris.append((-p, t))
    tools = sorted(pris)
    return tools[0][1]


def visualdiff(ui, repo, pats, opts):
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

    m = cmdutil.match(repo, pats, opts)
    n2 = ctx2.node()
    mod_a, add_a, rem_a = map(set, repo.status(ctx1a.node(), n2, m)[:3])
    if ctx1b:
        mod_b, add_b, rem_b = map(set, repo.status(ctx1b.node(), n2, m)[:3])
    else:
        mod_b, add_b, rem_b = set(), set(), set()
    MA = mod_a | add_a | mod_b | add_b
    MAR = MA | rem_a | rem_b
    if not MAR:
        gdialog.Prompt(_('No file changes'),
                       _('There are no file changes to view'), None).run()
        return None

    detectedtools = hglib.difftools(repo.ui)
    if not detectedtools:
        gdialog.Prompt(_('No diff tool found'),
                       _('No visual diff tools were detected'), None).run()
        return None

    preferred = besttool(repo.ui, detectedtools)
    dirdiff = repo.ui.configbool('merge-tools', preferred + '.dirdiff')

    # Build tool list based on diff-patterns matches
    toollist = set()
    patterns = ui.configitems('diff-patterns')
    patterns = [(p, t) for p,t in patterns if t in detectedtools]
    for path in MAR:
        for pat, tool in patterns:
            mf = match.match(repo.root, '', [pat])
            if mf(path):
                toollist.add(tool)
                break
        else:
            toollist.add(preferred)

    if len(toollist) > 1 or (len(MAR)>1 and not dirdiff):
        # Multiple required tools, or tool does not support directory diffs
        sa = [mod_a, add_a, rem_a]
        sb = [mod_b, add_b, rem_b]
        dlg = FileSelectionDialog(ui, repo, pats, ctx1a, sa, ctx1b, sb, ctx2)
        return dlg

    # We can directly use the selected tool, without a visual diff window
    assert(len(toollist)==1)
    diffcmd, diffopts, mergeopts = detectedtools[toollist.pop()]

    # Disable 3-way merge if there is only one parent or no tool support
    do3way = bool(mergeopts) and ctx1b is not None
    if do3way:
        args = ' '.join(mergeopts)
    else:
        args = ' '.join(diffopts)

    def dodiff(tmproot, diffcmd, args):
        fns_and_mtime = []

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
            gdialog.Prompt(_('Tool launch failure'),
                           _('%s : %s') % (diffcmd, str(e)), None).run()
            return None

        # detect if changes were made to mirrored working files
        for copy_fn, working_fn, mtime in fns_and_mtime:
            if os.path.getmtime(copy_fn) != mtime:
                ui.debug('file changed while diffing. '
                         'Overwriting: %s (src: %s)\n' % (working_fn, copy_fn))
                util.copyfile(copy_fn, working_fn)

    def dodiffwrapper():
        try:
            dodiff(tmproot, diffcmd, args)
        finally:
            ui.note(_('cleaning up temp directory\n'))
            shutil.rmtree(tmproot)

    tmproot = tempfile.mkdtemp(prefix='visualdiff.')
    if opts.get('mainapp'):
        dodiffwrapper()
    else:
        # We are not the main application, so this must be done in a
        # background thread
        thread = threading.Thread(target=dodiffwrapper, name='visualdiff')
        thread.setDaemon(True)
        thread.start()

class FileSelectionDialog(gtk.Dialog):
    'Dialog for selecting visual diff candidates'
    def __init__(self, ui, repo, pats, ctx1a, sa, ctx1b, sb, ctx2):
        'Initialize the Dialog'
        gtk.Dialog.__init__(self, title=_('Visual Diffs'))
        gtklib.set_tortoise_icon(self, 'menushowchanged.ico')
        gtklib.set_tortoise_keys(self)

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

        self.set_default_size(400, 150)
        self.set_has_separator(False)

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

        treeview.connect('row-activated', self.rowactivated)
        treeview.set_headers_visible(False)
        treeview.set_property('enable-grid-lines', True)
        treeview.set_enable_search(False)

        tools = hglib.difftools(ui)
        preferred = besttool(ui, tools)
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
            hbox = gtk.HBox()
            self.vbox.pack_start(hbox, False, False, 2)
            hbox.pack_start(lbl, False, False, 2)
            hbox.pack_start(combo, False, False, 2)

        cell = gtk.CellRendererText()
        stcol = gtk.TreeViewColumn('Status 1', cell)
        stcol.set_resizable(True)
        stcol.add_attribute(cell, 'text', 0)
        treeview.append_column(stcol)

        do3way = ctx1b is not None and self.mergeopts
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

        mod_a, add_a, rem_a = sa
        mod_b, add_b, rem_b = sb
        MA = mod_a | add_a | mod_b | add_b
        MAR = MA | rem_a | rem_b

        tmproot = tempfile.mkdtemp(prefix='visualdiff.')
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

        treeview.set_model(model)
        self.connect('response', self.response)

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

    def response(self, window, resp):
        self.should_live()

    def should_live(self):
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

def run(ui, *pats, **opts):
    try:
        path = opts.get('bundle') or paths.find_root()
        repo = hg.repository(ui, path=path)
    except error.RepoError:
        ui.warn(_('No repository found here') + '\n')
        return None

    pats = hglib.canonpaths(pats)
    if opts.get('canonpats'):
        pats = list(pats) + opts['canonpats']

    return visualdiff(ui, repo, pats, opts)

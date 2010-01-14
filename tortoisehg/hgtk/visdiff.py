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

from mercurial import hg, ui, cmdutil, util, error, match, copies

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, settings, paths

from tortoisehg.hgtk import gdialog, gtklib

try:
    import win32con
    openflags = win32con.CREATE_NO_WINDOW
except ImportError:
    openflags = 0

# Match parent2 first, so 'parent1?' will match both parent1 and parent
_regex = '\$(parent2|parent1?|child|plabel1|plabel2|clabel|ancestor|alabel)'

_nonexistant = _('[non-existant]')

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

def launchtool(cmd, opts, replace, block):
    def quote(match):
        key = match.group()[1:]
        return util.shellquote(replace[key])
    args = ' '.join(opts)
    args = re.sub(_regex, quote, args)
    cmdline = util.shellquote(cmd) + ' ' + args
    cmdline = util.quotecommand(cmdline)
    try:
        proc = subprocess.Popen(cmdline, shell=True,
                                creationflags=openflags,
                                stderr=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stdin=subprocess.PIPE)
        if block:
            proc.communicate()
    except (OSError, EnvironmentError), e:
        gdialog.Prompt(_('Tool launch failure'),
                       _('%s : %s') % (cmd, str(e)), None).run()

def filemerge(ui, fname, patchedfname):
    'Launch the preferred visual diff tool for two text files'
    detectedtools = hglib.difftools(ui)
    if not detectedtools:
        gdialog.Prompt(_('No diff tool found'),
                       _('No visual diff tools were detected'), None).run()
        return None
    preferred = besttool(ui, detectedtools)
    diffcmd, diffopts, mergeopts = detectedtools[preferred]
    replace = dict(parent=fname, parent1=fname,
                   plabel1=fname + _('[working copy]'),
                   child=patchedfname, clabel=_('[original]'))
    launchtool(diffcmd, diffopts, replace, True)


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

    try:
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
    except (error.LookupError, error.RepoError):
        gdialog.Prompt(_('Unable to find changeset'),
                       _('You likely need to refresh this application'),
                       None).run()
        return None

    lpats = [util.localpath(f) for f in pats]
    m = match.match(repo.root, repo.root, lpats)
    n2 = ctx2.node()
    mod_a, add_a, rem_a = map(set, repo.status(ctx1a.node(), n2, m)[:3])
    if ctx1b:
        mod_b, add_b, rem_b = map(set, repo.status(ctx1b.node(), n2, m)[:3])
        cpy = copies.copies(repo, ctx1a, ctx1b, ctx1a.ancestor(ctx1b))[0]
    else:
        cpy = copies.copies(repo, ctx1a, ctx2, repo[-1])[0]
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

    if len(toollist) > 1 or cpy:
        usewin = True
    else:
        preferred = toollist.pop()
        dirdiff = repo.ui.configbool('merge-tools', preferred + '.dirdiff')
        dir3diff = repo.ui.configbool('merge-tools', preferred + '.dir3diff')
        usewin = repo.ui.configbool('merge-tools', preferred + '.usewin')
        if not usewin and len(MAR) > 1:
            if ctx1b is not None:
                usewin = not dir3diff
            else:
                usewin = not dirdiff
    if usewin:
        # Multiple required tools, or tool does not support directory diffs
        sa = [mod_a, add_a, rem_a]
        sb = [mod_b, add_b, rem_b]
        dlg = FileSelectionDialog(repo, pats, ctx1a, sa, ctx1b, sb, ctx2, cpy)
        return dlg

    # We can directly use the selected tool, without a visual diff window
    diffcmd, diffopts, mergeopts = detectedtools[preferred]

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
        label1a = '@%d' % ctx1a.rev()
        if do3way:
            files = mod_b | rem_b | ((mod_a | add_a) - add_b)
            dir1b = snapshot(repo, files, ctx1b, tmproot)[0]
            label1b = '@%d' % ctx1b.rev()
            # snapshot for ancestor revision
            ctxa = ctx1a.ancestor(ctx1b)
            if ctxa == ctx1a:
                dira = dir1a
            elif ctxa == ctx1b:
                dira = dir1b
            else:
                dira = snapshot(repo, MAR, ctxa, tmproot)[0]
            labela = '@%d' % ctxa.rev()
        else:
            dir1b, dira = None, None
            label1b, labela = '', ''

        if ctx2.rev() is not None:
            # If ctx2 is not the working copy, create a snapshot for it
            dir2 = snapshot(repo, MA, ctx2, tmproot)[0]
            label2 = '@%d' % ctx2.rev()
        elif len(MAR) == 1:
            # This lets the diff tool open the changed file directly
            label2 = ''
            dir2 = repo.root
        else:
            # Create a snapshot, record mtime to detect mods made by
            # diff tool
            dir2, fns_and_mtime = snapshot(repo, MA, ctx2, tmproot)
            label2 = 'working files'

        def getfile(fname, dir, label):
            file = os.path.join(tmproot, dir, fname)
            if os.path.isfile(file):
                return fname+label, file
            nullfile = os.path.join(tmproot, 'empty')
            fp = open(nullfile, 'w')
            fp.close()
            return _nonexistant+label, nullfile

        # If only one change, diff the files instead of the directories
        # Handle bogus modifies correctly by checking if the files exist
        if len(MAR) == 1:
            lfile = util.localpath(MAR.pop())
            label1a, dir1a = getfile(lfile, dir1a, label1a)
            if do3way:
                label1b, dir1b = getfile(lfile, dir1b, label1b)
                labela, dira = getfile(lfile, dira, labela)
            label2, dir2 = getfile(lfile, dir2, label2)
        if do3way:
            label1a += '[local]'
            label1b += '[other]'
            labela += '[ancestor]'
            label2 += '[merged]'

        # Function to quote file/dir names in the argument string
        replace = dict(parent=dir1a, parent1=dir1a, parent2=dir1b,
                       plabel1=label1a, plabel2=label1b,
                       ancestor=dira, alabel=labela,
                       clabel=label2, child=dir2)
        launchtool(diffcmd, diffopts, replace, True)

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
    def __init__(self, repo, pats, ctx1a, sa, ctx1b, sb, ctx2, cpy):
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

        self.set_default_size(400, 250)
        self.set_has_separator(False)

        if ctx1b:
            ctxa = ctx1a.ancestor(ctx1b)
        else:
            ctxa = ctx1a
        self.ctxs = (ctx1a, ctx1b, ctxa, ctx2)
        self.copies = cpy
        self.ui = repo.ui

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

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)
        mod = gtklib.get_thg_modifier()
        key, modifier = gtk.accelerator_parse(mod+'d')
        treeview.add_accelerator('thg-diff', accelgroup, key,
                        modifier, gtk.ACCEL_VISIBLE)
        treeview.connect('thg-diff', self.rowactivated)

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

        model = gtk.ListStore(str, str)
        treeview.set_model(model)

        tools = hglib.difftools(repo.ui)
        preferred = besttool(repo.ui, tools)
        self.diffpath, self.diffopts, self.mergeopts = tools[preferred]

        hbox = gtk.HBox()
        self.vbox.pack_start(hbox, False, False, 2)

        if ctx2.rev() is None:
            pass
            # Do not offer directory diffs when the working directory
            # is being referenced directly
        elif ctx1b:
            self.p1button = gtk.Button(_('Dir diff to p1'))
            self.p1button.connect('pressed', self.p1dirdiff)
            self.p2button = gtk.Button(_('Dir diff to p2'))
            self.p2button.connect('pressed', self.p2dirdiff)
            self.p3button = gtk.Button(_('3-way dir diff'))
            self.p3button.connect('pressed', self.threewaydirdiff)
            hbox.pack_end(self.p3button, False, False)
            hbox.pack_end(self.p2button, False, False)
            hbox.pack_end(self.p1button, False, False)
        else:
            self.dbutton = gtk.Button(_('Directory diff'))
            self.dbutton.connect('pressed', self.p1dirdiff)
            hbox.pack_end(self.dbutton, False, False)

        self.update_diff_buttons(preferred)

        if len(tools) > 1:
            combo = gtk.combo_box_new_text()
            for i, name in enumerate(tools.iterkeys()):
                combo.append_text(name)
                if name == preferred:
                    defrow = i
            combo.set_active(defrow)
            combo.connect('changed', self.toolselect, tools)
            hbox.pack_start(combo, False, False, 2)

            patterns = repo.ui.configitems('diff-patterns')
            patterns = [(p, t) for p,t in patterns if t in tools]
            filesel = treeview.get_selection()
            filesel.connect('changed', self.fileselect, repo, combo, tools,
                            patterns, preferred)

        gobject.idle_add(self.fillmodel, repo, model, sa, sb)

    def fillmodel(self, repo, model, sa, sb):
        ctx1a, ctx1b, ctxa, ctx2 = self.ctxs
        mod_a, add_a, rem_a = sa
        mod_b, add_b, rem_b = sb
        sources = set(self.copies.values())

        MA = mod_a | add_a | mod_b | add_b
        MAR = MA | rem_a | rem_b | sources

        tmproot = tempfile.mkdtemp(prefix='visualdiff.')
        self.tmproot = tmproot

        # Always make a copy of node1a (and node1b, if applicable)
        files = sources | mod_a | rem_a | ((mod_b | add_b) - add_a)
        dir1a = snapshot(repo, files, ctx1a, tmproot)[0]
        rev1a = '@%d' % ctx1a.rev()
        if ctx1b:
            files = sources | mod_b | rem_b | ((mod_a | add_a) - add_b)
            dir1b = snapshot(repo, files, ctx1b, tmproot)[0]
            rev1b = '@%d' % ctx1b.rev()
            if ctxa == ctx1a:
                dira = dir1a
            elif ctxa == ctx1b:
                dira = dir1b
            else:
                # snapshot for ancestor revision
                dira = snapshot(repo, MAR, ctxa, tmproot)[0]
            reva = '@%d' % ctxa.rev()
        else:
            dir1b, dira = None, None
            rev1b, reva = '', ''

        # If ctx2 is the working copy, use it directly
        if ctx2.rev() is None:
            dir2 = repo.root
            rev2 = ''
        else:
            dir2 = snapshot(repo, MA, ctx2, tmproot)[0]
            rev2 = '@%d' % ctx2.rev()

        self.dirs = (dir1a, dir1b, dira, dir2)
        self.revs = (rev1a, rev1b, reva, rev2)

        def get_status(file, mod, add, rem):
            if file in mod:
                return 'M'
            if file in add:
                return 'A'
            if file in rem:
                return 'R'
            return ' '

        for f in mod_a | add_a | rem_a:
            model.append([get_status(f, mod_a, add_a, rem_a), hglib.toutf(f)])

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
            self.update_diff_buttons(sel)

    def update_diff_buttons(self, tool):
        if hasattr(self, 'p1button'):
            d2 = self.ui.configbool('merge-tools', tool + '.dirdiff')
            d3 = self.ui.configbool('merge-tools', tool + '.dir3diff')
            self.p1button.set_sensitive(d2)
            self.p2button.set_sensitive(d2)
            self.p3button.set_sensitive(d3)
        elif hasattr(self, 'dbutton'):
            d2 = self.ui.configbool('merge-tools', tool + '.dirdiff')
            self.dbutton.set_sensitive(d2)

    def fileselect(self, selection, repo, combo, tools, patterns, preferred):
        'user selected a file, pick an appropriate tool from combo'
        model, path = selection.get_selected()
        if not path:
            return
        row = model[path]
        fname = row[-1]
        for pat, tool in patterns:
            mf = match.match(repo.root, '', [pat])
            if mf(fname):
                selected = tool
                break
        else:
            selected = preferred
        for i, name in enumerate(tools.iterkeys()):
            if name == selected:
                combo.set_active(i)

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

    def rowactivated(self, tree, *args):
        selection = tree.get_selection()
        if selection.count_selected_rows() != 1:
            return False
        model, paths = selection.get_selected_rows()
        self.launch(*model[paths[0]])

    def launch(self, st, fname):
        fname = hglib.fromutf(fname)
        source = self.copies.get(fname, None)
        dir1a, dir1b, dira, dir2 = self.dirs
        rev1a, rev1b, reva, rev2 = self.revs
        ctx1a, ctx1b, ctxa, ctx2 = self.ctxs

        def getfile(ctx, dir, fname, source):
            m = ctx.manifest()
            if fname in m:
                path = os.path.join(dir, util.localpath(fname))
                return fname, path
            elif source and source in m:
                path = os.path.join(dir, util.localpath(source))
                return source, path
            else:
                nullfile = os.path.join(self.tmproot, 'empty')
                fp = open(nullfile, 'w')
                fp.close()
                return _nonexistant, nullfile

        local, file1a = getfile(ctx1a, dir1a, fname, source)
        if ctx1b:
            other, file1b = getfile(ctx1b, dir1b, fname, source)
            ancestor, filea = getfile(ctxa, dira, fname, source)
        else:
            other, ancestor = fname, fname
            file1b, filea = None, None
        fname, file2 = getfile(ctx2, dir2, fname, None)

        label1a = local+rev1a
        label1b = other+rev1b
        labela = ancestor+reva
        label2 = fname+rev2
        if ctx1b:
            label1a += '[local]'
            label1b += '[other]'
            labela += '[ancestor]'
            label2 += '[merged]'

        # Function to quote file/dir names in the argument string
        replace = dict(parent=file1a, parent1=file1a, plabel1=label1a,
                       parent2=file1b, plabel2=label1b,
                       ancestor=filea, alabel=labela,
                       clabel=label2, child=file2)
        args = ctx1b and self.mergeopts or self.diffopts
        launchtool(self.diffpath, args, replace, False)

    def p1dirdiff(self, button):
        dir1a, dir1b, dira, dir2 = self.dirs
        rev1a, rev1b, reva, rev2 = self.revs

        replace = dict(parent=dir1a, parent1=dir1a, plabel1=rev1a,
                       parent2='', plabel2='', ancestor='', alabel='',
                       clabel=rev2, child=dir2)
        launchtool(self.diffpath, self.diffopts, replace, False)

    def p2dirdiff(self, button):
        dir1a, dir1b, dira, dir2 = self.dirs
        rev1a, rev1b, reva, rev2 = self.revs

        replace = dict(parent=dir1b, parent1=dir1b, plabel1=rev1b,
                       parent2='', plabel2='', ancestor='', alabel='',
                       clabel=rev2, child=dir2)
        launchtool(self.diffpath, self.diffopts, replace, False)

    def threewaydirdiff(self, button):
        dir1a, dir1b, dira, dir2 = self.dirs
        rev1a, rev1b, reva, rev2 = self.revs

        replace = dict(parent=dir1a, parent1=dir1a, plabel1=rev1a,
                       parent2=dir1b, plabel2=rev1b,
                       ancestor=dira, alabel=reva,
                       clabel=dir2, child=rev2)
        launchtool(self.diffpath, self.mergeopts, replace, False)


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

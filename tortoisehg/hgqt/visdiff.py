# visdiff.py - launch external visual diff tools
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import subprocess
import stat
import shutil
import threading
import tempfile
import re

from mercurial import hg, cmdutil, util, error, match, copies

from tortoisehg.hgqt.i18n import _
from tortoisehg.util import hglib, paths
from tortoisehg.hgqt import qtlib

from PyQt4 import QtCore
from PyQt4 import QtGui

try:
    import win32con
    openflags = win32con.CREATE_NO_WINDOW
except ImportError:
    openflags = 0

# Match parent2 first, so 'parent1?' will match both parent1 and parent
_regex = '\$(parent2|parent1?|child|plabel1|plabel2|clabel|repo|phash1|phash2|chash)'

_nonexistant = _('[non-existant]')

def snapshot(repo, files, ctx):
    '''snapshot files as of some revision'''
    dirname = os.path.basename(repo.root) or 'root'
    if ctx.rev() is not None:
        dirname = '%s.%s' % (dirname, str(ctx))
    base = os.path.join(qtlib.gettempdir(), dirname)
    fns_and_mtime = []
    if not os.path.exists(base):
        os.mkdir(base)
    for fn in files:
        wfn = util.pconvert(fn)
        if not wfn in ctx:
            # File doesn't exist; could be a bogus modify
            continue
        dest = os.path.join(base, wfn)
        if os.path.exists(dest):
            # File has already been snapshot
            continue
        destdir = os.path.dirname(dest)
        if not os.path.isdir(destdir):
            os.makedirs(destdir)
        data = repo.wwritedata(wfn, ctx[wfn].data())
        f = open(dest, 'wb')
        f.write(data)
        f.close()
        if ctx.rev() is None:
            fns_and_mtime.append((dest, repo.wjoin(fn), os.path.getmtime(dest)))
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
        QtGui.QMessageBox.warning(None,
                _('Tool launch failure'),
                _('%s : %s') % (cmd, str(e)))

def filemerge(ui, fname, patchedfname):
    'Launch the preferred visual diff tool for two text files'
    detectedtools = hglib.difftools(ui)
    if not detectedtools:
        QtGui.QMessageBox.warning(None,
                _('No diff tool found'),
                _('No visual diff tools were detected'))
        return None
    preferred = besttool(ui, detectedtools)
    diffcmd, diffopts, mergeopts = detectedtools[preferred]
    replace = dict(parent=fname, parent1=fname,
                   plabel1=fname + _('[working copy]'),
                   repo='', phash1='', phash2='', chash='',
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
        QtGui.QMessageBox.warning(None,
                       _('Unable to find changeset'),
                       _('You likely need to refresh this application'))
        return None

    pats = cmdutil.expandpats(pats)
    m = match.match(repo.root, '', pats, None, None, 'relpath')
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
        QtGui.QMessageBox.information(None,
                _('No file changes'),
                _('There are no file changes to view'))
        return None

    detectedtools = hglib.difftools(repo.ui)
    if not detectedtools:
        QtGui.QMessageBox.warning(None,
                _('No diff tool found'),
                _('No visual diff tools were detected'))
        return None

    preferred = besttool(repo.ui, detectedtools)

    # Build tool list based on diff-patterns matches
    toollist = set()
    patterns = repo.ui.configitems('diff-patterns')
    patterns = [(p, t) for p,t in patterns if t in detectedtools]
    for path in MAR:
        for pat, tool in patterns:
            mf = match.match(repo.root, '', [pat])
            if mf(path):
                toollist.add(tool)
                break
        else:
            toollist.add(preferred)

    cto = cpy.keys()
    cfrom = cpy.values()
    for path in MAR:
        if path in cto or path in cfrom:
            hascopies = True
            break
    else:
        hascopies = False
    force = repo.ui.configbool('tortoisehg', 'forcevdiffwin')
    if len(toollist) > 1 or hascopies or force:
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
    do3way = False
    if ctx1b:
        if mergeopts:
            do3way = True
            args = mergeopts
        else:
            args = diffopts
            if str(ctx1b.rev()) in revs:
                ctx1a = ctx1b
    else:
        args = diffopts

    def dodiff():
        fns_and_mtime = []

        # Always make a copy of ctx1a (and ctx1b, if applicable)
        files = mod_a | rem_a | ((mod_b | add_b) - add_a)
        dir1a = snapshot(repo, files, ctx1a)[0]
        label1a = '@%d' % ctx1a.rev()
        if do3way:
            files = mod_b | rem_b | ((mod_a | add_a) - add_b)
            dir1b = snapshot(repo, files, ctx1b)[0]
            label1b = '@%d' % ctx1b.rev()
        else:
            dir1b =  None
            label1b = ''

        if ctx2.rev() is not None:
            # If ctx2 is not the working copy, create a snapshot for it
            dir2 = snapshot(repo, MA, ctx2)[0]
            label2 = '@%d' % ctx2.rev()
        elif len(MAR) == 1:
            # This lets the diff tool open the changed file directly
            label2 = ''
            dir2 = repo.root
        else:
            # Create a snapshot, record mtime to detect mods made by
            # diff tool
            dir2, fns_and_mtime = snapshot(repo, MA, ctx2)
            label2 = 'working files'

        def getfile(fname, dir, label):
            file = os.path.join(qtlib.gettempdir(), dir, fname)
            if os.path.isfile(file):
                return fname+label, file
            nullfile = os.path.join(qtlib.gettempdir(), 'empty')
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
            label2, dir2 = getfile(lfile, dir2, label2)
        if do3way:
            label1a += '[local]'
            label1b += '[other]'
            label2 += '[merged]'

        replace = dict(parent=dir1a, parent1=dir1a, parent2=dir1b,
                       plabel1=label1a, plabel2=label1b,
                       phash1=str(ctx1a), phash2=str(ctx1b),
                       repo=hglib.get_reponame(repo),
                       clabel=label2, child=dir2, chash=str(ctx2))
        launchtool(diffcmd, args, replace, True)

        # detect if changes were made to mirrored working files
        for copy_fn, working_fn, mtime in fns_and_mtime:
            if os.path.getmtime(copy_fn) != mtime:
                ui.debug('file changed while diffing. '
                         'Overwriting: %s (src: %s)\n' % (working_fn, copy_fn))
                util.copyfile(copy_fn, working_fn)

    def dodiffwrapper():
        try:
            dodiff()
        finally:
            # cleanup happens atexit
            ui.note(_('cleaning up temp directory\n'))

    if opts.get('mainapp'):
        dodiffwrapper()
    else:
        # We are not the main application, so this must be done in a
        # background thread
        thread = threading.Thread(target=dodiffwrapper, name='visualdiff')
        thread.setDaemon(True)
        thread.start()

class FileSelectionDialog(QtGui.QDialog):
    'Dialog for selecting visual diff candidates'
    def __init__(self, repo, pats, ctx1a, sa, ctx1b, sb, ctx2, cpy):
        'Initialize the Dialog'
        QtGui.QDialog.__init__(self)
        self.setWindowTitle(_('Visual Diffs'))
        self.curFile = None

        # TODO: Connect CTRL-D to row activation
        #qtlib.set_tortoise_icon(self, 'menushowchanged.ico')
        #qtlib.set_tortoise_keys(self)

        if ctx2.rev() is None:
            title = _('working changes')
        elif ctx1a == ctx2.parents()[0]:
            title = _('changeset ') + str(ctx2.rev())
        else:
            title = _('revisions %d to %d') % (ctx1a.rev(), ctx2.rev())
        title = _('Visual Diffs - ') + title
        if pats:
            title += _(' filtered')

        self.resize(400, 250)
        self.reponame = hglib.get_reponame(repo)

        self.ctxs = (ctx1a, ctx1b, ctx2)
        self.copies = cpy
        self.ui = repo.ui

        layout = QtGui.QVBoxLayout() 
        self.setLayout(layout)

        lbl = QtGui.QLabel(_('Temporary files are removed when this dialog'
            ' is closed'))
        layout.addWidget(lbl)

        list = QtGui.QListWidget()
        layout.addWidget(list)
        self.list = list
        self.connect(list, QtCore.SIGNAL('itemActivated(QListWidgetItem *)'),
            self.itemActivated)

        tools = hglib.difftools(repo.ui)
        preferred = besttool(repo.ui, tools)
        self.diffpath, self.diffopts, self.mergeopts = tools[preferred]
        self.tools = tools

        if len(tools) > 1:
            hbox = QtGui.QHBoxLayout() 
            combo = QtGui.QComboBox()
            lbl = QtGui.QLabel(_('Select Tool:'))
            lbl.setBuddy(combo)
            hbox.addWidget(lbl)
            hbox.addWidget(combo, 1)
            layout.addLayout(hbox)
            for i, name in enumerate(tools.iterkeys()):
                combo.addItem(name)
                if name == preferred:
                    defrow = i
            combo.setCurrentIndex(defrow)
            patterns = repo.ui.configitems('diff-patterns')
            patterns = [(p, t) for p,t in patterns if t in tools]

            callable = lambda row: self.fileSelect(row, repo, combo,
                                                   patterns, preferred)
            self.connect(list, QtCore.SIGNAL('currentRowChanged(int)'),
                         callable)
            self.connect(combo, QtCore.SIGNAL('currentIndexChanged(QString)'),
                         self.toolSelect)

        BB = QtGui.QDialogButtonBox
        bb = BB()
        layout.addWidget(bb)

        if ctx2.rev() is None:
            pass
            # Do not offer directory diffs when the working directory
            # is being referenced directly
        elif ctx1b:
            self.p1button = bb.addButton(_('Dir diff to p1'), BB.ActionRole)
            self.p1button.pressed.connect(self.p1dirdiff)
            self.p2button = bb.addButton(_('Dir diff to p2'), BB.ActionRole)
            self.p2button.pressed.connect(self.p2dirdiff)
            self.p3button = bb.addButton(_('3-way dir diff'), BB.ActionRole)
            self.p3button.pressed.connect(self.threewaydirdiff)
        else:
            self.dbutton = bb.addButton(_('Directory diff'), BB.ActionRole)
            self.dbutton.pressed.connect(self.p1dirdiff)

        self.updateDiffButtons(preferred)

        callable = lambda: self.fillmodel(repo, sa, sb)
        QtCore.QTimer.singleShot(0, callable)

    def fillmodel(self, repo, sa, sb):
        ctx1a, ctx1b, ctx2 = self.ctxs
        mod_a, add_a, rem_a = sa
        mod_b, add_b, rem_b = sb
        sources = set(self.copies.values())

        MA = mod_a | add_a | mod_b | add_b
        MAR = MA | rem_a | rem_b | sources

        # Always make a copy of node1a (and node1b, if applicable)
        files = sources | mod_a | rem_a | ((mod_b | add_b) - add_a)
        dir1a = snapshot(repo, files, ctx1a)[0]
        rev1a = '@%d' % ctx1a.rev()
        if ctx1b:
            files = sources | mod_b | rem_b | ((mod_a | add_a) - add_b)
            dir1b = snapshot(repo, files, ctx1b)[0]
            rev1b = '@%d' % ctx1b.rev()
        else:
            dir1b = None
            rev1b = ''

        # If ctx2 is the working copy, use it directly
        if ctx2.rev() is None:
            dir2 = repo.root
            rev2 = ''
        else:
            dir2 = snapshot(repo, MA, ctx2)[0]
            rev2 = '@%d' % ctx2.rev()

        self.dirs = (dir1a, dir1b, dir2)
        self.revs = (rev1a, rev1b, rev2)

        def get_status(file, mod, add, rem):
            if file in mod:
                return 'M'
            if file in add:
                return 'A'
            if file in rem:
                return 'R'
            return ' '

        for f in sorted(mod_a | add_a | rem_a):
            status = get_status(f, mod_a, add_a, rem_a)
            row = QtCore.QString('%s %s' % (status, hglib.tounicode(f)))
            self.list.addItem(row)

    def toolSelect(self, tool):
        'user selected a tool from the tool combo'
        tool = hglib.fromunicode(tool)
        assert tool in self.tools
        self.diffpath, self.diffopts, self.mergeopts = self.tools[tool]
        self.updateDiffButtons(tool)

    def updateDiffButtons(self, tool):
        if hasattr(self, 'p1button'):
            d2 = self.ui.configbool('merge-tools', tool + '.dirdiff')
            d3 = self.ui.configbool('merge-tools', tool + '.dir3diff')
            self.p1button.setEnabled(d2)
            self.p2button.setEnabled(d2)
            self.p3button.setEnabled(d3)
        elif hasattr(self, 'dbutton'):
            d2 = self.ui.configbool('merge-tools', tool + '.dirdiff')
            self.dbutton.setEnabled(d2)

    def fileSelect(self, row, repo, combo, patterns, preferred):
        'user selected a file, pick an appropriate tool from combo'
        fname = self.list.item(row).text()[2:]
        fname = hglib.fromunicode(fname)
        if self.curFile == fname:
            return
        self.curFile = fname
        for pat, tool in patterns:
            mf = match.match(repo.root, '', [pat])
            if mf(fname):
                selected = tool
                break
        else:
            selected = preferred
        for i, name in enumerate(self.tools.iterkeys()):
            if name == selected:
                combo.setCurrentIndex(i)

    def itemActivated(self, item):
        'A QListWidgetItem has been activated'
        self.launch(item.text()[2:])

    def launch(self, fname):
        fname = hglib.fromunicode(fname)
        source = self.copies.get(fname, None)
        dir1a, dir1b, dir2 = self.dirs
        rev1a, rev1b, rev2 = self.revs
        ctx1a, ctx1b, ctx2 = self.ctxs

        def getfile(ctx, dir, fname, source):
            m = ctx.manifest()
            if fname in m:
                path = os.path.join(dir, util.localpath(fname))
                return fname, path
            elif source and source in m:
                path = os.path.join(dir, util.localpath(source))
                return source, path
            else:
                nullfile = os.path.join(qtlib.gettempdir(), 'empty')
                fp = open(nullfile, 'w')
                fp.close()
                return _nonexistant, nullfile

        local, file1a = getfile(ctx1a, dir1a, fname, source)
        if ctx1b:
            other, file1b = getfile(ctx1b, dir1b, fname, source)
        else:
            other = fname, fname
            file1b = None
        fname, file2 = getfile(ctx2, dir2, fname, None)

        label1a = local+rev1a
        label1b = other+rev1b
        label2 = fname+rev2
        if ctx1b:
            label1a += '[local]'
            label1b += '[other]'
            label2 += '[merged]'

        # Function to quote file/dir names in the argument string
        replace = dict(parent=file1a, parent1=file1a, plabel1=label1a,
                       parent2=file1b, plabel2=label1b,
                       repo=self.reponame,
                       phash1=str(ctx1a), phash2=str(ctx1b), chash=str(ctx2),
                       clabel=label2, child=file2)
        args = ctx1b and self.mergeopts or self.diffopts
        launchtool(self.diffpath, args, replace, False)

    def p1dirdiff(self, button):
        dir1a, dir1b, dir2 = self.dirs
        rev1a, rev1b, rev2 = self.revs
        ctx1a, ctx1b, ctx2 = self.ctxs

        replace = dict(parent=dir1a, parent1=dir1a, plabel1=rev1a,
                       repo=self.reponame,
                       phash1=str(ctx1a), phash2=str(ctx1b), chash=str(ctx2),
                       parent2='', plabel2='', clabel=rev2, child=dir2)
        launchtool(self.diffpath, self.diffopts, replace, False)

    def p2dirdiff(self, button):
        dir1a, dir1b, dir2 = self.dirs
        rev1a, rev1b, rev2 = self.revs
        ctx1a, ctx1b, ctx2 = self.ctxs

        replace = dict(parent=dir1b, parent1=dir1b, plabel1=rev1b,
                       repo=self.reponame,
                       phash1=str(ctx1a), phash2=str(ctx1b), chash=str(ctx2),
                       parent2='', plabel2='', clabel=rev2, child=dir2)
        launchtool(self.diffpath, self.diffopts, replace, False)

    def threewaydirdiff(self, button):
        dir1a, dir1b, dir2 = self.dirs
        rev1a, rev1b, rev2 = self.revs
        ctx1a, ctx1b, ctx2 = self.ctxs

        replace = dict(parent=dir1a, parent1=dir1a, plabel1=rev1a,
                       repo=self.reponame,
                       phash1=str(ctx1a), phash2=str(ctx1b), chash=str(ctx2),
                       parent2=dir1b, plabel2=rev1b, clabel=dir2, child=rev2)
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

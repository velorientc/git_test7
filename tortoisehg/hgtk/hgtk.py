# hgtk.py - front-end script for TortoiseHg dialogs
#
# Copyright 2008 Steve Borho <steve@borho.org>
# Copyright 2008 TK Soh <teekaysoh@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

shortlicense = '''
Copyright (C) 2009 Steve Borho <steve@borho.org>.
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
'''

import os
import pdb
import sys
import traceback
import gtk
import gobject

import mercurial.ui as _ui
from mercurial import hg, util, fancyopts, cmdutil, extensions

from tortoisehg.util.i18n import agettext as _
from tortoisehg.util import hglib, paths, shlib
from tortoisehg.util import version as thgversion
try:
    from tortoisehg.util.config import nofork as config_nofork
except ImportError:
    config_nofork = None

nonrepo_commands = '''userconfig clone debugcomplete init about help
version thgstatus serve'''

# Add TortoiseHg signals, hooked to key accelerators in gtklib
for sig in ('copy-clipboard', 'thg-diff', 'thg-parent', 'thg-rename',
        'thg-revision'):
    gobject.signal_new(sig, gtk.TreeView,
        gobject.SIGNAL_ACTION, gobject.TYPE_NONE, ())
for sig in ('thg-exit', 'thg-close', 'thg-refresh', 'thg-accept', 'thg-reflow'):
    gobject.signal_new(sig, gtk.Window,
            gobject.SIGNAL_ACTION, gobject.TYPE_NONE, ())
for sig in ('thg-close', 'thg-new'):
    gobject.signal_new(sig, gtk.Notebook,
        gobject.SIGNAL_ACTION, gobject.TYPE_NONE, ())

gtkmainalive = False
def dispatch(args):
    "run the command specified in args"
    try:
        u = _ui.ui()
        if '--traceback' in args:
            u.setconfig('ui', 'traceback', 'on')
        if '--debugger' in args:
            pdb.set_trace()
        return _runcatch(u, args)
    except SystemExit:
        pass
    except KeyboardInterrupt:
        print _('\nCaught keyboard interrupt, aborting.\n')
    except:
        from tortoisehg.hgtk.bugreport import run
        if '--debugger' in args:
            pdb.post_mortem(sys.exc_info()[2])
        error = traceback.format_exc()
        opts = {}
        opts['cmd'] = ' '.join(sys.argv[1:])
        opts['error'] = error
        opts['nofork'] = True
        if gtkmainalive:
            dlg = run(u, **opts)
            dlg.display()
            dlg.show_all()
        else:
            gtkrun(run, u, **opts)

def portable_fork(ui, opts):
    if 'THG_HGTK_SPAWN' in os.environ or (
            not opts.get('fork') and (
                opts.get('nofork') or opts.get('repository'))):
        return
    elif ui.configbool('tortoisehg', 'hgtkfork', None) is not None:
        if not ui.configbool('tortoisehg', 'hgtkfork'):
            return
    elif config_nofork:
        return
    # Spawn background process and exit
    if hasattr(sys, "frozen"):
        args = sys.argv
    else:
        args = [sys.executable] + sys.argv
    if os.name == 'nt':
        args = ['"%s"' % arg for arg in args]
    env = os.environ.copy()
    env['THG_HGTK_SPAWN'] = '1'
    os.spawnve(os.P_NOWAIT, sys.executable, args, env)
    sys.exit(0)

def get_list_from_file(filename):
    try:
        if filename == '-':
            lines = [ x.replace("\n", "") for x in sys.stdin.readlines() ]
        else:
            fd = open(filename, "r")
            lines = [ x.replace("\n", "") for x in fd.readlines() ]
            fd.close()
            os.unlink(filename)
    except IOError, e:
        sys.stderr.write(_('can not read file "%s". Ignored.\n') % filename)
        return []

    # Convert absolute file paths to repo/cwd canonical
    cwd = os.getcwd()
    root = paths.find_root(cwd)
    if not root:
        return lines
    if cwd == root:
        cwd_rel = ''
    else:
        cwd_rel = cwd[len(root+os.sep):] + os.sep
    files = []
    for f in lines:
        try:
            cpath = util.canonpath(root, cwd, f)
            # canonpath will abort on .hg/ paths
        except util.Abort:
            continue
        if cpath.startswith(cwd_rel):
            cpath = cpath[len(cwd_rel):]
            files.append(cpath)
        else:
            files.append(f)
    return files

def _parse(ui, args):
    options = {}
    cmdoptions = {}

    try:
        args = fancyopts.fancyopts(args, globalopts, options)
    except fancyopts.getopt.GetoptError, inst:
        raise hglib.ParseError(None, inst)

    if args:
        alias, args = args[0], args[1:]
        aliases, i = cmdutil.findcmd(alias, table, ui.config("ui", "strict"))
        for a in aliases:
            if a.startswith(alias):
                alias = a
                break
        cmd = aliases[0]
        c = list(i[1])
    else:
        alias = None
        cmd = None
        c = []

    # combine global options into local
    for o in globalopts:
        c.append((o[0], o[1], options[o[1]], o[3]))

    try:
        args = fancyopts.fancyopts(args, c, cmdoptions)
    except fancyopts.getopt.GetoptError, inst:
        raise hglib.ParseError(cmd, inst)

    # separate global options back out
    for o in globalopts:
        n = o[1]
        options[n] = cmdoptions[n]
        del cmdoptions[n]

    listfile = options.get('listfile')
    if listfile:
        del options['listfile']
        args += get_list_from_file(listfile)

    return (cmd, cmd and i[0] or None, args, options, cmdoptions, alias)

def _runcatch(ui, args):
    try:
        try:
            return runcommand(ui, args)
        finally:
            ui.flush()
    except hglib.ParseError, inst:
        if inst.args[0]:
            ui.status(_("hgtk %s: %s\n") % (inst.args[0], inst.args[1]))
            help_(ui, inst.args[0])
        else:
            ui.status(_("hgtk: %s\n") % inst.args[1])
            help_(ui, 'shortlist')
    except hglib.AmbiguousCommand, inst:
        ui.status(_("hgtk: command '%s' is ambiguous:\n    %s\n") %
                (inst.args[0], " ".join(inst.args[1])))
    except hglib.UnknownCommand, inst:
        ui.status(_("hgtk: unknown command '%s'\n") % inst.args[0])
        help_(ui, 'shortlist')
    except hglib.RepoError, inst:
        ui.status(_("abort: %s!\n") % inst)

    return -1

def runcommand(ui, args):
    fullargs = args
    cmd, func, args, options, cmdoptions, alias = _parse(ui, args)
    cmdoptions['alias'] = alias
    ui.setconfig("ui", "verbose", str(bool(options["verbose"])))

    if options['help']:
        return help_(ui, cmd)
    elif not cmd:
        return help_(ui, 'shortlist')

    path = options['repository']
    if path:
        if path.startswith('bundle:'):
            s = path[7:].split('+', 1)
            if len(s) == 1:
                path, bundle = os.getcwd(), s[0]
            else:
                path, bundle = s
            cmdoptions['bundle'] = os.path.abspath(bundle)
        path = ui.expandpath(path)
        cmdoptions['repository'] = path
        os.chdir(path)
    if options['fork']:
        cmdoptions['fork'] = True
    if options['nofork']:
        cmdoptions['nofork'] = True
    path = paths.find_root(os.getcwd())
    if path:
        try:
            lui = ui.copy()
            lui.readconfig(os.path.join(path, ".hg", "hgrc"))
        except IOError:
            pass
    else:
        lui = ui

    extensions.loadall(ui)

    if options['quiet']:
        ui.quiet = True

    if cmd not in nonrepo_commands.split() and not path:
        raise hglib.RepoError(_("There is no Mercurial repository here"
                    " (.hg not found)"))

    try:
        return func(ui, *args, **cmdoptions)
    except TypeError, inst:
        # was this an argument error?
        tb = traceback.extract_tb(sys.exc_info()[2])
        if len(tb) != 1: # no
            raise
        raise hglib.ParseError(cmd, _("invalid arguments"))

mainwindow = None
def thgexit(win):
    if hasattr(mainwindow, 'should_live'):
        if mainwindow.should_live(): return
    mainwindow.destroy()

def gtkrun(dlgfunc, ui, *args, **opts):
    portable_fork(ui, opts)
    win = dlgfunc(ui, *args, **opts)
    if not win:
        return
    global mainwindow, gtkmainalive
    mainwindow = win
    if hasattr(win, 'display'):
        win.display()
    win.show_all()
    if 'response' in gobject.signal_list_names(win):
        win.connect('response', gtk.main_quit)
    win.connect('destroy', gtk.main_quit)
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtkmainalive = True
    gtk.main()
    gtkmainalive = False
    gtk.gdk.threads_leave()

def about(ui, *pats, **opts):
    """about TortoiseHg"""
    from tortoisehg.hgtk.about import run
    gtkrun(run, ui, *pats, **opts)

def add(ui, *pats, **opts):
    """add files"""
    from tortoisehg.hgtk.quickop import run
    gtkrun(run, ui, *pats, **opts)

def thgstatus(ui, *pats, **opts):
    """update TortoiseHg status cache"""
    from tortoisehg.util.thgstatus import run
    run(ui, *pats, **opts)

def clone(ui, *pats, **opts):
    """clone tool"""
    from tortoisehg.hgtk.clone import run
    gtkrun(run, ui, *pats, **opts)

def commit(ui, *pats, **opts):
    """commit tool"""
    # move cwd to repo root if repo is merged, so we can show
    # all the changed files
    repo = hg.repository(ui, path=paths.find_root())
    if len(repo.parents()) > 1:
        os.chdir(repo.root)
        pats = []
    from tortoisehg.hgtk.commit import run
    gtkrun(run, ui, *pats, **opts)

def shelve(ui, *pats, **opts):
    """shelve/unshelve tool"""
    from tortoisehg.hgtk.thgshelve import run
    gtkrun(run, ui, *pats, **opts)

def userconfig(ui, *pats, **opts):
    """user configuration editor"""
    from tortoisehg.hgtk.thgconfig import run
    gtkrun(run, ui, *pats, **opts)

def repoconfig(ui, *pats, **opts):
    """repository configuration editor"""
    from tortoisehg.hgtk.thgconfig import run
    gtkrun(run, ui, *pats, **opts)

def rename(ui, *pats, **opts):
    """rename a single file or directory"""
    if not pats or len(pats) > 2:
        from tortoisehg.hgtk import gdialog
        gdialog.Prompt(_('Rename error'),
                       _('rename takes one or two path arguments'), None).run()        
        return 
    from tortoisehg.hgtk.rename import run
    gtkrun(run, ui, *pats, **opts)

def guess(ui, *pats, **opts):
    """guess previous renames or copies"""
    from tortoisehg.hgtk.guess import run
    gtkrun(run, ui, *pats, **opts)

def datamine(ui, *pats, **opts):
    """repository search and annotate tool"""
    from tortoisehg.hgtk.datamine import run
    gtkrun(run, ui, *pats, **opts)

def hgignore(ui, *pats, **opts):
    """ignore filter editor"""
    from tortoisehg.hgtk.hgignore import run
    gtkrun(run, ui, *pats, **opts)

def hginit(ui, *pats, **opts):
    """repository initialization tool"""
    from tortoisehg.hgtk.hginit import run
    gtkrun(run, ui, *pats, **opts)

def log(ui, *pats, **opts):
    """changelog viewer"""
    from tortoisehg.hgtk.history import run
    gtkrun(run, ui, *pats, **opts)

def merge(ui, *pats, **opts):
    """merge tool"""
    from tortoisehg.hgtk.merge import run
    gtkrun(run, ui, *pats, **opts)

def recovery(ui, *pats, **opts):
    """recover, rollback & verify"""
    from tortoisehg.hgtk.recovery import run
    gtkrun(run, ui, *pats, **opts)

def remove(ui, *pats, **opts):
    """file status viewer in remove mode"""
    from tortoisehg.hgtk.quickop import run
    gtkrun(run, ui, *pats, **opts)

def revert(ui, *pats, **opts):
    """file status viewer in revert mode"""
    from tortoisehg.hgtk.quickop import run
    gtkrun(run, ui, *pats, **opts)

def forget(ui, *pats, **opts):
    """file status viewer in forget mode"""
    from tortoisehg.hgtk.quickop import run
    gtkrun(run, ui, *pats, **opts)

def serve(ui, *pats, **opts):
    """web server"""
    from tortoisehg.hgtk.serve import run
    if paths.find_root() == None and not opts['webdir_conf']:
        raise hglib.RepoError(_("There is no Mercurial repository here"
                    " (.hg not found)"))
    gtkrun(run, ui, *pats, **opts)

def status(ui, *pats, **opts):
    """file status & diff viewer"""
    from tortoisehg.hgtk.status import run
    gtkrun(run, ui, *pats, **opts)

def strip(ui, *pats, **opts):
    """strip changesets"""
    from tortoisehg.hgtk.thgstrip import run
    gtkrun(run, ui, *pats, **opts)

def synch(ui, *pats, **opts):
    """repository synchronization tool"""
    from tortoisehg.hgtk.synch import run
    cmd = opts['alias']
    if cmd in ('push', 'outgoing', 'email'):
        opts['pushmode'] = True
    else:
        opts['pushmode'] = False
    gtkrun(run, ui, *pats, **opts)

def update(ui, *pats, **opts):
    """update/checkout tool"""
    from tortoisehg.hgtk.update import run
    gtkrun(run, ui, *pats, **opts)

def vdiff(ui, *pats, **opts):
    """launch configured visual diff tool"""
    from tortoisehg.hgtk.visdiff import run, rawextdiff
    if opts.get('raw'):
        rawextdiff(ui, *pats, **opts)
        return
    gtkrun(run, ui, *pats, **opts)

### help management, adapted from mercurial.commands.help_()
def help_(ui, name=None, with_version=False, alias=None):
    """show help for a command, extension, or list of commands

    With no arguments, print a list of commands and short help.

    Given a command name, print help for that command.

    Given an extension name, print help for that extension, and the
    commands it provides."""
    option_lists = []

    def addglobalopts(aliases):
        if ui.verbose:
            option_lists.append((_("global options:"), globalopts))
            if name == 'shortlist':
                option_lists.append((_('use "hgtk help" for the full list '
                                       'of commands'), ()))
        else:
            if name == 'shortlist':
                msg = _('use "hgtk help" for the full list of commands '
                        'or "hgtk -v" for details')
            elif aliases:
                msg = _('use "hgtk -v help%s" to show aliases and '
                        'global options') % (name and " " + name or "")
            else:
                msg = _('use "hgtk -v help %s" to show global options') % name
            option_lists.append((msg, ()))

    def helpcmd(name):
        if with_version:
            version(ui)
            ui.write('\n')

        try:
            aliases, i = cmdutil.findcmd(name, table, False)
        except hglib.AmbiguousCommand, inst:
            select = lambda c: c.lstrip('^').startswith(inst.args[0])
            helplist(_('list of commands:\n\n'), select)
            return

        # synopsis
        ui.write("%s\n" % i[2])

        # aliases
        if not ui.quiet and len(aliases) > 1:
            ui.write(_("\naliases: %s\n") % ', '.join(aliases[1:]))

        # description
        doc = i[0].__doc__
        if not doc:
            doc = _("(No help text available)")
        if ui.quiet:
            doc = doc.splitlines(0)[0]
        ui.write("\n%s\n" % doc.rstrip())

        if not ui.quiet:
            # options
            if i[1]:
                option_lists.append((_("options:\n"), i[1]))

            addglobalopts(False)

    def helplist(header, select=None):
        h = {}
        cmds = {}
        for c, e in table.items():
            f = c.split("|", 1)[0]
            if select and not select(f):
                continue
            if name == "shortlist" and not f.startswith("^"):
                continue
            f = f.lstrip("^")
            if not ui.debugflag and f.startswith("debug"):
                continue
            doc = e[0].__doc__
            if not doc:
                doc = _("(No help text available)")
            h[f] = doc.splitlines(0)[0].rstrip()
            cmds[f] = c.lstrip("^")

        if not h:
            ui.status(_('no commands defined\n'))
            return

        ui.status(header)
        fns = h.keys()
        fns.sort()
        m = max(map(len, fns))
        for f in fns:
            if ui.verbose:
                commands = cmds[f].replace("|",", ")
                ui.write(" %s:\n      %s\n"%(commands, h[f]))
            else:
                ui.write(' %-*s   %s\n' % (m, f, h[f]))

        if not ui.quiet:
            addglobalopts(True)

    def helptopic(name):
        from mercurial import help
        for names, header, doc in help.helptable:
            if name in names:
                break
        else:
            raise hglib.UnknownCommand(name)

        # description
        if not doc:
            doc = _("(No help text available)")
        if hasattr(doc, '__call__'):
            doc = doc()

        ui.write("%s\n" % header)
        ui.write("%s\n" % doc.rstrip())

    if name and name != 'shortlist':
        i = None
        for f in (helpcmd, helptopic):
            try:
                f(name)
                i = None
                break
            except hglib.UnknownCommand, inst:
                i = inst
        if i:
            raise i

    else:
        # program name
        if ui.verbose or with_version:
            version(ui)
        else:
            ui.status(_("Hgtk - TortoiseHg's GUI tools for Mercurial SCM (Hg)\n"))
        ui.status('\n')

        # list of commands
        if name == "shortlist":
            header = _('basic commands:\n\n')
        else:
            header = _('list of commands:\n\n')

        helplist(header)

    # list all option lists
    opt_output = []
    for title, options in option_lists:
        opt_output.append(("\n%s" % title, None))
        for shortopt, longopt, default, desc in options:
            if "DEPRECATED" in desc and not ui.verbose: continue
            opt_output.append(("%2s%s" % (shortopt and "-%s" % shortopt,
                                          longopt and " --%s" % longopt),
                               "%s%s" % (desc,
                                         default
                                         and _(" (default: %s)") % default
                                         or "")))

    if opt_output:
        opts_len = max([len(line[0]) for line in opt_output if line[1]] or [0])
        for first, second in opt_output:
            if second:
                ui.write(" %-*s  %s\n" % (opts_len, first, second))
            else:
                ui.write("%s\n" % first)

def version(ui, **opts):
    """output version and copyright information"""
    ui.write(_('TortoiseHg Dialogs (version %s), '
               'Mercurial (version %s)\n') %
               (hglib.fromutf(thgversion.version()), hglib.hgversion))
    if not ui.quiet:
        ui.write(shortlicense)

def debugcomplete(ui, cmd='', **opts):
    """output list of possible commands"""
    if opts.get('options'):
        options = []
        otables = [globalopts]
        if cmd:
            aliases, entry = cmdutil.findcmd(cmd, table, False)
            otables.append(entry[1])
        for t in otables:
            for o in t:
                if o[0]:
                    options.append('-%s' % o[0])
                options.append('--%s' % o[1])
        ui.write("%s\n" % "\n".join(options))
        return

    cmdlist = cmdutil.findpossible(cmd, table)
    if ui.verbose:
        cmdlist = [' '.join(c[0]) for c in cmdlist.values()]
    ui.write("%s\n" % "\n".join(sorted(cmdlist)))

def archive(ui, *pats, **opts):
    """create an unversioned archive of a repository revision"""
    from tortoisehg.hgtk.archive import run
    gtkrun(run, ui, *pats, **opts)

globalopts = [
    ('R', 'repository', '',
     _('repository root directory or symbolic path name')),
    ('v', 'verbose', None, _('enable additional output')),
    ('q', 'quiet', None, _('suppress output')),
    ('h', 'help', None, _('display help and exit')),
    ('', 'debugger', None, _('start debugger')),
    ('', 'nofork', None, _('do not fork GUI process')),
    ('', 'fork', None, _('always fork GUI process')),
    ('', 'listfile', '', _('read file list from file')),
]

table = {
    "^about": (about, [], _('hgtk about')),
    "^add": (add, [], _('hgtk add [FILE]...')),
    "^clone": (clone, [],  _('hgtk clone SOURCE [DEST]')),
    "^commit|ci": (commit,
        [('u', 'user', '', _('record user as committer')),
         ('d', 'date', '', _('record datecode as commit date'))],
        _('hgtk commit [OPTIONS] [FILE]...')),
    "^datamine|annotate|blame|grep": (datamine, [], _('hgtk datamine')),
    "^hgignore|ignore|filter": (hgignore, [], _('hgtk hgignore [FILE]')),
    "^init": (hginit, [], _('hgtk init [DEST]')),
    "^log|history": (log,
        [('l', 'limit', '', _('limit number of changes displayed'))],
        _('hgtk log [OPTIONS] [FILE]')),
    "^merge": (merge, 
        [('r', 'rev', '', _('revision to merge with'))],
        _('hgtk merge')),
    "^recovery|rollback|verify": (recovery, [], _('hgtk recovery')),
    "^shelve|unshelve": (shelve, [], _('hgtk shelve')),
    "^synch|pull|push|incoming|outgoing|email": (synch, [], _('hgtk synch')),
    "^status|st|diff": (status,
        [('r', 'rev', [], _('revisions to compare'))],
        _('hgtk status [FILE]...')),
    "^userconfig": (userconfig,
        [('', 'focus', '', _('field to give initial focus'))],
        _('hgtk userconfig')),
    "^repoconfig": (repoconfig,
        [('', 'focus', '', _('field to give initial focus'))],
        _('hgtk repoconfig')),
    "^guess": (guess, [], _('hgtk guess')),
    "^remove|rm": (revert, [], _('hgtk remove [FILE]...')),
    "^rename|mv": (rename, [], _('hgtk rename SOURCE [DEST]')),
    "^revert": (revert, [], _('hgtk revert [FILE]...')),
    "^forget": (forget, [], _('hgtk forget [FILE]...')),
    "^serve":
        (serve,
         [('', 'webdir-conf', '', _('name of the webdir config file'))],
         _('hgtk serve [OPTION]...')),
    "thgstatus": (thgstatus,
        [('',  'delay', None, _('wait until the second ticks over')),
         ('n', 'notify', [], _('notify the shell for paths given')),
         ('',  'remove', None, _('remove the status cache')),
         ('s', 'show', None, _('show the contents of the'
                               ' status cache (no update)')),
         ('',  'all', None, _('udpate all repos in current dir')) ],
        _('hgtk thgstatus [OPTION]')),
    "^update|checkout|co": (update,
        [('r', 'rev', None, _('revision to update'))],
        ('hgtk update')),
    "^vdiff": (vdiff,
        [('c', 'change', '', _('changeset to view in diff tool')),
         ('r', 'rev', [], _('revisions to view in diff tool')),
         ('b', 'bundle', '', _('bundle file to preview')),
         ('', 'raw', None, _('directly use raw extdiff command'))],
            _('launch visual diff tool')),
    "^version": (version,
        [('v', 'verbose', None, _('print license'))],
        _('hgtk version [OPTION]')),
    "debugcomplete": (debugcomplete,
         [('o', 'options', None, _('show the command options'))],
         _('[-o] CMD')),
    "help": (help_, [], _('hgtk help [COMMAND]')),
    "^archive": (archive,
        [('r', 'rev', '', _('revision to update'))],
        ('hgtk archive')),
    "^strip": (strip, [], ('hgtk strip [REV]')),
}

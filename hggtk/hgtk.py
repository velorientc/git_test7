#!/usr/bin/env python
#
# front-end script for TortoiseHg dialogs
#
# Copyright (C) 2008-9 Steve Borho <steve@borho.org>
# Copyright (C) 2008 TK Soh <teekaysoh@gmail.com>

shortlicense = '''
Copyright (C) 2009 Steve Borho <steve@borho.org>.
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
'''

from mercurial.i18n import _
from mercurial import hg, util, fancyopts, commands, cmdutil
import pdb
import mercurial.ui as _ui

try:
    from mercurial.error import RepoError, UnknownCommand, AmbiguousCommand
    from mercurial.error import ParseError
except ImportError:
    from mercurial.repo import RepoError
    from mercurial.cmdutil import UnknownCommand, AmbiguousCommand
    from mercurial.dispatch import ParseError

import os
import sys
import traceback

nonrepo_commands = 'userconfig clone init about help version'

def dispatch(args):
    "run the command specified in args"
    try:
        u = _ui.ui(traceback='--traceback' in args)
    except util.Abort, inst:
        sys.stderr.write(_("abort: %s\n") % inst)
        return -1
    if '--debugger' in args:
        pdb.set_trace()
    try:
        return _runcatch(u, args)
    except:
        if '--debugger' in args:
            pdb.post_mortem(sys.exc_info()[2])
        u.print_exc()
        raise

def get_list_from_file(filename):
    try:
        if filename == '-':
            lines = [ x.replace("\n", "") for x in sys.stdin.readlines() ]
        else:
            fd = open(filename, "r")
            lines = [ x.replace("\n", "") for x in fd.readlines() ]
            fd.close()
            os.unlink(filename)
        return lines
    except IOError, e:
        sys.stderr.write(_('can not read file "%s". Ignored.\n') % filename)
        return []

def _parse(ui, args):
    options = {}
    cmdoptions = {}

    try:
        args = fancyopts.fancyopts(args, globalopts, options)
    except fancyopts.getopt.GetoptError, inst:
        raise ParseError(None, inst)

    if args:
        cmd, args = args[0], args[1:]
        aliases, i = cmdutil.findcmd(cmd, table, ui.config("ui", "strict"))
        cmd = aliases[0]
        c = list(i[1])
    else:
        cmd = None
        c = []

    # combine global options into local
    for o in globalopts:
        c.append((o[0], o[1], options[o[1]], o[3]))

    try:
        args = fancyopts.fancyopts(args, c, cmdoptions)
    except fancyopts.getopt.GetoptError, inst:
        raise ParseError(cmd, inst)

    # separate global options back out
    for o in globalopts:
        n = o[1]
        options[n] = cmdoptions[n]
        del cmdoptions[n]

    listfile = options.get('listfile')
    if listfile:
        del options['listfile']
        args += get_list_from_file(listfile)

    return (cmd, cmd and i[0] or None, args, options, cmdoptions)

def _runcatch(ui, args):
    try:
        try:
            return runcommand(ui, args)
        finally:
            ui.flush()
    except ParseError, inst:
        if inst.args[0]:
            ui.warn(_("hgtk %s: %s\n") % (inst.args[0], inst.args[1]))
            help_(ui, inst.args[0])
        else:
            ui.warn(_("hgtk: %s\n") % inst.args[1])
            help_(ui, 'shortlist')
    except AmbiguousCommand, inst:
        ui.warn(_("hgtk: command '%s' is ambiguous:\n    %s\n") %
                (inst.args[0], " ".join(inst.args[1])))
    except UnknownCommand, inst:
        ui.warn(_("hgtk: unknown command '%s'\n") % inst.args[0])
        help_(ui, 'shortlist')
    except RepoError, inst:
        ui.warn(_("abort: %s!\n") % inst)
    except util.Abort, inst:
        ui.warn(_("abort: %s\n") % inst)
        
    return -1

def runcommand(ui, args):
    fullargs = args
    cmd, func, args, options, cmdoptions = _parse(ui, args)
    ui.updateopts(options["verbose"])

    if options['help']:
        return help_(ui, cmd)
    elif not cmd:
        return help_(ui, 'shortlist')

    import hglib
    path = hglib.rootpath(os.getcwd())
    if path:
        try:
            lui = _ui.ui(parentui=ui)
            lui.readconfig(os.path.join(path, ".hg", "hgrc"))
        except IOError:
            pass
    else:
        lui = ui
    if options['repository']:
        path = lui.expandpath(options['repository'])

    if cmd not in nonrepo_commands.split():
        try:
            repo = hg.repository(ui, path=path)
        except RepoError, inst:
            # try to guess the repo from first of file args
            root = None
            if args:
                path = hglib.rootpath(args[0])
            if path:
                repo = hg.repository(ui, path=path)
            else:
                raise RepoError(_("There is no Mercurial repository here"
                        " (.hg not found)"))
        cmdoptions['root'] = os.path.abspath(path)

    try:
        return func(ui, *args, **cmdoptions)
    except TypeError, inst:
        # was this an argument error?
        tb = traceback.extract_tb(sys.exc_info()[2])
        if len(tb) != 1: # no
            raise
        raise ParseError(cmd, _("invalid arguments"))

def about(ui, **opts):
    """about TortoiseHg"""
    from hggtk.about import run
    run(**opts)

def add(ui, *pats, **opts):
    """add files"""
    from mercurial import dispatch
    dispatch.dispatch(['add'] + list(pats))

def clone(ui, source=None, dest=None, **opts):
    """clone tool"""
    from hggtk.clone import run
    opts['files'] = [os.path.abspath(x) for x in (source, dest) if x]
    run(**opts)

def commit(ui, *pats, **opts):
    """commit tool"""
    from hggtk.commit import run
    opts['files'] = [os.path.abspath(x) for x in pats]
    run(**opts)

def shelve(ui, *pats, **opts):
    """shelve/unshelve tool"""
    from hggtk.thgshelve import run
    opts['files'] = [os.path.abspath(x) for x in pats]
    run(**opts)

def userconfig(ui, **opts):
    """user configuration editor"""
    from hggtk.thgconfig import run
    run(**opts)

def repoconfig(ui, *pats, **opts):
    """repository configuration editor"""
    from hggtk.thgconfig import run
    opts['files'] = opts['root']
    run(**opts)

def rename(ui, *pats, **opts):
    """rename a single file or directory"""
    from hggtk.rename import run
    if not pats or len(pats) > 2:
        raise util.Abort(_('rename takes one or two path arguments'))
    opts['files'] = pats
    opts['detect'] = False
    run(**opts)

def guess(ui, *pats, **opts):
    """guess previous renames or copies"""
    from hggtk.rename import run
    opts['detect'] = True
    run(**opts)

def datamine(ui, *pats, **opts):
    """repository search and annotate tool"""
    from hggtk.datamine import run
    opts['files'] = pats or []
    opts['cwd'] = os.getcwd()
    run(**opts)

def hginit(ui, dest=None, **opts):
    """repository initialization tool"""
    from hggtk.hginit import run
    if dest:
        opts['files'] = [dest]
    run(**opts)

def log(ui, *pats, **opts):
    """changelog viewer"""
    from hggtk.history import run
    opts['files'] = [os.path.abspath(x) for x in pats]
    run(**opts)

def merge(ui, node=None, rev=None, **opts):
    """merge tool """
    from hggtk.merge import run
    run(**opts)

def recovery(ui, *pats, **opts):
    """recover, rollback & verify"""
    from hggtk.recovery import run
    run(**opts)

def serve(ui, **opts):
    """web server"""
    from hggtk.serve import run
    run(**opts)

def status(ui, *pats, **opts):
    """file status viewer

    Also do add, remove and revert.
    """
    from hggtk.status import run
    opts['files'] = [os.path.abspath(x) for x in pats]
    run(**opts)

def synch(ui, **opts):
    """repository synchronization tool"""
    from hggtk.synch import run
    cmd = sys.argv[1] 
    if 'push'.startswith(cmd) or 'outgoing'.startswith(cmd):
        opts['pushmode'] = True
    else:
        opts['pushmode'] = False
    run(**opts)

def update(ui, **opts):
    """update/checkout tool"""
    from hggtk.update import run
    run(**opts)

def vdiff(ui, *pats, **opts):
    """launch configured visual diff tool"""
    from mercurial import dispatch
    vdiff = ui.config('tortoisehg', 'vdiff', 'vdiff')
    if vdiff:
        dispatch.dispatch([vdiff] + list(pats))

### help management, adapted from mercurial.commands.help_()
def help_(ui, name=None, with_version=False):
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
        aliases, i = cmdutil.findcmd(name, table)
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
        v = None
        for i in help.helptable:
            l = i.split('|')
            if name in l:
                v = i
                header = l[-1]
        if not v:
            raise cmdutil.UnknownCommand(name)

        # description
        doc = help.helptable[v]
        if not doc:
            doc = _("(No help text available)")
        if callable(doc):
            doc = doc()

        ui.write("%s\n" % header)
        ui.write("%s\n" % doc.rstrip())

    def helpext(name):
        try:
            mod = extensions.find(name)
        except KeyError:
            raise cmdutil.UnknownCommand(name)

        doc = (mod.__doc__ or _('No help text available')).splitlines(0)
        ui.write(_('%s extension - %s\n') % (name.split('.')[-1], doc[0]))
        for d in doc[1:]:
            ui.write(d, '\n')

        ui.status('\n')

        try:
            ct = mod.cmdtable
        except AttributeError:
            ct = {}

        modcmds = dict.fromkeys([c.split('|', 1)[0] for c in ct])
        helplist(_('list of commands:\n\n'), modcmds.has_key)

    if name and name != 'shortlist':
        i = None
        for f in (helpcmd, helptopic, helpext):
            try:
                f(name)
                i = None
                break
            except cmdutil.UnknownCommand, inst:
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
    import hggtk.shlib
    ui.write(_('TortoiseHg Dialogs (version %s), '
               'Mercurial (version %s)\n') %
               (hggtk.shlib.version(), util.version()))
    if not ui.quiet:
        ui.write(shortlicense)

globalopts = [
    ('R', 'repository', '',
     _('repository root directory or symbolic path name')),
    ('v', 'verbose', None, _('enable additional output')),
    ('h', 'help', None, _('display help and exit')),
    ('l', 'listfile', '', _('read file list from file')),
]

table = {
    "^about": (about, [], _('hgtk about')),
    "^add": (add, [], _('hgtk add [FILE]...')),
    "^clone": (clone, [],  _('hgtk clone SOURCE [DEST]')),
    "^commit|ci": (commit, [], _('hgtk commit [FILE]...')),
    "^datamine|annotate|blame": (datamine, [], _('hgtk datamine')),
    "^init": (hginit, [], _('hgtk init [DEST]')),
    "^log|history": (log,
        [('l', 'limit', '', _('limit number of changes displayed'))],
        _('hgtk log [OPTIONS] [FILE]')),
    "^merge": (merge, [], _('hgtk merge')),
    "^recovery|rollback|verify": (recovery, [], _('hgtk recovery')),
    "^shelve|unshelve": (shelve, [], _('hgtk shelve')),
    "^synch|pull|push|incoming|outgoing|email": (synch, [], _('hgtk synch')),
    "^status|st": (status, [], _('hgtk status [FILE]...')),
    "^userconfig": (userconfig, [], _('hgtk userconfig')),
    "^repoconfig": (repoconfig, [], _('hgtk repoconfig')),
    "^guess": (guess, [], _('hgtk guess')),
    "^rename|mv": (rename, [], _('hgtk rename SOURCE [DEST]')),
    "^serve": 
        (serve,
         [('', 'webdir-conf', '', _('name of the webdir config file'))],
         _('hgtk serve [OPTION]...')),
    "^update|checkout|co": (update, [], _('hgtk update')),
    "^vdiff": (vdiff, [], _('launch visual diff tool')),
    "^version": (version,
        [('v', 'verbose', None, _('print license'))],
        _('hgtk version [OPTION]')),
    "help": (help_, [], _('hgtk help [COMMAND]')),
}

if __name__=='__main__':
    sys.exit(dispatch(sys.argv[1:]))

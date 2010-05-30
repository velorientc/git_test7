# run.py - front-end script for TortoiseHg dialogs
#
# Copyright 2008 Steve Borho <steve@borho.org>
# Copyright 2008 TK Soh <teekaysoh@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

shortlicense = '''
Copyright (C) 2008-2010 Steve Borho <steve@borho.org> and others.
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
'''

import os
import pdb
import sys
import subprocess
import traceback

from PyQt4 import QtCore, QtGui

import mercurial.ui as _ui
from mercurial import hg, util, fancyopts, cmdutil, extensions, error

from tortoisehg.hgqt.i18n import agettext as _
from tortoisehg.util import hglib, paths, shlib
from tortoisehg.util import version as thgversion
from tortoisehg.hgqt import qtlib
try:
    from tortoisehg.util.config import nofork as config_nofork
except ImportError:
    config_nofork = None

try:
    import win32con
    openflags = win32con.CREATE_NO_WINDOW
except ImportError:
    openflags = 0

nonrepo_commands = '''userconfig shellconfig clone debugcomplete init
about help version thgstatus serve log'''

def dispatch(args):
    """run the command specified in args"""
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
        from tortoisehg.hgqt.bugreport import run
        if '--debugger' in args:
            pdb.post_mortem(sys.exc_info()[2])
        error = traceback.format_exc()
        opts = {}
        opts['cmd'] = ' '.join(sys.argv[1:])
        opts['error'] = error
        opts['nofork'] = True
        qtrun(run, u, **opts)

origwdir = os.getcwd()
def portable_fork(ui, opts):
    if 'THG_GUI_SPAWN' in os.environ or (
        not opts.get('fork') and opts.get('nofork')):
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
    os.environ['THG_GUI_SPAWN'] = '1'
    cmdline = subprocess.list2cmdline(args)
    os.chdir(origwdir)
    subprocess.Popen(cmdline,
                     creationflags=openflags,
                     shell=True)
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
        raise error.ParseError(None, inst)

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
        raise error.ParseError(cmd, inst)

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
    except error.ParseError, inst:
        if inst.args[0]:
            ui.status(_("thg %s: %s\n") % (inst.args[0], inst.args[1]))
            help_(ui, inst.args[0])
        else:
            ui.status(_("thg: %s\n") % inst.args[1])
            help_(ui, 'shortlist')
    except error.AmbiguousCommand, inst:
        ui.status(_("thg: command '%s' is ambiguous:\n    %s\n") %
                (inst.args[0], " ".join(inst.args[1])))
    except error.UnknownCommand, inst:
        ui.status(_("thg: unknown command '%s'\n") % inst.args[0])
        help_(ui, 'shortlist')
    except error.RepoError, inst:
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
    if options['nofork'] or options['profile']:
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
        raise error.RepoError(_("There is no Mercurial repository here"
                    " (.hg not found)"))

    cmdoptions['mainapp'] = True
    d = lambda: util.checksignature(func)(ui, *args, **cmdoptions)
    return _runcommand(lui, options, cmd, d)

def _runcommand(ui, options, cmd, cmdfunc):
    def checkargs():
        try:
            return cmdfunc()
        except error.SignatureError:
            raise error.ParseError(cmd, _("invalid arguments"))

    if options['profile']:
        format = ui.config('profiling', 'format', default='text')

        if not format in ['text', 'kcachegrind']:
            ui.warn(_("unrecognized profiling format '%s'"
                        " - Ignored\n") % format)
            format = 'text'

        output = ui.config('profiling', 'output')

        if output:
            path = ui.expandpath(output)
            ostream = open(path, 'wb')
        else:
            ostream = sys.stderr

        try:
            from mercurial import lsprof
        except ImportError:
            raise util.Abort(_(
                'lsprof not available - install from '
                'http://codespeak.net/svn/user/arigo/hack/misc/lsprof/'))
        p = lsprof.Profiler()
        p.enable(subcalls=True)
        try:
            return checkargs()
        finally:
            p.disable()

            if format == 'kcachegrind':
                import lsprofcalltree
                calltree = lsprofcalltree.KCacheGrind(p)
                calltree.output(ostream)
            else:
                # format == 'text'
                stats = lsprof.Stats(p.getstats())
                stats.sort()
                stats.pprint(top=10, file=ostream, climit=5)

            if output:
                ostream.close()
    else:
        return checkargs()

mainapp = None
def qtrun(dlgfunc, ui, *args, **opts):
    portable_fork(ui, opts)

    global mainapp
    if mainapp:
        dlg = dlgfunc(ui, *args, **opts)
        if dlg:
            dlg.show()
        return

    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)

    mainapp = QtGui.QApplication(sys.argv)
    # default org is used by QSettings
    mainapp.setApplicationName('TortoiseHgQt')
    mainapp.setOrganizationName('TortoiseHg')
    mainapp.setOrganizationDomain('tortoisehg.org')
    mainapp.setApplicationVersion(thgversion.version())
    qtlib.setup_font_substitutions()
    mainapp.setStyleSheet(qtlib.appstylesheet)
    try:
        dlg = dlgfunc(ui, *args, **opts)
        if dlg:
            dlg.show()
            mainapp.exec_()
    except Exception, e:
        from tortoisehg.hgqt.bugreport import run
        error = _('Fatal error opening dialog\n')
        error += traceback.format_exc()
        opts = {}
        opts['cmd'] = ' '.join(sys.argv[1:])
        opts['error'] = error
        opts['nofork'] = True
        bugreport = run(ui, **opts)
        bugreport.show()
        mainapp.exec_()
    mainapp = None

def add(ui, *pats, **opts):
    """add files"""
    from tortoisehg.hgqt.quickop import run
    qtrun(run, ui, *pats, **opts)

def backout(ui, *pats, **opts):
    """backout tool"""
    from tortoisehg.hgqt.backout import run
    qtrun(run, ui, *pats, **opts)

def thgstatus(ui, *pats, **opts):
    """update TortoiseHg status cache"""
    from tortoisehg.util.thgstatus import run
    run(ui, *pats, **opts)

def userconfig(ui, *pats, **opts):
    """user configuration editor"""
    from tortoisehg.hgqt.settings import run
    qtrun(run, ui, *pats, **opts)

def repoconfig(ui, *pats, **opts):
    """repository configuration editor"""
    from tortoisehg.hgqt.settings import run
    qtrun(run, ui, *pats, **opts)

def clone(ui, *pats, **opts):
    """clone tool"""
    from tortoisehg.hgqt.clone import run
    qtrun(run, ui, *pats, **opts)

def commit(ui, *pats, **opts):
    """commit tool"""
    from tortoisehg.hgqt.commit import run
    qtrun(run, ui, *pats, **opts)

def email(ui, *pats, **opts):
    """send changesets by email"""
    from tortoisehg.hgqt.hgemail import run
    qtrun(run, ui, *pats, **opts)

def guess(ui, *pats, **opts):
    """guess previous renames or copies"""
    from tortoisehg.hgqt.guess import run
    qtrun(run, ui, *pats, **opts)

def status(ui, *pats, **opts):
    """browse working copy status"""
    from tortoisehg.hgqt.status import run
    qtrun(run, ui, *pats, **opts)

def tag(ui, *pats, **opts):
    """tag tool"""
    from tortoisehg.hgqt.tag import run
    qtrun(run, ui, *pats, **opts)

def test(ui, *pats, **opts):
    """test arbitrary widgets"""
    from tortoisehg.hgqt.chunkselect import run
    qtrun(run, ui, *pats, **opts)

def remove(ui, *pats, **opts):
    """remove selected files"""
    from tortoisehg.hgqt.quickop import run
    qtrun(run, ui, *pats, **opts)

def revert(ui, *pats, **opts):
    """revert selected files"""
    from tortoisehg.hgqt.quickop import run
    qtrun(run, ui, *pats, **opts)

def forget(ui, *pats, **opts):
    """forget selected files"""
    from tortoisehg.hgqt.quickop import run
    qtrun(run, ui, *pats, **opts)

def hgignore(ui, *pats, **opts):
    """ignore filter editor"""
    from tortoisehg.hgqt.hgignore import run
    qtrun(run, ui, *pats, **opts)

def shellconfig(ui, *pats, **opts):
    """explorer extension configuration editor"""
    from tortoisehg.hgqt.shellconf import run
    qtrun(run, ui, *pats, **opts)

def update(ui, *pats, **opts):
    """update/checkout tool"""
    from tortoisehg.hgqt.update import run
    qtrun(run, ui, *pats, **opts)

def log(ui, *pats, **opts):
    """workbench application"""
    from tortoisehg.hgqt.workbench import run
    qtrun(run, ui, *pats, **opts)

def vdiff(ui, *pats, **opts):
    """launch configured visual diff tool"""
    from tortoisehg.hgqt.visdiff import run
    qtrun(run, ui, *pats, **opts)

def about(ui, *pats, **opts):
    """about dialog"""
    from tortoisehg.hgqt.about import run
    qtrun(run, ui, *pats, **opts)

def grep(ui, *pats, **opts):
    """grep/search dialog"""
    from tortoisehg.hgqt.grep import run
    qtrun(run, ui, *pats, **opts)

def archive(ui, *pats, **opts):
    """archive dialog"""
    from tortoisehg.hgqt.archive import run
    qtrun(run, ui, *pats, **opts)

def annotate(ui, *pats, **opts):
    """annotate dialog"""
    from tortoisehg.hgqt.annotate import run
    if len(pats) != 1:
        ui.warn(_('annotate requires a single filename\n'))
        return
    qtrun(run, ui, *pats, **opts)

### help management, adapted from mercurial.commands.help_()
def help_(ui, name=None, with_version=False, **opts):
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
                option_lists.append((_('use "thg help" for the full list '
                                       'of commands'), ()))
        else:
            if name == 'shortlist':
                msg = _('use "thg help" for the full list of commands '
                        'or "thg -v" for details')
            elif aliases:
                msg = _('use "thg -v help%s" to show aliases and '
                        'global options') % (name and " " + name or "")
            else:
                msg = _('use "thg -v help %s" to show global options') % name
            option_lists.append((msg, ()))

    def helpcmd(name):
        if with_version:
            version(ui)
            ui.write('\n')

        try:
            aliases, i = cmdutil.findcmd(name, table, False)
        except error.AmbiguousCommand, inst:
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
        for c, e in table.iteritems():
            f = c.split("|", 1)[0]
            if select and not select(f):
                continue
            if (not select and name != 'shortlist' and
                e[0].__module__ != __name__):
                continue
            if name == "shortlist" and not f.startswith("^"):
                continue
            f = f.lstrip("^")
            if not ui.debugflag and f.startswith("debug"):
                continue
            doc = e[0].__doc__
            if doc and 'DEPRECATED' in doc and not ui.verbose:
                continue
            #doc = gettext(doc)
            if not doc:
                doc = _("(no help text available)")
            h[f] = doc.splitlines()[0].rstrip()
            cmds[f] = c.lstrip("^")

        if not h:
            ui.status(_('no commands defined\n'))
            return

        ui.status(header)
        fns = sorted(h)
        m = max(map(len, fns))
        for f in fns:
            if ui.verbose:
                commands = cmds[f].replace("|",", ")
                ui.write(" %s:\n      %s\n"%(commands, h[f]))
            else:
                ui.write(' %-*s   %s\n' % (m, f, util.wrap(h[f], m + 4)))

        if not ui.quiet:
            addglobalopts(True)

    def helptopic(name):
        from mercurial import help
        for names, header, doc in help.helptable:
            if name in names:
                break
        else:
            raise error.UnknownCommand(name)

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
            except error.UnknownCommand, inst:
                i = inst
        if i:
            raise i

    else:
        # program name
        if ui.verbose or with_version:
            version(ui)
        else:
            ui.status(_("Thg - TortoiseHg's GUI tools for Mercurial SCM (Hg)\n"))
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

globalopts = [
    ('R', 'repository', '',
     _('repository root directory or symbolic path name')),
    ('v', 'verbose', None, _('enable additional output')),
    ('q', 'quiet', None, _('suppress output')),
    ('h', 'help', None, _('display help and exit')),
    ('', 'debugger', None, _('start debugger')),
    ('', 'profile', None, _('print command execution profile')),
    ('', 'nofork', None, _('do not fork GUI process')),
    ('', 'fork', None, _('always fork GUI process')),
    ('', 'listfile', '', _('read file list from file')),
]

table = {
    "about": (about, [], _('thg about')),
    "add": (add, [], _('thg add [FILE]...')),
    "^annotate|blame": (annotate, 
          [('r', 'rev', '', _('revision to annotate')),
           ('n', 'line', '', _('open to line')),
           ('p', 'pattern', '', _('initial search pattern'))],
        _('thg annotate')),
    "archive": (archive,
        [('r', 'rev', '', _('revision to archive'))],
        _('thg archive')),
    "^backout": (backout,
        [('', 'merge', None,
          _('merge with old dirstate parent after backout')),
         ('', 'parent', '', _('parent to choose when backing out merge')),
         ('r', 'rev', '', _('revision to backout'))],
        _('thg backout [OPTION]... [[-r] REV]')),
    "^clone":
        (clone,
         [('U', 'noupdate', None,
           _('the clone will include an empty working copy '
             '(only a repository)')),
          ('u', 'updaterev', '',
           _('revision, tag or branch to check out')),
          ('r', 'rev', [], _('include the specified changeset')),
          ('b', 'branch', [],
           _('clone only the specified branch')),
          ('', 'pull', None, _('use pull protocol to copy metadata')),
          ('', 'uncompressed', None,
           _('use uncompressed transfer (fast over LAN)')),],
         _('thg clone [OPTION]... SOURCE [DEST]')),
    "^commit|ci": (commit,
        [('u', 'user', '', _('record user as committer')),
         ('d', 'date', '', _('record datecode as commit date'))],
        _('thg commit [OPTIONS] [FILE]...')),
    "^grep|search": (grep, [], _('thg grep')),
    "^guess": (guess, [], _('thg guess')),
    "^hgignore|ignore|filter": (hgignore, [], _('thg hgignore [FILE]')),
    "^email":
        (email,
         [('r', 'rev', [], _('a revision to send')),],
         _('thg email [REVS]')),
    "^log|history|explorer|workbench":
        (log,
         [('l', 'limit', '', _('limit number of changes displayed'))],
         _('thg log [OPTIONS] [FILE]')),
    "remove|rm": (remove, [], _('thg remove [FILE]...')),
    "revert": (revert, [], _('thg revert [FILE]...')),
    "forget": (forget, [], _('thg forget [FILE]...')),
    "^status": (status,
         [('c', 'clean', False, _('show files without changes')),
          ('i', 'ignored', False, _('show ignored files'))],
        _('thg status [OPTIONS] [FILE]')),
    "^tag":
        (tag,
         [('f', 'force', None, _('replace existing tag')),
          ('l', 'local', None, _('make the tag local')),
          ('r', 'rev', '', _('revision to tag')),
          ('', 'remove', None, _('remove a tag')),
          ('m', 'message', '', _('use <text> as commit message')),],
         _('thg tag [-f] [-l] [-m TEXT] [-r REV] [NAME]')),
    "test": (test, [], _('thg test')),
    "help": (help_, [], _('thg help [COMMAND]')),
    "^update|checkout|co":
        (update,
         [('C', 'clean', None, _('discard uncommitted changes (no backup)')),
          ('r', 'rev', '', _('revision to update')),],
         _('thg update [-C] [[-r] REV]')),
    "^userconfig": (userconfig,
        [('', 'focus', '', _('field to give initial focus'))],
        _('thg userconfig')),
    "^repoconfig": (repoconfig,
        [('', 'focus', '', _('field to give initial focus'))],
        _('thg repoconfig')),
    "^vdiff": (vdiff,
        [('c', 'change', '', _('changeset to view in diff tool')),
         ('r', 'rev', [], _('revisions to view in diff tool')),
         ('b', 'bundle', '', _('bundle file to preview'))],
            _('launch visual diff tool')),
}

if os.name == 'nt':
    # TODO: extra detection to determine if shell extension is installed
    table['shellconfig'] = (shellconfig, [], _('thg shellconfig'))

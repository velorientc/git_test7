# run.py - front-end script for TortoiseHg dialogs
#
# Copyright 2008 Steve Borho <steve@borho.org>
# Copyright 2008 TK Soh <teekaysoh@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

shortlicense = '''
Copyright (C) 2008-2013 Steve Borho <steve@borho.org> and others.
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
'''

import os
import pdb
import sys
import subprocess
import traceback
import zlib
import gc

from PyQt4.QtCore import *
from PyQt4.QtGui import *

import mercurial.ui as uimod
from mercurial import util, fancyopts, cmdutil, extensions, error, scmutil

from tortoisehg.hgqt.i18n import agettext as _
from tortoisehg.util import hglib, paths, i18n
from tortoisehg.util import version as thgversion
from tortoisehg.hgqt import bugreport, qtlib

try:
    from tortoisehg.util.config import nofork as config_nofork
except ImportError:
    config_nofork = None

try:
    from thginithook import thginithook
except ImportError:
    thginithook = None

nonrepo_commands = '''userconfig shellconfig clone init
about help version thgstatus serve rejects log'''

def dispatch(args):
    """run the command specified in args"""
    try:
        u = uimod.ui()
        if '--traceback' in args:
            u.setconfig('ui', 'traceback', 'on')
        if '--debugger' in args:
            pdb.set_trace()
        return _runcatch(u, args)
    except error.ParseError, e:
        from tortoisehg.hgqt.bugreport import ExceptionMsgBox
        opts = {}
        opts['cmd'] = ' '.join(sys.argv[1:])
        opts['values'] = e
        opts['error'] = traceback.format_exc()
        opts['nofork'] = True
        errstring = _('Error string "%(arg0)s" at %(arg1)s<br>Please '
                      '<a href="#edit:%(arg1)s">edit</a> your config')
        if not QApplication.instance():
            main = QApplication(sys.argv)
        dlg = ExceptionMsgBox(hglib.tounicode(str(e)),
                              hglib.tounicode(errstring), opts, parent=None)
        dlg.exec_()
    except SystemExit:
        pass
    except Exception, e:
        # generic errors before the QApplication is started
        if '--debugger' in args:
            pdb.post_mortem(sys.exc_info()[2])
        opts = {}
        opts['cmd'] = ' '.join(sys.argv[1:])
        opts['error'] = traceback.format_exc()
        if not QApplication.instance():
            main = QApplication(sys.argv)
        dlg = bugreport.BugReport(opts)
        dlg.exec_()
        return -1
    except KeyboardInterrupt:
        print _('\nCaught keyboard interrupt, aborting.\n')

origwdir = os.getcwd()
def portable_fork(ui, opts):
    if 'THG_GUI_SPAWN' in os.environ or (
        not opts.get('fork') and opts.get('nofork')):
        os.environ['THG_GUI_SPAWN'] = '1'
        return
    elif ui.configbool('tortoisehg', 'guifork', None) is not None:
        if not ui.configbool('tortoisehg', 'guifork'):
            return
    elif config_nofork:
        return
    portable_start_fork()
    sys.exit(0)

def portable_start_fork(extraargs=None):
    os.environ['THG_GUI_SPAWN'] = '1'
    # Spawn background process and exit
    if hasattr(sys, "frozen"):
        args = sys.argv
    else:
        args = [sys.executable] + sys.argv
    if extraargs:
        args += extraargs
    cmdline = subprocess.list2cmdline(args)
    os.chdir(origwdir)
    subprocess.Popen(cmdline,
                     creationflags=qtlib.openflags,
                     shell=True)

# Windows and Nautilus shellext execute
# "thg subcmd --listfile TMPFILE" or "thg subcmd --listfileutf8 TMPFILE"(planning) .
# Extensions written in .hg/hgrc is enabled after calling
# extensions.loadall(lui)
#
# 1. win32mbcs extension
#     Japanese shift_jis and Chinese big5 include '0x5c'(backslash) in filename.
#     Mercurial resolves this problem with win32mbcs extension.
#     So, thg must parse path after loading win32mbcs extension.
#
# 2. fixutf8 extension
#     fixutf8 extension requires paths encoding utf-8.
#     So, thg need to convert to utf-8.
#

_lines     = []
_linesutf8 = []

def get_lines_from_listfile(filename, isutf8):
    global _lines
    global _linesutf8
    try:
        if filename == '-':
            lines = [ x.replace("\n", "") for x in sys.stdin.readlines() ]
        else:
            fd = open(filename, "r")
            lines = [ x.replace("\n", "") for x in fd.readlines() ]
            fd.close()
            os.unlink(filename)
        if isutf8:
            _linesutf8 = lines
        else:
            _lines = lines
    except IOError:
        sys.stderr.write(_('can not read file "%s". Ignored.\n') % filename)

def get_files_from_listfile():
    global _lines
    global _linesutf8
    lines = []
    need_to_utf8 = False
    if os.name == 'nt':
        try:
            fixutf8 = extensions.find("fixutf8")
            if fixutf8:
                need_to_utf8 = True
        except KeyError:
            pass

    if need_to_utf8:
        lines += _linesutf8
        for l in _lines:
            lines.append(hglib.toutf(l))
    else:
        lines += _lines
        for l in _linesutf8:
            lines.append(hglib.fromutf(l))

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
            cpath = scmutil.canonpath(root, cwd, f)
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
        raise error.CommandError(None, inst)

    if args:
        alias, args = args[0], args[1:]
    elif options['help']:
        help_(ui, None)
        sys.exit()
    else:
        alias, args = 'workbench', []
    aliases, i = cmdutil.findcmd(alias, table, ui.config("ui", "strict"))
    for a in aliases:
        if a.startswith(alias):
            alias = a
            break
    cmd = aliases[0]
    c = list(i[1])

    # combine global options into local
    for o in globalopts:
        c.append((o[0], o[1], options[o[1]], o[3]))

    try:
        args = fancyopts.fancyopts(args, c, cmdoptions, True)
    except fancyopts.getopt.GetoptError, inst:
        raise error.CommandError(cmd, inst)

    # separate global options back out
    for o in globalopts:
        n = o[1]
        options[n] = cmdoptions[n]
        del cmdoptions[n]

    listfile = options.get('listfile')
    if listfile:
        del options['listfile']
        get_lines_from_listfile(listfile, False)
    listfileutf8 = options.get('listfileutf8')
    if listfileutf8:
        del options['listfileutf8']
        get_lines_from_listfile(listfileutf8, True)

    return (cmd, cmd and i[0] or None, args, options, cmdoptions, alias)

def _runcatch(ui, args):
    try:
        try:
            return runcommand(ui, args)
        finally:
            ui.flush()
    except error.AmbiguousCommand, inst:
        ui.status(_("thg: command '%s' is ambiguous:\n    %s\n") %
                (inst.args[0], " ".join(inst.args[1])))
    except error.UnknownCommand, inst:
        ui.status(_("thg: unknown command '%s'\n") % inst.args[0])
        help_(ui, 'shortlist')
    except error.CommandError, inst:
        if inst.args[0]:
            ui.status(_("thg %s: %s\n") % (inst.args[0], inst.args[1]))
            help_(ui, inst.args[0])
        else:
            ui.status(_("thg: %s\n") % inst.args[1])
            help_(ui, 'shortlist')
    except error.RepoError, inst:
        ui.status(_("abort: %s!\n") % inst)

    return -1

def runcommand(ui, args):
    cmd, func, args, options, cmdoptions, alias = _parse(ui, args)
    cmdoptions['alias'] = alias
    ui.setconfig("ui", "verbose", str(bool(options["verbose"])))
    i18n.setlanguage(ui.config('tortoisehg', 'ui.language'))

    if options['help']:
        return help_(ui, cmd)

    if options['newworkbench']:
        cmdoptions['newworkbench'] = True

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
        if not os.path.exists(path) or not os.path.isdir(path+'/.hg'):
            print 'abort: %s is not a repository' % path
            return 1
        os.chdir(path)
    if options['fork']:
        cmdoptions['fork'] = True
    if options['nofork'] or options['profile']:
        cmdoptions['nofork'] = True
    path = paths.find_root(os.getcwd())
    if path:
        cmdoptions['repository'] = path
        try:
            lui = ui.copy()
            lui.readconfig(os.path.join(path, ".hg", "hgrc"))
        except IOError:
            pass
    else:
        lui = ui

    hglib.wrapextensionsloader()  # enable blacklist of extensions
    extensions.loadall(lui)

    args += get_files_from_listfile()

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
            raise error.CommandError(cmd, _("invalid arguments"))

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

class GarbageCollector(QObject):
    '''
    Disable automatic garbage collection and instead collect manually
    every INTERVAL milliseconds.

    This is done to ensure that garbage collection only happens in the GUI
    thread, as otherwise Qt can crash.
    '''

    INTERVAL = 5000

    def __init__(self, parent, debug=False):
        QObject.__init__(self, parent)
        self.debug = debug

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)

        self.threshold = gc.get_threshold()
        gc.disable()
        self.timer.start(self.INTERVAL)
        #gc.set_debug(gc.DEBUG_SAVEALL)

    def check(self):
        l0, l1, l2 = gc.get_count()
        if l0 > self.threshold[0]:
            num = gc.collect(0)
            if self.debug:
                print 'GarbageCollector.check:', l0, l1, l2
                print 'collected gen 0, found', num, 'unreachable'
            if l1 > self.threshold[1]:
                num = gc.collect(1)
                if self.debug:
                    print 'collected gen 1, found', num, 'unreachable'
                if l2 > self.threshold[2]:
                    num = gc.collect(2)
                    if self.debug:
                        print 'collected gen 2, found', num, 'unreachable'

    def debug_cycles(self):
        gc.collect()
        for obj in gc.garbage:
            print (obj, repr(obj), type(obj))

class _QtRunner(QObject):
    """Run Qt app and hold its windows

    NOTE: This object will be instantiated before QApplication, it means
    there's a limitation on Qt's event handling. See
    http://doc.qt.nokia.com/4.6/threads-qobject.html#per-thread-event-loop
    """

    _exceptionOccured = pyqtSignal(object, object, object)

    # {exception class: message}
    # It doesn't check the hierarchy of exception classes for simplicity.
    _recoverableexc = {
        error.RepoLookupError: _('Try refreshing your repository.'),
        zlib.error:            _('Try refreshing your repository.'),
        error.ParseError: _('Error string "%(arg0)s" at %(arg1)s<br>Please '
                            '<a href="#edit:%(arg1)s">edit</a> your config'),
        error.ConfigError: _('Configuration Error: "%(arg0)s",<br>Please '
                             '<a href="#fix:%(arg0)s">fix</a> your config'),
        error.Abort: _('Operation aborted:<br><br>%(arg0)s.'),
        error.LockUnavailable: _('Repository is locked'),
        }

    def __init__(self):
        super(_QtRunner, self).__init__()
        gc.disable()
        self.debug = 'THGDEBUG' in os.environ
        self._mainapp = None
        self._dialogs = []
        self.errors = []
        sys.excepthook = lambda t, v, o: self.ehook(t, v, o)

        # can be emitted by another thread; postpones it until next
        # eventloop of main (GUI) thread.
        self._exceptionOccured.connect(self.putexception,
                                       Qt.QueuedConnection)

    def ehook(self, etype, evalue, tracebackobj):
        'Will be called by any thread, on any unhandled exception'
        elist = traceback.format_exception(etype, evalue, tracebackobj)
        if 'THGDEBUG' in os.environ:
            sys.stderr.write(''.join(elist))
        self._exceptionOccured.emit(etype, evalue, tracebackobj)
        # not thread-safe to touch self.errors here

    @pyqtSlot(object, object, object)
    def putexception(self, etype, evalue, tracebackobj):
        'Enque exception info and display it later; run in main thread'
        if not self.errors:
            QTimer.singleShot(10, self.excepthandler)
        self.errors.append((etype, evalue, tracebackobj))

    @pyqtSlot()
    def excepthandler(self):
        'Display exception info; run in main (GUI) thread'
        try:
            try:
                self._showexceptiondialog()
            except:
                # make sure to quit mainloop first, so that it never leave
                # zombie process.
                self._mainapp.exit(1)
                self._printexception()
        finally:
            self.errors = []

    def _showexceptiondialog(self):
        from tortoisehg.hgqt.bugreport import BugReport, ExceptionMsgBox
        opts = {}
        opts['cmd'] = ' '.join(sys.argv[1:])
        opts['error'] = ''.join(''.join(traceback.format_exception(*args))
                                for args in self.errors)
        etype, evalue = self.errors[0][:2]
        if (len(set(e[0] for e in self.errors)) == 1
            and etype in self._recoverableexc):
            opts['values'] = evalue
            errstr = self._recoverableexc[etype]
            if etype is error.Abort and evalue.hint:
                errstr = u''.join([errstr, u'<br><b>', _('hint:'),
                                   u'</b> %(arg1)s'])
                opts['values'] = [str(evalue), evalue.hint]
            dlg = ExceptionMsgBox(hglib.tounicode(str(evalue)),
                                  hglib.tounicode(errstr), opts,
                                  parent=self._mainapp.activeWindow())
        elif etype is KeyboardInterrupt:
            if qtlib.QuestionMsgBox(hglib.tounicode(_('Keyboard interrupt')),
                    hglib.tounicode(_('Close this application?'))):
                QApplication.quit()
            else:
                self.errors = []
                return
        else:
            dlg = BugReport(opts, parent=self._mainapp.activeWindow())
        dlg.exec_()

    def _printexception(self):
        for args in self.errors:
            traceback.print_exception(*args)

    def __call__(self, dlgfunc, ui, *args, **opts):
        portable_fork(ui, opts)

        if self._mainapp:
            self._opendialog(dlgfunc, ui, *args, **opts)
            return

        QSettings.setDefaultFormat(QSettings.IniFormat)

        self._mainapp = QApplication(sys.argv)
        try:
            self._gc = GarbageCollector(self, self.debug)
            # default org is used by QSettings
            self._mainapp.setApplicationName('TortoiseHgQt')
            self._mainapp.setOrganizationName('TortoiseHg')
            self._mainapp.setOrganizationDomain('tortoisehg.org')
            self._mainapp.setApplicationVersion(thgversion.version())
            self._fixlibrarypaths()
            self._installtranslator()
            qtlib.setup_font_substitutions()
            qtlib.fix_application_font()
            qtlib.configstyles(ui)
            qtlib.initfontcache(ui)
            self._mainapp.setWindowIcon(qtlib.geticon('thg-logo'))

            if 'repository' in opts:
                try:
                    # Ensure we can open the repository before opening any
                    # dialog windows.  Since thgrepo instances are cached, this
                    # is not wasted.
                    from tortoisehg.hgqt import thgrepo
                    thgrepo.repository(ui, opts['repository'])
                except error.RepoError, e:
                    qtlib.WarningMsgBox(hglib.tounicode(_('Repository Error')),
                                        hglib.tounicode(str(e)))
                    return
            dlg = dlgfunc(ui, *args, **opts)
            if dlg:
                dlg.show()
                dlg.raise_()
            else:
                return -1
        except:
            # Exception before starting eventloop needs to be postponed;
            # otherwise it will be ignored silently.
            def reraise():
                raise
            QTimer.singleShot(0, reraise)

        if thginithook is not None:
            thginithook()

        try:
            return self._mainapp.exec_()
        finally:
            self._mainapp = None

    def _fixlibrarypaths(self):
        # make sure to use the bundled Qt plugins to avoid ABI incompatibility
        # http://qt-project.org/doc/qt-4.8/deployment-windows.html#qt-plugins
        if os.name == 'nt' and getattr(sys, 'frozen', False):
            self._mainapp.setLibraryPaths([self._mainapp.applicationDirPath()])

    def _installtranslator(self):
        if not i18n.language:
            return
        t = QTranslator(self._mainapp)
        t.load('qt_' + i18n.language, qtlib.gettranslationpath())
        self._mainapp.installTranslator(t)

    def _opendialog(self, dlgfunc, ui, *args, **opts):
        dlg = dlgfunc(ui, *args, **opts)
        if not dlg:
            return

        self._dialogs.append(dlg)  # avoid garbage collection
        if hasattr(dlg, 'finished') and hasattr(dlg.finished, 'connect'):
            dlg.finished.connect(dlg.deleteLater)
        # NOTE: Somehow `destroyed` signal doesn't emit the original obj.
        # So we cannot write `dlg.destroyed.connect(self._forgetdialog)`.
        dlg.destroyed.connect(lambda: self._forgetdialog(dlg))
        dlg.show()

    def _forgetdialog(self, dlg):
        """forget the dialog to be garbage collectable"""
        assert dlg in self._dialogs
        self._dialogs.remove(dlg)

qtrun = _QtRunner()

table = {}
command = cmdutil.command(table)

# common command options

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
    ('', 'listfileutf8', '', _('read file list from file encoding utf-8')),
    ('', 'newworkbench', None, _('open a new workbench window')),
]

# commands start here, listed alphabetically

@command('about', [], _('thg about'))
def about(ui, *pats, **opts):
    """about dialog"""
    from tortoisehg.hgqt.about import run
    return qtrun(run, ui, *pats, **opts)

@command('add', [], _('thg add [FILE]...'))
def add(ui, *pats, **opts):
    """add files"""
    from tortoisehg.hgqt.quickop import run
    return qtrun(run, ui, *pats, **opts)

@command('^annotate|blame',
    [('r', 'rev', '', _('revision to annotate')),
     ('n', 'line', '', _('open to line')),
     ('p', 'pattern', '', _('initial search pattern'))],
    _('thg annotate'))
def annotate(ui, *pats, **opts):
    """annotate dialog"""
    from tortoisehg.hgqt.manifestdialog import run
    if len(pats) != 1:
        ui.warn(_('annotate requires a single filename\n'))
        if pats:
            pats = pats[0:]
        else:
            return
    return qtrun(run, ui, *pats, **opts)

@command('archive',
    [('r', 'rev', '', _('revision to archive'))],
    _('thg archive'))
def archive(ui, *pats, **opts):
    """archive dialog"""
    from tortoisehg.hgqt.archive import run
    return qtrun(run, ui, *pats, **opts)

@command('^backout',
    [('', 'merge', None, _('merge with old dirstate parent after backout')),
     ('', 'parent', '', _('parent to choose when backing out merge')),
     ('r', 'rev', '', _('revision to backout'))],
    _('thg backout [OPTION]... [[-r] REV]'))
def backout(ui, *pats, **opts):
    """backout tool"""
    from tortoisehg.hgqt.backout import run
    return qtrun(run, ui, *pats, **opts)

@command('^bisect', [], _('thg bisect'))
def bisect(ui, *pats, **opts):
    """bisect dialog"""
    from tortoisehg.hgqt.bisect import run
    return qtrun(run, ui, *pats, **opts)

@command('^clone',
    [('U', 'noupdate', None, _('the clone will include an empty working copy '
                               '(only a repository)')),
     ('u', 'updaterev', '', _('revision, tag or branch to check out')),
     ('r', 'rev', '', _('include the specified changeset')),
     ('b', 'branch', [], _('clone only the specified branch')),
     ('', 'pull', None, _('use pull protocol to copy metadata')),
     ('', 'uncompressed', None, _('use uncompressed transfer '
                                  '(fast over LAN)'))],
    _('thg clone [OPTION]... SOURCE [DEST]'))
def clone(ui, *pats, **opts):
    """clone tool"""
    from tortoisehg.hgqt.clone import run
    return qtrun(run, ui, *pats, **opts)

@command('^commit|ci',
    [('u', 'user', '', _('record user as committer')),
     ('d', 'date', '', _('record datecode as commit date'))],
    _('thg commit [OPTIONS] [FILE]...'))
def commit(ui, *pats, **opts):
    """commit tool"""
    from tortoisehg.hgqt.commit import run
    return qtrun(run, ui, *pats, **opts)

@command('debugbugreport', [], _('thg debugbugreport [TEXT]'))
def debugbugreport(ui, *pats, **opts):
    """open bugreport dialog by exception"""
    raise Exception(' '.join(pats))

@command('drag_copy', [], _('thg drag_copy SOURCE... DEST'))
def drag_copy(ui, *pats, **opts):
    """Copy the selected files to the desired directory"""
    from tortoisehg.hgqt.dnd import run_copy
    return qtrun(run_copy, ui, *pats, **opts)

@command('drag_move', [], _('thg drag_move SOURCE... DEST'))
def drag_move(ui, *pats, **opts):
    """Move the selected files to the desired directory"""
    from tortoisehg.hgqt.dnd import run_move
    return qtrun(run_move, ui, *pats, **opts)

@command('^email',
    [('r', 'rev', [], _('a revision to send'))],
    _('thg email [REVS]'))
def email(ui, *pats, **opts):
    """send changesets by email"""
    from tortoisehg.hgqt.hgemail import run
    return qtrun(run, ui, *pats, **opts)

@command('forget', [], _('thg forget [FILE]...'))
def forget(ui, *pats, **opts):
    """forget selected files"""
    from tortoisehg.hgqt.quickop import run
    return qtrun(run, ui, *pats, **opts)

@command('graft',
    [('r', 'rev', [], _('revisions to graft'))],
    _('thg graft [-r] REV...'))
def graft(ui, *revs, **opts):
    """graft dialog"""
    from tortoisehg.hgqt.graft import run
    return qtrun(run, ui, *revs, **opts)

@command('^grep|search',
    [('i', 'ignorecase', False, _('ignore case during search'))],
    _('thg grep'))
def grep(ui, *pats, **opts):
    """grep/search dialog"""
    from tortoisehg.hgqt.grep import run
    return qtrun(run, ui, *pats, **opts)

@command('^guess', [], _('thg guess'))
def guess(ui, *pats, **opts):
    """guess previous renames or copies"""
    from tortoisehg.hgqt.guess import run
    return qtrun(run, ui, *pats, **opts)

### help management, adapted from mercurial.commands.help_()
@command('help', [], _('thg help [COMMAND]'))
def help_(ui, name=None, with_version=False, **opts):
    """show help for a command, extension, or list of commands

    With no arguments, print a list of commands and short help.

    Given a command name, print help for that command.

    Given an extension name, print help for that extension, and the
    commands it provides."""
    option_lists = []
    textwidth = ui.termwidth() - 2

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
            doc = _("(no help text available)")
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
                ui.write('%s\n' % (util.wrap(h[f], textwidth,
                                             initindent=' %-*s   ' % (m, f),
                                             hangindent=' ' * (m + 4))))

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
            doc = _("(no help text available)")
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
                initindent = ' %-*s  ' % (opts_len, first)
                hangindent = ' ' * (opts_len + 3)
                ui.write('%s\n' % (util.wrap(second, textwidth,
                                             initindent=initindent,
                                             hangindent=hangindent)))
            else:
                ui.write("%s\n" % first)

@command('^hgignore|ignore|filter', [], _('thg hgignore [FILE]'))
def hgignore(ui, *pats, **opts):
    """ignore filter editor"""
    from tortoisehg.hgqt.hgignore import run
    return qtrun(run, ui, *pats, **opts)

@command('import',
    [('', 'mq', False, _('import to the patch queue (MQ)'))],
    _('thg import [OPTION] [SOURCE]...'))
def import_(ui, *pats, **opts):
    """import an ordered set of patches"""
    from tortoisehg.hgqt.thgimport import run
    return qtrun(run, ui, *pats, **opts)

@command('^init', [], _('thg init [DEST]'))
def init(ui, *pats, **opts):
    """init dialog"""
    from tortoisehg.hgqt.hginit import run
    return qtrun(run, ui, *pats, **opts)

@command('^log|history|explorer|workbench',
    [('l', 'limit', '', _('(DEPRECATED)'))],
    _('thg log [OPTIONS] [FILE]'))
def log(ui, *pats, **opts):
    """workbench application"""
    from tortoisehg.hgqt.workbench import run
    return qtrun(run, ui, *pats, **opts)

@command('manifest',
    [('r', 'rev', '', _('revision to display')),
     ('n', 'line', '', _('open to line')),
     ('p', 'pattern', '', _('initial search pattern'))],
    _('thg manifest [-r REV] [FILE]'))
def manifest(ui, *pats, **opts):
    """display the current or given revision of the project manifest"""
    from tortoisehg.hgqt.manifestdialog import run
    return qtrun(run, ui, *pats, **opts)

@command('^merge',
    [('r', 'rev', '', _('revision to merge'))],
    _('thg merge [[-r] REV]'))
def merge(ui, *pats, **opts):
    """merge wizard"""
    from tortoisehg.hgqt.merge import run
    return qtrun(run, ui, *pats, **opts)

@command('mq', [], _('thg mq'))
def mq(ui, *pats, **opts):
    """Mercurial Queue tool"""
    from tortoisehg.hgqt.mq import run
    return qtrun(run, ui, *pats, **opts)

@command('postreview',
    [('r', 'rev', [], _('a revision to post'))],
    _('thg postreview [-r] REV...'))
def postreview(ui, *pats, **opts):
    """post changesets to reviewboard"""
    from tortoisehg.hgqt.postreview import run
    return qtrun(run, ui, *pats, **opts)

@command('^purge', [], _('thg purge'))
def purge(ui, *pats, **opts):
    """purge unknown and/or ignore files from repository"""
    from tortoisehg.hgqt.purge import run
    return qtrun(run, ui, *pats, **opts)

@command('^qqueue', [], _('thg qqueue'))
def qqueue(ui, *pats, **opts):
    """manage multiple MQ patch queues"""
    from tortoisehg.hgqt.qqueue import run
    return qtrun(run, ui, *pats, **opts)

@command('^qreorder', [], _('thg qreorder'))
def qreorder(ui, *pats, **opts):
    """Reorder unapplied MQ patches"""
    from tortoisehg.hgqt.qreorder import run
    return qtrun(run, ui, *pats, **opts)

@command('^rebase',
    [('', 'keep', False, _('keep original changesets')),
     ('', 'keepbranches', False, _('keep original branch names')),
     ('', 'detach', False, _('(DEPRECATED)')),
     ('s', 'source', '', _('rebase from the specified changeset')),
     ('d', 'dest', '', _('rebase onto the specified changeset'))],
    _('thg rebase -s REV -d REV [--keep]'))
def rebase(ui, *pats, **opts):
    """rebase dialog"""
    from tortoisehg.hgqt.rebase import run
    return qtrun(run, ui, *pats, **opts)

@command('rejects', [], _('thg rejects [FILE]'))
def rejects(ui, *pats, **opts):
    """Manually resolve rejected patch chunks"""
    from tortoisehg.hgqt.rejects import run
    return qtrun(run, ui, *pats, **opts)

@command('remove|rm', [], _('thg remove [FILE]...'))
def remove(ui, *pats, **opts):
    """remove selected files"""
    from tortoisehg.hgqt.quickop import run
    return qtrun(run, ui, *pats, **opts)

@command('rename|mv|copy', [], _('thg rename SOURCE [DEST]...'))
def rename(ui, *pats, **opts):
    """rename dialog"""
    from tortoisehg.hgqt.rename import run
    return qtrun(run, ui, *pats, **opts)

@command('^repoconfig',
    [('', 'focus', '', _('field to give initial focus'))],
    _('thg repoconfig'))
def repoconfig(ui, *pats, **opts):
    """repository configuration editor"""
    from tortoisehg.hgqt.settings import run
    return qtrun(run, ui, *pats, **opts)

@command('resolve', [], _('thg resolve'))
def resolve(ui, *pats, **opts):
    """resolve dialog"""
    from tortoisehg.hgqt.resolve import run
    return qtrun(run, ui, *pats, **opts)

@command('^revdetails',
    [('r', 'rev', '', _('the revision to show'))],
    _('thg revdetails [-r REV]'))
def revdetails(ui, *pats, **opts):
    """revision details tool"""
    from tortoisehg.hgqt.revdetails import run
    return qtrun(run, ui, *pats, **opts)

@command('revert', [], _('thg revert [FILE]...'))
def revert(ui, *pats, **opts):
    """revert selected files"""
    from tortoisehg.hgqt.quickop import run
    return qtrun(run, ui, *pats, **opts)

@command('rupdate',
    [('r', 'rev', '', _('revision to update'))],
    _('thg rupdate [[-r] REV]'))
def rupdate(ui, *pats, **opts):
    """update a remote repository"""
    from tortoisehg.hgqt.rupdate import run
    return qtrun(run, ui, *pats, **opts)

@command('^serve',
    [('', 'web-conf', '', _('name of the hgweb config file (serve more than '
                            'one repository)')),
     ('', 'webdir-conf', '', _('name of the hgweb config file (DEPRECATED)'))],
    _('thg serve [--web-conf FILE]'))
def serve(ui, *pats, **opts):
    """start stand-alone webserver"""
    from tortoisehg.hgqt.serve import run
    return qtrun(run, ui, *pats, **opts)

if os.name == 'nt':
    # TODO: extra detection to determine if shell extension is installed
    @command('shellconfig', [], _('thg shellconfig'))
    def shellconfig(ui, *pats, **opts):
        """explorer extension configuration editor"""
        from tortoisehg.hgqt.shellconf import run
        return qtrun(run, ui, *pats, **opts)

@command('shelve|unshelve', [], _('thg shelve'))
def shelve(ui, *pats, **opts):
    """Move changes between working directory and patches"""
    from tortoisehg.hgqt.shelve import run
    return qtrun(run, ui, *pats, **opts)

@command('^status|st',
    [('c', 'clean', False, _('show files without changes')),
     ('i', 'ignored', False, _('show ignored files'))],
    _('thg status [OPTIONS] [FILE]'))
def status(ui, *pats, **opts):
    """browse working copy status"""
    from tortoisehg.hgqt.status import run
    return qtrun(run, ui, *pats, **opts)

@command('^strip',
    [('f', 'force', None, _('discard uncommitted changes (no backup)')),
     ('n', 'nobackup', None, _('do not back up stripped revisions')),
     ('r', 'rev', '', _('revision to strip'))],
    _('thg strip [-f] [-n] [[-r] REV]'))
def strip(ui, *pats, **opts):
    """strip dialog"""
    from tortoisehg.hgqt.thgstrip import run
    return qtrun(run, ui, *pats, **opts)

@command('^sync|synchronize', [], _('thg sync [PEER]'))
def sync(ui, *pats, **opts):
    """Synchronize with other repositories"""
    from tortoisehg.hgqt.sync import run
    return qtrun(run, ui, *pats, **opts)

@command('^tag',
    [('f', 'force', None, _('replace existing tag')),
     ('l', 'local', None, _('make the tag local')),
     ('r', 'rev', '', _('revision to tag')),
     ('', 'remove', None, _('remove a tag')),
     ('m', 'message', '', _('use <text> as commit message'))],
    _('thg tag [-f] [-l] [-m TEXT] [-r REV] [NAME]'))
def tag(ui, *pats, **opts):
    """tag tool"""
    from tortoisehg.hgqt.tag import run
    return qtrun(run, ui, *pats, **opts)

@command('thgstatus',
    [('',  'delay', None, _('wait until the second ticks over')),
     ('n', 'notify', [], _('notify the shell for paths given')),
     ('',  'remove', None, _('remove the status cache')),
     ('s', 'show', None, _('show the contents of the status cache '
                           '(no update)')),
     ('',  'all', None, _('udpate all repos in current dir'))],
    _('thg thgstatus [OPTION]'))
def thgstatus(ui, *pats, **opts):
    """update TortoiseHg status cache"""
    from tortoisehg.util.thgstatus import run
    run(ui, *pats, **opts)

@command('^update|checkout|co',
    [('C', 'clean', None, _('discard uncommitted changes (no backup)')),
     ('r', 'rev', '', _('revision to update')),],
    _('thg update [-C] [[-r] REV]'))
def update(ui, *pats, **opts):
    """update/checkout tool"""
    from tortoisehg.hgqt.update import run
    return qtrun(run, ui, *pats, **opts)

@command('^userconfig',
    [('', 'focus', '', _('field to give initial focus'))],
    _('thg userconfig'))
def userconfig(ui, *pats, **opts):
    """user configuration editor"""
    from tortoisehg.hgqt.settings import run
    return qtrun(run, ui, *pats, **opts)

@command('^vdiff',
    [('c', 'change', '', _('changeset to view in diff tool')),
     ('r', 'rev', [], _('revisions to view in diff tool')),
     ('b', 'bundle', '', _('bundle file to preview'))],
    _('launch visual diff tool'))
def vdiff(ui, *pats, **opts):
    """launch configured visual diff tool"""
    from tortoisehg.hgqt.visdiff import run
    return qtrun(run, ui, *pats, **opts)

@command('^version',
    [('v', 'verbose', None, _('print license'))],
    _('thg version [OPTION]'))
def version(ui, **opts):
    """output version and copyright information"""
    ui.write(_('TortoiseHg Dialogs (version %s), '
               'Mercurial (version %s)\n') %
               (thgversion.version(), hglib.hgversion))
    if not ui.quiet:
        ui.write(shortlicense)

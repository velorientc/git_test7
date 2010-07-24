# setup.py
# A distutils setup script to install TortoiseHg in Windows and Posix
# environments.
#
# On Windows, this script is mostly used to build a stand-alone
# TortoiseHg package.  See installer\build.txt for details. The other
# use is to report the current version of the TortoiseHg source.


import time
import sys
import os
import subprocess
from distutils import log
from distutils.core import setup, Command
from distutils.command.build import build
from distutils.dep_util import newer
from distutils.spawn import spawn, find_executable
from os.path import isdir, exists, join, walk, splitext

thgcopyright = 'Copyright (C) 2010 Steve Borho and others'
hgcopyright = 'Copyright (C) 2005-2010 Matt Mackall and others'

class build_mo(Command):

    description = "build translations (.mo files)"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        if not find_executable('msgfmt'):
            self.warn("could not find msgfmt executable, no translations "
                     "will be built")
            return

        podir = 'i18n/tortoisehg'
        if not os.path.isdir(podir):
            self.warn("could not find %s/ directory" % podir)
            return

        join = os.path.join
        for po in os.listdir(podir):
            if not po.endswith('.po'):
                continue
            pofile = join(podir, po)
            modir = join('locale', po[:-3], 'LC_MESSAGES')
            mofile = join(modir, 'tortoisehg.mo')
            cmd = ['msgfmt', '-v', '-o', mofile, pofile]
            if sys.platform != 'sunos5':
                # msgfmt on Solaris does not know about -c
                cmd.append('-c')
            self.mkpath(modir)
            self.make_file([pofile], mofile, spawn, (cmd,))

class build_qt(Command):
    description = "build PyQt GUIs (.ui) and resources (.qrc)"
    user_options = [('force', 'f', 'forcibly compile everything'
                     ' (ignore file timestamps)')]
    boolean_options = ('force',)

    def initialize_options(self):
        self.force = None

    def finalize_options(self):
        self.set_undefined_options('build', ('force', 'force'))

    def compile_ui(self, ui_file, py_file=None):
        # Search for pyuic4 in python bin dir, then in the $Path.
        if py_file is None:
            py_file = splitext(ui_file)[0] + "_ui.py"
        if not(self.force or newer(ui_file, py_file)):
            return
        try:
            from PyQt4 import uic
            fp = open(py_file, 'w')
            uic.compileUi(ui_file, fp)
            fp.close()
            log.info('compiled %s into %s' % (ui_file, py_file))
        except Exception, e:
            self.warn('Unable to compile user interface %s' % e)
            return

    def compile_rc(self, qrc_file, py_file=None):
        # Search for pyuic4 in python bin dir, then in the $Path.
        if py_file is None:
            py_file = splitext(qrc_file)[0] + "_rc.py"
        if not(self.force or newer(qrc_file, py_file)):
            return
        if os.system('pyrcc4 "%s" -o "%s"' % (qrc_file, py_file)) > 0:
            self.warn("Unable to generate python module for resource file %s"
                      % qrc_file)
        
    def run(self):
        for dirpath, _, filenames in os.walk(join('tortoisehg', 'hgqt')):
            for filename in filenames:
                if filename.endswith('.ui'):
                    self.compile_ui(join(dirpath, filename))
                elif filename.endswith('.qrc'):
                    self.compile_rc(join(dirpath, filename))


build.sub_commands.insert(0, ('build_qt', None))
build.sub_commands.append(('build_mo', None))

cmdclass = {
        'build_qt': build_qt ,
        'build_mo': build_mo ,
    }

def setup_windows(version):
    # Specific definitios for Windows NT-alike installations
    _scripts = []
    _data_files = []
    _packages = ['tortoisehg.hgqt', 'tortoisehg.util', 'tortoisehg']
    extra = {}
    hgextmods = []

    # py2exe needs to be installed to work
    try:
        import py2exe

        # Help py2exe to find win32com.shell
        try:
            import modulefinder
            import win32com
            for p in win32com.__path__[1:]: # Take the path to win32comext
                modulefinder.AddPackagePath("win32com", p)
            pn = "win32com.shell"
            __import__(pn)
            m = sys.modules[pn]
            for p in m.__path__[1:]:
                modulefinder.AddPackagePath(pn, p)
        except ImportError:
            pass

    except ImportError:
        if '--version' not in sys.argv:
            raise

    if 'py2exe' in sys.argv:
        import hgext
        hgextdir = os.path.dirname(hgext.__file__)
        hgextmods = set(["hgext." + os.path.splitext(f)[0]
                      for f in os.listdir(hgextdir)])
        _data_files = [(root, [os.path.join(root, file_) for file_ in files])
                            for root, dirs, files in os.walk('icons')]

    # add library files to support PyGtk-based dialogs/windows
    includes = ['dbhash', 'pango', 'atk', 'pangocairo', 'cairo', 'gobject']

    # Manually include other modules py2exe can't find by itself.
    if 'hgext.highlight' in hgextmods:
        includes += ['pygments.*', 'pygments.lexers.*', 'pygments.formatters.*',
                     'pygments.filters.*', 'pygments.styles.*']
    if 'hgext.patchbomb' in hgextmods:
        includes += ['email.*', 'email.mime.*']

    extra['options'] = {
       "py2exe" : {
           "skip_archive" : 0,

           # Don't pull in all this MFC stuff used by the makepy UI.
           "excludes" : "pywin,pywin.dialogs,pywin.dialogs.list",
           "includes" : includes,
           "optimize" : 1
       }
    }
    extra['console'] = [
            {'script':'contrib/hg', 
             'icon_resources':[(0,'icons/hg.ico')],
             'description':'Mercurial Distributed SCM',
             'copyright':hgcopyright,
             'product_version':version},
            {'script':'thg',
             'icon_resources':[(0,'icons/thg_logo.ico')],
             'description':'TortoiseHg GUI tools for Mercurial SCM',
             'copyright':thgcopyright,
             'product_version':version},
            {'script':'contrib/docdiff.py',
             'icon_resources':[(0,'icons/TortoiseMerge.ico')],
             'copyright':thgcopyright,
             'product_version':version}
            ]
    extra['windows'] = [
            {'script':'TortoiseHgOverlayServer.py',
             'icon_resources':[(0,'icons/thg_logo.ico')],
             'description':'TortoiseHg Overlay Icon Server',
             'copyright':thgcopyright,
             'product_version':version}
            ]

    return _scripts, _packages, _data_files, extra


def setup_posix():
    # Specific definitios for Posix installations
    _extra = {}
    _scripts = ['thg']
    _packages = ['tortoisehg', 'tortoisehg.hgqt', 'tortoisehg.util']
    _data_files = [(os.path.join('share/pixmaps/tortoisehg', root),
        [os.path.join(root, file_) for file_ in files])
        for root, dirs, files in os.walk('icons')]
    _data_files += [(os.path.join('share', root),
        [os.path.join(root, file_) for file_ in files])
        for root, dirs, files in os.walk('locale')]
    _data_files += [('lib/nautilus/extensions-2.0/python',
                     ['contrib/nautilus-thg.py'])]

    # Create a config.py.  Distributions will need to supply their own
    cfgfile = os.path.join('tortoisehg', 'util', 'config.py')
    if not os.path.exists(cfgfile) and not os.path.exists('.hg/requires'):
        f = open(cfgfile, "w")
        f.write('bin_path     = "/usr/bin"\n')
        f.write('license_path = "/usr/share/doc/tortoisehg/Copying.txt.gz"\n')
        f.write('locale_path  = "/usr/share/locale"\n')
        f.write('icon_path    = "/usr/share/pixmaps/tortoisehg/icons"\n')
        f.write('nofork       = True\n')
        f.close()

    return _scripts, _packages, _data_files, _extra

def runcmd(cmd, env):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=env)
    out, err = p.communicate()
    # If root is executing setup.py, but the repository is owned by
    # another user (as in "sudo python setup.py install") we will get
    # trust warnings since the .hg/hgrc file is untrusted. That is
    # fine, we don't want to load it anyway.
    err = [e for e in err.splitlines()
           if not e.startswith('Not trusting file')]
    if err:
        return ''
    return out

version = ''

if os.path.isdir('.hg'):
    from tortoisehg.util import version as _version
    branch, version = _version.liveversion()
    if version.endswith('+'):
        version += time.strftime('%Y%m%d')
elif os.path.exists('.hg_archival.txt'):
    kw = dict([t.strip() for t in l.split(':', 1)]
              for l in open('.hg_archival.txt'))
    if 'tag' in kw:
        version =  kw['tag']
    elif 'latesttag' in kw:
        version = '%(latesttag)s+%(latesttagdistance)s-%(node).12s' % kw
    else:
        version = kw.get('node', '')[:12]

if version:
    f = open("tortoisehg/util/__version__.py", "w")
    f.write('# this file is autogenerated by setup.py\n')
    f.write('version = "%s"\n' % version)
    f.close()

try:
    import tortoisehg.util.__version__
    version = tortoisehg.util.__version__.version
except ImportError:
    version = 'unknown'

if os.name == "nt":
    (scripts, packages, data_files, extra) = setup_windows(version)
    desc = 'Windows shell extension for Mercurial VCS'
    # Windows binary file versions for exe/dll files must have the
    # form W.X.Y.Z, where W,X,Y,Z are numbers in the range 0..65535
    from tortoisehg.util.version import package_version
    setupversion = package_version()
    productname = 'TortoiseHg'
else:
    (scripts, packages, data_files, extra) = setup_posix()
    desc = 'TortoiseHg dialogs for Mercurial VCS'
    setupversion = version
    productname = 'tortoisehg'

setup(name=productname,
        version=setupversion,
        author='Steve Borho',
        author_email='steve@borho.org',
        url='http://tortoisehg.org',
        description=desc,
        license='GNU GPL2',
        scripts=scripts,
        packages=packages,
        data_files=data_files,
        cmdclass=cmdclass,
        **extra
    )

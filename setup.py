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
from distutils.core import setup
from distutils.command.build import build
from distutils.spawn import spawn, find_executable


class build_mo(build):

    description = "build translations (.mo files)"

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

build.sub_commands.append(('build_mo', None))

cmdclass = {
        'build_mo': build_mo}

def setup_windows():
    # Specific definitios for Windows NT-alike installations
    _scripts = []
    _data_files = []
    _packages = ['tortoisehg.hgtk', 'tortoisehg.hgtk.logview',
                 'tortoisehg.util', 'tortoisehg']
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
           # This is one way to ensure that hgtk can find its icons when
           # running in a py2exe environment. It also makes debugging easier.
           "skip_archive" : 0,

           # Don't pull in all this MFC stuff used by the makepy UI.
           "excludes" : "pywin,pywin.dialogs,pywin.dialogs.list",
           "includes" : includes,
           "optimize" : 1
       }
    }
    extra['console'] = [
            {'script':'contrib/hg', 'icon_resources':[(0,'icons/hg.ico')]},
            {'script':'hgtk', 'icon_resources':[(0,'icons/thg_logo.ico')]}
            ]
    extra['windows'] = [
            {'script':'thgtaskbar.py',
             'icon_resources':[(0,'icons/thg_logo.ico')]}
            ]

    return _scripts, _packages, _data_files, extra


def setup_posix():
    # Specific definitios for Posix installations
    _extra = {}
    _scripts = ['hgtk']
    _packages = ['tortoisehg', 'tortoisehg.hgtk', 
                 'tortoisehg.hgtk.logview', 'tortoisehg.util']
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


if os.name == "nt":
    (scripts, packages, data_files, extra) = setup_windows()
    desc='Windows shell extension for Mercurial VCS'
else:
    (scripts, packages, data_files, extra) = setup_posix()
    desc='TortoiseHg dialogs for Mercurial VCS'

version = ''

try:
    l = os.popen('hg -R . id -i -t').read().split()
    while len(l) > 1 and l[-1][0].isalpha(): # remove non-numbered tags
        l.pop()
    if len(l) > 1: # tag found
        version = l[-1]
        if l[0].endswith('+'): # propagate the dirty status to the tag
            version += '+'
    elif len(l) == 1: # no tag found
        cmd = 'hg parents --template {latesttag}+{latesttagdistance}-'
        version = os.popen(cmd).read() + l[0]
    if version.endswith('+'):
        version += time.strftime('%Y%m%d')
except OSError:
    version = "unknown"

verfile = os.path.join('tortoisehg', 'util', '__version__.py')
if version != 'unknown' or not os.path.exists(verfile):
    f = file(verfile, "w")
    f.write('# this file is autogenerated by setup.py\n')
    f.write('version = "%s"\n' % version)
    f.close()
else:
    import tortoisehg.util.__version__
    version = tortoisehg.util.__version__.version

setup(name="tortoisehg",
        version=version,
        author='TK Soh',
        author_email='teekaysoh@gmail.com',
        url='http://bitbucket.org/tortoisehg/stable/',
        description=desc,
        license='GNU GPL2',
        scripts=scripts,
        packages=packages,
        data_files=data_files,
        cmdclass=cmdclass,
        **extra
    )

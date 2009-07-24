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

        podir = 'i18n'
        if not os.path.isdir(podir):
            self.warn("could not find %s/ directory" % podir)
            return

        join = os.path.join
        for po in os.listdir(podir):
            if not po.endswith('.po'):
                continue
            if not (po.find('tortoisehg-') == 0):
                self.warn("Found file '%s' that was not tortoisehg .po" % po)
                continue
            pofile = join(podir, po)
            modir = join('locale', po[11:-3], 'LC_MESSAGES')
            mofile = join(modir, 'tortoisehg.mo')
            cmd = ['msgfmt', '-v', '-o', mofile, pofile]
            if sys.platform != 'sunos5':
                # msgfmt on Solaris does not know about -c
                cmd.append('-c')
            self.mkpath(modir)
            self.make_file([pofile], mofile, spawn, (cmd,))
            self.distribution.data_files.append((join('tortoisehg', modir),
                                                 [mofile]))

build.sub_commands.append(('build_mo', None))

cmdclass = {
        'build_mo': build_mo}

def setup_windows():
    # Specific definitios for Windows NT-alike installations
    _scripts = []
    _data_files = []
    _packages = ['hggtk', 'hggtk.logview', 'thgutil']
    extra = {}
    hgextmods = []

    try: import py2exe
    except ImportError:
        if '--version' not in sys.argv:
            raise

    if 'py2exe' in sys.argv:
        # FIXME: quick hack to include installed hg extensions in py2exe binary
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
           "skip_archive" : 1,

           # Don't pull in all this MFC stuff used by the makepy UI.
           "excludes" : "pywin,pywin.dialogs,pywin.dialogs.list",

           # add library files to support PyGtk-based dialogs/windows
           # Note:
           #    after py2exe build, copy GTK's etc and lib directories into
           #    the dist directory created by py2exe.
           #    also needed is the GTK's share/themes (as dist/share/themes), 
           #    for dialogs to display in MS-Windows XP theme.
           "includes" : includes + list(hgextmods),
           "optimize" : 1
       }
    }

    return _scripts, _packages, _data_files, extra


def setup_posix():
    # Specific definitios for Posix installations
    _extra = {}
    _scripts = ['hgtk']
    _packages = ['hggtk', 'hggtk.logview', 'thgutil']
    _data_files = [(os.path.join('share/pixmaps/tortoisehg', root),
        [os.path.join(root, file_) for file_ in files])
        for root, dirs, files in os.walk('icons')]
    _data_files += [(os.path.join('share', root),
        [os.path.join(root, file_) for file_ in files])
        for root, dirs, files in os.walk('locale')]
    _data_files += [('lib/nautilus/extensions-2.0/python',
                     ['contrib/nautilus-thg.py'])]

    # Create a config.py.  Distributions will need to supply their own
    cfgfile = os.path.join('thgutil', 'config.py')
    if not os.path.exists(cfgfile) and not os.path.exists('.hg/requires'):
        f = open(cfgfile, "w")
        f.write('bin_path     = "/usr/bin"\n')
        f.write('license_path = "/usr/share/doc/tortoisehg/Copying.txt.gz"\n')
        f.write('locale_path  = "/usr/share/locale"\n')
        f.write('icon_path    = "/usr/share/pixmaps/tortoisehg/icons"\n')
        f.close()

    return _scripts, _packages, _data_files, _extra


if os.name == "nt":
    (scripts, packages, data_files, extra) = setup_windows()
    desc='Windows shell extension for Mercurial VCS'
else:
    (scripts, packages, data_files, extra) = setup_posix()
    desc='TortoiseHg dialogs for Mercurial VCS'

try:
    l = os.popen('hg -R . id -it').read().split()
    while len(l) > 1 and l[-1][0].isalpha(): # remove non-numbered tags
        l.pop()
    version = l and l[-1] or 'unknown' # latest tag or revision number
    if version.endswith('+'):
        version += time.strftime('%Y%m%d')
except OSError:
    version = "unknown"

verfile = os.path.join("thgutil", "__version__.py")
if version != 'unknown' or not os.path.exists(verfile):
    f = file(verfile, "w")
    f.write('# this file is autogenerated by setup.py\n')
    f.write('version = "%s"\n' % version)
    f.close()
else:
    import thgutil.__version__
    version = thgutil.__version__.version

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

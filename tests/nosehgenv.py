"""Nose plugin to set up test environment"""
import os, shutil, sys, tempfile
from nose import plugins
# don't import mercurial or tortoisehg before setting up test environment

class HgEnvPlugin(plugins.Plugin):
    """Set up temporary environment"""
    enabled = True
    name = 'hgenv'

    def options(self, parser, env):
        parser.add_option('--keep-tmpdir', action='store_true', default=False,
                          help='Keep temporary directory after running tests')
        parser.add_option('--tmpdir',
                          help=('Put temporary files in the given directory '
                                '(implies --keep-tmpdir)'))

    def configure(self, options, conf):
        self.keep_tmpdir = options.keep_tmpdir or bool(options.tmpdir)
        self.tmpdir = options.tmpdir

    def begin(self):
        if 'mercurial' in sys.modules:
            raise Exception('loaded mercurial module before setting up '
                            'test environment')
        self._setupsyspath()
        self._setuptmpdir()
        self._setuphgrc()
        self._setupmiscenv()

    def _setupsyspath(self):
        hgpath = os.environ.get('HGPATH')
        if hgpath:
            hgpath = os.path.abspath(hgpath)
            sys.path.insert(1, hgpath)
            os.environ['HGPATH'] = hgpath

        thgpath = os.environ.get('THGPATH')
        if not thgpath:
            thgpath = os.path.join(os.path.dirname(__file__), '..')
        thgpath = os.path.abspath(thgpath)
        sys.path.insert(1, thgpath)
        os.environ['THGPATH'] = thgpath

    def _setuptmpdir(self):
        if self.tmpdir:
            if os.path.exists(self.tmpdir):
                raise Exception('temp dir %r already exists' % self.tmpdir)
            os.makedirs(self.tmpdir)
        else:
            self.tmpdir = tempfile.mkdtemp('', 'thgtests.')
        os.environ['HGTMP'] = self.tmpdir

    def _setuphgrc(self):
        """Create a fresh hgrc for repeatable result"""
        os.environ['HGRCPATH'] = hgrcpath = os.path.join(self.tmpdir, '.hgrc')
        f = open(hgrcpath, 'w')
        try:
            f.write('[defaults]\n')
            f.write('backout = -d "0 0"\n')
            f.write('commit = -d "0 0"\n')
            f.write('tag = -d "0 0"\n')
        finally:
            f.close()

    def _setupmiscenv(self):
        """Reset some common environment variables for repeatable result"""
        os.environ['LANG'] = os.environ['LC_ALL'] = os.environ['LANGUAGE'] = 'C'
        os.environ['TZ'] = 'GMT'
        os.environ['HOME'] = self.tmpdir
        os.environ['APPDATA'] = self.tmpdir  # for QSettings on Windows
        os.environ['EMAIL'] = 'Foo Bar <foo.bar@example.com>'
        os.environ['http_proxy'] = ''
        os.environ['HGUSER'] = 'test'
        os.environ['HGENCODING'] = 'ascii'
        os.environ['HGENCODINGMODE'] = 'strict'

    def finalize(self, result):
        if not self.keep_tmpdir:
            # TODO: workaround for file lock problem on Windows
            # https://bitbucket.org/tortoisehg/thg/issue/1783/
            from tortoisehg.hgqt import thgrepo
            for e in thgrepo._repocache.itervalues():
                w = e._pyqtobj.watcher
                w.removePaths(w.directories())
                w.removePaths(w.files())

            shutil.rmtree(self.tmpdir)

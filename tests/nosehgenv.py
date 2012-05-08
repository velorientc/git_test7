"""Nose plugin to set up test environment"""
import os, shutil, tempfile
from nose import plugins

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
        self._setuptmpdir()

    def _setuptmpdir(self):
        if self.tmpdir:
            if os.path.exists(self.tmpdir):
                raise Exception('temp dir %r already exists' % self.tmpdir)
            os.makedirs(self.tmpdir)
        else:
            self.tmpdir = tempfile.mkdtemp('', 'thgtests.')
        os.environ['HGTMP'] = self.tmpdir

    def finalize(self, result):
        if not self.keep_tmpdir:
            shutil.rmtree(self.tmpdir)

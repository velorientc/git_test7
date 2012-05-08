"""Helper functions or classes imported from test case"""
import os, tempfile
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
from nose import tools
from mercurial import dispatch, ui as uimod
from tortoisehg.util import hglib

def mktmpdir(prefix):
    """Create temporary directory under HGTMP"""
    return tempfile.mkdtemp('', prefix, os.environ['HGTMP'])

# TODO: make this usable for unittest.TestCase?
def with_encoding(encoding, fallbackencoding=None):
    """Decorator for test function to change locale encoding temporarily"""
    orig_encoding = hglib._encoding
    orig_fallbackencoding = hglib._fallbackencoding

    def setenc():
        hglib._encoding = encoding
        hglib._fallbackencoding = fallbackencoding or encoding

    def restoreenc():
        hglib._encoding = orig_encoding
        hglib._fallbackencoding = orig_fallbackencoding

    return tools.with_setup(setenc, restoreenc)

class HgClient(object):
    """Mercurial client to set up fixture repository

    >>> hg = HgClient('/tmp/foo')
    >>> def dummydispatch(args):
    ...     print ' '.join(['hg'] + list(args))
    >>> hg._dispatch = dummydispatch

    >>> hg.init()
    hg init /tmp/foo/
    >>> hg.add('bar')
    hg add --cwd /tmp/foo bar
    >>> hg.commit('-m', 'add bar')
    hg commit --cwd /tmp/foo -m add bar

    >>> hg.wjoin('bar/baz')
    '/tmp/foo/bar/baz'
    >>> hg.wjoin('/absolute/path')
    Traceback (most recent call last):
      ...
    ValueError: not a relative path: /absolute/path
    """

    def __init__(self, path):
        self.path = os.path.abspath(path)

    def init(self, dest=None):
        """Create a new repository"""
        return self._dispatch(('init', self.wjoin(dest or '')))

    def __getattr__(self, name):
        """Return accessor for arbitrary Mercurial command"""
        def cmd(*args):
            return self._dispatch((name, '--cwd', self.path) + args)
        cmd.func_name = name
        return cmd

    def _dispatch(self, args):
        # TODO: use hglib in order to avoid pollution of global space?
        origwd = os.getcwd()
        ui = uimod.ui()
        ui.setconfig('ui', 'strict', True)
        ui.fout = StringIO.StringIO()
        ui.ferr = StringIO.StringIO()
        req = dispatch.request(list(args), ui=ui)
        try:
            result = dispatch._dispatch(req) or 0
            return result, ui.fout.getvalue(), ui.ferr.getvalue()
        finally:
            os.chdir(origwd)

    def ftouch(self, *paths):
        """Create empty file inside the repository"""
        for e in paths:
            fullpath = self.wjoin(e)
            if not os.path.exists(os.path.dirname(fullpath)):
                os.makedirs(os.path.dirname(fullpath))
            open(fullpath, 'w').close()

    def fwrite(self, path, content):
        """Write the given content to file"""
        f = open(self.wjoin(path), 'wb')
        try:
            f.write(content)
        finally:
            f.close()

    def fappend(self, path, content):
        """Append the given content to file"""
        f = open(self.wjoin(path), 'ab')
        try:
            f.write(content)
        finally:
            f.close()

    def fread(self, path):
        """Read content of file"""
        f = open(self.wjoin(path), 'rb')
        try:
            return f.read()
        finally:
            f.close()

    def wjoin(self, path):
        if path.startswith('/'):
            raise ValueError('not a relative path: %s' % path)
        return os.path.join(self.path, path)

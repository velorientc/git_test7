import os, tempfile, shutil
from nose.tools import *
from mercurial import ui, commands, error
from tortoisehg.util import hglib
from tortoisehg.hgqt import thgrepo

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')

def setup():
    global _tempdir, _reposdir
    _tempdir = tempfile.mkdtemp()
    _reposdir = os.path.join(_tempdir, 'repos')
    os.mkdir(_reposdir)

def teardown():
    shutil.rmtree(_tempdir)


def create_fixture_repo(name, dirname=None):
    """Create the fixture repo and return thgrepo object"""
    path = os.path.join(_reposdir, dirname or name)
    repo = thgrepo.repository(ui.ui(), path, create=True)
    commands.import_(repo.ui, repo, os.path.join(FIXTURES_DIR, name + '.diff'),
                     base='', strip=1, exact=True)
    return repo

def get_fixture_repo(name):
    """Return the thgrepo object for the specified fixture repo"""
    path = os.path.join(_reposdir, name)
    try:
        return thgrepo.repository(ui.ui(), path)
    except error.RepoError:
        return create_fixture_repo(name)


def with_encoding(encoding, fallbackencoding=None):
    """Change locale encoding temporarily"""
    orig_encoding = hglib._encoding
    orig_fallbackencoding = hglib._fallbackencoding

    def setenc():
        hglib._encoding = encoding
        hglib._fallbackencoding = fallbackencoding or encoding

    def restoreenc():
        hglib._encoding = orig_encoding
        hglib._fallbackencoding = orig_fallbackencoding

    return with_setup(setenc, restoreenc)

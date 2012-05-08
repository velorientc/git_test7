"""Helper functions or classes imported from test case"""
import os, tempfile
from nose import tools
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

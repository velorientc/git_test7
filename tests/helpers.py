"""Helper functions or classes imported from test case"""
import os, tempfile

def mktmpdir(prefix):
    """Create temporary directory under HGTMP"""
    return tempfile.mkdtemp('', prefix, os.environ['HGTMP'])

import os, tempfile, shutil
from nose.tools import *
from mercurial import ui, commands, error
from tortoisehg.util import hglib
from tortoisehg.hgqt import thgrepo

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')

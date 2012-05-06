import os
from nose.tools import *
from mercurial import node
from tortoisehg.hgqt.repotreemodel import *

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')

def openfixture(name, mode=QIODevice.ReadOnly):
    path = os.path.join(FIXTURES_DIR, name)
    f = QFile(path)
    f.open(mode)
    return f

def test_iterrepoitemfromxml():
    f = openfixture('reporegistry.xml')
    repos = list(iterRepoItemFromXml(f))
    f.close()
    assert_equals(['/thg', '/mercurial', '/python-vcs'],
                  map(lambda e: e.rootpath(), repos))
    assert_equals('thg', repos[0].shortname())
    assert_equals('bac32db38e52fd49acb62b94730a55f4f4b0cdee',
                  node.hex(repos[0].basenode()))

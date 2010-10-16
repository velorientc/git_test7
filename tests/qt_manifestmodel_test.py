from nose.tools import *
from PyQt4.QtCore import QModelIndex, QString
from tortoisehg.hgqt.manifestmodel import ManifestModel
from tests import get_fixture_repo, with_encoding

_aloha_ja = u'\u3042\u308d\u306f\u30fc'

def setup():
    global _repos
    _repos = {}
    for name in ('subdirs', 'euc-jp-path'):
        _repos[name] = get_fixture_repo(name)

def newmodel(name='subdirs', rev=0):
    return ManifestModel(_repos[name], rev=rev)

def test_data():
    m = newmodel()
    assert_equals('bar', m.data(m.index(1, 0)))
    assert_equals('baz', m.data(m.index(0, 0)))
    assert_equals('foo', m.data(m.index(2, 0)))

def test_data_subdir():
    m = newmodel()
    assert_equals('bax', m.data(m.index(0, 0, m.index(0, 0))))
    assert_equals('box', m.data(m.index(1, 0, m.index(0, 0))))

def test_data_inexistent():
    m = newmodel()
    assert_equals(None, m.data(QModelIndex()))
    assert_equals(None, m.data(m.index(0, 0, m.index(1, 0))))

@with_encoding('euc-jp')
def test_data_eucjp():
    m = newmodel(name='euc-jp-path')
    assert_equals(_aloha_ja, m.data(m.index(0, 0)))

def test_isdir():
    m = newmodel()
    assert m.isDir(m.indexFromPath(''))
    assert m.isDir(m.indexFromPath('baz'))
    assert not m.isDir(m.indexFromPath('foo'))

def test_rowcount():
    m = newmodel()
    assert_equals(3, m.rowCount())

def test_rowcount_subdirs():
    m = newmodel()
    assert_equals(2, m.rowCount(m.index(0, 0)))

def test_rowcount_invalid():
    m = newmodel()
    assert_equals(0, m.rowCount(m.index(1, 0)))

def test_pathfromindex():
    m = newmodel()
    assert_equals('', m.filePath(QModelIndex()))
    assert_equals('bar', m.filePath(m.index(1, 0)))
    assert_equals('baz', m.filePath(m.index(0, 0)))
    assert_equals('baz/bax', m.filePath(m.index(0, 0, m.index(0, 0))))

@with_encoding('euc-jp')
def test_pathfromindex_eucjp():
    m = newmodel(name='euc-jp-path')
    assert_equals(_aloha_ja, m.filePath(m.index(0, 0)))

def test_indexfrompath():
    m = newmodel()
    assert_equals(QModelIndex(), m.indexFromPath(''))
    assert_equals(m.index(1, 0), m.indexFromPath('bar'))
    assert_equals(m.index(0, 0), m.indexFromPath('baz'))
    assert_equals(m.index(0, 0, m.index(0, 0)), m.indexFromPath('baz/bax'))

def test_indexfrompath_qstr():
    m = newmodel()
    assert_equals(m.index(1, 0), m.indexFromPath(QString('bar')))

@with_encoding('euc-jp')
def test_indexfrompath_eucjp():
    m = newmodel(name='euc-jp-path')
    assert_equals(m.index(0, 0), m.indexFromPath(_aloha_ja))

def test_removed_should_be_listed():
    m = newmodel(rev=1)
    m.setStatusFilter('MARC')
    assert m.indexFromPath('baz/box').isValid()

def test_status_role():
    m = newmodel(rev=0)
    assert_equals('A', m.data(m.indexFromPath('foo'),
                                  role=ManifestModel.StatusRole))

    m = newmodel(rev=1)
    m.setStatusFilter('MARC')
    assert_equals('C', m.data(m.indexFromPath('foo'),
                              role=ManifestModel.StatusRole))
    assert_equals('R', m.data(m.indexFromPath('baz/box'),
                              role=ManifestModel.StatusRole))

def test_status_role_invalid():
    m = newmodel()
    assert_equals(None, m.data(QModelIndex(),
                               role=ManifestModel.StatusRole))

def test_status_filter_modified():
    m = newmodel(rev=1)
    m.setStatusFilter('M')
    assert_not_equals(QModelIndex(), m.indexFromPath('bar'))  # modified
    assert_equals(QModelIndex(), m.indexFromPath('zzz'))  # added
    assert_equals(QModelIndex(), m.indexFromPath('baz/box'))  # removed
    assert_equals(QModelIndex(), m.indexFromPath('foo'))  # clean

def test_status_filter_added():
    m = newmodel(rev=1)
    m.setStatusFilter('A')
    assert_equals(QModelIndex(), m.indexFromPath('bar'))  # modified
    assert_not_equals(QModelIndex(), m.indexFromPath('zzz'))  # added
    assert_equals(QModelIndex(), m.indexFromPath('baz/box'))  # removed
    assert_equals(QModelIndex(), m.indexFromPath('foo'))  # clean

def test_status_filter_removed():
    m = newmodel(rev=1)
    m.setStatusFilter('R')
    assert_equals(QModelIndex(), m.indexFromPath('bar'))  # modified
    assert_equals(QModelIndex(), m.indexFromPath('zzz'))  # added
    assert_not_equals(QModelIndex(), m.indexFromPath('baz/box'))  # removed
    assert_equals(QModelIndex(), m.indexFromPath('foo'))  # clean

def test_status_filter_clean():
    m = newmodel(rev=1)
    m.setStatusFilter('C')
    assert_equals(QModelIndex(), m.indexFromPath('bar'))  # modified
    assert_equals(QModelIndex(), m.indexFromPath('zzz'))  # added
    assert_equals(QModelIndex(), m.indexFromPath('baz/box'))  # removed
    assert_not_equals(QModelIndex(), m.indexFromPath('foo'))  # clean

def test_status_filter_change():
    m = newmodel(rev=1)
    m.setStatusFilter('C')
    assert_equals(QModelIndex(), m.indexFromPath('bar'))  # modified
    assert_not_equals(QModelIndex(), m.indexFromPath('foo'))  # clean

    m.setStatusFilter('M')
    assert_not_equals(QModelIndex(), m.indexFromPath('bar'))  # modified
    assert_equals(QModelIndex(), m.indexFromPath('foo'))  # clean

def test_status_filter_multi():
    m = newmodel(rev=1)
    m.setStatusFilter('MC')
    assert_not_equals(QModelIndex(), m.indexFromPath('bar'))  # modified
    assert_equals(QModelIndex(), m.indexFromPath('zzz'))  # added
    assert_equals(QModelIndex(), m.indexFromPath('baz/box'))  # removed
    assert_not_equals(QModelIndex(), m.indexFromPath('foo'))  # clean

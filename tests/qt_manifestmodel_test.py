import os
from nose.tools import *
from nose.plugins.skip import SkipTest
from PyQt4.QtCore import QModelIndex, QString
from tortoisehg.hgqt import thgrepo
from tortoisehg.hgqt.manifestmodel import ManifestModel

import helpers

_aloha_ja = u'\u3042\u308d\u306f\u30fc'

def setup():
    global _repos
    _repos = {}

    tmpdir = helpers.mktmpdir(__name__)

    hg = helpers.HgClient(os.path.join(tmpdir, 'subdirs'))
    hg.init()
    hg.ftouch('foo', 'bar', 'baz/bax', 'baz/box')
    hg.addremove()
    hg.commit('-m', 'foobar')
    hg.fwrite('bar', 'hello\n')
    hg.remove('baz/box')
    hg.ftouch('zzz')
    hg.addremove()
    hg.commit('-m', 'remove baz/box, add zzz, modify bar')
    _repos['subdirs'] = thgrepo.repository(path=hg.path)

    hg = helpers.HgClient(os.path.join(tmpdir, 'euc-jp-path'))
    hg.init()
    hg.ftouch(_aloha_ja.encode('euc-jp'))
    hg.addremove()
    hg.commit('-m', 'add aloha')
    _repos['euc-jp-path'] = thgrepo.repository(path=hg.path)

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

@helpers.with_encoding('euc-jp')
def test_data_eucjp():
    if os.name != 'posix':
        raise SkipTest
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

@helpers.with_encoding('euc-jp')
def test_pathfromindex_eucjp():
    if os.name != 'posix':
        raise SkipTest
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

@helpers.with_encoding('euc-jp')
def test_indexfrompath_eucjp():
    if os.name != 'posix':
        raise SkipTest
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

def test_name_filter():
    m = newmodel()
    m.setNameFilter('ax')
    assert not m.indexFromPath('bar').isValid()
    assert m.indexFromPath('baz/bax').isValid()
    assert not m.indexFromPath('baz/box').isValid()
    assert not m.indexFromPath('foo').isValid()

def test_name_filter_glob():
    m = newmodel()
    m.setNameFilter('b*x')
    assert not m.indexFromPath('bar').isValid()
    assert m.indexFromPath('baz/bax').isValid()
    assert m.indexFromPath('baz/box').isValid()
    assert not m.indexFromPath('foo').isValid()

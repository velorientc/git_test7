from nose.tools import *
from PyQt4.QtCore import QModelIndex
from tortoisehg.hgqt.manifestmodel import ManifestModel
from tests import get_fixture_repo

def setup():
    global _repo
    _repo = get_fixture_repo('subdirs')

def newmodel():
    return ManifestModel(_repo, rev=0)

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
    assert_equals('', m.pathFromIndex(QModelIndex()))
    assert_equals('bar', m.pathFromIndex(m.index(1, 0)))
    assert_equals('baz', m.pathFromIndex(m.index(0, 0)))
    assert_equals('baz/bax', m.pathFromIndex(m.index(0, 0, m.index(0, 0))))

def test_indexfrompath():
    m = newmodel()
    assert_equals(QModelIndex(), m.indexFromPath(''))
    assert_equals(m.index(1, 0), m.indexFromPath('bar'))
    assert_equals(m.index(0, 0), m.indexFromPath('baz'))
    assert_equals(m.index(0, 0, m.index(0, 0)), m.indexFromPath('baz/bax'))

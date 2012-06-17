import os, sys, unittest
from nose.plugins.skip import SkipTest
from PyQt4.QtCore import QModelIndex, QString
from PyQt4.QtGui import QApplication
from tortoisehg.hgqt import thgrepo
from tortoisehg.hgqt.manifestmodel import ManifestModel

import helpers

def setup():
    # necessary for style().standardIcon()
    if QApplication.type() != QApplication.GuiClient:
        raise SkipTest

    global _tmpdir
    _tmpdir = helpers.mktmpdir(__name__)

class ManifestModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        hg = helpers.HgClient(os.path.join(_tmpdir, cls.__name__))
        hg.init()
        hg.ftouch('foo', 'bar', 'baz/bax', 'baz/box')
        hg.addremove()
        hg.commit('-m', 'foobar')
        hg.fwrite('bar', 'hello\n')
        hg.remove('baz/box')
        hg.ftouch('zzz')
        hg.addremove()
        hg.commit('-m', 'remove baz/box, add zzz, modify bar')
        cls.repo = thgrepo.repository(path=hg.path)

    @classmethod
    def tearDownClass(cls):
        del cls.repo

    def test_data(self):
        m = ManifestModel(self.repo, rev=0)
        self.assertEqual('bar', m.data(m.index(1, 0)))
        self.assertEqual('baz', m.data(m.index(0, 0)))
        self.assertEqual('foo', m.data(m.index(2, 0)))

    def test_data_subdir(self):
        m = ManifestModel(self.repo, rev=0)
        self.assertEqual('bax', m.data(m.index(0, 0, m.index(0, 0))))
        self.assertEqual('box', m.data(m.index(1, 0, m.index(0, 0))))

    def test_data_inexistent(self):
        m = ManifestModel(self.repo, rev=0)
        self.assertEqual(None, m.data(QModelIndex()))
        self.assertEqual(None, m.data(m.index(0, 0, m.index(1, 0))))

    def test_isdir(self):
        m = ManifestModel(self.repo, rev=0)
        self.assertTrue(m.isDir(m.indexFromPath('')))
        self.assertTrue(m.isDir(m.indexFromPath('baz')))
        self.assertFalse(m.isDir(m.indexFromPath('foo')))

    def test_rowcount(self):
        m = ManifestModel(self.repo, rev=0)
        self.assertEqual(3, m.rowCount())

    def test_rowcount_subdirs(self):
        m = ManifestModel(self.repo, rev=0)
        self.assertEqual(2, m.rowCount(m.index(0, 0)))

    def test_rowcount_invalid(self):
        m = ManifestModel(self.repo, rev=0)
        self.assertEqual(0, m.rowCount(m.index(1, 0)))

    def test_pathfromindex(self):
        m = ManifestModel(self.repo, rev=0)
        self.assertEqual('', m.filePath(QModelIndex()))
        self.assertEqual('bar', m.filePath(m.index(1, 0)))
        self.assertEqual('baz', m.filePath(m.index(0, 0)))
        self.assertEqual('baz/bax', m.filePath(m.index(0, 0, m.index(0, 0))))

    def test_indexfrompath(self):
        m = ManifestModel(self.repo, rev=0)
        self.assertEqual(QModelIndex(), m.indexFromPath(''))
        self.assertEqual(m.index(1, 0), m.indexFromPath('bar'))
        self.assertEqual(m.index(0, 0), m.indexFromPath('baz'))
        self.assertEqual(m.index(0, 0, m.index(0, 0)),
                         m.indexFromPath('baz/bax'))

    def test_indexfrompath_qstr(self):
        m = ManifestModel(self.repo, rev=0)
        self.assertEqual(m.index(1, 0), m.indexFromPath(QString('bar')))

    def test_removed_should_be_listed(self):
        m = ManifestModel(self.repo, rev=1)
        m.setStatusFilter('MARC')
        self.assertTrue(m.indexFromPath('baz/box').isValid())

    def test_status_role(self):
        m = ManifestModel(self.repo, rev=0)
        self.assertEqual('A', m.data(m.indexFromPath('foo'),
                                     role=ManifestModel.StatusRole))

        m = ManifestModel(self.repo, rev=1)
        m.setStatusFilter('MARC')
        self.assertEqual('C', m.data(m.indexFromPath('foo'),
                                     role=ManifestModel.StatusRole))
        self.assertEqual('R', m.data(m.indexFromPath('baz/box'),
                                     role=ManifestModel.StatusRole))

    def test_status_role_invalid(self):
        m = ManifestModel(self.repo, rev=0)
        self.assertEqual(None, m.data(QModelIndex(),
                                      role=ManifestModel.StatusRole))

    def test_status_filter_modified(self):
        m = ManifestModel(self.repo, rev=1)
        m.setStatusFilter('M')
        self.assertNotEqual(QModelIndex(), m.indexFromPath('bar'))  # modified
        self.assertEqual(QModelIndex(), m.indexFromPath('zzz'))  # added
        self.assertEqual(QModelIndex(), m.indexFromPath('baz/box'))  # removed
        self.assertEqual(QModelIndex(), m.indexFromPath('foo'))  # clean

    def test_status_filter_added(self):
        m = ManifestModel(self.repo, rev=1)
        m.setStatusFilter('A')
        self.assertEqual(QModelIndex(), m.indexFromPath('bar'))  # modified
        self.assertNotEqual(QModelIndex(), m.indexFromPath('zzz'))  # added
        self.assertEqual(QModelIndex(), m.indexFromPath('baz/box'))  # removed
        self.assertEqual(QModelIndex(), m.indexFromPath('foo'))  # clean

    def test_status_filter_removed(self):
        m = ManifestModel(self.repo, rev=1)
        m.setStatusFilter('R')
        self.assertEqual(QModelIndex(), m.indexFromPath('bar'))  # modified
        self.assertEqual(QModelIndex(), m.indexFromPath('zzz'))  # added
        self.assertNotEqual(QModelIndex(), m.indexFromPath('baz/box'))  # removed
        self.assertEqual(QModelIndex(), m.indexFromPath('foo'))  # clean

    def test_status_filter_clean(self):
        m = ManifestModel(self.repo, rev=1)
        m.setStatusFilter('C')
        self.assertEqual(QModelIndex(), m.indexFromPath('bar'))  # modified
        self.assertEqual(QModelIndex(), m.indexFromPath('zzz'))  # added
        self.assertEqual(QModelIndex(), m.indexFromPath('baz/box'))  # removed
        self.assertNotEqual(QModelIndex(), m.indexFromPath('foo'))  # clean

    def test_status_filter_change(self):
        m = ManifestModel(self.repo, rev=1)
        m.setStatusFilter('C')
        self.assertEqual(QModelIndex(), m.indexFromPath('bar'))  # modified
        self.assertNotEqual(QModelIndex(), m.indexFromPath('foo'))  # clean

        m.setStatusFilter('M')
        self.assertNotEqual(QModelIndex(), m.indexFromPath('bar'))  # modified
        self.assertEqual(QModelIndex(), m.indexFromPath('foo'))  # clean

    def test_status_filter_multi(self):
        m = ManifestModel(self.repo, rev=1)
        m.setStatusFilter('MC')
        self.assertNotEqual(QModelIndex(), m.indexFromPath('bar'))  # modified
        self.assertEqual(QModelIndex(), m.indexFromPath('zzz'))  # added
        self.assertEqual(QModelIndex(), m.indexFromPath('baz/box'))  # removed
        self.assertNotEqual(QModelIndex(), m.indexFromPath('foo'))  # clean

    def test_name_filter(self):
        m = ManifestModel(self.repo, rev=0)
        m.setNameFilter('ax')
        self.assertFalse(m.indexFromPath('bar').isValid())
        self.assertTrue(m.indexFromPath('baz/bax').isValid())
        self.assertFalse(m.indexFromPath('baz/box').isValid())
        self.assertFalse(m.indexFromPath('foo').isValid())

    def test_name_filter_glob(self):
        m = ManifestModel(self.repo, rev=0)
        m.setNameFilter('b*x')
        self.assertFalse(m.indexFromPath('bar').isValid())
        self.assertTrue(m.indexFromPath('baz/bax').isValid())
        self.assertTrue(m.indexFromPath('baz/box').isValid())
        self.assertFalse(m.indexFromPath('foo').isValid())


_aloha_ja = u'\u3042\u308d\u306f\u30fc'

class ManifestModelEucjpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # TODO: make this compatible with binary-unsafe filesystem
        if os.name != 'posix' or sys.platform == 'darwin':
            raise SkipTest
        cls.encodingpatch = helpers.patchencoding('euc-jp')

        # include non-ascii char in repo path to test concatenation
        hg = helpers.HgClient(os.path.join(
            _tmpdir, cls.__name__ + _aloha_ja.encode('euc-jp')))
        hg.init()
        hg.ftouch(_aloha_ja.encode('euc-jp'))
        hg.ftouch(_aloha_ja.encode('euc-jp') + '.txt')
        hg.addremove()
        hg.commit('-m', 'add aloha')
        cls.repo = thgrepo.repository(path=hg.path)

    @classmethod
    def tearDownClass(cls):
        del cls.repo
        cls.encodingpatch.restore()

    def test_data(self):
        m = ManifestModel(self.repo, rev=0)
        self.assertEqual(_aloha_ja, m.data(m.index(0, 0)))

    def test_pathfromindex(self):
        m = ManifestModel(self.repo, rev=0)
        self.assertEqual(_aloha_ja, m.filePath(m.index(0, 0)))

    def test_indexfrompath(self):
        m = ManifestModel(self.repo, rev=0)
        self.assertEqual(m.index(0, 0), m.indexFromPath(_aloha_ja))

    def test_fileicon_path_concat(self):
        m = ManifestModel(self.repo, rev=0)
        m.fileIcon(m.indexFromPath(_aloha_ja + '.txt'))  # no unicode error

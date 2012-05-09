import mock, unittest
from nose.plugins.skip import SkipTest
from PyQt4.QtGui import QApplication
from tortoisehg.hgqt import sync, thgrepo
from tortoisehg.util import wconfig

import helpers

class SyncSaveDialogTest(unittest.TestCase):
    def setUp(self):
        self.app = QApplication([])
        self.repo = None  # use mock instead?

    def tearDown(self):
        del self.app

    def test_clearcb_save(self):
        origurl = 'http://foo:bar@example.org/baz'
        safeurl = 'http://foo:***@example.org/baz'
        cleanurl = 'http://example.org/baz'
        dlg = sync.SaveDialog(self.repo, 'default', origurl, safeurl,
                              parent=None, edit=False)
        self.assertTrue(dlg.clearcb.isChecked())
        self.assertEqual(cleanurl, dlg.urllabel.text())

        dlg.clearcb.setChecked(False)
        self.assertEqual(safeurl, dlg.urllabel.text())

    def test_clearcb_not_exist_on_save_noauth(self):
        url = 'http://example.org/'
        dlg = sync.SaveDialog(self.repo, 'default', url, url, parent=None,
                              edit=False)
        self.assertEqual(None, dlg.clearcb, 'no clearcb checkbox')
        self.assertEqual(url, dlg.urllabel.text())

    def test_clearcb_not_exist_on_edit(self):
        url = 'http://foo:bar@example.org/'
        dlg = sync.SaveDialog(self.repo, 'default', url, url, parent=None,
                              edit=True)
        self.assertEqual(None, dlg.clearcb, 'no clearcb checkbox')
        self.assertEqual(url, dlg.urlentry.text())

class SyncSaveDialogWriteTest(unittest.TestCase):
    def setUp(self):
        if not hasattr(wconfig.config(), 'write'):
            raise SkipTest
        self.app = QApplication([])
        self.hg = helpers.HgClient(helpers.mktmpdir(__name__))
        self.hg.init()

    def tearDown(self):
        del self.app

    def test_save_new(self):
        url = 'http://example.org/'
        repo = thgrepo.repository(path=self.hg.path)
        dlg = sync.SaveDialog(repo, 'default', url, url, parent=None,
                              edit=False)
        dlg.accept()
        self.assertEqual(['[paths]', 'default = %s' % url],
                         self.hg.fread('.hg/hgrc').splitlines()[-2:])

    @mock.patch('tortoisehg.hgqt.qtlib.QuestionMsgBox', return_value=True)
    def test_save_unchanged(self, mock_msgbox):
        url = 'http://example.org/'
        self.hg.fwrite('.hg/hgrc', '[paths]\ndefault = %s\n' % url)
        repo = thgrepo.repository(path=self.hg.path)
        dlg = sync.SaveDialog(repo, 'default', url, url, parent=None,
                              edit=False)
        dlg.accept()
        self.assertEqual(['[paths]', 'default = %s' % url],
                         self.hg.fread('.hg/hgrc').splitlines()[-2:])

    def test_save_new_alias(self):
        url = 'http://example.org/'
        self.hg.fwrite('.hg/hgrc', '[paths]\ndefault = %s\n' % url)
        repo = thgrepo.repository(path=self.hg.path)
        dlg = sync.SaveDialog(repo, 'default', url, url, parent=None,
                              edit=False)
        dlg.aliasentry.setText('default-push')
        dlg.accept()
        self.assertEqual(['[paths]', 'default = %s' % url,
                          'default-push = %s' % url],
                         self.hg.fread('.hg/hgrc').splitlines()[-3:])

    def test_edit_alias(self):
        url = 'http://example.org/'
        self.hg.fwrite('.hg/hgrc', '[paths]\ndefault = %s\n' % url)
        repo = thgrepo.repository(path=self.hg.path)
        dlg = sync.SaveDialog(repo, 'default', url, url, parent=None,
                              edit=True)
        dlg.aliasentry.setText('default-push')
        dlg.accept()
        self.assertEqual(['[paths]', 'default-push = %s' % url],
                         self.hg.fread('.hg/hgrc').splitlines()[-2:])

    @mock.patch('tortoisehg.hgqt.qtlib.QuestionMsgBox', return_value=True)
    def test_edit_url(self, mock_msgbox):
        origurl = 'http://example.org/'
        newurl = 'http://example.org/new/'
        self.hg.fwrite('.hg/hgrc', '[paths]\ndefault = %s\n' % origurl)
        repo = thgrepo.repository(path=self.hg.path)
        dlg = sync.SaveDialog(repo, 'default', origurl, origurl, parent=None,
                              edit=True)
        dlg.urlentry.setText(newurl)
        dlg.accept()
        self.assertEqual(['[paths]', 'default = %s' % newurl],
                         self.hg.fread('.hg/hgrc').splitlines()[-2:])

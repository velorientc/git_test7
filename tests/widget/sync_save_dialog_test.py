import unittest
from PyQt4.QtGui import QApplication
from tortoisehg.hgqt import sync

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

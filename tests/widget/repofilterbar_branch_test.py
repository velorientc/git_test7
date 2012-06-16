import mock, os, unittest
from tortoisehg.hgqt import qtlib, repofilter, thgrepo

import helpers

def setup():
    global _tmpdir
    _tmpdir = helpers.mktmpdir(__name__)

def _listitems(combo):
    return [unicode(combo.itemText(i)) for i in xrange(combo.count())]

class RepoFilterBarBranchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        hg = helpers.HgClient(os.path.join(_tmpdir, cls.__name__))
        hg.init()
        hg.ftouch('a')
        hg.addremove()
        hg.commit('-m', 'commit to default')
        for name in ('foo', 'bar', 'baz'):
            hg.update('0')
            hg.fappend('a', name + '\n')
            hg.branch(name)
            hg.commit('-m', 'create %s branch' % name)
        hg.commit('--close-branch', '-m', 'close baz branch')
        cls.repo = thgrepo.repository(path=hg.path)

    @classmethod
    def tearDownClass(cls):
        del cls.repo

    def setUp(self):
        qtlib.initfontcache(self.repo.ui)
        self.widget = repofilter.RepoFilterBar(self.repo)
        self.branchchanged = mock.Mock()
        self.widget.branchChanged.connect(self.branchchanged)
        # without show(), action.setChecked() sometimes fails with
        # "illegal hardware instruction"
        self.widget.show()

    def tearDown(self):
        del self.widget
        qtlib._fontcache.clear()

    def test_open_branches(self):
        self.assertEqual([self.widget._allBranchesLabel,
                          'default', 'bar', 'foo'],
                         _listitems(self.widget._branchCombo))
        self.assertTrue(self.widget._branchCombo.isEnabled())
        self.assertFalse(self.branchchanged.called)

    def test_only_active_branches(self):
        self.widget._abranchAction.setChecked(False)
        self.widget._abranchAction.trigger()  # checked
        self.assertEqual([self.widget._allBranchesLabel,
                          'bar', 'foo'],
                         _listitems(self.widget._branchCombo))
        self.assertTrue(self.widget._branchCombo.isEnabled())
        self.assertFalse(self.branchchanged.called)

    def test_include_closed_branches(self):
        self.widget._cbranchAction.setChecked(False)
        self.widget._cbranchAction.trigger()  # checked
        self.assertEqual([self.widget._allBranchesLabel,
                          'default', 'bar', 'baz', 'foo'],
                         _listitems(self.widget._branchCombo))
        self.assertTrue(self.widget._branchCombo.isEnabled())
        self.assertFalse(self.branchchanged.called)

    def test_change_branch(self):
        self.widget.setBranch('foo')
        self.assertEqual('foo', self.widget.branch())
        self.branchchanged.assert_called_once_with('foo', False)

class RepoFilterBarEmptyBranchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        hg = helpers.HgClient(os.path.join(_tmpdir, cls.__name__))
        hg.init()
        hg.ftouch('a')
        hg.addremove()
        hg.commit('-m', 'commit to default')
        hg.commit('--close-branch', '-m', 'close default branch')
        hg.branch('foo')
        hg.commit('-m', 'create foo branch')
        cls.repo = thgrepo.repository(path=hg.path)

    @classmethod
    def tearDownClass(cls):
        del cls.repo

    def setUp(self):
        qtlib.initfontcache(self.repo.ui)
        self.widget = repofilter.RepoFilterBar(self.repo)
        # without show(), action.setChecked() sometimes fails with
        # "illegal hardware instruction"
        self.widget.show()

    def tearDown(self):
        del self.widget
        qtlib._fontcache.clear()

    def test_empty_branch_combo_is_disabled(self):
        self.assertFalse(self.widget._branchCombo.isEnabled())

    def test_branch_combo_enabled_if_closed_branches_included(self):
        self.widget._cbranchAction.setChecked(False)
        self.widget._cbranchAction.trigger()  # checked
        self.assertTrue(self.widget._branchCombo.isEnabled())

import mock, unittest
from mercurial import ui
from tortoisehg.hgqt import thgrepo

def mockrepo(ui, path):
    m = mock.MagicMock(ui=ui, root=path)
    m.unfiltered = lambda: m
    return m

LOCAL_SIGNALS = ['repositoryOpened', 'repositoryClosed']
MAPPED_SIGNALS = ['configChanged', 'repositoryChanged', 'repositoryDestroyed']

class RepoManagerMockedTest(unittest.TestCase):
    def setUp(self):
        self.hgrepopatcher = mock.patch('mercurial.hg.repository', new=mockrepo)
        self.watcherpatcher = mock.patch('tortoisehg.hgqt.thgrepo.RepoWatcher')
        self.hgrepopatcher.start()
        self.watcherpatcher.start()
        self.repoman = thgrepo.RepoManager(ui.ui())

        for signame in LOCAL_SIGNALS + MAPPED_SIGNALS:
            slot = mock.Mock()
            setattr(self, signame, slot)
            getattr(self.repoman, signame).connect(slot)

    def tearDown(self):
        self.watcherpatcher.stop()
        self.hgrepopatcher.stop()
        thgrepo._repocache.clear()

    def test_cached(self):
        a1 = self.repoman.openRepoAgent('/a')
        a2 = self.repoman.openRepoAgent('/a')
        self.assertTrue(a1 is a2)

    def test_release(self):
        self.repoman.openRepoAgent('/a')
        self.repoman.openRepoAgent('/a')

        self.repoman.releaseRepoAgent('/a')
        self.assertTrue(self.repoman.repoAgent('/a'))

        self.repoman.releaseRepoAgent('/a')
        self.assertFalse(self.repoman.repoAgent('/a'))

    def test_signal_map(self):
        a = self.repoman.openRepoAgent('/a')
        for signame in MAPPED_SIGNALS:
            getattr(a, signame).emit()
            getattr(self, signame).assert_called_once_with('/a')

    def test_disconnect_signal_on_close(self):
        a = self.repoman.openRepoAgent('/a')
        self.repoman.releaseRepoAgent('/a')
        for signame in MAPPED_SIGNALS:
            getattr(a, signame).emit()
            self.assertFalse(getattr(self, signame).called)

    def test_opened_signal(self):
        self.repoman.repositoryOpened.connect(
            lambda: self.assertTrue(self.repoman.repoAgent('/a')))
        self.repoman.openRepoAgent('/a')
        self.repositoryOpened.assert_called_once_with('/a')
        self.repositoryOpened.reset_mock()
        # emitted only if repository is actually instantiated (i.e. not cached)
        self.repoman.openRepoAgent('/a')
        self.assertFalse(self.repositoryOpened.called)

    def test_closed_signal(self):
        self.repoman.repositoryClosed.connect(
            lambda: self.assertFalse(self.repoman.repoAgent('/a')))
        self.repoman.openRepoAgent('/a')
        self.repoman.openRepoAgent('/a')
        self.repoman.releaseRepoAgent('/a')
        self.assertFalse(self.repositoryClosed.called)
        self.repoman.releaseRepoAgent('/a')
        self.repositoryClosed.assert_called_once_with('/a')

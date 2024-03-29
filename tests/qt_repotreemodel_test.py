from PyQt4.QtCore import QByteArray, QBuffer, QIODevice
from nose.tools import *
from mercurial import node
from tortoisehg.hgqt import repotreemodel, repotreeitem

def with_qbuffer(data='', mode=QIODevice.ReadOnly):
    def decorate(func):
        def newfunc():
            ba = QByteArray(data)  # keep reference to avoid GC
            f = QBuffer(ba)
            f.open(mode)
            try:
                func(f)
            finally:
                f.close()
        return make_decorator(func)(newfunc)
    return decorate

full_data = r'''<?xml version="1.0" encoding="UTF-8"?>
<reporegistry>
  <treeitem>
    <allgroup name="default">
      <repo root="/thg" shortname="thg" basenode="bac32db38e52fd49acb62b94730a55f4f4b0cdee"/>
      <repo root="/mercurial" shortname="hg" basenode="9117c6561b0bd7792fa13b50d28239d51b78e51f"/>
      <subrepo root="/subroot/sub" shortname="sub" basenode="2f425e331c8cdffa5103f3b181358092245bdc10"/>
    </allgroup>
    <group name="bar">
      <group name="baz">
        <repo root="/qux" shortname="qux" basenode="6c30f00cc82daff63b1260eec198256a9c8e5a56"/>
      </group>
      <repo root="/subroot" shortname="subroot" basenode="b986218ba1c9b0d6a259fac9b050b1724ed8e545">
        <subrepo root="/subroot/svnsub" repotype="svn"/>
        <subrepo root="/subroot/sub" shortname="sub" basenode="2f425e331c8cdffa5103f3b181358092245bdc10"/>
      </repo>
    </group>
  </treeitem>
</reporegistry>
'''

full_data_standalone_repos = ['/thg', '/mercurial', '/subroot/sub',
                              '/qux', '/subroot']
full_data_all_repos = (full_data_standalone_repos
                       + ['/subroot/svnsub', '/subroot/sub'])

@with_qbuffer(full_data, QIODevice.ReadWrite)
def test_readwritexml(f):
    root = repotreemodel.readXml(f, 'reporegistry')
    f.buffer().clear()
    f.reset()
    repotreemodel.writeXml(f, root, 'reporegistry')
    assert_equals(full_data.splitlines(), str(f.data()).splitlines())

@with_qbuffer(full_data)
def test_iterrepoitemfromxml(f):
    repos = list(repotreemodel.iterRepoItemFromXml(f))
    assert_equals(full_data_standalone_repos,
                  map(lambda e: e.rootpath(), repos))
    assert_equals('thg', repos[0].shortname())
    assert_equals('bac32db38e52fd49acb62b94730a55f4f4b0cdee',
                  node.hex(repos[0].basenode()))

@with_qbuffer(full_data)
def test_getrepoitemlist_all(f):
    root = repotreemodel.readXml(f, 'reporegistry')
    items = repotreemodel.getRepoItemList(root)
    assert_equals(full_data_all_repos,
                  map(lambda e: e.rootpath(), items))

@with_qbuffer(full_data)
def test_getrepoitemlist_standalone(f):
    root = repotreemodel.readXml(f, 'reporegistry')
    items = repotreemodel.getRepoItemList(root, standalone=True)
    assert_equals(full_data_standalone_repos,
                  map(lambda e: e.rootpath(), items))

subrepos_data = r'''<?xml version="1.0" encoding="UTF-8"?>
<reporegistry>
  <treeitem>
    <allgroup name="default">
      <subrepo root="/subroot/sub" shortname="sub" basenode="2f425e331c8cdffa5103f3b181358092245bdc10"/>
      <repo root="/subroot" shortname="subroot" basenode="b986218ba1c9b0d6a259fac9b050b1724ed8e545">
        <subrepo root="/subroot/svnsub" repotype="svn"/>
        <subrepo root="/subroot/sub" shortname="sub" basenode="2f425e331c8cdffa5103f3b181358092245bdc10"/>
      </repo>
    </allgroup>
  </treeitem>
</reporegistry>
'''

@with_qbuffer(subrepos_data)
def test_undumpsubrepos(f):
    """<subrepo> element should be mapped to different classes"""
    root = repotreemodel.readXml(f, 'reporegistry')
    allgroup = root.child(0)
    assert type(allgroup.child(0)) is repotreeitem.StandaloneSubrepoItem
    subroot = allgroup.child(1)
    assert type(subroot) is repotreeitem.RepoItem
    assert type(subroot.child(0)) is repotreeitem.AlienSubrepoItem
    assert type(subroot.child(1)) is repotreeitem.SubrepoItem

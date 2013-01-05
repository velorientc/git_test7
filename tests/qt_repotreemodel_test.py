from PyQt4.QtCore import QByteArray, QBuffer, QIODevice
from nose.tools import *
from mercurial import node
from tortoisehg.hgqt import repotreemodel

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
    </allgroup>
    <group name="bar">
      <repo root="/python-vcs" shortname="python-vcs" basenode="b986218ba1c9b0d6a259fac9b050b1724ed8e545"/>
    </group>
  </treeitem>
</reporegistry>
'''

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
    assert_equals(['/thg', '/mercurial', '/python-vcs'],
                  map(lambda e: e.rootpath(), repos))
    assert_equals('thg', repos[0].shortname())
    assert_equals('bac32db38e52fd49acb62b94730a55f4f4b0cdee',
                  node.hex(repos[0].basenode()))

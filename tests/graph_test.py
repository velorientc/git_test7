import os
from nose.tools import *

from mercurial import hg, ui
from tortoisehg.hgqt import graph

import helpers

def setup():
    global _tmpdir
    _tmpdir = helpers.mktmpdir(__name__)

    # foo0 -- foo1 ---------- foo3 -------------------------- foo7
    #   \       \
    #    \       -------------------- baz4 -- baz5 -- baz6 --------
    #     \                                        /               \
    #      ---------- bar2 ------------------------------------------ bar8
    #       [branch: bar]
    hg = helpers.HgClient(os.path.join(_tmpdir, 'named-branch'))
    hg.init()
    hg.fappend('data', 'foo0')
    hg.commit('-Am', 'foo0')
    hg.fappend('data', 'foo1\n')
    hg.commit('-m', 'foo1')
    hg.update('0')
    hg.branch('bar')
    hg.fappend('data', 'bar2\n')
    hg.commit('-m', 'bar2')
    hg.update('1')
    hg.fappend('data', 'foo3\n')
    hg.commit('-m', 'foo3')
    hg.update('1')
    hg.fappend('data', 'baz4\n')
    hg.commit('-m', 'baz4')
    hg.fappend('data', 'baz5\n')
    hg.commit('-m', 'baz5')
    hg.merge('--tool=internal:local', '2')
    hg.commit('-m', 'baz6')
    hg.update('3')
    hg.fappend('data', 'foo7\n')
    hg.commit('-m', 'foo7')
    hg.update('2')
    hg.merge('--tool=internal:local', '6')
    hg.commit('-m', 'bar8')

def openrepo(name):
    return hg.repository(ui.ui(), os.path.join(_tmpdir, name))

def buildlinecolortable(grapher):
    table = {}  # rev: [linecolor, ...]
    for node in grapher:
        if not node:
            continue
        colors = [color for start, end, color, _linetype, _children, _rev
                  in sorted(node.bottomlines)]  # in (start, end) order
        table[node.rev] = colors
    return table

def test_linecolor_unfiltered():
    repo = openrepo('named-branch')
    grapher = graph.revision_grapher(repo)
    actualtable = buildlinecolortable(grapher)
    expectedtable = {
        None: [0],        # |
        8: [0, 2],        # |\
        7: [0, 2, 3],     # | | |
        6: [0, 0, 4, 3],  # |/| |
        5: [0, 4, 3],     # | | |
        4: [0, 3, 3],     # | | |
        3: [0, 3, 3],     # | |/
        2: [0, 3],        # | |
        1: [0, 0],        # |/
        0: [],
        9: [0],  # TODO bug?
        }
    assert_equal(expectedtable, actualtable)

def test_linecolor_branchfiltered():
    repo = openrepo('named-branch')
    grapher = graph.revision_grapher(repo, branch='default')
    actualtable = buildlinecolortable(grapher)
    expectedtable = {
        7: [1],     # |
        6: [1, 2],  # | |
        5: [1, 2],  # | |
        4: [1, 1],  # | |
        3: [1, 1],  # |/
        1: [1],     # |
        0: [],
        9: [],  # TODO bug?
        }
    assert_equal(expectedtable, actualtable)

def test_linecolor_filelog():
    repo = openrepo('named-branch')
    grapher = graph.filelog_grapher(repo, 'data')
    actualtable = buildlinecolortable(grapher)
    expectedtable = {
        7: [0],        # |
        6: [0, 3, 2],  # | |\
        5: [0, 3, 2],  # | | |
        4: [0, 3, 2],  # | | |
        3: [2, 3, 2],  #  X /
        2: [3, 2],     # | |
        1: [3, 3],     # |/
        0: [],
        }
    assert_equal(expectedtable, actualtable)

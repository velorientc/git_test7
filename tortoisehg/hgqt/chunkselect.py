# chunkselect.py - Change chunk selection dialog
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import sys
import cStringIO

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import hg, commands, util, cmdutil, mdiff, error, patch

from tortoisehg.util import hgshelve
from tortoisehg.hgqt.htmllistview import HtmlListView
from tortoisehg.hgqt import htmlui

def check_max_diff(ctx, wfile):
    lines = []
    try:
        fctx = ctx.filectx(wfile)
    except error.LookupError:
        fctx = None
    if fctx and fctx.size() > hglib.getmaxdiffsize(ctx._repo.ui):
        # Fake patch that displays size warning
        lines = ['diff --git a/%s b/%s\n' % (wfile, wfile)]
        lines.append(_('File is larger than the specified max size.\n'))
        lines.append(_('Hunk selection is disabled for this file.\n'))
        lines.append('--- a/%s\n' % wfile)
        lines.append('+++ b/%s\n' % wfile)
    elif '\0' in fctx.data():
        # Fake patch that displays binary file warning
        lines = ['diff --git a/%s b/%s\n' % (wfile, wfile)]
        lines.append(_('File is binary.\n'))
        lines.append(_('Hunk selection is disabled for this file.\n'))
        lines.append('--- a/%s\n' % wfile)
        lines.append('+++ b/%s\n' % wfile)
    return lines

class ChunkModel(QAbstractListModel):
    
    def __init__(self, chunks):
        QAbstractTableModel.__init__(self)
        self.chunks = chunks

    def rowCount(self, parent):
        if not parent.isValid():
            return len(self.chunks)
        return 0

    def columnCount(self):
        return 1

    def data(self, index, role):
        if not index.isValid() or role != Qt.DisplayRole:
            return QVariant()
        if index.row() < 0 or index.row() >= len(self.chunks):
            return QVariant()
        return QVariant(self.chunks[index.row()])

    def headerData(self, col, orientation, role):
        if col != 0 or role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return QVariant()
        else:
            return QVariant("Change chunks")

    def flags(self, index):
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled


def run(ui, *pats, **opts):
    repo = hg.repository(ui)
    fp = cStringIO.StringIO()
    matcher = cmdutil.matchall(repo)
    diffopts = mdiff.diffopts(git=True, nodates=True)
    try:
        node1, node2 = repo['tip'].node(), repo['tip'].parents()[0].node()
        for s in patch.diff(repo, node1, node2, match=matcher, opts=diffopts):
            fp.writelines(s.splitlines(True))
    except (IOError, error.RepoError, error.LookupError, util.Abort), e:
        self.stat.stbar.set_text(str(e))
    fp.seek(0)
    hu = htmlui.htmlui()
    items = []
    for chunk in hgshelve.parsepatch(fp):
        fp = cStringIO.StringIO()
        chunk.write(fp)
        fp.seek(0)
        for a, l in patch.difflabel(fp.readlines):
            if a: hu.write(a, label=l)
        o, e = hu.getdata()
        items.append(o)

    cm = ChunkModel(items)
    lv = HtmlListView(cm)
    lv.show()
    return lv

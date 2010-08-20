# -*- coding: utf-8 -*-
# Copyright (c) 2003-2010 LOGILAB S.A. (Paris, FRANCE).
# http://www.logilab.fr/ -- mailto:contact@logilab.fr
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
"""
Qt4 dialogs to display hg revisions of a file
"""

import sys, os
import os.path as osp

from mercurial import ui, util
from mercurial.revlog import LookupError

from PyQt4 import QtGui, QtCore, Qsci
from PyQt4.QtCore import Qt, QSettings

from tortoisehg.util import paths, thgrepo
from tortoisehg.util.hglib import tounicode

from tortoisehg.hgqt.dialogmixin import HgDialogMixin
from tortoisehg.hgqt.manifestmodel import ManifestModel
from tortoisehg.hgqt.lexers import get_lexer
from tortoisehg.hgqt.ManifestDialog_ui import Ui_ManifestDialog

connect = QtCore.QObject.connect
disconnect = QtCore.QObject.disconnect
SIGNAL = QtCore.SIGNAL
nullvariant = QtCore.QVariant()


class ManifestDialog(QtGui.QMainWindow, Ui_ManifestDialog, HgDialogMixin):
    """
    Qt4 dialog to display all files of a repo at a given revision
    """
    def __init__(self, repo, noderev):
        self.repo = repo
        QtGui.QMainWindow.__init__(self)
        HgDialogMixin.__init__(self, self.repo.ui)
        self.setWindowTitle('Hg manifest viewer - %s:%s' % (repo.root, noderev))

        # hg repo
        self.repo = repo
        self.rev = noderev
        self.setupModels()

        self.createActions()
        self.setupTextview()
        self._readsettings()

    def setupModels(self):
        self.treemodel = ManifestModel(self.repo, self.rev)
        self.treeView.setModel(self.treemodel)
        connect(self.treeView.selectionModel(),
                SIGNAL('currentChanged(const QModelIndex &, const QModelIndex &)'),
                self.fileSelected)

    def createActions(self):
        pass

    def setupTextview(self):
        lay = QtGui.QHBoxLayout(self.mainFrame)
        lay.setSpacing(0)
        lay.setContentsMargins(0,0,0,0)
        sci = Qsci.QsciScintilla(self.mainFrame)
        lay.addWidget(sci)
        sci.setMarginLineNumbers(1, True)
        sci.setMarginWidth(1, '000')
        sci.setReadOnly(True)
        sci.setFont(self._font)
        sci.setUtf8(True)

        sci.SendScintilla(sci.SCI_SETSELEOLFILLED, True)
        self.textView = sci

    def fileSelected(self, index, *args):
        if not index.isValid():
            return
        path = self.treemodel.pathFromIndex(index)
        try:
            fc = self.repo.changectx(self.rev).filectx(path)
        except LookupError:
            # may occur when a directory is selected
            self.textView.setMarginWidth(1, '00')
            self.textView.setText('')
            return

        if fc.size() > self.max_file_size:
            data = "file too big"
        else:
            # return the whole file
            data = fc.data()
            if util.binary(data):
                data = "binary file"
            else:
                data = tounicode(data)
                lexer = get_lexer(path, data, self.repo.ui)
                if lexer:
                    lexer.setFont(self._font)
                    self.textView.setLexer(lexer)
                self._cur_lexer = lexer
        nlines = data.count('\n')
        self.textView.setMarginWidth(1, str(nlines)+'00')
        self.textView.setText(data)

    def setCurrentFile(self, filename):
        index = QtCore.QModelIndex()
        path = filename.split(osp.sep)
        for p in path:
            self.treeView.expand(index)
            for row in range(self.treemodel.rowCount(index)):
                newindex = self.treemodel.index(row, 0, index)
                if newindex.internalPointer().data(0) == p:
                    index = newindex
                    break
        self.treeView.setCurrentIndex(index)

    def closeEvent(self, event):
        self._writesettings()
        super(ManifestDialog, self).closeEvent(event)

    def _readsettings(self):
        s = QSettings()
        self.restoreGeometry(s.value('manifest/geom').toByteArray())
        self.splitter.restoreState(s.value('manifest/splitter').toByteArray())

    def _writesettings(self):
        s = QSettings()
        s.setValue('manifest/geom', self.saveGeometry())
        s.setValue('manifest/splitter', self.splitter.saveState())


def run(ui, *pats, **opts):
    repo = opts.get('repo') or thgrepo.repository(ui, paths.find_root())
    return ManifestDialog(repo, opts.get('rev'))

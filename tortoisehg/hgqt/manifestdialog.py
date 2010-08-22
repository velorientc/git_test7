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

from mercurial import util
from mercurial.revlog import LookupError

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qsci import QsciScintilla

from tortoisehg.util import paths, thgrepo
from tortoisehg.util.hglib import tounicode

from tortoisehg.hgqt import qtlib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.manifestmodel import ManifestModel
from tortoisehg.hgqt.lexers import get_lexer

class ManifestDialog(QMainWindow):
    """
    Qt4 dialog to display all files of a repo at a given revision
    """
    def __init__(self, ui, repo, rev=None, parent=None):
        QMainWindow.__init__(self, parent)
        self.setWindowTitle(_('Hg manifest viewer - %s:%s') % (repo.root, rev))
        self.resize(400, 300)

        self._manifest_widget = ManifestWidget(ui, repo, rev)
        self.setCentralWidget(self._manifest_widget)

        self._readsettings()

    def closeEvent(self, event):
        self._writesettings()
        super(ManifestDialog, self).closeEvent(event)

    def _readsettings(self):
        s = QSettings()
        self.restoreGeometry(s.value('manifest/geom').toByteArray())
        # TODO: don't call deeply
        self._manifest_widget.splitter.restoreState(
            s.value('manifest/splitter').toByteArray())

    def _writesettings(self):
        s = QSettings()
        s.setValue('manifest/geom', self.saveGeometry())
        # TODO: don't call deeply
        s.setValue('manifest/splitter',
                   self._manifest_widget.splitter.saveState())

class ManifestWidget(QWidget):
    """Display file tree and contents at the specified revision"""
    max_file_size = 100000  # TODO: make it configurable

    def __init__(self, ui, repo, rev=None, parent=None):
        super(ManifestWidget, self).__init__(parent)
        self._ui = ui
        self.repo = repo
        self.rev = rev

        self._initwidget()
        self.setupModels()
        self.treeView.setCurrentIndex(self.treemodel.index(0, 0))

    def _initwidget(self):
        self.setLayout(QVBoxLayout())
        self.splitter = QSplitter()
        self.layout().addWidget(self.splitter)
        self.treeView = QTreeView()
        self.textView = QsciScintilla()
        self.textView.setMarginLineNumbers(1, True)
        self.textView.setMarginWidth(1, '000')
        self.textView.setReadOnly(True)
        self.textView.setFont(qtlib.getfont(self._ui, 'fontlog').font())
        self.textView.setUtf8(True)
        self.textView.SendScintilla(QsciScintilla.SCI_SETSELEOLFILLED, True)
        self.splitter.addWidget(self.treeView)
        self.splitter.addWidget(self.textView)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)

    def setupModels(self):
        self.treemodel = ManifestModel(self.repo, self.rev)
        self.treeView.setModel(self.treemodel)
        self.treeView.selectionModel().currentChanged.connect(self.fileSelected)

    @pyqtSlot(QModelIndex)
    def fileSelected(self, index):
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
            data = _("file too big")
        else:
            # return the whole file
            data = fc.data()
            if util.binary(data):
                data = _("binary file")
            else:
                data = tounicode(data)
                lexer = get_lexer(path, data, ui=self._ui)
                if lexer:
                    self.textView.setLexer(lexer)
        nlines = data.count('\n')
        self.textView.setMarginWidth(1, str(nlines)+'00')
        self.textView.setText(data)


def run(ui, *pats, **opts):
    repo = opts.get('repo') or thgrepo.repository(ui, paths.find_root())
    return ManifestDialog(ui, repo, opts.get('rev'))

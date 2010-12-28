# Copyright (c) 2009-2010 LOGILAB S.A. (Paris, FRANCE).
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

from tortoisehg.hgqt.repomodel import HgRepoListModel
from tortoisehg.hgqt.graph import Graph, filelog_grapher

from PyQt4.QtCore import *

class FileRevModel(HgRepoListModel):
    """
    Model used to manage the list of revisions of a file, in file
    viewer of in diff-file viewer dialogs.
    """
    filled = pyqtSignal()

    _allcolumns = ('Rev', 'Branch', 'Description', 'Author', 'Age',
                   'LocalTime', 'UTCTime', 'Tags', 'Filename')
    _columns = ('Rev', 'Branch', 'Description', 'Author', 'Age', 'Filename')
    _stretchs = {'Description': 1, }
    _getcolumns = "getFilelogColumns"

    def __init__(self, repo, filename=None, parent=None):
        """
        data is a HgHLRepo instance
        """
        HgRepoListModel.__init__(self, repo, '', [], False, parent)
        self.setFilename(filename)

    def setRepo(self, repo, branch='', fromhead=None, follow=False):
        self.repo = repo
        self._datacache = {}
        self.reloadConfig()

    def setFilename(self, filename):
        self.filename = filename

        self._user_colors = {}
        self._branch_colors = {}

        self.rowcount = 0
        self._datacache = {}

        if self.filename:
            grapher = filelog_grapher(self.repo, self.filename)
            self.graph = Graph(self.repo, grapher)
            fl = self.repo.file(self.filename)
            # we use fl.index here (instead of linkrev) cause
            # linkrev API changed between 1.0 and 1.?. So this
            # works with both versions.
            self.heads = [fl.index[fl.rev(x)][4] for x in fl.heads()]
            self.ensureBuilt(row=self.fill_step/2)
            QTimer.singleShot(0, lambda: self.filled.emit())
            self._fill_timer = self.startTimer(500)
        else:
            self.graph = None
            self.heads = []

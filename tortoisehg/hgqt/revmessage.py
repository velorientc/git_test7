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

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.hgqt import qtlib

class RevMessage(QWidget):
    revisionLinkClicked = pyqtSignal(str)

    def __init__(self, parent):
        QWidget.__init__(self, parent)

        vb = QVBoxLayout()
        vb.setMargin(0)

        self._message = w = QTextBrowser()
        w.setLineWrapMode(QTextEdit.NoWrap)
        #w.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        f = qtlib.getfont('fontcomment')
        f.changed.connect(lambda newfont: w.setFont(newfont))
        w.setFont(f.font())
        w.setOpenLinks(False)
        vb.addWidget(w)

        self.setLayout(vb)

        self._htmlize = qtlib.descriptionhtmlizer()

        self._message.anchorClicked.connect(self.anchorClicked)

    def anchorClicked(self, qurl):
        link = str(qurl.toString())
        if link.startswith('cset:'):
            rev = link[len('cset:'):]
            self.revisionLinkClicked.emit(rev)
        else:
            QDesktopServices.openUrl(qurl)

    def displayRevision(self, ctx):
        self.ctx = ctx
        self._message.setHtml('<pre>%s</pre>'
                              % self._htmlize(ctx.description()))

    def minimumSizeHint(self):
        return QSize(0, 25)

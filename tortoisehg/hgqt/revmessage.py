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

import re

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.util.util import xml_escape
from tortoisehg.util.hglib import tounicode

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib

# initialize changeset and url link regex
csmatch = r'(\b[0-9a-f]{12}(?:[0-9a-f]{28})?\b)'
httpmatch = r'(\b(http|https)://([-A-Za-z0-9+&@#/%?=~_()|!:,.;]*[-A-Za-z0-9+&@#/%=~_()|]))'
regexp = r'%s|%s' % (csmatch, httpmatch)
bodyre = re.compile(regexp)

revhashprefix = 'rev_hash_'

class RevMessage(QWidget):

    revisionLinkClicked = pyqtSignal(str)

    def __init__(self, ui, parent=None):
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

        self._message.anchorClicked.connect(self.anchorClicked)

    def anchorClicked(self, qurl):
        link = str(qurl.toString())
        if link.startswith(revhashprefix):
            rev = link[len(revhashprefix):]
            self.revisionLinkClicked.emit(rev)
        else:
            QDesktopServices.openUrl(qurl)

    def displayRevision(self, ctx):
        self.ctx = ctx

        desc = xml_escape(tounicode(ctx.description()))

        buf = ''
        pos = 0
        for m in bodyre.finditer(desc):
            a, b = m.span()
            if a >= pos:
                buf += desc[pos:a]
                pos = b
            groups = m.groups()
            if groups[0]:
                cslink = groups[0]
                buf += '<a href="%s%s">%s</a>' % (revhashprefix, cslink, cslink)
            if groups[1]:
                urllink = groups[1]
                buf += '<a href="%s">%s</a>' % (urllink, urllink)
        if pos < len(desc):
            buf += desc[pos:]

        buf = '<pre>%s</pre>' % buf
        self._message.setHtml(buf)

    def minimumSizeHint(self):
        return QSize(0, 25)

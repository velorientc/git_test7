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

from mercurial.node import short as short_hex

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt
connect = QtCore.QObject.connect
SIGNAL = QtCore.SIGNAL

from tortoisehg.util.util import format_desc, xml_escape
from tortoisehg.util import hglib

from tortoisehg.hgqt.config import HgConfig

headerstyle = '''
<style type="text/css">
.rev_number { font-family:Courier; }
.rev_hash { font-family:Courier; }
.label { color:gray; }
</style>
'''

linkfmt = '<span class="rev_number">%s</span>:' \
              '<span class="rev_hash"><a href="%s">%s</a>&nbsp;</span>'

labelfmt = '<td width=%i align="right"><span class="label">%s&nbsp;&nbsp;</span></td>'

csetfmt = '<tr>' + labelfmt + '<td>%s<span class="short_desc">%s</span></td></tr>\n'

labelwidth = 50
descwidth = 80  # number of chars displayed for parent/child descriptions

def cset(ctx, labelname):
    short = short_hex(ctx.node())
    desc = format_desc(ctx.description(), descwidth)
    rev = ctx.rev()
    rev = linkfmt % (rev, rev, short)
    return csetfmt % (labelwidth, labelname, rev, desc)


class RevDisplay(QtGui.QWidget):
    """
    Display metadata for one revision (rev, author, description, etc.)
    """

    commitsignal = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self._message = None
        self.ctx = None

        hb = QtGui.QHBoxLayout()
        hb.setMargin(0)
        self.setLayout(hb)

        self._header = w = QtGui.QLabel()
        w.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        hb.addWidget(w)
        hb.addStretch(0)

        vb = QtGui.QVBoxLayout()
        hb.addLayout(vb)

        hb2 = QtGui.QHBoxLayout()
        hb2.addStretch(0)
        vb.addLayout(hb2)

        # expand header button
        self._expander = w = QtGui.QToolButton()
        w.setArrowType(Qt.UpArrow)
        w.setIconSize(QtCore.QSize(10, 10))
        a = QtGui.QAction(self)
        connect(a, SIGNAL("triggered()"), self.expand)
        w.setDefaultAction(a)
        hb2.addWidget(w, 0, Qt.AlignTop)
        self._expanded = True

        hb3 = QtGui.QHBoxLayout()
        hb3.addStretch(0)
        vb.addLayout(hb3)
        self._commitbutton = w = QtGui.QPushButton('Commit')
        hb3.addWidget(w, 0, Qt.AlignBottom)
        connect(w, SIGNAL('clicked()'), self.commit)

        connect(self._header,
                SIGNAL('linkActivated(const QString&)'),
                self.anchorClicked)

    def commit(self):
        self.commitsignal.emit()

    def expand(self):
        self.setExpanded(not self._expanded)

    def setExpanded(self, state):
        state = bool(state)
        if (state == self._expanded):
            return
        self._expanded = state
        if self._expanded:
            t = Qt.UpArrow
        else:
            t = Qt.DownArrow
        self._expander.setArrowType(t)
        self.refreshDisplay()

    def expanded(self):
        return self._expanded

    def sizeHint(self):
        return self.minimumSizeHint()

    def minimumSizeHint(self):
        return self._header.minimumSizeHint()

    def setMessageWidget(self, w):
        self._message = w

    def anchorClicked(self, qurl):
        """
        Callback called when a link is clicked in the text browser
        """
        rev = str(qurl)
        if rev.startswith('diff_'):
            self.diffrev = int(rev[5:])
            self.refreshDisplay()
            # TODO: emit a signal to recompute the diff
            self.emit(SIGNAL('parentRevisionSelected'), self.diffrev)
        else:
            self.emit(SIGNAL('revisionSelected'), int(rev))

    def setDiffRevision(self, rev):
        if rev != self.diffrev:
            self.diffrev = rev
            self.refreshDisplay()

    def displayRevision(self, ctx):
        self.ctx = ctx
        self.diffrev = ctx.parents()[0].rev()
        if hasattr(self.ctx._repo, "mq"):
            self.mqseries = self.ctx._repo.mq.series[:]
            self.mqunapplied = [x[1] for x in self.ctx._repo.mq.unapplied(self.ctx._repo)]
            mqpatch = set(self.ctx.tags()).intersection(self.mqseries)            
            if mqpatch:
                self.mqpatch = mqpatch.pop()
            else:
                self.mqpatch = None
        else:
            self.mqseries = []
            self.mqunapplied = []
            self.mqpatch = None

        self.refreshDisplay()

    def selectNone(self):
        self._message.selectNone()

    def searchString(self, text):
        self._message.searchString(text)

    def refreshDisplay(self):
        if self.ctx == None:
            return

        ctx = self.ctx
        rev = ctx.rev()

        enableci = self._expanded and not rev
        self._commitbutton.setVisible(enableci)
        self._message.setEditable(enableci)

        buf = headerstyle
        if self.mqpatch:
            buf += "<table width=100%>\n"
            buf += '<tr bgcolor=%s>' % HgConfig(ctx._repo.ui).getMQFGColor()
            buf += '<td colspan=3 width=100%><b>Patch queue:</b>&nbsp;'
            for p in self.mqseries:
                if p in self.mqunapplied:
                    p = "<i>%s</i>" % p
                elif p == self.mqpatch:
                    p = "<b>%s</b>" % p
                buf += '&nbsp;%s&nbsp;' % (p)
            buf += '</td></tr>\n'
            buf += "</table>\n"

        buf += '<table width=100%>\n<tr>'
        if rev is None:
            buf += '<td><b>%s</b></td>' % 'Working Directory'
        else:
            desc = format_desc(ctx.description(), 80)
            buf += '<td><span class="rev_number">%d:</span>' \
                   '<span class="rev_hash">%s&nbsp;</span>' \
                   '<span class="short_desc"><b>%s</b></span></td>' \
                   '\n' % (ctx.rev(), short_hex(ctx.node()), desc)

        buf += (labelfmt + '<td>%s</td>\n') % (labelwidth, 'Branch', ctx.branch())
        buf += '</tr></table>\n'

        if self._expanded:
            buf += self.expandedText()

        self._header.setText(buf)

        self._message.displayRevision(ctx)

    def expandedText(self):
        ctx = self.ctx
        buf = '<table width=100%>\n'

        user = xml_escape(unicode(ctx.user(), 'utf-8', 'replace'))
        buf += ('<tr>' +  labelfmt + '<td>%s</td></tr>\n') % (
                   labelwidth, 'Author', user)

        date = ctx.date()
        disptime = hglib.displaytime(date)
        age = hglib.age(date)
        buf += ('<tr>' + labelfmt + '<td>%s (%s)</td></tr>\n') % (
                   labelwidth, 'Date', disptime, age)

        parents = [p for p in ctx.parents() if p]
        for p in parents:
            if p.rev() > -1:
                buf += cset(p, 'Parent')
        if len(parents) == 2:
            a = parents[0].ancestor(parents[1])
            buf += cset(a, 'Ancestor')

        for c in ctx.children():
            if c.rev() > -1:
                buf += cset(c, 'Child')

        buf += "</table>\n"
        return buf


# initialize changeset and url link regex
csmatch = r'(\b[0-9a-f]{12}(?:[0-9a-f]{28})?\b)'
httpmatch = r'(\b(http|https)://([-A-Za-z0-9+&@#/%?=~_()|!:,.;]*[-A-Za-z0-9+&@#/%=~_()|]))'
regexp = r'%s|%s' % (csmatch, httpmatch)
bodyre = re.compile(regexp)

revhashprefix = 'rev_hash_'

class RevMessage(QtGui.QWidget):

    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)

        vb = QtGui.QVBoxLayout()
        vb.setMargin(0)

        self._message = w = QtGui.QTextBrowser()
        w.setOpenLinks(False)
        vb.addWidget(w)

        self.setLayout(vb)

        connect(self._message, SIGNAL('anchorClicked(QUrl)'), self.anchorClicked)

    def anchorClicked(self, qurl):
        link = str(qurl.toString())
        if link.startswith(revhashprefix):
            rev = link[len(revhashprefix):]
            self.emit(SIGNAL('revisionSelected'), rev)
        else:
            QtGui.QDesktopServices.openUrl(qurl)

    def setEditable(self, editable):
        self._message.setReadOnly(not editable)

    def text(self):
        return str(self._message.toPlainText())

    def displayRevision(self, ctx):
        self.ctx = ctx
        desc = xml_escape(unicode(ctx.description(), 'utf-8', 'replace'))
        desc = desc.replace('\n', '<br/>\n')

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

        buf = '<div class="diff_desc"><p>%s</p></div>' % buf
        self._message.setHtml(buf)

    def selectNone(self):
        msg = self._message
        cursor = msg.textCursor()
        cursor.clearSelection()
        cursor.setPosition(0)
        msg.setTextCursor(cursor)
        msg.setExtraSelections([])

    def searchString(self, text):
        msg = self._message
        self.selectNone()
        if text in unicode(msg.toPlainText()):
            clist = []
            while msg.find(text):
                eselect = msg.ExtraSelection()
                eselect.cursor = msg.textCursor()
                eselect.format.setBackground(QtGui.QColor('#ffffbb'))
                clist.append(eselect)
            self.selectNone()
            msg.setExtraSelections(clist)
            def finditer(msg, text):
                if text:
                    while True:
                        if msg.find(text):
                            yield self.ctx.rev(), None                
                        else:
                            break
            return finditer(msg, text)

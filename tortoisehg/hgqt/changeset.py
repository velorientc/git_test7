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

class RevDisplay(QtGui.QWidget):
    """
    Display metadata for one revision (rev, author, description, etc.)
    """
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self._message = None

        hb = QtGui.QHBoxLayout()
        hb.setMargin(0)
        self.setLayout(hb)

        self._header = w = QtGui.QLabel()
        w.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        hb.addWidget(w)

        vb = QtGui.QVBoxLayout()
        hb.addLayout(vb)

        # expand header button
        self._expander = w = QtGui.QToolButton()
        w.setArrowType(Qt.UpArrow)
        w.setIconSize(QtCore.QSize(10, 10))
        a = QtGui.QAction(self)
        connect(a, SIGNAL("triggered()"), self.expand)
        w.setDefaultAction(a)
        vb.addWidget(w, 0, Qt.AlignTop)
        self._expanded = True

        self.descwidth = 80 # number of chars displayed for parent/child descriptions

        connect(self._header,
                SIGNAL('linkActivated(const QString&)'),
                self.anchorClicked)

    def expand(self):
        self._expanded = not self._expanded
        if self._expanded:
            t = Qt.UpArrow
        else:
            t = Qt.DownArrow
        self._expander.setArrowType(t)
        self.refreshDisplay()

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
        ctx = self.ctx
        rev = ctx.rev()
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
            buf += '<td><b>Working Directory</b></td>'
        else:
            desc = format_desc(ctx.description(), 80)
            buf += '<td><b><span class="rev_number">%d:</span>'\
                   '<span class="rev_hash">%s&nbsp;</span>'\
                   '<span class="short_desc">%s</span></b></td>'\
                   '\n' % (ctx.rev(), short_hex(ctx.node()), desc)
        buf += '<td width=50 align=right><span class="label">Branch&nbsp;</span></td>'\
               '<td>%s</td>'\
               '\n' % ctx.branch()
        buf += '</tr></table>\n'

        if self._expanded:
            buf += '<table width=100%>\n'
            buf += '<tr><td width=50 align="right"><span class="label">Author&nbsp;</span></td>'\
                   '<td colspan=5>%s</td></tr>'\
                   '\n' %  xml_escape(unicode(ctx.user(), 'utf-8', 'replace'))
            d = ctx.date()
            buf += '<tr><td width=50 align="right"><span class="label">Date&nbsp;</span></td>'\
                   '<td>%s (%s)</td></tr>'\
                   '\n' % (hglib.displaytime(d), hglib.age(d))

            parents = [p for p in ctx.parents() if p]
            for p in parents:
                if p.rev() > -1:
                    short = short_hex(p.node())
                    desc = format_desc(p.description(), self.descwidth)
                    p_rev = p.rev()
                    p_fmt = '<span class="rev_number">%s</span>:'\
                            '<a href="%s" class="rev_hash">%s</a>'
                    p_rev = p_fmt % (p_rev, p_rev, short)
                    buf += '<tr><td width=50 align="right"><span class="label">Parent&nbsp;</span></td>'\
                           '<td>%s'\
                           '<span class="short_desc">&nbsp;%s</span></td></tr>'\
                           '\n' % (p_rev, desc)
            if len(parents) == 2:
                p = parents[0].ancestor(parents[1])
                short = short_hex(p.node())
                desc = format_desc(p.description(), self.descwidth)
                p_rev = p.rev()
                p_fmt = '<span class="rev_number">%s</span>:'\
                        '<a href="%s" class="rev_hash">%s</a>'
                p_rev = p_fmt % (p_rev, p_rev, short)
                buf += '<tr><td width=50 align="right"><span class="label">Ancestor</span></td>'\
                       '<td>%s&nbsp;'\
                       '<span class="short_desc">%s</span></td></tr>'\
                       '\n' % (p_rev, desc)

            for p in ctx.children():
                if p.rev() > -1:
                    short = short_hex(p.node())
                    desc = format_desc(p.description(), self.descwidth)
                    buf += '<tr><td align="right"><span class="label">Child&nbsp;</span></td>'\
                           '<td><span class="rev_number">%d</span>:'\
                           '<a href="%s" class="rev_hash">%s</a>&nbsp;'\
                           '<span class="short_desc">%s</span></td></tr>'\
                           '\n' % (p.rev(), p.rev(), short, desc)

            buf += "</table>\n"

        self._header.setText(buf)

        self._message.displayRevision(ctx)


class RevMessage(QtGui.QWidget):

    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)

        vb = QtGui.QVBoxLayout()
        vb.setMargin(0)

        self._message = w = QtGui.QTextBrowser()
        vb.addWidget(w)

        self.setLayout(vb)

    def displayRevision(self, ctx):
        self.ctx = ctx
        desc = xml_escape(unicode(ctx.description(), 'utf-8', 'replace'))
        desc = desc.replace('\n', '<br/>\n')
        buf = '<div class="diff_desc"><p>%s</p></div>' % desc
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

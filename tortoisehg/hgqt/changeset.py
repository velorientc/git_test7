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

from tortoisehg.hgqt.config import HgConfig


class RevDisplay(QtGui.QWidget):
    """
    Display metadata for one revision (rev, author, description, etc.)
    """
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self._message = None

        vb = QtGui.QVBoxLayout()
        vb.setMargin(0)

        self._header = w = QtGui.QLabel()
        w.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        vb.addWidget(w)

        self.setLayout(vb)

        self.descwidth = 60 # number of chars displayed for parent/child descriptions

        connect(self._header,
                SIGNAL('linkActivated(const QString&)'),
                self.anchorClicked)

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
        cursor = self.textCursor()
        cursor.clearSelection()
        cursor.setPosition(0)
        self.setTextCursor(cursor)
        self.setExtraSelections([])
        
    def searchString(self, text):
        self.selectNone()
        if text in unicode(self.toPlainText()):
            clist = []
            while self.find(text):
                eselect = self.ExtraSelection()
                eselect.cursor = self.textCursor()
                eselect.format.setBackground(QtGui.QColor('#ffffbb'))
                clist.append(eselect)
            self.selectNone()
            self.setExtraSelections(clist)
            def finditer(self, text):
                if text:
                    while True:
                        if self.find(text):
                            yield self.ctx.rev(), None                
                        else:
                            break
            return finditer(self, text)
        
    def refreshDisplay(self):
        ctx = self.ctx
        rev = ctx.rev()
        buf = "<table width=100%>\n"
        if self.mqpatch:
            buf += '<tr bgcolor=%s>' % HgConfig(ctx._repo.ui).getMQFGColor()
            buf += '<td colspan=3 width=100%><b>Patch queue:</b>&nbsp;'
            for p in self.mqseries:
                if p in self.mqunapplied:
                    p = "<i>%s</i>" % p
                elif p == self.mqpatch:
                    p = "<b>%s</b>" % p
                buf += '&nbsp;%s&nbsp;' % (p)
            buf += '</td></tr>\n'

        buf += '<tr>'
        if rev is None:
            buf += "<td><b>Working Directory</b></td>\n"
        else:
            buf += '<td><b>Revision:</b>&nbsp;'\
                   '<span class="rev_number">%d</span>:'\
                   '<span class="rev_hash">%s</span></td>'\
                   '\n' % (ctx.rev(), short_hex(ctx.node()))

        buf += '<td><b>Author:</b>&nbsp;'\
               '%s</td>'\
               '\n' %  unicode(ctx.user(), 'utf-8', 'replace')
        buf += '<td><b>Branch:</b>&nbsp;%s</td>' % ctx.branch()
        buf += '</tr>'
        buf += "</table>\n"
        buf += "<table width=100%>\n"
        parents = [p for p in ctx.parents() if p]
        for p in parents:
            if p.rev() > -1:
                short = short_hex(p.node())
                desc = format_desc(p.description(), self.descwidth)
                p_rev = p.rev()
                p_fmt = '<span class="rev_number">%s</span>:'\
                        '<a href="%s" class="rev_hash">%s</a>'
                if p_rev == self.diffrev:
                    p_rev = '<b>%s</b>' % (p_fmt % (p_rev, p_rev, short))
                else:
                    p_rev = p_fmt % ('<a href="diff_%s" class="rev_diff">%s</a>' % (p_rev, p_rev), p_rev, short)
                buf += '<tr><td width=50 class="label"><b>Parent:</b></td>'\
                       '<td colspan=5>%s&nbsp;'\
                       '<span class="short_desc"><i>%s</i></span></td></tr>'\
                       '\n' % (p_rev, desc)
        if len(parents) == 2:
            p = parents[0].ancestor(parents[1])
            short = short_hex(p.node())
            desc = format_desc(p.description(), self.descwidth)
            p_rev = p.rev()
            p_fmt = '<span class="rev_number">%s</span>:'\
                    '<a href="%s" class="rev_hash">%s</a>'
            if p_rev == self.diffrev:
                p_rev = '<b>%s</b>' % (p_fmt % (p_rev, p_rev, short))
            else:
                p_rev = p_fmt % ('<a href="diff_%s" class="rev_diff">%s</a>' % (p_rev, p_rev), p_rev, short)
            buf += '<tr><td width=50 class="label"><b>Ancestor:</b></td>'\
                   '<td colspan=5>%s&nbsp;'\
                   '<span class="short_desc"><i>%s</i></span></td></tr>'\
                   '\n' % (p_rev, desc)

        for p in ctx.children():
            if p.rev() > -1:
                short = short_hex(p.node())
                desc = format_desc(p.description(), self.descwidth)
                buf += '<tr><td class="label"><b>Child:</b></td>'\
                       '<td colspan=5><span class="rev_number">%d</span>:'\
                       '<a href="%s" class="rev_hash">%s</a>&nbsp;'\
                       '<span class="short_desc"><i>%s</i></span></td></tr>'\
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
        cursor = self.textCursor()
        cursor.clearSelection()
        cursor.setPosition(0)
        self.setTextCursor(cursor)
        self.setExtraSelections([])

    def searchString(self, text):
        self.selectNone()
        if text in unicode(self.toPlainText()):
            clist = []
            while self.find(text):
                eselect = self.ExtraSelection()
                eselect.cursor = self.textCursor()
                eselect.format.setBackground(QtGui.QColor('#ffffbb'))
                clist.append(eselect)
            self.selectNone()
            self.setExtraSelections(clist)
            def finditer(self, text):
                if text:
                    while True:
                        if self.find(text):
                            yield self.ctx.rev(), None                
                        else:
                            break
            return finditer(self, text)

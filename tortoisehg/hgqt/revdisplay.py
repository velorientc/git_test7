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

from PyQt4 import QtCore, QtGui
Qt = QtCore.Qt
connect = QtCore.QObject.connect
SIGNAL = QtCore.SIGNAL

from tortoisehg.util.util import xml_escape, tounicode
from tortoisehg.util import hglib

from tortoisehg.hgqt.i18n import _


# initialize changeset and url link regex
csmatch = r'(\b[0-9a-f]{12}(?:[0-9a-f]{28})?\b)'
httpmatch = r'(\b(http|https)://([-A-Za-z0-9+&@#/%?=~_()|!:,.;]*[-A-Za-z0-9+&@#/%=~_()|]))'
regexp = r'%s|%s' % (csmatch, httpmatch)
bodyre = re.compile(regexp)

revhashprefix = 'rev_hash_'

class RevMessage(QtGui.QWidget):

    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.unsavedMessage = None
        self.startEditMessage = ''

        vb = QtGui.QVBoxLayout()
        vb.setMargin(0)

        self._message = w = QtGui.QTextBrowser()
        w.setOpenLinks(False)
        vb.addWidget(w)

        self.setLayout(vb)

        connect(self._message, SIGNAL('anchorClicked(QUrl)'), self.anchorClicked)

    def isSaved(self):
        if self._message.isReadOnly():
            res = self.unsavedMessage is None or self.unsavedMessage == ''
        else:
            res = str(self._message.toPlainText()) == str(self.startEditMessage)
        return res

    def setSaved(self):
        self.unsavedMessage = None
        self._message.setReadOnly(True)

    def clear(self):
        self._message.setText('')

    def anchorClicked(self, qurl):
        link = str(qurl.toString())
        if link.startswith(revhashprefix):
            rev = link[len(revhashprefix):]
            self.emit(SIGNAL('revisionSelected'), rev)
        else:
            QtGui.QDesktopServices.openUrl(qurl)

    def text(self):
        return str(self._message.toPlainText())

    def displayRevision(self, ctx, mqpatch):
        self.ctx = ctx

        editing = not self._message.isReadOnly()

        isWorkingDir = ctx.rev() is None
        if isWorkingDir:
            if not editing:
                self._message.setReadOnly(False)
                if self.unsavedMessage != None:
                    msg = self.unsavedMessage
                elif mqpatch:
                    msg = ctx.p1().description()
                    self.startEditMessage = msg
                else:
                    msg = ''
                    self.startEditMessage = msg
                self._message.setText(msg)
            return

        if editing:
            self.unsavedMessage = str(self._message.toPlainText())

        self._message.setReadOnly(True)

        desc = xml_escape(tounicode(ctx.description()))
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

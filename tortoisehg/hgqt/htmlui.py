# htmlui.py - mercurial.ui.ui class which emits HTML/Rich Text
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import ui
from tortoisehg.hgqt import qtlib
from tortoisehg.util import hglib

class htmlui(ui.ui):
    def __init__(self, src=None):
        super(htmlui, self).__init__(src)
        self.setconfig('ui', 'interactive', 'off')
        self.setconfig('progress', 'disable', 'True')
        self.output = ''
        self.error = ''
        os.environ['TERM'] = 'dumb'
        qtlib.configstyles(self)

    def write(self, *args, **opts):
        label = opts.get('label', '')
        if self._buffers:
            self._buffers[-1].extend([(str(a), label) for a in args])
        else:
            self.output += self.label(''.join(args), label)

    def write_err(self, *args, **opts):
        label = opts.get('label', 'ui.error')
        self.error += self.label(''.join(args), label)

    def label(self, msg, label):
        msg = hglib.tounicode(msg)
        style = qtlib.geteffect(label)
        return '<pre style="%s">%s</pre>' % (style, msg)

    def popbuffer(self, labeled=False):
        b = self._buffers.pop()
        if labeled:
            return ''.join(self.label(a, label) for a, label in b)
        return ''.join(a for a, label in b)

    def plain(self):
        return True

    def getdata(self):
        d, e = self.output, self.error
        self.output, self.error = '', ''
        return d, e

if __name__ == "__main__":
    from mercurial import hg
    u = htmlui()
    repo = hg.repository(u)
    repo.status()

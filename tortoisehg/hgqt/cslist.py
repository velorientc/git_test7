# cslist.py - embeddable changeset/patch list component
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
# Copyright 2010 David Wilhelm <dave@jumbledpile.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from mercurial import hg

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from tortoisehg.hgqt import csinfo
from tortoisehg.hgqt.i18n import _

_SPACING = 6

class ChangesetList(QWidget):

    def __init__(self, parent=None):
        super(ChangesetList, self).__init__()

        self.currepo = None
        self.curitems = None
        self.showitems = None
        self.limit = 20

        # main layout
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.mainvbox = QVBoxLayout()
        self.mainvbox.setSpacing(_SPACING)
        self.mainvbox.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.setLayout(self.mainvbox)

        ## status box
        self.statusbox = QHBoxLayout()
        self.statuslabel = QLabel('')
        self.statusbox.addWidget(self.statuslabel)
        self.mainvbox.addLayout(self.statusbox)

        ## scroll area
        self.scrollarea = QScrollArea()
        self.scrollarea.setMinimumSize(400, 200)
        self.scrollarea.setWidgetResizable(True)
        self.mainvbox.addWidget(self.scrollarea)

        ### cs layout grid, contains Factory objects, one per revision
        self.scrollbox = QWidget()
        self.csvbox = QVBoxLayout()
        self.csvbox.setSpacing(_SPACING)
        self.csvbox.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.scrollbox.setLayout(self.csvbox)
        self.scrollarea.setWidget(self.scrollbox)

    def clear(self):
        """Clear the item list"""
        while self.csvbox.count():
            w = self.csvbox.takeAt(0).widget()
            w.deleteLater()
        self.curitems = None

    def insertcs(self, item, pos):
        """Insert changeset info into the item list.

        item: String, revision number or patch file path to display.
        pos: Number, an index of insertion point.  If -1, indicates
        the end of the item list.
        """
        info = self.curfactory(item)
        info.update(item)
        self.csvbox.addWidget(info, Qt.AlignTop)

    def updatestatus(self):
        if self.curitems is None:
            text = _('No items to display')
        else:
            num = dict(count=len(self.showitems), total=len(self.curitems))
            text = _('Displaying %(count)d of %(total)d items') % num
        self.statuslabel.setText(text)

    def update(self, repo, items, uselimit=True):
        """Update the item list.

        Public arguments:
        repo: Repository used to get changeset information.
        items: List of revision numbers and/or patch file paths.
               You can pass a mixed list. The order will be respected.
        uselimit: If True, some of items will be shown.

        return: True if the item list was updated successfully,
                False if it wasn't updated.
        """
        # setup
        self.clear()
        contents = ('%(rev)s', ' %(branch)s', ' %(tags)s', ' %(summary)s')
        style = csinfo.labelstyle(contents=contents, width=350,
                                  selectable=True)
        self.curfactory = csinfo.factory(repo, style=style)

        # initialize variables
        self.currepo = repo
        self.curitems = items

        if not items or not repo:
            self.updatestatus()
            return False

        # determine the items to show
        if uselimit and self.limit < len(items):
            showitems, lastitem = items[:self.limit - 1], items[-1]
        else:
            showitems, lastitem = items, None
        numshow = len(showitems) + (lastitem and 1 or 0)
        self.showitems = showitems + (lastitem and [lastitem] or [])

        # show items
        for item in showitems:
            self.insertcs(item, -1)
        if lastitem:
            self.csvbox.addWidget(QLabel("..."))
            self.insertcs(lastitem, -1)
        self.updatestatus()
        return True


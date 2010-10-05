# revset.py - revision set query dialog
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from tortoisehg.hgqt import qtlib, cmdui
from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _

from PyQt4.QtCore import *
from PyQt4.QtGui import *

# TODO:
#  Connect to repoview revisionClicked events
#  Shift-Click rev range -> revision range X:Y
#  Ctrl-Click two revs -> DAG range X::Y

_common = (
    ('user(string)',
     _('Changesets where username contains string.')),
    ('keyword(string)',
     _('Search commit message, user name, and names of changed '
       'files for string.')),
    ('grep(regex)',
     _('Like "keyword(string)" but accepts a regex.')),
    ('outgoing([path])',
     _('Changesets not found in the specified destination repository,'
       ' or the default push location.')),
    ('tagged()',
     _('Changeset is tagged.')),
    ('head()',
     _('Changeset is a head.')),
    ('merge()',
     _('Changeset is a merge changeset.')),
    ('closed()',
     _('Changeset is closed.')),
    ('date(interval)',
     _('Changesets within the interval, see <a href="http://www.selenic.com/'
       'mercurial/hg.1.html#dates">help dates</a>')),
)

_filepatterns = (
    ('file(pattern)',
     _('Changesets affecting files matched by pattern.  '
       'See <a href="http://www.selenic.com/mercurial/hg.1.html#patterns">'
       'help patterns</a>')),
    ('modifies(pattern)',
     _('Changesets which modify files matched by pattern.')),
    ('adds(pattern)',
     _('Changesets which add files matched by pattern.')),
    ('removes(pattern)',
     _('Changesets which remove files matched by pattern.')),
    ('contains(pattern)',
     _('Changesets containing files matched by pattern.')),
)

_ancestry = (
    ('branch(set)',
     _('All changesets belonging to the branches of changesets in set.')),
    ('heads(set)',
     _('Members of a set with no children in set.')),
    ('descendants(set)',
     _('Changesets which are descendants of changesets in set.')),
    ('children(set)',
     _('Child changesets of changesets in set.')),
    ('parents(set)',
     _('The set of all parents for all changesets in set.')),
    ('p1(set)',
     _('First parent for all changesets in set.')),
    ('p2(set)',
     _('Second parent for all changesets in set.')),
    ('roots(set)',
     _('Changesets whith no parent changeset in set.')),
    ('present(set)',
     _('An empty set, if any revision in set isn\'t found; otherwise, '
       'all revisions in set.')),
)

_logical = (
    ('min(set)',
     _('Changeset with lowest revision number in set.')),
    ('max(set)',
     _('Changeset with highest revision number in set.')),
    ('limit(set, n)',
     _('Firt n members of a set.')),
    ('sort(set[, [-]key...])',
     _('Sort set by keys.  The default sort order is ascending, specify a '
       'key as "-key" to sort in descending order.')),
    ('follow()',
     _('An alias for "::." (ancestors of the working copy\'s first parent).')),
    ('all()',
     _('All changesets, the same as 0:tip.')),
)

class RevisionSetQuery(QDialog):
    queryIssued = pyqtSignal(QString)

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)

        self.setWindowTitle(_('Revision Set Query'))
        self.setWindowFlags(self.windowFlags() & \
                            ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.setContentsMargins(*(4,)*4)
        self.setLayout(layout)

        self.stbar = cmdui.ThgStatusBar(self)
        self.stbar.setSizeGripEnabled(False)
        self.stbar.lbl.setOpenExternalLinks(True)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(*(0,)*4)

        cgb = QGroupBox(_('Common sets'))
        cgb.setLayout(QVBoxLayout())
        cgb.layout().setContentsMargins(*(0,)*4)
        def setCommonHelp(item):
            self.stbar.showMessage(self.clw._help[self.clw.row(item)])
        self.clw = QListWidget(self)
        self.clw.addItems([x for x, y in _common])
        self.clw._help = [y for x, y in _common]
        self.clw.itemClicked.connect(setCommonHelp)
        cgb.layout().addWidget(self.clw)
        hbox.addWidget(cgb)

        fgb = QGroupBox(_('File pattern sets'))
        fgb.setLayout(QVBoxLayout())
        fgb.layout().setContentsMargins(*(0,)*4)
        def setFileHelp(item):
            self.stbar.showMessage(self.flw._help[self.flw.row(item)])
        self.flw = QListWidget(self)
        self.flw.addItems([x for x, y in _filepatterns])
        self.flw._help = [y for x, y in _filepatterns]
        self.flw.itemClicked.connect(setFileHelp)
        fgb.layout().addWidget(self.flw)
        hbox.addWidget(fgb)

        agb = QGroupBox(_('Set Ancestry'))
        agb.setLayout(QVBoxLayout())
        agb.layout().setContentsMargins(*(0,)*4)
        def setAncHelp(item):
            self.stbar.showMessage(self.alw._help[self.alw.row(item)])
        self.alw = QListWidget(self)
        self.alw.addItems([x for x, y in _ancestry])
        self.alw._help = [y for x, y in _ancestry]
        self.alw.itemClicked.connect(setAncHelp)
        agb.layout().addWidget(self.alw)
        hbox.addWidget(agb)

        lgb = QGroupBox(_('Set Logic'))
        lgb.setLayout(QVBoxLayout())
        lgb.layout().setContentsMargins(*(0,)*4)
        def setManipHelp(item):
            self.stbar.showMessage(self.llw._help[self.llw.row(item)])
        self.llw = QListWidget(self)
        self.llw.addItems([x for x, y in _logical])
        self.llw._help = [y for x, y in _logical]
        self.llw.itemClicked.connect(setManipHelp)
        lgb.layout().addWidget(self.llw)
        hbox.addWidget(lgb)

        # Clicking on one listwidget should clear selection of the others
        listwidgets = (self.clw, self.flw, self.alw, self.llw)
        for w in listwidgets:
            for w2 in listwidgets:
                if w is not w2:
                    w.itemClicked.connect(w2.clearSelection)

        layout.addLayout(hbox)

        txt = _('<a href="http://www.selenic.com/mercurial/hg.1.html#revsets">'
                'help revsets</a>')
        helpLabel = QLabel(txt)
        helpLabel.setOpenExternalLinks(True)
        self.stbar.addPermanentWidget(helpLabel)

        layout.addWidget(self.stbar)

        hbox = QHBoxLayout()
        clear = QPushButton(_('Clear'))
        queryle = QComboBox()
        queryle.setEditable(True)
        issue = QPushButton(_('Issue'))
        remember = QPushButton(_('Remember'))
        hbox.addWidget(clear)
        hbox.addWidget(queryle, 1)
        hbox.addWidget(issue)
        hbox.addWidget(remember)
        clear.pressed.connect(queryle.lineEdit().clear)
        layout.addLayout(hbox)
        
def run(ui, *pats, **opts):
    return RevisionSetQuery()

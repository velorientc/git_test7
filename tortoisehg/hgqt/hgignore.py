# hgignore.py - TortoiseHg's dialog for editing .hgignore
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import re

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import hg, ui, match, util, error

from tortoisehg.util.i18n import _
from tortoisehg.util import shlib, hglib, paths

from tortoisehg.hgqt import qtlib

class HgignoreDialog(QDialog):
    'Edit a reposiory .hgignore file'

    ignoreFilterUpdated = pyqtSignal()

    def __init__(self, parent=None, root=None, fileglob='', *pats):
        'Initialize the Dialog'
        QDialog.__init__(self, parent)

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root(root))
        except error.RepoError:
            QDialog.reject(self)
            return

        self.repo = repo
        self.setWindowTitle(_('Ignore filter - %s') % hglib.get_reponame(repo))

        vbox = QVBoxLayout()
        self.setLayout(vbox)

        # layer 1
        hbox = QHBoxLayout()
        vbox.addLayout(hbox)
        recombo = QComboBox()
        recombo.addItems([_('Glob'), _('Regexp')])
        hbox.addWidget(recombo)

        le = QLineEdit()
        hbox.addWidget(le, 1)
        le.setText(hglib.tounicode(fileglob))
        le.returnPressed.connect(self.addEntry)

        add = QPushButton(_('Add'))
        add.clicked.connect(self.addEntry)
        hbox.addWidget(add, 0)

        # layer 2
        hbox = QHBoxLayout()
        vbox.addLayout(hbox)
        ignorefiles = [repo.wjoin('.hgignore')]
        for name, value in repo.ui.configitems('ui'):
            if name == 'ignore' or name.startswith('ignore.'):
                ignorefiles.append(os.path.expanduser(value))

        filecombo = QComboBox()
        hbox.addWidget(filecombo)
        for f in ignorefiles:
            filecombo.addItem(hglib.tounicode(f))
        filecombo.currentIndexChanged.connect(self.fileselect)
        self.ignorefile = ignorefiles[0]

        edit = QPushButton(_('Edit File'))
        edit.clicked.connect(self.editClicked)
        hbox.addWidget(edit)
        hbox.addStretch(1)

        # layer 3 - main widgets
        split = QSplitter()
        vbox.addWidget(split, 1)

        ignorelist = QListWidget(split)
        unknownlist = QListWidget(split)

        # layer 4 - dialog buttons
        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Close)
        self.connect(bb, SIGNAL("accepted()"), self, SLOT("accept()"))
        self.connect(bb, SIGNAL("rejected()"), self, SLOT("reject()"))
        vbox.addWidget(bb)
        self.bb = bb

        le.setFocus()
        self.le, self.recombo, self.filecombo = le, recombo, filecombo
        self.ignorelist, self.unknownlist = ignorelist, unknownlist
        QTimer.singleShot(0, self.refresh)

        s = QSettings()
        self.restoreGeometry(s.value('hgignore/geom').toByteArray())


    def fileselect(self):
        'user selected another ignore file'
        self.ignorefile = hglib.fromunicode(self.filecombo.getCurrentText())
        self.refresh()

    def editClicked(self):
        if qtlib.fileEditor(self.ignorefile) == QDialog.Accepted:
            self.refresh()

    def addEntry(self):
        newfilter = hglib.fromunicode(self.le.text()).strip()
        if newfilter == '':
            return
        if self.recombo.currentIndex() == 0:
            newfilter = 'glob:' + newfilter
            try:
                match.match(self.repo.root, '', [], [newfilter])
            except util.Abort, inst:
                qtlib.WarningMsgBox(_('Invalid glob expression'), str(inst),
                                    parent=self)
                return
        else:
            newfilter = 'relre:' + newfilter
            try:
                match.match(self.repo.root, '', [], [newfilter])
                re.compile(newfilter)
            except (util.Abort, re.error), inst:
                qtlib.WarningMsgBox(_('Invalid regexp expression'), str(inst),
                                    parent=self)
                return
        self.ignorelines.append(newfilter)
        self.writeIgnoreFile()
        self.le.clear()
        self.refresh()

    def refresh(self):
        uni = hglib.tounicode
        try:
            hglib.invalidaterepo(self.repo)
            wctx = self.repo[None]
            wctx.status(unknown=True)
        except util.Abort, error.RepoError:
            qtlib.WarningMsgBox(_('Unable to read repository status'),
                                uni(str(e)), parent=self)

        self.unknown = wctx.unknown()
        self.unknownlist.clear()
        self.unknownlist.addItems([uni(u) for u in self.unknown])

        try:
            l = open(self.ignorefile, 'rb').readlines()
            self.doseoln = l[0].endswith('\r\n')
        except (IOError, ValueError, IndexError):
            self.doseoln = os.name == 'nt'
            l = []
        self.ignorelines = [line.strip() for line in l]
        self.ignorelist.clear()
        self.ignorelist.addItems([uni(l) for l in self.ignorelines])

    def writeIgnoreFile(self):
        eol = self.doseoln and '\r\n' or '\n'
        out = eol.join(self.ignorelines) + eol

        try:
            f = util.atomictempfile(self.ignorefile, 'wb', createmode=None)
            f.write(out)
            f.rename()
            shlib.shell_notify([self.ignorefile])
            self.emit(SIGNAL('ignoreFilterUpdated'))
        except IOError, e:
            qtlib.WarningMsgBox(_('Unable to write .hgignore file'),
                                hglib.tounicode(str(e)), parent=self)

    def accept(self):
        s = QSettings()
        s.setValue('hgignore/geom', self.saveGeometry())
        QDialog.accept(self)

    def reject(self):
        s = QSettings()
        s.setValue('hgignore/geom', self.saveGeometry())
        QDialog.reject(self)

def run(_ui, *pats, **opts):
    if pats and pats[0].endswith('.hgignore'):
        pats = []
    return HgignoreDialog(None, root=None, *pats)

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

from tortoisehg.hgqt.i18n import _
from tortoisehg.util import shlib, hglib, paths

from tortoisehg.hgqt import qtlib, thgrepo

class HgignoreDialog(QDialog):
    'Edit a repository .hgignore file'

    ignoreFilterUpdated = pyqtSignal()

    contextmenu = None

    def __init__(self, parent=None, root=None, *pats):
        'Initialize the Dialog'
        QDialog.__init__(self, parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        try:
            repo = thgrepo.repository(ui.ui(), path=paths.find_root(root))
        except error.RepoError:
            QDialog.reject(self)
            return

        self.repo = repo
        self.pats = pats
        self.setWindowTitle(_('Ignore filter - %s') % repo.displayname)

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

        ignoregb = QFrame()
        ignoregb.setFrameStyle(QFrame.Panel|QFrame.Raised)
        ivbox = QVBoxLayout()
        ignoregb.setLayout(ivbox)
        lbl = QLabel(_('<b>Ignore Filter</b>'))
        ivbox.addWidget(lbl)
        split.addWidget(ignoregb)

        unknowngb = QFrame()
        unknowngb.setFrameStyle(QFrame.Panel|QFrame.Raised)
        uvbox = QVBoxLayout()
        unknowngb.setLayout(uvbox)
        lbl = QLabel(_('<b>Untracked Files</b>'))
        uvbox.addWidget(lbl)
        split.addWidget(unknowngb)

        ignorelist = QListWidget()
        ivbox.addWidget(ignorelist)
        unknownlist = QListWidget()
        uvbox.addWidget(unknownlist)
        unknownlist.currentTextChanged.connect(self.setGlobFilter)
        unknownlist.setContextMenuPolicy(Qt.CustomContextMenu)
        unknownlist.customContextMenuRequested.connect(self.menuRequest)
        lbl = QLabel(_('Backspace or Del to remove a row'))
        ivbox.addWidget(lbl)

        # layer 4 - dialog buttons
        BB = QDialogButtonBox
        bb = QDialogButtonBox(BB.Close)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        vbox.addWidget(bb)
        self.bb = bb

        le.setFocus()
        self.le, self.recombo, self.filecombo = le, recombo, filecombo
        self.ignorelist, self.unknownlist = ignorelist, unknownlist
        ignorelist.installEventFilter(self)
        QTimer.singleShot(0, self.refresh)

        s = QSettings()
        self.restoreGeometry(s.value('hgignore/geom').toByteArray())

    def eventFilter(self, obj, event):
        if obj != self.ignorelist:
            return False
        if event.type() != QEvent.KeyPress:
            return False
        elif event.key() not in (Qt.Key_Backspace, Qt.Key_Delete):
            return False
        row = obj.currentRow()
        if row < 0:
            return False
        self.ignorelines.pop(row)
        self.writeIgnoreFile()
        self.refresh()
        return True

    def menuRequest(self, point):
        'context menu request for unknown list'
        point = self.unknownlist.mapToGlobal(point)
        row = self.unknownlist.currentRow()
        if row < 0:
            return
        local = self.lclunknowns[row]
        if not self.contextmenu:
            self.contextmenu = QMenu(self)
            self.contextmenu.setTitle(_('Add ignore filter...'))
        else:
            self.contextmenu.clear()
        filters = [local]
        base, ext = os.path.splitext(local)
        if ext:
            filters.append('*'+ext)
        dirname = os.path.dirname(local)
        while dirname:
            filters.append(dirname)
            dirname = os.path.dirname(dirname)
        for f in filters:
            action = self.contextmenu.addAction(_('Ignore ') + hglib.tounicode(f))
            action.args = (f,False)
            action.run = lambda: self.insertFilter(*action.args)
            action.triggered.connect(action.run)
        self.contextmenu.exec_(point)

    def insertFilter(self, pat, isregexp):
        h = isregexp and 'syntax: regexp' or 'syntax: glob'
        if h in self.ignorelines:
            l = self.ignorelines.index(h)
            for i, line in enumerate(self.ignorelines[l+1:]):
                if line.startswith('syntax:'):
                    self.ignorelines.insert(l+i+1, pat)
                    break
            else:
                self.ignorelines.append(pat)
        else:
            self.ignorelines.append(h)
            self.ignorelines.append(pat)
        self.writeIgnoreFile()
        self.refresh()

    def setGlobFilter(self, qstr):
        'user selected an unknown file; prep a glob filter'
        self.recombo.setCurrentIndex(0)
        self.le.setText(qstr)

    def fileselect(self):
        'user selected another ignore file'
        self.ignorefile = hglib.fromunicode(self.filecombo.currentText())
        self.refresh()

    def editClicked(self):
        if qtlib.fileEditor(self.ignorefile) == QDialog.Accepted:
            self.refresh()

    def addEntry(self):
        newfilter = hglib.fromunicode(self.le.text()).strip()
        if newfilter == '':
            return
        if self.recombo.currentIndex() == 0:
            test = 'glob:' + newfilter
            try:
                match.match(self.repo.root, '', [], [test])
                self.insertFilter(newfilter, False)
            except util.Abort, inst:
                qtlib.WarningMsgBox(_('Invalid glob expression'), str(inst),
                                    parent=self)
                return
        else:
            test = 'relre:' + newfilter
            try:
                match.match(self.repo.root, '', [], [test])
                re.compile(test)
                self.insertFilter(newfilter, True)
            except (util.Abort, re.error), inst:
                qtlib.WarningMsgBox(_('Invalid regexp expression'), str(inst),
                                    parent=self)
                return
        self.le.clear()

    def refresh(self):
        uni = hglib.tounicode
        try:
            self.repo.thginvalidate()
            wctx = self.repo[None]
            wctx.status(unknown=True)
        except (util.Abort, error.RepoError), e:
            qtlib.WarningMsgBox(_('Unable to read repository status'),
                                uni(str(e)), parent=self)
            return

        self.lclunknowns = wctx.unknown()
        self.unknownlist.clear()
        self.unknownlist.addItems([uni(u) for u in self.lclunknowns])
        for i, u in enumerate(self.lclunknowns):
            if u in self.pats:
                item = self.unknownlist.item(i)
                self.unknownlist.setItemSelected(item, True)
                self.unknownlist.setCurrentItem(item)
                # single selection only
                break

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
            self.ignoreFilterUpdated.emit()
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
    return HgignoreDialog(None, None, *pats)

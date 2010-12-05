# bookmark.py - Bookmark dialog for TortoiseHg
#
# Copyright 2010 Michal De Wildt <michael.dewildt@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import error

from tortoisehg.util import hglib, i18n
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib
from hgext import bookmarks

keep = i18n.keepgettext()

class BookmarkDialog(QDialog):
    showMessage = pyqtSignal(QString)

    def __init__(self, repo, rev, parent):
        super(BookmarkDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & \
                            ~Qt.WindowContextHelpButtonHint)
        self.repo = repo

        # base layout box
        base = QVBoxLayout()
        base.setSpacing(0)
        base.setContentsMargins(*(0,)*4)

        # main layout box
        box = QVBoxLayout()
        box.setSpacing(6)
        box.setContentsMargins(*(6,)*4)
        base.addLayout(box)

        ## main layout grid
        grid = QGridLayout()
        grid.setSpacing(6)
        box.addLayout(grid)

        ### bookmark combo
        self.bookmark_combo = QComboBox()
        self.bookmark_combo.setEditable(True)
        self.bookmark_combo.setMinimumWidth(180)
        self.bookmark_combo.setEditText('')
        grid.addWidget(QLabel(_('Bookmark:')), 0, 0)
        grid.addWidget(self.bookmark_combo, 0, 1)

        ### Rename input
        self.new_name_text = QLineEdit()
        self.new_name_text.setMaximumWidth(100)
        self.new_name_text.textEdited.connect(self.new_bookmark_changed)
        self.new_name_label = QLabel(_('New name:'))
        grid.addWidget(self.new_name_label, 1, 0)
        grid.addWidget(self.new_name_text, 1, 1)
        self.enable_new_name(False)

        ### revision input
        self.initial_rev = str(rev)
        self.rev_text = QLineEdit()
        self.rev_text.setMaximumWidth(100)
        self.rev_text.setText(rev)
        self.rev_text.setReadOnly(True)
        #self.rev_text.textEdited.connect(self.update_sensitives)
        grid.addWidget(QLabel(_('Revision:')), 2, 0)
        grid.addWidget(self.rev_text, 2, 1)

        ## bottom buttons
        buttons = QDialogButtonBox()
        self.close_btn = buttons.addButton(QDialogButtonBox.Close)
        self.close_btn.clicked.connect(self.reject)
        self.add_btn = buttons.addButton(_('&Add'),
                                         QDialogButtonBox.ActionRole)
        self.add_btn.clicked.connect(self.add_bookmark)
        self.rename_btn = buttons.addButton(_('&Rename'),
                                         QDialogButtonBox.ActionRole)
        self.rename_btn.clicked.connect(self.rename_bookmark)
        self.remove_btn = buttons.addButton(_('&Remove'),
                                            QDialogButtonBox.ActionRole)
        self.remove_btn.clicked.connect(self.remove_bookmark)
        box.addWidget(buttons)

        # add signals
        self.bookmark_combo.currentIndexChanged.connect(self.toggle_new_bookmark)
        self.bookmark_combo.editTextChanged.connect(self.update_sensitives)

        ## horizontal separator
        self.sep = QFrame()
        self.sep.setFrameShadow(QFrame.Sunken)
        self.sep.setFrameShape(QFrame.HLine)
        base.addWidget(self.sep)

        ## status line
        self.status = qtlib.StatusLabel()
        self.status.setContentsMargins(4, 2, 4, 4)
        base.addWidget(self.status)

        # dialog setting
        self.setLayout(base)
        self.layout().setSizeConstraint(QLayout.SetFixedSize)
        self.setWindowTitle(_('Bookmark - %s') % self.repo.displayname)
        self.setWindowIcon(qtlib.geticon('bookmark'))

        # prepare to show
        self.clear_status()
        self.update_bookmark_combo(clear=False)
        self.update_sensitives()
        self.rename_btn.setVisible(False)
        self.rename_btn.setEnabled(False)
        self.enable_new_name(False)
        self.bookmark_combo.setFocus()

    ### Private Methods ###
    def enable_new_name(self, enabled):
        self.new_name_text.setEnabled(enabled)
        self.new_name_label.setEnabled(enabled)

    def update_bookmark_combo(self, clear=True):
        """ update display on dialog with recent repo data """
        bookmark_name = self.bookmark_combo.currentText()
        self.bookmark_combo.clear()

        # add bookmarks to drop-down list
        bookmarks = self.repo.bookmarks.keys()[:]
        bookmarks.sort()
        bookmarks.reverse()
        for bookmark in bookmarks:
            if bookmark == 'tip':
                continue
            self.bookmark_combo.addItem(hglib.tounicode(bookmark))
        self.bookmark_combo.clearEditText()

        # restore tag name
        if not clear and bookmark_name:
            self.bookmark_combo.setEditText(bookmark_name)

    def toggle_new_bookmark(self):
        bookmark = self.bookmark_combo.currentText()
        bookmarkutf = unicode(bookmark).encode('utf-8')
        is_new = bookmarkutf not in self.repo.bookmarks
        self.add_btn.setVisible(is_new)
        self.add_btn.setDisabled(not is_new)
        self.remove_btn.setVisible(not is_new)
        self.rename_btn.setVisible(not is_new)
        self.enable_new_name(not is_new)

    @pyqtSlot()
    def update_sensitives(self):
        """ update bottom button sensitives based on rev and bookmark """
        self.toggle_new_bookmark()
        revstr = self.rev_text.text()
        if not revstr or not self.bookmark_combo.currentText():
            self.add_btn.setDisabled(True)
            return

        try:
            # check if valid revision, tag, or branch
            self.repo[unicode(revstr, 'utf-8')]
        except (error.LookupError, error.RepoLookupError, error.RepoError):
            self.add_btn.setDisabled(True)
            self.remove_btn.setDisabled(True)
            self.rename_btn.setDisabled(True)

    def set_status(self, text, icon=None):
        self.status.setShown(True)
        self.sep.setShown(True)
        self.status.set_status(text, icon)
        self.showMessage.emit(text)

    def clear_status(self):
        self.status.setHidden(True)
        self.sep.setHidden(True)

    def add_bookmark(self):
        bookmark = self.bookmark_combo.currentText()
        bookmarkutf = unicode(bookmark).encode('utf-8')
        if bookmarkutf in self.repo.bookmarks:
            self.set_status(_('A bookmark named "%s" already exists') %
                            bookmark, False)
            return

        bookmarks.bookmark(ui=self.repo.ui,
                           repo=self.repo,
                           rev=self.initial_rev,
                           mark=bookmarkutf)

        self.bookmark_combo.addItem(bookmark)
        self.set_status(_("Bookmark '%s' has been added") % bookmark, True)
        self.toggle_new_bookmark()
        self.bookmark_combo.clearEditText()

    def remove_bookmark(self):
        bookmark = self.bookmark_combo.currentText()
        bookmarkutf = unicode(bookmark).encode('utf-8')
        if not bookmarkutf in self.repo.bookmarks:
            self.set_status(_("Bookmark '%s' does not exist") % bookmark, False)
            return

        bookmarks.bookmark(ui=self.repo.ui,
                           repo=self.repo,
                           mark=bookmarkutf,
                           delete=True)

        self.bookmark_combo.removeItem(self.bookmark_combo.currentIndex())
        self.new_name_text.setText("")
        self.set_status(_("Bookmark '%s' has been removed") % bookmark, True)
        self.update_sensitives()

    def rename_bookmark(self):
        name = self.bookmark_combo.currentText()
        nameutf = unicode(name).encode('utf-8')

        newname = self.new_name_text.text()
        newnameutf = unicode(newname).encode('utf-8')
        if not nameutf in self.repo.bookmarks:
            self.set_status(_("Bookmark '%s' does not exist") % name, False)
            return

        if newnameutf in self.repo.bookmarks:
            self.set_status(_('A bookmark named "%s" already exists') %
                            newname, False)
            return

        bookmarks.bookmark(ui=self.repo.ui,
                           repo=self.repo,
                           mark=newnameutf,
                           rename=nameutf)

        self.bookmark_combo.removeItem(self.bookmark_combo.currentIndex())
        self.bookmark_combo.addItem(newname)
        self.new_name_text.setText("")
        self.set_status(_("Bookmark '%s' has been renamed to '%s'") %
                        (name, newname), True)

    @pyqtSlot(QString)
    def new_bookmark_changed(self, value):
        self.rename_btn.setDisabled(not value)

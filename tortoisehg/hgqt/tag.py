# tag.py - Tag dialog for TortoiseHg
#
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import traceback

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import hg, ui, error

from tortoisehg.util import hglib, paths, i18n, thgrepo
from tortoisehg.hgqt.qtlib import getpixmap
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib

keep = i18n.keepgettext()

class TagDialog(QDialog):

    tagChanged = pyqtSignal()
    localTagChanged = pyqtSignal()
    showMessage = pyqtSignal(str)

    def __init__(self, repo=None, tag='', rev='tip', parent=None, opts={}):
        super(TagDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.ui = ui.ui()
        if repo:
            self.repo = repo
        else:
            root = paths.find_root()
            if root:
                self.repo = thgrepo.repository(self.ui, path=root)
            else:
                raise 'no repository found'

        if not tag and rev and rev != 'tip':
            bmarks = hglib.get_repo_bookmarks(self.repo)
            for t in self.repo.nodetags(self.repo[rev].node()):
                if t != 'tip' \
                        and ((not bmarks) or (bmarks and t not in bmarks)):
                    tag = t
                    break
            else:
                tag = ''

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

        ### tag combo
        self.tag_combo = QComboBox()
        self.tag_combo.setEditable(True)
        self.tag_combo.setMinimumWidth(180)
        self.tag_combo.setEditText(tag)
        self.tag_combo.editTextChanged.connect(self.tag_changed)
        grid.addWidget(QLabel(_('Tag:')), 0, 0)
        grid.addWidget(self.tag_combo, 0, 1)

        ### revision input
        self.initial_rev = rev
        self.rev_text = QLineEdit()
        self.rev_text.setMaximumWidth(100)
        self.rev_text.setText(rev)
        self.rev_text.textEdited.connect(lambda s: self.update_sensitives())
        grid.addWidget(QLabel(_('Revision:')), 1, 0)
        grid.addWidget(self.rev_text, 1, 1)

        ### options
        expander = qtlib.ExpanderLabel(_('Options'), False)
        expander.expanded.connect(self.show_options)
        grid.addWidget(expander, 2, 0, 1, 2, Qt.AlignLeft | Qt.AlignTop)

        optbox = QVBoxLayout()
        optbox.setSpacing(6)
        grid.addLayout(optbox, 3, 0, 1, 2)

        hbox = QHBoxLayout()
        hbox.setSpacing(0)
        optbox.addLayout(hbox)

        self.local_chk = QCheckBox(_('Local tag'))
        self.local_chk.toggled.connect(self.local_toggled)
        self.replace_chk = QCheckBox(_('Replace existing tag (-f/--force)'))
        self.replace_chk.toggled.connect(lambda b: self.update_sensitives())
        optbox.addWidget(self.local_chk)
        optbox.addWidget(self.replace_chk)

        self.eng_chk = QCheckBox(_('Use English commit message'))
        engmsg = self.repo.ui.configbool('tortoisehg', 'engmsg', False)
        self.eng_chk.setChecked(engmsg)
        optbox.addWidget(self.eng_chk)

        self.custom_chk = QCheckBox(_('Use custom commit message:'))
        self.custom_chk.toggled.connect(
             lambda e: self.toggle_enabled(e, self.custom_text))
        self.custom_text = QLineEdit()
        optbox.addWidget(self.custom_chk)
        optbox.addWidget(self.custom_text)

        ## bottom buttons
        buttons = QDialogButtonBox()
        self.close_btn = buttons.addButton(QDialogButtonBox.Close)
        self.close_btn.clicked.connect(self.reject)
        self.add_btn = buttons.addButton(_('&Add'),
                                         QDialogButtonBox.ActionRole)
        self.add_btn.clicked.connect(self.add_tag)
        self.remove_btn = buttons.addButton(_('&Remove'),
                                            QDialogButtonBox.ActionRole)
        self.remove_btn.clicked.connect(self.remove_tag)
        box.addWidget(buttons)

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
        reponame = hglib.get_reponame(self.repo)
        self.setWindowTitle(_('Tag - %s') % hglib.tounicode(reponame))
        self.setWindowIcon(qtlib.geticon('tag'))

        # prepare to show
        self.custom_text.setDisabled(True)
        self.clear_statue()
        self.update_tagcombo(clear=False)
        self.update_sensitives(affectlocal=True)
        self.show_options(False)
        self.tag_combo.setFocus()

        self.replace_chk.setChecked(bool(opts.get('force')))
        self.local_chk.setChecked(bool(opts.get('local')))
        if not opts.get('local') and opts.get('message'):
            self.custom_chk.setChecked(True)
            self.custom_text.setText(opts.get('message', ''))

    ### Private Methods ###

    def update_tagcombo(self, clear=True):
        """ update display on dialog with recent repo data """
        self.repo.thginvalidate()
        tag_name = self.tag_combo.currentText()
        self.tag_combo.clear()

        # add tags to drop-down list
        tags = list(self.repo.tags())
        tags.sort()
        tags.reverse()
        for tag in tags:
            if tag == 'tip':
                continue
            self.tag_combo.addItem(hglib.tounicode(tag))
        self.tag_combo.clearEditText()

        # restore tag name 
        if not clear and tag_name:
            self.tag_combo.setEditText(tag_name)

    def update_sensitives(self, affectlocal=False):
        """ update bottom button sensitives based on rev and tag """
        tag = self.tag_combo.currentText()
        rev = self.rev_text.text()
        if not rev or not tag:
            self.add_btn.setDisabled(True)
            self.remove_btn.setDisabled(True)
            return

        # check if valid revision
        try:
            self.repo[hglib.fromunicode(rev)]
        except (error.LookupError, error.RepoLookupError, error.RepoError):
            self.add_btn.setDisabled(True)
            self.remove_btn.setDisabled(True)
            return

        # check tag existence
        force = self.replace_chk.isChecked()
        is_exist = hglib.fromunicode(tag) in self.repo.tags()
        self.add_btn.setEnabled(not is_exist or force)
        self.remove_btn.setEnabled(is_exist)

        # check if local
        is_local = self.repo.tagtype(hglib.fromunicode(tag))
        if affectlocal and is_local is not None:
            self.local_chk.setChecked(is_local == 'local')
        self.update_revision()

    def update_revision(self):
        """ update revision entry based on tag """
        tagmap = self.repo.tags()
        tag = self.tag_combo.currentText()
        replace = self.replace_chk.isChecked()
        if not tag or hglib.fromunicode(tag) not in tagmap or replace:
            if self.initial_rev:
                self.rev_text.setText(self.initial_rev)
            return

        node = tagmap[hglib.fromunicode(tag)]
        ctx = self.repo[node]
        self.rev_text.setText(unicode(ctx.rev()))

    def show_options(self, visible):
        self.local_chk.setVisible(visible)
        self.replace_chk.setVisible(visible)
        self.eng_chk.setVisible(visible)
        self.custom_chk.setVisible(visible)
        self.custom_text.setVisible(visible)

    def set_status(self, text, icon=None):
        self.status.setShown(True)
        self.sep.setShown(True)
        self.status.set_status(text, icon)
        self.showMessage.emit(text)

    def clear_statue(self):
        self.status.setHidden(True)
        self.sep.setHidden(True)

    def add_tag(self):
        local = self.local_chk.isChecked()
        name = self.tag_combo.currentText()
        lname = hglib.fromunicode(name)
        rev = hglib.fromunicode(self.rev_text.text())
        force = self.replace_chk.isChecked()
        english = self.eng_chk.isChecked()
        message = self.custom_text.text()

        try:
            # tagging
            if lname in self.repo.tags() and not force:
                raise util.Abort(_("Tag '%s' already exist") % name)
            ctx = self.repo[rev]
            node = ctx.node()
            if not message:
                msgset = keep._('Added tag %s for changeset %s')
                message = (english and msgset['id'] or msgset['str']) \
                            % (name, str(ctx))
            if not isinstance(message, str):
                message = hglib.fromunicode(message)
            self.repo.tag(lname, node, message, local, None, None)

            # update UI
            self.set_status(_("Tag '%s' has been added") % name, True)
            self.update_tagcombo()
            self.close_btn.setFocus()
            self.repo.thginvalidate()
            if local:
                self.localTagChanged.emit()
            else:
                self.tagChanged.emit()
        except:
            self.set_status(_('Error in tagging'), False)
            print traceback.format_exc()

    def remove_tag(self):
        local = self.local_chk.isChecked()
        name = self.tag_combo.currentText()
        lname = hglib.fromunicode(name)
        english = self.eng_chk.isChecked()
        message = hglib.fromunicode(self.custom_text.text())

        try:
            # tagging
            tagtype = self.repo.tagtype(lname)
            if local:
                if tagtype != 'local':
                    raise util.Abort(_('tag \'%s\' is not a local tag') % lname)
            else:
                if tagtype != 'global':
                    raise util.Abort(_('tag \'%s\' is not a global tag') % lname)
            if not message:
                msgset = keep._('Removed tag %s')
                message = (english and msgset['id'] or msgset['str']) % name
            node = self.repo[-1].node()
            self.repo.tag(lname, node, message, local, None, None)

            # update UI
            self.set_status(_("Tag '%s' has been removed") % name, True)
            self.update_tagcombo()
            self.close_btn.setFocus()
            self.repo.thginvalidate()
            if local:
                self.localTagChanged.emit()
            else:
                self.tagChanged.emit()
        except:
            self.set_status(_('Error in tagging'), False)
            print traceback.format_exc()

    ### Signal Handlers ###

    def local_toggled(self, checked):
        self.eng_chk.setEnabled(not checked)
        self.custom_chk.setEnabled(not checked)
        custom = self.custom_chk.isChecked()
        self.custom_text.setEnabled(not checked and custom)

    def tag_changed(self, combo):
        self.update_revision()
        self.update_sensitives(True)

    def toggle_enabled(self, checked, target):
        target.setEnabled(checked)
        if checked:
            target.setFocus()

def run(ui, *pats, **opts):
    kargs = {}
    tag = len(pats) > 0 and pats[0] or None
    if tag:
        kargs['tag'] = tag
    rev = opts.get('rev')
    if rev:
        kargs['rev'] = rev
    return TagDialog(opts=opts, **kargs)

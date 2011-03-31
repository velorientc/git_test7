# Copyright 2011 Ryan Seto <mr.werewolf@gmail.com>
#
# rupdate.py - Remote Update dialog for TortoiseHg
#
# This dialog lets users update a remote ssh repository.
#
# Requires a copy of the rupdate plugin found at:
#     http://bitbucket.org/MrWerewolf/rupdate
#
# Also, enable the plugin with the following in mercurial.ini:
#
# [extensions]
# rupdate = /path/to/rupdate
#
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import error, node, merge as mergemod

from tortoisehg.util import hglib, paths 
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui, csinfo, qtlib, thgrepo, resolve
from tortoisehg.hgqt.update import UpdateDialog

class rUpdateDialog(UpdateDialog):

    def __init__(self, repo, rev=None, parent=None, opts={}):
        super(rUpdateDialog, self).__init__(repo, rev, parent, opts)

        # Get configured paths
        self.paths = {}
        fn = self.repo.join('hgrc')
        fn, cfg = qtlib.loadIniFile([fn], self)
        if 'paths' in cfg:
            for alias in cfg['paths']:
                self.paths[ alias ] = cfg['paths'][alias]

        ### target path combo
        self.path_combo = pcombo = QComboBox()
        pcombo.setEditable(True)

        for alias in self.paths:
            pcombo.addItem(hglib.tounicode(self.paths[alias]))

        ### shift existing items down a row.
        for i in range(self.grid.count()-1, -1, -1):
            row, col, rowSp, colSp = self.grid.getItemPosition(i)
            item = self.grid.takeAt(i)
            self.grid.removeItem(item)
            self.grid.addItem(item, row + 1, col, rowSp, colSp, item.alignment())

        ### add target path combo to grid
        self.grid.addWidget(QLabel(_('Location:')), 0, 0)
        self.grid.addWidget(pcombo, 0, 1)

        ### Options
        self.push_chk = QCheckBox(_('Perform a push before updating'
                                        ' (-p/--push)'))
        self.newbranch_chk = QCheckBox(_('Allow pushing new branches'
                                        ' (--new-branch)'))
        self.force_chk = QCheckBox(_('Force push to remote location'
                                        ' (-f/--force)'))
        self.optbox.removeWidget(self.showlog_chk)
        self.optbox.addWidget(self.push_chk)
        self.optbox.addWidget(self.newbranch_chk)
        self.optbox.addWidget(self.force_chk)
        self.optbox.addWidget(self.showlog_chk)

        # prepare to show
        self.push_chk.setHidden(True)
        self.newbranch_chk.setHidden(True)
        self.force_chk.setHidden(True)
        self.update_info()

    ### Private Methods ###

    def update_info(self):
        super(rUpdateDialog, self).update_info()
        
        # Keep update button enabled.
        self.update_btn.setDisabled(False)

    def update(self):
        cmdline = ['rupdate']

        if self.discard_chk.isChecked():
            cmdline.append('--clean')
        if self.push_chk.isChecked():
            cmdline.append('--push')
        if self.newbranch_chk.isChecked():
            cmdline.append('--new-branch')
        if self.force_chk.isChecked():
            cmdline.append('--force')

        dest = hglib.fromunicode(self.path_combo.currentText())
        cmdline.append('-d')
        cmdline.append(dest)

        # Refer to the revision by the short hash.
        rev = hglib.fromunicode(self.rev_combo.currentText())
        revShortHash = node.short(self.repo[rev].node())
        cmdline.append(revShortHash)

        # start updating
        self.repo.incrementBusyCount()
        self.cmd.run(cmdline)

    ### Signal Handlers ###

    def show_options(self, visible):
        self.push_chk.setShown(visible)
        self.newbranch_chk.setShown(visible)
        self.force_chk.setShown(visible)
        self.showlog_chk.setShown(visible)

    def command_started(self):
        super(rUpdateDialog, self).command_started()
        self.update_btn.setHidden(False)

def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    repo = thgrepo.repository(ui, path=paths.find_root())
    rev = None
    if opts.get('rev'):
        rev = opts.get('rev')
    elif len(pats) == 1:
        rev = pats[0]
    return rUpdateDialog(repo, rev, None, opts)

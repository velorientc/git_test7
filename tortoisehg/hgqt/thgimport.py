# thgimport.py - Import dialog for TortoiseHg
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
# Copyright 2010 David Wilhelm <dave@jumbledpile.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os, tempfile

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import hg, ui, error

from tortoisehg.util import hglib, paths, thgrepo
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui, cslist, qtlib

_FILE_FILTER = "%s;;%s" % (_("Patch files (*.diff *.patch)"),
                           _("All files (*)"))

class ImportDialog(QDialog):
    """Dialog to import patches"""

    repoInvalidated = pyqtSignal()

    def __init__(self, repo=None, rev=None, parent=None, opts={}):
        super(ImportDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() &
                            ~Qt.WindowContextHelpButtonHint)

        self.tempfiles = []

        self.ui = ui.ui()
        if repo:
            self.repo = repo
        else:
            root = paths.find_root()
            if root:
                self.repo = thgrepo.repository(self.ui, path=root)
            else:
                raise 'not repository'

        # base layout box
        box = QVBoxLayout()
        box.setSpacing(6)

        ## main layout grid
        self.grid = grid = QGridLayout()
        grid.setSpacing(6)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        box.addLayout(grid)

        ### source input
        self.src_combo = QComboBox()
        self.src_combo.setEditable(True)
        self.src_combo.setMinimumWidth(310)
        self.file_btn = QPushButton(_('Browse...'))
        self.file_btn.setAutoDefault(False)
        self.connect(self.file_btn, SIGNAL("clicked()"), self.browsefiles)
        self.clip_btn = QPushButton(_('Import from Clipboard'))
        self.clip_btn.setAutoDefault(False)
        self.connect(self.clip_btn, SIGNAL("clicked()"), self.getcliptext)
        grid.addWidget(QLabel(_('Source:')), 0, 0)
        grid.addWidget(self.src_combo, 0, 1)
        srcbox = QHBoxLayout()
        srcbox.addWidget(self.file_btn)
        srcbox.addWidget(self.clip_btn)
        grid.addLayout(srcbox, 1, 1)
        self.p0chk = QCheckBox(_('Do not strip paths (-p0), '
                                 'required for SVN patches'))
        grid.addWidget(self.p0chk, 2, 1, Qt.AlignLeft)
        grid.addWidget(QLabel(_('Preview:')), 3, 0, Qt.AlignLeft | Qt.AlignTop)
        self.status = QLabel("")
        grid.addWidget(self.status, 3, 1, Qt.AlignLeft | Qt.AlignTop)

        ### patch list
        self.cslist = cslist.ChangesetList()
        grid.addWidget(self.cslist, 4, 1, Qt.AlignLeft | Qt.AlignTop)

        ## command widget
        self.cmd = cmdui.Widget()
        self.cmd.commandStarted.connect(self.command_started)
        self.cmd.commandFinished.connect(self.command_finished)
        self.cmd.commandCanceling.connect(self.command_canceling)
        box.addWidget(self.cmd)

        ## bottom buttons
        buttons = QDialogButtonBox()
        self.cancel_btn = buttons.addButton(QDialogButtonBox.Cancel)
        self.cancel_btn.clicked.connect(self.cancel_clicked)
        self.close_btn = buttons.addButton(QDialogButtonBox.Close)
        self.close_btn.clicked.connect(self.reject)
        self.close_btn.setAutoDefault(False)
        self.import_btn = buttons.addButton(_('&Import'),
                                            QDialogButtonBox.ActionRole)
        self.import_btn.clicked.connect(self.thgimport)
        self.detail_btn = buttons.addButton(_('Detail'),
                                            QDialogButtonBox.ResetRole)
        self.detail_btn.setAutoDefault(False)
        self.detail_btn.setCheckable(True)
        self.detail_btn.toggled.connect(self.detail_toggled)
        box.addWidget(buttons)

        # signal handlers
        self.src_combo.editTextChanged.connect(lambda *a: self.preview())
        self.src_combo.lineEdit().returnPressed.connect(self.thgimport)
        self.p0chk.toggled.connect(lambda *a: self.preview())

        # dialog setting
        self.setLayout(box)
        self.layout().setSizeConstraint(QLayout.SetMinAndMaxSize)
        reponame = hglib.get_reponame(self.repo)
        self.setWindowTitle(_('Import - %s') % hglib.tounicode(reponame))
        #self.setWindowIcon(qtlib.geticon('import'))

        # prepare to show
        self.src_combo.lineEdit().selectAll()
        self.cslist.setHidden(False)
        self.cmd.setHidden(True)
        self.cancel_btn.setHidden(True)
        self.detail_btn.setHidden(True)
        self.p0chk.setHidden(False)
        self.preview()

    ### Private Methods ###

    def browsefiles(self):
        caption = _("Select patches")
        path = QFileDialog.getOpenFileNames(parent=self, caption=caption,
            filter=_FILE_FILTER)
        if path:
            response = os.pathsep.join([str(x) for x in path])
            self.src_combo.setEditText(response)
            self.src_combo.setFocus()

    def getcliptext(self):
        text = hglib.fromunicode(QApplication.clipboard().text())
        if not text:
            return
        filename = self.writetempfile(text)
        curtext = self.src_combo.currentText()
        if curtext:
            self.src_combo.setEditText(curtext + os.pathsep + filename)
        else:
            self.src_combo.setEditText(filename)

    def updatestatus(self):
        items = self.cslist.curitems
        count = items and len(items) or 0
        countstr = qtlib.markup(_("%s patches") % count, weight='bold')
        if count:
            self.status.setText(_('%s will be imported to the repository') %
                                countstr)
        else:
            text = qtlib.markup(_('Nothing to import'), weight='bold',
                                fg='red')
            self.status.setText(text)

    def preview(self):
        patches = hglib.fromunicode(self.src_combo.currentText())
        if not patches:
            self.cslist.clear()
            self.import_btn.setDisabled(True)
        else:
            patches = patches.split(os.pathsep)
            self.cslist.update(self.repo, patches)
            self.import_btn.setEnabled(True)
        self.updatestatus()

    def thgimport(self):
        hgcmd = 'import'
        cmdline = [hgcmd, '--repository', self.repo.root]
        if self.p0chk.isChecked():
            cmdline.append('-p0')
        cmdline.extend(['--verbose', '--'])
        cmdline.extend(self.cslist.curitems)

        self.cmd.run(cmdline)

    def writetempfile(self, text):
        fd, filename = tempfile.mkstemp(suffix='.patch', prefix='thg-import-')
        try:
            os.write(fd, text)
        finally:
            os.close(fd)
        self.tempfiles.append(filename)
        return filename

    def unlinktempfiles(self):
        for path in self.tempfiles:
            os.unlink(path)

    ### Override Handlers ###

    def accept(self):
        self.unlinktempfiles()
        super(ImportDialog, self).accept()

    def reject(self):
        self.unlinktempfiles()
        super(ImportDialog, self).reject()

    ### Signal Handlers ###

    def cancel_clicked(self):
        self.cmd.cancel()
        self.reject()

    def detail_toggled(self, checked):
        self.cmd.show_output(checked)

    def command_started(self):
        self.cmd.setShown(True)
        self.import_btn.setHidden(True)
        self.close_btn.setHidden(True)
        self.cancel_btn.setShown(True)
        self.detail_btn.setShown(True)

    def command_finished(self, wrapper):
        if wrapper.data is not 0 or self.cmd.is_show_output():
            self.detail_btn.setChecked(True)
            self.close_btn.setShown(True)
            self.close_btn.setAutoDefault(True)
            self.close_btn.setFocus()
            self.cancel_btn.setHidden(True)
        else:
            self.repoInvalidated.emit()
            self.accept()

    def command_canceling(self):
        self.cancel_btn.setDisabled(True)

def run(ui, *pats, **opts):
    return ImportDialog(opts=opts)

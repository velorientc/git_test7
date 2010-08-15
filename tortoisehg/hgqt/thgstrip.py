# thgstrip.py - MQ strip dialog for TortoiseHg
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
# Copyright 2010 David Wilhelm <dave@jumbledpile.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from mercurial import hg, ui, error

from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui, csinfo, qtlib

class StripDialog(QDialog):
    """Dialog to strip changesets"""

    repoInvalidated = pyqtSignal()

    def __init__(self, repo=None, rev=None, parent=None, opts={}):
        super(StripDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.ui = ui.ui()
        if repo:
            self.repo = repo
        else:
            root = paths.find_root()
            if root:
                self.repo = hg.repository(self.ui, path=root)
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

        ### target revision combo
        self.rev_combo = combo = QComboBox()
        combo.setEditable(True)
        grid.addWidget(QLabel(_('Strip:')), 0, 0)
        grid.addWidget(combo, 0, 1)
        grid.addWidget(QLabel(_('Preview:')), 1, 0, Qt.AlignLeft | Qt.AlignTop)
        self.resultlbl = QLabel("")
        grid.addWidget(self.resultlbl, 1, 1, Qt.AlignLeft | Qt.AlignTop)

        if rev is None:
            rev = self.repo.dirstate.branch()
        else:
            rev = str(rev)
        combo.addItem(hglib.tounicode(rev))
        combo.setCurrentIndex(0)
        for name in hglib.getlivebranch(self.repo):
            combo.addItem(hglib.tounicode(name))

        tags = list(self.repo.tags())
        tags.sort()
        tags.reverse()
        for tag in tags:
            combo.addItem(hglib.tounicode(tag))

        ### preview box, contained in scroll area, contains preview grid
        self.scrollarea = QScrollArea()
        self.scrollarea.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.scrollarea.setWidgetResizable(True)
        self.previewbox = QWidget()
        self.previewbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.previewgrid = QVBoxLayout()

        #### preview layout grid, contains Factory objects (one per revision)
        self.previewgrid.setSpacing(6)
        self.previewgrid.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.previewbox.setLayout(self.previewgrid)

        self.scrollarea.setWidget(self.previewbox)
        grid.addWidget(self.scrollarea, 2, 1, Qt.AlignLeft | Qt.AlignTop)

        ### options
        optbox = QVBoxLayout()
        optbox.setSpacing(6)
        expander = qtlib.ExpanderLabel(_('Options:'), False)
        expander.expanded.connect(self.show_options)
        grid.addWidget(expander, 3, 0, Qt.AlignLeft | Qt.AlignTop)
        grid.addLayout(optbox, 3, 1)

        self.discard_chk = QCheckBox(_('Discard local changes, no backup (-f/--force)'))
        self.nobackup_chk = QCheckBox(_('No backup (-n/--nobackup)'))
        optbox.addWidget(self.discard_chk)
        optbox.addWidget(self.nobackup_chk)

        self.discard_chk.setChecked(bool(opts.get('force')))

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
        self.strip_btn = buttons.addButton(_('&Strip'),
                                           QDialogButtonBox.ActionRole)
        self.strip_btn.clicked.connect(self.strip)
        self.detail_btn = buttons.addButton(_('Detail'),
                                            QDialogButtonBox.ResetRole)
        self.detail_btn.setAutoDefault(False)
        self.detail_btn.setCheckable(True)
        self.detail_btn.toggled.connect(self.detail_toggled)
        box.addWidget(buttons)

        # signal handlers
        self.rev_combo.editTextChanged.connect(lambda *a: self.strip_info())
        self.rev_combo.lineEdit().returnPressed.connect(self.strip)
        self.discard_chk.toggled.connect(lambda *a: self.strip_info())

        # dialog setting
        self.setLayout(box)
        self.layout().setSizeConstraint(QLayout.SetMinAndMaxSize)
        reponame = hglib.get_reponame(self.repo)
        self.setWindowTitle(_('Strip - %s') % hglib.tounicode(reponame))
        #self.setWindowIcon(qtlib.geticon('strip'))

        # prepare to show
        self.rev_combo.lineEdit().selectAll()
        self.previewbox.setHidden(False)
        self.cmd.setHidden(True)
        self.cancel_btn.setHidden(True)
        self.detail_btn.setHidden(True)
        self.nobackup_chk.setHidden(True)
        self.strip_info()

    ### Private Methods ###

    def clear_preview(self):
        while self.previewgrid.count():
            w = self.previewgrid.takeAt(0).widget()
            w.deleteLater()

    def preview_updated(self, rev):
        items = ('%(rev)s', ' %(branch)s', ' %(tags)s', ' %(summary)s')
        style = csinfo.labelstyle(contents=items, width=350, selectable=True)
        factory = csinfo.factory(self.repo, style=style)
        parctxs = self.repo[None].parents()
        striprevs = list(self.repo.changelog.descendants(rev))
        striprevs.append(rev)
        striprevs.sort()
        self.resultlbl.setText(_("%s will be stripped") % _("%s changesets")
                               % len(striprevs))
        self.clear_preview()
        for striprev in striprevs:
            info = factory()
            info.update(self.repo[striprev])
            self.previewgrid.addWidget(info, Qt.AlignTop)

    def strip_info(self):
        revstr = hglib.fromunicode(self.rev_combo.currentText())
        if not revstr:
            self.clear_preview()
            self.resultlbl.setText(_('unknown revision!'))
            self.strip_btn.setDisabled(True)
            return
        try:
            self.preview_updated(self.repo[revstr].rev())
            self.strip_btn.setEnabled(True)
        except (error.LookupError, error.RepoLookupError, error.RepoError):
            self.clear_preview()
            self.resultlbl.setText(_('unknown revision!'))
            self.strip_btn.setDisabled(True)

    def strip(self):
        cmdline = ['strip', '--repository', self.repo.root, '--verbose']
        rev = hglib.fromunicode(self.rev_combo.currentText())
        if not rev:
            return
        cmdline.append(rev)

        if self.discard_chk.isChecked():
            cmdline.append('--force')
        else:
            try:
                node = self.repo[rev]
            except (error.LookupError, error.RepoLookupError, error.RepoError):
                return
            def isclean():
                """return whether WD is changed"""
                wc = self.repo[None]
                return not (wc.modified() or wc.added() or wc.removed())
            if not isclean():
                main = _("Detected uncommitted local changes.")
                text = _("Do you want to discard them and continue?")
                labels = ((QMessageBox.Yes, _('&Yes (--force)')),
                          (QMessageBox.No, _('&No')))
                if qtlib.QuestionMsgBox(_('Confirm Strip'), main, text,
                                        labels=labels, parent=self):
                    cmdline.append('--force')
                else:
                    return

        # backup options
        if self.nobackup_chk.isChecked():
            cmdline.append('--nobackup')

        # start the strip
        self.cmd.run(cmdline)

    ### Signal Handlers ###

    def cancel_clicked(self):
        self.cmd.cancel()
        self.reject()

    def detail_toggled(self, checked):
        self.cmd.show_output(checked)

    def show_options(self, visible):
        self.nobackup_chk.setShown(visible)

    def command_started(self):
        self.cmd.setShown(True)
        self.strip_btn.setHidden(True)
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
    rev = None
    if opts.get('rev'):
        rev = opts.get('rev')
    elif len(pats) == 1:
        rev = pats[0]
    return StripDialog(rev, opts=opts)

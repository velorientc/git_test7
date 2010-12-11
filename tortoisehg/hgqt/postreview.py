# postreview.py - post review dialog for TortoiseHg
#
# Copyright 2010 Michael De Wildt <michael.dewildt@gmail.com>
#
# A dialog to allow users to post a review to reviewboard
# http:///www.reviewboard.org
#
# This dialog requires the reviewboard mercurial plugin which can be
# downloaded from:
#
# http://bitbucket.org/michaeldewildt/mercurial-reviewboard
#
# It is a fork of mdelagra's plugin with some small changes to make it
# play nicer with the thg ui. Mdelagra's reviewboard extension is a fork
# of the original extension found on the Mercurial website.
#
# Original: http://mercurial.selenic.com/wiki/ReviewboardExtension
# Mdelagra's Fork: http://bitbucket.org/mdelagra/mercurial-reviewboard/overview/
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.
import time, datetime

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from mercurial import error, extensions, cmdutil
from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui, qtlib, thgrepo
from tortoisehg.hgqt.postreview_ui import Ui_PostReviewDialog
from tortoisehg.hgqt.hgemail import _ChangesetsModel
from hgext import reviewboard

class LoadReviewDataThread(QThread):
    def __init__ (self, dialog):
        super(LoadReviewDataThread, self).__init__(dialog)
        self.dialog = dialog

    def run(self):
        msg = None
        reviewboard = extensions.find('reviewboard')

        server = self.dialog.server
        user = self.dialog.user
        password = self.dialog.password
        
        if server:
            if user and password:
                try:
                    self._reviewboard = reviewboard.ReviewBoard(server, None,
                                                                False)
                    self._reviewboard.login(user, password)
                    self.load_combos()

                except reviewboard.ReviewBoardError, e:
                    msg = e.message
            else:
                msg = _("Invalid Settings - Please provide your ReviewBoard " +
                        "username and password")
        else:
            msg = _("Invalid Settings - The ReviewBoard server is not setup")

        self.dialog._error_message = msg

    def load_combos(self):
        #Get the index of a users previously selected repo id
        index = 0
        count = 0

        self.dialog._qui.progress_label.setText("Loading repositories...")
        for r in self._reviewboard.repositories():
            if r['id'] == self.dialog._repo_id:
                index = count
            self.dialog._qui.repo_id_combo.addItem(str(r['id']) + ": " + r['name'])
            count += 1

        if self.dialog._qui.repo_id_combo.count():
            self.dialog._qui.repo_id_combo.setCurrentIndex(index)

        self.dialog._qui.progress_label.setText("Loading existing reviews...")
        for r in self._reviewboard.requests():
            if self.is_valid_request(r):
                summary = str(r['id']) + ": " + str(r['summary'])[0:100]
                self.dialog._qui.review_id_combo.addItem(summary)

        if self.dialog._qui.review_id_combo.count():
            self.dialog._qui.review_id_combo.setCurrentIndex(0)

    def is_valid_request(self, request):
        #We only want to include pending requests
        if request['status'] != 'pending':
            return False
        #And requests for the current user
        if request['submitter']['username'] != self.dialog.user:
            return False

        #And only requests within the last week
        delta = datetime.timedelta(days=7)
        today = datetime.datetime.today()
        sevenDaysAgo = today - delta
        dateToCompare = datetime.datetime.strptime(request["last_updated"],
                                                   "%Y-%m-%d %H:%M:%S")
        if (dateToCompare < sevenDaysAgo):
            return False

        return True

class PostReviewDialog(QDialog):
    """Dialog for sending patches to reviewboard"""
    def __init__(self, ui, repo, revs, parent=None):
        super(PostReviewDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._ui = ui
        self._repo = repo
        self._error_message = None

        self._qui = Ui_PostReviewDialog()
        self._qui.setupUi(self)

        self._initchangesets(revs)
        self._readsettings()

        self._review_thread = LoadReviewDataThread(self)
        self._review_thread.finished.connect(self.error_prompt)
        self._review_thread.start()

    def keyPressEvent(self, event):
    # don't post review by just hitting enter
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() == Qt.ControlModifier and self._isvalid():
                self.accept()  # Ctrl+Enter

            return

        super(PostReviewDialog, self).keyPressEvent(event)

    @pyqtSlot()
    def error_prompt(self):
        self._qui.progress_bar.hide()
        self._qui.progress_label.hide()

        if self._error_message:
            qtlib.ErrorMsgBox(_('Review Board'),
                              _('Error'), self._error_message)
            self.close()
        elif self._isvalid():
            self._qui.post_review_button.setEnabled(True)

    def closeEvent(self, event):
        # Dispose of the review data thread
        self._review_thread.terminate()
        self._review_thread.wait()

        self._writesettings()
        super(PostReviewDialog, self).closeEvent(event)

    def _readsettings(self):
        s = QSettings()

        self.restoreGeometry(s.value('reviewboard/geom').toByteArray())

        self._qui.publish_immediately_check.setChecked(
                s.value('reviewboard/publish_immediately_check').toBool())
        self._qui.outgoing_changes_check.setChecked(
                s.value('reviewboard/outgoing_changes_check').toBool())
        self._qui.update_fields.setChecked(
                s.value('reviewboard/update_fields').toBool())
        self._qui.summary_edit.addItems(
                s.value('reviewboard/summary_edit_history').toStringList())

        self._repo_id = s.value('reviewboard/repo_id').toInt()[0]

        self.server = self._repo.ui.config('reviewboard', 'server')
        self.user = self._repo.ui.config('reviewboard', 'user')
        self.password = self._repo.ui.config('reviewboard', 'password')
        self.browser = self._repo.ui.config('reviewboard', 'browser')

    def _writesettings(self):
        s = QSettings()
        s.setValue('reviewboard/geom', self.saveGeometry())
        s.setValue('reviewboard/publish_immediately_check',
                   self._qui.publish_immediately_check.isChecked())
        s.setValue('reviewboard/outgoing_changes_check',
                   self._qui.outgoing_changes_check.isChecked())
        s.setValue('reviewboard/update_fields',
                   self._qui.update_fields.isChecked())
        s.setValue('reviewboard/repo_id', self._getrepoid())

        def itercombo(w):
            if w.currentText():
                yield w.currentText()
            for i in xrange(w.count()):
                if w.itemText(i) != w.currentText():
                    yield w.itemText(i)

        s.setValue('reviewboard/summary_edit_history',
                   list(itercombo(self._qui.summary_edit))[:10])

    def _initchangesets(self, revs, selected_revs=None):
        def purerevs(revs):
            return cmdutil.revrange(self._repo,
                                    iter(str(e) for e in revs))
        if selected_revs:
             selectedrevs = purerevs(selected_revs)
        else:
             selectedrevs = purerevs(revs)

        self._changesets = _ChangesetsModel(self._repo,
                                            # TODO: [':'] is inefficient
                                            revs=purerevs(revs or [':']),
                                            selectedrevs=selectedrevs,
                                            parent=self)

        self._qui.changesets_view.setModel(self._changesets)

    @property
    def _selectedrevs(self):
        """Returns list of revisions to be sent"""
        return self._changesets.selectedrevs

    @property
    def _allrevs(self):
        """Returns list of revisions to be sent"""
        return self._changesets.revs

    def _getrepoid(self):
        comboText = self._qui.repo_id_combo.currentText().split(":")
        return str(comboText[0])

    def _getreviewid(self):
        comboText = self._qui.review_id_combo.currentText().split(":")
        return str(comboText[0])

    def _getsummary(self):
        comboText = self._qui.review_id_combo.currentText().split(":")
        return str(comboText[1])

    def _postreviewopts(self, **opts):
        """Generate opts for reviewboard by form values"""
        opts['outgoingchanges'] = self._qui.outgoing_changes_check.isChecked()
        opts['publish'] = self._qui.publish_immediately_check.isChecked()

        if self._qui.tab_widget.currentIndex() == 1:
            opts["existing"] = self._getreviewid()
            opts['update'] = self._qui.update_fields.isChecked()
            opts['summary'] = self._getsummary()
        else:
            opts['repoid'] = self._getrepoid()
            opts['summary'] = hglib.fromunicode(self._qui.summary_edit.currentText())

        if (len(self._selectedrevs) > 1):
            #Set the parent to the revision below the last one on the list
            #so all checked revisions are included in the request
            opts['parent'] = str(self._selectedrevs[0] - 1)

        # Always use the upstream repo to determine the parent diff base
        # without the diff uploaded to reviewboard dies
        # TODO: Fix this is a bug in the postreview extension
        opts['outgoing'] = True

        #Finally we want to pass the repo path to the hg extension
        opts['repository'] = self._repo.root

        return opts

    def _isvalid(self):
        """Filled all required values?"""
        if not self._qui.repo_id_combo.currentText():
            return False

        if self._qui.tab_widget.currentIndex() == 1:
            if not self._qui.review_id_combo.currentText():
                return False

        if not self._allrevs:
            return False

        return True

    @pyqtSlot()
    def tab_changed(self):
        self._qui.post_review_button.setEnabled(self._isvalid())

    @pyqtSlot()
    def toggle_outgoing_changesets(self):
        if  self._qui.changesets_view.isEnabled():
            self._initchangesets(self._allrevs, [self._selectedrevs.pop()])
            self._qui.changesets_view.setEnabled(False)
        else:
            self._initchangesets(self._allrevs, self._allrevs)
            self._qui.changesets_view.setEnabled(True)

    def accept(self):
        self._qui.progress_bar.show()
        self._qui.progress_label.setText("Posting Review...")
        self._qui.progress_label.show()

        def cmdargs(opts):
            args = []
            for k, v in opts.iteritems():
                if isinstance(v, bool):
                    if v:
                        args.append('--%s' % k.replace('_', '-'))
                else:
                    for e in isinstance(v, basestring) and [v] or v:
                        args += ['--%s' % k.replace('_', '-'), e]

            return args

        hglib.loadextension(self._ui, 'reviewboard')

        opts = self._postreviewopts()

        revstr = str(self._selectedrevs.pop())

        self._qui.post_review_button.setEnabled(False)

        self._cmd = cmdui.Dialog(['postreview'] + cmdargs(opts) + [revstr],
                                 self, self.on_completion)
        self._cmd.setWindowTitle(_('Posting Review'))
        self._cmd.show_output(False)

    @pyqtSlot()
    def on_completion(self):
        self._qui.progress_bar.hide()
        self._qui.progress_label.hide()

        output = self._cmd.core.get_rawoutput()

        saved = 'saved:' in output
        published = 'published:' in output
        if (saved or published):
            if saved:
                url = output.split('saved: ').pop().strip()
                msg = _('Review draft posted to %s\n' % url)
            else:
                url = output.split('published: ').pop().strip()
                msg = _('Review published to %s\n' % url)

            QDesktopServices.openUrl(QUrl(url))

            qtlib.InfoMsgBox(_('Review Board'), _('Success'),
                               msg, parent=self)
        else:
            error = output.split('abort: ').pop().strip()
            qtlib.ErrorMsgBox(_('Review Board'),
                              _('Error'), error)

        self._writesettings()
        super(PostReviewDialog, self).accept()

    @pyqtSlot()
    def on_settings_button_clicked(self):
        from tortoisehg.hgqt import settings

        settings.SettingsDialog(parent=self, focus='reviewboard.server').exec_()

def run(ui, *pats, **opts):
    revs = opts.get('rev') or None
    if not revs and len(pats):
        revs = pats[0]
    repo = opts.get('repo') or thgrepo.repository(ui, path=paths.find_root())

    try:
        return PostReviewDialog(repo.ui, repo, revs)
    except error.RepoLookupError, e:
        qtlib.ErrorMsgBox(_('Failed to open Review Board dialog'),
                          hglib.tounicode(e.message))

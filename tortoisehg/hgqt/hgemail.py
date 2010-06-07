# hgemail.py - TortoiseHg's dialog for sending patches via email
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
# Copyright 2010 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os, tempfile, re
from StringIO import StringIO
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from mercurial import hg, error, extensions, util, cmdutil
from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import cmdui, lexers

try:
    from tortoisehg.hgqt.ui_hgemail import Ui_EmailDialog
except ImportError:
    from PyQt4 import uic
    Ui_EmailDialog = uic.loadUiType(os.path.join(os.path.dirname(__file__),
                                                 'hgemail.ui'))[0]

class EmailDialog(QDialog):
    """Dialog for sending patches via email"""
    def __init__(self, ui, repo, revs, parent=None):
        super(EmailDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._ui = ui
        self._repo = repo
        self._revs = revs

        self._qui = Ui_EmailDialog()
        self._qui.setupUi(self)
        self._qui.bundle_radio.setEnabled(False)  # TODO: bundle support

        changesets = _ChangesetsModel(self._repo, self._purerevs, parent=self)
        self._qui.changesets_view.setModel(changesets)

        self._initpreviewtab()
        self._initintrobox()
        self._readhistory()
        self._filldefaults()
        self._connectvalidateform()
        self._validateform()
        self._readsettings()

    def keyPressEvent(self, event):
        # don't send email by just hitting enter
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() == Qt.ControlModifier:
                self.accept()  # Ctrl+Enter

            return

        super(EmailDialog, self).keyPressEvent(event)

    def closeEvent(self, event):
        self._writesettings()
        super(EmailDialog, self).closeEvent(event)

    def _readsettings(self):
        s = QSettings()
        self.restoreGeometry(s.value('email/geom').toByteArray())
        self._qui.intro_changesets_splitter.restoreState(
            s.value('email/intor_changesets_splitter').toByteArray())

    def _writesettings(self):
        s = QSettings()
        s.setValue('email/geom', self.saveGeometry())
        s.setValue('email/intor_changesets_splitter',
                   self._qui.intro_changesets_splitter.saveState())

    def _readhistory(self):
        s = QSettings()
        for k in ('to', 'cc', 'from', 'flag'):
            w = getattr(self._qui, '%s_edit' % k)
            w.addItems(s.value('email/%s_history' % k).toStringList())
            w.setCurrentIndex(-1)  # unselect

    def _writehistory(self):
        def itercombo(w):
            if w.currentText():
                yield w.currentText()
            for i in xrange(w.count()):
                if w.itemText(i) != w.currentText():
                    yield w.itemText(i)

        s = QSettings()
        for k in ('to', 'cc', 'from', 'flag'):
            w = getattr(self._qui, '%s_edit' % k)
            s.setValue('email/%s_history' % k, list(itercombo(w))[:10])

    def _filldefaults(self):
        """Fill form by default values"""
        def getfromaddr(ui):
            """Get sender address in the same manner as patchbomb"""
            addr = ui.config('email', 'from') or ui.config('patchbomb', 'from')
            if addr:
                return addr
            try:
                return ui.username()
            except error.Abort:
                return ''

        self._qui.to_edit.setEditText(
            hglib.tounicode(self._ui.config('email', 'to', '')))
        self._qui.cc_edit.setEditText(
            hglib.tounicode(self._ui.config('email', 'cc', '')))
        self._qui.from_edit.setEditText(hglib.tounicode(getfromaddr(self._ui)))

        self.setdiffformat(self._ui.configbool('diff', 'git') and 'git' or 'hg')

    def setdiffformat(self, format):
        """Set diff format, 'hg', 'git' or 'plain'"""
        try:
            radio = getattr(self._qui, '%spatch_radio' % format)
        except AttributeError:
            raise ValueError('unknown diff format: %r' % format)

        radio.setChecked(True)

    def getdiffformat(self):
        """Selected diff format"""
        for e in self._qui.patch_frame.children():
            m = re.match(r'(\w+)patch_radio', str(e.objectName()))
            if m and e.isChecked():
                return m.group(1)

        return 'hg'

    def getextraopts(self):
        """Dict of extra options"""
        opts = {}
        for e in self._qui.extra_frame.children():
            m = re.match(r'(\w+)_check', str(e.objectName()))
            if m:
                opts[m.group(1)] = e.isChecked()

        return opts

    def _patchbombopts(self, **opts):
        """Generate opts for patchbomb by form values"""
        opts['to'] = [hglib.fromunicode(self._qui.to_edit.currentText())]
        opts['cc'] = [hglib.fromunicode(self._qui.cc_edit.currentText())]
        opts['from'] = hglib.fromunicode(self._qui.from_edit.currentText())
        opts['in_reply_to'] = hglib.fromunicode(self._qui.inreplyto_edit.text())
        opts['flag'] = [hglib.fromunicode(self._qui.flag_edit.currentText())]

        def diffformat():
            n = self.getdiffformat()
            if n == 'hg':
                return {}
            else:
                return {n: True}
        opts.update(diffformat())

        opts.update(self.getextraopts())

        def writetempfile(s):
            fd, fname = tempfile.mkstemp(prefix='thg_emaildesc_')
            try:
                os.write(fd, s)
                return fname
            finally:
                os.close(fd)

        opts['intro'] = self._qui.writeintro_check.isChecked()
        if opts['intro']:
            opts['subject'] = hglib.fromunicode(self._qui.subject_edit.text())
            opts['desc'] = writetempfile(hglib.fromunicode(self._qui.body_edit.toPlainText()))
            # TODO: change patchbomb not to use temporary file

        return opts

    def _isvalid(self):
        """Filled all required values?"""
        for e in ('to_edit', 'from_edit'):
            if not getattr(self._qui, e).currentText():
                return False

        if self._qui.writeintro_check.isChecked() and not self._qui.subject_edit.text():
            return False

        # TODO: is it nice if we can choose revisions to send?
        if not self._purerevs:
            return False

        return True

    @pyqtSlot()
    def _validateform(self):
        """Check form values to update send/preview availability"""
        valid = self._isvalid()
        self._qui.send_button.setEnabled(valid)
        self._qui.main_tabs.setTabEnabled(self._previewtabindex(), valid)

    def _connectvalidateform(self):
        # TODO: connect programmatically
        for e in ('to_edit', 'from_edit'):
            getattr(self._qui, e).editTextChanged.connect(self._validateform)

        self._qui.subject_edit.textChanged.connect(self._validateform)
        self._qui.writeintro_check.toggled.connect(self._validateform)

    def accept(self):
        # TODO: want to pass patchbombopts directly
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

        hglib.loadextension(self._ui, 'patchbomb')

        opts = self._patchbombopts()
        try:
            cmd = cmdui.Dialog(['email'] + cmdargs(opts) + list(self._revs),
                               parent=self)
            cmd.setWindowTitle(_('Sending Email'))
            cmd.show_output(False)
            if cmd.exec_():
                self._writehistory()
                super(EmailDialog, self).accept()
        finally:
            if 'desc' in opts:
                os.unlink(opts['desc'])  # TODO: don't use tempfile

    def _initintrobox(self):
        self._qui.intro_box.hide()  # hidden by default
        if self._introrequired():
            self._qui.writeintro_check.setChecked(True)
            self._qui.writeintro_check.setEnabled(False)

    def _introrequired(self):
        """Is intro message required?"""
        return len(self._purerevs) > 1

    def _initpreviewtab(self):
        def initqsci(w):
            w.setUtf8(True)
            w.setReadOnly(True)
            w.setMarginWidth(1, 0)  # hide area for line numbers
            w.setLexer(lexers.DiffLexerSelector().lexer())
            # TODO: better way to setup diff lexer
        initqsci(self._qui.preview_edit)

        self._qui.main_tabs.currentChanged.connect(self._refreshpreviewtab)
        self._refreshpreviewtab(self._qui.main_tabs.currentIndex())

    @pyqtSlot(int)
    def _refreshpreviewtab(self, index):
        """Generate preview text if current tab is preview"""
        if self._previewtabindex() != index:
            return

        self._qui.preview_edit.setText(self._preview())

    def _preview(self):
        """Generate preview text by running patchbomb"""
        def loadpatchbomb():
            hglib.loadextension(self._ui, 'patchbomb')
            return extensions.find('patchbomb')

        def wrapui(ui):
            buf = StringIO()
            # TODO: common way to prepare pure ui
            newui = ui.copy()
            newui.setconfig('ui', 'interactive', False)
            newui.setconfig('diff', 'git', False)
            newui.write = lambda *args, **opts: buf.write(''.join(args))
            newui.status = lambda *args, **opts: None
            return newui, buf

        def stripheadmsg(s):
            # TODO: skip until first Content-type: line ??
            return '\n'.join(s.splitlines()[3:])

        ui, buf = wrapui(self._ui)
        opts = self._patchbombopts(test=True)
        try:
            # TODO: fix hgext.patchbomb's implementation instead
            if 'PAGER' in os.environ:
                del os.environ['PAGER']

            loadpatchbomb().patchbomb(ui, self._repo, *self._revs,
                                      **opts)
            return stripheadmsg(hglib.tounicode(buf.getvalue()))
        finally:
            if 'desc' in opts:
                os.unlink(opts['desc'])  # TODO: don't use tempfile

    def _previewtabindex(self):
        """Index of preview tab"""
        return self._qui.main_tabs.indexOf(self._qui.preview_tab)

    @util.propertycache
    def _purerevs(self):
        """Extract revranges to list of pure revision numbers"""
        return cmdutil.revrange(self._repo, self._revs)

    @pyqtSlot()
    def on_settings_button_clicked(self):
        from tortoisehg.hgqt import settings
        settings.SettingsDialog(parent=self, focus='email.from').exec_()
        # TODO: update form values and ui appropriately

class _ChangesetsModel(QAbstractTableModel):  # TODO: use component of log viewer?
    _COLUMNS = [('rev', lambda ctx: '%d:%s' % (ctx.rev(), ctx)),
                ('author', lambda ctx: hglib.username(ctx.user())),
                ('date', lambda ctx: util.shortdate(ctx.date())),
                ('description', lambda ctx: ctx.description().splitlines()[0])]

    def __init__(self, repo, revs, parent=None):
        super(_ChangesetsModel, self).__init__(parent)
        self._repo = repo
        self._revs = revs

    def data(self, index, role):
        if (not index.isValid()) or role != Qt.DisplayRole:
            return QVariant()

        coldata = self._COLUMNS[index.column()][1]
        rev = self._revs[index.row()]
        return QVariant(hglib.tounicode(coldata(self._repo[rev])))

    def rowCount(self, parent=QModelIndex()):
        return len(self._revs)

    def columnCount(self, parent=QModelIndex()):
        return len(self._COLUMNS)

    def headerData(self, section, orientation, role):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return QVariant()

        return QVariant(self._COLUMNS[section][0].capitalize())

def run(ui, *revs, **opts):
    # TODO: same options as patchbomb
    # TODO: repo should be specified as an argument?
    # TODO: if no revs specified?
    if opts.get('rev'):
        if revs:
            raise util.Abort(_('use only one form to specify the revision'))
        revs = opts.get('rev')

    repo = hg.repository(ui, paths.find_root())
    return EmailDialog(repo.ui, repo, revs)

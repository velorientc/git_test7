# hgemail.py - TortoiseHg's dialog for sending patches via email
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import sys
import gobject
import gtk
import pango
import tempfile

from mercurial import hg, ui, extensions

from thgutil.i18n import _
from thgutil import hglib, settings

from hggtk import gtklib, dialog, thgconfig, hgcmd

class EmailDialog(gtk.Window):
    """ Send patches or bundles via email """
    def __init__(self, root='', revargs=[]):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        gtklib.set_tortoise_icon(self, 'hg.ico')
        gtklib.set_tortoise_keys(self)
        self.root = root
        self.revargs = revargs

        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()

        tbuttons = [
                self._toolbutton(gtk.STOCK_GOTO_LAST, _('send'),
                                 self._on_send_clicked,
                                 _('Send email(s)')),
                self._toolbutton(gtk.STOCK_FIND, _('test'),
                                 self._on_test_clicked,
                                 _('Show email(s) which would be sent')),
                gtk.SeparatorToolItem(),
                self._toolbutton(gtk.STOCK_PREFERENCES, _('configure'),
                                 self._on_conf_clicked,
                                 _('Configure email settings'))
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        mainvbox = gtk.VBox()
        self.add(mainvbox)
        mainvbox.pack_start(self.tbar, False, False, 2)

        # set dialog title
        if revargs[0] in ('--outgoing', '-o'):
            self.set_title(_('Email outgoing changes'))
        elif revargs[0] in ('--rev', '-r'):
            self.set_title(_('Email revision(s) ') + ' '.join(revargs[1:]))
        else:
            self.set_title(_('Email Mercurial Patches'))
        self.set_default_size(650, 450)

        hbox = gtk.HBox()
        envframe = gtk.Frame(_('Envelope'))
        flagframe = gtk.Frame(_('Options'))
        hbox.pack_start(envframe, True, True, 4)
        hbox.pack_start(flagframe, False, False, 4)
        mainvbox.pack_start(hbox, False, True, 4)

        vbox = gtk.VBox()
        envframe.add(vbox)

        # To: combo box
        hbox = gtk.HBox()
        self._tolist = gtk.ListStore(str)
        self._tobox = gtk.ComboBoxEntry(self._tolist, 0)
        lbl = gtk.Label(_('To:'))
        lbl.set_property('width-chars', 10)
        lbl.set_alignment(1.0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        hbox.pack_start(self._tobox, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)

        # Cc: combo box
        hbox = gtk.HBox()
        self._cclist = gtk.ListStore(str)
        self._ccbox = gtk.ComboBoxEntry(self._cclist, 0)
        lbl = gtk.Label(_('Cc:'))
        lbl.set_property('width-chars', 10)
        lbl.set_alignment(1.0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        hbox.pack_start(self._ccbox, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)

        # From: combo box
        hbox = gtk.HBox()
        self._fromlist = gtk.ListStore(str)
        self._frombox = gtk.ComboBoxEntry(self._fromlist, 0)
        lbl = gtk.Label(_('From:'))
        lbl.set_property('width-chars', 10)
        lbl.set_alignment(1.0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        hbox.pack_start(self._frombox, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)

        hbox = gtk.HBox()
        self._replyto = gtk.Entry()
        lbl = gtk.Label(_('In-Reply-To:'))
        lbl.set_property('width-chars', 10)
        lbl.set_alignment(1.0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        hbox.pack_start(self._replyto, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)
        self.tips.set_tip(self._replyto,
            _('Message identifier to reply to, for threading'))

        vbox = gtk.VBox()
        flagframe.add(vbox)

        self.tooltips = gtk.Tooltips()
        self._normal = gtk.RadioButton(None, _('Send changesets as HG patches'))
        vbox.pack_start(self._normal, True, True, 4)
        self.tooltips.set_tip(self._normal,
                _('HG patches (as generated by export command) are compatible'
                ' with most patch programs.  They include a header which'
                ' contains the most important changeset metadata.'))

        self._git = gtk.RadioButton(self._normal,
                _('Use extended (git) patch format'))
        vbox.pack_start(self._git, True, True, 4)
        self.tooltips.set_tip(self._git,
                _('Git patches can describe binary files, copies, and'
                ' permission changes, but recipients may not be able to'
                ' use them if they are not using git or Mercurial.'))

        self._plain = gtk.RadioButton(self._normal,
                _('Plain, do not prepend HG header'))
        vbox.pack_start(self._plain, True, True, 4)
        self.tooltips.set_tip(self._plain,
                _('Stripping Mercurial header removes username and parent'
                ' information.  Only useful if recipient is not using'
                ' Mercurial (and does not like to see the headers).'))

        self._bundle = gtk.RadioButton(self._normal,
                _('Send single binary bundle, not patches'))
        vbox.pack_start(self._bundle, True, True, 4)
        self.tooltips.set_tip(self._bundle,
                _('Bundles store complete changesets in binary form.'
                ' Upstream users can pull from them. This is the safest'
                ' way to send changes to recipient Mercurial users.'))

        hbox = gtk.HBox()
        vbox.pack_start(hbox, False, False, 2)

        self._attach = gtk.CheckButton(_('attach'))
        self.tooltips.set_tip(self._attach,
                _('send patches as attachments'))
        self._inline = gtk.CheckButton(_('inline'))
        self.tooltips.set_tip(self._inline,
                _('send patches as inline attachments'))
        self._diffstat = gtk.CheckButton(_('diffstat'))
        self.tooltips.set_tip(self._diffstat,
                _('add diffstat output to messages'))
        hbox.pack_start(self._attach, True, True, 2)
        hbox.pack_start(self._inline, True, True, 2)
        hbox.pack_start(self._diffstat, True, True, 2)

        vbox = gtk.VBox()
        hbox = gtk.HBox()
        self._subjlist = gtk.ListStore(str)
        self._subjbox = gtk.ComboBoxEntry(self._subjlist, 0)
        hbox.pack_start(gtk.Label(_('Subject:')), False, False, 4)
        hbox.pack_start(self._subjbox, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)

        self.descview = gtk.TextView(buffer=None)
        self.descview.set_editable(True)
        self.descview.modify_font(pango.FontDescription('Monospace'))
        self.descbuffer = self.descview.get_buffer()
        gtklib.addspellcheck(self.descview)
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.add(self.descview)
        frame = gtk.Frame(_('Patch Series (Bundle) Description'))
        frame.set_border_width(4)
        vbox.pack_start(scrolledwindow, True, True, 4)
        vbox.set_border_width(4)
        eventbox = gtk.EventBox()
        eventbox.add(vbox)
        frame.add(eventbox)
        self._eventbox = eventbox
        mainvbox.pack_start(frame, True, True, 4)
        gobject.idle_add(self._refresh, True)

    def _toolbutton(self, stock, label, handler, tip):
        tbutton = gtk.ToolButton(stock)
        tbutton.set_label(label)
        tbutton.set_tooltip(self.tips, tip)
        tbutton.connect('clicked', handler)
        return tbutton

    def _refresh(self, initial):
        def fill_history(history, vlist, cpath):
            vlist.clear()
            if cpath not in history.get_keys():
                return
            for v in history.get_value(cpath):
                vlist.append([v])

        history = settings.Settings('email')
        try:
            repo = hg.repository(ui.ui(), path=self.root)
            self.repo = repo
        except hglib.RepoError:
            self.repo = None
            return

        extensions.load(self.repo.ui, 'patchbomb', None)

        if initial:
            # Only zap these fields at startup
            self._tobox.child.set_text(hglib.fromutf(repo.ui.config('email', 'to', '')))
            self._ccbox.child.set_text(hglib.fromutf(repo.ui.config('email', 'cc', '')))
            self._frombox.child.set_text(hglib.fromutf(repo.ui.config('email', 'from', '')))
            self._subjbox.child.set_text(hglib.fromutf(repo.ui.config('email', 'subject', '')))
            self.tooltips.set_tip(self._eventbox,
                    _('Patch series description is sent in initial summary'
                    ' email with [PATCH 0 of N] subject.  It should describe'
                    ' the effects of the entire patch series.  When emailing'
                    ' a bundle, these fields make up the message subject and body.')
                    )
        fill_history(history, self._tolist, 'email.to')
        fill_history(history, self._cclist, 'email.cc')
        fill_history(history, self._fromlist, 'email.from')
        fill_history(history, self._subjlist, 'email.subject')

        # See if user has set flags in defaults.email
        self._git.set_sensitive(True)
        self._bundle.set_sensitive(True)
        self._plain.set_sensitive(True)
        self._inline.set_sensitive(True)
        self._attach.set_sensitive(True)
        self._diffstat.set_sensitive(True)
        defaults = repo.ui.config('defaults', 'email', '').split()
        for flag in defaults:
            if flag in ('-g', '--git'):
                self._git.set_active(True)
                self._git.set_sensitive(False)
            if flag in ('-b', '--bundle'):
                self._bundle.set_active(True)
                self._bundle.set_sensitive(False)
            if flag in ('--plain'):
                self._plain.set_active(True)
                self._plain.set_sensitive(False)
            if flag in ('i', '--inline'):
                self._inline.set_active(True)
                self._inline.set_sensitive(False)
            if flag in ('a', '--attach'):
                self._attach.set_active(True)
                self._attach.set_sensitive(False)
            if flag in ('d', '--diffstat'):
                self._diffstat.set_active(True)
                self._diffstat.set_sensitive(False)

    def _on_conf_clicked(self, button):
        dlg = thgconfig.ConfigDialog(False)
        dlg.show_all()
        dlg.focus_field('email.from')
        dlg.run()
        dlg.hide()
        self._refresh(False)

    def _on_send_clicked(self, button):
        self.send()

    def _on_test_clicked(self, button):
        self.send(True)

    def send(self, test = False):
        def record_new_value(cpath, history, newvalue):
            if not newvalue: return
            if cpath not in history.get_keys():
                history.set_value(cpath, [])
            elif newvalue in history.get_value(cpath):
                history.get_value(cpath).remove(newvalue)
            history.get_value(cpath).insert(0, newvalue)

        totext = hglib.fromutf(self._tobox.child.get_text())
        cctext = hglib.fromutf(self._ccbox.child.get_text())
        fromtext = hglib.fromutf(self._frombox.child.get_text())
        subjtext = hglib.fromutf(self._subjbox.child.get_text())
        inreplyto = hglib.fromutf(self._replyto.get_text())

        if not totext:
            dialog.info_dialog(self, _('Info required'),
                        _('You must specify a recipient'))
            self._tobox.grab_focus()
            return
        if not fromtext:
            dialog.info_dialog(self, _('Info required'),
                        _('You must specify a sender address'))
            self._frombox.grab_focus()
            return
        if not self.repo:
            return

        if self.repo.ui.config('email', 'method', 'smtp') == 'smtp' and not test:
            if not self.repo.ui.config('smtp', 'host'):
                dialog.info_dialog(self, _('Info required'),
                            _('You must configure SMTP'))
                dlg = thgconfig.ConfigDialog(False)
                dlg.show_all()
                dlg.focus_field('smtp.host')
                dlg.run()
                dlg.hide()
                self._refresh(False)
                return

        if not test:
            history = settings.Settings('email')
            record_new_value('email.to', history, totext)
            record_new_value('email.cc', history, cctext)
            record_new_value('email.from', history, fromtext)
            record_new_value('email.subject', history, subjtext)
            history.write()

        cmdline = ['hg', 'email', '-f', fromtext, '-t', totext, '-c', cctext]
        oldpager = os.environ.get('PAGER')
        if test:
            if oldpager:
                del os.environ['PAGER']
            cmdline.insert(2, '--test')
        if subjtext:
            cmdline += ['--subject', subjtext]
        if self._bundle.get_active():
            cmdline += ['--bundle']
            if '--outgoing' in self.revargs:
                self.revargs.remove('--outgoing')
        elif self._plain.get_active():  cmdline += ['--plain']
        elif self._git.get_active():    cmdline += ['--git']
        if self._inline.get_active():   cmdline += ['--inline']
        if self._attach.get_active():   cmdline += ['--attach']
        if self._diffstat.get_active(): cmdline += ['--diffstat']
        if inreplyto:
            cmdline += ['--in-reply-to', inreplyto]
        start = self.descbuffer.get_start_iter()
        end = self.descbuffer.get_end_iter()
        desc = self.descbuffer.get_text(start, end)
        if desc:
            cmdline += ['--intro']
        tmpfile = None
        try:
            fd, tmpfile = tempfile.mkstemp(prefix="thg_emaildesc_")
            os.write(fd, desc)
            os.close(fd)
            cmdline += ['--desc', tmpfile]
            cmdline.extend(self.revargs)

            dlg = hgcmd.CmdDialog(cmdline)
            dlg.show_all()
            dlg.run()
            dlg.hide()
        finally:
            if oldpager:
                os.environ['PAGER'] = oldpager
            if tmpfile:
                os.unlink(tmpfile)


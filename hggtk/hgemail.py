#
# hgemail.py - TortoiseHg's dialog for sending patches via email
#
# Copyright (C) 2007 Steve Borho <steve@borho.org>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import sys
import gtk
import pango
import shelve
import shlib
from tempfile import mkstemp
from dialog import *
from mercurial import hg, ui, extensions
from mercurial.repo import RepoError
from thgconfig import ConfigDialog
from hgcmd import CmdDialog

class EmailDialog(gtk.Window):
    """ Send patches or bundles via email """
    def __init__(self, root='', revargs=[]):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        shlib.set_tortoise_icon(self, 'hg.ico')
        self.root = root
        self.revargs = revargs
        
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()

        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)
        self._btn_close = self._toolbutton(gtk.STOCK_CLOSE, 'Close',
                self._close_clicked, 'Close Window')

        tbuttons = [
                self._toolbutton(gtk.STOCK_GOTO_LAST, 'Send',
                                 self._on_send_clicked,
                                 'Send email(s)'),
                gtk.SeparatorToolItem(),
                self._toolbutton(gtk.STOCK_PREFERENCES, 'configure',
                                 self._on_conf_clicked,
                                 'Configure email settings'),
                sep,
                self._btn_close
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        mainvbox = gtk.VBox()
        self.add(mainvbox)
        mainvbox.pack_start(self.tbar, False, False, 2)

        # set dialog title
        if revargs[0] in ('--outgoing', '-o'):
            self.set_title('Email outgoing changes')
        elif revargs[0] in ('--rev', '-r'):
            self.set_title('Email revision(s) ' + ' '.join(revargs[1:]))
        else:
            self.set_title('Email Mercurial Patches')
        self.set_default_size(630, 400)

        hbox = gtk.HBox()
        envframe = gtk.Frame('Envelope')
        flagframe = gtk.Frame('Options')
        hbox.pack_start(envframe, True, True, 4)
        hbox.pack_start(flagframe, False, False, 4)
        mainvbox.pack_start(hbox, False, True, 4)

        vbox = gtk.VBox()
        envframe.add(vbox)

        # To: combo box
        hbox = gtk.HBox()
        self._tolist = gtk.ListStore(str)
        self._tobox = gtk.ComboBoxEntry(self._tolist, 0)
        lbl = gtk.Label('To:')
        lbl.set_property("width-chars", 5)
        lbl.set_alignment(1.0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        hbox.pack_start(self._tobox, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)

        # Cc: combo box
        hbox = gtk.HBox()
        self._cclist = gtk.ListStore(str)
        self._ccbox = gtk.ComboBoxEntry(self._cclist, 0)
        lbl = gtk.Label('Cc:')
        lbl.set_property("width-chars", 5)
        lbl.set_alignment(1.0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        hbox.pack_start(self._ccbox, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)

        # From: combo box
        hbox = gtk.HBox()
        self._fromlist = gtk.ListStore(str)
        self._frombox = gtk.ComboBoxEntry(self._fromlist, 0)
        lbl = gtk.Label('From:')
        lbl.set_property("width-chars", 5)
        lbl.set_alignment(1.0, 0.5)
        hbox.pack_start(lbl, False, False, 4)
        hbox.pack_start(self._frombox, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)

        vbox = gtk.VBox()
        flagframe.add(vbox)

        self.tooltips = gtk.Tooltips()
        self._normal = gtk.RadioButton(None, "Send changesets as HG patches")
        vbox.pack_start(self._normal, True, True, 4)
        self.tooltips.set_tip(self._normal, 
                'HG patches (as generated by export command) are compatible'
                ' with most patch programs.  They include a header which'
                ' contains the most important changeset metadata.')

        self._git = gtk.RadioButton(self._normal,
                "Use extended (git) patch format")
        vbox.pack_start(self._git, True, True, 4)
        self.tooltips.set_tip(self._git, 
                'Git patches can describe binary files, copies, and'
                ' permission changes, but recipients may not be able to'
                ' use them if they are not using git or Mercurial.')

        self._plain = gtk.RadioButton(self._normal,
                "Plain, do not prepend HG header")
        vbox.pack_start(self._plain, True, True, 4)
        self.tooltips.set_tip(self._plain, 
                'Stripping Mercurial header removes username and parent'
                ' information.  Only useful if recipient is not using'
                ' Mercurial (and does not like to see the headers).')

        self._bundle = gtk.RadioButton(self._normal,
                "Send single binary bundle, not patches")
        vbox.pack_start(self._bundle, True, True, 4)
        self.tooltips.set_tip(self._bundle, 
                'Bundles store complete changesets in binary form.'
                ' Upstream users can pull from them. This is the safest'
                ' way to send changes to recipient Mercurial users.')

        vbox = gtk.VBox()
        hbox = gtk.HBox()
        self._subjlist = gtk.ListStore(str)
        self._subjbox = gtk.ComboBoxEntry(self._subjlist, 0)
        hbox.pack_start(gtk.Label('Subject:'), False, False, 4)
        hbox.pack_start(self._subjbox, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)

        self.descview = gtk.TextView(buffer=None)
        self.descview.set_editable(True)
        self.descview.modify_font(pango.FontDescription("Monospace"))
        self.descbuffer = self.descview.get_buffer()
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.add(self.descview)
        frame = gtk.Frame('Patch Series (Bundle) Description')
        frame.set_border_width(4)
        vbox.pack_start(scrolledwindow, True, True, 4)
        vbox.set_border_width(4)
        eventbox = gtk.EventBox()
        eventbox.add(vbox)
        frame.add(eventbox)
        self.tooltips.set_tip(eventbox, 
                'Patch series description is sent in initial summary'
                ' email with [PATCH 0 of N] subject.  It should describe'
                ' the effects of the entire patch series.  When emailing'
                ' a bundle, these fields make up the message subject and body.'
                ' The description field is unused when sending a single patch')
        mainvbox.pack_start(frame, True, True, 4)

        self.connect('map_event', self._on_window_map_event)

    def _close_clicked(self, toolbutton, data=None):
        self.destroy()

    def _toolbutton(self, stock, label, handler, tip):
        tbutton = gtk.ToolButton(stock)
        tbutton.set_label(label)
        tbutton.set_tooltip(self.tips, tip)
        tbutton.connect('clicked', handler)
        return tbutton
        
    def _on_window_map_event(self, event, param):
        self._refresh(True)

    def _refresh(self, initial):
        def fill_history(history, vlist, cpath):
            vlist.clear()
            if cpath not in history.get_keys():
                return
            for v in history.get_value(cpath):
                vlist.append([v])

        history = shlib.Settings('config_history')
        try:
            repo = hg.repository(ui.ui(), path=self.root)
            self.repo = repo
        except RepoError:
            self.repo = None
            return

        for name, module in extensions.extensions():
            if name == 'patchbomb':
                break
        else:
            error_dialog(self, 'Email not enabled',
                    'You must enable the patchbomb extension to use this tool')
            self.response(gtk.RESPONSE_CANCEL)

        if initial:
            # Only zap these fields at startup
            self._tobox.child.set_text(repo.ui.config('email', 'to', ''))
            self._ccbox.child.set_text(repo.ui.config('email', 'cc', ''))
            self._frombox.child.set_text(repo.ui.config('email', 'from', ''))
            self._subjbox.child.set_text(repo.ui.config('email', 'subject', ''))
        fill_history(history, self._tolist, 'email.to')
        fill_history(history, self._cclist, 'email.cc')
        fill_history(history, self._fromlist, 'email.from')
        fill_history(history, self._subjlist, 'email.subject')

        # See if user has set flags in defaults.email
        self._git.set_sensitive(True)
        self._bundle.set_sensitive(True)
        self._plain.set_sensitive(True)
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

    def _on_conf_clicked(self, button):
        dlg = ConfigDialog(self.root, False)
        dlg.show_all()
        dlg.focus_field('email.from')
        dlg.run()
        dlg.hide()
        self._refresh(False)

    def _on_send_clicked(self, button):
        def record_new_value(cpath, history, newvalue):
            if not newvalue: return
            if cpath not in history.get_keys():
                history.set_value(cpath, [])
            elif newvalue in history.get_value(cpath):
                history.get_value(cpath).remove(newvalue)
            history.get_value(cpath).insert(0, newvalue)

        totext = self._tobox.child.get_text()
        cctext = self._ccbox.child.get_text()
        fromtext = self._frombox.child.get_text()
        subjtext = self._subjbox.child.get_text()

        if not totext:
            info_dialog(self, 'Info required', 'You must specify a recipient')
            self._tobox.grab_focus()
            return
        if not fromtext:
            info_dialog(self, 'Info required', 'You must specify a sender address')
            self._frombox.grab_focus()
            return
        if not self.repo:
            return

        if self.repo.ui.config('email', 'method', 'smtp') == 'smtp':
            if not self.repo.ui.config('smtp', 'host'):
                info_dialog(self, 'Info required', 'You must configure SMTP')
                dlg = ConfigDialog(self.root, False)
                dlg.show_all()
                dlg.focus_field('smtp.host')
                dlg.run()
                dlg.hide()
                self._refresh(False)
                return

        history = shlib.Settings('config_history')
        record_new_value('email.to', history, totext)
        record_new_value('email.cc', history, cctext)
        record_new_value('email.from', history, fromtext)
        record_new_value('email.subject', history, subjtext)
        history.write()

        cmdline = ['hg', 'email', '-f', fromtext, '-t', totext, '-c', cctext]
        cmdline += ['--repository', self.repo.root]
        if subjtext:
            cmdline += ['--subject', subjtext]
        if self._bundle.get_active():
            cmdline += ['--bundle']
            if '--outgoing' in self.revargs:
                self.revargs.remove('--outgoing')
        elif self._plain.get_active():  cmdline += ['--plain']
        elif self._git.get_active():    cmdline += ['--git']
        start = self.descbuffer.get_start_iter()
        end = self.descbuffer.get_end_iter()
        desc = self.descbuffer.get_text(start, end)
        try:
            fd, tmpfile = mkstemp(prefix="thg_emaildesc_")
            os.write(fd, desc)
            os.close(fd)
            cmdline += ['--desc', tmpfile]
            cmdline.extend(self.revargs)

            dlg = CmdDialog(cmdline)
            dlg.show_all()
            dlg.run()
            dlg.hide()
        finally:
            os.unlink(tmpfile)

def run(root='', **opts):
    # In most use cases, this dialog will be launched by other
    # hggtk tools like glog and synch.  It's not expected to be
    # used from hgproc or the command line.  I leave this path in
    # place for testing purposes.
    dialog = EmailDialog(root, ['tip'])
    dialog.show_all()
    dialog.connect('destroy', gtk.main_quit)
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or os.getcwd()
    run(**opts)

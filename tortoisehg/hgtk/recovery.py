# recovery.py - Repository recovery dialog for TortoiseHg
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import gobject
import pango
import Queue
import os
import time

from mercurial import hg, ui, error

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, shlib, paths

from tortoisehg.hgtk import gdialog, dialog, gtklib, hgthread, statusbar

class RecoveryDialog(gtk.Window):
    def __init__(self):
        """ Initialize the Dialog. """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        gtklib.set_tortoise_icon(self, 'general.ico')
        gtklib.set_tortoise_keys(self)
        self.set_default_size(600, 400)
        self.connect('delete-event', self._delete)
        self.hgthread = None

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except error.RepoError:
            gtklib.idle_add_single_call(self.destroy)
            return
        self.repo = repo
        self.reponame = hglib.get_reponame(repo)
        self.set_title(_('%s - recovery') % self.reponame)

        # toolbar
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()
        self._stop_button = self._toolbutton(gtk.STOCK_STOP,
                _('Stop'), self._stop_clicked, tip=_('Stop the hg operation'))
        self._stop_button.set_sensitive(False)
        tbuttons = [
                self._toolbutton(gtk.STOCK_CLEAR,
                                 _('Clean'),
                                 self._clean_clicked,
                                 tip=_('Clean checkout, undo all changes')),
                gtk.SeparatorToolItem(),
                self._toolbutton(gtk.STOCK_UNDO,
                                 _('Rollback'),
                                 self._rollback_clicked,
                                 tip=_('Rollback (undo) last transaction to'
                                     ' repository (pull, commit, etc)')),
                gtk.SeparatorToolItem(),
                self._toolbutton(gtk.STOCK_CLEAR,
                                 _('Recover'),
                                 self._recover_clicked,
                                 tip=_('Recover from interrupted operation')),
                gtk.SeparatorToolItem(),
                self._toolbutton(gtk.STOCK_APPLY,
                                 _('Verify'),
                                 self._verify_clicked,
                                 tip=_('Validate repository consistency')),
                gtk.SeparatorToolItem(),
                self._stop_button,
                gtk.SeparatorToolItem(),
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        vbox = gtk.VBox()
        self.add(vbox)
        vbox.pack_start(self.tbar, False, False, 2)

        # hg output window
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.textview = gtk.TextView(buffer=None)
        self.textview.set_editable(False)
        fontlog = hglib.getfontconfig()['fontlog']
        self.textview.modify_font(pango.FontDescription(fontlog))
        scrolledwindow.add(self.textview)
        self.textbuffer = self.textview.get_buffer()
        self.textbuffer.create_tag('error', weight=pango.WEIGHT_HEAVY,
                                   foreground=gtklib.DRED)
        vbox.pack_start(scrolledwindow, True, True)

        self.stbar = statusbar.StatusBar()
        vbox.pack_start(self.stbar, False, False, 2)

    def _delete(self, widget, event):
        if not self.should_live():
            self.destroy()
        return True

    def should_live(self):
        if self._cmd_running():
            dialog.error_dialog(self, _('Cannot close now'),
                    _('command is running'))
            return True
        return False

    def _toolbutton(self, stock, label, handler,
                    menu=None, userdata=None, tip=None):
        if menu:
            tbutton = gtk.MenuToolButton(stock)
            tbutton.set_menu(menu)
        else:
            tbutton = gtk.ToolButton(stock)

        tbutton.set_label(label)
        if tip:
            tbutton.set_tooltip(self.tips, tip)
        tbutton.connect('clicked', handler, userdata)
        return tbutton

    def _clean_clicked(self, toolbutton, data=None):
        response = gdialog.Confirm(_('Confirm clean repository'), [], self,
                _("Clean repository '%s' ?") % self.reponame).run()
        if response != gtk.RESPONSE_YES:
            return
        pl = self.repo.parents()
        cmd = ['update', '--clean', '--rev', str(pl[0].rev())]
        self._exec_cmd(cmd, postfunc=self._notify)

    def _notify(self, ret, *args):
        time.sleep(0.5)     # give fs some time to pick up changes
        shlib.shell_notify([self.repo.root])

    def _rollback_clicked(self, toolbutton, data=None):
        response = gdialog.Confirm(_('Confirm rollback repository'), [], self,
                _("Rollback repository '%s' ?") % self.reponame).run()
        if response != gtk.RESPONSE_YES:
            return
        cmd = ['rollback']
        self._exec_cmd(cmd, postfunc=self._notify)

    def _recover_clicked(self, toolbutton, data=None):
        cmd = ['recover']
        self._exec_cmd(cmd)

    def _verify_clicked(self, toolbutton, data=None):
        cmd = ['verify']
        self._exec_cmd(cmd)

    def _stop_clicked(self, toolbutton, data=None):
        if self.hgthread and self.hgthread.isAlive():
            try:
                self.hgthread.terminate()
            except ValueError:
                pass # race, thread was already terminated
            self._stop_button.set_sensitive(False)

    def _exec_cmd(self, cmd, postfunc=None):
        if self._cmd_running():
            dialog.error_dialog(self, _('Cannot run now'),
                _('Please try again after the previous command is completed'))
            return

        self._stop_button.set_sensitive(True)
        cmdline = cmd
        cmdline.append('--verbose')
        cmdline.append('--repository')
        cmdline.append(self.repo.root)

        # show command to be executed
        self.write("", False)

        # execute command and show output on text widget
        gobject.timeout_add(10, self.process_queue)
        self.hgthread = hgthread.HgThread(cmdline, postfunc)
        self.hgthread.start()
        self.stbar.begin()
        self.stbar.set_text('hg ' + ' '.join(cmdline))

    def _cmd_running(self):
        if self.hgthread and self.hgthread.isAlive():
            return True
        else:
            return False

    def write(self, msg, append=True):
        msg = hglib.toutf(msg)
        if append:
            enditer = self.textbuffer.get_end_iter()
            self.textbuffer.insert(enditer, msg)
        else:
            self.textbuffer.set_text(msg)

    def write_err(self, msg):
        enditer = self.textbuffer.get_end_iter()
        self.textbuffer.insert_with_tags_by_name(enditer, msg, 'error')
        self.textview.scroll_to_mark(self.textbuffer.get_insert(), 0)

    def process_queue(self):
        """
        Handle all the messages currently in the queue (if any).
        """
        self.hgthread.process_dialogs()
        while self.hgthread.getqueue().qsize():
            try:
                msg = self.hgthread.getqueue().get(0)
                self.write(msg)
            except Queue.Empty:
                pass
        while self.hgthread.geterrqueue().qsize():
            try:
                msg = self.hgthread.geterrqueue().get(0)
                self.write_err(msg)
            except Queue.Empty:
                pass

        if self._cmd_running():
            return True
        else:
            self.stbar.end()
            self._stop_button.set_sensitive(False)
            if self.hgthread.return_code() is None:
                self.write_err(_('[command interrupted]'))
            return False # Stop polling this function

def run(ui, *pats, **opts):
    return RecoveryDialog()

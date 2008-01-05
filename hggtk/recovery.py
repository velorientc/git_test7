#
# Repository recovery dialog for TortoiseHg
#
# Copyright (C) 2007 Steve Borho <steve@borho.org>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

try:
    import pygtk
    pygtk.require("2.0")
except:
    pass

import gtk
import gobject
import pango
import Queue
import os
import threading
from mercurial import hg, ui, util 
from mercurial.node import *
from dialog import error_dialog
from hglib import HgThread
from shlib import set_tortoise_icon, shell_notify

class RecoveryDialog(gtk.Dialog):
    def __init__(self, cwd='', root=''):
        """ Initialize the Dialog. """
        gtk.Dialog.__init__(self, parent=None,
                                  flags=0,
                                  buttons=())

        set_tortoise_icon(self, 'general.ico')
        self.root = root
        self.cwd = cwd
        self.selected_path = None

        self.set_default_size(600, 400)

        self.paths = self._get_paths()
        name = os.path.basename(os.path.abspath(root))
        self.set_title("TortoiseHg Recovery - " + name)

        self.connect('delete-event', self._delete)
        self.connect('response', self._response)

        self._btn_close = gtk.Button("Close")
        self._btn_close.connect('clicked', self._close_clicked)
        self.action_area.pack_end(self._btn_close)

        # toolbar
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()
        tbuttons = [
                self._toolbutton(gtk.STOCK_UNDO,
                                 'rollback', 
                                 self._rollback_clicked,
                                 tip='Rollback (undo) last transaction to local'
                                 ' repository (pull, commit, etc)'),
                gtk.SeparatorToolItem(),
                self._toolbutton(gtk.STOCK_CLEAR,
                                 'recover',
                                 self._recover_clicked,
                                 tip='Recover from interrupted operation.'
                                 ' Only required if specifically requested'),
                gtk.SeparatorToolItem(),
                self._toolbutton(gtk.STOCK_APPLY,
                                 'verify',
                                 self._verify_clicked,
                                 tip='Validate repository consistency'),
                gtk.SeparatorToolItem(),
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        self.vbox.pack_start(self.tbar, False, False, 2)
        
        # hg output window
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.textview = gtk.TextView(buffer=None)
        self.textview.set_editable(False)
        self.textview.modify_font(pango.FontDescription("Monospace"))
        scrolledwindow.add(self.textview)
        self.textview.set_editable(False)
        self.textbuffer = self.textview.get_buffer()
        self.vbox.pack_start(scrolledwindow, True, True)

    def _get_paths(self):
        """ retrieve repo revisions """
        try:
            self.repo = hg.repository(ui.ui(), path=self.root)
            return self.repo.ui.configitems('paths')
        except hg.RepoError:
            return None
        
    def _close_clicked(self, *args):
        if threading.activeCount() != 1:
            error_dialog("Can't close now", "command is running")
        else:
            self.response(gtk.RESPONSE_CLOSE)
        
    def _delete(self, widget, event):
        return True
        
    def _response(self, widget, response_id):
        if threading.activeCount() != 1:
            error_dialog("Can't close now", "command is running")
            widget.emit_stop_by_name('response')
        else:
            gtk.main_quit()
    
    def _toolbutton(self, stock, label, handler,
                    menu=None, userdata=None, tip=None):
        if menu:
            tbutton = gtk.MenuToolButton(stock)
            tbutton.set_menu(menu)
        else:
            tbutton = gtk.ToolButton(stock)
            
        if tip:
            self.tips.set_tip(tbutton, tip)
        tbutton.set_label(label)
        tbutton.connect('clicked', handler, userdata)
        return tbutton
        
    def _rollback_clicked(self, toolbutton, data=None):
        def notify(ret, *args):
            import time
            time.sleep(0.5)     # give fs some time to pick up changes
            shell_notify([self.cwd])
        cmd = ['rollback']
        self._exec_cmd(cmd, postfunc=notify)
        
    def _recover_clicked(self, toolbutton, data=None):
        cmd = ['recover']
        self._exec_cmd(cmd)
        
    def _verify_clicked(self, toolbutton, data=None):
        cmd = ['verify']
        self._exec_cmd(cmd)
    
    def _exec_cmd(self, cmd, postfunc=None):            
        cmdline = cmd
        cmdline.append('--verbose')
        cmdline.append('--repository')
        cmdline.append(self.root)
        
        # show command to be executed
        self.write("", False)
        #self.write("$ %s\n" % ' '.join(cmdline))

        # execute command and show output on text widget
        gobject.timeout_add(10, self.process_queue)
        self.hgthread = HgThread(cmdline, postfunc)
        self.hgthread.start()
        
    def write(self, msg, append=True):
        msg = unicode(msg, 'iso-8859-1')
        if append:
            enditer = self.textbuffer.get_end_iter()
            self.textbuffer.insert(enditer, msg)
        else:
            self.textbuffer.set_text(msg)

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
        if threading.activeCount() == 1:
            return False # Stop polling this function
        else:
            return True

def run(cwd='', root='', **opts):
    dialog = RecoveryDialog(cwd, root)
    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()
    
if __name__ == "__main__":
    import sys
    run(*sys.argv[1:])

#
# Repository synchronization dialog for TortoiseHg
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
import subprocess
import os
import threading
from mercurial import hg, ui, util 
from mercurial.node import *
from hglib import rootpath
from dialog import error_dialog

class SynchDialog(gtk.Dialog):
    def __init__(self, cwd='', repos=[]):
        """ Initialize the Dialog. """
        rootbase = os.path.basename(cwd)
        gtk.Dialog.__init__(self, title="TortoiseHg Synchronize - %s" % rootbase,
                                  parent=None,
                                  flags=0,
                                  buttons=())
        self.root = rootpath(cwd)
        self.selected_path = None
        self.thread1 = None
        self.queue = Queue.Queue()

        try:
            self.repo = hg.repository(ui.ui(), path=self.root)
        except hg.RepoError:
            return None

        self.set_default_size(600, 400)

        #self.connect('delete-event', lambda x, y: True)
        self.connect('delete-event', self._delete)
        self.connect('response', self._response)

        self._btn_close = gtk.Button("Close")
        self._btn_close.connect('clicked', self._close_clicked)
        self.action_area.pack_end(self._btn_close)

        # toolbar
        self.tbar = gtk.Toolbar()
        tbuttons = [
                self._toolbutton(gtk.STOCK_GO_DOWN,
                                 'incoming', 
                                 self._incoming_clicked,
                                 self._incoming_menu()),
                self._toolbutton(gtk.STOCK_GOTO_BOTTOM,
                                 'pull',
                                 self._pull_clicked,
                                 self._pull_menu()),
                gtk.SeparatorToolItem(),
                self._toolbutton(gtk.STOCK_GO_UP,
                                 'outgoing',
                                 self._outgoing_clicked,
                                 self._outgoing_menu()),
                self._toolbutton(gtk.STOCK_GOTO_TOP,
                                 'push',
                                 self._push_clicked,
                                 self._push_menu()),
                gtk.SeparatorToolItem(),
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        self.vbox.pack_start(self.tbar, False, False, 2)
        
        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Button("Remote Path:")
        lbl.unset_flags(gtk.CAN_FOCUS)
        lbl.connect('clicked', self._btn_remotepath_clicked)
        
        # revisions  combo box
        revlist = gtk.ListStore(str)
        self._pathbox = gtk.ComboBoxEntry(revlist, 0)
        self._pathtext = self._pathbox.get_child()
        
        self.paths = self._get_paths()
        defrow = None
        defpushrow = None
        for row, (name, path) in enumerate(self.paths):
            if name == 'default':
                defrow = row
                if defpushrow is None:
                    defpushrow = row
            elif name == 'default-push':
                defpushrow = row
            revlist.append([path])

        if repos:
            self._pathtext.set_text(repos[0])
        elif defrow is not None:
            self._pathbox.set_active(defrow)
        elif defpushrow is not None:
            self._pathbox.set_active(defpushrow)

        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self._pathbox, True, True)
        self.vbox.pack_start(revbox, False, False, 2)

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
        
    def _pull_menu(self):
        menu = gtk.Menu()
           
        self._pull_update = gtk.CheckMenuItem("Update to new tip")
        menu.append(self._pull_update)

        self._pull_force = gtk.CheckMenuItem("Force pull")
        menu.append(self._pull_force)
        
        menu.show_all()
        return menu
        
    def _push_menu(self):
        menu = gtk.Menu()
        
        self._push_force = gtk.CheckMenuItem("Force push")
        menu.append(self._push_force)
        
        menu.show_all()
        return menu
        
    def _incoming_menu(self):
        menu = gtk.Menu()

        self._incoming_show_patch = gtk.CheckMenuItem("Show patch")
        menu.append(self._incoming_show_patch)
        
        self._incoming_no_merges = gtk.CheckMenuItem("Do not show merges")
        menu.append(self._incoming_no_merges)

        self._incoming_newest = gtk.CheckMenuItem("Show newest record first")
        menu.append(self._incoming_newest)

        self._incoming_force = gtk.CheckMenuItem("Force incoming")
        menu.append(self._incoming_force)
        
        menu.show_all()
        return menu
        
    def _outgoing_menu(self):
        menu = gtk.Menu()

        self._outgoing_show_patch = gtk.CheckMenuItem("Show patch")
        menu.append(self._outgoing_show_patch)
        
        self._outgoing_no_merges = gtk.CheckMenuItem("Do not show merges")
        menu.append(self._outgoing_no_merges)

        self._outgoing_newest = gtk.CheckMenuItem("Show newest record first")
        menu.append(self._outgoing_newest)
        
        self._outgoing_force = gtk.CheckMenuItem("Force incoming")
        menu.append(self._outgoing_force)
        
        menu.show_all()
        return menu
        
    def _get_paths(self):
        """ retrieve repo revisions """
        try:
            repo = hg.repository(ui.ui(), path=self.root)
            return repo.ui.configitems('paths')
        except hg.RepoError:
            return None

    def _btn_remotepath_clicked(self, button):
        """ select source folder to clone """
        dialog = gtk.FileChooserDialog(title="Select Repository",
                action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,
                         gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        dialog.set_default_response(gtk.RESPONSE_OK)
        dialog.set_current_folder(self.root)
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            self._pathtext.set_text(dialog.get_filename())
        dialog.destroy()
        
    def _close_clicked(self, *args):
        if self.thread1 and self.thread1.isAlive():
            error_dialog("Can't close now", "command is running")
        else:
            self.response(gtk.RESPONSE_CLOSE)
        
    def _delete(self, widget, event):
        return True
        
    def _response(self, widget, response_id):
        if self.thread1 and self.thread1.isAlive():
            error_dialog("Can't close now", "command is running")
            widget.emit_stop_by_name('response')
        else:
            gtk.main_quit()
    
    def _toolbutton(self, stock, label, handler, menu=None, userdata=None):
        if menu:
            tbutton = gtk.MenuToolButton(stock)
            tbutton.set_menu(menu)
        else:
            tbutton = gtk.ToolButton(stock)
            
        tbutton.set_label(label)
        tbutton.connect('clicked', handler, userdata)
        return tbutton
        
    def _pull_clicked(self, toolbutton, data=None):
        cmd = 'pull'
        if self._pull_update.get_active():
            cmd += " --update"
        if self._pull_force.get_active():
            cmd += " --force"
        self._exec_cmd(cmd)
    
    def _push_clicked(self, toolbutton, data=None):
        cmd = 'push'
        if self._push_force.get_active():
            cmd += " --force"
        self._exec_cmd(cmd)
        
    def _incoming_clicked(self, toolbutton, data=None):
        cmd = 'incoming'
        if self._incoming_show_patch.get_active():
            cmd += " --patch"
        if self._incoming_no_merges.get_active():
            cmd += " --no-merges"
        if self._incoming_force.get_active():
            cmd += " --force"
        if self._incoming_newest.get_active():
            cmd += " --newest-first"
        self._exec_cmd(cmd)
        
    def _outgoing_clicked(self, toolbutton, data=None):
        cmd = 'outgoing'
        if self._outgoing_show_patch.get_active():
            cmd += " --patch"
        if self._outgoing_no_merges.get_active():
            cmd += " --no-merges"
        if self._outgoing_force.get_active():
            cmd += " --force"
        if self._outgoing_newest.get_active():
            cmd += " --newest-first"
        self._exec_cmd(cmd)
        
    def _exec_cmd(self, cmd):
        text_entry = self._pathbox.get_child()
        remote_path = str(text_entry.get_text())
        
        self.cmdline = "hg %s --verbose --repository %s %s" % (cmd,
                                                     util.shellquote(self.repo.root),
                                                     util.shellquote(remote_path),
                                                     )
        
        # show command to be executed
        if type(self.cmdline) == type([]):
            cmd = " ".join(self.cmdline)
        else:
            cmd = self.cmdline
        
        # execute comnand and show output on text widget
        self.write("", False)
        self.write("$ %s\n" % cmd)
        self._start_thread()

    def _start_thread(self):
        gobject.timeout_add(10, self.process_queue)
        self.thread1 = threading.Thread(target=self._do_popen)
        self.thread1.start()
        
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
        while self.queue.qsize():
            try:
                msg = self.queue.get(0)
                self.write(msg)
            except Queue.Empty:
                pass
                
        return True
        
    def _do_popen(self):        
        if not self.cmdline:
            return

        # run hg in unbuffered mode, so the output can be captured and display a.s.a.p.
        os.environ['PYTHONUNBUFFERED'] = "1"

        # start hg operation on a subprocess and capture the output
        pop = subprocess.Popen(self.cmdline, 
                               shell=True,
                               stderr=subprocess.STDOUT,
                               stdout=subprocess.PIPE,
                               stdin=subprocess.PIPE)

        try:
            line = 0
            blocksize = 1024
            while pop.poll() == None:
                if line < 100:
                    out = pop.stdout.readline()
                    line += 1
                else:
                    out = pop.stdout.read(blocksize)
                    if blocksize < 1024 * 50:
                        blocksize *= 2
                self.queue.put(out)
            out = pop.stdout.read()
            self.queue.put(out)
        except IOError:
            pass

def run(cwd='', files=[], **opts):
    dialog = SynchDialog(cwd, repos=files)
    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()
    
if __name__ == "__main__":
    run(**{})

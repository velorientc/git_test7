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
import os
import threading
from mercurial import hg, ui, util 
from mercurial.node import *
from dialog import error_dialog
from hglib import HgThread
from shlib import set_tortoise_icon

class SynchDialog(gtk.Dialog):
    def __init__(self, cwd='', root = '', repos=[]):
        """ Initialize the Dialog. """
        gtk.Dialog.__init__(self, parent=None,
                                  flags=0,
                                  buttons=())

        set_tortoise_icon(self, 'menusynch.ico')
        self.root = root
        self.selected_path = None

        self.set_default_size(600, 400)

        self.paths = self._get_paths()
        name = self.repo.ui.config('web', 'name') or os.path.basename(root)
        self.set_title("TortoiseHg Synchronize - " + name)

        #self.connect('delete-event', lambda x, y: True)
        self.connect('delete-event', self._delete)
        self.connect('response', self._response)

        self._btn_close = gtk.Button("Close")
        self._btn_close.connect('clicked', self._close_clicked)
        self.action_area.pack_end(self._btn_close)

        # toolbar
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()
        tbuttons = [
                self._toolbutton(gtk.STOCK_GO_DOWN,
                                 'incoming', 
                                 self._incoming_clicked,
                                 self._incoming_menu(),
                                 tip='Display changes that can be pulled'
                                 ' from selected repository'),
                self._toolbutton(gtk.STOCK_GOTO_BOTTOM,
                                 'pull',
                                 self._pull_clicked,
                                 self._pull_menu(),
                                 tip='Pull changes from selected'
                                 ' repository'),
                gtk.SeparatorToolItem(),
                self._toolbutton(gtk.STOCK_GO_UP,
                                 'outgoing',
                                 self._outgoing_clicked,
                                 self._outgoing_menu(),
                                 tip='Display local changes that will be pushed'
                                 ' to selected repository'),
                self._toolbutton(gtk.STOCK_GOTO_TOP,
                                 'push',
                                 self._push_clicked,
                                 self._push_menu(),
                                 tip='Push local changes to selected'
                                 ' repository'),
                self._toolbutton(gtk.STOCK_GOTO_LAST,
                                 'email',
                                 self._email_clicked,
                                 tip='Email local outgoing changes to'
                                 ' one or more recipients'),
                gtk.SeparatorToolItem(),
                self._toolbutton(gtk.STOCK_PREFERENCES,
                                 'configure',
                                 self._conf_clicked,
                                 tip='Configure peer repository paths'),
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
        self.revlist = gtk.ListStore(str)
        self._pathbox = gtk.ComboBoxEntry(self.revlist, 0)
        self._pathtext = self._pathbox.get_child()
        
        defrow = None
        defpushrow = None
        for row, (name, path) in enumerate(self.paths):
            if name == 'default':
                defrow = row
                if defpushrow is None:
                    defpushrow = row
            elif name == 'default-push':
                defpushrow = row
            self.revlist.append([path])

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
            self.repo = hg.repository(ui.ui(), path=self.root)
            return self.repo.ui.configitems('paths')
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
            
        tbutton.set_label(label)
        if tip:
            self.tips.set_tip(tbutton, tip)
        tbutton.connect('clicked', handler, userdata)
        return tbutton
        
    def _pull_clicked(self, toolbutton, data=None):
        cmd = ['pull']
        if self._pull_update.get_active():
            cmd.append('--update')
        if self._pull_force.get_active():
            cmd.append('--force')
        self._exec_cmd(cmd)
    
    def _push_clicked(self, toolbutton, data=None):
        cmd = ['push']
        if self._push_force.get_active():
            cmd.append('--force')
        self._exec_cmd(cmd)
        
    def _conf_clicked(self, toolbutton, data=None):
        newpath = self._pathtext.get_text()
        for name, path in self.paths:
            if path == newpath:
                newpath = None
                break
        from thgconfig import ConfigDialog
        dlg = ConfigDialog(self.root, True)
        dlg.show_all()
        if newpath:
            dlg.new_path(newpath)
        else:
            dlg.focus_field('paths.default')
        dlg.run()
        dlg.hide()
        self.paths = self._get_paths()
        self.revlist.clear()
        for row, (name, path) in enumerate(self.paths):
            self.revlist.append([path])

    def _email_clicked(self, toolbutton, data=None):
        path = self._pathtext.get_text()
        if not path:
            info_dialog('No repository selected',
                    'Select a peer repository to compare with')
            self._pathbox.grab_focus()
            return
        from hgemail import EmailDialog
        dlg = EmailDialog(self.root, ['--outgoing', path])
        dlg.show_all()
        dlg.run()
        dlg.hide()

    def _incoming_clicked(self, toolbutton, data=None):
        cmd = ['incoming']
        if self._incoming_show_patch.get_active():
            cmd.append('--patch')
        if self._incoming_no_merges.get_active():
            cmd.append('--no-merges')
        if self._incoming_force.get_active():
            cmd.append('--force')
        if self._incoming_newest.get_active():
            cmd.append('--newest-first')
        self._exec_cmd(cmd)
        
    def _outgoing_clicked(self, toolbutton, data=None):
        cmd = ['outgoing']
        if self._outgoing_show_patch.get_active():
            cmd.append('--patch')
        if self._outgoing_no_merges.get_active():
            cmd.append('--no-merges')
        if self._outgoing_force.get_active():
            cmd.append('--force')
        if self._outgoing_newest.get_active():
            cmd.append('--newest-first')
        self._exec_cmd(cmd)
        
    def _exec_cmd(self, cmd):
        text_entry = self._pathbox.get_child()
        remote_path = str(text_entry.get_text())
        
        cmdline = cmd
        cmdline.append('--verbose')
        cmdline.append('--repository')
        cmdline.append(self.root)
        cmdline.append(remote_path)
        
        # show command to be executed
        self.write("", False)
        self.write("$ %s\n" % ' '.join(cmdline))

        # execute command and show output on text widget
        gobject.timeout_add(10, self.process_queue)
        self.hgthread = HgThread(cmdline)
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

def run(cwd='', root='', files=[], **opts):
    dialog = SynchDialog(cwd, root, files)
    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()
    
if __name__ == "__main__":
    run(**{})

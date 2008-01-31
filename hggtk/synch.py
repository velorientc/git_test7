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
import gtklib

class SynchDialog(gtk.Window):
    def __init__(self, cwd='', root = '', repos=[]):
        """ Initialize the Dialog. """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        set_tortoise_icon(self, 'menusynch.ico')
        self.root = root
        self.selected_path = None

        self.set_default_size(610, 400)

        self.paths = self._get_paths()
        name = self.repo.ui.config('web', 'name') or os.path.basename(root)
        self.set_title("TortoiseHg Synchronize - " + name)

        self.connect('delete-event', self._delete)

        # toolbar
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()
        tbuttons = [
                self._toolbutton(gtk.STOCK_GO_DOWN,
                                 'Incoming', 
                                 self._incoming_clicked,
                                 tip='Display changes that can be pulled'
                                 ' from selected repository'),
                self._toolbutton(gtk.STOCK_GOTO_BOTTOM,
                                 '   Pull   ',
                                 self._pull_clicked,
                                 self._pull_menu(),
                                 tip='Pull changes from selected'
                                 ' repository'),
                gtk.SeparatorToolItem(),
                self._toolbutton(gtk.STOCK_GO_UP,
                                 'Outgoing',
                                 self._outgoing_clicked,
                                 tip='Display local changes that will be pushed'
                                 ' to selected repository'),
                self._toolbutton(gtk.STOCK_GOTO_TOP,
                                 'Push',
                                 self._push_clicked,
                                 tip='Push local changes to selected'
                                 ' repository'),
                self._toolbutton(gtk.STOCK_GOTO_LAST,
                                 'Email',
                                 self._email_clicked,
                                 tip='Email local outgoing changes to'
                                 ' one or more recipients'),
                gtk.SeparatorToolItem(),
                self._toolbutton(gtk.STOCK_PREFERENCES,
                                 'Configure',
                                 self._conf_clicked,
                                 tip='Configure peer repository paths'),
                gtk.SeparatorToolItem(),
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        sep = gtk.SeparatorToolItem()
        sep.set_expand(True)
        sep.set_draw(False)
        self.tbar.insert(sep, -1)
        button = self._toolbutton(gtk.STOCK_CLOSE, 'Close',
                self._close_clicked, tip='Close Application')
        self.tbar.insert(button, -1)
        vbox = gtk.VBox()
        self.add(vbox)
        vbox.pack_start(self.tbar, False, False, 2)
        
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

        # create checkbox to disable proxy
        self._use_proxy = gtk.CheckButton("use proxy server")        
        if ui.ui().config('http_proxy', 'host', ''):   
            self._use_proxy.set_active(True)
        else:
            self._use_proxy.set_sensitive(False)

        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self._pathbox, True, True)
        revbox.pack_end(self._use_proxy, False, False)
        vbox.pack_start(revbox, False, False, 2)

        expander = gtk.Expander('Advanced Options')
        expander.set_expanded(False)
        hbox = gtk.HBox()
        expander.add(hbox)

        revvbox = gtk.VBox()
        revhbox = gtk.HBox()
        self._reventry = gtk.Entry()
        self._force = gtk.CheckButton('Force pull or push')
        self.tips.set_tip(self._force, 'Run even when remote repository'
                ' is unrelated.')

        revhbox.pack_start(gtk.Label('Target Revision:'), False, False, 2)
        revhbox.pack_start(self._reventry, True, True, 2)
        eventbox = gtk.EventBox()
        eventbox.add(revhbox)
        self.tips.set_tip(eventbox, 'A specific revision up to which you'
                ' would like to push or pull.')
        revvbox.pack_start(eventbox, True, True, 8)
        revvbox.pack_start(self._force, False, False, 2)
        hbox.pack_start(revvbox, True, True, 4)

        frame = gtk.Frame('Incoming/Outgoing')
        hbox.pack_start(frame, False, False, 2)

        self._showpatch = gtk.CheckButton('Show Patches')
        self._newestfirst = gtk.CheckButton('Show Newest First')
        self._nomerge = gtk.CheckButton('Show No Merges')

        hbox = gtk.HBox()
        hbox.pack_start(self._showpatch, False, False, 2)
        hbox.pack_start(self._newestfirst, False, False, 2)
        hbox.pack_start(self._nomerge, False, False, 2)
        frame.add(hbox)
        vbox.pack_start(expander, False, False, 2)

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
        vbox.pack_start(scrolledwindow, True, True)

        self.stbar = gtklib.StatusBar()
        vbox.pack_start(self.stbar, False, False, 2)
        
    def _pull_menu(self):
        menu = gtk.Menu()
           
        self._pull_update = gtk.CheckMenuItem("Update to new tip")
        menu.append(self._pull_update)
        
        menu.show_all()
        return menu
        
    def _get_paths(self, sort="value"):
        """ retrieve symbolic paths """
        try:
            self.repo = hg.repository(ui.ui(), path=self.root)
            paths = self.repo.ui.configitems('paths')
            if sort:
                if sort == "value":
                    sortfunc = lambda a,b: cmp(a[1], b[1])
                elif sort == "name":
                    sortfunc = lambda a,b: cmp(a[0], b[0])
                else:
                    raise "unknown sort key '%s'" % sort
                paths.sort(sortfunc)
            return paths
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
        
    def _close_clicked(self, toolbutton, data=None):
        if threading.activeCount() != 1:
            error_dialog("Can't close now", "command is running")
        else:
            gtk.main_quit()
        
    def _delete(self, widget, event):
        if threading.activeCount() != 1:
            error_dialog("Can't close now", "command is running")
            return True
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
            tbutton.set_tooltip(self.tips, tip)
        tbutton.connect('clicked', handler, userdata)
        return tbutton
        
    def _pull_clicked(self, toolbutton, data=None):
        cmd = ['pull']
        if self._pull_update.get_active():
            cmd.append('--update')
        if self._force.get_active():
            cmd.append('--force')
        self._exec_cmd(cmd)
    
    def _push_clicked(self, toolbutton, data=None):
        cmd = ['push']
        if self._force.get_active():
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
        if self._showpatch.get_active():
            cmd.append('--patch')
        if self._nomerge.get_active():
            cmd.append('--no-merges')
        if self._force.get_active():
            cmd.append('--force')
        if self._newestfirst.get_active():
            cmd.append('--newest-first')
        self._exec_cmd(cmd)
        
    def _outgoing_clicked(self, toolbutton, data=None):
        cmd = ['outgoing']
        if self._showpatch.get_active():
            cmd.append('--patch')
        if self._nomerge.get_active():
            cmd.append('--no-merges')
        if self._force.get_active():
            cmd.append('--force')
        if self._newestfirst.get_active():
            cmd.append('--newest-first')
        self._exec_cmd(cmd)
        
    def _exec_cmd(self, cmd):
        proxy_host = ui.ui().config('http_proxy', 'host', '')
        use_proxy = self._use_proxy.get_active()
        text_entry = self._pathbox.get_child()
        remote_path = str(text_entry.get_text())
        
        cmdline = cmd[:]
        cmdline += ['--verbose', '--repository', self.root]
        if proxy_host and not use_proxy:
            cmdline += ["--config", "http_proxy.host="]
        cmdline += [remote_path]
        
        # show command to be executed
        self.write("", False)

        # execute command and show output on text widget
        gobject.timeout_add(10, self.process_queue)
        self.hgthread = HgThread(cmdline)
        self.hgthread.start()
        self.stbar.begin()
        self.stbar.set_status_text('hg ' + ' '.join(cmd + [remote_path]))
        
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
            self.stbar.end()
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

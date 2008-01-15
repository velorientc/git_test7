#
# logfilter.py - TortoiseHg's dialog for defining log filter criteria
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import pygtk
pygtk.require("2.0")

import os
import sys
import gtk
from dialog import *
from mercurial.node import *
from mercurial import util, hg, ui
from shlib import shell_notify, set_tortoise_icon

class FilterDialog(gtk.Dialog):
    """ Dialog for creating log filters """
    def __init__(self, root='', revs=[], files=[]):
        """ Initialize the Dialog """
        buttons = (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        super(FilterDialog, self).__init__(flags=gtk.DIALOG_MODAL, 
                                           buttons=buttons)

        set_tortoise_icon(self, 'menucheckout.ico')
        self.set_title("hg log filter - %s" % os.path.basename(root))

        try:
            self.repo = hg.repository(ui.ui(), path=root)
        except hg.RepoError:
            return None

        self.set_default_size(350, 120)

        # add toolbar with tooltips
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()
        
        self._btn_execute = self._toolbutton(
                gtk.STOCK_FIND,
                'Execute', 
                self._btn_execute_clicked,
                tip='Execute filtered search of revision history')
        tbuttons = [
                self._btn_execute,
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        self.vbox.pack_start(self.tbar, False, False, 2)
        
        # branch: combo box
        hbox = gtk.HBox()
        self.branchradio = gtk.RadioButton(None, 'Branch')
        self.branchlist = gtk.ListStore(str)
        self.branchbox = gtk.ComboBoxEntry(self.branchlist, 0)
        hbox.pack_start(self.branchradio, False, False, 4)
        hbox.pack_start(self.branchbox, True, True, 4)
        self.vbox.pack_start(hbox, False, False, 4)
        for name in self.repo.branchtags().keys():
            self.branchlist.append([name])

        # Revision range entries
        hbox = gtk.HBox()
        self.revradio = gtk.RadioButton(self.branchradio, 'Rev Range')
        self.rev0Entry = gtk.Entry()
        self.rev1Entry = gtk.Entry()
        hbox.pack_start(self.revradio, False, False, 4)
        hbox.pack_start(self.rev0Entry, True, False, 4)
        hbox.pack_start(self.rev1Entry, True, False, 4)
        self.vbox.pack_start(hbox, False, False, 4)
        if revs:
            self.rev0Entry.set_text(str(revs[0]))
        if len(revs) > 1:
            self.rev1Entry.set_text(str(revs[1]))

        hbox = gtk.HBox()
        self.searchradio = gtk.RadioButton(self.branchradio, 'Search Filter')
        hbox.pack_start(self.searchradio, False, False, 4)
        self.vbox.pack_start(hbox, False, False, 4)

        self.searchframe = gtk.Frame()
        self.vbox.pack_start(self.searchframe, True, False, 4)
        vbox = gtk.VBox()
        self.searchframe.add(vbox)

        hbox = gtk.HBox()
        self.filescheck = gtk.CheckButton("File(s)")
        self.filesentry = gtk.Entry()
        hbox.pack_start(self.filescheck, False, False, 4)
        hbox.pack_start(self.filesentry, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)
        
        hbox = gtk.HBox()
        self.kwcheck = gtk.CheckButton("Keyword(s)")
        self.kwentry = gtk.Entry()
        hbox.pack_start(self.kwcheck, False, False, 4)
        hbox.pack_start(self.kwentry, True, True, 4)
        vbox.pack_start(hbox, False, False, 4)

        hbox = gtk.HBox()
        self.datecheck = gtk.CheckButton("Date")
        self.dateentry = gtk.Entry()
        self.helpbutton = gtk.Button("Help...")
        self.helpbutton.connect('clicked', self._date_help)
        hbox.pack_start(self.datecheck, False, False, 4)
        hbox.pack_start(self.dateentry, True, True, 4)
        hbox.pack_start(self.helpbutton, False, False, 4)
        vbox.pack_start(hbox, False, False, 4)

        self.searchradio.connect('toggled', self.searchtoggle)
        self.revradio.connect('toggled', self.revtoggle)
        self.branchradio.connect('toggled', self.branchtoggle)

        # toggle them all once
        self.searchradio.set_active(True)
        self.revradio.set_active(True)
        self.branchradio.set_active(True)

        # show them all
        self.show_all()

    def searchtoggle(self, button):
        self.searchframe.set_sensitive(button.get_active())

    def revtoggle(self, button):
        self.rev0Entry.set_sensitive(button.get_active())
        self.rev1Entry.set_sensitive(button.get_active())

    def branchtoggle(self, button):
        self.branchbox.set_sensitive(button.get_active())

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
        
    def _btn_execute_clicked(self, button, data=None):
        # validate inputs
        # set _filter, _revs
        # signal response
        pass
        
    def _date_help(self, button):
        cmdline = ['hg', 'help', 'dates']
        from hgcmd import CmdDialog
        dlg = CmdDialog(cmdline)
        dlg.run()
        dlg.hide()

if __name__ == "__main__":
    # this dialog is not designed for standalone use
    # this is for debugging only
    dialog = FilterDialog()
    dialog.show_all()
    dialog.connect('response', gtk.main_quit)
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

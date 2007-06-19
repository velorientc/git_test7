#
# Add/Remove dialog for TortoiseHg
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

try:
    import pygtk
    pygtk.require("2.0")
except:
    pass

import sys
import gtk
import gobject
from mercurial import util
from mercurial.i18n import _
from dialog import question_dialog, error_dialog
import hglib

DIALOG_TYPE_ADD = 1
DIALOG_TYPE_REMOVE = 2

def get_tag_list(path):
    root = path
    u = ui.ui()
    try:
        repo = hg.repository(u, path=root)
    except repo.RepoError:
        return None

    l = repo.tagslist()
    l.reverse()
    hexfunc = node.hex
    taglist = []
    for t, n in l:
        try:
            hn = hexfunc(n)
            r, c = repo.changelog.rev(n), hexfunc(n)
        except revlog.LookupError:
            r, c = "?", hn

        taglist.append((t, r, c))

    return taglist

class AddRemoveDialog(gtk.Dialog):
    """ TortoiseHg dialog to add/remove files """
    def __init__(self, cmd, root='', files=[]):
        """ Initialize the Status window. """
        super(AddRemoveDialog, self).__init__(flags=gtk.DIALOG_MODAL, 
                                              buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))

        self.cmd = cmd
        self.root = root
        self.files = files
        self.hg = hglib.Hg(root)
        
        # set dialog title
        title = "hg %s" % cmd
        if root: title += " - %s" % root
        self.set_title(title)

        # build dialog
        self.set_default_size(550, 400)
        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self._treeview = gtk.TreeView()
        scrolledwindow.add(self._treeview)
        self._create_file_view()
        self.vbox.pack_start(scrolledwindow, True, True)

        # add remove & remove button
        if cmd == "add":
            btn_label = "Add"
            self.list_added = True
            self.list_clean = False
            self.list_removed = False
            self.list_unknown = True
            self.list_ignored = False
            self._do_action = self._do_add
        elif cmd == "remove":
            btn_label = "Remove"
            self.list_added = False
            self.list_clean = True
            self.list_removed = True
            self.list_unknown = False
            self.list_ignored = False
            self._do_action = self._do_remove
        else:
            raise "Unknown cmd '%s'" % cmd
        
        self._button_action = gtk.Button(btn_label)
        self._button_action.connect('clicked', self._on_button_clicked)
        self._button_action.set_flags(gtk.CAN_DEFAULT)
        self.action_area.pack_end(self._button_action)

        self.vbox.show_all()
        
        # Generate status output
        self._generate_status()

    def _create_file_view(self):
        self._file_store = gtk.ListStore(gobject.TYPE_BOOLEAN,   # [0] checkbox
                                         gobject.TYPE_STRING,    # [1] path to display
                                         gobject.TYPE_STRING,    # [2] changes type
                                         gobject.TYPE_STRING)    # [3] real path
        self._treeview.set_model(self._file_store)
        crt = gtk.CellRendererToggle()
        crt.set_property("activatable", True)
        crt.connect("toggled", self._on_toggle, self._file_store)
        self._treeview.append_column(gtk.TreeViewColumn(_(''),
                                     crt, active=0))
        self._treeview.append_column(gtk.TreeViewColumn(_('File'),
                                     gtk.CellRendererText(), text=1))
        self._treeview.append_column(gtk.TreeViewColumn(_('Status'),
                                     gtk.CellRendererText(), text=2))

    def _generate_status(self):
        # clear changed files display
        self._file_store.clear()

        # get file status
        try:
            modified, added, removed, deleted, unknown, ignored, clean = \
                    self.hg.status(files=self.files, list_clean=self.list_clean)
        except util.Abort, inst:
            return None
            
        def add_files(status, files):
            for path in files:
                self._file_store.append([ True, path, status, path ])
         
        # add target files to list window
        if self.list_clean:
            add_files(_('clean'), clean)
        if self.list_unknown:
            add_files(_('unknown'), unknown)
        if self.list_ignored:
            add_files(_('ignored'), ignored)
    
        # disable action button if no row is added
        self._button_action.set_sensitive(len(self._file_store))
        
    def _on_button_clicked(self, button):
        files = self._get_selected_files()
        if not files:
            return False
        return self._do_action(files)

    def _on_toggle(self, cell, path, model):
        model[path][0] = not model[path][0]
        return

    def _get_selected_files(self):
        ret = []
        it = self._file_store.get_iter_first()
        while it:
            if self._file_store.get_value(it, 0):
                # get real path from hidden column 3
                ret.append(self._file_store.get_value(it, 3))
            it = self._file_store.iter_next(it)

        return ret

    def _do_add(self, files):
        response = question_dialog("Add selected files?", "")
        if response == gtk.RESPONSE_YES:
            import os.path
            if self._do_hg_cmd('add', files) == True:
                # refresh changed file display
                self._generate_status()
       
    def _do_remove(self, files):
        response = question_dialog("Remove selected files?", "")
        if response == gtk.RESPONSE_YES:
            import os.path
            if self._do_hg_cmd('remove', files) == True:
                # refresh changed file display
                self._generate_status()
         
    def _do_hg_cmd(self, cmd, files):        
        try:
            self.hg.command(cmd, files=files)
        except util.Abort, inst:
            error_dialog("Error in revert", "abort: %s" % inst)
            return False
        except:
            import traceback
            error_dialog("Error in revert", "Traceback:\n%s" % traceback.format_exc())
            return False
        return True

def run(cmd, root='', files=[]):
    dialog = AddRemoveDialog(cmd, root=root, files=files)
    dialog.run()
    
if __name__ == "__main__":
    #run('add', r'c:\hg\h1', [r'c:\hg\h1\mercurial'])
    run('remove',r'c:\hg\h1', [r'c:\hg\h1\mercurial\hgweb'])

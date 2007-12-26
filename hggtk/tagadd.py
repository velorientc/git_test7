#
# TortoiseHg dialog to add tag
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

try:
    import pygtk
    pygtk.require("2.0")
except:
    pass

import os
import sys
import gtk
from dialog import question_dialog, error_dialog, info_dialog
from mercurial import hg, ui, cmdutil, util
from mercurial.i18n import _
from mercurial.node import *

class TagAddDialog(gtk.Dialog):
    """ Dialog to add tag to Mercurial repo """
    def __init__(self, root='', tag='', rev=None):
        """ Initialize the Dialog """
        super(TagAddDialog, self).__init__(flags=gtk.DIALOG_MODAL, 
                                           buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))

        # set dialog title
        title = "hg tag "
        title += " - %s" % (root or os.getcwd())
        self.set_title(title)

        self.root = root
        self.repo = None

        # build dialog
        self._create(tag, rev)

    def _create(self, tag, rev):
        self.set_default_size(350, 180)
        
        # tag name input
        tagbox = gtk.HBox()
        lbl = gtk.Label("Tag:")
        lbl.set_property("width-chars", 10)
        lbl.set_alignment(0, 0.5)
        self._tag_input = gtk.Entry()
        self._btn_tag_browse = gtk.Button("Browse...")
        self._btn_tag_browse.connect('clicked', self._btn_tag_clicked)
        self._tag_input.set_text(tag)
        tagbox.pack_start(lbl, False, False)
        tagbox.pack_start(self._tag_input, False, False)
        tagbox.pack_start(self._btn_tag_browse, False, False, 5)
        self.vbox.pack_start(tagbox, False, False, 2)

        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Label("Revision:")
        lbl.set_property("width-chars", 10)
        lbl.set_alignment(0, 0.5)
        self._rev_input = gtk.Entry()
        self._rev_input.set_text(rev and rev or "tip")
        self._btn_rev_browse = gtk.Button("Browse...")
        self._btn_rev_browse.connect('clicked', self._btn_rev_clicked)
        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self._rev_input, False, False)
        revbox.pack_start(self._btn_rev_browse, False, False, 5)
        self.vbox.pack_start(revbox, False, False, 2)

        # tag options
        option_box = gtk.VBox()
        self._local_tag = gtk.CheckButton("Create local tag")
        self._replace_tag = gtk.CheckButton("Replace existing tag")
        self._use_msg = gtk.CheckButton("Use custom commit message")
        option_box.pack_start(self._local_tag, False, False)
        option_box.pack_start(self._replace_tag, False, False)
        option_box.pack_start(self._use_msg, False, False)
        self.vbox.pack_start(option_box, False, False, 15)

        # commit message
        lbl = gtk.Label("Commit message:")
        lbl.set_alignment(0, 0.5)
        self._commit_message = gtk.Entry()
        self.vbox.pack_end(self._commit_message, False, False, 1)
        self.vbox.pack_end(lbl, False, False, 1)
        
        # add action buttn
        self._btn_addtag = gtk.Button("Add")
        self._btn_addtag.connect('clicked', self._btn_addtag_clicked)
        self.action_area.pack_end(self._btn_addtag)
        
        # show them all
        self.vbox.show_all()

    def _btn_rev_clicked(self, button):
        """ select revision from history dialog """
        import histselect
        rev = histselect.select(self.root)
        if rev is not None:
            self._rev_input.set_text(rev)
        
    def _btn_tag_clicked(self, button):
        """ select tag from tags dialog """
        import tags
        tag = tags.select(self.root)
        if tag is not None:
            self._tag_input.set_text(tag)
        
    def _btn_addtag_clicked(self, button):
        self._do_add_tag()
    
    def _do_add_tag(self):
        # gather input data
        is_local = self._local_tag.get_active()
        name = self._tag_input.get_text()
        rev = self._rev_input.get_text()
        force = self._replace_tag.get_active()
        use_msg = self._use_msg.get_active()
        message = self._commit_message.get_text()
        
        # verify input
        if name == "":
            error_dialog("Tag input is empty", "Please enter tag name")
            self._tag_input.grab_focus()
            return False
        if rev == "":
            error_dialog("Revision input is empty", "Please enter revision to tag")
            self._rev_input.grab_focus()
            return False
        if use_msg and not message:
            error_dialog("Custom commit message is empty", "Please enter commit message")
            self._commit_message.grab_focus()
            return False
            
        # add tag to repo        
        try:
            self._add_hg_tag(name, rev, message, is_local, force=force)
            info_dialog("Tagging completed", "Tag '%s' has been added" % name)
        except util.Abort, inst:
            error_dialog("Error in tagging", str(inst))
            return False
        except:
            import traceback
            error_dialog("Error in tagging", traceback.format_exc())
            return False
            
    def _add_hg_tag(self, name, revision, message, local, user=None,
                    date=None, force=False):
        u = ui.ui()
        try:
            repo = hg.repository(u, path=self.root)
        except hg.RepoError:
            return None

        if name in repo.tags() and not force:
            raise util.Abort(_('a tag named "%s" already exists')
                             % name)
        r = repo.changectx(revision).node()

        if not message:
            message = _('Added tag %s for changeset %s') % (name, short(r))

        if name in repo.tags() and not force:
            util.Abort("Tag '%s' already exist" % name)
            
        repo.tag(name, r, message, local, user, date)

def run(root='', tag='', rev=None, **opts):
    dialog = TagAddDialog(root, tag, rev)

    # the dialog maybe called by another window/dialog, so we only
    # enable the close dialog handler if dialog is run as mainapp
    dialog.connect('response', gtk.main_quit)
    
    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or ''
    #opts['tag'] = 'mytag'
    #opts['rev'] = '-1'
    run(**opts)

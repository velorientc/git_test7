# bookmarkadd.py - TortoiseHg dialog to add bookmark
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
# Copyright 2009 Emmanuel Rosa <goaway1000@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import traceback

from mercurial import hg, ui, util
from hgext import bookmarks

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, i18n

from tortoisehg.hgtk import dialog, gtklib

keep = i18n.keepgettext()

class BookmarkAddDialog(gtk.Dialog):
    """ Dialog to add bookmark to Mercurial repo """
    def __init__(self, repo, bookmark='', rev=''):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self,
                            buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
        gtklib.set_tortoise_keys(self)
        self.set_title(_('Bookmark - %s') % hglib.get_reponame(repo))
        self.set_resizable(False)
        self.set_has_separator(False)
        self.connect('response', self.dialog_response)

        self.repo = repo

        # add Add button
        addbutton = gtk.Button(_('Add'))
        addbutton.connect('clicked', lambda b: self._do_add_bookmark())
        self.action_area.pack_end(addbutton)

        # add Remove button
        removebutton = gtk.Button(_('Remove'))
        removebutton.connect('clicked', lambda b: self._do_rm_bookmark())
        self.action_area.pack_end(removebutton)

        # top layout table
        table = gtklib.LayoutTable()
        self.vbox.pack_start(table, True, True, 2)

        ## bookmark name input
        self._bookmarkslist = gtk.ListStore(str)
        self._bookmarklistbox = gtk.ComboBoxEntry(self._bookmarkslist, 0)
        self._bookmark_input = self._bookmarklistbox.get_child()
        self._bookmark_input.connect('activate', self._bookmarkinput_activated)
        self._bookmark_input.set_text(bookmark)
        table.add_row(_('Bookmark:'), self._bookmarklistbox, padding=False)

        ## revision input
        self._rev_input = gtk.Entry()
        self._rev_input.set_width_chars(12)
        self._rev_input.set_text(rev)
        table.add_row(_('Revision:'), self._rev_input)

        # prepare to show
        self._refresh()
        self._bookmarklistbox.grab_focus()

    def _refresh(self):
        """ update display on dialog with recent repo data """
        self.repo.invalidate()
        self._bookmarkslist.clear()
        self._bookmark_input.set_text("")

        # add bookmarks to drop-down list
        bookmarks = hglib.get_repo_bookmarks(self.repo) 
        bookmarks.sort()
        for bookmarkname in bookmarks:
            if bookmarkname != "tip":
                self._bookmarkslist.append([bookmarkname])

    def dialog_response(self, dialog, response_id):
        if response_id == gtk.RESPONSE_CLOSE \
                or response_id == gtk.RESPONSE_DELETE_EVENT:
            self.destroy()

    def _bookmarkinput_activated(self, bookmarkinput):
        self._do_add_bookmark()

    def _do_add_bookmark(self):
        # gather input data
        name = self._bookmark_input.get_text()
        rev = self._rev_input.get_text()

        # verify input
        if name == '':
            dialog.error_dialog(self, _('Bookmark input is empty'),
                         _('Please enter bookmark name'))
            self._bookmark_input.grab_focus()
            return False

        # add bookmark to repo
        try:
            self._add_hg_bookmark(name, rev)
            dialog.info_dialog(self, _('Bookmarking completed'),
                              _('Bookmark "%s" has been added') % name)
            self._refresh()
        except util.Abort, inst:
            dialog.error_dialog(self, _('Error in bookmarking'), str(inst))
            return False
        except:
            dialog.error_dialog(self, _('Error in bookmarking'),
                    traceback.format_exc())
            return False

    def _do_rm_bookmark(self):
        # gather input data
        name = self._bookmark_input.get_text()

        # verify input
        if name == '':
            dialog.error_dialog(self, _('Bookmark name is empty'),
                         _('Please select bookmark name to remove'))
            self._bookmark_input.grab_focus()
            return False

        try:
            self._rm_hg_bookmark(name)
            dialog.info_dialog(self, _('Bookmarking completed'),
                              _('Bookmark "%s" has been removed') % name)
            self._refresh()
        except util.Abort, inst:
            dialog.error_dialog(self, _('Error in bookmarking'), str(inst))
            return False
        except:
            dialog.error_dialog(self, _('Error in bookmarking'),
                    traceback.format_exc())
            return False

    def _add_hg_bookmark(self, name, revision):
        if name in hglib.get_repo_bookmarks(self.repo):
            raise util.Abort(_('a bookmark named "%s" already exists') % name)

        bookmarks.bookmark(ui=ui.ui(), 
                           repo=self.repo, 
                           rev=revision, 
                           mark=name)

    def _rm_hg_bookmark(self, name):
        if not name in hglib.get_repo_bookmarks(self.repo):
            raise util.Abort(_("Bookmark '%s' does not exist") % name)

        bookmarks.bookmark(ui=ui.ui(), 
                           repo=self.repo, 
                           mark=name,
                           delete=True)

class BookmarkRenameDialog(gtk.Dialog):
    """ Dialog to rename a bookmark """
    def __init__(self, repo, bookmark='', rev=''):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self,
                            buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
        gtklib.set_tortoise_keys(self)
        self.set_title(_('Bookmark - %s') % hglib.get_reponame(repo))
        self.set_resizable(False)
        self.set_has_separator(False)
        self.connect('response', self.dialog_response)

        self.repo = repo

        # add Rename button
        renamebutton = gtk.Button(_('Rename'))
        renamebutton.connect('clicked', lambda b: self._do_rename_bookmark())
        self.action_area.pack_end(renamebutton)

        # top layout table
        table = gtklib.LayoutTable()
        self.vbox.pack_start(table, True, True, 2)

        ## bookmark name input
        self._bookmarkslist = gtk.ListStore(str)
        self._bookmarklistbox = gtk.ComboBoxEntry(self._bookmarkslist, 0)
        self._bookmark_input = self._bookmarklistbox.get_child()
        self._bookmark_input.connect('activate', self._bookmarkinput_activated)
        self._bookmark_input.set_text(bookmark)
        table.add_row(_('Bookmark:'), self._bookmarklistbox, padding=False)

        ## revision input
        self._name_input = gtk.Entry()
        table.add_row(_('New name:'), self._name_input)

        # prepare to show
        self._refresh()
        self._bookmarklistbox.grab_focus()

    def _refresh(self):
        """ update display on dialog with recent repo data """
        self.repo.invalidate()
        self._bookmarkslist.clear()
        self._bookmark_input.set_text("")

        # add bookmarks to drop-down list
        bookmarks = hglib.get_repo_bookmarks(self.repo) 
        bookmarks.sort()
        for bookmarkname in bookmarks:
            if bookmarkname == "tip":
                continue
            self._bookmarkslist.append([bookmarkname])

    def dialog_response(self, dialog, response_id):
        if response_id == gtk.RESPONSE_CLOSE \
                or response_id == gtk.RESPONSE_DELETE_EVENT:
            self.destroy()

    def _bookmarkinput_activated(self, bookmarkinput):
        self._do_rename_bookmark()

    def _do_rename_bookmark(self):
        # gather input data
        name = self._bookmark_input.get_text()
        new_name = self._name_input.get_text()

        # verify input
        if name == '':
            dialog.error_dialog(self, _('Bookmark input is empty'),
                         _('Please enter bookmark name'))
            self._bookmark_input.grab_focus()
            return False

        if new_name == '':
            dialog.error_dialog(self, _('Bookmark new name input is empty'),
                         _('Please enter new bookmark name'))
            self._bookmark_input.grab_focus()
            return False

        # rename bookmark 
        try:
            self._rename_hg_bookmark(name, new_name)
            dialog.info_dialog(self, _('Bookmarking completed'),
                              _('Bookmark "%s" has been renamed to "%s"') % 
                              (name, new_name))
            self._refresh()
        except util.Abort, inst:
            dialog.error_dialog(self, _('Error in bookmarking'), str(inst))
            return False
        except:
            dialog.error_dialog(self, _('Error in bookmarking'),
                    traceback.format_exc())
            return False

    def _rename_hg_bookmark(self, name, new_name):
        if new_name in hglib.get_repo_bookmarks(self.repo):
            raise util.Abort(_('a bookmark named "%s" already exists') % new_name)
        bookmarks.bookmark(ui=ui.ui(), 
                           repo=self.repo, 
                           mark=new_name,
                           rename=name)


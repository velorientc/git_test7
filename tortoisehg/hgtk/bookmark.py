# bookmark.py - TortoiseHg dialog to add/remove/rename bookmarks
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
# Copyright 2009 Emmanuel Rosa <goaway1000@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import traceback

from mercurial import ui, util, commands

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, i18n, settings

from tortoisehg.hgtk import dialog, gtklib

TYPE_ADDREMOVE = 1
TYPE_RENAME    = 2

RESPONSE_ADD     = 1
RESPONSE_REMOVE  = 2
RESPONSE_RENAME  = 3
RESPONSE_MOVE    = 5

class BookmarkDialog(gtk.Dialog):
    """ Dialog to add bookmark to Mercurial repo """
    def __init__(self, repo, type, bookmark='', rev=''):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self)
        gtklib.set_tortoise_keys(self)
        self.set_title(_('Bookmark - %s') % hglib.get_reponame(repo))
        self.set_resizable(False)
        self.set_has_separator(False)

        self.repo = repo

        # persistent settings
        self.settings = settings.Settings('bookmark')

        # add buttons
        if type == TYPE_ADDREMOVE:
            self._button_add = self.add_button(_('Add'), RESPONSE_ADD)
            self._button_move = self.add_button(_('Move'), RESPONSE_MOVE)
            self.add_button(_('Remove'), RESPONSE_REMOVE)
        elif type == TYPE_RENAME:
            self.add_button(_('Rename'), RESPONSE_RENAME)
        else:
            raise _('unexpected type: %s') % type
        self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)

        # layout table
        table = gtklib.LayoutTable()
        self.vbox.pack_start(table, True, True, 2)

        ## bookmark name input
        self._bookmarkslist = gtk.ListStore(str)
        self._bookmarklistbox = gtk.ComboBoxEntry(self._bookmarkslist, 0)
        self._bookmark_input = self._bookmarklistbox.get_child()
        self._bookmark_input.set_text(bookmark)
        if type == TYPE_RENAME:
            label = _('Old name:')
        else:
            label = _('Bookmark:')
        table.add_row(label, self._bookmarklistbox, padding=False)

        ## add entry
        entry = gtk.Entry()
        if type == TYPE_ADDREMOVE:
            self._rev_input = entry
            entry.set_width_chars(12)
            entry.set_text(rev)
            label = _('Revision:')
        elif type == TYPE_RENAME:
            self._name_input = entry
            label = _('New Name:')
        table.add_row(label, entry, padding=False)

        # signal handlers
        self.connect('response', self.dialog_response)
        self._bookmark_input.connect('activate', self.entry_activated, type)
        entry.connect('activate', self.entry_activated, type)
        if type == TYPE_ADDREMOVE:
            self._bookmark_input.connect('changed', self.bookmark_changed)

        # prepare to show
        if type == TYPE_ADDREMOVE:
            self.set_add_move_button_sensitivity()
        self._refresh(clear=False)
        if type == TYPE_RENAME:
            self._name_input.grab_focus()
        else:
            self._bookmarklistbox.grab_focus()

    def _refresh(self, clear=True):
        """ update display on dialog with recent repo data """
        self.repo.invalidate()
        self._bookmarkslist.clear()

        # add bookmarks to drop-down list
        marks = self.repo._bookmarks.keys()
        marks.sort()
        for mark in marks:
            self._bookmarkslist.append([mark])

        # clear bookmark name input
        if clear:
            self._bookmark_input.set_text('')

    def dialog_response(self, dialog, response_id):
        # Add button
        if response_id == RESPONSE_ADD:
            self._do_add_bookmark()
        # Move button
        elif response_id == RESPONSE_MOVE:
            self._do_move_bookmark()
        # Remove button
        elif response_id == RESPONSE_REMOVE:
            self._do_remove_bookmark()
        # Rename button
        elif response_id == RESPONSE_RENAME:
            self._do_rename_bookmark()
        # Close button or closed by the user
        elif response_id in (gtk.RESPONSE_CLOSE, gtk.RESPONSE_DELETE_EVENT):
            self.settings.write()
            self.destroy()
            return # close dialog
        else:
            raise _('unexpected response id: %s') % response_id

        self.run() # don't close dialog

    def entry_activated(self, entry, type):
        if type == TYPE_ADDREMOVE:
            if self._button_add.get_property('sensitive'):
                self.response(RESPONSE_ADD)
            else:
                self.response(RESPONSE_MOVE)
        elif type == TYPE_RENAME:
            self.response(RESPONSE_RENAME)
        else:
            raise _('unexpected type: %s') % type

    def rev_changed(self, rev_input):
        rev = rev_input.get_text()
        self.opt_newcurrent.set_sensitive(hglib.is_rev_current(self.repo, rev))

    def bookmark_changed(self, bookmark_widget):
        self.set_add_move_button_sensitivity()

    def set_add_move_button_sensitivity(self):
        mark = self._bookmark_input.get_text()
        if mark in self.repo._bookmarks:
            self._button_add.set_sensitive(False)
            self._button_move.set_sensitive(True)
        else:
            self._button_add.set_sensitive(True)
            self._button_move.set_sensitive(False)


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

    def _do_move_bookmark(self):
        # gather input data
        name = self._bookmark_input.get_text()
        rev = self._rev_input.get_text()

        # verify input
        if name == '':
            dialog.error_dialog(self, _('Bookmark input is empty'),
                         _('Please enter bookmark name'))
            self._bookmark_input.grab_focus()
            return False

        # move bookmark
        try:
            self._move_hg_bookmark(name, rev)
            dialog.info_dialog(self, _('Bookmarking completed'),
                              _('Bookmark "%s" has been moved') % name)
            self._refresh()
        except util.Abort, inst:
            dialog.error_dialog(self, _('Error in bookmarking'), str(inst))
            return False
        except:
            dialog.error_dialog(self, _('Error in bookmarking'),
                    traceback.format_exc())
            return False

    def _do_remove_bookmark(self):
        # gather input data
        name = self._bookmark_input.get_text()

        # verify input
        if name == '':
            dialog.error_dialog(self, _('Bookmark name is empty'),
                         _('Please select bookmark name to remove'))
            self._bookmark_input.grab_focus()
            return False

        try:
            self._remove_hg_bookmark(name)
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

    def _add_hg_bookmark(self, name, revision):
        repo = self.repo
        if name in repo._bookmarks:
            raise util.Abort(_('a bookmark named "%s" already exists') % name)
        commands.bookmark(repo.ui, repo, name, revision, True)

    def _move_hg_bookmark(self, name, revision):
        repo = self.repo
        if name not in repo._bookmarks:
            raise util.Abort(_('No bookmark named "%s" exists') % name)
        commands.bookmark(repo.ui, repo, name, revision, True)

    def _remove_hg_bookmark(self, name):
        repo = self.repo
        if not name in repo._bookmarks:
            raise util.Abort(_("Bookmark '%s' does not exist") % name)
        commands.bookmark(repo.ui, repo, name, None, True, True)

    def _rename_hg_bookmark(self, name, new_name):
        repo = self.repo
        if new_name in repo._bookmarks:
            raise util.Abort(_('a bookmark named "%s" already exists') %
                             new_name)
        commands.bookmark(repo.ui, repo, new_name, None, True, False, name)

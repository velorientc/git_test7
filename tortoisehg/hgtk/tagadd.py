# tagadd.py - TortoiseHg dialog to add tag
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import traceback

from mercurial import hg, ui, util, error

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, settings, i18n

from tortoisehg.hgtk import dialog, gtklib

keep = i18n.keepgettext()

RESPONSE_ADD    = 1
RESPONSE_REMOVE = 2

class TagAddDialog(gtk.Dialog):
    """ Dialog to add tag to Mercurial repo """
    def __init__(self, repo, tag='', rev=''):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self)
        gtklib.set_tortoise_keys(self)
        self.set_title(_('Tag - %s') % hglib.get_reponame(repo))
        self.set_resizable(False)
        self.set_has_separator(False)
        self.connect('response', self.dialog_response)

        self.repo = repo

        # add buttons
        self.addbtn = self.add_button(_('Add'), RESPONSE_ADD)
        self.removebtn = self.add_button(_('Remove'), RESPONSE_REMOVE)
        self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)

        # persistent settings
        self.settings = settings.Settings('tagadd')

        # top layout table
        table = gtklib.LayoutTable()
        self.vbox.pack_start(table, True, True, 2)

        ## tag name input
        self.tagcombo = gtk.combo_box_entry_new_text()
        self.tagentry = self.tagcombo.get_child()
        self.tagentry.set_text(hglib.toutf(tag))
        self.tagcombo.connect('changed', self.combo_changed)
        self.tagentry.connect('activate',
                              lambda *a: self.response(RESPONSE_ADD))
        table.add_row(_('Tag:'), self.tagcombo, padding=False)

        ## revision input
        self._rev_input = gtk.Entry()
        self._rev_input.set_width_chars(12)
        self._rev_input.set_text(rev)
        self._rev_input.connect('notify::text',
                                lambda *a: self.update_sensitives())
        table.add_row(_('Revision:'), self._rev_input)
        
        # advanced options expander
        self.expander = gtk.Expander(_('Advanced options'))
        self.vbox.pack_start(self.expander, True, True, 2)

        # advanced options layout table
        table = gtklib.LayoutTable()
        self.expander.add(table)

        ## tagging options
        self._local_tag = gtk.CheckButton(_('Tag is local'))
        self._local_tag.connect('toggled', self.local_tag_toggled)
        self._replace_tag = gtk.CheckButton(_('Replace existing tag'))
        self._replace_tag.connect('toggled',
                                  lambda *a: self.update_sensitives())
        self._eng_msg = gtk.CheckButton(_('Use English commit message'))
        table.add_row(self._local_tag)
        table.add_row(self._replace_tag)
        table.add_row(self._eng_msg)

        ## custom commit message
        self._use_msg = gtk.CheckButton(_('Use custom commit message:'))
        self._use_msg.connect('toggled', self.msg_toggled)
        self._commit_message = gtk.Entry()
        self._commit_message.set_sensitive(False)
        table.add_row(self._use_msg)
        table.add_row(self._commit_message, padding=False)

        # prepare to show
        self.load_settings()
        self.update_tagcombo(clear=False)
        self.update_sensitives(True)
        self.tagentry.grab_focus()

    def update_tagcombo(self, clear=True):
        """ update display on dialog with recent repo data """
        self.repo.invalidate()
        self.tagcombo.get_model().clear()

        # add tags to drop-down list
        tags = list(self.repo.tags())
        tags.sort()
        tags.reverse()
        for tag in tags:
            if tag == 'tip':
                continue
            self.tagcombo.append_text(hglib.toutf(tag))

        # clear tag input
        if clear:
            self.tagentry.set_text('')

    def update_revision(self):
        """ update revision entry based on tag """
        tagmap = self.repo.tags()
        tag = self.tagentry.get_text()
        if not tag or hglib.fromutf(tag) not in tagmap:
            return

        node = tagmap[hglib.fromutf(tag)]
        ctx = self.repo[node]
        self._rev_input.set_text(str(ctx.rev()))

    def update_sensitives(self, affectlocal=False):
        """ update bottom button sensitives based on rev and tag """
        rev = self._rev_input.get_text()
        tag = self.tagentry.get_text()
        if not rev or not tag:
            self.addbtn.set_sensitive(False)
            self.removebtn.set_sensitive(False)
            return

        # check if valid revision
        try:
            self.repo[hglib.fromutf(rev)]
        except (error.LookupError, error.RepoLookupError, error.RepoError):
            self.addbtn.set_sensitive(False)
            self.removebtn.set_sensitive(False)
            return
        # check tag existence
        force = self._replace_tag.get_active()
        is_exist = hglib.fromutf(tag) in self.repo.tags()
        self.addbtn.set_sensitive(not is_exist or force)
        self.removebtn.set_sensitive(is_exist)

        # check if local
        is_local = self.repo.tagtype(hglib.fromutf(tag))
        if affectlocal and is_local is not None:
            self._local_tag.set_active(is_local == 'local')

    def load_settings(self):
        expanded = self.settings.get_value('expanded', False, True)
        self.expander.set_property('expanded', expanded)

        checked = self.settings.get_value('english', False, True)
        self._eng_msg.set_active(checked)

    def store_settings(self):
        expanded = self.expander.get_property('expanded')
        self.settings.set_value('expanded', expanded)

        checked = self._eng_msg.get_active()
        self.settings.set_value('english', checked)

        self.settings.write()

    def local_tag_toggled(self, checkbutton):
        local_tag_st = checkbutton.get_active()
        self._eng_msg.set_sensitive(not local_tag_st)
        self._use_msg.set_sensitive(not local_tag_st)
        use_msg_st = self._use_msg.get_active()
        self._commit_message.set_sensitive(not local_tag_st and use_msg_st)

    def msg_toggled(self, checkbutton):
        state = checkbutton.get_active()
        self._commit_message.set_sensitive(state)
        if state:
            self._commit_message.grab_focus()

    def combo_changed(self, combo):
        self.update_revision()
        self.update_sensitives(True)

    def dialog_response(self, dialog, response_id):
        # Add button
        if response_id == RESPONSE_ADD:
            self._do_add_tag()
        # Remove button
        elif response_id == RESPONSE_REMOVE:
            self._do_remove_tag()
        # Close button or closed by the user
        elif response_id in (gtk.RESPONSE_CLOSE, gtk.RESPONSE_DELETE_EVENT):
            self.store_settings()
            self.destroy()
            return # close dialog
        else:
            raise _('unexpected response id: %s') % response_id

        self.run() # don't close dialog

    def _do_add_tag(self):
        # gather input data
        is_local = self._local_tag.get_active()
        name = self.tagentry.get_text()
        rev = self._rev_input.get_text()
        force = self._replace_tag.get_active()
        eng_msg = self._eng_msg.get_active()
        use_msg = self._use_msg.get_active()
        message = self._commit_message.get_text()

        # verify input
        if name == '':
            dialog.error_dialog(self, _('Tag input is empty'),
                         _('Please enter tag name'))
            self.tagentry.grab_focus()
            return False
        if use_msg and not message:
            dialog.error_dialog(self, _('Custom commit message is empty'),
                         _('Please enter commit message'))
            self._commit_message.grab_focus()
            return False

        # add tag to repo
        try:
            self._add_hg_tag(name, rev, message, is_local, force=force,
                            english=eng_msg)
            dialog.info_dialog(self, _('Tagging completed'),
                              _('Tag "%s" has been added') % name)
            self.update_tagcombo()
        except util.Abort, inst:
            dialog.error_dialog(self, _('Error in tagging'), str(inst))
            return False
        except:
            dialog.error_dialog(self, _('Error in tagging'),
                    traceback.format_exc())
            return False

    def _do_remove_tag(self):
        # gather input data
        is_local = self._local_tag.get_active()
        name = self.tagentry.get_text()
        eng_msg = self._eng_msg.get_active()
        use_msg = self._use_msg.get_active()

        # verify input
        if name == '':
            dialog.error_dialog(self, _('Tag name is empty'),
                         _('Please select tag name to remove'))
            self.tagentry.grab_focus()
            return False

        if use_msg:
            message = self._commit_message.get_text()
        else:
            message = ''

        try:
            self._remove_hg_tag(name, message, is_local, english=eng_msg)
            dialog.info_dialog(self, _('Tagging completed'),
                              _('Tag "%s" has been removed') % name)
            self.update_tagcombo()
        except util.Abort, inst:
            dialog.error_dialog(self, _('Error in tagging'), str(inst))
            return False
        except:
            dialog.error_dialog(self, _('Error in tagging'),
                    traceback.format_exc())
            return False


    def _add_hg_tag(self, name, revision, message, local, user=None,
                    date=None, force=False, english=False):
        if hglib.fromutf(name) in self.repo.tags() and not force:
            raise util.Abort(_('a tag named "%s" already exists') % name)

        ctx = self.repo[revision]
        r = ctx.node()

        if not message:
            msgset = keep._('Added tag %s for changeset %s')
            message = (english and msgset['id'] or msgset['str']) \
                        % (name, str(ctx))
        if name in self.repo.tags() and not force:
            raise util.Abort(_("Tag '%s' already exist") % name)

        lname = hglib.fromutf(name)
        self.repo.tag(lname, r, hglib.fromutf(message), local, user, date)

    def _remove_hg_tag(self, name, message, local, user=None, date=None,
                    english=False):
        if hglib.fromutf(name) not in self.repo.tags():
            raise util.Abort(_("Tag '%s' does not exist") % name)

        if not message:
            msgset = keep._('Removed tag %s')
            message = (english and msgset['id'] or msgset['str']) % name
        r = self.repo[-1].node()
        lname = hglib.fromutf(name)
        self.repo.tag(lname, r, hglib.fromutf(message), local, user, date)

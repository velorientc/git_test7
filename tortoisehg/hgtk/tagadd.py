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

from mercurial import hg, ui, util

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, settings, i18n

from tortoisehg.hgtk import dialog, gtklib

keep = i18n.keepgettext()

class TagAddDialog(gtk.Dialog):
    """ Dialog to add tag to Mercurial repo """
    def __init__(self, repo, tag='', rev=''):
        """ Initialize the Dialog """
        root = hglib.toutf(os.path.basename(repo.root))
        gtk.Dialog.__init__(self, title=_('TortoiseHg Tag - %s') % root,
                          buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
        gtklib.set_tortoise_keys(self)
        self.set_resizable(False)
        self.set_has_separator(False)
        self.connect('response', self.dialog_response)

        # add Add button
        addbutton = gtk.Button(_('Add'))
        addbutton.connect('clicked', lambda b: self._do_add_tag())
        self.action_area.pack_end(addbutton)

        # add Remove button
        removebutton = gtk.Button(_('Remove'))
        removebutton.connect('clicked', lambda b: self._do_rm_tag())
        self.action_area.pack_end(removebutton)

        # persistent settings
        self.settings = settings.Settings('tagadd')

        self.repo = repo

        # copy from 'clone.py'
        def createtable(cols=2):
            newtable = gtk.Table(1, cols)
            def addrow(*widgets):
                row = newtable.get_property('n-rows')
                newtable.set_property('n-rows', row + 1)
                if len(widgets) == 1:
                    col = newtable.get_property('n-columns')
                    newtable.attach(widgets[0], 0, col, row, row + 1, gtk.FILL|gtk.EXPAND, 0, 4, 2)
                else:
                    for col, widget in enumerate(widgets):
                        flag = (col == 0) and gtk.FILL or gtk.FILL|gtk.EXPAND
                        newtable.attach(widget, col, col + 1, row, row + 1, flag, 0, 4, 2)
            return newtable, addrow

        # top layout table
        table, addrow = createtable()
        self.vbox.pack_start(table, True, True, 2)

        ## tag name input
        lbl = gtk.Label(_('Tag:'))
        lbl.set_alignment(1, 0.5)
        self._tagslist = gtk.ListStore(str)
        self._taglistbox = gtk.ComboBoxEntry(self._tagslist, 0)
        self._tag_input = self._taglistbox.get_child()
        self._tag_input.connect('activate', self._taginput_activated)
        self._tag_input.set_text(tag)
        addrow(lbl, self._taglistbox)

        ## revision input
        lbl = gtk.Label(_('Revision:'))
        lbl.set_alignment(1, 0.5)
        hbox = gtk.HBox()
        self._rev_input = gtk.Entry()
        self._rev_input.set_width_chars(12)
        self._rev_input.set_text(rev)
        hbox.pack_start(self._rev_input, False, False)
        hbox.pack_start(gtk.Label(''))
        addrow(lbl, hbox)
        
        # advanced options expander
        self.expander = gtk.Expander(_('Advanced options'))
        self.vbox.pack_start(self.expander, True, True, 2)

        # advanced options layout table
        table, addrow = createtable()
        self.expander.add(table)

        ## tagging options
        self._local_tag = gtk.CheckButton(_('Tag is local'))
        self._replace_tag = gtk.CheckButton(_('Replace existing tag'))
        self._eng_msg = gtk.CheckButton(_('Use English commit message'))
        addrow(self._local_tag)
        addrow(self._replace_tag)
        addrow(self._eng_msg)

        ## custom commit message
        self._use_msg = gtk.CheckButton(_('Use custom commit message:'))
        self._use_msg.connect('toggled', self.msg_toggled)
        addrow(self._use_msg)
        self._commit_message = gtk.Entry()
        self._commit_message.set_sensitive(False)
        addrow(self._commit_message)

        # prepare to show
        self.load_settings()
        self._refresh()
        self._taglistbox.grab_focus()

    def _refresh(self):
        """ update display on dialog with recent repo data """
        self.repo.invalidate()
        self._tagslist.clear()
        self._tag_input.set_text("")

        # add tags to drop-down list
        tags = [x[0] for x in self.repo.tagslist()]
        tags.sort()
        for tagname in tags:
            if tagname == "tip":
                continue
            self._tagslist.append([tagname])

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

    def msg_toggled(self, checkbutton):
        state = checkbutton.get_active()
        self._commit_message.set_sensitive(state)
        if state:
            self._commit_message.grab_focus()

    def dialog_response(self, dialog, response_id):
        self.store_settings()
        if response_id == gtk.RESPONSE_CLOSE \
                or response_id == gtk.RESPONSE_DELETE_EVENT:
            self.destroy()

    def _taginput_activated(self, taginput):
        self._do_add_tag()

    def _do_add_tag(self):
        # gather input data
        is_local = self._local_tag.get_active()
        name = self._tag_input.get_text()
        rev = self._rev_input.get_text()
        force = self._replace_tag.get_active()
        eng_msg = self._eng_msg.get_active()
        use_msg = self._use_msg.get_active()
        message = self._commit_message.get_text()

        # verify input
        if name == '':
            dialog.error_dialog(self, _('Tag input is empty'),
                         _('Please enter tag name'))
            self._tag_input.grab_focus()
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
            self._refresh()
        except util.Abort, inst:
            dialog.error_dialog(self, _('Error in tagging'), str(inst))
            return False
        except:
            dialog.error_dialog(self, _('Error in tagging'),
                    traceback.format_exc())
            return False

    def _do_rm_tag(self):
        # gather input data
        is_local = self._local_tag.get_active()
        name = self._tag_input.get_text()
        eng_msg = self._eng_msg.get_active()
        use_msg = self._use_msg.get_active()

        # verify input
        if name == '':
            dialog.error_dialog(self, _('Tag name is empty'),
                         _('Please select tag name to remove'))
            self._tag_input.grab_focus()
            return False

        if use_msg:
            message = self._commit_message.get_text()
        else:
            message = ''

        try:
            self._rm_hg_tag(name, message, is_local, english=eng_msg)
            dialog.info_dialog(self, _('Tagging completed'),
                              _('Tag "%s" has been removed') % name)
            self._refresh()
        except util.Abort, inst:
            dialog.error_dialog(self, _('Error in tagging'), str(inst))
            return False
        except:
            dialog.error_dialog(self, _('Error in tagging'),
                    traceback.format_exc())
            return False


    def _add_hg_tag(self, name, revision, message, local, user=None,
                    date=None, force=False, english=False):
        if name in self.repo.tags() and not force:
            raise util.Abort(_('a tag named "%s" already exists') % name)

        ctx = self.repo[revision]
        r = ctx.node()

        if not message:
            msgset = keep._('Added tag %s for changeset %s')
            message = (english and msgset['id'] or msgset['str']) \
                        % (name, str(ctx))
        if name in self.repo.tags() and not force:
            raise util.Abort(_("Tag '%s' already exist") % name)

        self.repo.tag(name, r, hglib.fromutf(message), local, user, date)

    def _rm_hg_tag(self, name, message, local, user=None, date=None,
                    english=False):
        if not name in self.repo.tags():
            raise util.Abort(_("Tag '%s' does not exist") % name)

        if not message:
            msgset = keep._('Removed tag %s')
            message = (english and msgset['id'] or msgset['str']) % name
        r = self.repo[-1].node()
        self.repo.tag(name, r, message, local, user, date)

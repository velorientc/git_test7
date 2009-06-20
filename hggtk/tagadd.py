#
# TortoiseHg dialog to add tag
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import gtk
import traceback

from mercurial import hg, ui, util

from thgutil.i18n import _
from thgutil import hglib

from hggtk import dialog, gtklib

class TagAddDialog(gtk.Window):
    """ Dialog to add tag to Mercurial repo """
    def __init__(self, root='', tag='', rev=''):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        gtklib.set_tortoise_keys(self)

        title = _('TortoiseHg Tag - %s') % (root or os.getcwd())
        self.set_title(title)

        self.root = root
        self.repo = None

        try:
            self.repo = hg.repository(ui.ui(), path=self.root)
        except hglib.RepoError:
            pass

        # build dialog
        self._create(tag, rev)

    def _create(self, tag, rev):
        self.set_default_size(350, 180)

        # add toolbar with tooltips
        self.tbar = gtk.Toolbar()
        self.tips = gtk.Tooltips()

        self._btn_addtag = self._toolbutton(
                gtk.STOCK_ADD, _('Add'),
                self._btn_addtag_clicked,
                tip=_('Add tag to selected version'))
        self._btn_rmtag = self._toolbutton(
                gtk.STOCK_DELETE, _('Remove'),
                self._btn_rmtag_clicked,
                tip=_('Remove tag from repository'))
        tbuttons = [
                self._btn_addtag,
                self._btn_rmtag
            ]
        for btn in tbuttons:
            self.tbar.insert(btn, -1)
        vbox = gtk.VBox()
        self.add(vbox)
        vbox.pack_start(self.tbar, False, False, 2)

        # tag name input
        tagbox = gtk.HBox()
        lbl = gtk.Label(_('Tag:'))
        lbl.set_property('width-chars', 10)
        lbl.set_alignment(0, 0.5)
        self._tagslist = gtk.ListStore(str)
        self._taglistbox = gtk.ComboBoxEntry(self._tagslist, 0)
        self._tag_input = self._taglistbox.get_child()
        self._tag_input.connect('activate', self._taginput_activated)
        self._tag_input.set_text(tag)
        tagbox.pack_start(lbl, False, False)
        tagbox.pack_start(self._taglistbox, True, True)
        vbox.pack_start(tagbox, True, True, 2)

        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Label(_('Revision:'))
        lbl.set_property('width-chars', 10)
        lbl.set_alignment(0, 0.5)
        self._rev_input = gtk.Entry()
        self._rev_input.set_text(rev)
        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self._rev_input, False, False)
        vbox.pack_start(revbox, False, False, 2)

        # tag options
        option_box = gtk.VBox()
        self._local_tag = gtk.CheckButton(_('Tag is local'))
        self._replace_tag = gtk.CheckButton(_('Replace existing tag'))
        self._use_msg = gtk.CheckButton(_('Use custom commit message'))
        option_box.pack_start(self._local_tag, False, False)
        option_box.pack_start(self._replace_tag, False, False)
        option_box.pack_start(self._use_msg, False, False)
        vbox.pack_start(option_box, False, False, 15)

        # commit message
        lbl = gtk.Label(_('Commit message:'))
        lbl.set_alignment(0, 0.5)
        self._commit_message = gtk.Entry()
        vbox.pack_end(self._commit_message, False, False, 1)
        vbox.pack_end(lbl, False, False, 1)

        # focus on tag input
        self._taglistbox.grab_focus()

        # show them all
        self._refresh()
        vbox.show_all()

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

    def _taginput_activated(self, taginput):
        self._do_add_tag()

    def _btn_tag_clicked(self, button):
        """ select tag from tags dialog """
        import tags
        tag = tags.select(self.root)
        if tag is not None:
            self._tag_input.set_text(tag)

    def _btn_addtag_clicked(self, button, data=None):
        self._do_add_tag()

    def _btn_rmtag_clicked(self, button, data=None):
        self._do_rm_tag()

    def _do_add_tag(self):
        # gather input data
        is_local = self._local_tag.get_active()
        name = self._tag_input.get_text()
        rev = self._rev_input.get_text()
        force = self._replace_tag.get_active()
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
            self._add_hg_tag(name, rev, message, is_local, force=force)
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
            self._rm_hg_tag(name, message, is_local)
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
                    date=None, force=False):
        if name in self.repo.tags() and not force:
            raise util.Abort(_('a tag named "%s" already exists') % name)

        ctx = self.repo[revision]
        r = ctx.node()

        if not message:
            message = _('Added tag %s for changeset %s') % (name, str(ctx))
        if name in self.repo.tags() and not force:
            raise util.Abort(_("Tag '%s' already exist") % name)

        self.repo.tag(name, r, hglib.fromutf(message), local, user, date)

    def _rm_hg_tag(self, name, message, local, user=None, date=None):
        if not name in self.repo.tags():
            raise util.Abort(_("Tag '%s' does not exist") % name)

        if not message:
            message = _('Removed tag %s') % name
        r = self.repo[-1].node()
        self.repo.tag(name, r, message, local, user, date)

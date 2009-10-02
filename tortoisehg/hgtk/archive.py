# archive.py - TortoiseHg's dialog for archiving a repo revision
#
# Copyright 2009 Emmanuel Rosa <goaway1000@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject
import pango

from mercurial import hg, ui

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths

from tortoisehg.hgtk import hgcmd, gtklib

_working_dir_parent_ = _('= Working Directory Parent =')

class ArchiveDialog(gtk.Dialog):
    """ Dialog to archive a Mercurial repo """

    def __init__(self, rev=None):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self)
        gtklib.set_tortoise_icon(self, 'menucheckout.ico')
        gtklib.set_tortoise_keys(self)
        self.set_resizable(False)
        self.set_has_separator(False)
        self.connect('response', self.dialog_response)

        # buttons
        self.archivebtn = self.add_button(_('Archive'), gtk.RESPONSE_OK)
        self.closebtn = self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except hglib.RepoError:
            gobject.idle_add(self.destroy)
            return

        title = _('Archive - %s') % hglib.toutf(os.path.basename(repo.root))
        self.set_title(title)

        hbox = gtk.HBox()
        lbl = gtk.Label(_('Archive revision:'))
        hbox.pack_start(lbl, False, False, 2)

        # revisions editable combo box
        self.combo = gtk.combo_box_entry_new_text()
        combo = self.combo
        combo.child.connect('activate', lambda b: self.response(gtk.RESPONSE_OK))
        hbox.pack_start(combo, True, True, 2)
        self.vbox.pack_start(hbox, False, False, 10)
        if rev:
            combo.append_text(str(rev))
        else:
            combo.append_text(_working_dir_parent_)
        combo.set_active(0)
        for b in repo.branchtags():
            combo.append_text(b)
        tags = list(repo.tags())
        tags.sort()
        tags.reverse()
        for t in tags:
            combo.append_text(t)

        self.vbox.add(self.get_destination_container(self.get_default_path()))
        self.vbox.add(self.get_type_container())

        # prepare to show
        self.archivebtn.grab_focus()

    def get_type_container(self):
        """Return a frame containing the supported archive types"""
        frame = gtk.Frame(_('Archive type'))
        vbox = gtk.VBox()

        self.filesradio = gtk.RadioButton(None, _('Directory of files'))
        self.tarradio = gtk.RadioButton(self.filesradio, _('Uncompressed tar archive'))
        self.tbz2radio = gtk.RadioButton(self.filesradio, _('Tar archive compressed using bzip2'))
        self.tgzradio = gtk.RadioButton(self.filesradio, _('Tar archive compressed using gzip'))
        self.uzipradio = gtk.RadioButton(self.filesradio, _('Uncompressed zip archive'))
        self.zipradio = gtk.RadioButton(self.filesradio, _('Zip archive compressed using deflate'))

        vbox.pack_start(self.filesradio, True, True, 2)
        vbox.pack_start(self.tarradio, True, True, 2)
        vbox.pack_start(self.tbz2radio, True, True, 2)
        vbox.pack_start(self.tgzradio, True, True, 2)
        vbox.pack_start(self.uzipradio, True, True, 2)
        vbox.pack_start(self.zipradio, True, True, 2)
        frame.add(vbox)
        frame.set_border_width(2)
        return frame

    def get_destination_container(self, default_path):
        """Return an hbox containing the widgets for the destination path"""
        hbox = gtk.HBox()
        lbl = gtk.Label(_('Destination Path:'))

        # create drop-down list for source paths
        self.destlist = gtk.ListStore(str)
        destcombo = gtk.ComboBoxEntry(self.destlist, 0)
        self.destentry = destcombo.get_child()
        self.destentry.set_text(default_path)
        self.destentry.set_position(-1)
        self.destentry.set_width_chars(38)

        # replace the drop-down widget so we can modify it's properties
        destcombo.clear()
        cell = gtk.CellRendererText()
        cell.set_property('ellipsize', pango.ELLIPSIZE_MIDDLE)
        destcombo.pack_start(cell)
        destcombo.add_attribute(cell, 'text', 0)

        destbrowse = gtk.Button(_('Browse...'))
        destbrowse.connect('clicked', self.browse_clicked)
        hbox.pack_start(lbl, False, False)
        hbox.pack_start(destcombo, True, True, 2)
        hbox.pack_end(destbrowse, False, False, 5)
        return hbox

    def dialog_response(self, dialog, response_id):
        # Archive button
        if response_id == gtk.RESPONSE_OK:
            self.archive()
            self.run()
        else:
            self.destroy()

    def get_default_path(self):
        """Return the default destination path"""
        return hglib.toutf(os.getcwd())

    def get_save_file_dialog(self, filter):
        """Return a configured save file dialog"""
        return gtklib.NativeSaveFileDialogWrapper(
            InitialDir=self.destentry.get_text(), 
            Title=_('Select Destination File'),
            Filter=filter)

    def get_selected_archive_type(self):
        """Return a dictionary describing the selected archive type"""
        dict = {}
        if self.tarradio.get_active():
            dict['type'] = 'tar'
            dict['filter'] = ((_('Tar archives'), '*.tar'),)
        elif self.tbz2radio.get_active():
            dict['type'] = 'tbz2'
            dict['filter'] = ((_('Bzip2 tar archives'), '*.tbz2'),)
        elif self.tgzradio.get_active():
            dict['type'] = 'tgz'
            dict['filter'] = ((_('Gzip tar archives'), '*.tgz'),)
        elif self.uzipradio.get_active():
            dict['type'] = 'uzip'
            dict['filter'] = ((_('Uncompressed zip archives'), '*.uzip'),)
        elif self.zipradio.get_active():
            dict['type'] = 'zip'
            dict['filter'] = ((_('Compressed zip archives'), '*.zip'),)
        else:
            dict['type'] = 'files'

        return dict

    def browse_clicked(self, button):
        """Select the destination directory or file"""
        archive_type = self.get_selected_archive_type()
        if archive_type['type'] == 'files':
            response = gtklib.NativeFolderSelectDialog(
                          initial=self.destentry.get_text(),
                          title=_('Select Destination Folder')).run()
        else:
            filter = archive_type['filter']
            response = self.get_save_file_dialog(filter).run()

        if response:
            self.destentry.set_text(response)

    def archive(self):
        rev = self.combo.get_active_text()

        cmdline = ['hg', 'archive', '--verbose']
        if rev != _working_dir_parent_:
            cmdline.append('--rev')
            cmdline.append(rev)

        cmdline.append('-t')
        cmdline.append(self.get_selected_archive_type()['type'])
        cmdline.append(hglib.fromutf(self.destentry.get_text()))

        dlg = hgcmd.CmdDialog(cmdline)
        dlg.run()
        dlg.hide()

def run(ui, *pats, **opts):
    return ArchiveDialog(opts.get('rev'))

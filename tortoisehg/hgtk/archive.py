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

from tortoisehg.hgtk import hgcmd, gtklib, gdialog

WD_PARENT = _('= Working Directory Parent =')
MODE_NORMAL  = 'normal'
MODE_WORKING = 'working'

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
            gtklib.idle_add_single_call(self.destroy)
            return
        self.repo = repo
        self.set_title(_('Archive - %s') % hglib.get_reponame(repo))
        self.prevtarget = None

        # layout table
        self.table = table = gtklib.LayoutTable()
        self.vbox.pack_start(table, True, True, 2)

        ## revision combo
        self.combo = gtk.combo_box_entry_new_text()
        self.combo.child.set_width_chars(28)
        self.combo.child.connect('activate',
                                 lambda b: self.response(gtk.RESPONSE_OK))
        if rev:
            self.combo.append_text(str(rev))
        else:
            self.combo.append_text(WD_PARENT)
        self.combo.set_active(0)
        for b in repo.branchtags():
            self.combo.append_text(b)
        tags = list(repo.tags())
        tags.sort()
        tags.reverse()
        for t in tags:
            self.combo.append_text(t)

        table.add_row(_('Archive revision:'), self.combo)

        ## dest combo & browse button
        self.destentry = gtk.Entry()
        self.destentry.set_width_chars(46)

        destbrowse = gtk.Button(_('Browse...'))
        destbrowse.connect('clicked', self.browse_clicked)

        table.add_row(_('Destination path:'), self.destentry, 0, destbrowse)

        ## archive types
        self.filesradio = gtk.RadioButton(None, _('Directory of files'))
        self.filesradio.connect('toggled', self.type_changed)
        table.add_row(_('Archive types:'), self.filesradio, ypad=0)
        def add_type(label):
            radio = gtk.RadioButton(self.filesradio, label)
            radio.connect('toggled', self.type_changed)
            table.add_row(None, radio, ypad=0)
            return radio
        self.tarradio = add_type(_('Uncompressed tar archive'))
        self.tbz2radio = add_type(_('Tar archive compressed using bzip2'))
        self.tgzradio = add_type(_('Tar archive compressed using gzip'))
        self.uzipradio = add_type(_('Uncompressed zip archive'))
        self.zipradio = add_type(_('Zip archive compressed using deflate'))

        # register signal handlers
        self.combo.connect('changed', lambda c: self.update_path())

        # prepare to show
        self.update_path(hglib.toutf(repo.root))
        self.archivebtn.grab_focus()
        gtklib.idle_add_single_call(self.after_init)

    def after_init(self):
        # CmdWidget
        self.cmd = hgcmd.CmdWidget()
        self.cmd.show_all()
        self.cmd.hide()
        self.vbox.pack_start(self.cmd, True, True, 6)

        # abort button
        self.abortbtn = self.add_button(_('Abort'), gtk.RESPONSE_CANCEL)
        self.abortbtn.hide()

    def dialog_response(self, dialog, response_id):
        def abort():
            self.cmd.stop()
            self.cmd.show_log()
            self.switch_to(MODE_NORMAL, cmd=False)
        # Archive button
        if response_id == gtk.RESPONSE_OK:
            self.archive()
        # Close button or dialog closing by the user
        elif response_id in (gtk.RESPONSE_CLOSE, gtk.RESPONSE_DELETE_EVENT):
            if self.cmd.is_alive():
                ret = gdialog.Confirm(_('Confirm Abort'), [], self,
                                      _('Do you want to abort?')).run()
                if ret == gtk.RESPONSE_YES:
                    abort()
            else:
                self.destroy()
                return # close dialog
        # Abort button
        elif response_id == gtk.RESPONSE_CANCEL:
            abort()
        else:
            raise _('unexpected response id: %s') % response_id

        self.run() # don't close dialog

    def type_changed(self, radio):
        if not radio.get_active():
            return
        self.update_path()

    def update_path(self, path=None):
        def remove_ext(path):
            for ext in ('.tar', '.tar.bz2', '.tar.gz', '.zip'):
                if path.endswith(ext):
                    return path.replace(ext, '')
            return path
        def remove_rev(path):
            model = self.combo.get_model()
            revs = [rev[0] for rev in model]
            revs.append(wdrev)
            if not self.prevtarget is None:
                revs.append(self.prevtarget)
            for rev in ['_' + rev for rev in revs]:
                if path.endswith(rev):
                    return path.replace(rev, '')
            return path
        def add_rev(path, rev):
            return '%s_%s' % (path, rev)
        def add_ext(path):
            select = self.get_selected_archive_type()
            if select['type'] != 'files':
                path += select['ext']
            return path
        text = self.combo.get_active_text()
        if len(text) == 0:
            return
        wdrev = str(self.repo['.'].rev())
        if text == WD_PARENT:
            text = wdrev
        else:
            try:
                self.repo[text]
            except (hglib.RepoError, hglib.LookupError):
                return
        if path is None:
            path = self.destentry.get_text()
        path = remove_ext(path)
        path = remove_rev(path)
        path = add_rev(path, text)
        path = add_ext(path)
        self.destentry.set_text(path)
        self.prevtarget = text

    def get_selected_archive_type(self):
        """Return a dictionary describing the selected archive type"""
        if self.tarradio.get_active():
            return {'type': 'tar', 'ext': '.tar',
                    'label': _('Tar archives')}
        elif self.tbz2radio.get_active():
            return {'type': 'tbz2', 'ext': '.tar.bz2',
                    'label': _('Bzip2 tar archives')}
        elif self.tgzradio.get_active():
            return {'type': 'tgz', 'ext': '.tar.gz',
                    'label': _('Gzip tar archives')}
        elif self.uzipradio.get_active():
            return {'type': 'uzip', 'ext': '.zip',
                    'label': ('Uncompressed zip archives')}
        elif self.zipradio.get_active():
            return {'type': 'zip', 'ext': '.zip',
                    'label': _('Compressed zip archives')}
        return {'type': 'files', 'ext': None, 'label': None}

    def browse_clicked(self, button):
        """Select the destination directory or file"""
        dest = hglib.fromutf(self.destentry.get_text())
        if not os.path.exists(dest):
            dest = os.path.dirname(dest)
        select = self.get_selected_archive_type()
        if select['type'] == 'files':
            response = gtklib.NativeFolderSelectDialog(
                            initial=dest,
                            title=_('Select Destination Folder')).run()
        else:
            ext = '*' + select['ext']
            label = '%s (%s)' % (select['label'], ext)
            response = gtklib.NativeSaveFileDialogWrapper(
                            initial=dest, 
                            title=_('Select Destination File'),
                            filter=((label, ext),
                                    (_('All Files (*.*)'), '*.*'))).run()
        if response:
            self.destentry.set_text(response)

    def switch_to(self, mode, cmd=True):
        if mode == MODE_NORMAL:
            normal = True
            self.closebtn.grab_focus()
        elif mode == MODE_WORKING:
            normal = False
            self.abortbtn.grab_focus()
        else:
            raise _('unknown mode name: %s') % mode
        working = not normal

        self.table.set_sensitive(normal)
        self.archivebtn.set_property('visible', normal)
        self.closebtn.set_property('visible', normal)
        if cmd:
            self.cmd.set_property('visible', working)
        self.abortbtn.set_property('visible', working)

    def archive(self):
        # verify input
        type = self.get_selected_archive_type()['type']
        dest = self.destentry.get_text()
        if os.path.exists(dest):
            if type != 'files':
                ret = gdialog.Confirm(_('Confirm Overwrite'), [], self,
                            _('The destination "%s" already exists!\n\n'
                              'Do you want to overwrite it?') % dest).run()
                if ret != gtk.RESPONSE_YES:
                    return False
            elif len(os.listdir(dest)) > 0:
                ret = gdialog.Confirm(_('Confirm Overwrite'), [], self,
                            _('The directory "%s" isn\'t empty!\n\n'
                              'Do you want to overwrite it?') % dest).run()
                if ret != gtk.RESPONSE_YES:
                    return False

        cmdline = ['hg', 'archive', '--verbose']
        rev = self.combo.get_active_text()
        if rev != WD_PARENT:
            cmdline.append('--rev')
            cmdline.append(rev)
        cmdline.append('-t')
        cmdline.append(type)
        cmdline.append(hglib.fromutf(dest))

        def cmd_done(returncode, useraborted):
            self.switch_to(MODE_NORMAL, cmd=False)
            if returncode == 0:
                if not self.cmd.is_show_log():
                    self.response(gtk.RESPONSE_CLOSE)
                self.cmd.set_result(_('Archived successfully'), style='ok')
            elif useraborted:
                self.cmd.set_result(_('Canceled archiving'), style='error')
            else:
                self.cmd.set_result(_('Failed to archive'), style='error')
        self.switch_to(MODE_WORKING)
        self.cmd.execute(cmdline, cmd_done)

def run(ui, *pats, **opts):
    return ArchiveDialog(opts.get('rev'))

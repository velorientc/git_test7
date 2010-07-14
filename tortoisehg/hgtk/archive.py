# archive.py - TortoiseHg's dialog for archiving a repo revision
#
# Copyright 2009 Emmanuel Rosa <goaway1000@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk

from mercurial import error

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib

from tortoisehg.hgtk import gtklib, gdialog

WD_PARENT = _('= Working Directory Parent =')

class ArchiveDialog(gdialog.GDialog):
    """ Dialog to archive a Mercurial repo """
    def __init__(self, rev=None):
        gdialog.GDialog.__init__(self)
        self.initrev = rev

    ### Start of Overriding Section ###

    def get_title(self, reponame):
        return _('Archive - %s') % reponame

    def get_icon(self):
        return 'menucheckout.ico'

    def get_body(self, vbox):
        self.prevtarget = None

        # layout table
        self.table = table = gtklib.LayoutTable()
        vbox.pack_start(table, True, True, 2)

        ## revision combo
        self.combo = gtk.combo_box_entry_new_text()
        self.combo.child.set_width_chars(28)
        self.combo.child.connect('activate',
                                 lambda b: self.response(gtk.RESPONSE_OK))
        if self.initrev:
            self.combo.append_text(str(self.initrev))
        else:
            self.combo.append_text(WD_PARENT)
        self.combo.set_active(0)
        for b in self.repo.branchtags():
            self.combo.append_text(b)
        tags = list(self.repo.tags())
        tags.sort()
        tags.reverse()
        for t in tags:
            self.combo.append_text(t)

        table.add_row(_('Archive revision:'), self.combo)

        self.opt_files_in_rev = gtk.CheckButton(
                    _('Only files modified/created in this revision'))
        table.add_row('', self.opt_files_in_rev, ypad=0)

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

        # signal handler
        self.combo.connect('changed', lambda c: self.update_path())

        # prepare to show
        self.update_path(hglib.toutf(self.repo.root))

    def get_buttons(self):
        return [('archive', _('Archive'), gtk.RESPONSE_OK),
                ('close', gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)]

    def get_action_map(self):
        return {gtk.RESPONSE_OK: self.archive}

    def switch_to(self, normal, working, cmd):
        self.table.set_sensitive(normal)
        self.buttons['archive'].set_property('visible', normal)
        self.buttons['close'].set_property('visible', normal)
        if normal:
            self.buttons['close'].grab_focus()

    def command_done(self, returncode, useraborted, *args):
        if returncode == 0:
            self.cmd.set_result(_('Archived successfully'), style='ok')
        elif useraborted:
            self.cmd.set_result(_('Canceled archiving'), style='error')
        else:
            self.cmd.set_result(_('Failed to archive'), style='error')

    ### End of Overriding Section ###

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
            except (error.RepoError, error.LookupError):
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

        # prepare command line
        cmdline = ['hg', 'archive', '--verbose']
        rev = self.combo.get_active_text()
        if rev != WD_PARENT:
            cmdline.append('--rev')
            cmdline.append(rev)
        cmdline.append('-t')
        cmdline.append(type)
        if self.opt_files_in_rev.get_active():
            ctx = self.repo[rev]
            for f in ctx.files():
                cmdline.append('-I')
                cmdline.append(f)
        cmdline.append('--')
        cmdline.append(hglib.fromutf(dest))

        # start archiving
        self.execute_command(cmdline)

def run(ui, *pats, **opts):
    return ArchiveDialog(opts.get('rev'))

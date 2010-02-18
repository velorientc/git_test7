# clone.py - Clone dialog for TortoiseHg
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import pango

from mercurial import extensions

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, shlib, settings
from tortoisehg.hgtk import gdialog, gtklib

class CloneDialog(gdialog.GDialog):
    """ Dialog to clone a Mercurial repo """
    def __init__(self, repos=[]):
        gdialog.GDialog.__init__(self, norepo=True)

        srcpath = hglib.toutf(os.getcwd())
        destpath = srcpath
        if len(repos) > 1:
            srcpath = repos[0]
            destpath = repos[1]
        elif len(repos):
            srcpath = repos[0]
        self.srcpath = srcpath
        self.destpath = destpath

    ### Start of Overriding Section ###

    def get_title(self, *args):
        return _('TortoiseHg Clone')

    def get_icon(self):
        return 'menuclone.ico'

    def get_setting_name(self):
        return 'clone'

    def get_body(self, vbox):
        # MRU lists
        self.recentsrc = self.settings.mrul('src_paths')
        self.recentdest = self.settings.mrul('dest_paths')

        def createcombo(path, label, title, bundle=False):
            # comboentry
            model = gtk.ListStore(str)
            combo = gtk.ComboBoxEntry(model, 0)
            combo.set_size_request(280, -1)
            combo.size_request()
            entry = combo.get_child()
            entry.set_text(path)
            entry.set_position(-1)
            entry.connect('activate',
                          lambda b: self.response(gtk.RESPONSE_OK))

            # replace the drop-down widget so we can modify it's properties
            combo.clear()
            cell = gtk.CellRendererText()
            cell.set_property('ellipsize', pango.ELLIPSIZE_MIDDLE)
            combo.pack_start(cell)
            combo.add_attribute(cell, 'text', 0)

            # browse button
            browse = gtk.Button(_('Browse...'))
            browse.connect('clicked', self.browse_clicked, title, entry)

            if bundle:
                # bundle button
                bundlebtn = gtk.Button(_('Bundle...'))
                bundlebtn.connect('clicked', self.bundle_clicked, 
                                  _('Select a Mercurial Bundle'), entry)
                table.add_row(label, combo, 0, browse, bundlebtn)
            else:
                table.add_row(label, combo, 0, browse)

            return model, combo

        # layout table for fixed options
        self.table = table = gtklib.LayoutTable()
        vbox.pack_start(table, True, True, 2)

        ## comboentry for source paths
        self.srclist, srccombo = createcombo(self.srcpath,
                                             _('Source path:'),
                                             _('Select Source Folder'), True)
        self.srcentry = srccombo.get_child()

        ## add pre-defined src paths to pull-down list
        sync_src = settings.Settings('synch').mrul('src_paths')
        sympaths = [x[1] for x in self.ui.configitems('paths')]
        recent = [x for x in self.recentsrc]
        syncsrc = [x for x in sync_src]
        paths = list(set(sympaths + recent + syncsrc))
        paths.sort()
        for p in paths:
            self.srclist.append([p])

        ## comboentry for destination paths
        self.destlist, destcombo = createcombo(self.destpath,
                                               _('Destination path:'),
                                               _('Select Destination Folder'))
        self.destentry = destcombo.get_child()

        ## add most-recent dest paths to pull-down list
        paths = list(self.recentdest)
        paths.sort()
        for p in paths:
            self.destlist.append([p])

        # expander for advanced options
        self.expander = expander = gtk.Expander(_('Advanced options'))
        vbox.pack_start(expander, True, True, 2)

        # layout table for advanced options
        table = gtklib.LayoutTable()
        expander.add(table)

        ## revision option
        self.reventry = gtk.Entry()
        self.reventry.set_sensitive(False)
        self.optrev = gtk.CheckButton(_('Clone to revision:'))
        self.optrev.connect('toggled', self.checkbutton_toggled, self.reventry)
        table.add_row(self.optrev, self.reventry)

        self.exs = [name for name, module in extensions.extensions()]
        if 'perfarce' in self.exs:
            self.startreventry = gtk.Entry()
            self.startreventry.set_sensitive(False)
            self.optstartrev = gtk.CheckButton(_('Starting P4 Changelist:'))
            self.optstartrev.connect('toggled',
                    self.checkbutton_toggled, self.startreventry)
            table.add_row(self.optstartrev, self.startreventry)

        ## options
        self.optupdate = gtk.CheckButton(_('Do not update the new working directory'))
        self.optpull = gtk.CheckButton(_('Use pull protocol to copy metadata'))
        self.optuncomp = gtk.CheckButton(_('Use uncompressed transfer'))
        table.add_row(self.optupdate)
        table.add_row(self.optpull)
        table.add_row(self.optuncomp)

        ## proxy options
        self.optproxy = gtk.CheckButton(_('Use proxy server'))
        table.add_row(self.optproxy)
        if self.ui.config('http_proxy', 'host'):
            self.optproxy.set_active(True)
        else:
            self.optproxy.set_sensitive(False)

        ## remote cmd option
        self.remotecmdentry = gtk.Entry()
        self.remotecmdentry.set_sensitive(False)
        self.optremote = gtk.CheckButton(_('Remote command:'))
        self.optremote.connect('toggled', self.checkbutton_toggled, self.remotecmdentry)
        table.add_row(self.optremote)
        table.add_row(self.remotecmdentry, padding=False)

    def get_buttons(self):
        return [('clone', _('Clone'), gtk.RESPONSE_OK),
                ('cancel', gtk.STOCK_CANCEL, gtk.RESPONSE_CLOSE)]

    def get_default_button(self):
        return 'clone'

    def get_action_map(self):
        return {gtk.RESPONSE_OK: self.clone}

    def switch_to(self, normal, *args):
        self.table.set_sensitive(normal)
        self.expander.set_sensitive(normal)
        self.buttons['clone'].set_property('visible', normal)
        self.buttons['cancel'].set_property('visible', normal)
        if normal:
            self.buttons['cancel'].grab_focus()

    def command_done(self, returncode, useraborted, src, dest):
        self.add_src_to_recent(src)
        self.add_dest_to_recent(dest)
        if returncode == 0:
            shlib.shell_notify([dest])
            self.cmd.set_result(_('Cloned successfully'), style='ok')
        elif useraborted:
            self.cmd.set_result(_('Canceled updating'), style='error')
        else:
            self.cmd.set_result(_('Failed to clone'), style='error')

    def load_settings(self):
        expanded = self.settings.get_value('expanded', False, True)
        self.expander.set_property('expanded', expanded)

    def store_settings(self):
        expanded = self.expander.get_property('expanded')
        self.settings.set_value('expanded', expanded)
        self.settings.write()

    ### End of Overriding Section ###

    def browse_clicked(self, button, title, entry):
        res = gtklib.NativeFolderSelectDialog(
                     initial=entry.get_text().strip(), title=title).run()
        if res:
            entry.set_text(res)

    def bundle_clicked(self, button, title, entry):
        path = entry.get_text().strip()
        if os.path.isdir(path):
            initial = path
        else:
            initial = os.path.dirname(path)

        res = gtklib.NativeSaveFileDialogWrapper(
                     initial=initial,
                     title=title, 
                     filter= ((_('Mercurial bundles'), '*.hg'),),
                     open=True).run()
        if res:
            entry.set_text(res)

    def checkbutton_toggled(self, checkbutton, entry):
        state = checkbutton.get_active()
        entry.set_sensitive(state)
        if state:
            entry.grab_focus()

    def add_src_to_recent(self, src):
        if os.path.exists(src):
            src = os.path.abspath(src)

        # save path to recent list in history
        self.recentsrc.add(src)
        self.settings.write()

        # update drop-down list
        self.srclist.clear()
        sympaths = [x[1] for x in self.ui.configitems('paths')]
        paths = list(set(sympaths + [x for x in self.recentsrc]))
        paths.sort()
        for p in paths:
            self.srclist.append([p])

    def add_dest_to_recent(self, dest):
        if not dest:
            return
        if os.path.exists(dest):
            dest = os.path.abspath(dest)

        # save path to recent list in history
        self.recentdest.add(dest)
        self.settings.write()

        # update drop down list
        paths = list(self.recentdest)
        paths.sort()
        self.destlist.clear()
        for p in paths:
            self.destlist.append([p])

    def clone(self):
        # gather input data
        src = self.srcentry.get_text().strip()
        dest = self.destentry.get_text().strip() or os.path.basename(src)
        remotecmd = self.remotecmdentry.get_text().strip()
        if self.reventry.get_property('sensitive'):
            rev = self.reventry.get_text().strip()
        else:
            rev = None

        if hasattr(self, 'startreventry') and \
                   self.startreventry.get_property('sensitive'):
            startrev = self.startreventry.get_text().strip()
        else:
            startrev = None

        # verify input
        if src == '':
            gdialog.Prompt(_('Source path is empty'),
                    _('Please enter a valid source path'), self).run()
            self.srcentry.grab_focus()
            return False

        if src == dest:
            gdialog.Prompt(_('Source and destination are the same'),
                    _('Please specify different paths'), self).run()
            self.destentry.grab_focus()
            return False

        if dest == os.getcwd():
            if os.listdir(dest):
                # cur dir has files, specify no dest, let hg take
                # basename
                dest = None
            else:
                dest = '.'
        else:
            abs = os.path.abspath(dest)
            dirabs = os.path.dirname(abs)
            if dirabs == src:
                dest = os.path.join(os.path.dirname(dirabs), dest)

        # prepare command line
        cmdline = ['hg', 'clone']
        if self.optupdate.get_active():
            cmdline.append('--noupdate')
        if self.optuncomp.get_active():
            cmdline.append('--uncompressed')
        if self.optpull.get_active():
            cmdline.append('--pull')
        if self.ui.config('http_proxy', 'host'):
            if not self.optproxy.get_active():
                cmdline += ['--config', 'http_proxy.host=']
        if remotecmd:
            cmdline.append('--remotecmd')
            cmdline.append(hglib.fromutf(remotecmd))
        if rev:
            cmdline.append('--rev')
            cmdline.append(rev)
        if src.startswith('p4://') and startrev:
            cmdline.append('--startrev')
            cmdline.append(startrev)

        cmdline.append('--verbose')
        cmdline.append(hglib.fromutf(src))
        if dest:
            cmdline.append(hglib.fromutf(dest))

        # start cloning
        self.execute_command(cmdline, src, dest)

def run(_ui, *pats, **opts):
    return CloneDialog(pats)

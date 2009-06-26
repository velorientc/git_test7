#
# TortoiseHg dialog to clone a repo
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import gtk
import os
import pango
import traceback

from mercurial import ui, util
from thgutil.i18n import _
from thgutil import hglib, shlib, settings
from hggtk import gdialog, gtklib, hgcmd

class CloneDialog(gtk.Window):
    """ Dialog to clone a Mercurial repo """
    def __init__(self, repos=[]):
        """ Initialize the Dialog """
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        gtklib.set_tortoise_icon(self, 'menuclone.ico')
        gtklib.set_tortoise_keys(self)
        self.set_default_size(520, 180)
        self.set_title(_('TortoiseHg Clone'))

        self.ui = ui.ui()
        self.clonesettings = settings.Settings('clone')
        self.recentsrc = self.clonesettings.mrul('src_paths')
        self.recentdest = self.clonesettings.mrul('dest_paths')

        srcpath = hglib.toutf(os.getcwd())
        destpath = srcpath
        if len(repos) > 1:
            srcpath = repos[0]
            destpath = repos[1]
        elif len(repos):
            srcpath = repos[0]

        ewidth = 20

        vbox = gtk.VBox()
        self.add(vbox)

        # clone source
        srcbox = gtk.HBox()
        lbl = gtk.Label(_('Source Path:'))
        lbl.set_property('width-chars', ewidth)
        lbl.set_alignment(0, 0.5)

        # create drop-down list for source paths
        self.srclist = gtk.ListStore(str)
        srccombo = gtk.ComboBoxEntry(self.srclist, 0)
        self.srcentry = srccombo.get_child()
        self.srcentry.set_text(srcpath)
        self.srcentry.set_position(-1)

        # replace the drop-down widget so we can modify it's properties
        srccombo.clear()
        cell = gtk.CellRendererText()
        cell.set_property('ellipsize', pango.ELLIPSIZE_MIDDLE)
        srccombo.pack_start(cell)
        srccombo.add_attribute(cell, 'text', 0)

        srcbrowse = gtk.Button(_('Browse...'))
        srcbrowse.connect('clicked', self.source_browse_clicked)
        srcbox.pack_start(lbl, False, False)
        srcbox.pack_start(srccombo, True, True)
        srcbox.pack_end(srcbrowse, False, False, 5)
        vbox.pack_start(srcbox, False, False, 2)

        # add pre-defined src paths to pull-down list
        sync_src = settings.Settings('synch').mrul('src_paths')
        sympaths = [x[1] for x in self.ui.configitems('paths')]
        recent = [x for x in self.recentsrc]
        syncsrc = [x for x in sync_src]
        paths = list(set(sympaths + recent + syncsrc))
        paths.sort()
        for p in paths:
            self.srclist.append([p])

        # clone destination
        destbox = gtk.HBox()
        lbl = gtk.Label(_('Destination Path:'))
        lbl.set_property('width-chars', ewidth)
        lbl.set_alignment(0, 0.5)
        self.destlist = gtk.ListStore(str)
        destcombo = gtk.ComboBoxEntry(self.destlist, 0)
        self.destentry = destcombo.get_child()
        self.destentry.set_text(destpath)
        self.destentry.set_position(-1)
        self.destentry.connect('activate', self.clone_clicked)

        # replace the drop-down widget so we can modify it's properties
        destcombo.clear()
        cell = gtk.CellRendererText()
        cell.set_property('ellipsize', pango.ELLIPSIZE_MIDDLE)
        destcombo.pack_start(cell)
        destcombo.add_attribute(cell, 'text', 0)

        srcbrowse = gtk.Button(_('Browse...'))
        srcbrowse.connect('clicked', self.dest_browse_clicked)
        destbox.pack_start(lbl, False, False)
        destbox.pack_start(destcombo, True, True)
        destbox.pack_end(srcbrowse, False, False, 5)
        vbox.pack_start(destbox, False, False, 2)

        # add most-recent dest paths to pull-down list
        paths = list(self.recentdest)
        paths.sort()
        for p in paths:
            self.destlist.append([p])

        # revision input
        revbox = gtk.HBox()
        lbl = gtk.Label(_('Clone To Revision:'))
        lbl.set_property('width-chars', ewidth)
        lbl.set_alignment(0, 0.5)
        self.reventry = gtk.Entry()
        self.reventry.set_text("")
        revbox.pack_start(lbl, False, False)
        revbox.pack_start(self.reventry, False, False)
        vbox.pack_start(revbox, False, False, 2)

        # options
        option_box = gtk.VBox()
        self.optupdate = gtk.CheckButton(_('do not update the new working directory'))
        self.optpull = gtk.CheckButton(_('use pull protocol to copy metadata'))
        self.optuncomp = gtk.CheckButton(_('use uncompressed transfer'))
        self.optproxy = gtk.CheckButton(_('use proxy server'))
        option_box.pack_start(self.optupdate, False, False)
        option_box.pack_start(self.optpull, False, False)
        option_box.pack_start(self.optuncomp, False, False)
        option_box.pack_start(self.optproxy, False, False)
        vbox.pack_start(option_box, False, False, 15)

        if self.ui.config('http_proxy', 'host'):
            self.optproxy.set_active(True)
        else:
            self.optproxy.set_sensitive(False)

        # remote cmd
        lbl = gtk.Label(_('Remote Cmd:'))
        lbl.set_alignment(0, 0.5)
        self.remotecmdentry = gtk.Entry()
        vbox.pack_start(self.remotecmdentry, False, False, 1)
        vbox.pack_start(lbl, False, False, 1)

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)
        mod = gtklib.get_thg_modifier()

        hbbox = gtk.HButtonBox()
        hbbox.set_layout(gtk.BUTTONBOX_END)
        vbox.pack_start(hbbox, False, False, 2)

        close = gtk.Button(_('Cancel'))
        close.connect('clicked', lambda x: self.destroy())
        key, modifier = gtk.accelerator_parse('Escape')
        close.add_accelerator('clicked', accelgroup, key, 0,
                gtk.ACCEL_VISIBLE)
        self.close_button = close
        hbbox.add(close)

        clone = gtk.Button(_('Clone'))
        key, modifier = gtk.accelerator_parse(mod+'Return')
        clone.add_accelerator('clicked', accelgroup, key, modifier,
                gtk.ACCEL_VISIBLE)
        clone.connect('clicked', self.clone_clicked)
        hbbox.add(clone)

        destcombo.grab_focus()

    def dest_browse_clicked(self, button):
        'select folder as clone destination'
        response = gtklib.NativeFolderSelectDialog(
                          initial=self.destentry.get_text(),
                          title=_('Select Destination Folder')).run()
        if response:
            self.destentry.set_text(response)

    def source_browse_clicked(self, button):
        'select source folder to clone'
        response = gtklib.NativeFolderSelectDialog(
                          initial=self.destentry.get_text(),
                          title=_('Select Source Folder')).run()
        if response:
            self.srcentry.set_text(response)

    def add_src_to_recent(self, src):
        if os.path.exists(src):
            src = os.path.abspath(src)

        # save path to recent list in history
        self.recentsrc.add(src)
        self.clonesettings.write()

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
        self.clonesettings.write()

        # update drop down list
        paths = list(self.recentdest)
        paths.sort()
        self.destlist.clear()
        for p in paths:
            self.destlist.append([p])

    def clone_clicked(self, toolbutton, data=None):
        # gather input data
        src = self.srcentry.get_text()
        dest = self.destentry.get_text() or os.path.basename(src)
        remotecmd = self.remotecmdentry.get_text()
        rev = self.reventry.get_text()

        # verify input
        if src == '':
            gdialog.Prompt(_('Source path is empty'),
                    _('Please enter a valid source path'), self).run()
            self.srcentry.grab_focus()
            return False

        if src == dest:
            gdialog.Prompt(_('Source and dest are the same'),
                    _('Please specify a different destination'), self).run()
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

        # start cloning
        try:
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

            cmdline.append('--verbose')
            cmdline.append(hglib.fromutf(src))
            if dest:
                cmdline.append(hglib.fromutf(dest))

            dlg = hgcmd.CmdDialog(cmdline)
            dlg.run()
            dlg.hide()
        except util.Abort, inst:
            gdialog.Prompt(_('Clone aborted'), str(inst), self).run()
            return False
        except:
            gdialog.Prompt(_('Clone error'),
                    traceback.format_exc(), self).run()
            return False

        self.add_src_to_recent(src)
        self.add_dest_to_recent(dest)
        self.close_button.grab_focus()

        if dlg.return_code() == 0:
            shlib.shell_notify([dest])

def run(_ui, *pats, **opts):
    return CloneDialog(pats)

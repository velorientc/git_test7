# clone.py - Clone dialog for TortoiseHg
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

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
        self.set_resizable(False)
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

        mainvbox = gtk.VBox()
        self.add(mainvbox)

        # copy from 'thgconfig.py'
        def createtable(cols=2):
            newtable = gtk.Table(1, cols)
            def addrow(*widgets):
                row = newtable.get_property('n-rows')
                newtable.set_property('n-rows', row + 1)
                def getwidget(obj):
                    if obj == None:
                        return gtk.Label('')
                    elif isinstance(obj, (int, long)):
                        widget = gtk.Label('')
                        widget.set_width_chars(obj)
                        return widget
                    return obj
                if len(widgets) == 1:
                    col = newtable.get_property('n-columns')
                    widget = getwidget(widgets[0])
                    newtable.attach(widget, 0, col, row, row + 1, gtk.FILL|gtk.EXPAND, 0, 4, 2)
                else:
                    for col, widget in enumerate(widgets):
                        widget = getwidget(widget)
                        flag = gtk.FILL if col == 0 else gtk.FILL|gtk.EXPAND
                        newtable.attach(widget, col, col + 1, row, row + 1, flag, 0, 4, 2)
            return newtable, addrow

        # layout table for fixed options
        table, addrow = createtable()
        mainvbox.pack_start(table, True, True, 2)
        def setcombosize(combo):
            combo.set_size_request(300, -1)
            combo.size_request()

        ## clone source label
        lbl = gtk.Label(_('Source path:'))
        lbl.set_alignment(1, 0.5)

        ## comboentry for source paths
        srcbox = gtk.HBox()
        self.srclist = gtk.ListStore(str)
        srccombo = gtk.ComboBoxEntry(self.srclist, 0)
        setcombosize(srccombo)
        self.srcentry = srccombo.get_child()
        self.srcentry.set_text(srcpath)
        self.srcentry.set_position(-1)
        srcbox.pack_start(srccombo)

        ## replace the drop-down widget so we can modify it's properties
        srccombo.clear()
        cell = gtk.CellRendererText()
        cell.set_property('ellipsize', pango.ELLIPSIZE_MIDDLE)
        srccombo.pack_start(cell)
        srccombo.add_attribute(cell, 'text', 0)

        ## source browse button
        srcbrowse = gtk.Button(_('Browse...'))
        srcbrowse.connect('clicked', self.source_browse_clicked)
        srcbox.pack_start(srcbrowse, False, False, 4)

        addrow(lbl, srcbox)

        ## add pre-defined src paths to pull-down list
        sync_src = settings.Settings('synch').mrul('src_paths')
        sympaths = [x[1] for x in self.ui.configitems('paths')]
        recent = [x for x in self.recentsrc]
        syncsrc = [x for x in sync_src]
        paths = list(set(sympaths + recent + syncsrc))
        paths.sort()
        for p in paths:
            self.srclist.append([p])

        ## clone destination
        destbox = gtk.HBox()
        lbl = gtk.Label(_('Destination path:'))
        lbl.set_alignment(1, 0.5)

        ## comboentry for destination paths
        self.destlist = gtk.ListStore(str)
        destcombo = gtk.ComboBoxEntry(self.destlist, 0)
        setcombosize(destcombo)
        self.destentry = destcombo.get_child()
        self.destentry.set_text(destpath)
        self.destentry.set_position(-1)
        self.destentry.connect('activate', self.clone_clicked)
        destbox.pack_start(destcombo)

        ## replace the drop-down widget so we can modify it's properties
        destcombo.clear()
        cell = gtk.CellRendererText()
        cell.set_property('ellipsize', pango.ELLIPSIZE_MIDDLE)
        destcombo.pack_start(cell)
        destcombo.add_attribute(cell, 'text', 0)

        ## source browse button
        destbrowse = gtk.Button(_('Browse...'))
        destbrowse.connect('clicked', self.dest_browse_clicked)
        destbox.pack_end(destbrowse, False, False, 4)

        addrow(lbl, destbox)

        ## add most-recent dest paths to pull-down list
        paths = list(self.recentdest)
        paths.sort()
        for p in paths:
            self.destlist.append([p])

        # expander for advanced options
        self.expander = expander = gtk.Expander(_('Advanced options'))
        mainvbox.pack_start(expander, True, True, 2)

        # layout table for advanced options
        table, addrow = createtable()
        expander.add(table)

        ## revision option
        hbox = gtk.HBox()
        self.reventry = gtk.Entry()
        self.reventry.set_sensitive(False)
        self.optrev = gtk.CheckButton(_('Clone to revision:'))
        self.optrev.connect('toggled', self.checkbutton_toggled, self.reventry)
        hbox.pack_start(self.optrev, False, False)
        hbox.pack_start(self.reventry, False, False, 4)
        addrow(hbox)

        ## options
        self.optupdate = gtk.CheckButton(_('Do not update the new working directory'))
        self.optpull = gtk.CheckButton(_('Use pull protocol to copy metadata'))
        self.optuncomp = gtk.CheckButton(_('Use uncompressed transfer'))
        addrow(self.optupdate)
        addrow(self.optpull)
        addrow(self.optuncomp)

        ## proxy options
        self.optproxy = gtk.CheckButton(_('Use proxy server'))
        addrow(self.optproxy)
        if self.ui.config('http_proxy', 'host'):
            self.optproxy.set_active(True)
        else:
            self.optproxy.set_sensitive(False)

        ## remote cmd option
        self.remotecmdentry = gtk.Entry()
        self.remotecmdentry.set_sensitive(False)
        self.optremote = gtk.CheckButton(_('Remote command:'))
        self.optremote.connect('toggled', self.checkbutton_toggled, self.remotecmdentry)
        addrow(self.optremote)
        addrow(self.remotecmdentry)

        ## keyboard accelerators
        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)
        mod = gtklib.get_thg_modifier()

        ## bottom buttons
        hbbox = gtk.HButtonBox()
        hbbox.set_layout(gtk.BUTTONBOX_END)
        mainvbox.pack_start(hbbox, False, False, 2)

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

        # give focus to dest combo
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

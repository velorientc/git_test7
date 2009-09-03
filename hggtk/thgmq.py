# thgmq.py - embeddable widget for MQ extension
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject

from thgutil.i18n import _
from thgutil import hglib

from hggtk import gtklib, hgcmd

# MQ patches row enumerations
MQ_INDEX   = 0
MQ_STATUS  = 1
MQ_NAME    = 2
MQ_SUMMARY = 3

class MQWidget(gtk.HBox):
    def __init__(self, repo):
        gtk.HBox.__init__(self)

        self.repo = repo

        # side toolbar
        toolbar = gtk.Toolbar()
        toolbar.set_style(gtk.TOOLBAR_ICONS)
        toolbar.set_orientation(gtk.ORIENTATION_VERTICAL)
        toolbar.set_property('icon-size', gtk.ICON_SIZE_SMALL_TOOLBAR)

        popallbtn = gtk.ToolButton(gtk.STOCK_GOTO_TOP)
        popallbtn.connect('clicked', self.popall_clicked)
        toolbar.insert(popallbtn, -1)

        popbtn = gtk.ToolButton(gtk.STOCK_GO_UP)
        popbtn.connect('clicked', self.pop_clicked)
        toolbar.insert(popbtn, -1)

        sep = gtk.SeparatorToolItem()
        sep.set_draw(False)
        sep.set_expand(True)
        toolbar.insert(sep, -1)

        pushbtn = gtk.ToolButton(gtk.STOCK_GO_DOWN)
        pushbtn.connect('clicked', self.push_clicked)
        toolbar.insert(pushbtn, -1)

        pushallbtn = gtk.ToolButton(gtk.STOCK_GOTO_BOTTOM)
        pushallbtn.connect('clicked', self.pushall_clicked)
        toolbar.insert(pushallbtn, -1)

        self.pack_start(toolbar, False, False)

        # scrolled pane
        pane = gtk.ScrolledWindow()
        pane.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        pane.set_shadow_type(gtk.SHADOW_IN)
        self.pack_start(pane)

        ## patch list
        self.model = gtk.ListStore(int, # patch index, -1 means separator
                                   str, # patch status
                                   str, # patch name
                                   str) # summary
        self.list = gtk.TreeView(self.model)
        self.list.set_size_request(180, -1)
        self.list.size_request()
        self.list.set_row_separator_func(self.row_sep_func)
        self.list.connect('button-press-event', self.list_pressed)
        cell = gtk.CellRendererText()

        col = gtk.TreeViewColumn(_('#'), cell)
        col.add_attribute(cell, 'text', MQ_INDEX)
        col.set_cell_data_func(cell, self.cell_data_func)
        col.set_resizable(False)
        self.list.append_column(col)

        col = gtk.TreeViewColumn(_('Name'), cell)
        col.add_attribute(cell, 'text', MQ_NAME)
        col.set_cell_data_func(cell, self.cell_data_func)
        col.set_resizable(False)
        self.list.append_column(col)

        col = gtk.TreeViewColumn(_('Summary'), cell)
        col.add_attribute(cell, 'text', MQ_SUMMARY)
        col.set_cell_data_func(cell, self.cell_data_func)
        col.set_resizable(True)
        self.list.append_column(col)

        pane.add(self.list)

        # prepare to show
        self.refresh()

    """ public functions """

    def refresh(self):
        self.model.clear()

        # build list of patches
        from hgext import mq
        q = self.repo.mq
        q.parse_series()
        top = None
        applied = set([p.name for p in q.applied])
        for index, patchname in enumerate(q.series):
            stat = patchname in applied and 'A' or 'U'
            msg = mq.patchheader(q.join(patchname)).message[0]
            iter = self.model.append((index, stat, patchname, msg))
            if stat == 'A':
                top = iter

        # insert separator
        self.model.insert_after(top, (-1, '', '', ''))

    def qpop(self, all=False):
        cmdline = ['hg', 'qpop']
        if all:
            cmdline.append('--all')
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        self.repo.mq.invalidate()
        self.refresh()

    def qpush(self, all=False):
        cmdline = ['hg', 'qpush']
        if all:
            cmdline.append('--all')
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        self.repo.mq.invalidate()
        self.refresh()

    """ internal functions """

    def cell_data_func(self, column, cell, model, iter):
        stat = model[iter][MQ_STATUS]
        if stat == 'A':
            cell.set_property('foreground', 'blue')
        elif stat == 'U':
            cell.set_property('foreground', '#909090')
        else:
            cell.set_property('foreground', 'black')

    def row_sep_func(self, model, iter, data=None):
        return model[iter][MQ_INDEX] == -1;

    """ signal handlers """

    def list_pressed(self, list, event):
        if event.button == 1:
            x, y = int(event.x), int(event.y)
            path = list.get_path_at_pos(x, y)
            if not path:
                # HACK: clear selection after this function calling,
                # against selection by getting focus
                def unselect():
                    selection = list.get_selection()
                    selection.unselect_all()
                gobject.idle_add(unselect)

    def popall_clicked(self, toolbutton):
        self.qpop(all=True)

    def pop_clicked(self, toolbutton):
        self.qpop()

    def push_clicked(self, toolbutton):
        self.qpush()

    def pushall_clicked(self, toolbutton):
        self.qpush(all=True)

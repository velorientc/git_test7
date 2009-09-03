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

    __gsignals__ = {
        'repo-invalidated': (gobject.SIGNAL_RUN_FIRST,
                             gobject.TYPE_NONE,
                             ()),
        'patch-selected': (gobject.SIGNAL_RUN_FIRST,
                           gobject.TYPE_NONE,
                           (int,  # revision number
                            str)) # patch name
    }

    def __init__(self, repo):
        gtk.HBox.__init__(self)

        self.repo = repo

        # side toolbar
        toolbar = gtk.Toolbar()
        toolbar.set_style(gtk.TOOLBAR_ICONS)
        toolbar.set_orientation(gtk.ORIENTATION_VERTICAL)
        toolbar.set_property('icon-size', gtk.ICON_SIZE_SMALL_TOOLBAR)

        self.btn = {}

        popallbtn = gtk.ToolButton(gtk.STOCK_GOTO_TOP)
        popallbtn.connect('clicked', self.popall_clicked)
        toolbar.insert(popallbtn, -1)
        self.btn['popall'] = popallbtn

        popbtn = gtk.ToolButton(gtk.STOCK_GO_UP)
        popbtn.connect('clicked', self.pop_clicked)
        toolbar.insert(popbtn, -1)
        self.btn['pop'] = popbtn

        sep = gtk.SeparatorToolItem()
        sep.set_draw(False)
        sep.set_expand(True)
        toolbar.insert(sep, -1)

        pushbtn = gtk.ToolButton(gtk.STOCK_GO_DOWN)
        pushbtn.connect('clicked', self.push_clicked)
        toolbar.insert(pushbtn, -1)
        self.btn['push'] = pushbtn

        pushallbtn = gtk.ToolButton(gtk.STOCK_GOTO_BOTTOM)
        pushallbtn.connect('clicked', self.pushall_clicked)
        toolbar.insert(pushallbtn, -1)
        self.btn['pushall'] = pushallbtn

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
        self.list.connect('cursor-changed', self.list_sel_changed)
        self.list.connect('button-press-event', self.list_pressed)
        self.list.connect('row-activated', self.list_row_activated)

        cell = gtk.CellRendererText()
        editcell = gtk.CellRendererText()
        editcell.set_property('editable', True)
        editcell.connect('edited', self.list_cell_edited, self.model)

        self.cols = {}
        self.cells = {}

        def addcol(header, col_idx, cell=cell, resizable=False):
            col = gtk.TreeViewColumn(header, cell)
            col.add_attribute(cell, 'text', col_idx)
            col.set_cell_data_func(cell, self.cell_data_func)
            col.set_resizable(resizable)
            self.list.append_column(col)
            self.cols[col_idx] = col
            self.cells[col_idx] = cell

        addcol(_('#'), MQ_INDEX)
        addcol(_('Name'), MQ_NAME, cell=editcell)
        addcol(_('Summary'), MQ_SUMMARY, resizable=True)

        pane.add(self.list)

        # prepare to show
        self.refresh()

    ### public functions ###

    def refresh(self):
        """
        Refresh the list of patches.
        """
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

        # update toolbar buttons
        self.update_toolbuttons()

    def qgoto(self, patch):
        """
        [MQ] Execute 'qgoto' command.

        patch: the patch name or an index to specify the patch.
        """
        cmdline = ['hg', 'qgoto', patch]
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        self.repo.mq.invalidate()
        self.refresh()
        self.emit('repo-invalidated')

    def qpop(self, all=False):
        """
        [MQ] Execute 'qpop' command.

        all: if True, use '--all' option. (default: False)
        """
        cmdline = ['hg', 'qpop']
        if all:
            cmdline.append('--all')
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        self.repo.mq.invalidate()
        self.refresh()
        self.emit('repo-invalidated')

    def qpush(self, all=False):
        """
        [MQ] Execute 'qpush' command.

        all: if True, use '--all' option. (default: False)
        """
        cmdline = ['hg', 'qpush']
        if all:
            cmdline.append('--all')
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        self.repo.mq.invalidate()
        self.refresh()
        self.emit('repo-invalidated')

    def qdelete(self, patch):
        """
        [MQ] Execute 'qdelete' command.

        patch: the patch name or an index to specify the patch.
        """
        cmdline = ['hg', 'qdelete', patch]
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        self.repo.mq.invalidate()
        self.refresh()

    def qrename(self, name, patch='qtip'):
        """
        [MQ] Execute 'qrename' command.
        If 'patch' param isn't specified, renaming should be applied
        'qtip' (current) patch.

        name: the new patch name for renaming.
        patch: the target patch name or index. (default: 'qtip')
        """
        if not name:
            return
        cmdline = ['hg', 'qrename', patch, name]
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        self.repo.mq.invalidate()
        self.refresh()
        self.emit('repo-invalidated')

    def qrename_ui(self, patch='qtip'):
        """
        Prepare the user interface for renaming the patch.
        If 'patch' param isn't specified, renaming should be started
        'qtip' (current) patch.

        Return True if succeed to prepare; otherwise False.

        patch: the target patch name or index. (default: 'qtip')
        """
        target = self.repo.mq.lookup(patch)
        if not target:
            return False

        for row in self.model:
            if row[MQ_NAME] == target:
                path = row.path
                break
        else:
            return False

        self.list.set_cursor_on_cell(path, self.cols[MQ_NAME], None, True)
        return True

    def qfinish(self, applied=False):
        """
        [MQ] Execute 'qfinish' command.

        applied: if True, enable '--applied' option. (default: False)
        """
        cmdline = ['hg', 'qfinish']
        if applied:
            cmdline.append('--applied')
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        self.repo.mq.invalidate()
        self.refresh()
        self.emit('repo-invalidated')

    def qfold(self, patch):
        """
        [MQ] Execute 'qdelete' command.

        patch: the patch name or an index to specify the patch.
        """
        if not patch:
            return
        cmdline = ['hg', 'qfold', patch]
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.show_all()
        dlg.run()
        dlg.hide()
        self.repo.mq.invalidate()
        self.refresh()
        self.emit('repo-invalidated')

    ### internal functions ###

    def is_top_patch(self, patchname):
        if patchname:
            return self.get_top_patchname() == patchname
        return False

    def get_top_patchname(self):
        return self.repo.mq.lookup('qtip')

    def update_toolbuttons(self):
        q = self.repo.mq
        in_bottom = len(q.applied) == 0
        in_top = len(q.unapplied(self.repo)) == 0
        self.btn['popall'].set_sensitive(not in_bottom)
        self.btn['pop'].set_sensitive(not in_bottom)
        self.btn['push'].set_sensitive(not in_top)
        self.btn['pushall'].set_sensitive(not in_top)

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

    def list_popup_menu(self, list, path):
        row = self.model[path]
        if row[MQ_INDEX] == -1:
            return

        menu = gtk.Menu()
        def append(label, handler=None):
            item = gtk.MenuItem(label, True)
            item.set_border_width(1)
            if handler:
                item.connect('activate', handler, row)
            menu.append(item)

        is_top = self.is_top_patch(row[MQ_NAME])
        is_applied = row[MQ_STATUS] == 'A'

        if not is_top:
            append(_('_goto'), self.goto_activated)
        append(_('_rename'), self.rename_activated)
        append(_('_finish applied'), self.finish_activated)
        if not is_applied:
            append(_('_delete'), self.delete_activated)
            append(_('f_old'), self.fold_activated)

        menu.show_all()
        menu.popup(None, None, None, 0, 0)
        return True

    ### signal handlers ###

    def list_pressed(self, list, event):
        x, y = int(event.x), int(event.y)
        pathinfo = list.get_path_at_pos(x, y)
        if event.button == 1:
            if not pathinfo:
                # HACK: clear selection after this function calling,
                # against selection by getting focus
                def unselect():
                    selection = list.get_selection()
                    selection.unselect_all()
                gobject.idle_add(unselect)
        elif event.button == 3:
            if pathinfo:
                self.list_popup_menu(self.list, pathinfo[0])

    def list_sel_changed(self, list):
        path, focus = list.get_cursor()
        patchname = self.model[path][MQ_NAME]
        try:
            ctx = self.repo[patchname]
            self.emit('patch-selected', ctx.rev(), patchname)
        except hglib.RepoError:
            pass

    def list_row_activated(self, list, path, column):
        patchname = self.model[path][MQ_NAME]
        if self.get_top_patchname() != patchname:
            self.qgoto(patchname)

    def list_cell_edited(self, cell, path, newname, model):
        patchname = model[path][MQ_NAME]
        if newname != patchname:
            self.qrename(newname, patch=patchname)

    def popall_clicked(self, toolbutton):
        self.qpop(all=True)

    def pop_clicked(self, toolbutton):
        self.qpop()

    def push_clicked(self, toolbutton):
        self.qpush()

    def pushall_clicked(self, toolbutton):
        self.qpush(all=True)

    """ context menu signal handlers """

    def goto_activated(self, menuitem, row):
        self.qgoto(row[MQ_NAME])

    def delete_activated(self, menuitem, row):
        self.qdelete(row[MQ_NAME])

    def rename_activated(self, menuitem, row):
        self.qrename_ui(row[MQ_NAME])

    def finish_activated(self, menuitem, row):
        self.qfinish(applied=True)

    def fold_activated(self, menuitem, row):
        self.qfold(row[MQ_NAME])

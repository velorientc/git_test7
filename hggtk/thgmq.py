# thgmq.py - embeddable widget for MQ extension
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject
import pango

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
        self.mqloaded = hasattr(repo, 'mq')

        # side toolbar
        toolbar = gtk.Toolbar()
        toolbar.set_style(gtk.TOOLBAR_ICONS)
        toolbar.set_orientation(gtk.ORIENTATION_VERTICAL)
        toolbar.set_property('icon-size', gtk.ICON_SIZE_SMALL_TOOLBAR)

        self.btn = {}

        menubtn = gtk.MenuToolButton('')
        menubtn.set_menu(self.create_view_menu())
        toolbar.insert(menubtn, -1)
        self.btn['menu'] = menubtn
        def after_init():
            arrowbtn = menubtn.child.get_children()[1]
            arrowbtn.child.set(gtk.ARROW_DOWN, gtk.SHADOW_IN)
            menubtn.child.get_children()[0].hide()
        gobject.idle_add(after_init)

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
        self.list.connect('size-allocate', self.list_size_allocated)

        self.cols = {}
        self.cells = {}

        def addcol(header, col_idx, right=False, resizable=False,
                   editable=False, editfunc=None):
            header = (right and '%s ' or ' %s') % header
            cell = gtk.CellRendererText()
            if editable:
                cell.set_property('editable', True)
                cell.connect('edited', editfunc)
            col = gtk.TreeViewColumn(header, cell)
            col.add_attribute(cell, 'text', col_idx)
            col.set_cell_data_func(cell, self.cell_data_func)
            col.set_resizable(resizable)
            if right:
                col.set_alignment(1)
                cell.set_property('xalign', 1)
            self.list.append_column(col)
            self.cols[col_idx] = col
            self.cells[col_idx] = cell

        def cell_edited(cell, path, newname):
            patchname = self.model[path][MQ_NAME]
            if newname != patchname:
                self.qrename(newname, patch=patchname)

        addcol(_('#'), MQ_INDEX, right=True)
        addcol(_('Name'), MQ_NAME, editable=True, editfunc=cell_edited)
        addcol(_('Summary'), MQ_SUMMARY, resizable=True)

        pane.add(self.list)

        # prepare to show
        self.refresh()

    ### public functions ###

    def refresh(self):
        """
        Refresh the list of patches.
        This operation will try to keep selection state.
        """
        if not self.mqloaded:
            return

        # store patch selection state
        sel = self.list.get_selection()
        model, prevpaths = sel.get_selected_rows()

        # clear model data
        model.clear()

        # build list of patches
        from hgext import mq
        q = self.repo.mq
        q.parse_series()
        top = None
        applied = set([p.name for p in q.applied])
        for index, patchname in enumerate(q.series):
            stat = patchname in applied and 'A' or 'U'
            msg = mq.patchheader(q.join(patchname)).message[0]
            iter = model.append((index, stat, patchname, msg))
            if stat == 'A':
                top = iter

        # insert separator
        model.insert_after(top, (-1, '', '', ''))

        # restore patch selection state
        if len(prevpaths) > 0:
            for path in prevpaths:
                iter = self.get_iter_by_patchname(model[path][MQ_NAME])
                if iter:
                    sel.select_iter(iter)

        # update UI sensitives
        self.update_sensitives()

    def qgoto(self, patch):
        """
        [MQ] Execute 'qgoto' command.

        patch: the patch name or an index to specify the patch.
        """
        if not self.is_operable():
            return
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
        if not self.is_operable():
            return
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
        if not self.is_operable():
            return
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
        if not self.has_patch():
            return
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
        if not name or not self.has_patch():
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
        if not self.mqloaded or \
               patch == 'qtip' and 'qtip' in self.repo.tags():
            return False
        target = self.repo.mq.lookup(patch)
        if not target:
            return False
        path = self.get_path_by_patchname(target)
        if not path:
            return False
        # start editing patchname cell
        self.list.set_cursor_on_cell(path, self.cols[MQ_NAME], None, True)
        return True

    def qfinish(self, applied=False):
        """
        [MQ] Execute 'qfinish' command.

        applied: if True, enable '--applied' option. (default: False)
        """
        if not self.has_applied():
            return
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
        if not patch or not self.has_applied():
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

    def has_patch(self):
        """ return True if MQ has applicable patch """
        if self.mqloaded:
            return len(self.repo.mq.series) > 0
        return False

    def has_applied(self):
        """ return True if MQ has applied patches """
        if self.mqloaded:
            return len(self.repo.mq.applied) > 0
        return False

    def is_operable(self):
        """ return True if MQ is operable """
        if self.mqloaded:
            repo = self.repo
            if 'qtip' in self.repo.tags():
                return repo['.'] == repo['qtip']
            return len(repo.mq.series) > 0
        return False

    def get_iter_by_patchname(self, name):
        """ return iter has specified patch name """
        if name:
            for row in self.model:
                if row[MQ_NAME] == name:
                    return row.iter
        return None

    def get_path_by_patchname(self, name):
        """ return path has specified patch name """
        return self.model.get_path(self.get_iter_by_patchname(name))

    def get_qtip_patchname(self):
        if self.mqloaded and 'qtip' in self.repo.tags():
            return self.repo.mq.applied[-1].name
        return None

    def is_qtip(self, patchname):
        if patchname:
            return patchname == self.get_qtip_patchname()
        return False

    def update_sensitives(self):
        """ Update the sensitives of entire UI """
        def disable_mqmoves():
            for name in ('popall', 'pop', 'push', 'pushall'):
                self.btn[name].set_sensitive(False)
        if self.mqloaded:
            self.list.set_sensitive(True)
            self.btn['menu'].set_sensitive(True)
            if self.is_operable():
                q = self.repo.mq
                in_bottom = len(q.applied) == 0
                in_top = len(q.unapplied(self.repo)) == 0
                self.btn['popall'].set_sensitive(not in_bottom)
                self.btn['pop'].set_sensitive(not in_bottom)
                self.btn['push'].set_sensitive(not in_top)
                self.btn['pushall'].set_sensitive(not in_top)
            else:
                disable_mqmoves()
        else:
            self.list.set_sensitive(False)
            self.btn['menu'].set_sensitive(False)
            disable_mqmoves()

    def scroll_to_current(self):
        """
        Scroll to current patch in the patch list.
        If the patch is selected, it will do nothing.
        """
        if self.list.get_selection().count_selected_rows() > 0:
            return
        qtipname = self.get_qtip_patchname()
        if not qtipname:
            return
        path = self.get_path_by_patchname(qtipname)
        if path:
            self.list.scroll_to_cell(path)

    def cell_data_func(self, column, cell, model, iter):
        row = model[iter]

        stat = row[MQ_STATUS]
        if stat == 'A':
            cell.set_property('foreground', 'blue')
        elif stat == 'U':
            cell.set_property('foreground', '#909090')
        else:
            cell.set_property('foreground', 'black')

        patchname = row[MQ_NAME]
        if self.is_qtip(patchname):
            cell.set_property('weight', pango.WEIGHT_BOLD)
        else:
            cell.set_property('weight', pango.WEIGHT_NORMAL)

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

        is_top = self.is_qtip(row[MQ_NAME])
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

    def create_view_menu(self):
        menu = gtk.Menu()

        def append(label, col_idx):
            item = gtk.CheckMenuItem(label)
            item.set_active(True)
            item.set_border_width(1)
            item.set_draw_as_radio(True)
            def handler(menuitem):
                col = self.cols[col_idx]
                col.set_visible(menuitem.get_active())
            item.connect('activate', handler)
            menu.append(item)

        append(_('Show index'), MQ_INDEX)
        append(_('Show name'), MQ_NAME)
        append(_('Show summary'), MQ_SUMMARY)

        menu.show_all()
        return menu

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
        if self.get_qtip_patchname() != patchname:
            self.qgoto(patchname)

    def list_size_allocated(self, list, req):
        if self.mqloaded and self.has_applied():
            self.scroll_to_current()

    def popall_clicked(self, toolbutton):
        self.qpop(all=True)

    def pop_clicked(self, toolbutton):
        self.qpop()

    def push_clicked(self, toolbutton):
        self.qpush()

    def pushall_clicked(self, toolbutton):
        self.qpush(all=True)

    ### context menu signal handlers ###

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

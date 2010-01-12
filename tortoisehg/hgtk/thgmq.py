# thgmq.py - embeddable widget for MQ extension
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gtk.keysyms
import gobject
import pango

from mercurial import extensions, error

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib

from tortoisehg.hgtk import gdialog, gtklib, hgcmd

# MQ patches row enumerations
MQ_INDEX   = 0
MQ_STATUS  = 1
MQ_NAME    = 2
MQ_SUMMARY = 3
MQ_ESCAPED = 4

# Special patch indices
INDEX_SEPARATOR = -1
INDEX_QPARENT   = -2

class MQWidget(gtk.VBox):

    __gproperties__ = {
        'index-column-visible': (gobject.TYPE_BOOLEAN,
                                    'Index',
                                    'Show index column',
                                    False,
                                    gobject.PARAM_READWRITE),
        'status-column-visible': (gobject.TYPE_BOOLEAN,
                                    'Status',
                                    'Show status column',
                                    False,
                                    gobject.PARAM_READWRITE),
        'name-column-visible': (gobject.TYPE_BOOLEAN,
                                    'Name',
                                    'Show name column',
                                    False,
                                    gobject.PARAM_READWRITE),
        'summary-column-visible': (gobject.TYPE_BOOLEAN,
                                    'Summary',
                                    'Show summary column',
                                    False,
                                    gobject.PARAM_READWRITE),
        'editable-cell': (gobject.TYPE_BOOLEAN,
                            'EditableCell',
                            'Enable editable cells',
                            False,
                            gobject.PARAM_READWRITE),
        'show-qparent': (gobject.TYPE_BOOLEAN,
                            'ShowQParent',
                            "Show 'qparent'",
                            False,
                            gobject.PARAM_READWRITE)
    }

    __gsignals__ = {
        'repo-invalidated': (gobject.SIGNAL_RUN_FIRST,
                             gobject.TYPE_NONE,
                             ()),
        'patch-selected': (gobject.SIGNAL_RUN_FIRST,
                           gobject.TYPE_NONE,
                           (int,  # revision number
                            str)) # patch name
    }

    def __init__(self, repo, statusbar, accelgroup=None, tooltips=None):
        gtk.VBox.__init__(self)

        self.repo = repo
        self.mqloaded = hasattr(repo, 'mq')
        self.statusbar = statusbar

        try:
            extensions.find('qup')
            self.hasqup = True
        except KeyError:
            self.hasqup = False

        # top toolbar
        tbar = gtklib.SlimToolbar(tooltips)

        ## buttons
        self.btn = {}
        popallbtn = tbar.append_button(gtk.STOCK_GOTO_FIRST,
                                      _('Unapply all patches'))
        popallbtn.connect('clicked', self.popall_clicked)
        self.btn['popall'] = popallbtn

        popbtn = tbar.append_button(gtk.STOCK_GO_BACK,
                                   _('Unapply last patch'))
        popbtn.connect('clicked', self.pop_clicked)
        self.btn['pop'] = popbtn

        pushbtn = gtk.ToolButton(gtk.STOCK_GO_FORWARD)
        pushbtn = tbar.append_button(gtk.STOCK_GO_FORWARD,
                                    _('Apply next patch'))
        pushbtn.connect('clicked', self.push_clicked)
        self.btn['push'] = pushbtn

        pushallbtn = tbar.append_button(gtk.STOCK_GOTO_LAST,
                                       _('Apply all patches'))
        pushallbtn.connect('clicked', self.pushall_clicked)
        self.btn['pushall'] = pushallbtn

        ## separator
        tbar.append_space()

        ## drop-down menu
        menubtn = gtk.MenuToolButton('')
        menubtn.set_menu(self.create_view_menu())
        tbar.append_widget(menubtn, padding=0)
        self.btn['menu'] = menubtn
        def after_init():
            menubtn.child.get_children()[0].hide()
        gtklib.idle_add_single_call(after_init)
        self.pack_start(tbar, False, False)

        # center pane
        mainbox = gtk.VBox()
        self.pack_start(mainbox, True, True)

        ## scrolled pane
        pane = gtk.ScrolledWindow()
        pane.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        pane.set_shadow_type(gtk.SHADOW_IN)
        mainbox.pack_start(pane)

        ### patch list
        self.model = gtk.ListStore(int, # patch index
                                   str, # patch status
                                   str, # patch name
                                   str, # summary (utf-8)
                                   str) # escaped summary (utf-8)
        self.list = gtk.TreeView(self.model)
        self.list.set_row_separator_func(self.row_sep_func)
        # To support old PyGTK (<2.12)
        if hasattr(self.list, 'set_tooltip_column'):
            self.list.set_tooltip_column(MQ_ESCAPED)
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
            if editfunc:
                cell.set_property('editable', editable)
                cell.connect('edited', editfunc)
            col = gtk.TreeViewColumn(header, cell)
            col.add_attribute(cell, 'text', col_idx)
            col.set_cell_data_func(cell, self.cell_data_func)
            col.set_resizable(resizable)
            col.set_visible(self.get_property(self.col_to_prop(col_idx)))
            if right:
                col.set_alignment(1)
                cell.set_property('xalign', 1)
            self.list.append_column(col)
            self.cols[col_idx] = col
            self.cells[col_idx] = cell

        def cell_edited(cell, path, newname):
            row = self.model[path]
            if row[MQ_INDEX] < 0:
                return
            patchname = row[MQ_NAME]
            if newname != patchname:
                self.qrename(newname, patch=patchname)

        addcol(_('#'), MQ_INDEX, right=True)
        addcol(_('st'), MQ_STATUS)
        addcol(_('Patch'), MQ_NAME, editfunc=cell_edited)
        addcol(_('Summary'), MQ_SUMMARY, resizable=True)

        pane.add(self.list)

        ## command widget
        self.cmd = hgcmd.CmdWidget(style=hgcmd.STYLE_COMPACT,
                                   tooltips=tooltips)
        mainbox.pack_start(self.cmd, False, False)

        # accelerators
        if accelgroup:

            key, mod = gtk.accelerator_parse('F2')
            self.list.add_accelerator('thg-rename', accelgroup,
                    key, mod, gtk.ACCEL_VISIBLE)
            def thgrename(list):
                sel = self.list.get_selection()
                if sel.count_selected_rows() == 1:
                    model, paths = sel.get_selected_rows()
                    self.qrename_ui(model[paths[0]][MQ_NAME])
            self.list.connect('thg-rename', thgrename)

            mod = gtk.gdk.CONTROL_MASK

            def mq_move(tree, key):
                oldrow = tree.get_cursor()[0][0]
                minval = self.separator_pos + 1
                if oldrow < minval:
                    return True
                maxval = len(self.model) - 1
                if key == gtk.keysyms.Up:
                    newrow = oldrow - 1
                elif key == gtk.keysyms.Down:
                    newrow = oldrow + 1
                elif key == gtk.keysyms.Page_Up:
                    newrow = minval
                elif key == gtk.keysyms.Page_Down:
                    newrow = maxval
                else:
                    return True
                if newrow != oldrow and newrow >= minval and newrow <= maxval:
                    self.move_patch(oldrow, newrow)
                return True

            def add(name, key, hook=None):
                self.list.add_accelerator(name, accelgroup, key, mod, 0)
                if hook:
                    self.list.connect(name, hook)
                else:
                    self.list.connect(name, mq_move, key)

            add('mq-move-up', gtk.keysyms.Up)
            add('mq-move-down', gtk.keysyms.Down)
            add('mq-move-top', gtk.keysyms.Page_Up)
            add('mq-move-bottom', gtk.keysyms.Page_Down)
            add('mq-pop', gtk.keysyms.Left, lambda _: self.qpop())
            add('mq-push', gtk.keysyms.Right, lambda _: self.qpush())

    def move_patch(self, oldidx, newidx):

        def list_move_item(list, oldpos, newpos):
            olditem = list[oldpos]
            del list[oldpos]
            list.insert(newpos, olditem)

        # Update series
        p = self.repo.mq
        model = self.model
        oldrow = model[oldidx]
        newrow = model[newidx]
        list_move_item(p.full_series, p.find_series(oldrow[MQ_NAME]),
                                      p.find_series(newrow[MQ_NAME]))
        p.series_dirty = True
        p.save_dirty()

        # Update TreeView
        if newidx < oldidx:
            model.move_before(oldrow.iter, newrow.iter)
        else:
            model.move_after(oldrow.iter, newrow.iter)
        begin = min(oldidx, newidx)
        offset = min(oldrow[MQ_INDEX], newrow[MQ_INDEX]) - begin
        for i in xrange(begin, max(oldidx, newidx) + 1):
            model[i][MQ_INDEX] = i + offset


    ### public functions ###

    def refresh(self):
        """
        Refresh the list of patches.
        This operation will try to keep selection state.
        """
        if not self.mqloaded:
            return

        # store selected patch name
        selname = None
        model, paths = self.list.get_selection().get_selected_rows()
        if len(paths) > 0:
            selname = model[paths[0]][MQ_NAME]

        # clear model data
        self.model.clear()

        # insert 'qparent' row
        top = None
        if self.get_property('show-qparent'):
            top = self.model.append((INDEX_QPARENT, None, None, None, None))

        # add patches
        from hgext import mq
        q = self.repo.mq
        q.parse_series()
        applied = set([p.name for p in q.applied])
        for index, patchname in enumerate(q.series):
            stat = patchname in applied and 'A' or 'U'
            try:
                msg = hglib.toutf(mq.patchheader(q.join(patchname)).message[0])
                msg_esc = gtklib.markup_escape_text(msg)
            except IndexError:
                msg = msg_esc = None
            iter = self.model.append((index, stat, patchname, msg, msg_esc))
            if stat == 'A':
                top = iter

        # insert separator
        if top:
            row = self.model.insert_after(top, (INDEX_SEPARATOR, None, None, None, None))
            self.separator_pos = self.model.get_path(row)[0]

        # restore patch selection
        if selname:
            iter = self.get_iter_by_patchname(selname)
            if iter:
                self.list.get_selection().select_iter(iter)

        # update UI sensitives
        self.update_sensitives()

        # report status
        status_text = ''
        idle_text = None
        if self.has_mq():
            nser = len(self.repo.mq.series)
            if nser:
                napp = len(self.repo.mq.applied)
                status_text = _('%(count)d of %(total)d Patches applied') % {
                        'count': napp, 'total': nser}
                if napp:
                    pn = self.get_qtip_patchname()
                    idle_text = _("Patch '%s' applied") % pn
        self.statusbar.set_right3_text(status_text)
        self.statusbar.set_idle_text(idle_text)

    def set_repo(self, repo):
        self.repo = repo

    def qgoto(self, patch):
        """
        [MQ] Execute 'qgoto' command.

        patch: the patch name or an index to specify the patch.
        """
        if not self.is_operable():
            return
        cmdline = ['hg', 'qgoto', patch]
        self.cmd.execute(cmdline, self.cmd_done)

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
        self.cmd.execute(cmdline, self.cmd_done)

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
        self.cmd.execute(cmdline, self.cmd_done)

    def qdelete(self, patch, keep=False):
        """
        [MQ] Execute 'qdelete' command.

        patch: the patch name or an index to specify the patch.
        keep: if True, use '--keep' option. (default: False)
        """
        if not self.has_patch():
            return
        if not keep:
            ret = gdialog.CustomPrompt(_('Confirm Delete'),
                          _('Do you want to delete?'), None,
                          (_('&Yes'), _('Yes (&keep)'),
                          _('&Cancel')), default=2, esc=2).run()
            if ret == 0:
                pass
            elif ret == 1:
                keep = True
            else:
                return
        cmdline = ['hg', 'qdelete', patch]
        if keep:
            cmdline.append('--keep')
        self.cmd.execute(cmdline, self.cmd_done, noemit=True)

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
        self.cmd.execute(cmdline, self.cmd_done)

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
        # make the cell editable
        cell = self.cells[MQ_NAME]
        if not cell.get_property('editable'):
            cell.set_property('editable', True)
            def canceled(cell, *arg):
                cell.disconnect(cancel_id)
                cell.disconnect(edited_id)
                cell.set_property('editable', False)
            cancel_id = cell.connect('editing-canceled', canceled)
            edited_id = cell.connect('edited', canceled)
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
        self.cmd.execute(cmdline, self.cmd_done)

    def qfold(self, patch):
        """
        [MQ] Execute 'qfold' command.

        patch: the patch name or an index to specify the patch.
        """
        if not patch or not self.has_applied():
            return
        data = dict(target=patch, qtip=self.get_qtip_patchname())
        ret = gdialog.Confirm(_('Confirm Fold'), [], None,
                    _("Do you want to fold un-applied patch '%(target)s'"
                      " into current patch '%(qtip)s'?") % data).run()
        if ret != gtk.RESPONSE_YES:
            return
        cmdline = ['hg', 'qfold', patch]
        self.cmd.execute(cmdline, self.cmd_done)

    def mknext(self, patch):
        """
        [MQ] Execute 'qup patch'

        patch: the patch name or an index to specify the patch.
        """
        if not (self.hasqup and patch and self.is_operable()):
            return
        cmdline = ['hg', 'qup', patch]
        self.cmd.execute(cmdline, self.cmd_done)

    def has_mq(self):
        return self.mqloaded and os.path.isdir(self.repo.mq.path)

    def has_patch(self):
        """ return True if MQ has applicable patches """
        return bool(self.get_num_patches())

    def has_applied(self):
        """ return True if MQ has applied patches """
        return bool(self.get_num_applied())

    def get_num_patches(self):
        """ return the number of patches in patch queue """
        if self.mqloaded:
            return len(self.repo.mq.series)
        return 0

    def get_num_applied(self):
        """ return the number of applied patches """
        if self.mqloaded:
            return len(self.repo.mq.applied)
        return 0

    def is_operable(self):
        """ return True if MQ is operable """
        if self.mqloaded:
            repo = self.repo
            if 'qtip' in self.repo.tags():
                return repo['.'] == repo['qtip']
            return len(repo.mq.series) > 0
        return False

    def is_qtip(self, patchname):
        if patchname:
            return patchname == self.get_qtip_patchname()
        return False

    ### internal functions ###

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

        if row[MQ_INDEX] == INDEX_QPARENT:
            if column == self.cols[MQ_INDEX]:
                cell.set_property('text', '')
            elif column == self.cols[MQ_NAME]:
                cell.set_property('text', '[qparent]')

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
        return model[iter][MQ_INDEX] == INDEX_SEPARATOR

    def show_patch_cmenu(self, list, path):
        row = self.model[path]
        if row[MQ_INDEX] == INDEX_SEPARATOR:
            return

        menu = gtk.Menu()
        def append(label, handler=None):
            item = gtk.MenuItem(label, True)
            item.set_border_width(1)
            if handler:
                item.connect('activate', handler, row)
            menu.append(item)

        is_operable = self.is_operable()
        has_patch = self.has_patch()
        has_applied = self.has_applied()
        is_qtip = self.is_qtip(row[MQ_NAME])
        is_qparent = row[MQ_INDEX] == INDEX_QPARENT
        is_applied = row[MQ_STATUS] == 'A'
        is_next = row[MQ_INDEX] == self.get_num_applied()

        if is_operable and not is_qtip and (not is_qparent or has_applied):
            append(_('_Goto'), self.goto_activated)
        if has_patch and not is_qparent:
            append(_('_Rename'), self.rename_activated)
        if has_applied and not is_qparent:
            append(_('_Finish Applied'), self.finish_activated)
        if not is_applied and not is_qparent:
            append(_('_Delete'), self.delete_activated)
            if has_applied and not is_qparent:
                append(_('F_old'), self.fold_activated)
            if self.hasqup and not is_next:
                append(_('Make It _Next'), self.mknext_activated)

        if len(menu.get_children()) > 0:
            menu.show_all()
            menu.popup(None, None, None, 0, 0)

    def create_view_menu(self):
        menu = gtk.Menu()
        def append(item=None, handler=None, check=False,
                   active=False, sep=False):
            if sep:
                item = gtk.SeparatorMenuItem()
            else:
                if isinstance(item, str):
                    if check:
                        item = gtk.CheckMenuItem(item)
                        item.set_active(active)
                    else:
                        item = gtk.MenuItem(item)
                item.set_border_width(1)
            if handler:
                item.connect('activate', handler)
            menu.append(item)
            return item
        def colappend(label, col_idx, active=True):
            def handler(menuitem):
                col = self.cols[col_idx]
                col.set_visible(menuitem.get_active())
            propname = self.col_to_prop(col_idx)
            item = append(label, handler, check=True, active=active)
            self.vmenu[propname] = item

        self.vmenu = {}

        colappend(_('Show Index'), MQ_INDEX)
        colappend(_('Show Status'), MQ_STATUS, active=False)
        colappend(_('Show Summary'), MQ_SUMMARY, active=False)

        append(sep=True)

        def enable_editable(item):
            self.cells[MQ_NAME].set_property('editable', item.get_active())
        item = append(_('Enable editable cells'), enable_editable,
                check=True, active=False)
        self.vmenu['editable-cell'] = item
        item = append(_("Show 'qparent'"), lambda item: self.refresh(),
                check=True, active=True)
        self.vmenu['show-qparent'] = item

        menu.show_all()
        return menu

    def qgoto_by_row(self, row):
        if self.get_qtip_patchname() == row[MQ_NAME]:
            return
        if row[MQ_INDEX] == INDEX_QPARENT:
            self.qpop(all=True)
        else:
            self.qgoto(row[MQ_NAME])

    def cmd_done(self, returncode, useraborted, noemit=False):
        if returncode == 0:
            if self.cmd.get_pbar():
                self.cmd.set_result(_('Succeed'), style='ok')
        elif useraborted:
            self.cmd.set_result(_('Canceled'), style='error')
        else:
            self.cmd.set_result(_('Failed'), style='error')
        self.repo.mq.invalidate()
        self.refresh()
        if not noemit:
            self.emit('repo-invalidated')

    def do_get_property(self, property):
        if property.name == 'name-column-visible':
            return True
        try:
            return self.vmenu[property.name].get_active()
        except:
            raise AttributeError, 'unknown property %s' % property.name

    def do_set_property(self, property, value):
        try:
            self.vmenu[property.name].set_active(value)
        except:
            raise AttributeError, 'unknown property %s' % property.name

    def col_to_prop(self, col_idx):
        if col_idx == MQ_INDEX:
            return 'index-column-visible'
        if col_idx == MQ_STATUS:
            return 'status-column-visible'
        elif col_idx == MQ_NAME:
            return 'name-column-visible'
        elif col_idx == MQ_SUMMARY:
            return 'summary-column-visible'
        return ''

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
                gtklib.idle_add_single_call(unselect)
        elif event.button == 3:
            if pathinfo:
                self.show_patch_cmenu(self.list, pathinfo[0])

    def list_sel_changed(self, list):
        path, focus = list.get_cursor()
        row = self.model[path]
        if row[MQ_INDEX] < 0:
            return
        patchname = row[MQ_NAME]
        try:
            ctx = self.repo[patchname]
            revid = ctx.rev()
        except (error.RepoError, error.RepoLookupError):
            revid = -1
        self.emit('patch-selected', revid, patchname)

    def list_row_activated(self, list, path, column):
        self.qgoto_by_row(self.model[path])

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
        self.qgoto_by_row(row)

    def delete_activated(self, menuitem, row):
        self.qdelete(row[MQ_NAME])

    def rename_activated(self, menuitem, row):
        self.qrename_ui(row[MQ_NAME])

    def finish_activated(self, menuitem, row):
        self.qfinish(applied=True)

    def fold_activated(self, menuitem, row):
        self.qfold(row[MQ_NAME])

    def mknext_activated(self, menuitem, row):
        self.mknext(row[MQ_NAME])

# thgpbranch.py - embeddable widget for the PatchBranch extension
#
# Copyright 2009 Peer Sommerlund <peer.sommerlund@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import gobject

from mercurial import extensions

from tortoisehg.util.i18n import _

from tortoisehg.hgtk import gtklib, dialog
from tortoisehg.hgtk.logview import graphcell

# Patch Branch model enumeration
M_NODE      = 0
M_IN_LINES  = 1
M_OUT_LINES = 2
M_NAME      = 3

# Patch Branch column enumeration
PB_GRAPH   = 0
PB_NAME    = 1

class PBranchWidget(gtk.VBox):

    __gproperties__ = {
        'graph-column-visible': (gobject.TYPE_BOOLEAN,
                                    'Graph',
                                    'Show graph column',
                                    False,
                                    gobject.PARAM_READWRITE),
        'name-column-visible': (gobject.TYPE_BOOLEAN,
                                    'Name',
                                    'Show name column',
                                    False,
                                    gobject.PARAM_READWRITE),
        'show-internal-branches': (gobject.TYPE_BOOLEAN,
                            'ShowInternalBranches',
                            "Show internal branches",
                            False,
                            gobject.PARAM_READWRITE)
    }

    __gsignals__ = {
        'repo-invalidated': (gobject.SIGNAL_RUN_FIRST,
                             gobject.TYPE_NONE,
                             ()),
    }

    def __init__(self, repo, statusbar, accelgroup=None, tooltips=None):
        gtk.VBox.__init__(self)

        self.repo = repo
        self.pbranch = extensions.find('pbranch')
        self.statusbar = statusbar

        # top toolbar
        tbar = gtklib.SlimToolbar(tooltips)

        ## buttons
        self.btn = {}
        pmergebtn = tbar.append_stock(gtk.STOCK_CONVERT,
                                      _('Merge pending dependencies'))
        pmergebtn.connect('clicked', self.pmerge_clicked)
        self.btn['pmerge'] = pmergebtn

        pbackoutbtn = tbar.append_stock(gtk.STOCK_GO_BACK,
                                   _('Backout current patch branch'))
        pbackoutbtn.connect('clicked', self.pbackout_clicked)
        self.btn['pbackout'] = pbackoutbtn

        reapplybtn = gtk.ToolButton(gtk.STOCK_GO_FORWARD)
        reapplybtn = tbar.append_stock(gtk.STOCK_GO_FORWARD,
                                    _('Backport part of a changeset to a dependency'))
        reapplybtn.connect('clicked', self.reapply_clicked)
        self.btn['reapply'] = reapplybtn

        pnewbtn = tbar.append_stock(gtk.STOCK_NEW,
                                       _('Start a new patch branch'))
        pnewbtn.connect('clicked', self.pnew_clicked)
        self.btn['pnew'] = pnewbtn

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
        #### patch list model
        self.model = gtk.ListStore(
                gobject.TYPE_PYOBJECT, # node info
                gobject.TYPE_PYOBJECT, # in-lines
                gobject.TYPE_PYOBJECT, # out-lines
                str) # patch name
        #### patch list view
        self.list = gtk.TreeView(self.model)
        self.list.connect('size-allocate', self.list_size_allocated)

        #### patch list columns
        self.cols = {}
        self.cells = {}

        def addcol(header, col_idx, model_idx=None, right=False, resizable=False,
                   editable=False, editfunc=None, cell_renderer=None,
                   properties=[]):
            header = (right and '%s ' or ' %s') % header
            cell = cell_renderer or gtk.CellRendererText()
            if editfunc:
                cell.set_property('editable', editable)
                cell.connect('edited', editfunc)
            col = gtk.TreeViewColumn(header, cell)
            if cell_renderer is None:
                col.add_attribute(cell, 'text', model_idx)
            col.set_resizable(resizable)
            col.set_visible(self.get_property(self.col_to_prop(col_idx)))
            if right:
                col.set_alignment(1)
                cell.set_property('xalign', 1)
            for (property_name, model_index) in properties:
                col.add_attribute(cell, property_name, model_index)
            self.list.append_column(col)
            self.cols[col_idx] = col
            self.cells[col_idx] = cell

        def cell_edited(cell, path, newname):
            row = self.model[path]
            patchname = row[PB_NAME]
            if newname != patchname:
                self.qrename(newname, patch=patchname)

        #### patch list columns and cell renderers

        addcol(_('Graph'), PB_GRAPH, resizable=True, 
            cell_renderer=graphcell.CellRendererGraph(),
            properties=[("node", M_NODE), 
                        ("in-lines",M_IN_LINES), 
                        ("out-lines", M_OUT_LINES)]
            )
        addcol(_('Name'), PB_NAME, M_NAME, editfunc=cell_edited)

        pane.add(self.list)

        # accelerator
        if accelgroup:
            # TODO
            pass

    ### public functions ###

    def refresh(self):
        """
        Refresh the list of patches.
        This operation will try to keep selection state.
        """
        if not self.pbranch:
            return

        # store selected patch name
        selname = None
        model, paths = self.list.get_selection().get_selected_rows()
        if len(paths) > 0:
            selname = model[paths[0]][PB_NAME]

        # compute model data
        self.model.clear()
        opts = {}
        mgr = self.pbranch.patchmanager(self.repo.ui, self.repo, opts)
        graph = mgr.graphforopts(opts)
        if not self.get_property('show-internal-branches'):
            graph = mgr.patchonlygraph(graph)
        names = None
        patch_list = graph.topolist(names)
        in_lines = []
        if patch_list:
            dep_list = [patch_list[0]]
        for name in patch_list:
            parents = graph.deps(name)

            # Node properties
            if name in dep_list: 
                node_col = dep_list.index(name)
            else:
                node_col = len(dep_list)
            node = (node_col,0,0) #             (column, colour, status) tuple to draw revision node,
            
            # Find next dependency list
            my_deps = []
            for p in parents:
                if p not in dep_list:
                    my_deps.append(p)
            next_dep_list = dep_list[:]
            next_dep_list[node_col:node_col+1] = my_deps
            
            # Dependency lines
            shift = len(parents) - 1
            out_lines = []
            for p in parents:
                dep_col = next_dep_list.index(p)
                colour = 0 # black
                style = 0 # solid lines
                out_lines.append((node_col, dep_col, colour, style))
            for lines in in_lines:
                (start, end, colour, style) = lines
                if end == node_col:
                    # Deps to current patch end here
                    pass
                else:
                    # Find line continuations
                    dep = dep_list[end]
                    dep_col = next_dep_list.index(dep)
                    out_lines.append((end, dep_col, colour, style))
                    
            stat = '?' # patch status
            patchname = name
            msg = '%s' % parents # summary (utf-8)
            msg_esc = 'what-is-this-for' # escaped summary (utf-8)
            self.model.append((node, in_lines, out_lines, patchname))
            # Loop
            in_lines = out_lines
            dep_list = next_dep_list


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
        if self.has_patch():
            status_text = self.pending_merges() \
                and _('pending pmerges') \
                or _('no pending pmerges')
        self.statusbar.set_right3_text(status_text)
        self.statusbar.set_idle_text(idle_text)

    def pgraph(self):
        """
        [pbranch] Execute 'pgraph' command.
        
        :returns: A list of patches and dependencies
        """
        if self.pbranch is None:
            return None
        opts = {}
        mgr = self.pbranch.patchmanager(self.repo.ui, self.repo, opts)
        return mgr.graphforopts(opts)

    def patch_list(self, opts={}):
        """List all patches in pbranch dependency DAG"""
        mgr = self.pbranch.patchmanager(self.repo.ui, self.repo, opts)
        graph = mgr.graphforopts(opts)
        names = None
        return graph.topolist(names)
        
    def pending_merges(self):
        """Return True if there are pending pmerge operations"""
        for patch in self.patch_list():
            if self.pstatus(patch):
                return True
        return False

    def pstatus(self, patch_name):
        """
        [pbranch] Execute 'pstatus' command.
        
        :param patch_name: Name of patch-branch
        :retv: list of status messages. If empty there is no pending merges
        """
        if self.pbranch is None:
            return None
        status = []
        opts = {}
        mgr = self.pbranch.patchmanager(self.repo.ui, self.repo, opts)
        graph = mgr.graphforopts(opts)
        heads = self.repo.branchheads(patch_name)
        if len(heads) > 1:
            status.append(_('needs merge of %i heads\n') % len(heads))
        for dep, through in graph.pendingmerges(patch_name):
            if through:
                status.append(_('needs merge with %s (through %s)\n') %
                          (dep, ", ".join(through)))
            else:
                status.append(_('needs merge with %s\n') % dep)
        for dep in graph.pendingrebases(patch_name):
            status.append(_('needs update of diff base to tip of %s\n') % dep)
        return status

    def pnew_ui(self):
        """
        Create new patch.
        Propmt user for new patch name. Patch is created
        on current branch.
        """
        parent =  None
        title = _('New Patch Name')
        new_name = dialog.entry_dialog(parent, title)
        if not new_name:
            return False
        self.pnew(new_name)
        return True

    def pnew(self, patch_name):
        """
        [pbranch] Execute 'pnew' command.
        
        :param patch_name: Name of new patch-branch
        """
        if self.pbranch is None:
            return False
        self.pbranch.cmdnew(self.repo.ui, self.repo, patch_name)
        self.emit('repo-invalidated')
        return True
        
    def pmerge(self):
        """
        [pbranch] Execute 'pmerge' command.
        """
        assert False
        
    def pbackout(self):
        """
        [pbranch] Execute 'pbackout' command.
        """
        assert False

    def has_pbranch(self):
        return self.pbranch is not None

    def has_patch(self):
        return self.has_pbranch() and self.pgraph() != []

    def cur_patch(self):
        current_patch = self.repo.dirstate.branch()
        if current_patch == 'default':
            return None
        if current_patch not in self.patch_list():
            return None
        return current_patch

    ### internal functions ###

    def get_iter_by_patchname(self, name):
        """ return iter has specified patch name """
        if name:
            for row in self.model:
                if row[PB_NAME] == name:
                    return row.iter
        return None

    def get_path_by_patchname(self, name):
        """ return path has specified patch name """
        return self.model.get_path(self.get_iter_by_patchname(name))

    def update_sensitives(self):
        """ Update the sensitives of entire UI """
        def disable_pbranchcmd():
            for name in ('pbackout', 'pmerge', 'pnew', 'reapply'):
                self.btn[name].set_sensitive(False)
        if self.pbranch:
            self.list.set_sensitive(True)
            self.btn['menu'].set_sensitive(True)
            in_pbranch = True #TODO
            self.btn['pmerge'].set_sensitive(in_pbranch)
            self.btn['pbackout'].set_sensitive(in_pbranch)
            self.btn['pnew'].set_sensitive(True)
            self.btn['reapply'].set_sensitive(True)
        else:
            self.list.set_sensitive(False)
            self.btn['menu'].set_sensitive(False)
            disable_pbranchcmd()

    def scroll_to_current(self):
        """
        Scroll to current patch in the patch list.
        If the patch is selected, it will do nothing.
        """
        if self.list.get_selection().count_selected_rows() > 0:
            return
        curpatch = self.cur_patch()
        if not curpatch:
            return
        path = self.get_path_by_patchname(curpatch)
        if path:
            self.list.scroll_to_cell(path)

    def show_patch_cmenu(self, list, path):
        """Context menu for selected patch"""
        row = self.model[path]

        menu = gtk.Menu()
        def append(label, handler=None):
            item = gtk.MenuItem(label, True)
            item.set_border_width(1)
            if handler:
                item.connect('activate', handler, row)
            menu.append(item)

        is_operable = self.is_operable()
        has_patch = self.has_patch()

        append(_('_goto (update workdir)'), self.update_activated)
        append(_('_rename'), self.rename_activated)
        append(_('_delete'), self.delete_activated)

        if len(menu.get_children()) > 0:
            menu.show_all()
            menu.popup(None, None, None, 0, 0)

    def create_view_menu(self):
        """Top right menu for selection of columns and 
        view configuration."""
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

        colappend(_('Show graph'), PB_GRAPH)
        colappend(_('Show name'), PB_NAME)

        append(sep=True)

        def enable_editable(item):
            self.cells[PB_NAME].set_property('editable', item.get_active())
        item = append(_('Enable editable cells'), enable_editable,
                check=True, active=False)
        self.vmenu['editable-cell'] = item
        item = append(_("Show internal branches"), lambda item: self.refresh(),
                check=True, active=False)
        self.vmenu['show-internal-branches'] = item

        menu.show_all()
        return menu

    def do_get_property(self, property):
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
        if col_idx == PB_GRAPH:
            return 'graph-column-visible'
        if col_idx == PB_NAME:
            return 'name-column-visible'
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
        patchname = row[PB_NAME]
        try:
            ctx = self.repo[patchname]
            revid = ctx.rev()
        except hglib.RepoError:
            revid = -1
        self.emit('patch-selected', revid, patchname)

    def list_row_activated(self, list, path, column):
        self.qgoto_by_row(self.model[path])

    def list_size_allocated(self, list, req):
        if self.has_patch():
            self.scroll_to_current()

    def pbackout_clicked(self, toolbutton):
        pass

    def pmerge_clicked(self, toolbutton):
        pass

    def pnew_clicked(self, toolbutton):
        self.pnew_ui()

    def reapply_clicked(self, toolbutton):
        pass

    ### context menu signal handlers ###

    def pnew_activated(self, menuitem, row):
        """Insert new patch after this row"""
        if self.cur_patch() == row[M_NAME]:
            self.pnew_ui()
            return
        # pnew from patch different than current
        assert False
        if self.wdir_modified():
            # Ask user if current changes should be discarded
            # Abort if user does not agree
            pass
        # remember prev branch
        # Update to row[M_NAME]
        # pnew_ui
        # if aborted, update back to prev branch
        pass
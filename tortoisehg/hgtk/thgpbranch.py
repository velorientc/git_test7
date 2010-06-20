# thgpbranch.py - embeddable widget for the PatchBranch extension
#
# Copyright 2009 Peer Sommerlund <peer.sommerlund@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import tempfile
import gtk
import gobject

from mercurial import cmdutil, extensions, util
from mercurial import commands as hg
import mercurial.ui

from tortoisehg.util.i18n import _

from tortoisehg.hgtk import hgcmd
from tortoisehg.hgtk import update
from tortoisehg.hgtk import gtklib, dialog
from tortoisehg.hgtk.logview import graphcell

# Patch Branch model enumeration
M_NODE      = 0
M_IN_LINES  = 1
M_OUT_LINES = 2
M_NAME      = 3
M_STATUS    = 4
M_TITLE     = 5
M_MSG       = 6
M_MSGESC    = 7

# Patch Branch column enumeration
C_GRAPH   = 0
C_STATUS  = 1
C_NAME    = 2
C_TITLE   = 3
C_MSG     = 4

class PBranchWidget(gtk.VBox):

    __gproperties__ = {
        'graph-column-visible': (gobject.TYPE_BOOLEAN,
                                    'Graph',
                                    'Show graph column',
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
        'title-column-visible': (gobject.TYPE_BOOLEAN,
                                    'Title',
                                    'Show title column',
                                    False,
                                    gobject.PARAM_READWRITE),
        'message-column-visible': (gobject.TYPE_BOOLEAN,
                                    'Title',
                                    'Show title column',
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
        'patch-selected': (gobject.SIGNAL_RUN_FIRST,
                           gobject.TYPE_NONE,
                           (int,  # revision number for patch head
                            str)) # patch name
    }

    def __init__(self, parentwin, repo, statusbar, accelgroup=None, tooltips=None):
        gtk.VBox.__init__(self)

        self.parent_window = parentwin
        self.repo = repo
        self.pbranch = extensions.find('pbranch')
        self.statusbar = statusbar

        # top toolbar
        tbar = gtklib.SlimToolbar(tooltips)

        ## buttons
        self.btn = {}
        pmergebtn = tbar.append_button(gtk.STOCK_CONVERT,
                                      _('Merge all pending dependencies'))
        pmergebtn.connect('clicked', self.pmerge_clicked)
        self.btn['pmerge'] = pmergebtn

        pbackoutbtn = tbar.append_button(gtk.STOCK_GO_BACK,
                                   _('Backout current patch branch'))
        pbackoutbtn.connect('clicked', self.pbackout_clicked)
        self.btn['pbackout'] = pbackoutbtn

        reapplybtn = gtk.ToolButton(gtk.STOCK_GO_FORWARD)
        reapplybtn = tbar.append_button(gtk.STOCK_GO_FORWARD,
                                    _('Backport part of a changeset to a dependency'))
        reapplybtn.connect('clicked', self.reapply_clicked)
        self.btn['reapply'] = reapplybtn

        pnewbtn = tbar.append_button(gtk.STOCK_NEW,
                                       _('Start a new patch branch'))
        pnewbtn.connect('clicked', self.pnew_clicked)
        self.btn['pnew'] = pnewbtn

        pgraphbtn = tbar.append_button(gtk.STOCK_EDIT,
                                       _('Edit patch dependency graph'))
        pgraphbtn.connect('clicked', self.edit_pgraph_clicked)
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
                str, # patch name
                str, # patch status
                str, # patch title
                str, # patch message
                str) # patch message escaped
        #### patch list view
        self.list = gtk.TreeView(self.model)
        # To support old PyGTK (<2.12)
        if hasattr(self.list, 'set_tooltip_column'):
            self.list.set_tooltip_column(M_MSGESC)
        self.list.connect('cursor-changed', self.list_sel_changed)
        self.list.connect('button-press-event', self.list_pressed)
        self.list.connect('row-activated', self.list_row_activated)
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
            patchname = row[M_NAME]
            if newname != patchname:
                self.qrename(newname, patch=patchname)

        #### patch list columns and cell renderers

        addcol(_('Graph'), C_GRAPH, resizable=True, 
            cell_renderer=graphcell.CellRendererGraph(),
            properties=[("node", M_NODE), 
                        ("in-lines",M_IN_LINES), 
                        ("out-lines", M_OUT_LINES)]
            )
        addcol(_('St'), C_STATUS, M_STATUS)
        addcol(_('Name'), C_NAME, M_NAME, editfunc=cell_edited)
        addcol(_('Title'), C_TITLE, M_TITLE)
        addcol(_('Message'), C_MSG, M_MSG)

        pane.add(self.list)

        ## command widget
        self.cmd = hgcmd.CmdWidget(style=hgcmd.STYLE_COMPACT,
                                   tooltips=tooltips)
        mainbox.pack_start(self.cmd, False, False)

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
            selname = model[paths[0]][M_NAME]

        # compute model data
        self.model.clear()
        opts = {'tips': True}
        mgr = self.pbranch.patchmanager(self.repo.ui, self.repo, opts)
        graph = mgr.graphforopts(opts)
        if not self.get_property('show-internal-branches'):
            graph = mgr.patchonlygraph(graph)
        names = None
        patch_list = graph.topolist(names)
        in_lines = []
        if patch_list:
            dep_list = [patch_list[0]]
        cur_branch = self.repo['.'].branch()
        patch_status = {}
        for name in patch_list:
            patch_status[name] = self.pstatus(name)
        for name in patch_list:
            parents = graph.deps(name)

            # Node properties
            if name in dep_list: 
                node_column = dep_list.index(name)
            else:
                node_column = len(dep_list)
            node_colour = patch_status[name] and '#ff0000' or 0
            node_status = (name == cur_branch) and 4 or 0
            node = (node_column, node_colour, node_status)
            
            # Find next dependency list
            my_deps = []
            for p in parents:
                if p not in dep_list:
                    my_deps.append(p)
            next_dep_list = dep_list[:]
            next_dep_list[node_column:node_column+1] = my_deps
            
            # Dependency lines
            shift = len(parents) - 1
            out_lines = []
            for p in parents:
                dep_column = next_dep_list.index(p)
                colour = 0 # black
                if patch_status[p]:
                    colour = '#ff0000' # red
                style = 0 # solid lines
                out_lines.append((node_column, dep_column, colour, style))
            for lines in in_lines:
                (start_column, end_column, colour, style) = lines
                if end_column == node_column:
                    # Deps to current patch end here
                    pass
                else:
                    # Find line continuations
                    dep = dep_list[end_column]
                    dep_column = next_dep_list.index(dep)
                    out_lines.append((end_column, dep_column, colour, style))
                    
            stat = patch_status[name] and 'M' or 'C' # patch status
            patchname = name
            msg = self.pmessage(name) # summary
            if msg:
                msg_esc = gtklib.markup_escape_text(msg) # escaped summary (utf-8)
                title = msg.split('\n')[0]
            else:
                msg_esc = None
                title = None
            self.model.append((node, in_lines, out_lines, patchname, stat,
                               title, msg, msg_esc))
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
        self.statusbar.set_text(status_text, 'pbranch')
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

    def pmessage(self, patch_name):
        """
        Get patch message

        :param patch_name: Name of patch-branch
        :retv: Full patch message. If you extract the first line
        you will get the patch title. If the repo does not contain
        message or patch, the function returns None
        """
        opts = {}
        mgr = self.pbranch.patchmanager(self.repo.ui, self.repo, opts)
        try:
            return mgr.patchdesc(patch_name)
        except:
            return None

    def peditmessage(self, patch_name):
        """
        Edit patch message

        :param patch_name: Name of patch-branch
        """
        if not patch_name in self.patch_list():
            return
        cmdline = ['hg', 'peditmessage', patch_name]
        self.cmd.execute(cmdline, self.cmd_done)
        
    def pdiff(self, patch_name):
        """
        [pbranch] Execute 'pdiff --tips' command.
        
        :param patch_name: Name of patch-branch
        :retv: list of lines of generated patch
        """
        opts = {}
        mgr = self.pbranch.patchmanager(self.repo.ui, self.repo, opts)
        graph = mgr.graphattips()
        return graph.diff(patch_name, None, opts)

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
        
    def pmerge(self, patch_name=None):
        """
        [pbranch] Execute 'pmerge' command.

        :param patch_name: Merge to this patch-branch
        """
        if not self.has_patch():
            return
        cmdline = ['hg', 'pmerge']
        if patch_name:
            cmdline += [patch_name]
        else:
            cmdline += ['--all']
        self.cmd.execute(cmdline, self.cmd_done)
        
    def pbackout(self):
        """
        [pbranch] Execute 'pbackout' command.
        """
        assert False

    def pfinish(self, patch_name):
        """
        [pbranch] Execute 'pfinish' command.
        
        The workdir must be clean.
        The patch branch dependencies must be merged.
        
        :param patch_name: A patch branch (not an internal branch)
        """
        # Check preconditions for pfinish

        assert self.is_patch(patch_name)

        pmerge_status = self.pstatus(patch_name)
        if pmerge_status != []:
            dialog.error_dialog(self.parent_window,
            _('Pending Pmerge'),
            _('You cannot finish this patch branch unless you pmerge it first.\n'
              'pmerge will solve the following issues with %(patch)s:\n'
              '* %(issuelist)s') %
            {'patch': patch_name,
             'issuelist': '* '.join(pmerge_status)}
            )
            return

        if not self.workdir_is_clean():
            dialog.error_dialog(self.parent_window,
            _('Uncommitted Local Changes'),
            _('pfinish uses your working directory for temporary work.\n'
              'Please commit your local changes before issuing pfinish.')
            )
            return

        if hasattr(self.repo, 'mq') and len(self.repo.mq.applied) > 0:
            dialog.error_dialog(self.parent_window,
            _('Applied MQ patch'),
            _('pfinish must be able to commit, but this is not allowed\n'
              'as long as you have MQ patches applied.')
            )
            return

        # Set up environment for mercurial commands
        class CmdWidgetUi(mercurial.ui.ui):
            def __init__(self, cmdLogWidget):
                src = None
                super(CmdWidgetUi, self).__init__(src)
                self.cmdLogWidget = cmdLogWidget
            def write(self, *args):
                for a in args:
                    self.cmdLogWidget.append(str(a))
            def write_err(self, *args):
                for a in args:
                    self.cmdLogWidget.append(str(a), error=True)
            def flush(self):
                pass
            def prompt(self, msg, choices=None, default="y"):
                raise util.Abort("Internal Error: prompt not available")
            def promptchoice(self, msg, choices, default=0):
                raise util.Abort("Internal Error: promptchoice not available")
            def getpass(self, prompt=None, default=None):
                raise util.Abort("Internal Error: getpass not available")
        repo = self.repo
        ui = CmdWidgetUi(self.cmd.log)
        old_ui = repo.ui
        repo.ui = ui

        # Commit patch to dependency
        fd, patch_file_name = tempfile.mkstemp(prefix='thg-patch-')
        patch_file = os.fdopen(fd, 'w')
        patch_file.writelines(self.pdiff(patch_name))
        patch_file.close()    
        upstream_branch = self.pgraph().deps(patch_name)[0]
        hg.update(ui, repo, rev=upstream_branch)
        hg.import_(ui, repo, patch_file_name, base='', strip=1)
        os.unlink(patch_file_name)
        
        # Close patch branch
        hg.update(ui, repo, rev=patch_name)
        hg.merge(ui, repo, upstream_branch)
        msg = _('Patch branch finished')
        hg.commit(ui, repo, close_branch=True, message=msg)
        
        # Update GUI
        repo.ui = old_ui
        self.emit('repo-invalidated')

    def has_pbranch(self):
        """ return True if pbranch extension can be used """
        return self.pbranch is not None

    def has_patch(self):
        """ return True if pbranch extension is in use on repo """
        return self.has_pbranch() and self.pgraph() != []

    def is_patch(self, branch_name):
        """ return True if branch is a patch. This excludes root branches
        and internal diff base branches (for patches with multiple 
        dependencies. """
        return self.has_pbranch() and self.pgraph().ispatch(branch_name)

    def cur_branch(self):
        """ Return branch that workdir belongs to. """
        return self.repo.dirstate.branch()

    def workdir_is_clean(self):
        """ return True if the working directory is clean """
        c = self.repo[None]
        return not (c.modified() or c.added() or c.removed())

    ### internal functions ###

    def get_iter_by_patchname(self, name):
        """ return iter has specified patch name """
        if name:
            for row in self.model:
                if row[M_NAME] == name:
                    return row.iter
        return None

    def get_path_by_patchname(self, name):
        """ return path has specified patch name """
        iter = self.get_iter_by_patchname(name)
        if iter:
            return self.model.get_path(iter)
        return None

    def update_sensitives(self):
        """ Update the sensitives of entire UI """
        def disable_pbranchcmd():
            for name in ('pbackout', 'pmerge', 'pnew', 'reapply'):
                self.btn[name].set_sensitive(False)
        if self.pbranch:
            self.list.set_sensitive(True)
            self.btn['menu'].set_sensitive(True)
            in_pbranch = True #TODO
            is_merge = len(self.repo.parents()) > 1
            self.btn['pmerge'].set_sensitive(in_pbranch)
            self.btn['pbackout'].set_sensitive(in_pbranch)
            self.btn['pnew'].set_sensitive(not is_merge)
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
        curpatch = self.cur_branch()
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

        has_pbranch = self.has_pbranch()
        is_current = self.has_patch() and self.cur_branch() == row[M_NAME]
        is_patch = self.is_patch(row[M_NAME])
        is_internal = self.pbranch.isinternal(row[M_NAME])
        is_merge = len(self.repo.branchheads(row[M_NAME])) > 1

        if has_pbranch and not is_merge and not is_internal:
            append(_('_new'), self.pnew_activated)
        if not is_current:
            append(_('_goto (update workdir)'), self.goto_activated)
        if is_patch:
            append(_('_edit message'), self.edit_message_activated)
            append(_('_rename'), self.rename_activated)
            append(_('_delete'), self.delete_activated)
            append(_('_finish'), self.finish_activated)

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

        colappend(_('Show graph'), C_GRAPH)
        colappend(_('Show status'), C_STATUS, active=False)
        colappend(_('Show name'), C_NAME)
        colappend(_('Show title'), C_TITLE, active=False)
        colappend(_('Show message'), C_MSG, active=False)

        append(sep=True)

        def enable_editable(item):
            self.cells[C_NAME].set_property('editable', item.get_active())
        item = append(_('Enable editable cells'), enable_editable,
                check=True, active=False)
        self.vmenu['editable-cell'] = item
        item = append(_("Show internal branches"), lambda item: self.refresh(),
                check=True, active=False)
        self.vmenu['show-internal-branches'] = item

        menu.show_all()
        return menu

    def show_dialog(self, dlg):
        """Show modal dialog and block application
        See also show_dialog in history.py
        """
        dlg.set_transient_for(self.parent_window)
        dlg.show_all()
        dlg.run()
        if gtk.pygtk_version < (2, 12, 0):
            # Workaround for old PyGTK (< 2.12.0) issue.
            # See background of this: f668034aeda3
            dlg.set_transient_for(None)
        

    def update_by_row(self, row):
        branch = row[M_NAME]
        rev = cmdutil.revrange(self.repo, [branch])
        parents = [x.node() for x in self.repo.parents()]
        dialog = update.UpdateDialog(rev[0])
        self.show_dialog(dialog)
        self.update_completed(parents)

    def update_completed(self, oldparents):
        self.repo.invalidate()
        self.repo.dirstate.invalidate()
        newparents = [x.node() for x in self.repo.parents()]
        if not oldparents == newparents:
            self.emit('repo-invalidated')

    def cmd_done(self, returncode, useraborted, noemit=False):
        if returncode == 0:
            if self.cmd.get_pbar():
                self.cmd.set_result(_('Succeed'), style='ok')
        elif useraborted:
            self.cmd.set_result(_('Canceled'), style='error')
        else:
            self.cmd.set_result(_('Failed'), style='error')
        self.refresh()
        if not noemit:
            self.emit('repo-invalidated')

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
        if col_idx == C_GRAPH:
            return 'graph-column-visible'
        if col_idx == C_STATUS:
            return 'status-column-visible'
        if col_idx == C_NAME:
            return 'name-column-visible'
        if col_idx == C_TITLE:
            return 'title-column-visible'
        if col_idx == C_MSG:
            return 'message-column-visible'
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
        patchname = row[M_NAME]
        try:
            ctx = self.repo[patchname]
            revid = ctx.rev()
        except hglib.RepoError:
            revid = -1
        self.emit('patch-selected', revid, patchname)

    def list_row_activated(self, list, path, column):
        self.update_by_row(self.model[path])

    def list_size_allocated(self, list, req):
        if self.has_patch():
            self.scroll_to_current()

    def pbackout_clicked(self, toolbutton):
        pass

    def pmerge_clicked(self, toolbutton):
        self.pmerge()

    def pnew_clicked(self, toolbutton):
        self.pnew_ui()

    def reapply_clicked(self, toolbutton):
        pass

    def edit_pgraph_clicked(self, toolbutton):
        opts = {} # TODO: How to find user ID
        mgr = self.pbranch.patchmanager(self.repo.ui, self.repo, opts)
        oldtext = mgr.graphdesc()
        # run editor in the repository root
        olddir = os.getcwd()
        os.chdir(self.repo.root)
        newtext = self.repo.ui.edit(oldtext, opts.get('user'))
        os.chdir(olddir)
        mgr.updategraphdesc(newtext)

    ### context menu signal handlers ###

    def pnew_activated(self, menuitem, row):
        """Insert new patch after this row"""
        if self.cur_branch() == row[M_NAME]:
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

    def edit_message_activated(self, menuitem, row):
        self.peditmessage(row[M_NAME])

    def goto_activated(self, menuitem, row):
        self.update_by_row(row)

    def delete_activated(self, menuitem, row):
        assert False

    def rename_activated(self, menuitem, row):
        assert False

    def finish_activated(self, menuitem, row):
        self.pfinish(row[M_NAME])

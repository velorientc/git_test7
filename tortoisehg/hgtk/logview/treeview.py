# treeview.py - changelog viewer implementation
#
# Copyright 2008 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

''' Mercurial revision DAG visualization library

  Implements a gtk.TreeModel which visualizes a Mercurial repository
  revision history.

Portions of this code stolen mercilessly from bzr-gtk visualization
dialog.  Other portions stolen from graphlog extension.
'''

import gtk
import gobject
import pango
import os
import time

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib

from tortoisehg.hgtk.logview import treemodel
from tortoisehg.hgtk.logview.graphcell import CellRendererGraph
from tortoisehg.hgtk.logview.revgraph import *

COLS = 'graph rev id revhex branch changes msg user date utc age tag'

class TreeView(gtk.ScrolledWindow):

    __gproperties__ = {
        'repo': (gobject.TYPE_PYOBJECT,
                   'Repository',
                   'The Mercurial repository being visualized',
                   gobject.PARAM_CONSTRUCT_ONLY | gobject.PARAM_WRITABLE),

        'limit': (gobject.TYPE_PYOBJECT,
                   'Revision Display Limit',
                   'The maximum number of revisions to display',
                   gobject.PARAM_READWRITE),

        'original-tip-revision': (gobject.TYPE_PYOBJECT,
                   'Tip revision when application opened',
                   'Revisions above this number will be drawn green',
                   gobject.PARAM_READWRITE),

        'msg-column-visible': (gobject.TYPE_BOOLEAN,
                                 'Summary',
                                 'Show summary column',
                                 True,
                                 gobject.PARAM_READWRITE),
        'user-column-visible': (gobject.TYPE_BOOLEAN,
                                 'User',
                                 'Show user column',
                                 True,
                                 gobject.PARAM_READWRITE),
        'date-column-visible': (gobject.TYPE_BOOLEAN,
                                 'Date',
                                 'Show date column',
                                 False,
                                 gobject.PARAM_READWRITE),
        'utc-column-visible': (gobject.TYPE_BOOLEAN,
                                 'UTC',
                                 'Show UTC/GMT date column',
                                 False,
                                 gobject.PARAM_READWRITE),
        'age-column-visible': (gobject.TYPE_BOOLEAN,
                                 'Age',
                                 'Show age column',
                                 False,
                                 gobject.PARAM_READWRITE),
        'rev-column-visible': (gobject.TYPE_BOOLEAN,
                                 'Rev',
                                 'Show revision number column',
                                 False,
                                 gobject.PARAM_READWRITE),
        'id-column-visible': (gobject.TYPE_BOOLEAN,
                                 'ID',
                                 'Show revision ID column',
                                 False,
                                 gobject.PARAM_READWRITE),
        'revhex-column-visible': (gobject.TYPE_BOOLEAN,
                                 'Rev/ID',
                                 'Show revision number/ID column',
                                 False,
                                 gobject.PARAM_READWRITE),
        'branch-column-visible': (gobject.TYPE_BOOLEAN,
                                 'Branch',
                                 'Show branch',
                                 False,
                                 gobject.PARAM_READWRITE),
        'changes-column-visible': (gobject.TYPE_BOOLEAN,
                                 'Changes',
                                 'Show changes column',
                                 False,
                                 gobject.PARAM_READWRITE),
        'tag-column-visible': (gobject.TYPE_BOOLEAN,
                                 'Tags',
                                 'Show tag column',
                                 False,
                                 gobject.PARAM_READWRITE),
        'branch-color': (gobject.TYPE_BOOLEAN,
                                 'Branch color',
                                 'Color by branch',
                                 False,
                                 gobject.PARAM_READWRITE)
    }

    __gsignals__ = {
        'revisions-loaded': (gobject.SIGNAL_RUN_FIRST, 
                             gobject.TYPE_NONE,
                             ()),
        'batch-loaded': (gobject.SIGNAL_RUN_FIRST, 
                         gobject.TYPE_NONE,
                         ()),
        'revision-selected': (gobject.SIGNAL_RUN_FIRST,
                              gobject.TYPE_NONE,
                              ())
    }

    def __init__(self, repo, limit=500, stbar=None):
        """Create a new TreeView.

        :param repo:  Repository object to show
        """
        gtk.ScrolledWindow.__init__(self)

        self.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.set_shadow_type(gtk.SHADOW_IN)

        self.batchsize = limit
        self.repo = repo
        self.currevid = None
        self.stbar = stbar
        self.grapher = None
        self.graphdata = []
        self.index = {}
        self.opts = { 'outgoing':[], 'orig-tip':None, 'npreviews':0,
                      'branch-color':False, 'show-graph':True }
        self.construct_treeview()

    def set_repo(self, repo, stbar=None):
        self.repo = repo
        self.stbar = stbar

    def search_in_tree(self, model, column, key, iter, data):
        """Searches all fields shown in the tree when the user hits crtr+f,
        not just the ones that are set via tree.set_search_column.
        Case insensitive
        """
        key = key.lower()
        row = model[iter]
        if row[treemodel.HEXID].startswith(key):
            return False
        for col in (treemodel.REVID, treemodel.COMMITER, treemodel.MESSAGE):
            if key in str(row[col]).lower():
                return False
        return True

    def create_log_generator(self, graphcol, pats, opts):
        if self.repo is None:
            self.grapher = None
            return
            
        only_branch = opts.get('branch', None)

        if opts.get('filehist') is not None:
            self.grapher = filelog_grapher(self.repo, opts['filehist'])
        elif graphcol:
            end = 0
            if only_branch is not None:
                b = self.repo.branchtags()
                if only_branch in b:
                    node = b[only_branch]
                    start = self.repo.changelog.rev(node)
                else:
                    start = len(self.repo.changelog) - 1
            elif opts.get('revrange'):
                if len(opts['revrange']) >= 2:
                    start, end = opts['revrange']
                else:
                    start = opts['revrange'][0]
                    end = start
            else:
                start = len(self.repo.changelog) - 1
            noheads = opts.get('noheads', False)
            if opts.get('branch-view', False):
                self.grapher = branch_grapher(self.repo, start, end, 
                    only_branch, self.opts.get('branch-color'))
            else:
                self.grapher = revision_grapher(self.repo, start, end,
                        only_branch, noheads, self.opts.get('branch-color'))
        elif opts.get('revlist', None):
            self.grapher = dumb_log_generator(self.repo, opts['revlist'])
        else:
            self.grapher = filtered_log_generator(self.repo, pats, opts)
        self.opts['show-graph'] = graphcol
        self.graphdata = []
        self.index = {}
        self.max_cols = 1
        self.model = None
        self.limit = self.batchsize

    def populate(self, revid=None):
        'Fill the treeview with contents'
        stopped = False
        if self.repo is None:
            stopped = True
            return False

        if os.name == "nt":
            timer = time.clock
        else:
            timer = time.time
        startsec = timer()
        try:
            while (not self.limit) or len(self.graphdata) < self.limit:
                (rev, node, lines, wfile) = self.grapher.next()
                self.max_cols = max(self.max_cols, len(lines))
                self.index[rev] = len(self.graphdata)
                self.graphdata.append( (rev, node, lines, wfile) )
                if self.model:
                    rowref = self.model.get_iter(len(self.graphdata)-1)
                    path = self.model.get_path(rowref) 
                    self.model.row_inserted(path, rowref) 
                cursec = timer()
                if cursec < startsec or cursec > startsec + 0.1:
                    break
        except StopIteration:
            stopped = True

        if stopped:
            pass
        elif self.limit is None:
            return True
        elif len(self.graphdata) < self.limit:
            return True

        if not len(self.graphdata):
            self.treeview.set_model(None)
            if self.stbar is not None:
                self.stbar.end()
            self.emit('revisions-loaded')
            return False

        self.graph_cell.columns_len = self.max_cols
        width = self.graph_cell.get_size(self.treeview)[2]
        if width > 500:
            width = 500
        gcol = self.tvcolumns['graph']
        gcol.set_fixed_width(width)
        gcol.set_visible(self.opts.get('show-graph'))

        if not self.model:
            model = treemodel.TreeModel(self.repo, self.graphdata, self.opts)
            self.treeview.set_model(model)
            self.model = model

        self.emit('batch-loaded')
        if stopped:
            self.emit('revisions-loaded')
        if revid is not None:
            self.set_revision_id(revid)
        if self.stbar is not None:
            self.stbar.end()
            revision_text = _('%(count)d of %(total)d Revisions') % {
                    'count': len(self.model),
                    'total': len(self.repo) }
            self.stbar.set_text(revision_text, name='rev')
        return False

    def do_get_property(self, property):
        pn = property.name
        cv = '-column-visible'
        if pn.endswith(cv):
            colname = pn[:-len(cv)]
            return self.tvcolumns[colname].get_visible()
        elif pn == 'branch-color':
            return self.opts.get('branch-color')
        elif pn == 'repo':
            return self.repo
        elif pn == 'limit':
            return self.limit
        else:
            raise AttributeError, 'unknown property %s' % pn

    def do_set_property(self, property, value):
        pn = property.name
        cv = '-column-visible'
        if pn.endswith(cv):
            colname = pn[:-len(cv)]
            self.tvcolumns[colname].set_visible(value)
        elif pn == 'branch-color':
            self.opts['branch-color'] = value
        elif pn == 'repo':
            self.repo = value
        elif pn == 'limit':
            self.batchsize = value
        else:
            raise AttributeError, 'unknown property %s' % pn

    def get_revid_at_path(self, path):
        return self.model[path][treemodel.REVID]

    def get_path_at_revid(self, revid):
        if revid in self.index:
            row_index = self.index[revid]
            iter = self.model.get_iter(row_index)
            path = self.model.get_path(iter)
            return path
        else:
            return None

    def get_wfile_at_path(self, path):
        if self.model:
            return self.model[path][treemodel.WFILE]
        else:
            return None

    def next_revision_batch(self, size):
        if not self.grapher:
            self.emit('revisions-loaded')
            return
        self.batchsize = size
        self.limit += self.batchsize
        if self.stbar is not None:
            self.stbar.begin()
        gobject.idle_add(self.populate)

    def load_all_revisions(self):
        if not self.grapher:
            self.emit('revisions-loaded')
            return
        self.limit = None
        if self.stbar is not None:
            self.stbar.begin()
        gobject.idle_add(self.populate)

    def scroll_to_revision(self, revid):
        if revid in self.index:
            row = self.index[revid]
            self.treeview.scroll_to_cell(row, use_align=True, row_align=0.5)

    def set_revision_id(self, revid, load=False):
        """Change the currently selected revision.

        :param revid: Revision id of revision to display.
        """
        if revid in self.index:
            row = self.index[revid]
            self.treeview.set_cursor(row)
            self.treeview.grab_focus()
        elif load:
            handler = None

            def loaded(dummy):
                if revid in self.index:
                    if handler is not None:
                        self.disconnect(handler)
                    self.set_revision_id(revid)
                    self.scroll_to_revision(revid)
                else:
                    self.next_revision_batch(self.batchsize)

            handler = self.connect('batch-loaded', loaded)
            self.next_revision_batch(self.batchsize)

    def refresh(self, graphcol, pats, opts):
        self.opts.update(opts)
        if self.repo is not None:
            hglib.invalidaterepo(self.repo)
            if len(self.repo) > 0:
                self.create_log_generator(graphcol, pats, opts)
                if self.stbar is not None:
                    self.stbar.begin()
                gobject.idle_add(self.populate, self.currevid)
            else:
                self.treeview.set_model(None)
                self.stbar.set_text(_('Repository is empty'))

    def construct_treeview(self):
        self.treeview = gtk.TreeView()
        self.treeview.set_rules_hint(True)
        self.treeview.set_reorderable(False)
        self.treeview.set_enable_search(True)
        self.treeview.set_search_equal_func(self.search_in_tree, None)

        self.treeview.get_selection().set_mode(gtk.SELECTION_SINGLE)
        self.treeview.connect("cursor-changed", self._on_selection_changed)
        self.treeview.set_property('fixed-height-mode', True)
        self.treeview.show()
        self.add(self.treeview)

        self.tvcolumns = {}

        self.graph_cell = CellRendererGraph()
        col = self.tvcolumns['graph'] = gtk.TreeViewColumn(_('Graph'))
        col.set_resizable(True)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        col.pack_start(self.graph_cell, expand=False)
        col.add_attribute(self.graph_cell,
                "node", treemodel.GRAPHNODE)
        col.add_attribute(self.graph_cell,
                "in-lines", treemodel.LAST_LINES)
        col.add_attribute(self.graph_cell,
                "out-lines", treemodel.LINES)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 8)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        cell.set_property("xalign", 1.0)
        col = self.tvcolumns['rev'] = gtk.TreeViewColumn(_('Rev'))
        col.set_visible(False)
        col.set_resizable(True)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        col.set_fixed_width(cell.get_size(self.treeview)[2])
        col.pack_start(cell, expand=True)
        col.add_attribute(cell, "text", treemodel.REVID)
        col.add_attribute(cell, "foreground", treemodel.FGCOLOR)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 15)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        cell.set_property("family", "Monospace")
        col = self.tvcolumns['id'] = gtk.TreeViewColumn(_('ID'))
        col.set_visible(False)
        col.set_resizable(True)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        col.set_fixed_width(cell.get_size(self.treeview)[2])
        col.pack_start(cell, expand=True)
        col.add_attribute(cell, "text", treemodel.HEXID)
        col.add_attribute(cell, "foreground", treemodel.FGCOLOR)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 22)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        col = self.tvcolumns['revhex'] = gtk.TreeViewColumn(_('Rev/ID'))
        col.set_visible(False)
        col.set_resizable(True)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        col.set_fixed_width(cell.get_size(self.treeview)[2])
        col.pack_start(cell, expand=True)
        col.add_attribute(cell, "foreground", treemodel.FGCOLOR)
        col.add_attribute(cell, "markup", treemodel.REVHEX)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 15)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        col = self.tvcolumns['branch'] = gtk.TreeViewColumn(_('Branch'))
        col.set_visible(False)
        col.set_resizable(True)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        col.set_fixed_width(cell.get_size(self.treeview)[2])
        col.pack_start(cell, expand=True)
        col.add_attribute(cell, "text", treemodel.BRANCH)
        col.add_attribute(cell, "foreground", treemodel.FGCOLOR)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 10)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        col = self.tvcolumns['changes'] = gtk.TreeViewColumn(_('Changes'))
        col.set_visible(False)
        col.set_resizable(True)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        col.set_fixed_width(cell.get_size(self.treeview)[2])
        col.pack_start(cell, expand=True)
        col.add_attribute(cell, "markup", treemodel.CHANGES)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 80)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        col = self.tvcolumns['msg'] = gtk.TreeViewColumn(_('Summary'))
        col.set_resizable(True)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        col.set_fixed_width(cell.get_size(self.treeview)[2])
        col.pack_end(cell, expand=True)
        col.add_attribute(cell, "foreground", treemodel.FGCOLOR)
        col.add_attribute(cell, "markup", treemodel.MESSAGE)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 20)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        col = self.tvcolumns['user'] = gtk.TreeViewColumn(_('User'))
        col.set_resizable(True)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        col.set_fixed_width(cell.get_size(self.treeview)[2])
        col.pack_start(cell, expand=True)
        col.add_attribute(cell, "text", treemodel.COMMITER)
        col.add_attribute(cell, "foreground", treemodel.FGCOLOR)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 20)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        col = self.tvcolumns['date'] = gtk.TreeViewColumn(_('Local Date'))
        col.set_visible(False)
        col.set_resizable(True)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        col.set_fixed_width(cell.get_size(self.treeview)[2])
        col.pack_start(cell, expand=True)
        col.add_attribute(cell, "text", treemodel.LOCALTIME)
        col.add_attribute(cell, "foreground", treemodel.FGCOLOR)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 20)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        col = self.tvcolumns['utc'] = gtk.TreeViewColumn(_('Universal Date'))
        col.set_visible(False)
        col.set_resizable(True)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        col.set_fixed_width(cell.get_size(self.treeview)[2])
        col.pack_start(cell, expand=True)
        col.add_attribute(cell, "text", treemodel.UTC)
        col.add_attribute(cell, "foreground", treemodel.FGCOLOR)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 16)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        col = self.tvcolumns['age'] = gtk.TreeViewColumn(_('Age'))
        col.set_visible(True)
        col.set_resizable(True)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        col.set_fixed_width(cell.get_size(self.treeview)[2])
        col.pack_start(cell, expand=True)
        col.add_attribute(cell, "text", treemodel.AGE)
        col.add_attribute(cell, "foreground", treemodel.FGCOLOR)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 10)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        col = self.tvcolumns['tag']  = gtk.TreeViewColumn(_('Tags'))
        col.set_visible(False)
        col.set_resizable(True)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        col.set_fixed_width(cell.get_size(self.treeview)[2])
        col.pack_start(cell, expand=True)
        col.add_attribute(cell, "text", treemodel.TAGS)
        col.add_attribute(cell, "foreground", treemodel.FGCOLOR)

        self.columns = COLS.split()

    def set_columns(self, columns):
        if ' '.join(columns) != ' '.join(self.columns):
            cols = self.treeview.get_columns()
            for cn in self.columns:
                c = self.tvcolumns[cn]
                if c in cols:
                    self.treeview.remove_column(c)
            for cn in columns:
                try:
                    c = self.tvcolumns[cn]
                    self.treeview.append_column(c)
                except KeyError:
                    continue
            self.columns = columns

    def get_columns(self):
        return self.columns

    def _on_selection_changed(self, treeview):
        """callback for when the treeview changes."""
        (path, focus) = treeview.get_cursor()
        if path and self.model:
            self.currevid = self.model[path][treemodel.REVID]
            self.emit('revision-selected')


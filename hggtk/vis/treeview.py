''' Mercurial revision DAG visualization library

  Implements a gtk.TreeModel which visualizes a Mercurial repository
  revision history.

Portions of this code stolen mercilessly from bzr-gtk visualization
dialog.  Other portions stolen from graphlog extension.
'''

import gtk
import gobject
import pango
import treemodel
from graphcell import CellRendererGraph
from revgraph import revision_grapher, filtered_log_generator

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

        'revision': (gobject.TYPE_PYOBJECT,
                     'Revision',
                     'The currently selected revision',
                     gobject.PARAM_READWRITE),

        'revision-number': (gobject.TYPE_STRING,
                            'Revision number',
                            'The number of the selected revision',
                            '',
                            gobject.PARAM_READABLE),

        'date-column-visible': (gobject.TYPE_BOOLEAN,
                                 'Date',
                                 'Show date column',
                                 False,
                                 gobject.PARAM_READWRITE),
    }

    __gsignals__ = {
        'revisions-loaded': (gobject.SIGNAL_RUN_FIRST, 
                             gobject.TYPE_NONE,
                             ()),
        'revision-selected': (gobject.SIGNAL_RUN_FIRST,
                              gobject.TYPE_NONE,
                              ())
    }

    def __init__(self, repo, limit = None):
        """Create a new TreeView.

        :param repo:  Repository object to show
        """
        gtk.ScrolledWindow.__init__(self)

        self.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        self.set_shadow_type(gtk.SHADOW_IN)

        self.batchsize = limit
        self.repo = repo
        self.currev = None
        self.construct_treeview()

    def search_in_tree(self, model, column, key, iter, data):
        """Searches all fields shown in the tree when the user hits crtr+f,
        not just the ones that are set via tree.set_search_column.
        Case insensitive
        """
        key = key.lower()
        for col in (treemodel.REVID, treemodel.TAGS, treemodel.COMMITER,
                treemodel.MESSAGE):
            if key in model.get_value(iter, col).lower():
                return False
        return True

    def create_log_generator(self, revs, pats, opts):
        if revs is None:
            if pats is not None:  # branch name
                b = self.repo.branchtags()
                if b.has_key(pats):
                    node = b[pats]
                    start = self.repo.changelog.rev(node)
                    print 'branch', pats, 'starts at rev', start
                else:
                    start = self.repo.changelog.count() - 1
            else:
                start = self.repo.changelog.count() - 1
            self.grapher = revision_grapher(self.repo, start, 0, pats)
            self.show_graph = True
        else:
            self.grapher = filtered_log_generator(self.repo, revs, pats, opts)
            self.show_graph = False
        self.graphdata = []
        self.index = {}
        self.max_cols = 1
        self.model = None
        self.limit = self.batchsize

    def populate(self, revision=None):
        """Fill the treeview with contents.
        """
        try:
            (rev, node, lines, parents) = self.grapher.next()
            self.max_cols = max(self.max_cols, len(lines))
            self.index[rev] = len(self.graphdata)
            self.graphdata.append( (rev, node, lines, parents) )
            if self.model:
                rowref = self.model.get_iter(len(self.graphdata)-1)
                path = self.model.get_path(rowref) 
                self.model.row_inserted(path, rowref) 
        except StopIteration:
            self.emit('revisions-loaded')
            self.limit = len(self.graphdata)

        if not self.limit or len(self.graphdata) < self.limit:
            return True

        if not self.model:
            self.model = treemodel.TreeModel(self.repo, self.graphdata)
            self.treeview.set_model(self.model)

        self.graph_cell.columns_len = self.max_cols
        width = self.graph_cell.get_size(self.treeview)[2]
        if width > 500:
            width = 500
        self.graph_column.set_fixed_width(width)
        self.graph_column.set_max_width(width)
        self.graph_column.set_visible(self.show_graph)

        if revision is None:
            self.treeview.set_cursor(0)
        else:
            self.set_revision_id(revision[treemodel.REVID])
        return False

    def do_get_property(self, property):
        if property.name == 'date-column-visible':
            return self.date_column.get_visible()
        elif property.name == 'repo':
            return self.repo
        elif property.name == 'limit':
            return self.limit
        elif property.name == 'revision':
            return self.currev
        else:
            raise AttributeError, 'unknown property %s' % property.name

    def do_set_property(self, property, value):
        if property.name == 'date-column-visible':
            self.date_column.set_visible(value)
        elif property.name == 'repo':
            self.repo = value
        elif property.name == 'limit':
            self.limit = value
            gobject.idle_add(self.populate, self.get_revision())
        elif property.name == 'revision':
            self.set_revision_id(value)
        else:
            raise AttributeError, 'unknown property %s' % property.name

    def next_revision_batch(self):
        self.limit += self.batchsize
        gobject.idle_add(self.populate, self.get_revision())

    def load_all_revisions(self):
        self.limit = None
        gobject.idle_add(self.populate, self.get_revision())

    def get_revision(self):
        """Return revision id of currently selected revision, or None."""
        return self.get_property('revision')

    def scroll_to_revision(self, revid):
        if self.index.has_key(revid):
            row = self.index[revid]
            self.treeview.scroll_to_cell(row, use_align=True, row_align=0.5)

    def set_revision_id(self, revid):
        """Change the currently selected revision.

        :param revid: Revision id of revision to display.
        """
        if self.index.has_key(revid):
            row = self.index[revid]
            self.treeview.set_cursor(row)
            self.treeview.grab_focus()

    def get_parents(self):
        """Return the parents of the currently selected revision.

        :return: list of revision ids.
        """
        return self.get_property('parents')
        
    def refresh(self, revs, pats, opts):
        self.repo.invalidate()
        self.repo.dirstate.invalidate()
        self.create_log_generator(revs, pats, opts)
        gobject.idle_add(self.populate, self.get_revision())

    def construct_treeview(self):
        self.treeview = gtk.TreeView()
        self.treeview.set_rules_hint(True)
        self.treeview.set_reorderable(False)
        self.treeview.set_enable_search(True)
        self.treeview.set_search_equal_func(self.search_in_tree, None)
        
        # Fix old PyGTK bug - by JAM
        set_tooltip = getattr(self.treeview, 'set_tooltip_column', None)
        if set_tooltip is not None:
            set_tooltip(treemodel.MESSAGE)

        self.treeview.get_selection().set_mode(gtk.SELECTION_SINGLE)
        self.treeview.connect("cursor-changed", self._on_selection_changed)
        self.treeview.set_property('fixed-height-mode', True)
        self.treeview.show()
        self.add(self.treeview)

        self.graph_cell = CellRendererGraph()
        self.graph_column = gtk.TreeViewColumn('Graph')
        self.graph_column.set_resizable(True)
        self.graph_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.graph_column.pack_start(self.graph_cell, expand=False)
        self.graph_column.add_attribute(self.graph_cell,
                "node", treemodel.NODE)
        self.graph_column.add_attribute(self.graph_cell,
                "in-lines", treemodel.LAST_LINES)
        self.graph_column.add_attribute(self.graph_cell,
                "out-lines", treemodel.LINES)
        self.treeview.append_column(self.graph_column)

        pcell = gtk.CellRendererPixbuf()
        hcell = gtk.CellRendererPixbuf()
        self.status_column = gtk.TreeViewColumn('Status')
        self.status_column.pack_start(pcell, expand=True)
        self.status_column.pack_start(hcell, expand=True)
        self.status_column.set_resizable(True)
        self.status_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.status_column.set_fixed_width(48)
        self.status_column.set_cell_data_func(pcell, self.make_parent)
        self.status_column.set_cell_data_func(hcell, self.make_head)
        self.treeview.append_column(self.status_column)
        
        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 8)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.rev_column = gtk.TreeViewColumn("Rev")
        self.rev_column.set_resizable(True)
        self.rev_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.rev_column.set_fixed_width(cell.get_size(self.treeview)[2])
        self.rev_column.pack_start(cell, expand=True)
        self.rev_column.add_attribute(cell, "text", treemodel.REVID)
        self.rev_column.set_cell_data_func(cell, self.text_color)
        self.treeview.append_column(self.rev_column)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 10)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.tag_column = gtk.TreeViewColumn("Tag")
        self.tag_column.set_resizable(True)
        self.tag_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.tag_column.set_fixed_width(cell.get_size(self.treeview)[2])
        self.tag_column.pack_start(cell, expand=True)
        self.tag_column.add_attribute(cell, "text", treemodel.TAGS)
        self.tag_column.set_cell_data_func(cell, self.text_color)
        self.treeview.append_column(self.tag_column)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 65)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.msg_column = gtk.TreeViewColumn("Summary")
        self.msg_column.set_resizable(True)
        self.msg_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.msg_column.set_fixed_width(cell.get_size(self.treeview)[2])
        self.msg_column.pack_start(cell, expand=True)
        self.msg_column.add_attribute(cell, "markup", treemodel.MESSAGE)
        self.msg_column.set_cell_data_func(cell, self.text_color)
        self.treeview.append_column(self.msg_column)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 30)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.committer_column = gtk.TreeViewColumn("User")
        self.committer_column.set_resizable(True)
        self.committer_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.committer_column.set_fixed_width(cell.get_size(self.treeview)[2])
        self.committer_column.pack_start(cell, expand=True)
        self.committer_column.add_attribute(cell, "text", treemodel.COMMITER)
        self.committer_column.set_cell_data_func(cell, self.text_color)
        self.treeview.append_column(self.committer_column)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 20)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.date_column = gtk.TreeViewColumn("Date")
        self.date_column.set_visible(False)
        self.date_column.set_resizable(True)
        self.date_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.date_column.set_fixed_width(cell.get_size(self.treeview)[2])
        self.date_column.pack_start(cell, expand=True)
        self.date_column.add_attribute(cell, "text", treemodel.TIMESTAMP)
        self.date_column.set_cell_data_func(cell, self.text_color)
        self.treeview.append_column(self.date_column)

    def make_parent(self, tvcolumn, cell, model, iter):
        stock = model.get_value(iter, treemodel.WCPARENT)
        pb = self.treeview.render_icon(stock, gtk.ICON_SIZE_MENU, None)
        cell.set_property('pixbuf', pb)

    def make_head(self, tvcolumn, cell, model, iter):
        stock = model.get_value(iter, treemodel.HEAD)
        pb = self.treeview.render_icon(stock, gtk.ICON_SIZE_MENU, None)
        cell.set_property('pixbuf', pb)

    def text_color(self, column, text_renderer, list, row_iter):
        parents = list[row_iter][treemodel.PARENTS]
        if len(parents) == 2: # mark merge changesets green
            text_renderer.set_property('foreground', '#006400')
        else:
            text_renderer.set_property('foreground', 'black')

    def _on_selection_changed(self, treeview):
        """callback for when the treeview changes."""
        (path, focus) = treeview.get_cursor()
        if path is not None:
            iter = self.model.get_iter(path)
            self.currev = self.model.get_value(iter, treemodel.REVISION)
            self.emit('revision-selected')


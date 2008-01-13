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
from revgraph import revision_grapher

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
        self.limit = limit
        self.repo = repo
        self.currev = None

        self.construct_treeview()
        self.create_grapher()
        gobject.idle_add(self.populate)

    def create_grapher(self):
        self.grapher = revision_grapher(self.repo,
                self.repo.changelog.count() - 1, 0)
        self.graphdata = []
        self.index = {}
        self.max_cols = 1
        self.model = None
        self.fill_model()
        self.model = treemodel.TreeModel(self.repo, self.graphdata)
        self.treeview.set_model(self.model)

    def fill_model(self):
        savedlen = len(self.graphdata)
        while not self.limit or len(self.graphdata) < self.limit:
            try:
                (rev, node, lines, parents) = self.grapher.next()
            except StopIteration:
                if self.nextbutton:
                    self.nextbutton.destroy()
                    self.nextbutton = None
                break
            self.max_cols = max(self.max_cols, len(lines))
            self.index[rev] = len(self.graphdata)
            self.graphdata.append( (rev, node, lines, parents) )
        if self.model:
            for x in xrange(savedlen, len(self.graphdata)):
                rowref = self.model.get_iter(x)
                path = self.model.get_path(rowref) 
                self.model.row_inserted(path, rowref) 

    def populate(self, revision=None):
        """Fill the treeview with contents.
        """
        self.graph_cell.columns_len = self.max_cols
        width = self.graph_cell.get_size(self.treeview)[2]
        if width > 500:
            width = 500
        self.graph_column.set_fixed_width(width)
        self.graph_column.set_max_width(width)

        if revision is None:
            self.treeview.set_cursor(0)
        else:
            self.set_revision_id(revision[treemodel.REVID])
        self.emit('revisions-loaded')
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
            self.fill_model()
            gobject.idle_add(self.populate, self.get_revision())
        elif property.name == 'revision':
            self.set_revision_id(value)
        else:
            raise AttributeError, 'unknown property %s' % property.name

    def _next_clicked(self, button):
        self.limit += self.batchsize
        self.fill_model()
        gobject.idle_add(self.populate, self.get_revision())

    def get_revision(self):
        """Return revision id of currently selected revision, or None."""
        return self.get_property('revision')

    def set_revision_id(self, revid):
        """Change the currently selected revision.

        :param revid: Revision id of revision to display.
        """
        self.treeview.set_cursor(self.index[revid])
        self.treeview.grab_focus()

    def get_parents(self):
        """Return the parents of the currently selected revision.

        :return: list of revision ids.
        """
        return self.get_property('parents')
        
    def refresh(self):
        self.create_grapher()
        gobject.idle_add(self.populate, self.get_revision())

    def construct_treeview(self):
        self.treeview = gtk.TreeView()

        self.treeview.set_rules_hint(True)
        self.treeview.set_search_column(treemodel.REVID)
        
        # Fix old PyGTK bug - by JAM
        set_tooltip = getattr(self.treeview, 'set_tooltip_column', None)
        if set_tooltip is not None:
            set_tooltip(treemodel.MESSAGE)

        self.treeview.connect("cursor-changed", self._on_selection_changed)
        self.treeview.set_property('fixed-height-mode', True)
        self.treeview.show()

        if self.batchsize:
            vbox = gtk.VBox()
            vbox.pack_start(self.treeview, expand = True)
            self.nextbutton = gtk.Button("next %d revisions" % self.batchsize)
            self.nextbutton.connect('clicked', self._next_clicked)
            hbox = gtk.HBox()
            hbox.pack_start(self.nextbutton, expand = False)
            vbox.pack_start(hbox, expand = False)
            self.add_with_viewport(vbox)
        else:
            self.nextbutton = None
            self.add(self.treeview)

        self.graph_cell = CellRendererGraph()
        self.graph_column = gtk.TreeViewColumn()
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

        cell = gtk.CellRendererPixbuf()
        self.status_column = gtk.TreeViewColumn('status')
        self.status_column.pack_start(cell, expand=True)
        self.status_column.set_resizable(True)
        self.status_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.status_column.set_fixed_width(32)
        self.status_column.set_cell_data_func(cell, self.make_parent)
        self.treeview.append_column(self.status_column)
        
        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 65)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.msg_column = gtk.TreeViewColumn("Message")
        self.msg_column.set_resizable(True)
        self.msg_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.msg_column.set_fixed_width(cell.get_size(self.treeview)[2])
        self.msg_column.pack_start(cell, expand=True)
        self.msg_column.add_attribute(cell, "markup", treemodel.MESSAGE)
        self.treeview.append_column(self.msg_column)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 30)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.committer_column = gtk.TreeViewColumn("Committer")
        self.committer_column.set_resizable(True)
        self.committer_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.committer_column.set_fixed_width(cell.get_size(self.treeview)[2])
        self.committer_column.pack_start(cell, expand=True)
        self.committer_column.add_attribute(cell, "text", treemodel.COMMITER)
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
        self.treeview.append_column(self.date_column)

    def make_parent(self, tvcolumn, cell, model, iter):
        stock = model.get_value(iter, treemodel.WCPARENT)
        pb = self.treeview.render_icon(stock, gtk.ICON_SIZE_MENU, None)
        cell.set_property('pixbuf', pb)

    def _on_selection_changed(self, treeview):
        """callback for when the treeview changes."""
        (path, focus) = treeview.get_cursor()
        if path is not None:
            iter = self.model.get_iter(path)
            self.currev = self.model.get_value(iter, treemodel.REVISION)
            self.emit('revision-selected')


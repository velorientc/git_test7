''' Mercurial revision DAG visualization library

  Implements a gtk.TreeModel which visualizes a Mercurial repository
  revision history.

Portions of this code stolen mercilessly from bzr-gtk visualization
dialog.  Other portions stolen from graphlog extension.
'''

import gtk
import gobject
import pango
import re

from mercurial.node import hex

from thgutil.i18n import _
from thgutil import hglib

from hggtk.logview import treemodel
from hggtk.logview.graphcell import CellRendererGraph
from hggtk.logview.revgraph import *


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
        'utc-column-visible': (gobject.TYPE_BOOLEAN,
                                 'UTC',
                                 'Show UTC/GMT date column',
                                 False,
                                 gobject.PARAM_READWRITE),
        'rev-column-visible': (gobject.TYPE_BOOLEAN,
                                 'Rev',
                                 'Show revision number column',
                                 False,
                                 gobject.PARAM_READWRITE),
        'id-column-visible': (gobject.TYPE_BOOLEAN,
                                 'Tags',
                                 'Show revision ID column',
                                 False,
                                 gobject.PARAM_READWRITE),

        'branch-column-visible': (gobject.TYPE_BOOLEAN,
                                 'Branch',
                                 'Show branch',
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

    def __init__(self, repo, limit=500, pbar=None):
        """Create a new TreeView.

        :param repo:  Repository object to show
        """
        gtk.ScrolledWindow.__init__(self)

        self.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.set_shadow_type(gtk.SHADOW_IN)

        self.batchsize = limit
        self.repo = repo
        self.currev = None
        self.construct_treeview()
        self.pbar = pbar
        self.origtip = None

    def set_repo(self, repo, pbar=None):
        self.repo = repo
        self.pbar = pbar
        self.set_author_color()

    def search_in_tree(self, model, column, key, iter, data):
        """Searches all fields shown in the tree when the user hits crtr+f,
        not just the ones that are set via tree.set_search_column.
        Case insensitive
        """
        key = key.lower()

        node = hex(model.get_value(iter, treemodel.REVISION)[treemodel.NODE])
        if node.startswith(key):
            return False

        for col in (treemodel.REVID, treemodel.TAGS, treemodel.COMMITER,
                treemodel.MESSAGE):
            if key in model.get_value(iter, col).lower():
                return False
        return True

    def create_log_generator(self, graphcol, pats, opts):
        if self.repo is None:
            self.grapher = None
            return

        if 'filehist' in opts:
            self.grapher = filelog_grapher(self.repo, opts['filehist'])
        elif graphcol:
            end = 0
            if pats is not None:  # branch name
                b = self.repo.branchtags()
                if pats in b:
                    node = b[pats]
                    start = self.repo.changelog.rev(node)
                else:
                    start = len(self.repo.changelog) - 1
            elif opts['revrange']:
                if len(opts['revrange']) >= 2:
                    start, end = opts['revrange']
                else:
                    start = opts['revrange'][0]
                    end = start
            else:
                start = len(self.repo.changelog) - 1
            noheads = opts.get('noheads', False)
            self.grapher = revision_grapher(self.repo, start, end, pats,
                    noheads)
        elif opts.get('revs', None):
            self.grapher = dumb_log_generator(self.repo, opts['revs'])
        else:
            self.grapher = filtered_log_generator(self.repo, pats, opts)
        self.show_graph = graphcol
        self.graphdata = []
        self.index = {}
        self.max_cols = 1
        self.model = None
        self.limit = self.batchsize

    def populate(self, revision=None):
        """Fill the treeview with contents.
        """
        stopped = False
        if self.repo is None:
            stopped = True
            return False

        try:
            for x in xrange(0, 50):
                (rev, node, lines, parents) = self.grapher.next()
                self.max_cols = max(self.max_cols, len(lines))
                self.index[rev] = len(self.graphdata)
                self.graphdata.append( (rev, node, lines, parents) )
                if self.model:
                    rowref = self.model.get_iter(len(self.graphdata)-1)
                    path = self.model.get_path(rowref) 
                    self.model.row_inserted(path, rowref) 
                if self.limit and len(self.graphdata) >= self.limit:
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
            if self.pbar is not None:
                self.pbar.end()
            self.emit('revisions-loaded')
            return False

        if not self.model:
            self.model = treemodel.TreeModel(self.repo, self.graphdata,
                    self.color_func)
            self.treeview.set_model(self.model)

        self.graph_cell.columns_len = self.max_cols
        width = self.graph_cell.get_size(self.treeview)[2]
        if width > 500:
            width = 500
        self.graph_column.set_fixed_width(width)
        self.graph_column.set_max_width(width)
        self.graph_column.set_visible(self.show_graph)

        if stopped:
            self.emit('revisions-loaded')
        if revision is not None:
            self.set_revision_id(revision[treemodel.REVID])
        if self.pbar is not None:
            self.pbar.end()
        return False

    def do_get_property(self, property):
        if property.name == 'date-column-visible':
            return self.date_column.get_visible()
        elif property.name == 'id-column-visible':
            return self.id_column.get_visible()
        elif property.name == 'rev-column-visible':
            return self.rev_column.get_visible()
        elif property.name == 'branch-column-visible':
            return self.branch_column.get_visible()
        elif property.name == 'utc-column-visible':
            return self.utc_column.get_visible()
        elif property.name == 'repo':
            return self.repo
        elif property.name == 'limit':
            return self.limit
        elif property.name == 'revision':
            return self.currev
        elif property.name == 'original-tip-revision':
            return self.origtip
        else:
            raise AttributeError, 'unknown property %s' % property.name

    def do_set_property(self, property, value):
        if property.name == 'date-column-visible':
            self.date_column.set_visible(value)
        elif property.name == 'id-column-visible':
            self.id_column.set_visible(value)
        elif property.name == 'rev-column-visible':
            self.rev_column.set_visible(value)
        elif property.name == 'branch-column-visible':
            self.branch_column.set_visible(value)
        elif property.name == 'utc-column-visible':
            self.utc_column.set_visible(value)
        elif property.name == 'repo':
            self.repo = value
        elif property.name == 'limit':
            self.batchsize = value
        elif property.name == 'revision':
            self.set_revision_id(value)
        elif property.name == 'original-tip-revision':
            self.origtip = value
        else:
            raise AttributeError, 'unknown property %s' % property.name

    def next_revision_batch(self, size):
        self.batchsize = size
        self.limit += self.batchsize
        if self.pbar is not None:
            self.pbar.begin()
        gobject.idle_add(self.populate)

    def load_all_revisions(self):
        self.limit = None
        if self.pbar is not None:
            self.pbar.begin()
        gobject.idle_add(self.populate)

    def get_revision(self):
        """Return revision id of currently selected revision, or None."""
        return self.get_property('revision')

    def scroll_to_revision(self, revid):
        if revid in self.index:
            row = self.index[revid]
            self.treeview.scroll_to_cell(row, use_align=True, row_align=0.5)

    def set_revision_id(self, revid):
        """Change the currently selected revision.

        :param revid: Revision id of revision to display.
        """
        if revid in self.index:
            row = self.index[revid]
            self.treeview.set_cursor(row)
            self.treeview.grab_focus()

    def get_parents(self):
        """Return the parents of the currently selected revision.

        :return: list of revision ids.
        """
        return self.get_property('parents')
        
    def refresh(self, graphcol, pats, opts):
        if self.repo is not None:
            hglib.invalidaterepo(self.repo)
            if len(self.repo.changelog) > 0:
                self.create_log_generator(graphcol, pats, opts)
                if self.pbar is not None:
                    self.pbar.begin()
                gobject.idle_add(self.populate, self.get_revision())
            else:
                self.pbar.set_status_text('Repository is empty')

    def set_author_color(self):
        # If user has configured authorcolor in [tortoisehg], color
        # rows by author matches
        self.author_pats = []
        self.color_func =  self.text_color_orig

        if self.repo is not None:
            for k, v in self.repo.ui.configitems('tortoisehg'):
                if not k.startswith('authorcolor.'): continue
                pat = k[12:]
                self.author_pats.append((re.compile(pat, re.I), v))
            if self.author_pats or self.repo.ui.configbool('tortoisehg',
                    'authorcolor'):
                self.color_func = self.text_color_author
            else:
                self.color_func = self.text_color_orig

    def construct_treeview(self):
        self.treeview = gtk.TreeView()
        self.treeview.set_rules_hint(True)
        self.treeview.set_reorderable(False)
        self.treeview.set_enable_search(True)
        self.treeview.set_search_equal_func(self.search_in_tree, None)
        self.set_author_color()

        # Fix old PyGTK (<1.12) bug - by JAM
        set_tooltip = getattr(self.treeview, 'set_tooltip_column', None)
        if set_tooltip is not None:
            set_tooltip(treemodel.MESSAGE)

        self.treeview.get_selection().set_mode(gtk.SELECTION_SINGLE)
        self.treeview.connect("cursor-changed", self._on_selection_changed)
        self.treeview.set_property('fixed-height-mode', True)
        self.treeview.show()
        self.add(self.treeview)

        self.graph_cell = CellRendererGraph()
        self.graph_column = gtk.TreeViewColumn(_('Graph'))
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

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 8)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.rev_column = gtk.TreeViewColumn(_('Rev'))
        self.rev_column.set_visible(False)
        self.rev_column.set_resizable(True)
        self.rev_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.rev_column.set_fixed_width(cell.get_size(self.treeview)[2])
        self.rev_column.pack_start(cell, expand=True)
        self.rev_column.add_attribute(cell, "text", treemodel.REVID)
        self.rev_column.add_attribute(cell, "foreground", treemodel.FGCOLOR)
        self.treeview.append_column(self.rev_column)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 15)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.id_column = gtk.TreeViewColumn(_('ID'))
        self.id_column.set_visible(False)
        self.id_column.set_resizable(True)
        self.id_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.id_column.set_fixed_width(cell.get_size(self.treeview)[2])
        self.id_column.pack_start(cell, expand=True)
        self.id_column.add_attribute(cell, "text", treemodel.HEXID)
        self.id_column.add_attribute(cell, "foreground", treemodel.FGCOLOR)
        self.treeview.append_column(self.id_column)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 15)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.branch_column = gtk.TreeViewColumn(_('Branch'))
        self.branch_column.set_visible(False)
        self.branch_column.set_resizable(True)
        self.branch_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.branch_column.set_fixed_width(cell.get_size(self.treeview)[2])
        self.branch_column.pack_start(cell, expand=True)
        self.branch_column.add_attribute(cell, "foreground", treemodel.FGCOLOR)
        self.branch_column.add_attribute(cell, "markup", treemodel.BRANCHES)
        self.treeview.append_column(self.branch_column)
        cell = gtk.CellRendererText()

        cell.set_property("width-chars", 65)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.msg_column = gtk.TreeViewColumn(_('Summary'))
        self.msg_column.set_resizable(True)
        self.msg_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.msg_column.set_fixed_width(cell.get_size(self.treeview)[2])
        self.msg_column.pack_end(cell, expand=True)
        self.msg_column.add_attribute(cell, "foreground", treemodel.FGCOLOR)
        self.msg_column.add_attribute(cell, "markup", treemodel.MESSAGE)
        self.treeview.append_column(self.msg_column)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 20)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.committer_column = gtk.TreeViewColumn(_('User'))
        self.committer_column.set_resizable(True)
        self.committer_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.committer_column.set_fixed_width(cell.get_size(self.treeview)[2])
        self.committer_column.pack_start(cell, expand=True)
        self.committer_column.add_attribute(cell, "text", treemodel.COMMITER)
        self.committer_column.add_attribute(cell, "foreground",
                treemodel.FGCOLOR)
        self.treeview.append_column(self.committer_column)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 20)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.date_column = gtk.TreeViewColumn(_('Local Date'))
        self.date_column.set_visible(False)
        self.date_column.set_resizable(True)
        self.date_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.date_column.set_fixed_width(cell.get_size(self.treeview)[2])
        self.date_column.pack_start(cell, expand=True)
        self.date_column.add_attribute(cell, "text", treemodel.TIMESTAMP)
        self.date_column.add_attribute(cell, "foreground", treemodel.FGCOLOR)
        self.treeview.append_column(self.date_column)

        cell = gtk.CellRendererText()
        cell.set_property("width-chars", 20)
        cell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.utc_column = gtk.TreeViewColumn(_('Universal Date'))
        self.utc_column.set_visible(False)
        self.utc_column.set_resizable(True)
        self.utc_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.utc_column.set_fixed_width(cell.get_size(self.treeview)[2])
        self.utc_column.pack_start(cell, expand=True)
        self.utc_column.add_attribute(cell, "text", treemodel.UTC)
        self.utc_column.add_attribute(cell, "foreground", treemodel.FGCOLOR)
        self.treeview.append_column(self.utc_column)

    def text_color_orig(self, parents, rev, author):
        if self.origtip is not None and int(rev) >= self.origtip:
            return 'darkgreen'
        if len(parents) == 2:
            # mark merge changesets blue
            return 'blue'
        elif len(parents) == 1:
            # detect non-trivial parent
            if long(rev) != parents[0]+1:
                return '#900000'
            else:
                return 'black'
        else:
            return 'black'

    colors = '''black blue deeppink mediumorchid blue burlywood4 goldenrod
     slateblue red2 navy dimgrey'''.split()
    color_cache = {}

    def text_color_author(self, parents, rev, author):
        if self.origtip is not None and int(rev) >= self.origtip:
            return 'darkgreen'
        for re, v in self.author_pats:
            if (re.search(author)):
                return v
        if author not in self.color_cache:
            color = self.colors[len(self.color_cache.keys()) % len(self.colors)]
            self.color_cache[author] = color
        return self.color_cache[author]

    def _on_selection_changed(self, treeview):
        """callback for when the treeview changes."""
        (path, focus) = treeview.get_cursor()
        if path is not None and self.model is not None:
            iter = self.model.get_iter(path)
            self.currev = self.model.get_value(iter, treemodel.REVISION)
            self.emit('revision-selected')


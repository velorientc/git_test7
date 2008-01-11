''' Mercurial revision DAG visualization library

  Implements a gtk.TreeModel which visualizes a Mercurial repository
  revision history.

Portions of this code stolen mercilessly from bzr-gtk visualization
dialog.  Other portions stolen from graphlog extension.
'''

import cairo
import gtk
import gobject
import math
import pango
import sys
import string
import re
from time import (strftime, localtime)

from mercurial.cmdutil import revrange, show_changeset
from mercurial.i18n import _
from mercurial.node import nullid, nullrev
from mercurial.util import Abort

# treemodel row enumerated attributes
REVID = 0
NODE = 1
LINES = 2
LAST_LINES = 3
MESSAGE = 4
COMMITER = 5
TIMESTAMP = 6
REVISION = 7
PARENTS = 8
CHILDREN = 9

def revision_grapher(repo, start_rev, stop_rev):
    """incremental revision grapher

    This generator function walks through the revision history from
    revision start_rev to revision stop_rev (which must be less than
    or equal to start_rev) and for each revision emits tuples with the
    following elements:

      - Current revision.
      - Current node.
      - Column of the current node in the set of ongoing edges.
      - Edges; a list of (col, next_col) indicating the edges between
        the current node and its parents.
      - Number of columns (ongoing edges) in the current revision.
      - current revision parents
      - current revision children
    """

    assert start_rev >= stop_rev
    curr_rev = start_rev
    revs = []
    while curr_rev >= stop_rev:
        node = repo.changelog.node(curr_rev)

        # Compute revs and next_revs.
        if curr_rev not in revs:
            # New head.
            revs.append(curr_rev)
        rev_index = revs.index(curr_rev)
        next_revs = revs[:]

        # Add parents to next_revs.
        parents = [x for x in repo.changelog.parentrevs(curr_rev) if x != nullrev]
        parents_to_add = []
        for parent in parents:
            if parent not in next_revs:
                parents_to_add.append(parent)
        parents_to_add.sort()
        next_revs[rev_index:rev_index + 1] = parents_to_add

        edges = []
        for parent in parents:
            edges.append((rev_index, next_revs.index(parent)))

        children = repo.changelog.children(node)
        yield (curr_rev, node, rev_index, edges, len(revs), parents, children)

        revs = next_revs
        curr_rev -= 1

class TreeModel(gtk.GenericTreeModel):

    def __init__ (self, repo, graph_generator):
        gtk.GenericTreeModel.__init__(self)
        self.revisions = {}
        self.repo = repo
        self.grapher = graph_generator
        self.line_graph_data = []

    def on_get_flags(self):
        return gtk.TREE_MODEL_LIST_ONLY

    def on_get_n_columns(self):
        return 11

    def on_get_column_type(self, index):
        if index == REVID: return gobject.TYPE_STRING
        if index == NODE: return gobject.TYPE_PYOBJECT
        if index == LINES: return gobject.TYPE_PYOBJECT
        if index == LAST_LINES: return gobject.TYPE_PYOBJECT
        if index == MESSAGE: return gobject.TYPE_STRING
        if index == COMMITER: return gobject.TYPE_STRING
        if index == TIMESTAMP: return gobject.TYPE_STRING
        if index == REVISION: return gobject.TYPE_PYOBJECT
        if index == PARENTS: return gobject.TYPE_PYOBJECT
        if index == CHILDREN: return gobject.TYPE_PYOBJECT

    def on_get_iter(self, path):
        return path[0]

    def on_get_path(self, rowref):
        return rowref

    def on_get_value(self, rowref, column):
        # Dynamically generate graph rows on demand
        while rowref >= len(self.line_graph_data):
            (rev, node, node_index, edges,
                    n_columns, parents, children) = self.grapher()
            lines = [(r, 0) for (r, n) in edges]
            self.line_graph_data.append( (rev, (node_index, 0),
                lines, parents, children) )

        (revid, node, lines, parents, children) = self.line_graph_data[rowref]

        if column == REVID: return revid
        if column == NODE: return node
        if column == LINES: return lines
        if column == PARENTS: return parents
        if column == CHILDREN: return children
        if column == LAST_LINES:
            if rowref>0:
                return self.line_graph_data[rowref-1][2]
            return []

        if revid not in self.revisions:
            # TODO: not sure about this
            ctx = self.repo.changectx(revid)
            revision = (ctx.user(), ctx.date(), ctx.description())
            self.revisions[revid] = revision
        else:
            revision = self.revisions[revid]

        if column == REVISION: return revision
        if column == MESSAGE: return revision[2]
        if column == COMMITER: return re.sub('<.*@.*>', '',
                                             revision[0]).strip(' ')
        if column == TIMESTAMP: # TODO: not sure if this is correct
            return strftime("%Y-%m-%d %H:%M", localtime(revision[1]))

    def on_iter_next(self, rowref):
        if rowref < len(self.line_graph_data) - 1:
            return rowref+1
        return None

    def on_iter_children(self, parent):
        if parent is None: return 0
        return None

    def on_iter_has_child(self, rowref):
        return False

    def on_iter_n_children(self, rowref):
        if rowref is None: return len(self.line_graph_data)
        return 0

    def on_iter_nth_child(self, parent, n):
        if parent is None: return n
        return None

    def on_iter_parent(self, child):
        return None


class CellRendererGraph(gtk.GenericCellRenderer):
    """Cell renderer for directed graph.

    Properties:
      node              (column, colour) tuple to draw revision node,
      in_lines          (start, end, colour) tuple list to draw inward lines,
      out_lines         (start, end, colour) tuple list to draw outward lines.
    """

    columns_len = 0

    __gproperties__ = {
        "node":         ( gobject.TYPE_PYOBJECT, "node",
                          "revision node instruction",
                          gobject.PARAM_WRITABLE
                        ),
        "in-lines":     ( gobject.TYPE_PYOBJECT, "in-lines",
                          "instructions to draw lines into the cell",
                          gobject.PARAM_WRITABLE
                        ),
        "out-lines":    ( gobject.TYPE_PYOBJECT, "out-lines",
                          "instructions to draw lines out of the cell",
                          gobject.PARAM_WRITABLE
                        ),
        }

    def do_set_property(self, property, value):
        """Set properties from GObject properties."""
        if property.name == "node":
            self.node = value
        elif property.name == "in-lines":
            self.in_lines = value
        elif property.name == "out-lines":
            self.out_lines = value
        else:
            raise AttributeError, "no such property: '%s'" % property.name

    def box_size(self, widget):
        """Calculate box size based on widget's font.

        Cache this as it's probably expensive to get.  It ensures that we
        draw the graph at least as large as the text.
        """
        try:
            return self._box_size
        except AttributeError:
            pango_ctx = widget.get_pango_context()
            font_desc = widget.get_style().font_desc
            metrics = pango_ctx.get_metrics(font_desc)

            ascent = pango.PIXELS(metrics.get_ascent())
            descent = pango.PIXELS(metrics.get_descent())

            self._box_size = ascent + descent + 6
            return self._box_size

    def set_colour(self, ctx, colour, bg, fg):
        """Set the context source colour.

        Picks a distinct colour based on an internal wheel; the bg
        parameter provides the value that should be assigned to the 'zero'
        colours and the fg parameter provides the multiplier that should be
        applied to the foreground colours.
        """
        mainline_color = ( 0.0, 0.0, 0.0 )
        colours = [
            ( 1.0, 0.0, 0.0 ),
            ( 1.0, 1.0, 0.0 ),
            ( 0.0, 1.0, 0.0 ),
            ( 0.0, 1.0, 1.0 ),
            ( 0.0, 0.0, 1.0 ),
            ( 1.0, 0.0, 1.0 ),
            ]

        if colour == 0:
            colour_rgb = mainline_color
        else:
            colour_rgb = colours[colour % len(colours)]

        red   = (colour_rgb[0] * fg) or bg
        green = (colour_rgb[1] * fg) or bg
        blue  = (colour_rgb[2] * fg) or bg

        ctx.set_source_rgb(red, green, blue)

    def on_get_size(self, widget, cell_area):
        """Return the size we need for this cell.

        Each cell is drawn individually and is only as wide as it needs
        to be, we let the TreeViewColumn take care of making them all
        line up.
        """
        box_size = self.box_size(widget) + 1

        width = box_size * (self.columns_len + 1)
        height = box_size

        # FIXME I have no idea how to use cell_area properly
        return (0, 0, width, height)

    def on_render(self, window, widget, bg_area, cell_area, exp_area, flags):
        """Render an individual cell.

        Draws the cell contents using cairo, taking care to clip what we
        do to within the background area so we don't draw over other cells.
        Note that we're a bit naughty there and should really be drawing
        in the cell_area (or even the exposed area), but we explicitly don't
        want any gutter.

        We try and be a little clever, if the line we need to draw is going
        to cross other columns we actually draw it as in the .---' style
        instead of a pure diagonal ... this reduces confusion by an
        incredible amount.
        """
        ctx = window.cairo_create()
        ctx.rectangle(bg_area.x, bg_area.y, bg_area.width, bg_area.height)
        ctx.clip()

        box_size = self.box_size(widget)

        ctx.set_line_width(box_size / 8)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)

        # Draw lines into the cell
        for start, end, colour in self.in_lines:
            self.render_line (ctx, cell_area, box_size,
                         bg_area.y, bg_area.height,
                         start, end, colour)

        # Draw lines out of the cell
        for start, end, colour in self.out_lines:
            self.render_line (ctx, cell_area, box_size,
                         bg_area.y + bg_area.height, bg_area.height,
                         start, end, colour)

        # Draw the revision node in the right column
        (column, colour) = self.node
        ctx.arc(cell_area.x + box_size * column + box_size / 2,
                cell_area.y + cell_area.height / 2,
                box_size / 4, 0, 2 * math.pi)

        self.set_colour(ctx, colour, 0.0, 0.5)
        ctx.stroke_preserve()

        self.set_colour(ctx, colour, 0.5, 1.0)
        ctx.fill()

    def render_line (self, ctx, cell_area, box_size, mid,
            height, start, end, colour):
        if start is None:
            x = cell_area.x + box_size * end + box_size / 2
            ctx.move_to(x, mid + height / 3)
            ctx.line_to(x, mid + height / 3)
            ctx.move_to(x, mid + height / 6)
            ctx.line_to(x, mid + height / 6)

        elif end is None:
            x = cell_area.x + box_size * start + box_size / 2
            ctx.move_to(x, mid - height / 3)
            ctx.line_to(x, mid - height / 3)
            ctx.move_to(x, mid - height / 6)
            ctx.line_to(x, mid - height / 6)
        else:
            startx = cell_area.x + box_size * start + box_size / 2
            endx = cell_area.x + box_size * end + box_size / 2

            ctx.move_to(startx, mid - height / 2)

            if start - end == 0 :
                ctx.line_to(endx, mid + height / 2)
            else:
                ctx.curve_to(startx, mid - height / 5,
                             startx, mid - height / 5,
                             startx + (endx - startx) / 2, mid)

                ctx.curve_to(endx, mid + height / 5,
                             endx, mid + height / 5 ,
                             endx, mid + height / 2)

        self.set_colour(ctx, colour, 0.0, 0.65)
        ctx.stroke()

class TreeView(gtk.ScrolledWindow):

    __gproperties__ = {
        'repo': (gobject.TYPE_PYOBJECT,
                   'Repository',
                   'The Mercurial repository being visualized',
                   gobject.PARAM_CONSTRUCT_ONLY | gobject.PARAM_WRITABLE),

        'revision': (gobject.TYPE_PYOBJECT,
                     'Revision',
                     'The currently selected revision',
                     gobject.PARAM_READWRITE),

        'revision-number': (gobject.TYPE_STRING,
                            'Revision number',
                            'The number of the selected revision',
                            '',
                            gobject.PARAM_READABLE),

        'children': (gobject.TYPE_PYOBJECT,
                     'Child revisions',
                     'Children of the currently selected revision',
                     gobject.PARAM_READABLE),

        'parents': (gobject.TYPE_PYOBJECT,
                    'Parent revisions',
                    'Parents to the currently selected revision',
                    gobject.PARAM_READABLE),

        'date-column-visible': (gobject.TYPE_BOOLEAN,
                                 'Date',
                                 'Show date column',
                                 False,
                                 gobject.PARAM_READWRITE),

        'compact': (gobject.TYPE_BOOLEAN,
                    'Compact view',
                    'Break ancestry lines to save space',
                    True,
                    gobject.PARAM_CONSTRUCT | gobject.PARAM_READWRITE)

    }

    __gsignals__ = {
        'revisions-loaded': (gobject.SIGNAL_RUN_FIRST, 
                             gobject.TYPE_NONE,
                             ()),
        'revision-selected': (gobject.SIGNAL_RUN_FIRST,
                              gobject.TYPE_NONE,
                              ())
    }

    def __init__(self, repo, start, maxnum, compact=True):
        """Create a new TreeView.

        :param repo:  Repository object to show.
        :param start: Revision id of top revision.
        :param maxnum: Maximum number of revisions to display, 
                       None for no limit.
        """
        gtk.ScrolledWindow.__init__(self)

        self.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        self.set_shadow_type(gtk.SHADOW_IN)

        self.construct_treeview()

        self.iter   = None
        self.repo = repo

        self.start = start
        self.maxnum = maxnum
        self.compact = compact

        gobject.idle_add(self.populate)

    def do_get_property(self, property):
        if property.name == 'date-column-visible':
            return self.date_column.get_visible()
        elif property.name == 'compact':
            return self.compact
        elif property.name == 'repo':
            return self.repo
        elif property.name == 'revision':
            return self.model.get_value(self.iter, treemodel.REVISION)
        elif property.name == 'children':
            return self.model.get_value(self.iter, treemodel.CHILDREN)
        elif property.name == 'parents':
            return self.model.get_value(self.iter, treemodel.PARENTS)
        else:
            raise AttributeError, 'unknown property %s' % property.name

    def do_set_property(self, property, value):
        if property.name == 'date-column-visible':
            self.date_column.set_visible(value)
        elif property.name == 'compact':
            self.compact = value
        elif property.name == 'repo':
            self.repo = value
        elif property.name == 'revision':
            self.set_revision_id(value.revision_id)
        else:
            raise AttributeError, 'unknown property %s' % property.name

    def get_revision(self):
        """Return revision id of currently selected revision, or None."""
        return self.get_property('revision')

    def set_revision(self, revision):
        self.set_property('revision', revision)

    def set_revision_id(self, revid):
        """Change the currently selected revision.

        :param revid: Revision id of revision to display.
        """
        self.treeview.set_cursor(self.index[revid])
        self.treeview.grab_focus()

    def get_children(self):
        """Return the children of the currently selected revision.

        :return: list of revision ids.
        """
        return self.get_property('children')

    def get_parents(self):
        """Return the parents of the currently selected revision.

        :return: list of revision ids.
        """
        return self.get_property('parents')
        
    def refresh(self):
        gobject.idle_add(self.populate, self.get_revision())

    def update(self):
        print 'TreeView.update() unimplemented'

    def back(self):
        """Signal handler for the Back button."""
        parents = self.get_parents()
        if not len(parents):
            return

        for parent_id in parents:
            parent_index = self.index[parent_id]
            parent = self.model[parent_index][treemodel.REVISION]
            if same_branch(self.get_revision(), parent):
                self.set_revision(parent)
                break
        else:
            self.set_revision_id(parents[0])

    def forward(self):
        """Signal handler for the Forward button."""
        children = self.get_children()
        if not len(children):
            return

        for child_id in children:
            child_index = self.index[child_id]
            child = self.model[child_index][treemodel.REVISION]
            if same_branch(child, self.get_revision()):
                self.set_revision(child)
                break
        else:
            self.set_revision_id(children[0])

    def populate(self, revision=None):
        """Fill the treeview with contents.
        """
        opts = { 'rev' : [] }
        limit = self.repo.ui.config('tortoisehg', 'graphlimit')
        (start_rev, stop_rev) = (repo.changelog.count() - 1, 0)
        stop_rev = max(stop_rev, start_rev - limit + 1)
        grapher = revision_grapher(self.repo, start_rev, stop_rev)

        self.model = TreeModel(self.repo, grapher)
        self.graph_cell.columns_len = 4 # TODO not known up-front
        width = self.graph_cell.get_size(self.treeview)[2]
        if width > 500:
            width = 500
        self.graph_column.set_fixed_width(width)
        self.graph_column.set_max_width(width)
        self.index = index
        self.treeview.set_model(self.model)

        if revision is None:
            self.treeview.set_cursor(0)
        else:
            self.set_revision(revision)

        # TODO: this looks broken
        self.emit('revisions-loaded')
        return False

    def construct_treeview(self):
        self.treeview = gtk.TreeView()

        self.treeview.set_rules_hint(True)
        self.treeview.set_search_column(treemodel.REVID)
        
        # Fix old PyGTK bug - by JAM
        set_tooltip = getattr(self.treeview, 'set_tooltip_column', None)
        if set_tooltip is not None:
            set_tooltip(treemodel.MESSAGE)

        self.treeview.connect("cursor-changed",
                self._on_selection_changed)

        # TODO: Parent should connect menu events
        #self.treeview.connect("row-activated", 
        #        self._on_revision_activated)
        #self.treeview.connect("button-release-event", 
        #        self._on_revision_selected)
        #self.treeview.connect('popup-menu',
        #        self._popup_menu)

        self.treeview.set_property('fixed-height-mode', True)

        self.add(self.treeview)
        self.treeview.show()

        self.graph_cell = CellRendererGraph()
        self.graph_column = gtk.TreeViewColumn()
        self.graph_column.set_resizable(True)
        self.graph_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.graph_column.pack_start(self.graph_cell, expand=False)
        self.graph_column.add_attribute(self.graph_cell, "node", treemodel.NODE)
        self.graph_column.add_attribute(self.graph_cell, "in-lines", treemodel.LAST_LINES)
        self.graph_column.add_attribute(self.graph_cell, "out-lines", treemodel.LINES)
        self.treeview.append_column(self.graph_column)

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
        cell.set_property("width-chars", 15)
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

    def _on_selection_changed(self, treeview):
        """callback for when the treeview changes."""
        (path, focus) = treeview.get_cursor()
        if path is not None:
            self.iter = self.model.get_iter(path)
            self.emit('revision-selected')


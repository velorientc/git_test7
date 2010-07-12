# Copyright (c) 2009-2010 LOGILAB S.A. (Paris, FRANCE).
# http://www.logilab.fr/ -- mailto:contact@logilab.fr
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

from mercurial import util, error

from tortoisehg.util import hglib
from tortoisehg.hgqt.graph import Graph
from tortoisehg.hgqt.graph import revision_grapher
from tortoisehg.hgqt import qtlib

from tortoisehg.hgqt.i18n import _

from PyQt4.QtCore import *
from PyQt4.QtGui import *

nullvariant = QVariant()

# TODO: Remove these two when we adopt GTK author color scheme
COLORS = [ "blue", "darkgreen", "red", "green", "darkblue", "purple",
           "cyan", Qt.darkYellow, "magenta", "darkred", "darkmagenta",
           "darkcyan", "gray", "yellow", ]
COLORS = [str(QColor(x).name()) for x in COLORS]

ALLCOLUMNS = ('Graph', 'ID', 'Branch', 'Log', 'Author', 'Tags', 'Node',
              'Age', 'LocalTime', 'UTCTime')

def get_color(n, ignore=()):
    """
    Return a color at index 'n' rotating in the available
    colors. 'ignore' is a list of colors not to be chosen.
    """
    ignore = [str(QColor(x).name()) for x in ignore]
    colors = [x for x in COLORS if x not in ignore]
    if not colors: # ghh, no more available colors...
        colors = COLORS
    return colors[n % len(colors)]

def datacached(meth):
    """
    decorator used to cache 'data' method of Qt models. It will *not*
    cache nullvariant return values (so costly non-null values
    can be computed and filled as a background process)
    """
    def data(self, index, role):
        if not index.isValid():
            return nullvariant
        row = index.row()
        col = index.column()
        if (row, col, role) in self.datacache:
            return self.datacache[(row, col, role)]
        try:
            result = meth(self, index, role)
        except util.Abort:
            result = nullvariant
        if result is not nullvariant:
            self.datacache[(row, col, role)] = result
        return result
    return data

class HgRepoListModel(QAbstractTableModel):
    """
    Model used for displaying the revisions of a Hg *local* repository
    """
    _columns = ('Graph', 'ID', 'Branch', 'Log', 'Author', 'Age', 'Tags',)
    _stretchs = {'Log': 1, }

    def __init__(self, repo, branch='', parent=None):
        """
        repo is a hg repo instance
        """
        QAbstractTableModel.__init__(self, parent)
        self.datacache = {}
        self.mqueues = []
        self.wd_revs = []
        self.graph = None
        self.timerHandle = None
        self.rowcount = 0
        self.repo = repo
        self.reloadConfig()
        self.setRepo(repo, branch=branch)

        # To be deleted
        self._user_colors = {}
        self._branch_colors = {}

        self._columnmap = {'ID':       lambda ctx, gnode: ctx.rev() is not None and str(ctx.rev()) or "",
                           'Node':     lambda ctx, gnode: str(ctx),
                           'Graph':    lambda ctx, gnode: "",
                           'Log':      self.getlog,
                           'Author':   lambda ctx, gnode: hglib.username(ctx.user()),
                           'Tags':     self.gettags,
                           'Branch':   lambda ctx, gnode: ctx.branch(),
                           'Filename': lambda ctx, gnode: gnode.extra[0],
                           'Age':      lambda ctx, gnode: hglib.age(ctx.date()),
                           'LocalTime':lambda ctx, gnode: hglib.displaytime(ctx.date()),
                           'UTCTime':  lambda ctx, gnode: hglib.utctime(ctx.date()),
                           }


    def setRepo(self, repo, branch=''):
        oldroot = self.repo.root
        self.repo = repo
        self.filterbranch = branch
        if oldroot != repo.root:
            self.reloadConfig()
        self.datacache = {}
        try:
            wdctxs = self.repo.parents()
        except error.Abort:
            # might occur if reloading during a mq operation (or
            # whatever operation playing with hg history)
            return
        self.wd_revs = [ctx.rev() for ctx in wdctxs]
        self.mqueues = hglib.getmqpatchtags(self.repo)
        grapher = revision_grapher(self.repo, start_rev=None,
                                   follow=False, branch=branch)
        self.graph = Graph(self.repo, grapher, self.max_file_size)
        self.rowcount = 0
        self.emit(SIGNAL('layoutChanged()'))
        self.heads = [self.repo.changectx(x).rev() for x in self.repo.heads()]
        self.ensureBuilt(row=self.fill_step)
        # filled signal triggers column resize using first fill_step rows
        QTimer.singleShot(0, lambda: self.emit(SIGNAL('filled')))
        self.timerHandle = self.startTimer(1)

    def reloadConfig(self):
        self.dot_radius = 8
        self.rowheight = 20
        self.fill_step = 500            # use hgtk logic
        self.max_file_size = 1024*1024  # will be removed
        self.authorcolor = self.repo.ui.configbool('tortoisehg', 'authorcolor')
        self.updateColumns()
        self.maxauthor = 'author name'

    def updateColumns(self):
        s = QSettings()
        cols = s.value('workbench/columns').toStringList()
        cols = [str(col) for col in cols]
        validcols = [col for col in cols if col in ALLCOLUMNS]
        if validcols:
            self._columns = tuple(validcols)
            self.datacache = {}
            self.emit(SIGNAL("layoutChanged()"))

    def branch(self):
        return self.filterbranch

    def ensureBuilt(self, rev=None, row=None):
        """
        Make sure rev data is available (graph element created).

        """
        if self.graph.isfilled():
            return
        required = 0
        buildrev = rev
        n = len(self.graph)
        if rev is not None:
            if n and self.graph[-1].rev <= rev:
                buildrev = None
            else:
                required = self.fill_step/2
        elif row is not None and row > (n - self.fill_step / 2):
            required = row - n + self.fill_step
        if required or buildrev:
            self.graph.build_nodes(nnodes=required, rev=buildrev)
            self.updateRowCount()
        elif row and row > self.rowcount:
            # asked row was already built, but views where not aware of this
            self.updateRowCount()
        elif rev is not None and rev <= self.graph[self.rowcount].rev:
            # asked rev was already built, but views where not aware of this
            self.updateRowCount()

    def timerEvent(self, event):
        if event.timerId() == self.timerHandle:
            self.emit(SIGNAL('showMessage'), 'filling (%s)'%(len(self.graph)))
            if self.graph.isfilled():
                self.killTimer(self.timerHandle)
                self.timerHandle = None
                self.emit(SIGNAL('showMessage'), '')
                self.emit(SIGNAL('loaded'))
            # we only fill the graph data structures without telling
            # views until the model is loaded, to keep maximal GUI
            # reactivity
            elif not self.graph.build_nodes():
                self.killTimer(self.timerHandle)
                self.timerHandle = None
                self.updateRowCount()
                self.emit(SIGNAL('showMessage'), '')
                self.emit(SIGNAL('loaded'))

    def updateRowCount(self):
        currentlen = self.rowcount
        newlen = len(self.graph)

        sauthors = [hglib.username(user) for user in list(self.graph.authors)]
        sauthors.append(self.maxauthor)
        self.maxauthor = sorted(sauthors, key=lambda x: len(x))[-1]

        if newlen > self.rowcount:
            self.beginInsertRows(QModelIndex(), currentlen, newlen-1)
            self.rowcount = newlen
            self.endInsertRows()

    def rowCount(self, parent=None):
        return self.rowcount

    def columnCount(self, parent=None):
        return len(self._columns)

    def maxWidthValueForColumn(self, col):
        column = self._columns[col]
        if column == 'ID':
            return str(len(self.repo))
        if column == 'Node':
            return str(self.repo['.'])
        if column in ('Age', 'LocalTime', 'UTCTime'):
            return hglib.displaytime(self.repo[None].date())
        if column == 'Tags':
            try:
                return sorted(self.repo.tags().keys(), key=lambda x: len(x))[-1][:10]
            except IndexError:
                pass
        if column == 'Branch':
            try:
                return sorted(self.repo.branchtags().keys(), key=lambda x: len(x))[-1]
            except IndexError:
                pass
        if column == 'Author':
            return self.maxauthor
        if column == 'Filename':
            return self.filename
        if column == 'Graph':
            res = self.col2x(self.graph.max_cols)
            return min(res, 150)
        # Fall through for Log
        return None

    def user_color(self, user):
        'deprecated, please replace with hgtk color scheme'
        if user not in self._user_colors:
            self._user_colors[user] = get_color(len(self._user_colors),
                                                self._user_colors.values())
        return self._user_colors[user]

    def namedbranch_color(self, branch):
        'deprecated, please replace with hgtk color scheme'
        if branch not in self._branch_colors:
            self._branch_colors[branch] = get_color(len(self._branch_colors))
        return self._branch_colors[branch]

    def col2x(self, col):
        return 2 * self.dot_radius * col + self.dot_radius/2 + 8

    def graphctx(self, ctx, gnode):
        w = self.col2x(gnode.cols) + 10
        h = self.rowheight

        dot_y = h / 2

        pix = QPixmap(w, h)
        pix.fill(QColor(0,0,0,0))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)

        pen = QPen(Qt.blue)
        pen.setWidth(2)
        painter.setPen(pen)

        lpen = QPen(pen)
        lpen.setColor(Qt.black)
        painter.setPen(lpen)
        for y1, y4, lines in ((dot_y, dot_y + h, gnode.bottomlines),
                              (dot_y - h, dot_y, gnode.toplines)):
            y2 = y1 + 1 * (y4 - y1)/4
            ymid = (y1 + y4)/2
            y3 = y1 + 3 * (y4 - y1)/4

            for start, end, color in lines:
                lpen = QPen(pen)
                lpen.setColor(QColor(get_color(color)))
                lpen.setWidth(2)
                painter.setPen(lpen)
                x1 = self.col2x(start)
                x2 = self.col2x(end)
                path = QPainterPath()
                path.moveTo(x1, y1)
                path.cubicTo(x1, y2,
                             x1, y2,
                             (x1 + x2)/2, ymid)
                path.cubicTo(x2, y3,
                             x2, y3,
                             x2, y4)
                painter.drawPath(path)

        # Draw node
        dot_color = QColor(self.namedbranch_color(ctx.branch()))
        dotcolor = dot_color.lighter()
        pencolor = dot_color.darker()
        white = QColor("white")
        fillcolor = gnode.rev is None and white or dotcolor

        pen = QPen(pencolor)
        pen.setWidthF(1.5)                
        painter.setPen(pen)

        radius = self.dot_radius
        centre_x = self.col2x(gnode.x)
        centre_y = h/2

        def circle(r):
            rect = QRectF(centre_x - r,
                          centre_y - r,
                          2 * r, 2 * r)
            painter.drawEllipse(rect)                    
            
        def diamond(r):
            poly = QPolygonF([QPointF(centre_x - r, centre_y),
                              QPointF(centre_x, centre_y - r),
                              QPointF(centre_x + r, centre_y),
                              QPointF(centre_x, centre_y + r),
                              QPointF(centre_x - r, centre_y),])
            painter.drawPolygon(poly)

        tags = set(ctx.tags())
        if tags.intersection(self.mqueues):  # diamonds for patches
            if self.is_working_directory_parent(gnode.rev):
                painter.setBrush(white)
                diamond(2 * 0.9 * radius / 1.5)
            painter.setBrush(fillcolor)
            diamond(radius / 1.5)
        else:  # circles for normal revisions
            if self.is_working_directory_parent(gnode.rev):
                painter.setBrush(white)
                circle(0.9 * radius)
            painter.setBrush(fillcolor)
            circle(0.5 * radius)

        painter.end()
        return QVariant(pix)

    @datacached
    def data(self, index, role):
        if not index.isValid():
            return nullvariant
        row = index.row()
        self.ensureBuilt(row=row)
        column = self._columns[index.column()]
        gnode = self.graph[row]
        ctx = self.repo.changectx(gnode.rev)
        if role == Qt.DisplayRole:
            text = self._columnmap[column](ctx, gnode)
            if not isinstance(text, (QString, unicode)):
                text = hglib.tounicode(text)
            return QVariant(text)
        elif role == Qt.ForegroundRole:
            if column == 'Author':
                if self.authorcolor:
                    return QVariant(QColor(self.user_color(ctx.user())))
                return nullvariant
            if column == 'Branch':
                return QVariant(QColor(self.namedbranch_color(ctx.branch())))
        elif role == Qt.DecorationRole:
            if column == 'Graph':
                return self.graphctx(ctx, gnode)
        return nullvariant

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return QVariant(self._columns[section])
            if role == Qt.TextAlignmentRole:
                return QVariant(Qt.AlignLeft)
        return nullvariant

    def rowFromRev(self, rev):
        row = self.graph.index(rev)
        if row == -1:
            row = None
        return row

    def indexFromRev(self, rev):
        self.ensureBuilt(rev=rev)
        row = self.rowFromRev(rev)
        if row is not None:
            return self.index(row, 0)
        return None

    def clear(self):
        'empty the list'
        self.graph = None
        self.datacache = {}
        self.emit(SIGNAL("layoutChanged()"))

    def gettags(self, ctx, gnode):
        if ctx.rev() is None:
            return ""
        mqtags = ['qbase', 'qtip', 'qparent']
        tags = ctx.tags()
        tags = [t for t in tags if t not in mqtags]
        return hglib.tounicode(",".join(tags))

    def is_working_directory_parent(self, rev):
        return rev in self.wd_revs
    
    def getlog(self, ctx, gnode):
        # TODO: add bookmark
        if ctx.rev() is None:
            return '**  ' + _('Working copy changes') + '  **'
        
        parts = []
        if ctx in [self.repo[x] for x in self.repo.branchmap()]:
            effects = qtlib.geteffect('log.branch')
            text = qtlib.applyeffects(' %s ' % ctx.branch(), effects)
            parts.append(text)

        for tag in (hglib.getctxtags(ctx) or []):
            style = tag in self.mqueues and 'log.patch' or 'log.tag'
            effects = qtlib.geteffect(style)
            text = qtlib.applyeffects(' %s ' % tag, effects)
            parts.append(text)

        msg = hglib.tounicode(ctx.description())
        if msg:
            msg = msg.splitlines()[0]
            if self.is_working_directory_parent(gnode.rev):
                msg = qtlib.markup(msg, weight='bold')
        parts.append(msg)

        return ' '.join(parts)

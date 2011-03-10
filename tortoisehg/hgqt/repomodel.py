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
from mercurial.util import propertycache

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

ALLCOLUMNS = ('Graph', 'Rev', 'Branch', 'Description', 'Author', 'Tags', 'Node',
              'Age', 'LocalTime', 'UTCTime', 'Changes')

UNAPPLIED_PATCH_COLOR = '#999999'

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

class HgRepoListModel(QAbstractTableModel):
    """
    Model used for displaying the revisions of a Hg *local* repository
    """
    showMessage = pyqtSignal(unicode)
    filled = pyqtSignal()
    loaded = pyqtSignal()

    _columns = ('Graph', 'Rev', 'Branch', 'Description', 'Author', 'Age', 'Tags',)
    _stretchs = {'Description': 1, }
    _mqtags = ('qbase', 'qtip', 'qparent')

    def __init__(self, repo, branch, revset, rfilter, parent):
        """
        repo is a hg repo instance
        """
        QAbstractTableModel.__init__(self, parent)
        self._cache = []
        self.graph = None
        self.timerHandle = None
        self.dotradius = 8
        self.rowheight = 20
        self.rowcount = 0
        self.repo = repo
        self.revset = revset
        self.filterbyrevset = rfilter
        self.unicodestar = True
        self.unicodexinabox = True

        # To be deleted
        self._user_colors = {}
        self._branch_colors = {}

        self._columnmap = {
            'Rev':      self.getrev,
            'Node':     lambda ctx, gnode: str(ctx),
            'Graph':    lambda ctx, gnode: "",
            'Description': self.getlog,
            'Author':   self.getauthor,
            'Tags':     self.gettags,
            'Branch':   self.getbranch,
            'Filename': lambda ctx, gnode: gnode.extra[0],
            'Age':      lambda ctx, gnode: hglib.age(ctx.date()),
            'LocalTime':lambda ctx, gnode: hglib.displaytime(ctx.date()),
            'UTCTime':  lambda ctx, gnode: hglib.utctime(ctx.date()),
            'Changes':  self.getchanges,
        }

        if repo:
            self.reloadConfig()
            self.updateColumns()
            self.setBranch(branch)

    def setBranch(self, branch=None, allparents=True):
        self.filterbranch = branch
        self.invalidateCache()
        if self.revset and self.filterbyrevset:
            grapher = revision_grapher(self.repo, revset=self.revset)
            self.graph = Graph(self.repo, grapher, include_mq=False)
        else:
            grapher = revision_grapher(self.repo, branch=branch,
                                       allparents=allparents)
            self.graph = Graph(self.repo, grapher, include_mq=True)
        self.rowcount = 0
        self.layoutChanged.emit()
        self.ensureBuilt(row=0)
        self.showMessage.emit('')
        QTimer.singleShot(0, lambda: self.filled.emit())

    def reloadConfig(self):
        _ui = self.repo.ui
        self.fill_step = int(_ui.config('tortoisehg', 'graphlimit', 500))
        self.authorcolor = _ui.configbool('tortoisehg', 'authorcolor')

    def updateColumns(self):
        s = QSettings()
        cols = s.value('workbench/columns').toStringList()
        cols = [str(col) for col in cols]
        # Fixup older names for columns
        if 'Log' in cols:
            cols[cols.index('Log')] = 'Description'
            s.setValue('workbench/columns', cols)
        if 'ID' in cols:
            cols[cols.index('ID')] = 'Rev'
            s.setValue('workbench/columns', cols)
        validcols = [col for col in cols if col in ALLCOLUMNS]
        if validcols:
            self._columns = tuple(validcols)
            self.invalidateCache()
            self.layoutChanged.emit()

    def invalidate(self):
        self.reloadConfig()
        self.invalidateCache()
        self.layoutChanged.emit()

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

        if self.rowcount >= len(self.graph):
            return  # no need to update row count
        if row and row > self.rowcount:
            # asked row was already built, but views where not aware of this
            self.updateRowCount()
        elif rev is not None and rev <= self.graph[self.rowcount].rev:
            # asked rev was already built, but views where not aware of this
            self.updateRowCount()

    def loadall(self):
        self.timerHandle = self.startTimer(1)

    def timerEvent(self, event):
        if event.timerId() == self.timerHandle:
            self.showMessage.emit(_('filling (%d)')%(len(self.graph)))
            if self.graph.isfilled():
                self.killTimer(self.timerHandle)
                self.timerHandle = None
                self.showMessage.emit('')
                self.loaded.emit()
            # we only fill the graph data structures without telling
            # views until the model is loaded, to keep maximal GUI
            # reactivity
            elif not self.graph.build_nodes():
                self.killTimer(self.timerHandle)
                self.timerHandle = None
                self.updateRowCount()
                self.showMessage.emit('')
                self.loaded.emit()

    def updateRowCount(self):
        currentlen = self.rowcount
        newlen = len(self.graph)

        if newlen > self.rowcount:
            self.beginInsertRows(QModelIndex(), currentlen, newlen-1)
            self.rowcount = newlen
            self.endInsertRows()

    def rowCount(self, parent):
        if parent.isValid():
            return 0
        return self.rowcount

    def columnCount(self, parent):
        if parent.isValid():
            return 0
        return len(self._columns)

    def maxWidthValueForColumn(self, col):
        if self.graph is None:
            return 'XXXX'
        column = self._columns[col]
        if column == 'Rev':
            return '8' * len(str(len(self.repo))) + '+'
        if column == 'Node':
            return '8' * 12 + '+'
        if column in ('LocalTime', 'UTCTime'):
            return hglib.displaytime(util.makedate())
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
        if column == 'Filename':
            return self.filename
        if column == 'Graph':
            res = self.col2x(self.graph.max_cols)
            return min(res, 150)
        if column == 'Changes':
            return 'Changes'
        # Fall through for Description
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
        return 2 * self.dotradius * col + self.dotradius/2 + 8

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

        radius = self.dotradius
        centre_x = self.col2x(gnode.x)
        centre_y = h/2

        def circle(r):
            rect = QRectF(centre_x - r,
                          centre_y - r,
                          2 * r, 2 * r)
            painter.drawEllipse(rect)

        def closesymbol(s):
            rect_ = QRectF(centre_x - 1.5 * s, centre_y - 0.5 * s, 3 * s, s)
            painter.drawRect(rect_)

        def diamond(r):
            poly = QPolygonF([QPointF(centre_x - r, centre_y),
                              QPointF(centre_x, centre_y - r),
                              QPointF(centre_x + r, centre_y),
                              QPointF(centre_x, centre_y + r),
                              QPointF(centre_x - r, centre_y),])
            painter.drawPolygon(poly)

        if ctx.thgmqappliedpatch():  # diamonds for patches
            if ctx.thgwdparent():
                painter.setBrush(white)
                diamond(2 * 0.9 * radius / 1.5)
            painter.setBrush(fillcolor)
            diamond(radius / 1.5)
        elif ctx.thgmqunappliedpatch():
            patchcolor = QColor('#dddddd')
            painter.setBrush(patchcolor)
            painter.setPen(patchcolor)
            diamond(radius / 1.5)
        elif ctx.extra().get('close'):
            painter.setBrush(fillcolor)
            closesymbol(0.5 * radius)
        else:  # circles for normal revisions
            if ctx.thgwdparent():
                painter.setBrush(white)
                circle(0.9 * radius)
            painter.setBrush(fillcolor)
            circle(0.5 * radius)

        painter.end()
        return QVariant(pix)

    def invalidateCache(self):
        self._cache = []
        for a in ('_roleoffsets',):
            if hasattr(self, a):
                delattr(self, a)

    @propertycache
    def _roleoffsets(self):
        return {Qt.DisplayRole : 0,
                Qt.ForegroundRole : len(self._columns),
                Qt.DecorationRole : len(self._columns) * 2}

    def data(self, index, role):
        if not index.isValid():
            return nullvariant
        if role in self._roleoffsets:
            offset = self._roleoffsets[role]
        else:
            return nullvariant
        row = index.row()
        self.ensureBuilt(row=row)
        graphlen = len(self.graph)
        cachelen = len(self._cache)
        if graphlen > cachelen:
            self._cache.extend([None,] * (graphlen-cachelen))
        data = self._cache[row]
        if data is None:
            data = [None,] * (self._roleoffsets[Qt.DecorationRole]+1)
        column = self._columns[index.column()]
        if role == Qt.DecorationRole:
            if column != 'Graph':
                return nullvariant
            if data[offset] is None:
                gnode = self.graph[row]
                ctx = self.repo.changectx(gnode.rev)
                data[offset] = self.graphctx(ctx, gnode)
                self._cache[row] = data
            return data[offset]
        else:
            idx = index.column() + offset
            if data[idx] is None:
                try:
                    result = self.rawdata(row, column, role)
                except util.Abort:
                    result = nullvariant
                data[idx] = result
                self._cache[row] = data
            return data[idx]

    def rawdata(self, row, column, role):
        gnode = self.graph[row]
        ctx = self.repo.changectx(gnode.rev)

        if role == Qt.DisplayRole:
            text = self._columnmap[column](ctx, gnode)
            if not isinstance(text, (QString, unicode)):
                text = hglib.tounicode(text)
            return QVariant(text)
        elif role == Qt.ForegroundRole:
            if ctx.thgmqunappliedpatch():
                return QColor(UNAPPLIED_PATCH_COLOR)
            if column == 'Author':
                if self.authorcolor:
                    return QVariant(QColor(self.user_color(ctx.user())))
                return nullvariant
            if column == 'Branch':
                return QVariant(QColor(self.namedbranch_color(ctx.branch())))
        return nullvariant

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlags(0)
        if not self.revset:
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled

        row = index.row()
        self.ensureBuilt(row=row)
        gnode = self.graph[row]
        ctx = self.repo.changectx(gnode.rev)

        if ctx.rev() not in self.revset:
            return Qt.ItemFlags(0)
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled

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
        if self.graph is None:
            return None
        self.ensureBuilt(rev=rev)
        row = self.rowFromRev(rev)
        if row is not None:
            return self.index(row, 0)
        return None

    def clear(self):
        'empty the list'
        self.graph = None
        self.datacache = {}
        self.layoutChanged.emit()

    def getbranch(self, ctx, gnode):
        b = hglib.tounicode(ctx.branch())
        if ctx.extra().get('close'):
            if self.unicodexinabox:
                b += u' \u2327'
            else:
                b += u'--'
        return b

    def gettags(self, ctx, gnode):
        if ctx.rev() is None:
            return ''
        tags = [t for t in ctx.tags() if t not in self._mqtags]
        return hglib.tounicode(','.join(tags))

    def getrev(self, ctx, gnode):
        rev = ctx.rev()
        if type(rev) is int:
            return str(rev)
        elif rev is None:
            return u'%d+' % ctx.p1().rev()
        else:
            return ''

    def getauthor(self, ctx, gnode):
        try:
            return hglib.username(ctx.user())
        except error.Abort:
            return _('Mercurial User')

    def getlog(self, ctx, gnode):
        if ctx.rev() is None:
            if self.unicodestar:
                # The Unicode symbol is a black star:
                return u'\u2605 ' + _('Working Directory') + u' \u2605'
            else:
                return '*** ' + _('Working Directory') + ' ***'

        msg = ctx.longsummary()

        if ctx.thgmqunappliedpatch():
            effects = qtlib.geteffect('log.unapplied_patch')
            text = qtlib.applyeffects(' %s ' % ctx._patchname, effects)
            # qtlib.markup(msg, fg=UNAPPLIED_PATCH_COLOR)
            msg = qtlib.markup(msg)
            return hglib.tounicode(text + ' ' + msg)

        parts = []
        if ctx.thgbranchhead():
            branchu = hglib.tounicode(ctx.branch())
            effects = qtlib.geteffect('log.branch')
            parts.append(qtlib.applyeffects(u' %s ' % branchu, effects))

        for mark in ctx.bookmarks():
            style = 'log.bookmark'
            if mark == self.repo._bookmarkcurrent:
                bn = self.repo._bookmarks[self.repo._bookmarkcurrent]
                if bn in self.repo.dirstate.parents():
                    style = 'log.curbookmark'
            marku = hglib.tounicode(mark)
            effects = qtlib.geteffect(style)
            parts.append(qtlib.applyeffects(u' %s ' % marku, effects))

        for tag in ctx.thgtags():
            if self.repo.thgmqtag(tag):
                style = 'log.patch'
            else:
                style = 'log.tag'
            tagu = hglib.tounicode(tag)
            effects = qtlib.geteffect(style)
            parts.append(qtlib.applyeffects(u' %s ' % tagu, effects))

        if msg:
            if ctx.thgwdparent():
                msg = qtlib.markup(msg, weight='bold')
            else:
                msg = qtlib.markup(msg)
            parts.append(hglib.tounicode(msg))

        return ' '.join(parts)

    def getchanges(self, ctx, gnode):
        """Return the MAR status for the given ctx."""
        changes = []
        M, A, R = ctx.changesToParent(0)
        def addtotal(files, style):
            effects = qtlib.geteffect(style)
            text = qtlib.applyeffects(' %s ' % len(files), effects)
            changes.append(text)
        if M:
            addtotal(M, 'log.modified')
        if A:
            addtotal(A, 'log.added')
        if R:
            addtotal(R, 'log.removed')
        return ''.join(changes)

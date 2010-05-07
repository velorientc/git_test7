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

from mercurial import error

from tortoisehg.util.util import tounicode, Curry

from tortoisehg.hgqt.graph import Graph
from tortoisehg.hgqt.graph import revision_grapher
from tortoisehg.hgqt.config import HgConfig
from tortoisehg.hgqt import icon as geticon

from PyQt4 import QtCore, QtGui
connect = QtCore.QObject.connect
SIGNAL = QtCore.SIGNAL
nullvariant = QtCore.QVariant()

# XXX make this better than a poor hard written list...
COLORS = [ "blue", "darkgreen", "red", "green", "darkblue", "purple",
           "cyan", QtCore.Qt.darkYellow, "magenta", "darkred", "darkmagenta",
           "darkcyan", "gray", "yellow", ]
COLORS = [str(QtGui.QColor(x).name()) for x in COLORS]
#COLORS = [str(color) for color in QtGui.QColor.colorNames()]

def get_color(n, ignore=()):
    """
    Return a color at index 'n' rotating in the available
    colors. 'ignore' is a list of colors not to be chosen.
    """
    ignore = [str(QtGui.QColor(x).name()) for x in ignore]
    colors = [x for x in COLORS if x not in ignore]
    if not colors: # ghh, no more available colors...
        colors = COLORS
    return colors[n % len(colors)]

def cvrt_date(date):
    """
    Convert a date given the hg way, ie. couple (date, tz), into a
    formatted QString
    """
    date, tzdelay = date
    return QtCore.QDateTime.fromTime_t(int(date)).toString(QtCore.Qt.LocaleDate)

def gettags(model, ctx, gnode):
    if ctx.rev() is None:
        return ""
    mqtags = ['qbase', 'qtip', 'qparent']
    tags = ctx.tags()
    if model.hide_mq_tags:
        tags = [t for t in tags if t not in mqtags]
    return ",".join(tags)

def getlog(model, ctx, gnode):
    if ctx.rev() is not None:
        msg = tounicode(ctx.description())
        if msg:
            msg = msg.splitlines()[0]
    else:
        msg = "WORKING DIRECTORY (locally modified)"
    return msg

# XXX maybe it's time to make these methods of the model...
# in following lambdas, ctx is a hg changectx
_columnmap = {'ID': lambda model, ctx, gnode: ctx.rev() is not None and str(ctx.rev()) or "",
              'Log': getlog,
              'Author': lambda model, ctx, gnode: tounicode(ctx.user()),
              'Date': lambda model, ctx, gnode: cvrt_date(ctx.date()),
              'Tags': gettags,
              'Branch': lambda model, ctx, gnode: ctx.branch(),
              'Filename': lambda model, ctx, gnode: gnode.extra[0],
              }

_tooltips = {'ID': lambda model, ctx,
                   gnode: ctx.rev() is not None and ctx.hex() or "Working Directory",
             }

# in following lambdas, r is a hg repo
_maxwidth = {'ID': lambda self, r: str(len(r.changelog)),
             'Date': lambda self, r: cvrt_date(r.changectx(0).date()),
             'Tags': lambda self, r: sorted(r.tags().keys(),
                                            key=lambda x: len(x))[-1][:10],
             'Branch': lambda self, r: sorted(r.branchtags().keys(),
                                              key=lambda x: len(x))[-1],
             'Author': lambda self, r: 'author name',
             'Filename': lambda self, r: self.filename,
             }

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
        if (row, col, role) in self._datacache:
            return self._datacache[(row, col, role)]
        result = meth(self, index, role)
        if result is not nullvariant:
            self._datacache[(row, col, role)] = result
        return result
    return data

class HgRepoListModel(QtCore.QAbstractTableModel):
    """
    Model used for displaying the revisions of a Hg *local* repository
    """
    _allcolumns = ('ID', 'Branch', 'Log', 'Author', 'Date', 'Tags',)
    _columns = ('ID', 'Branch', 'Log', 'Author', 'Date', 'Tags',)
    _stretchs = {'Log': 1, }
    _getcolumns = "getChangelogColumns"

    def __init__(self, repo, branch='', fromhead=None, follow=False, parent=None):
        """
        repo is a hg repo instance
        """
        QtCore.QAbstractTableModel.__init__(self, parent)
        self._datacache = {}
        self._hasmq = False
        self.mqueues = []
        self.wd_revs = []
        self.graph = None
        self._fill_timer = None
        self.rowcount = 0
        self.repo = repo
        self.load_config()
        self.setRepo(repo, branch=branch, fromhead=fromhead, follow=follow)

    def setRepo(self, repo, branch='', fromhead=None, follow=False):
        oldrepo = self.repo
        self.repo = repo
        if oldrepo.root != repo.root:
            self.load_config()
        self._datacache = {}
        try:
            wdctxs = self.repo.changectx(None).parents()
        except error.Abort:
            # might occur if reloading during a mq operation (or
            # whatever operation playing with hg history)
            return
        self._hasmq = hasattr(self.repo, "mq")
        if self._hasmq:
            self.mqueues = self.repo.mq.series[:]
        self.wd_revs = [ctx.rev() for ctx in wdctxs]
        self.wd_status = [self.repo.status(ctx.node(), None)[:4] for ctx in wdctxs]
        self._user_colors = {}
        self._branch_colors = {}
        grapher = revision_grapher(self.repo, start_rev=fromhead,
                                   follow=follow, branch=branch)
        self.graph = Graph(self.repo, grapher, self.max_file_size)
        self.rowcount = 0
        self.emit(SIGNAL('layoutChanged()'))
        self.heads = [self.repo.changectx(x).rev() for x in self.repo.heads()]
        self.ensureBuilt(row=self.fill_step)
        QtCore.QTimer.singleShot(0, Curry(self.emit, SIGNAL('filled')))
        self._fill_timer = self.startTimer(50)

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
        if event.timerId() == self._fill_timer:
            self.emit(SIGNAL('showMessage'), 'filling (%s)'%(len(self.graph)))
            if self.graph.isfilled():
                self.killTimer(self._fill_timer)
                self._fill_timer = None
                self.emit(SIGNAL('showMessage'), '')
                self.emit(SIGNAL('loaded'))
            # we only fill the graph data strctures without telling
            # views (until we atually did the full job), to keep
            # maximal GUI reactivity
            elif not self.graph.build_nodes(nnodes=self.fill_step):
                self.killTimer(self._fill_timer)
                self._fill_timer = None
                self.updateRowCount()
                self.emit(SIGNAL('showMessage'), '')
                self.emit(SIGNAL('loaded'))

    def updateRowCount(self):
        currentlen = self.rowcount
        newlen = len(self.graph)
        if newlen > self.rowcount:
            self.beginInsertRows(QtCore.QModelIndex(), currentlen, newlen-1)
            self.rowcount = newlen
            self.endInsertRows()

    def rowCount(self, parent=None):
        return self.rowcount

    def columnCount(self, parent=None):
        return len(self._columns)

    def load_config(self):
        cfg = HgConfig(self.repo.ui)
        self._users, self._aliases = cfg.getUsers()
        self.dot_radius = cfg.getDotRadius(default=8)
        self.rowheight = cfg.getRowHeight()
        self.fill_step = cfg.getFillingStep()
        self.max_file_size = cfg.getMaxFileSize()
        self.hide_mq_tags = cfg.getMQHideTags()
        
        cols = getattr(cfg, self._getcolumns)()
        if cols is not None:
            validcols = [col for col in cols if col in self._allcolumns]
            if len(validcols) != len(cols):
                wrongcols = [col for col in cols if col not in self._allcolumns]
                print "WARNING! %s are not valid column names. Check your configuration." % ','.join(wrongcols)
                print "         reverting to default columns configuration"
            elif 'Log' not in validcols or 'ID' not in validcols:
                print "WARNING! 'Log' and 'ID' are mandatory. Check your configuration."
                print "         reverting to default columns configuration"
            else:
                self._columns = tuple(validcols)

    def maxWidthValueForColumn(self, column):
        column = self._columns[column]
        if column in _maxwidth:
            return _maxwidth[column](self, self.repo)
        return None

    def user_color(self, user):
        if user in self._aliases:
            user = self._aliases[user]
        if user in self._users:
            try:
                color = self._users[user]['color']
                color = QtGui.QColor(color).name()
                self._user_colors[user] = color
            except:
                pass
        if user not in self._user_colors:
            self._user_colors[user] = get_color(len(self._user_colors),
                                                self._user_colors.values())
        return self._user_colors[user]

    def user_name(self, user):
        return self._aliases.get(user, user)

    def namedbranch_color(self, branch):
        if branch not in self._branch_colors:
            self._branch_colors[branch] = get_color(len(self._branch_colors))
        return self._branch_colors[branch]

    def col2x(self, col):
        return (1.2*self.dot_radius + 0) * col + self.dot_radius/2 + 3

    @datacached
    def data(self, index, role):
        if not index.isValid():
            return nullvariant
        row = index.row()
        self.ensureBuilt(row=row)
        column = self._columns[index.column()]
        gnode = self.graph[row]
        ctx = self.repo.changectx(gnode.rev)
        if role == QtCore.Qt.DisplayRole:
            if column == 'Author': #author
                return QtCore.QVariant(self.user_name(_columnmap[column](self, ctx, gnode)))
            elif column == 'Log':
                msg = _columnmap[column](self, ctx, gnode)
                return QtCore.QVariant(msg)
            return QtCore.QVariant(_columnmap[column](self, ctx, gnode))
        elif role == QtCore.Qt.ToolTipRole:
            msg = "<b>Branch:</b> %s<br>\n" % ctx.branch()
            if gnode.rev in self.wd_revs:
                msg += " <i>Working Directory position"
                states = 'modified added removed deleted'.split()
                status = self.wd_status[self.wd_revs.index(gnode.rev)]
                status = [state for st, state in zip(status, states) if st]
                if status:
                    msg += ' (%s)' % (', '.join(status))
                msg += "</i><br>\n"
            msg += _tooltips.get(column, _columnmap[column])(self, ctx, gnode)
            return QtCore.QVariant(msg)
        elif role == QtCore.Qt.ForegroundRole:
            if column == 'Author': #author
                return QtCore.QVariant(QtGui.QColor(self.user_color(ctx.user())))
            if column == 'Branch': #branch
                return QtCore.QVariant(QtGui.QColor(self.namedbranch_color(ctx.branch())))
        elif role == QtCore.Qt.DecorationRole:
            if column == 'Log':
                radius = self.dot_radius
                w = (gnode.cols)*(1*radius + 0) + 20
                h = self.rowheight

                dot_x = self.col2x(gnode.x) - radius / 2
                dot_y = h / 2

                pix = QtGui.QPixmap(w, h)
                pix.fill(QtGui.QColor(0,0,0,0))
                painter = QtGui.QPainter(pix)
                painter.setRenderHint(QtGui.QPainter.Antialiasing)

                pen = QtGui.QPen(QtCore.Qt.blue)
                pen.setWidth(2)
                painter.setPen(pen)

                lpen = QtGui.QPen(pen)
                lpen.setColor(QtCore.Qt.black)
                painter.setPen(lpen)

                for y1, y2, lines in ((0, h, gnode.bottomlines),
                                      (-h, 0, gnode.toplines)):
                    for start, end, color in lines:
                        lpen = QtGui.QPen(pen)
                        lpen.setColor(QtGui.QColor(get_color(color)))
                        lpen.setWidth(2)
                        painter.setPen(lpen)
                        x1 = self.col2x(start)
                        x2 = self.col2x(end)
                        painter.drawLine(x1, dot_y + y1, x2, dot_y + y2)

                dot_color = QtGui.QColor(self.namedbranch_color(ctx.branch()))
                dotcolor = QtGui.QColor(dot_color)
                if gnode.rev in self.heads:
                    penradius = 2
                    pencolor = dotcolor.darker()
                else:
                    penradius = 1
                    pencolor = QtCore.Qt.black

                dot_y = (h/2) - radius / 2

                painter.setBrush(dotcolor)
                pen = QtGui.QPen(pencolor)
                pen.setWidth(penradius)
                painter.setPen(pen)
                tags = set(ctx.tags())
                icn = None

                modified = False
                atwd = False
                if gnode.rev in self.wd_revs:
                    atwd = True
                    status = self.wd_status[self.wd_revs.index(gnode.rev)]
                    if [True for st in status if st]:
                        modified = True

                if gnode.rev is None:
                    # WD is displayed only if there are local
                    # modifications, so let's use the modified icon
                    icn = geticon('modified')
                elif tags.intersection(self.mqueues):
                    icn = geticon('mqpatch')
                #elif modified:
                #    icn = geticon('modified')
                elif atwd:
                    icn = geticon('clean')

                if icn:
                    icn.paint(painter, dot_x-5, dot_y-5, 17, 17)
                else:
                    painter.drawEllipse(dot_x, dot_y, radius, radius)
                painter.end()
                ret = QtCore.QVariant(pix)
                return ret
        return nullvariant

    def headerData(self, section, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return QtCore.QVariant(self._columns[section])
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
        """empty the list"""
        self.graph = None
        self._datacache = {}
        self.notify_data_changed()

    def notify_data_changed(self):
        self.emit(SIGNAL("layoutChanged()"))

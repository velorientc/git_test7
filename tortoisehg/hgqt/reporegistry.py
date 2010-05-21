# reporegistry.py - registry for a user's repositories
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import sys
import os

from PyQt4 import QtCore, QtGui

from PyQt4.QtCore import Qt, QVariant, SIGNAL, SLOT
from PyQt4.QtCore import QModelIndex, QString

from PyQt4.QtGui import QWidget, QVBoxLayout

from tortoisehg.hgqt.i18n import _

connect = QtCore.QObject.connect

extractXmlElementName = 'reporegextract'
repoRegMimeType = 'application/thg-reporegistry'

class RepoTreeItem:
    def __init__(self, parent=None):
        self._parent = parent
        self.childs = []
        self._row = 0

    def appendChild(self, child):
        child._row = len(self.childs)
        child._parent = self
        self.childs.append(child)

    def child(self, row):
        return self.childs[row]

    def childCount(self):
        return len(self.childs)

    def columnCount(self):
        return 2

    def data(self, column):
        return QVariant()

    def row(self):
        return self._row

    def parent(self):
        return self._parent

    def menulist(self):
        return []

    def flags(self):
        return Qt.NoItemFlags

    def removeRows(self, row, count):
        cs = self.childs
        remove = cs[row : row + count]
        keep = cs[:row] + cs[row + count:]
        self.childs = keep
        for c in remove:
            c._row = 0
            c._parent = QModelIndex()
        for i, c in enumerate(keep):
            c._row = i        
        return True

    def dump(self, xw):
        for c in self.childs:
            c.dumpObject(xw)

    def undump(self, xr):
        print "RepoTreeItem.undump()"
        while not xr.atEnd():
            xr.readNext()
            if xr.isStartElement():
                item = undumpObject(xr)
                self.appendChild(item)
                xr.skipCurrentElement()
            elif xr.isEndElement():
                break

    def dumpObject(self, xw):
        xw.writeStartElement(self.__class__.__name__)
        self.dump(xw)
        xw.writeEndElement()


def encodeToXml(item, rootElementName):
    buf = QtCore.QByteArray()
    xw = QtCore.QXmlStreamWriter(buf)
    xw.setAutoFormatting(True)
    xw.setAutoFormattingIndent(2)
    xw.writeStartDocument()
    xw.writeStartElement(rootElementName)
    item.dumpObject(xw)
    xw.writeEndElement()
    xw.writeEndDocument()
    return buf


def undumpObject(xr):
    print "undumpObject()"
    classname = str(xr.name().toString())
    print "classname = %s" % classname
    class_ = getattr(sys.modules[RepoTreeItem.__module__], classname)
    obj = class_()
    obj.undump(xr)
    return obj


class RepoItem(RepoTreeItem):
    def __init__(self, rootpath='', parent=None):
        RepoTreeItem.__init__(self, parent)
        self._root = rootpath
        
    def rootpath(self):
        return self._root

    def data(self, column):
        if column == 0:
            return QVariant(os.path.basename(self._root))
        elif column == 1:
            return QVariant(self._root)
        return QVariant()

    def menulist(self):
        return ['open']

    def flags(self):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled

    def removeRows(self, row, count):
        return False

    def dump(self, xw):
        RepoTreeItem.dump(self, xw)
        xw.writeAttribute('root', self._root)

    def undump(self, xr):
        print "RepoItem.undump()"
        a = xr.attributes()
        self._root = str(a.value('', 'root').toString())
        print "self._root = %s" % self._root
        RepoTreeItem.undump(self, xr)
        print "RepoItem.undump() finished"


class RepoGroupItem(RepoTreeItem):
    def __init__(self, name, parent=None):
        RepoTreeItem.__init__(self, parent)
        self.name = name

    def data(self, column):
        if column == 0:
            return QVariant(self.name)
        return QVariant()

    def menulist(self):
        return ['newGroup']

    def flags(self):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDropEnabled

    def dump(self, xw):
        xw.writeAttribute('name', self.name)
        RepoTreeItem.dump(self, xw)

    def undump(self, xr):
        print "RepoGroupItem.undump()"
        a = xr.attributes()
        self.name = str(a.value('', 'name').toString())
        print "self.name = %s" % self.name
        RepoTreeItem.undump(self, xr)


class RepoTreeModel(QtCore.QAbstractItemModel):
    def __init__(self, parent=None):
        QtCore.QAbstractItemModel.__init__(self, parent)

        self.rootItem = root = RepoTreeItem()

        self.allrepos = all = RepoGroupItem(_('All Repositories'))
        root.appendChild(all)

    # see http://doc.qt.nokia.com/4.6/model-view-model-subclassing.html

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if (not parent.isValid()):
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()
        childItem = parentItem.child(row)
        if childItem:
            return self.createIndex(row, column, childItem)
        else:
            return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        childItem = index.internalPointer()
        parentItem = childItem.parent()
        if parentItem is self.rootItem:
            return QModelIndex()
        return self.createIndex(parentItem.row(), 0, parentItem)

    def rowCount(self, parent):
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            parentItem = self.rootItem;
        else:
            parentItem = parent.internalPointer()
        return parentItem.childCount()
 
    def columnCount(self, parent):
        if parent.isValid():
            return parent.internalPointer().columnCount()
        else:
            return self.rootItem.columnCount()

    def data(self, index, role):
        if not index.isValid():
            return QVariant()
        if role != Qt.DisplayRole:
            return QVariant();
        item = index.internalPointer()
        return item.data(index.column())

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                if section == 1:
                    return QString(_('Path'))
        return QVariant()

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        item = index.internalPointer()
        return item.flags()

    def supportedDropActions(self):
        return Qt.MoveAction

    def removeRows(self, row, count, parent):
        print "removeRows()"
        self.beginRemoveRows(parent, row, row+count)
        item = parent.internalPointer()
        res = item.removeRows(row, count)
        self.endRemoveRows()

        # dump everything for debug purposes
        all = encodeToXml(self.rootItem, 'reporegistry')
        print all

        return res

    def mimeTypes(self):
        return QtCore.QStringList(repoRegMimeType)

    def mimeData(self, indexes):
        print "mimeData()"
        i = indexes[0]
        item = i.internalPointer()
        buf = encodeToXml(item, extractXmlElementName)
        print str(buf)
        d = QtCore.QMimeData()
        d.setData(repoRegMimeType, buf)
        return d

    def dropMimeData(self, data, action, row, column, parent):
        print "dropMimeData()"
        print "action = %s" % action
        print "formats:"
        for s in data.formats():
            print s
        d = str(data.data(repoRegMimeType))
        print "d = %s" % d

        xr = QtCore.QXmlStreamReader(d)
        if xr.readNextStartElement():
            ele = str(xr.name().toString())
            if ele != extractXmlElementName:
                print "unexpected xml element '%s' "\
                      "(was looking for %s)" % (ele, extractXmlElementName)
                return
        if xr.hasError():
            print str(xr.errorString())
        if xr.readNextStartElement():
            itemread = undumpObject(xr)
            xr.skipCurrentElement()
        if xr.hasError():
            print str(xr.errorString())

        print "itemread = %s" % itemread

        group = parent.internalPointer()
        cc = group.childCount()
        self.beginInsertRows(parent, cc, cc)
        group.appendChild(itemread)
        self.endInsertRows()
        return True

    # functions not defined in QAbstractItemModel

    def allreposIndex(self):
        return self.createIndex(0, 0, self.allrepos)

    def addRepo(self, reporoot):
        all = self.allrepos
        cc = all.childCount()
        self.beginInsertRows(self.allreposIndex(), cc, cc + 1)
        all.appendChild(RepoItem(reporoot))
        self.endInsertRows()

    def getRepoItem(self, reporoot):
        for c in self.allrepos.childs:
            if c.rootpath() == reporoot:
                return c
        return None

    def addGroup(self, name):
        ri = self.rootItem
        cc = ri.childCount()
        self.beginInsertRows(QModelIndex(), cc, cc + 1)
        ri.appendChild(RepoGroupItem(name, ri))
        self.endInsertRows()


class RepoTreeView(QtGui.QTreeView):
    def __init__(self, parent):
        QtGui.QTreeView.__init__(self)
        self.parent = parent
        self.selitem = None

        # enable drag and drop
        # (see http://doc.qt.nokia.com/4.6/model-view-dnd.html)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QtGui.QAbstractItemView.InternalMove)
        self.setDropIndicatorShown(True)

        self.createActions()

    def contextMenuEvent(self, event):
        selection = self.selectedIndexes()
        if len(selection) == 0:
            return
        self.selitem = selection[0].internalPointer()
        menulist = self.selitem.menulist()
        if len(menulist) > 0:
            menu = QtGui.QMenu(self)
            for act in menulist:
                if act:
                    menu.addAction(self._actions[act])
                else:
                    menu.addSeparator()
            menu.exec_(event.globalPos())

    def _action_defs(self):
        a = [("open", _("Open"), None, 
                _("Opens the repository in a new tab"), None, self.open),
             ("newGroup", _("New Group"), None, 
                _("Create a new group"), None, self.newGroup),
             ]
        return a

    def createActions(self):
        self._actions = {}
        for name, desc, icon, tip, key, cb in self._action_defs():
            self._actions[name] = QtGui.QAction(desc, self)
        QtCore.QTimer.singleShot(0, self.configureActions)

    def configureActions(self):
        for name, desc, icon, tip, key, cb in self._action_defs():
            act = self._actions[name]
            '''
            if icon:
                act.setIcon(geticon(icon))
            '''
            if tip:
                act.setStatusTip(tip)
            if key:
                act.setShortcut(key)
            if cb:
                connect(act, SIGNAL('triggered()'), cb)
            self.addAction(act)

    def open(self):
        self.parent.openrepo(self.selitem.rootpath())

    def newGroup(self):
        m = self.model()
        m.addGroup(_('New Group'))


class RepoRegistryView(QWidget):

    openRepoSignal = QtCore.pyqtSignal(QtCore.QString)

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)

        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        self.setLayout(lay)

        self.tmodel = m = RepoTreeModel()

        self.tview = tv = RepoTreeView(self)
        lay.addWidget(tv)
        tv.setModel(m)

        tv.setIndentation(10)
        tv.setFirstColumnSpanned(0, QModelIndex(), True)

        self.tview.setColumnHidden(1, True)
        QtCore.QTimer.singleShot(0, self.expand)

    def expand(self):
        self.tview.expandToDepth(0)

    def addRepo(self, reporoot):
        m = self.tmodel
        if m.getRepoItem(reporoot) == None:
            m.addRepo(reporoot)

    def openrepo(self, path):
        self.openRepoSignal.emit(path)

    def showPaths(self, show):
        self.tview.setColumnHidden(1, not show)
        if show:
            self.tview.resizeColumnToContents(0)
            self.tview.resizeColumnToContents(1)

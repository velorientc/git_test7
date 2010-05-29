# reporegistry.py - registry for a user's repositories
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import sys
import os

from mercurial import hg

from PyQt4 import QtCore, QtGui

from PyQt4.QtCore import Qt, QVariant, SIGNAL, SLOT
from PyQt4.QtCore import QModelIndex, QString

from PyQt4.QtGui import QVBoxLayout, QDockWidget, QFrame

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.qtlib import geticon

from settings import SettingsDialog

connect = QtCore.QObject.connect


extractXmlElementName = 'reporegextract'
reporegistryXmlElementName = 'reporegistry'

repoRegMimeType = 'application/thg-reporegistry'

xmlClassMap = {
      'allgroup': 'AllRepoGroupItem',
      'group': 'RepoGroupItem',
      'repo': 'RepoItem',
      'treeitem': 'RepoTreeItem',
      'paths': 'RepoPathsItem',
      'path': 'RepoPathItem',
    }

inverseXmlClassMap = {}

def xmlToClass(ele):
    return xmlClassMap[ele]

def classToXml(classname):
    if len(inverseXmlClassMap) == 0:
        for k,v in xmlClassMap.iteritems():
            inverseXmlClassMap[v] = k
    return inverseXmlClassMap[classname]

def settingsfilename():
    s = QtCore.QSettings()
    dir = os.path.dirname(str(s.fileName()))
    return dir + '/' + 'thg-reporegistry.xml'

def writeXml(target, item, rootElementName):
    xw = QtCore.QXmlStreamWriter(target)
    xw.setAutoFormatting(True)
    xw.setAutoFormattingIndent(2)
    xw.writeStartDocument()
    xw.writeStartElement(rootElementName)
    item.dumpObject(xw)
    xw.writeEndElement()
    xw.writeEndDocument()

def readXml(source, rootElementName, model):
    itemread = None
    xr = QtCore.QXmlStreamReader(source)
    if xr.readNextStartElement():
        ele = str(xr.name().toString())
        if ele != rootElementName:
            print "unexpected xml element '%s' "\
                  "(was looking for %s)" % (ele, rootElementName)
            return
    if xr.hasError():
        print str(xr.errorString())
    if xr.readNextStartElement():
        itemread = undumpObject(xr, model)
        xr.skipCurrentElement()
    if xr.hasError():
        print str(xr.errorString())
    return itemread

def undumpObject(xr, model):
    classname = xmlToClass(str(xr.name().toString()))
    class_ = getattr(sys.modules[RepoTreeItem.__module__], classname)
    obj = class_(model)
    obj.undump(xr)
    return obj


class RepoTreeItem:
    def __init__(self, model, parent=None):
        self.model = model
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

    def data(self, column, role):
        return QVariant()

    def setData(self, column, value):
        return False

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
            c._parent = None
        for i, c in enumerate(keep):
            c._row = i        
        return True

    def dump(self, xw):
        for c in self.childs:
            c.dumpObject(xw)

    def undump(self, xr):
        while not xr.atEnd():
            xr.readNext()
            if xr.isStartElement():
                item = undumpObject(xr, self.model)
                self.appendChild(item)
            elif xr.isEndElement():
                break

    def dumpObject(self, xw):
        xw.writeStartElement(classToXml(self.__class__.__name__))
        self.dump(xw)
        xw.writeEndElement()

    def open(self):
        pass


class RepoItem(RepoTreeItem):
    def __init__(self, model, rootpath='', parent=None):
        RepoTreeItem.__init__(self, model, parent)
        self._root = rootpath
        self._setttingsdlg = None
        if rootpath:
            pi = RepoPathsItem(model)
            self.appendChild(pi)
            repo = hg.repository(model.ui, path=rootpath)
            for alias, path in repo.ui.configitems('paths'):
                item = RepoPathItem(model, alias, path)
                pi.appendChild(item)

    def rootpath(self):
        return self._root

    def data(self, column, role):
        if role == Qt.DecorationRole:
            if column == 0:
                ico = geticon('hg')
                return QVariant(ico)
            return QVariant()
        if column == 0:
            return QVariant(os.path.basename(self._root))
        elif column == 1:
            return QVariant(self._root)
        return QVariant()

    def menulist(self):
        return ['open', 'remove', None, 'settings']

    def flags(self):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled

    def removeRows(self, row, count):
        return False

    def dump(self, xw):
        xw.writeAttribute('root', self._root)
        RepoTreeItem.dump(self, xw)

    def undump(self, xr):
        a = xr.attributes()
        self._root = str(a.value('', 'root').toString())
        RepoTreeItem.undump(self, xr)

    def open(self):
        self.model.openrepofunc(self._root)

    def startSettings(self, parent):
        if self._setttingsdlg is None:
            self._setttingsdlg = SettingsDialog(
                configrepo=True, focus='web.name', parent=parent,
                root=self._root)
        self._setttingsdlg.show()


class RepoPathsItem(RepoTreeItem):
    def __init__(self, model, parent=None):
        RepoTreeItem.__init__(self, model, parent)

    def data(self, column, role):
        if role == Qt.DecorationRole:
            if column == 0:
                s = QtGui.QApplication.style()
                ico = s.standardIcon(QtGui.QStyle.SP_DirIcon)
                return QVariant(ico)
            return QVariant()
        if column == 0:
            return QVariant(_('Paths'))
        return QVariant()

    def setData(self, column, value):
        return False

    def menulist(self):
        return []

    def flags(self):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def dump(self, xw):
        RepoTreeItem.dump(self, xw)

    def undump(self, xr):
        RepoTreeItem.undump(self, xr)


class RepoPathItem(RepoTreeItem):
    def __init__(self, model, alias='', path='', parent=None):
        RepoTreeItem.__init__(self, model, parent)
        self._alias = alias
        self._path = path

    def url(self):
        return self._url

    def data(self, column, role):
        if role == Qt.DecorationRole:
            if column == 0:
                ico = geticon('sync')
                return QVariant(ico)
            return QVariant()
        if column == 0:
            return QVariant(self._alias)
        elif column == 1:
            return QVariant(self._path)
        return QVariant()

    def menulist(self):
        return []

    def flags(self):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled

    def removeRows(self, row, count):
        return False

    def dump(self, xw):
        xw.writeAttribute('alias', self._alias)
        xw.writeAttribute('path', self._path)
        RepoTreeItem.dump(self, xw)

    def undump(self, xr):
        a = xr.attributes()
        self._alias = str(a.value('', 'alias').toString())
        self._path = str(a.value('', 'path').toString())
        RepoTreeItem.undump(self, xr)


class RepoGroupItem(RepoTreeItem):
    def __init__(self, model, name=None, parent=None):
        RepoTreeItem.__init__(self, model, parent)
        if name:
            self.name = name
        else:
            self.name = QString()

    def data(self, column, role):
        if role == Qt.DecorationRole:
            if column == 0:
                s = QtGui.QApplication.style()
                ico = s.standardIcon(QtGui.QStyle.SP_DirIcon)
                return QVariant(ico)
            return QVariant()
        if column == 0:
            return QVariant(self.name)
        return QVariant()

    def setData(self, column, value):
        if column == 0:
            self.name = value.toString()
            return True
        return False

    def menulist(self):
        return ['newGroup', None, 'rename', 'remove']

    def flags(self):
        return (Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDropEnabled
            | Qt.ItemIsEditable)

    def dump(self, xw):
        xw.writeAttribute('name', self.name)
        RepoTreeItem.dump(self, xw)

    def undump(self, xr):
        a = xr.attributes()
        self.name = a.value('', 'name').toString()
        RepoTreeItem.undump(self, xr)


class AllRepoGroupItem(RepoTreeItem):
    def __init__(self, model, parent=None):
        RepoTreeItem.__init__(self, model, parent)

    def data(self, column, role):
        if role == Qt.DecorationRole:
            if column == 0:
                s = QtGui.QApplication.style()
                ico = s.standardIcon(QtGui.QStyle.SP_DirIcon)
                return QVariant(ico)
            return QVariant()
        if column == 0:
            return QVariant(_('all'))
        return QVariant()

    def setData(self, column, value):
        return False

    def menulist(self):
        return ['newGroup']

    def flags(self):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDropEnabled

    def dump(self, xw):
        RepoTreeItem.dump(self, xw)

    def undump(self, xr):
        RepoTreeItem.undump(self, xr)


class RepoTreeModel(QtCore.QAbstractItemModel):
    def __init__(self, openrepofunc, ui, filename=None, parent=None):
        QtCore.QAbstractItemModel.__init__(self, parent)

        self.openrepofunc = openrepofunc
        self.ui = ui

        root = None
        all = None

        if filename:
            f = QtCore.QFile(filename)
            if f.open(QtCore.QIODevice.ReadOnly):
                root = readXml(f, reporegistryXmlElementName, self)
                f.close()
                if root:
                    for c in root.childs:
                        if isinstance(c, AllRepoGroupItem):
                            all = c
                            break

        if not root:
            root = RepoTreeItem(self)
            all = AllRepoGroupItem(self)
            root.appendChild(all)

        self.rootItem = root
        self.allrepos = all

    # see http://doc.qt.nokia.com/4.6/model-view-model-subclassing.html

    # overrides from QAbstractItemModel

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
        if (role != Qt.DisplayRole 
                and role != Qt.EditRole and role != Qt.DecorationRole):
            return QVariant()
        item = index.internalPointer()
        return item.data(index.column(), role)

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
        item = parent.internalPointer()
        if item is None:
            item = self.rootItem
        self.beginRemoveRows(parent, row, row+count-1)
        res = item.removeRows(row, count)
        self.endRemoveRows()
        return res

    def mimeTypes(self):
        return QtCore.QStringList(repoRegMimeType)

    def mimeData(self, indexes):
        i = indexes[0]
        item = i.internalPointer()
        buf = QtCore.QByteArray()
        writeXml(buf, item, extractXmlElementName)
        d = QtCore.QMimeData()
        d.setData(repoRegMimeType, buf)
        return d

    def dropMimeData(self, data, action, row, column, parent):
        d = str(data.data(repoRegMimeType))
        itemread = readXml(d, extractXmlElementName, self)

        group = parent.internalPointer()
        cc = group.childCount()
        self.beginInsertRows(parent, cc, cc)
        group.appendChild(itemread)
        self.endInsertRows()
        return True

    def setData(self, index, value, role):
        if not index.isValid() or role != Qt.EditRole:
            return False
        s = value.toString()
        if s.isEmpty():
            return False
        item = index.internalPointer()
        if item.setData(index.column(), value):
            self.emit(SIGNAL('dataChanged(index, index)'), index, index)
            return True
        return False

    # functions not defined in QAbstractItemModel

    def allreposIndex(self):
        return self.createIndex(0, 0, self.allrepos)

    def addRepo(self, reporoot):
        all = self.allrepos
        cc = all.childCount()
        self.beginInsertRows(self.allreposIndex(), cc, cc + 1)
        all.appendChild(RepoItem(self, reporoot))
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

    def write(self, fn):
        f = QtCore.QFile(fn)
        f.open(QtCore.QIODevice.WriteOnly)
        writeXml(f, self.rootItem, reporegistryXmlElementName)
        f.close()


class RepoTreeView(QtGui.QTreeView):
    def __init__(self, parent):
        QtGui.QTreeView.__init__(self)
        self.parent = parent
        self.selitem = None

        self.setExpandsOnDoubleClick(False)

        # enable drag and drop
        # (see http://doc.qt.nokia.com/4.6/model-view-dnd.html)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QtGui.QAbstractItemView.DragDrop)
        self.setDropIndicatorShown(True)

        self.createActions()

    def contextMenuEvent(self, event):
        menulist = self.selitem.internalPointer().menulist()
        if len(menulist) > 0:
            menu = QtGui.QMenu(self)
            for act in menulist:
                if act:
                    menu.addAction(self._actions[act])
                else:
                    menu.addSeparator()
            menu.exec_(event.globalPos())

    def mouseDoubleClickEvent(self, event):
        self.open()

    def selectionChanged(self, selected, deselected):
        selection = self.selectedIndexes()
        if len(selection) == 0:
            self.selitem = None
        else:
            self.selitem = selection[0]       

    def _action_defs(self):
        a = [("open", _("Open"), None, 
                _("Opens the repository in a new tab"), None, self.open),
             ("newGroup", _("New Group"), None, 
                _("Create a new group"), None, self.newGroup),
             ("rename", _("Rename"), None, 
                _("Rename the entry"), None, self.startRename),
             ("settings", _("Settings"), None, 
                _("View the repository's settings"), None, self.startSettings),
             ("remove", _("Remove entry"), None, 
                _("Remove the entry"), None, self.removeSelected),
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

    def startSettings(self):
        if not self.selitem:
            return
        self.selitem.internalPointer().startSettings(self.parent)

    def startRename(self):
        if not self.selitem:
            return
        self.edit(self.selitem)

    def open(self):
        if not self.selitem:
            return
        self.selitem.internalPointer().open()

    def newGroup(self):
        m = self.model()
        m.addGroup(_('New Group'))

    def removeSelected(self):
        if not self.selitem:
            return
        m = self.model()
        s = self.selitem
        row = s.row()
        parent = s.parent()
        m.removeRows(row, 1, parent)


class RepoRegistryView(QDockWidget):

    openRepoSignal = QtCore.pyqtSignal(QtCore.QString)
    visibilityChanged = QtCore.pyqtSignal(bool)

    def __init__(self, ui, parent):
        QDockWidget.__init__(self, parent)

        self.setFeatures(QDockWidget.DockWidgetClosable |
                         QDockWidget.DockWidgetMovable  |
                         QDockWidget.DockWidgetFloatable)
        self.setWindowTitle(_('Repository Registry'))

        mainframe = QFrame()
        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        mainframe.setLayout(lay)
        self.setWidget(mainframe)

        self.tmodel = m = RepoTreeModel(self.openrepo, ui, settingsfilename())

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

    def close(self):
        self.tmodel.write(settingsfilename())

    def showEvent(self, event):
        self.visibilityChanged.emit(True)

    def hideEvent(self, event):
        self.visibilityChanged.emit(False)

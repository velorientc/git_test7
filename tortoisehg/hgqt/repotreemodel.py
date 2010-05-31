# repotreemodel.py - model for the reporegistry
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

from PyQt4 import QtCore

from PyQt4.QtCore import Qt, QVariant, SIGNAL, SLOT
from PyQt4.QtCore import QModelIndex, QString

from tortoisehg.hgqt.i18n import _

from repotreeitem import undumpObject, AllRepoGroupItem, RepoGroupItem, RepoItem


extractXmlElementName = 'reporegextract'
reporegistryXmlElementName = 'reporegistry'

repoRegMimeType = 'application/thg-reporegistry'


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
        return self.rootItem.getRepoItem(reporoot)

    def addGroup(self, name):
        ri = self.rootItem
        cc = ri.childCount()
        self.beginInsertRows(QModelIndex(), cc, cc + 1)
        ri.appendChild(RepoGroupItem(self, name, ri))
        self.endInsertRows()

    def write(self, fn):
        f = QtCore.QFile(fn)
        f.open(QtCore.QIODevice.WriteOnly)
        writeXml(f, self.rootItem, reporegistryXmlElementName)
        f.close()

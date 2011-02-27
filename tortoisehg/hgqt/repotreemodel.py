# repotreemodel.py - model for the reporegistry
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

from mercurial import error

from tortoisehg.hgqt import thgrepo, qtlib
from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _

from repotreeitem import undumpObject, AllRepoGroupItem, RepoGroupItem
from repotreeitem import RepoItem, RepoTreeItem

from PyQt4.QtCore import *
from PyQt4.QtGui import *


extractXmlElementName = 'reporegextract'
reporegistryXmlElementName = 'reporegistry'

repoRegMimeType = 'application/thg-reporegistry'


def writeXml(target, item, rootElementName):
    xw = QXmlStreamWriter(target)
    xw.setAutoFormatting(True)
    xw.setAutoFormattingIndent(2)
    xw.writeStartDocument()
    xw.writeStartElement(rootElementName)
    item.dumpObject(xw)
    xw.writeEndElement()
    xw.writeEndDocument()

def readXml(source, rootElementName, model):
    itemread = None
    xr = QXmlStreamReader(source)
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

def iterRepoItemFromXml(source, model=None):
    xr = QXmlStreamReader(source)
    while not xr.atEnd():
        t = xr.readNext()
        if t == QXmlStreamReader.StartElement and xr.name() == 'repo':
            yield undumpObject(xr, model)

class RepoTreeModel(QAbstractItemModel):
    def __init__(self, openrepofunc, filename=None, parent=None):
        QAbstractItemModel.__init__(self, parent)

        self.openrepofunc = openrepofunc

        root = None
        all = None

        if filename:
            f = QFile(filename)
            if f.open(QIODevice.ReadOnly):
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
        if role not in (Qt.DisplayRole, Qt.EditRole, Qt.DecorationRole):
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
        return Qt.CopyAction | Qt.MoveAction | Qt.LinkAction

    def removeRows(self, row, count, parent):
        item = parent.internalPointer()
        if item is None:
            item = self.rootItem
        self.beginRemoveRows(parent, row, row+count-1)
        res = item.removeRows(row, count)
        self.endRemoveRows()
        return res

    def mimeTypes(self):
        return QStringList(repoRegMimeType)

    def mimeData(self, indexes):
        i = indexes[0]
        item = i.internalPointer()
        buf = QByteArray()
        writeXml(buf, item, extractXmlElementName)
        d = QMimeData()
        d.setData(repoRegMimeType, buf)
        d.setUrls([QUrl.fromLocalFile(hglib.tounicode(item.rootpath()))])
        return d

    def dropMimeData(self, data, action, row, column, parent):
        d = str(data.data(repoRegMimeType))
        itemread = readXml(d, extractXmlElementName, self)
        group = parent.internalPointer()
        if row < 0:
            row = 0
        self.beginInsertRows(parent, row, row)
        group.insertChild(row, itemread)
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

    def addRepo(self, group, repo):
        if not repo:
            caption = _('Select repository directory to add')
            FD = QFileDialog
            path = FD.getExistingDirectory(caption=caption,
                    options=FD.ShowDirsOnly | FD.ReadOnly)
            if path:
                try:
                    lpath = hglib.fromunicode(path)
                    repo = thgrepo.repository(None, path=lpath)
                except error.RepoError:
                    # NOTE: here we cannot pass parent=self because self
                    # isn't a QWidget. Codes under `if not repo:` should
                    # be handled by a widget, not by a model.
                    qtlib.WarningMsgBox(
                        _('Failed to add repository'),
                        _('%s is not a valid repository') % path)
                    return
            else:
                return
        grp = group
        if grp == None:
            grp = self.allreposIndex()
        rgi = grp.internalPointer()
        cc = rgi.childCount()
        self.beginInsertRows(grp, cc, cc + 1)
        rgi.appendChild(RepoItem(self, repo))
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
        f = QFile(fn)
        f.open(QIODevice.WriteOnly)
        writeXml(f, self.rootItem, reporegistryXmlElementName)
        f.close()

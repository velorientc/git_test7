# repotreemodel.py - model for the reporegistry
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib

from repotreeitem import undumpObject, AllRepoGroupItem, RepoGroupItem
from repotreeitem import RepoItem, RepoTreeItem

from PyQt4.QtCore import *
from PyQt4.QtGui import *


extractXmlElementName = 'reporegextract'
reporegistryXmlElementName = 'reporegistry'

repoRegMimeType = 'application/thg-reporegistry'
repoRegGroupMimeType = 'application/thg-reporegistrygroup'
repoExternalMimeType = 'text/uri-list'


def writeXml(target, item, rootElementName):
    xw = QXmlStreamWriter(target)
    xw.setAutoFormatting(True)
    xw.setAutoFormattingIndent(2)
    xw.writeStartDocument()
    xw.writeStartElement(rootElementName)
    item.dumpObject(xw)
    xw.writeEndElement()
    xw.writeEndDocument()

def readXml(source, rootElementName):
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
        itemread = undumpObject(xr)
        xr.skipCurrentElement()
    if xr.hasError():
        print str(xr.errorString())
    return itemread

def iterRepoItemFromXml(source):
    xr = QXmlStreamReader(source)
    while not xr.atEnd():
        t = xr.readNext()
        if t == QXmlStreamReader.StartElement and xr.name() == 'repo':
            yield undumpObject(xr)

def getRepoItemList(root):
    if isinstance(root, RepoItem):
        return [root]
    if not isinstance(root, RepoTreeItem):
        return []
    return reduce(lambda a, b: a + b,
                  (getRepoItemList(c) for c in root.childs), [])


class RepoTreeModel(QAbstractItemModel):

    def __init__(self, filename, parent, showSubrepos=False,
            showNetworkSubrepos=False):
        QAbstractItemModel.__init__(self, parent)

        self.showSubrepos = showSubrepos
        self.showNetworkSubrepos = showNetworkSubrepos

        root = None
        all = None

        if filename:
            f = QFile(filename)
            if f.open(QIODevice.ReadOnly):
                root = readXml(f, reporegistryXmlElementName)
                f.close()
                if root:
                    for c in root.childs:
                        if isinstance(c, AllRepoGroupItem):
                            all = c
                            break

                    if self.showSubrepos:
                        self.loadSubrepos(root)

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
        return QStringList([repoRegMimeType, repoRegGroupMimeType,
                            repoExternalMimeType])

    def mimeData(self, indexes):
        i = indexes[0]
        item = i.internalPointer()
        buf = QByteArray()
        writeXml(buf, item, extractXmlElementName)
        d = QMimeData()
        if isinstance(item, RepoItem):
            d.setData(repoRegMimeType, buf)
            d.setUrls([QUrl.fromLocalFile(hglib.tounicode(item.rootpath()))])
        else:
            d.setData(repoRegGroupMimeType, buf)
            d.setText(QString(item.name))
        return d

    def dropMimeData(self, data, action, row, column, parent):
        group = parent.internalPointer()
        if data.hasUrls():
            d = str(data.data(repoRegMimeType))
        else:
            row = parent.row()
            group = self.rootItem
            parent = QModelIndex()
            d = str(data.data(repoRegGroupMimeType))
        itemread = readXml(d, extractXmlElementName)
        if itemread is None:
            return False
        if group is None:
            return False
        if row < 0:
            row = 0
        if self.showSubrepos:
            self.loadSubrepos(itemread)
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
            self.dataChanged.emit(index, index)
            return True
        return False

    # functions not defined in QAbstractItemModel

    def allreposIndex(self):
        return self.createIndex(0, 0, self.allrepos)

    def addRepo(self, group, root, row=-1):
        grp = group
        if grp == None:
            grp = self.allreposIndex()
        rgi = grp.internalPointer()
        if row < 0:
            row = rgi.childCount()
        self.beginInsertRows(grp, row, row)
        ri = RepoItem(root)
        rgi.insertChild(row, ri)

        if not self.showSubrepos \
                or (not self.showNetworkSubrepos and paths.netdrive_status(root)):
            self.endInsertRows()
            return

        invalidRepoList = ri.appendSubrepos()

        self.endInsertRows()

        if invalidRepoList:
            if invalidRepoList[0] == root:
                qtlib.WarningMsgBox(_('Could not get subrepository list'),
                    _('It was not possible to get the subrepository list for '
                    'the repository in:<br><br><i>%s</i>') % root)
            else:
                qtlib.WarningMsgBox(_('Could not open some subrepositories'),
                    _('It was not possible to fully load the subrepository '
                    'list for the repository in:<br><br><i>%s</i><br><br>'
                    'The following subrepositories may be missing, broken or '
                    'on an inconsistent state and cannot be accessed:'
                    '<br><br><i>%s</i>')  %
                    (root, "<br>".join(invalidRepoList)))

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

    def depth(self, index):
        count = 1
        while True:
            index = index.parent()
            if index.row() < 0:
                return count
            count += 1

    def loadSubrepos(self, root):
        warningmsg = ''
        for c in getRepoItemList(root):
            if self.showNetworkSubrepos \
                    or not paths.netdrive_status(c.rootpath()):

                invalidRepoList = c.appendSubrepos()

                if invalidRepoList:
                    # The top repo or some of its subrepos could not be loaded
                    warningmsg += "<li>" + c.rootpath()
                    if invalidRepoList[0] == c.rootpath():
                        invalidRepoList = invalidRepoList[1:]
                    if invalidRepoList:
                        warningmsg += "<ul><li>"
                        warningmsg += "<li>".join(invalidRepoList)
                        warningmsg += "</ul>"

        # If some repos or subrepos could not be loaded, show a warning message
        if warningmsg:
            warningmsg = _('Some repos could not be fully loaded:') + \
                "<ul>" + warningmsg + '</ul>'
            QTimer.singleShot(0, \
                lambda: qtlib.WarningMsgBox(
                            _('Missing or invalid repos or subrepos '
                            'on the repository registry'),
                            warningmsg))

# repotreemodel.py - model for the reporegistry
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

from mercurial import util, hg, ui

from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, repotreeitem

from PyQt4.QtCore import *
from PyQt4.QtGui import *

import os


extractXmlElementName = 'reporegextract'
reporegistryXmlElementName = 'reporegistry'

repoRegMimeType = 'application/thg-reporegistry'
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
        itemread = repotreeitem.undumpObject(xr)
        xr.skipCurrentElement()
    if xr.hasError():
        print str(xr.errorString())
    return itemread

def iterRepoItemFromXml(source):
    'Used by thgrepo.relatedRepositories to scan the XML file'
    xr = QXmlStreamReader(source)
    while not xr.atEnd():
        t = xr.readNext()
        if t == QXmlStreamReader.StartElement and xr.name() in ('repo', 'subrepo'):
            yield repotreeitem.undumpObject(xr)

def getRepoItemList(root, standalone=False):
    if standalone:
        stopfunc = lambda e: isinstance(e, repotreeitem.RepoItem)
    else:
        stopfunc = None
    return [e for e in repotreeitem.flatten(root, stopfunc=stopfunc)
            if isinstance(e, repotreeitem.RepoItem)]


class RepoTreeModel(QAbstractItemModel):
    def __init__(self, filename, parent=None,
            showNetworkSubrepos=False, showShortPaths=False):
        QAbstractItemModel.__init__(self, parent)
        self.showNetworkSubrepos = showNetworkSubrepos
        self.showShortPaths = showShortPaths
        self._activeRepoItem = None

        root = None
        if filename:
            f = QFile(filename)
            if f.open(QIODevice.ReadOnly):
                root = readXml(f, reporegistryXmlElementName)
                f.close()

        if not root:
            root = repotreeitem.RepoTreeItem(self)
        # due to issue #1075, 'all' may be missing even if 'root' exists
        try:
            all = repotreeitem.find(
                root, lambda e: isinstance(e, repotreeitem.AllRepoGroupItem))
        except ValueError:
            all = repotreeitem.AllRepoGroupItem()
            root.appendChild(all)

        self.rootItem = root
        self.allrepos = all
        self.updateCommonPaths()

    # see http://doc.qt.nokia.com/4.6/model-view-model-subclassing.html

    # overrides from QAbstractItemModel

    def index(self, row, column, parent=QModelIndex()):
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

    def rowCount(self, parent=QModelIndex()):
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            parentItem = self.rootItem;
        else:
            parentItem = parent.internalPointer()
        return parentItem.childCount()

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return parent.internalPointer().columnCount()
        else:
            return self.rootItem.columnCount()

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        if role not in (Qt.DisplayRole, Qt.EditRole, Qt.DecorationRole,
                Qt.FontRole):
            return QVariant()
        item = index.internalPointer()
        if role == Qt.FontRole and item is self._activeRepoItem:
            font = QFont()
            font.setBold(True)
            return font
        else:
            return item.data(index.column(), role)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
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

    def removeRows(self, row, count, parent=QModelIndex()):
        item = parent.internalPointer()
        if item is None:
            item = self.rootItem
        self.beginRemoveRows(parent, row, row+count-1)
        if self._activeRepoItem in item.childs[row:row + count]:
            self._activeRepoItem = None
        res = item.removeRows(row, count)
        self.endRemoveRows()
        return res

    def mimeTypes(self):
        return QStringList([repoRegMimeType, repoExternalMimeType])

    def mimeData(self, indexes):
        i = indexes[0]
        item = i.internalPointer()
        buf = QByteArray()
        writeXml(buf, item, extractXmlElementName)
        d = QMimeData()
        d.setData(repoRegMimeType, buf)
        if isinstance(item, repotreeitem.RepoItem):
            d.setUrls([QUrl.fromLocalFile(hglib.tounicode(item.rootpath()))])
        else:
            d.setText(QString(item.name))
        return d

    def dropMimeData(self, data, action, row, column, parent):
        group = parent.internalPointer()
        d = str(data.data(repoRegMimeType))
        if not data.hasUrls():
            # The source is a group
            if row < 0:
                # The group has been dropped on a group
                # In that case, place the group at the same level as the target
                # group
                row = parent.row()
                parent = parent.parent()
                group = parent.internalPointer()
                if row < 0 or not isinstance(group, repotreeitem.RepoGroupItem):
                    # The group was dropped at the top level
                    group = self.rootItem
                    parent = QModelIndex()
        itemread = readXml(d, extractXmlElementName)
        if itemread is None:
            return False
        if group is None:
            return False
        # Avoid copying subrepos multiple times
        if Qt.CopyAction == action and self.getRepoItem(itemread.rootpath()):
            return False
        if row < 0:
            row = 0
        self.beginInsertRows(parent, row, row)
        group.insertChild(row, itemread)
        self.endInsertRows()
        if isinstance(itemread, repotreeitem.AllRepoGroupItem):
            self.allrepos = itemread
        return True

    def setData(self, index, value, role=Qt.EditRole):
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

    def addRepo(self, root, row=-1, parent=QModelIndex()):
        if not parent.isValid():
            parent = self._indexFromItem(self.allrepos)
        rgi = parent.internalPointer()
        if row < 0:
            row = rgi.childCount()

        # make sure all paths are properly normalized
        root = os.path.normpath(root)

        # Check whether the repo that we are adding is a subrepo
        knownitem = self.getRepoItem(root, lookForSubrepos=True)
        itemIsSubrepo = isinstance(knownitem,
                                   (repotreeitem.StandaloneSubrepoItem,
                                    repotreeitem.SubrepoItem))

        self.beginInsertRows(parent, row, row)
        if itemIsSubrepo:
            ri = repotreeitem.StandaloneSubrepoItem(root)
        else:
            ri = repotreeitem.RepoItem(root)
        rgi.insertChild(row, ri)

        if not self.showNetworkSubrepos and paths.netdrive_status(root):
            self.endInsertRows()
            return self._indexFromItem(ri)

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

        return self._indexFromItem(ri)

    # TODO: merge getRepoItem() to indexFromRepoRoot()
    def getRepoItem(self, reporoot, lookForSubrepos=False):
        reporoot = os.path.normcase(reporoot)
        items = getRepoItemList(self.rootItem, standalone=not lookForSubrepos)
        for e in items:
            if os.path.normcase(e.rootpath()) == reporoot:
                return e

    def indexFromRepoRoot(self, uroot, column=0, standalone=False):
        item = self.getRepoItem(hglib.fromunicode(uroot),
                                lookForSubrepos=not standalone)
        return self._indexFromItem(item, column)

    def indexesOfRepoItems(self, column=0, standalone=False):
        return [self._indexFromItem(e, column)
                for e in getRepoItemList(self.rootItem, standalone)]

    def _indexFromItem(self, item, column=0):
        if item:
            return self.createIndex(item.row(), column, item)
        else:
            return QModelIndex()

    def repoRoot(self, index):
        item = index.internalPointer()
        if not isinstance(item, repotreeitem.RepoItem):
            return
        return hglib.tounicode(item.rootpath())

    def addGroup(self, name):
        ri = self.rootItem
        cc = ri.childCount()
        self.beginInsertRows(QModelIndex(), cc, cc + 1)
        ri.appendChild(repotreeitem.RepoGroupItem(name, ri))
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

    def setActiveRepo(self, index):
        """Highlight the specified item as active"""
        newitem = index.internalPointer()
        if newitem is self._activeRepoItem:
            return
        previtem = self._activeRepoItem
        self._activeRepoItem = newitem
        for it in [previtem, newitem]:
            if it:
                self.dataChanged.emit(
                    self.createIndex(it.row(), 0, it),
                    self.createIndex(it.row(), self.columnCount(), it))

    def activeRepoIndex(self, column=0):
        return self._indexFromItem(self._activeRepoItem, column)

    def loadSubrepos(self, index):
        """Scan subrepos of the repo; returns list of invalid paths"""
        item = index.internalPointer()
        if (not isinstance(item, repotreeitem.RepoItem)
            or isinstance(item, repotreeitem.AlienSubrepoItem)):
            return []
        self.removeRows(0, item.childCount(), index)
        return map(hglib.tounicode, item.appendSubrepos())

    def updateCommonPaths(self, showShortPaths=None):
        if not showShortPaths is None:
            self.showShortPaths = showShortPaths
        for grp in self.rootItem.childs:
            if isinstance(grp, repotreeitem.RepoGroupItem):
                if self.showShortPaths:
                    grp.updateCommonPath()
                else:
                    grp.updateCommonPath('')

    def sortchilds(self, childs, keyfunc):
        self.layoutAboutToBeChanged.emit()
        childs.sort(key=keyfunc)
        self.layoutChanged.emit()

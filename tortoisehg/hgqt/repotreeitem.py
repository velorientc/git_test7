# repotreeitem.py - treeitems for the reporegistry
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import sys
import os

from mercurial import hg, url

from PyQt4 import QtCore, QtGui

from PyQt4.QtCore import Qt, QVariant, QString

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.qtlib import geticon

from tortoisehg.hgqt.settings import SettingsDialog


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

def undumpObject(xr, model):
    classname = xmlToClass(str(xr.name().toString()))
    class_ = getattr(sys.modules[RepoTreeItem.__module__], classname)
    obj = class_(model)
    obj.undump(xr)
    return obj


class RepoTreeItem(object):
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

    def details(self):
        return ''


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

    def details(self):
        return _('Local Repository %s') % self._root


class RepoPathsItem(RepoTreeItem):
    def __init__(self, model, parent=None):
        RepoTreeItem.__init__(self, model, parent)

    def data(self, column, role):
        if role == Qt.DisplayRole and column == 0:
            return QVariant(_('Synchronize'))
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
        return self._path

    def data(self, column, role):
        if role == Qt.DecorationRole:
            if column == 0:
                ico = geticon('sync')
                return QVariant(ico)
            return QVariant()
        if column == 0:
            return QVariant(self._alias)
        elif column == 1:
            path = url.hidepassword(self._path)
            return QVariant(path)
        return QVariant()

    def menulist(self):
        return ['pull']

    def flags(self):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

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

    def details(self):
        path = url.hidepassword(self._path)
        return _('Repository URL %s') % path


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

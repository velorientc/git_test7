# repotreeitem.py - treeitems for the reporegistry
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import sys, os

from mercurial import node, error

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, thgrepo
from tortoisehg.hgqt.settings import SettingsDialog

from PyQt4.QtCore import *
from PyQt4.QtGui import *


xmlClassMap = {
      'allgroup': 'AllRepoGroupItem',
      'group': 'RepoGroupItem',
      'repo': 'RepoItem',
      'treeitem': 'RepoTreeItem',
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

    def insertChild(self, row, child):
        child._row = row
        child._parent = self
        self.childs.insert(row, child)

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
                try:
                    item = undumpObject(xr, self.model)
                    self.appendChild(item)
                except KeyError:
                    pass # ignore unknown classes in xml
            elif xr.isEndElement():
                break

    def dumpObject(self, xw):
        xw.writeStartElement(classToXml(self.__class__.__name__))
        self.dump(xw)
        xw.writeEndElement()

    def open(self, reuse=False):
        pass

    def openAll(self):
        pass

    def showFirstTabOrOpen(self, workbench=None):
        pass

    def details(self):
        return ''

    def getRepoItem(self, reporoot):
        for c in self.childs:
            ri = c.getRepoItem(reporoot)
            if ri:
                return ri
        return None

    def okToDelete(self, parentWidget):
        return True


class RepoItem(RepoTreeItem):
    def __init__(self, model, repo=None, parent=None):
        RepoTreeItem.__init__(self, model, parent)
        self._repo = repo
        self._root = repo and repo.root or ''  # local str
        self._shortname = repo and repo.shortname or ''  # unicode
        self._basenode = repo and repo[0].node() or node.nullid

    def rootpath(self):
        return self._root

    def shortname(self):
        if self._repo:
            return self._repo.shortname
        elif self._shortname:
            return self._shortname
        else:
            return hglib.tounicode(os.path.basename(self._root))

    def basenode(self):
        """Return node id of revision 0"""
        if self._repo:
            return self._repo[0].node()
        else:
            return self._basenode or node.nullid

    def data(self, column, role):
        if role == Qt.DecorationRole:
            if column == 0:
                ico = qtlib.geticon('hg')
                return QVariant(ico)
            return QVariant()
        if column == 0:
            return QVariant(self.shortname())
        elif column == 1:
            return QVariant(hglib.tounicode(self._root))
        return QVariant()

    def menulist(self):
        return ['open', 'remove', 'clone', None, 'explore', 'terminal',
                None, 'settings']

    def flags(self):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled

    def removeRows(self, row, count):
        return False

    def dump(self, xw):
        xw.writeAttribute('root', hglib.tounicode(self._root))
        xw.writeAttribute('shortname', self.shortname())
        xw.writeAttribute('basenode', node.hex(self.basenode()))
        RepoTreeItem.dump(self, xw)

    def undump(self, xr):
        a = xr.attributes()
        self._root = hglib.fromunicode(a.value('', 'root').toString())
        self._shortname = unicode(a.value('', 'shortname').toString())
        self._basenode = node.bin(str(a.value('', 'basenode').toString()))
        RepoTreeItem.undump(self, xr)

    def open(self, reuse=False):
        self.model.openrepofunc(self._root, reuse)

    def showFirstTabOrOpen(self, workbench=None):
        workbench.showRepo(hglib.tounicode(self._root))

    def startSettings(self, parent):
        try:
            try:
                dlg = SettingsDialog(configrepo=True, focus='web.name', parent=parent,
                                     root=self._root)
                self.ensureRepoLoaded()
                dlg.exec_()
            except error.RepoError:
                pass
        finally:
            dlg.deleteLater()

    def ensureRepoLoaded(self):
        """load repo object if necessary

        Until repo loaded, it uses cached shortname for less overhead.
        """
        if self._repo:
            return
        self._repo = thgrepo.repository(path=self._root)

    def details(self):
        return _('Local Repository %s') % hglib.tounicode(self._root)

    def getRepoItem(self, reporoot):
        if (reporoot == self._root or
            (os.name == 'nt' and reporoot.lower() == self._root.lower())):
            return self
        return None


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
                s = QApplication.style()
                ico = s.standardIcon(QStyle.SP_DirIcon)
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
        return ['openAll', 'add', None, 'newGroup', None, 'rename', 'remove']

    def flags(self):
        return (Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDropEnabled
            | Qt.ItemIsEditable)

    def openAll(self):
        for c in self.childs:
            c.open(reuse=True)

    def dump(self, xw):
        xw.writeAttribute('name', self.name)
        RepoTreeItem.dump(self, xw)

    def undump(self, xr):
        a = xr.attributes()
        self.name = a.value('', 'name').toString()
        RepoTreeItem.undump(self, xr)

    def okToDelete(self, parentWidget):
        labels = [(QMessageBox.Yes, _('&Delete')),
                  (QMessageBox.No, _('Cancel'))]
        return qtlib.QuestionMsgBox(
            _('Confirm Delete'),
            _("Delete Group '%s' and all its entries?") % self.name,
            labels=labels, parent=parentWidget)


class AllRepoGroupItem(RepoTreeItem):
    def __init__(self, model, parent=None):
        RepoTreeItem.__init__(self, model, parent)

    def data(self, column, role):
        if role == Qt.DecorationRole:
            if column == 0:
                s = QApplication.style()
                ico = s.standardIcon(QStyle.SP_DirIcon)
                return QVariant(ico)
            return QVariant()
        if column == 0:
            return QVariant(_('default'))
        return QVariant()

    def setData(self, column, value):
        return False

    def menulist(self):
        return ['add', 'newGroup']

    def flags(self):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDropEnabled

    def dump(self, xw):
        RepoTreeItem.dump(self, xw)

    def undump(self, xr):
        RepoTreeItem.undump(self, xr)

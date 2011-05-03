# repotreeitem.py - treeitems for the reporegistry
#
# Copyright 2010 Adrian Buehlmann <adrian@cadifra.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import sys, os

from mercurial import node
from mercurial import ui, hg, util, error

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib
from tortoisehg.hgqt import thgrepo

from PyQt4.QtCore import *
from PyQt4.QtGui import *


xmlClassMap = {
      'allgroup': 'AllRepoGroupItem',
      'group': 'RepoGroupItem',
      'repo': 'RepoItem',
      'subrepo': 'SubrepoItem',
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
                item = undumpObject(xr, self.model)
                self.appendChild(item)
            elif xr.isEndElement():
                break

    def dumpObject(self, xw):
        xw.writeStartElement(classToXml(self.__class__.__name__))
        self.dump(xw)
        xw.writeEndElement()

    def isRepo(self):
        return False

    def details(self):
        return ''

    def getRepoItem(self, reporoot):
        for c in self.childs:
            ri = c.getRepoItem(reporoot)
            if ri:
                return ri
        return None

    def okToDelete(self):
        return True


class RepoItem(RepoTreeItem):
    def __init__(self, model, root=None, parent=None):
        RepoTreeItem.__init__(self, model, parent)
        self._root = root or ''
        self._shortname = u''
        self._basenode = node.nullid
        self._repotype = 'hg'
        # The _valid property is used to display a "warning" icon for repos
        # that cannot be open
        # If root is set we assume that the repo is valid (an actual validity
        # test would require calling hg.repository() which is expensive)
        # Regardless, self._valid may be set to False if self.undump() fails
        if self._root:
            self._valid = True
        else:
            self._valid = False

    def isRepo(self):
        return True
    def rootpath(self):
        return self._root

    def shortname(self):
        if self._shortname:
            return self._shortname
        else:
            return hglib.tounicode(os.path.basename(self._root))

    def repotype(self):
        return self._repotype

    def basenode(self):
        """Return node id of revision 0"""
        return self._basenode

    def setBaseNode(self, basenode):
        self._basenode = basenode

    def setShortName(self, uname):
        self._shortname = uname

    def data(self, column, role):
        if role == Qt.DecorationRole:
            if column == 0:
                ico = qtlib.geticon('hg')
                if not self._valid:
                    ico = _overlaidicon(ico, qtlib.geticon('dialog-warning'))
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
    def undump(self, xr):
        self._valid = False # Will be set to True if everything goes fine
        a = xr.attributes()
        self._root = hglib.fromunicode(a.value('', 'root').toString())
        self._shortname = unicode(a.value('', 'shortname').toString())
        self._basenode = node.bin(str(a.value('', 'basenode').toString()))
        RepoTreeItem.undump(self, xr)

        def addSubrepos(ri, repo):
            invalidRepoList = []
            try:
                wctx = repo['.']
                for subpath in wctx.substate:
                    # For now we only support showing mercurial subrepos
                    subtype = wctx.substate[subpath][2]
                    sctx = wctx.sub(subpath)
                    ri.appendChild(
                        SubrepoItem(self.model, sctx._repo.root, subtype=subtype))
                    if subtype == 'hg':
                        # Only recurse into mercurial subrepos
                        if ri.childCount():
                            invalidRepoList += \
                                addSubrepos(
                                    ri.child(ri.childCount()-1), sctx._repo)
            except (EnvironmentError, error.RepoError, util.Abort), e:
                # Add the repo to the list of repos/subrepos
                # that could not be open
                invalidRepoList.append(repo.root)

            return invalidRepoList

        root = self.rootpath()
        try:
            repo = hg.repository(ui.ui(), root)
        except (EnvironmentError, error.RepoError, util.Abort), e:
            # Do not try to show the list of subrepos when the top repository
            # could not be open
            # TODO: Mark the repo with a "warning" icon or similar to indicate
            #       that the repository cannot be open
            return

        invalidRepoList = \
            addSubrepos(self, repo)

        if invalidRepoList:
            if invalidRepoList[0] == root:
                qtlib.WarningMsgBox(_('Could not get subrepository list'),
                    _('It was not possible to get the subrepository list for '
                    'the repository in:<br><br><i>%s</i>') % root)
            else:
                qtlib.WarningMsgBox(_('Could not open some subrepositories'),
                    _('It was not possible to fully load the subrepository list '
                    'for the repository in:<br><br><i>%s</i><br><br>'
                    'The following subrepositories could not be accessed:'
                    '<br><br><i>%s</i>') %
                    (root, "<br>".join(invalidRepoList)))
        else:
            self._valid = True
    def details(self):
        return _('Local Repository %s') % hglib.tounicode(self._root)

    def getRepoItem(self, reporoot):
        if reporoot == self._root:
            return self
        return None


def _overlaidicon(base, overlay):
    """Generate overlaid icon"""
    # TODO: This was copied from manifestmodel.py
    # TODO: generalize this function as a utility
    pixmap = base.pixmap(16, 16)
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
    painter.drawPixmap(0, 0, overlay.pixmap(16, 16))
    del painter
    return QIcon(pixmap)


class SubrepoItem(RepoItem):
    _subrepoType2IcoMap = {
          'hg': 'hg',
          'git': 'thg-git-subrepo',
          'svn': 'thg-svn-subrepo',
    }

    def __init__(self, model, repo=None, parent=None, parentrepo=None,
            subtype='hg'):
        RepoItem.__init__(self, model, repo, parent)
        self._parentrepo = parentrepo
        self._repotype = subtype
        if self._repotype != 'hg':
            # Make sure that we cannot drag non hg subrepos
            # To do so we disable the dumpObject method for non hg subrepos
            def doNothing(dummy):
                pass
            self.dumpObject = doNothing

            # Limit the context menu to those actions that are valid for non
            # mercurial subrepos
            def nonHgMenulist():
                return ['remove', None, 'explore', 'terminal']
            self.menulist = nonHgMenulist

    def data(self, column, role):
        if role == Qt.DecorationRole:
            if column == 0:
                subiconame = SubrepoItem._subrepoType2IcoMap.get(self._repotype, None)
                if subiconame is None:
                    # Unknown (or generic) subrepo type
                    ico = qtlib.geticon('thg-subrepo')
                else:
                    # Overlay the "subrepo icon" on top of the selected subrepo
                    # type icon
                    ico = qtlib.geticon(subiconame)
                    ico = _overlaidicon(ico, qtlib.geticon('thg-subrepo'))
                return QVariant(ico)
            return QVariant()
        else:
            return super(SubrepoItem, self).data(column, role)


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
            | Qt.ItemIsDragEnabled | Qt.ItemIsEditable)

    def childRoots(self):
        return [c._root for c in self.childs]

    def dump(self, xw):
        xw.writeAttribute('name', self.name)
        RepoTreeItem.dump(self, xw)

    def undump(self, xr):
        a = xr.attributes()
        self.name = a.value('', 'name').toString()
        RepoTreeItem.undump(self, xr)

    def okToDelete(self):
        return False


class AllRepoGroupItem(RepoGroupItem):
    def __init__(self, model, parent=None):
        RepoTreeItem.__init__(self, model, parent)
        self.name = _('default')

    def menulist(self):
        return ['openAll', 'add', None, 'newGroup', None, 'rename']

    def undump(self, xr):
        a = xr.attributes()
        name = a.value('', 'name').toString()
        if name:
            self.name = name
        RepoTreeItem.undump(self, xr)

# -*- coding: utf-8 -*-
# Copyright (c) 2003-2010 LOGILAB S.A. (Paris, FRANCE).
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

#
# make sure the Qt rc files are converted into python modules, then load them
# this must be done BEFORE other tortoisehg modules are loaded.
import os
import os.path as osp
import sys

def should_rebuild(srcfile, pyfile):
    return not osp.isfile(pyfile) or osp.isfile(srcfile) and \
               osp.getmtime(pyfile) < osp.getmtime(srcfile)

# automatically load resource module, creating it on the fly if
# required
curdir = osp.dirname(__file__)
pyfile = osp.join(curdir, "workbench_rc.py")
rcfile = osp.join(curdir, "workbench.qrc")
if should_rebuild(rcfile, pyfile):
    if os.system('pyrcc4 %s -o %s' % (rcfile, pyfile)):
        print "ERROR: Cannot convert the resource file '%s' into a python module."
        print "Please check the PyQt 'pyrcc4' tool is installed, or do it by hand running:"
        print "pyrcc4 %s -o %s" % (rcfile, pyfile)

# load icons from resource and store them in a dict, no matter their
# extension (.svg or .png)
from PyQt4 import QtCore
from PyQt4 import QtGui, uic
connect = QtCore.QObject.connect
SIGNAL = QtCore.SIGNAL
Qt = QtCore.Qt
import workbench_rc


_icons = {}
def _load_icons():
    d = QtCore.QDir(':/icons')
    for icn in d.entryList():
        name, ext = osp.splitext(str(icn))
        if name not in _icons or ext == ".svg":
            _icons[name] = QtGui.QIcon(':/icons/%s' % icn)

def icon(name):
    """
    Return a QIcon for the resource named 'name.(svg|png)' (the given
    'name' parameter must *not* provide the extension).
    """
    if not _icons:
        _load_icons()
    return _icons.get(name)


# dirty hack to please PyQt4 uic
import repoview, fileview
sys.modules['repoview'] = repoview
sys.modules['fileview'] = fileview
sys.modules['workbench_rc'] = workbench_rc

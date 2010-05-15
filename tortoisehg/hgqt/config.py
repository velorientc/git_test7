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
# pylint: disable-msg=C0103

"""
Module for managing configuration parameters of hgview using Hg's
configuration system
"""
import os
import re

def cached(meth):
    """
    decorator to cache config values once they are read
    """
    name = meth.func_name
    def wrapper(self, *args, **kw):
        if name in self._cache:
            return self._cache[name]
        res = meth(self, *args, **kw)
        self._cache[name] = res
        return res
    wrapper.__doc__ = meth.__doc__
    return wrapper

class HgConfig(object):
    """
    Class managing user configuration from hg standard configuration system (.hgrc)
    """
    def __init__(self, ui, section="TortoiseHgQt"):
        self.ui = ui
        self.section = section
        self._cache = {}

    @cached
    def getFont(self):
        """
        font: default font used to display diffs and files. Use Qt4 format.
        """
        return self.ui.config(self.section, 'font', 'Monospace')

    @cached
    def getFontSize(self, default=10):
        """
        fontsize: text size in file content viewer
        """
        return int(self.ui.config(self.section, 'fontsize', default))

    @cached
    def getDotRadius(self, default=8):
        """
        dotradius: radius (in pixels) of the dot in the revision graph
        """
        r = self.ui.config(self.section, 'dotradius', default)
        return int(r)

    @cached
    def getUsers(self):
        """
        users: path of the file holding users configurations
        """
        users = {}
        aliases = {}
        usersfile = self.ui.config(self.section, 'users',
                                   os.path.join('~', ".hgusers"))
        cfgfile = None
        if usersfile:
            try:
                cfgfile = open(os.path.expanduser(usersfile))
            except IOError:
                cfgfile = None

        if cfgfile:
            currid = None
            for line in cfgfile:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                cmd, val = line.split('=', 1)
                if cmd == 'id':
                    currid = val
                    if currid in users:
                        print "W: user %s is defined several times" % currid
                    users[currid] = {'aliases': set()}
                elif cmd == "alias":
                    users[currid]['aliases'].add(val)
                    if val in aliases:
                        print ("W: alias %s is used in several "
                               "user definitions" % val)
                    aliases[val] = currid
                else:
                    users[currid][cmd] = val
        return users, aliases

    @cached
    def getFileModifiedColor(self, default='blue'):
        """
        filemodifiedcolor: display color of a modified file
        """
        return self.ui.config(self.section, 'filemodifiedcolor', default)
    @cached
    def getFileRemovedColor(self, default='red'):
        """
        fileremovedcolor: display color of a removed file
        """
        return self.ui.config(self.section, 'fileremovededcolor', default)
    @cached
    def getFileDeletedColor(self, default='darkred'):
        """
        filedeletedcolor: display color of a deleted file
        """
        return self.ui.config(self.section, 'filedeletedcolor', default)
    @cached
    def getFileAddedColor(self, default='green'):
        """
        fileaddedcolor: display color of an added file
        """
        return self.ui.config(self.section, 'fileaddedcolor', default)

    @cached
    def getRowHeight(self, default=20):
        """
        rowheight: height (in pixels) on a row of the revision table
        """
        return int(self.ui.config(self.section, 'rowheight', default))

    @cached
    def getHideFindDelay(self, default=10000):
        """
        hidefinddelay: delay (in ms) after which the find bar will disappear
        """
        return int(self.ui.config(self.section, 'hidefindddelay', default))

    @cached
    def getFillingStep(self, default=300):
        """
        fillingstep: number of nodes 'loaded' at a time when updating repo graph log
        """
        return int(self.ui.config(self.section, 'fillingstep', default))

    @cached
    def getChangelogColumns(self, default=None):
        """
        changelogcolumns: ordered list of displayed columns in changelog views;
                    defaults to ID, Branch, Log, Author, Date, Tags
        """
        cols = self.ui.config(self.section, 'changelogcolumns', default)
        if cols is None:
            return None
        return [col.strip() for col in cols.split(',') if col.strip()]

    @cached
    def getFilelogColumns(self, default=None):
        """
        filelogcolumns: ordered list of displayed columns in filelog views;
                  defaults to ID, Log, Author, Date
        """
        cols = self.ui.config(self.section, 'filelogcolumns', default)
        if cols is None:
            return None
        return [col.strip() for col in cols.split(',') if col.strip()]

    @cached
    def getDisplayDiffStats(self, default="no"):
        """
        displaydiffstats: flag controllong the appearance of the
                    'Diff' column in a revision's file list
        """
        val = str(self.ui.config(self.section, 'displaydiffstats', default))
        return val.lower() in ['true', 'yes', '1', 'on']

    @cached
    def getMaxFileSize(self, default=100000):
        """
        maxfilesize: max size of a file (for diff computations, display content, etc.)
        """
        return int(self.ui.config(self.section, 'maxfilesize', default))

    @cached
    def getDiffBGColor(self, default='white'):
        """
        diffbgcolor: background color of diffs
        """
        return self.ui.config(self.section, 'diffbgcolor', default)

    @cached
    def getDiffFGColor(self, default='black'):
        """
        difffgcolor: text color of diffs
        """
        return self.ui.config(self.section, 'difffgcolor', default)

    @cached
    def getDiffPlusColor(self, default='green'):
        """
        diffpluscolor: text color of added lines in diffs
        """
        return self.ui.config(self.section, 'diffpluscolor', default)

    @cached
    def getDiffMinusColor(self, default='red'):
        """
        diffminuscolor: text color of removed lines in diffs
        """
        return self.ui.config(self.section, 'diffminuscolor', default)

    @cached
    def getDiffSectionColor(self, default='magenta'):
        """
        diffsectioncolor: text color of new section in diffs
        """
        return self.ui.config(self.section, 'diffsectioncolor', default)

    @cached
    def getMQFGColor(self, default='#ff8183'):
        """
        mqfgcolor: bg color to highlight mq patches
        """
        return self.ui.config(self.section, 'mqfgcolor', default)

    @cached
    def getMQHideTags(self, default=False):
        """
        mqhidetags: hide mq tags
        """
        return self.ui.config(self.section, 'mqhidetags', default)



_HgConfig = HgConfig
# HgConfig is instanciated only once (singleton)
#
# this 'factory' is used to manage this (not using heavy guns of
# metaclass or so)
_hgconfig = None
def HgConfig(ui):
    """Factory to instanciate HgConfig class as a singleton
    """
    # pylint: disable-msg=E0102
    global _hgconfig
    if _hgconfig is None:
        _hgconfig = _HgConfig(ui)
    return _hgconfig


def get_option_descriptions(rest=False):
    """
    Extract options descriptions (docstrings of HgConfig methods)
    """
    options = []
    for attr in dir(_HgConfig):
        if attr.startswith('get'):
            meth = getattr(_HgConfig, attr)
            if callable(meth):
                doc = meth.__doc__
                if doc and doc.strip():
                    doc = doc.strip()
                    if rest:
                        doc = re.sub(r' *(?P<arg>.*) *: *(?P<desc>.*)', r'``\1`` \2', doc.strip())
                        doc = ' '.join(doc.split()) # remove \n and other multiple whitespaces
                    options.append(doc)
    return options


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
"""mercurial interactive history viewer

Its purpose is similar to the hgk tool of mercurial, and it has been
written with efficiency in mind when dealing with big repositories
(it can happily be used to browse Linux kernel source code
repository).
"""

# monkey patch to support older hg versions
from mercurial import changelog, filelog
if not hasattr(changelog.changelog, '__len__'):
    changelog.changelog.__len__ = changelog.changelog.count
if not hasattr(filelog.filelog, '__len__'):
    filelog.filelog.__len__ = filelog.filelog.count

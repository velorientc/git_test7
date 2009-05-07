# thgstatus.py - TortoiseHg status cache extension for Mercurial
#
# Copyright (C) 2009 Adrian Buehlmann
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from mercurial.i18n import _
from mercurial import commands

def cachefilepath(repo):
    return repo.root + "/.hg/thgstatus"

def dirname(f):
    return '/'.join(f.split('/')[:-1])

def thgstatus(ui, repo, source='default', **opts):
    '''update directory status cache for TortoiseHg

    Caches the information provided by 'hg status' in the file .hg/thgstatus
    which can then be used by the TortoiseHg shell extension to display
    overlay icons for directories.
    The file .hg/thgstatus contains one line for each directory that has
    removed, modified or added files (in that order of preference). Each line
    consists of one char for the status of the directory (r, m or a), followed
    by the relative path of the directory in the repo.
    If the file is empty, then the repo is clean.
    '''

    repostate = repo.status()
    modified, added, removed, deleted, unknown, ignored, clean = repostate
    dirstatus = {}
    for fn in added:
        dirstatus[dirname(fn)] = 'a'
    for fn in modified:
        dirstatus[dirname(fn)] = 'm'
    for fn in removed:
        dirstatus[dirname(fn)] = 'r'
    nmodified, nadded, nremoved = 0, 0, 0
    f = open(cachefilepath(repo), 'wb')
    for dn in sorted(dirstatus):
        s = dirstatus[dn]
        if (s == 'm'):
            nmodified += 1
        elif (s == 'a'):
            nadded += 1
        elif (s == 'r'):
            nremoved +=1
        f.write(dirstatus[dn] + dn + '\n')
    f.close()
    ui.status(_("updated cached directory status: "
        "%i modified, %i added, %i removed") % (nmodified, nadded, nremoved))

cmdtable = {
    'thgstatus':
        (thgstatus,
        [ ],
        _('hg thgstatus')),
}

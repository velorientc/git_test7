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

'''update directory status cache for TortoiseHg'''

from mercurial.i18n import _
from mercurial import commands
import os
import time

def cachefilepath(repo):
    return repo.join("thgstatus")

def dirname(f):
    return f[:max(0, f.rfind("/"))]

def showentry(f, e):
    f("%s %s\n" % (e[0], e[1:-1]))

def thgstatus(ui, repo, **opts):
    '''update directory status cache for TortoiseHg

    Caches the information provided by 'hg status' in the file .hg/thgstatus
    which can then be used by the TortoiseHg shell extension to display
    overlay icons for directories.

    The file .hg/thgstatus contains one line for each directory that has
    removed, modified or added files (in that order of preference). Each line
    consists of one char for the status of the directory (r, m or a), followed
    by the relative path of the directory in the repo.
    If the file is empty, then the repo is clean.

    Specify --delay to wait until the system clock ticks to the next second
    before accessing the dirstate. This is useful when the dirstate contains
    unset entries (in output of "hg debugstate"). unset entries happen if the
    dirstate was updated within the same second as the respective file in the
    working tree was updated. This happens with a high probability for example
    when cloning a repo. The TortoiseHg shell extension will display unset
    dirstate entries as (potentially false) modified. Specifying --delay ensures
    that there are no unset entries in the dirstate.
    '''

    if opts.get('remove'):
        try:
            os.remove(cachefilepath(repo))
        except OSError:
            pass
        return

    if opts.get('show'):
        try:
            f = open(cachefilepath(repo), 'rb')
            for e in f:
                showentry(ui.status, e)
            f.close()
        except IOError:
            ui.status("*no status*\n")
        return

    if opts.get('delay'):
        tref = time.time()
        tdelta = float(int(tref)) + 1.0 - tref
        if (tdelta > 0.0):
            time.sleep(tdelta)

    repostate = repo.status()
    modified, added, removed, deleted = repostate[:4]
    dirstatus = {}
    for fn in added:
        dirstatus[dirname(fn)] = 'a'
    for fn in modified:
        dirstatus[dirname(fn)] = 'm'
    for fn in removed + deleted:
        dirstatus[dirname(fn)] = 'r'

    f = open(cachefilepath(repo), 'wb')
    for dn in sorted(dirstatus):
        e = dirstatus[dn] + dn + '\n'
        f.write(e)
        showentry(ui.note, e)
    f.close()

    if opts.get('notify'):
        from mercurial import demandimport
        demandimport.disable()
        from thgutil import shlib
        shlib.shell_notify(opts.get('notify'))
        demandimport.enable()
    ui.note("thgstatus updated\n") 

cmdtable = {
    'thgstatus':
        (thgstatus,
        [ ('',  'delay', None, _('wait until the second ticks over')),
          ('n', 'notify', [], _('notify the shell for path(s) given')),
          ('',  'remove', None, _('remove the status file')),
          ('s', 'show', None, _('just show the contents of '
                                'the status file (no update)')) ],
        _('hg thgstatus [OPTION]...')),
}

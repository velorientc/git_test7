# bfprompt.py - prompt to add large files as bfiles
#
# Copyright 2011 Fog Creek Software
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os

from mercurial import match
from tortoisehg.hgqt import qtlib
from tortoisehg.hgqt.i18n import _

class LfilesPrompt(qtlib.CustomPrompt):
    def __init__(self, parent, files=None):
        qtlib.CustomPrompt.__init__(self, _('Confirm Add'),
                                    _('Some of the files that you have selected are of a size '
                                      'over 10 MB.  You may make more efficient use of disk space '
                                      'by adding these files as largefiles, which will store only the '
                                      'most recent revision of each file in your local repository, '
                                      'with older revisions available on the server.  Do you wish '
                                      'to add these files as largefiles?'), parent,
                                      (_('Add as &Largefiles'), _('Add as &Normal Files'), _('Cancel')),
                                      0, 2, files)

class BfilesPrompt(qtlib.CustomPrompt):
    def __init__(self, parent, files=None):
        qtlib.CustomPrompt.__init__(self, _('Confirm Add'),
                                    _('Some of the files that you have selected are of a size '
                                      'over 10 MB.  You may make more efficient use of disk space '
                                      'by adding these files as bfiles, which will store only the '
                                      'most recent revision of each file in your local repository, '
                                      'with older revisions available on the server.  Do you wish '
                                      'to add these files as bfiles?'), parent,
                                      (_('Add as &Bfiles'), _('Add as &Normal Files'), _('Cancel')),
                                      0, 2, files)
                                      
def promptForLfiles(parent, ui, repo, files, haskbf=False):
    lfiles = []
    usekbf = os.path.exists('.kbf')
    uself = os.path.exists('.hglf')
    useneither = not usekbf and not uself
    if haskbf:
        section = 'kilnbfiles'
    else:
        section = 'largefiles'
    minsize = int(ui.config(section, 'size', default='10'))
    patterns = ui.config(section, 'patterns', default=())
    if patterns:
        patterns = patterns.split(' ')
        matcher = match.match(repo.root, '', list(patterns))
    else:
        matcher = None
    for wfile in files:
        if not matcher or not matcher(wfile) or useneither:
            filesize = os.path.getsize(repo.wjoin(wfile))
            if filesize >= 10*1024*1024 and (filesize < minsize*1024*1024 or useneither):
                lfiles.append(wfile)
    if lfiles:
        if haskbf:
            ret = BfilesPrompt(parent, files).run()
        else:
            ret = LfilesPrompt(parent, files).run()
        if ret == 0:
            # add as largefiles/bfiles
            for lfile in lfiles:
                files.remove(lfile)
        elif ret == 1:
            # add as normal files
            lfiles = []
        elif ret == 2:
            return None
    return files, lfiles

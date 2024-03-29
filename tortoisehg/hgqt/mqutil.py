# mqutil.py - Common functionality for TortoiseHg MQ widget
#
# Copyright 2011 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os, re, time

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, rejects

def defaultNewPatchName(repo):
    t = time.strftime('%Y-%m-%d_%H-%M-%S')
    return t + '_r%d+.diff' % repo['.'].rev()

def getPatchNameLineEdit():
    patchNameLE = QLineEdit()
    if hasattr(patchNameLE, 'setPlaceholderText'): # Qt >= 4.7
        patchNameLE.setPlaceholderText(_('### patch name ###'))
    return patchNameLE

def getUserOptions(opts, *optionlist):
    out = []
    for opt in optionlist:
        if opt not in opts:
            continue
        val = opts[opt]
        if val is False:
            continue
        elif val is True:
            out.append('--' + opt)
        else:
            out.append('--' + opt)
            out.append(val)
    return out

def checkForRejects(repo, rawoutput, parent=None):
    """Parse output of qpush/qpop to resolve hunk failure manually"""
    rejre = re.compile('saving rejects to file (.*).rej')
    for m in rejre.finditer(rawoutput):
        wfile = m.groups()[0]
        if not os.path.exists(repo.wjoin(wfile)):
            continue
        ufile = hglib.tounicode(wfile)
        if qtlib.QuestionMsgBox(_('Manually resolve rejected chunks?'),
                                _('%s had rejected chunks, edit patched '
                                  'file together with rejects?') % ufile,
                                parent=parent):
            dlg = rejects.RejectsDialog(repo.wjoin(wfile), parent)
            dlg.exec_()

def mqNewRefreshCommand(repo, isnew, stwidget, pnwidget, message, opts, olist):
    if isnew:
        name = hglib.fromunicode(pnwidget.text())
        if not name:
            qtlib.ErrorMsgBox(_('Patch Name Required'),
                              _('You must enter a patch name'))
            pnwidget.setFocus()
            return
        cmdline = ['qnew', '--repository', repo.root, name]
    else:
        cmdline = ['qrefresh', '--repository', repo.root]
    if message:
        cmdline += ['--message=' + hglib.fromunicode(message)]
    cmdline += getUserOptions(opts, *olist)
    files = ['--'] + [repo.wjoin(x) for x in stwidget.getChecked()]
    addrem = [repo.wjoin(x) for x in stwidget.getChecked('!?')]
    if len(files) > 1:
        cmdline += files
    else:
        cmdline += ['--exclude', repo.root]
    if addrem:
        cmdlines = [ ['addremove', '-R', repo.root] + addrem, cmdline]
    else:
        cmdlines = [cmdline]
    return cmdlines

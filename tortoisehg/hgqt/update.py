# update.py - Update dialog for TortoiseHg
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from tortoisehg.hgqt import cmdui

def run(ui, *pats, **opts):
    args = ['update']
    if opts.get('rev'):
        args += ['-r', opts.get('rev')]
    elif len(pats) == 1:
        args += [pats[0]]
    return cmdui.Dialog(args)

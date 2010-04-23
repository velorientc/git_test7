# clone.py - Clone dialog for TortoiseHg
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from tortoisehg.util import hglib
from tortoisehg.hgqt import cmdui

def run(ui, *pats, **opts):
    src = hglib.toutf(os.getcwd())
    dest = src
    if len(pats) > 1:
        src = pats[0]
        dest = pats[1]
    else:
        src = pats[0]
    return cmdui.Dialog(['clone', src, dest])

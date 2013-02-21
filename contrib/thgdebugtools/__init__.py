# thgdebugtools - extension to add debug actions to TortoiseHg
#
# Copyright 2013 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

"""add debug actions to TortoiseHg GUI

This extension adds "Debug" menu to the Workbench window.
"""

import sys

def extsetup(ui):
    if 'tortoisehg.hgqt.run' not in sys.modules:
        return  # not a TortoiseHg

    # now it's safe to load TortoiseHg-specific modules
    import core
    core.extsetup(ui)

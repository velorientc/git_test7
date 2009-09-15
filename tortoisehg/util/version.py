# version.py - TortoiseHg version
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from tortoisehg.util.i18n import _

def version():
    try:
        import __version__
        return __version__.version
    except ImportError:
        return _('unknown')



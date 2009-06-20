"""
version.py - TortoiseHg version
 Copyright (C) 2009 Steve Borho <steve@borho.org>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.
"""

from thgutil.i18n import _

def version():
    try:
        import __version__
        return __version__.version
    except ImportError:
        return _('unknown')



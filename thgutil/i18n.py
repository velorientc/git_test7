"""
i18n.py
 Copyright (C) 2009 Steve Borho <steve@borho.org>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.
"""

import gettext, sys
from gettext import gettext as _
from thgutil import paths, hglib

gettext.bindtextdomain("tortoisehg", paths.get_locale_path())
gettext.textdomain("tortoisehg")

def agettext(message):
    """Translate message and convert to local encoding
    such as 'ascii' before being returned.

    Only use this if you need to output translated messages
    to command-line interface (ie: Windows Command Prompt).
    """
    try:
        u = _(message)
        return hglib.fromutf(u)
    except LookupError:
        return message


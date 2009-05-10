"""
i18n.py
 Copyright (C) 2009 Steve Borho <steve@borho.org>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.
"""

import gettext
from gettext import gettext as _

# TODO: get proper path from somewheres
gettext.bindtextdomain("thg", "c:/path/to/locale")
gettext.textdomain("thg")

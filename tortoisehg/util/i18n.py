# i18n.py - TortoiseHg internationalization code
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gettext, sys
from gettext import gettext as _
from tortoisehg.util import paths

gettext.bindtextdomain("tortoisehg", paths.get_locale_path())
gettext.textdomain("tortoisehg")

def agettext(message):
    """Translate message and convert to local encoding
    such as 'ascii' before being returned.

    Only use this if you need to output translated messages
    to command-line interface (ie: Windows Command Prompt).
    """
    try:
        from tortoisehg.util import hglib
        u = _(message)
        return hglib.fromutf(u)
    except (LookupError, UnicodeEncodeError):
        return message

class keepgettext(object):
    def _(self, message):
        return {'id': message, 'str': _(message)}

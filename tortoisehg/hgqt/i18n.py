# i18n.py - internationalization support for TortoiseHg
#
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

from tortoisehg.util.i18n import _ as _gettext
from tortoisehg.util.i18n import agettext

def _(message):
    return unicode(_gettext(message), 'utf-8')

class localgettext(object):
    def _(self, message):
        return agettext(message)

class keepgettext(object):
    def _(self, message):
        return {'id': message, 'str': _(message)}

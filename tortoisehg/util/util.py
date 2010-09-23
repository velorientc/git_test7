# -*- coding: utf-8 -*-
# util functions
#
# Copyright (C) 2009-2010 Logilab. All rights reserved.
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.
"""
Several helper functions
"""
import string

from tortoisehg.util import hglib

class Curry(object):
    """Curryfication de fonction (http://fr.wikipedia.org/wiki/Curryfication)"""
    def __init__(self, function, *additional_args, **additional_kwargs):
        self.func = function
        self.additional_args = additional_args
        self.additional_kwargs = additional_kwargs

    def __call__(self, *args, **kwargs):
        args += self.additional_args
        kwarguments = self.additional_kwargs.copy()
        kwarguments.update(kwargs)
        return self.func(*args, **kwarguments)

CONTROL_CHARS = [chr(ci) for ci in range(32)]
TR_CONTROL_CHARS = [' '] * len(CONTROL_CHARS)
for c in ('\n', '\r', '\t'):
    TR_CONTROL_CHARS[ord(c)] = c
TR_CONTROL_CHARS[ord('\f')] = '\n'
TR_CONTROL_CHARS[ord('\v')] = '\n'
ESC_CAR_TABLE = string.maketrans(''.join(CONTROL_CHARS),
                                 ''.join(TR_CONTROL_CHARS))
ESC_UCAR_TABLE = unicode(ESC_CAR_TABLE, 'latin1')

def xml_escape(data):
    """escapes XML forbidden characters in attributes and PCDATA"""
    if isinstance(data, unicode):
        data = data.translate(ESC_UCAR_TABLE)
    else:
        data = data.translate(ESC_CAR_TABLE)
    return (data.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
            .replace('"','&quot;').replace("'",'&#39;'))

def format_desc(desc, width):
    """
    Helper function to format a ctx description for oneliner
    representation (summary view)
    """
    desc = xml_escape(hglib.tounicode(desc).split('\n', 1)[0])
    if len(desc) > width:
        desc = desc[:width] + '...'
    return desc


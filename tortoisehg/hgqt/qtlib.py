# qtlib.py - Qt utility code
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

from PyQt4 import QtCore, QtGui
from mercurial import extensions

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from hgext.color import _styles
# _styles maps from ui labels to effects
# _effects maps an effect to font style properties.  We define a limited
# set of _effects, since we convert color effect names to font style
# effect programatically.

_effects = {
    'bold': 'font-weight: bold',
    'italic': 'font-style: italic',
    'underline': 'text-decoration: underline',
}

thgstylesheet = '* { white-space: pre; font-family: monospace; font-size: 9pt; }'

def configstyles(ui):
    # extensions may provide more labels and default effects
    for name, ext in extensions.extensions():
        _styles.update(getattr(ext, 'colortable', {}))

    # tortoisehg defines a few labels and default effects
    _styles.update({'ui.error':'red bold', 'control':'black bold'})

    # allow the user to override
    for status, cfgeffects in ui.configitems('color'):
        if '.' not in status:
            continue
        cfgeffects = ui.configlist('color', status)
        _styles[status] = ' '.join(cfgeffects)

# See http://doc.trolltech.com/4.2/richtext-html-subset.html
# and http://www.w3.org/TR/SVG/types.html#ColorKeywords

def geteffect(labels):
    'map labels like "log.date" to Qt font styles'
    effects = []
    # Multiple labels may be requested
    for l in labels.split():
        if not l:
            continue
        # Each label may request multiple effects
        es = _styles.get(l, '')
        for e in es.split():
            if e in _effects:
                effects.append(_effects[e])
            elif e in QtGui.QColor.colorNames():
                # Accept any valid QColor
                effects.append('color: ' + e)
            elif e.endswith('_background'):
                e = e[:-11]
                if e in QtGui.QColor.colorNames():
                    effects.append('bgcolor: ' + e)
    return ';'.join(effects)

NAME_MAP = {
    'fg': 'color', 'bg': 'background-color', 'family': 'font-family',
    'size': 'font-size', 'weight': 'font-weight', 'space': 'white-space',
    'style': 'font-style', 'decoration': 'text-decoration',
}

def markup(msg, **styles):
    style = []
    for name, value in styles.items():
        if not value:
            continue
        if NAME_MAP.has_key(name):
            name = NAME_MAP[name]
        style.append('%s: %s' % (name, value))
    style = ';'.join(style)
    msg = hglib.tounicode(msg)
    msg = QtCore.Qt.escape(msg)
    msg = msg.replace('\n', '<br />')
    return '<font style="%s">%s</font>' % (style, msg)

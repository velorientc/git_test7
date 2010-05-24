# qtlib.py - Qt utility code
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import atexit
import shutil
import tempfile

from PyQt4 import QtCore, QtGui
from PyQt4 import Qsci
from mercurial import extensions, util

from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import icon as geticon
from hgext.color import _styles

qsci = Qsci.QsciScintilla

tmproot = None
def gettempdir():
    global tmproot
    def cleanup():
        try: shutil.rmtree(tmproot)
        except: pass
    if not tmproot:
        tmproot = tempfile.mkdtemp(prefix='thg.')
        atexit.register(cleanup)
    return tmproot

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

    for status, cfgeffects in ui.configitems('thg-color'):
        if '.' not in status:
            continue
        cfgeffects = ui.configlist('thg-color', status)
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
    style = {'white-space': 'pre'}
    for name, value in styles.items():
        if not value:
            continue
        if NAME_MAP.has_key(name):
            name = NAME_MAP[name]
        style[name] = value
    style = ';'.join(['%s: %s' % t for t in style.items()])
    msg = hglib.tounicode(msg)
    msg = QtCore.Qt.escape(msg)
    msg = msg.replace('\n', '<br />')
    return '<span style="%s">%s</span>' % (style, msg)

def CommonMsgBox(icon, title, main, text='', buttons=QtGui.QMessageBox.Close,
                 parent=None):
    msg = QtGui.QMessageBox(parent)
    msg.setIcon(icon)
    msg.setWindowTitle(title)
    msg.setStandardButtons(buttons)
    msg.setText('<b>%s</b>' % main)
    info = ''
    for line in text.split('\n'):
        info += '<nobr>%s</nobr><br />' % line
    msg.setInformativeText(info)
    return msg.exec_()

def InfoMsgBox(*args, **kargs):
    return CommonMsgBox(QtGui.QMessageBox.Information, *args, **kargs)

def WarningMsgBox(*args, **kargs):
    return CommonMsgBox(QtGui.QMessageBox.Warning, *args, **kargs)

def ErrorMsgBox(*args, **kargs):
    return CommonMsgBox(QtGui.QMessageBox.Critical, *args, **kargs)

def QuestionMsgBox(*args, **kargs):
    return CommonMsgBox(QtGui.QMessageBox.Question, *args, **kargs)

class CustomPrompt(QtGui.QMessageBox):
    def __init__(self, title, message, parent, choices, default=None,
                 esc=None, files=None):
        QtGui.QMessageBox.__init__(self, parent)

        self.setWindowTitle(hglib.toutf(title))
        self.setText(hglib.toutf(message))
        if files:
            msg = ''
            for i, file in enumerate(files):
                msg += '   %s\n' % file
                if i == 9:
                    msg += '   ...\n'
                    break
            self.setDetailedText(hglib.toutf(msg))
        self.hotkeys = {}
        for i, s in enumerate(choices):
            btn = self.addButton(s, QtGui.QMessageBox.AcceptRole)
            try:
                char = s[s.index('&')+1].lower()
                self.hotkeys[char] = btn
                if default == i:
                    self.setDefaultButton(btn)
                if esc == i:
                    self.setEscapeButton(btn)
            except ValueError:
                pass

    def run(self):
        return self.exec_()

    def keyPressEvent(self, event):
        for k, btn in self.hotkeys.iteritems():
            if event.text() == k:
                btn.emit(QtCore.SIGNAL('clicked()'))
        super(CustomPrompt, self).keyPressEvent(event)

def setup_font_substitutions():
    QtGui.QFont.insertSubstitutions('monospace', ['monaco', 'courier new'])

class PMButton(QtGui.QPushButton):
    """Toggle button with plus/minus icon images"""

    def __init__(self, expanded=True, parent=None):
        QtGui.QPushButton.__init__(self, parent)

        size = QtCore.QSize(11, 11)
        self.setIconSize(size)
        self.setMaximumSize(size)
        self.setFlat(True)

        self.plus = geticon('plus')
        self.minus = geticon('minus')
        icon = expanded and self.minus or self.plus
        self.setIcon(icon)

        def clicked():
            icon = self.is_expanded() and self.plus or self.minus
            self.setIcon(icon)
        self.clicked.connect(clicked)

    def set_expanded(self, state=True):
        icon = state and self.minus or self.plus
        self.setIcon(icon)

    def set_collapsed(self, state=True):
        icon = state and self.plus or self.minus
        self.setIcon(icon)

    def is_expanded(self):
        return self.icon().serialNumber() == self.minus.serialNumber()

    def is_collapsed(self):
        return not self.is_expanded()

def fileEditor(filename):
    'Open a simple modal file editing dialog'
    dialog = QtGui.QDialog()
    vbox = QtGui.QVBoxLayout()
    dialog.setLayout(vbox)
    editor = qsci()
    editor.setBraceMatching(qsci.SloppyBraceMatch)
    vbox.addWidget(editor)
    BB = QtGui.QDialogButtonBox
    bb = QtGui.QDialogButtonBox(BB.Save|BB.Cancel)
    dialog.connect(bb, QtCore.SIGNAL('accepted()'),
                   dialog, QtCore.SLOT('accept()'))
    dialog.connect(bb, QtCore.SIGNAL('rejected()'),
                   dialog, QtCore.SLOT('reject()'))
    vbox.addWidget(bb)
    lexer = Qsci.QsciLexerProperties()
    editor.setLexer(lexer)
    s = QtCore.QSettings()
    ret = QtGui.QDialog.Rejected
    try:
        contents = open(filename, 'rb').read()
        dialog.setWindowTitle(filename)
        geomname = 'editor-geom'
        editor.setText(contents)
        editor.setModified(False)
        dialog.restoreGeometry(s.value(geomname).toByteArray())
        ret = dialog.exec_()
        if ret == QtGui.QDialog.Accepted:
            f = util.atomictempfile(filename, 'w', createmode=None)
            f.write(editor.text())
            f.rename()
        s.setValue(geomname, dialog.saveGeometry())
    except EnvironmentError, e:
        qtlib.WarningMsgBox(_('Unable to read/write config file'),
               hglib.tounicode(e), parent=dialog)
    return ret

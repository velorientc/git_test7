# qtlib.py - Qt utility code
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os
import atexit
import shutil
import tempfile

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qsci import *
from mercurial import extensions, util

from tortoisehg.util import hglib, paths
from tortoisehg.hgqt.i18n import _
from hgext.color import _styles

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

_thgstyles = {
   # Styles defined by TortoiseHg
   'log.branch': 'black #aaffaa_background',
   'log.patch': 'black #aaddff_background',
   'log.unapplied_patch': 'black #dddddd_background',
   'log.tag': 'black #ffffaa_background',
   'log.modified': 'black #ffddaa_background',
   'log.added': 'black #aaffaa_background',
   'log.removed': 'black #ffcccc_background',
   'ui.error': 'red bold',
   'control': 'black bold',
}

thgstylesheet = '* { white-space: pre; font-family: monospace; font-size: 9pt; }'

"""app-global stylesheet"""
appstylesheet = '''
/* expander-like check box: checkbox.setProperty('expander', True) */
QCheckBox[expander="true"]::indicator:unchecked { image: url(:/icons/plus.png); }
QCheckBox[expander="true"]::indicator:checked { image: url(:/icons/minus.png); }
'''

def configstyles(ui):
    # extensions may provide more labels and default effects
    for name, ext in extensions.extensions():
        _styles.update(getattr(ext, 'colortable', {}))

    # tortoisehg defines a few labels and default effects
    _styles.update(_thgstyles)

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
            elif e.endswith('_background'):
                e = e[:-11]
                if e.startswith('#') or e in QColor.colorNames():
                    effects.append('background-color: ' + e)
            elif e.startswith('#') or e in QColor.colorNames():
                # Accept any valid QColor
                effects.append('color: ' + e)
    return ';'.join(effects)

def applyeffects(chars, effects):
    return '<span style="white-space: pre;%s">%s</span>' % (effects, chars)

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
        if name in NAME_MAP:
            name = NAME_MAP[name]
        style[name] = value
    style = ';'.join(['%s: %s' % t for t in style.items()])
    msg = hglib.tounicode(msg)
    msg = Qt.escape(msg)
    msg = msg.replace('\n', '<br />')
    return '<span style="%s">%s</span>' % (style, msg)

_iconcache = {}

def geticon(name):
    """
    Return a QIcon for the specified name. (the given 'name' parameter
    must *not* provide the extension).

    This searches for the icon from Qt resource or icons directory,
    named as 'name.(svg|png|ico)'.
    """
    # TODO: icons should be placed at single location before release
    def findicon(name):
        for pfx in (':/icons', os.path.join(paths.get_icon_path(), 'svg'),
                    paths.get_icon_path()):
            for ext in ('svg', 'png', 'ico'):
                path = '%s/%s.%s' % (pfx, name, ext)
                if QFile.exists(path):
                    return QIcon(path)

        return QIcon(':/icons/fallback.svg')

    try:
        return _iconcache[name]
    except KeyError:
        _iconcache[name] = findicon(name)
        return _iconcache[name]

_pixmapcache = {}

def getpixmap(name, width=16, height=16):
    key = '%s_%sx%s' % (name, width, height)
    try:
        return _pixmapcache[key]
    except KeyError:
        pixmap = geticon(name).pixmap(width, height)
    _pixmapcache[key] = pixmap
    return pixmap

class ThgFont(QObject):
    changed = pyqtSignal(QFont)
    def __init__(self, name):
        QObject.__init__(self)
        self.myfont = QFont()
        self.myfont.fromString(name)
    def font(self):
        return self.myfont
    def setFont(self, f):
        self.myfont = f
        self.changed.emit(f)

_fontdefaults = {
    'fontcomment': 'monospace,10',
    'fontdiff': 'monospace,10',
    'fontlist': 'sans,9',
    'fontlog': 'monospace,10'
}
_fontcache = {}
def getfont(ui, name):
    assert name in _fontdefaults
    if name not in _fontcache:
        fname = ui.config('tortoisehg', name, _fontdefaults[name])
        _fontcache[name] = ThgFont(fname)
    return _fontcache[name]

def CommonMsgBox(icon, title, main, text='', buttons=QMessageBox.Close,
                 labels=[], parent=None, defaultbutton=None):
    msg = QMessageBox(parent)
    msg.setIcon(icon)
    msg.setWindowTitle(title)
    msg.setStandardButtons(buttons)
    for button_id, label in labels:
        msg.setButtonText(button_id, label)
    if defaultbutton:
        msg.setDefaultButton(defaultbutton)
    msg.setText('<b>%s</b>' % main)
    info = ''
    for line in text.split('\n'):
        info += '<nobr>%s</nobr><br />' % line
    msg.setInformativeText(info)
    return msg.exec_()

def InfoMsgBox(*args, **kargs):
    return CommonMsgBox(QMessageBox.Information, *args, **kargs)

def WarningMsgBox(*args, **kargs):
    return CommonMsgBox(QMessageBox.Warning, *args, **kargs)

def ErrorMsgBox(*args, **kargs):
    return CommonMsgBox(QMessageBox.Critical, *args, **kargs)

def QuestionMsgBox(*args, **kargs):
    btn = QMessageBox.Yes | QMessageBox.No
    res = CommonMsgBox(QMessageBox.Question, buttons=btn, *args, **kargs)
    return res == QMessageBox.Yes

class CustomPrompt(QMessageBox):
    def __init__(self, title, message, parent, choices, default=None,
                 esc=None, files=None):
        QMessageBox.__init__(self, parent)

        self.setWindowTitle(hglib.tounicode(title))
        self.setText(hglib.tounicode(message))
        if files:
            self.setDetailedText(hglib.tounicode('\n'.join(files)))
        self.hotkeys = {}
        for i, s in enumerate(choices):
            btn = self.addButton(s, QMessageBox.AcceptRole)
            try:
                char = s[s.index('&')+1].lower()
                self.hotkeys[char] = btn
                if default == i:
                    self.setDefaultButton(btn)
                if esc == i:
                    self.setEscapeButton(btn)
            except (ValueError, IndexError):
                pass

    def run(self):
        return self.exec_()

    def keyPressEvent(self, event):
        for k, btn in self.hotkeys.iteritems():
            if event.text() == k:
                btn.clicked.emit()
        super(CustomPrompt, self).keyPressEvent(event)

def setup_font_substitutions():
    QFont.insertSubstitutions('monospace', ['monaco', 'courier new'])

class PMButton(QPushButton):
    """Toggle button with plus/minus icon images"""

    def __init__(self, expanded=True, parent=None):
        QPushButton.__init__(self, parent)

        size = QSize(11, 11)
        self.setIconSize(size)
        self.setMaximumSize(size)
        self.setFlat(True)
        self.setAutoDefault(False)

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

class ClickableLabel(QLabel):

    clicked = pyqtSignal()

    def __init__(self, label, parent=None):
        QLabel.__init__(self, parent)

        self.setText(label)

    def mouseReleaseEvent(self, event):
        self.clicked.emit()

class ExpanderLabel(QWidget):

    expanded = pyqtSignal(bool)

    def __init__(self, label, expanded=True, stretch=True, parent=None):
        QWidget.__init__(self, parent)

        box = QHBoxLayout()
        box.setSpacing(4)
        box.setContentsMargins(*(0,)*4)
        self.button = PMButton(expanded, self)
        self.button.clicked.connect(self.pm_clicked)
        box.addWidget(self.button)
        self.label = ClickableLabel(label, self)
        self.label.clicked.connect(lambda: self.button.click())
        box.addWidget(self.label)
        if not stretch:
            box.addStretch(0)

        self.setLayout(box)

    def pm_clicked(self):
        self.expanded.emit(self.button.is_expanded())

class StatusLabel(QWidget):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)

        box = QHBoxLayout()
        box.setContentsMargins(*(0,)*4)
        self.status_icon = QLabel()
        self.status_icon.setMaximumSize(16, 16)
        self.status_icon.setAlignment(Qt.AlignCenter)
        box.addWidget(self.status_icon)
        self.status_text = QLabel()
        self.status_text.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        box.addWidget(self.status_text)
        box.addStretch(0)

        self.setLayout(box)

    def set_status(self, text, icon=None):
        self.set_text(text)
        self.set_icon(icon)

    def clear_status(self):
        self.clear_text()
        self.clear_icon()

    def set_text(self, text=''):
        if text is None:
            text = ''
        self.status_text.setText(text)

    def clear_text(self):
        self.set_text()

    def set_icon(self, icon=None):
        if icon is None:
            self.clear_icon()
        else:
            if isinstance(icon, bool):
                pixmap = icon and getpixmap('success') or getpixmap('error')
            elif isinstance(icon, basestring):
                pixmap = getpixmap(icon)
            elif isinstance(icon, QIcon):
                pixmap = icon.pixmap(16, 16)
            elif isinstance(icon, QPixmap):
                pixmap = icon
            else:
                raise TypeError, '%s: bool, str, QIcon or QPixmap' % type(icon)
            self.status_icon.setShown(True)
            self.status_icon.setPixmap(pixmap)

    def clear_icon(self):
        self.status_icon.setHidden(True)

class LabeledSeparator(QWidget):

    def __init__(self, label=None, parent=None):
        QWidget.__init__(self, parent)

        box = QHBoxLayout()
        box.setContentsMargins(*(0,)*4)

        if label:
            if isinstance(label, basestring):
                label = QLabel(label)
            box.addWidget(label)

        sep = QFrame()
        sep.setFrameShadow(QFrame.Sunken)
        sep.setFrameShape(QFrame.HLine)
        box.addWidget(sep, 1, Qt.AlignVCenter)

        self.setLayout(box)

class WidgetGroups(object):
    """ Support for bulk-updating properties of Qt widgets """

    def __init__(self):
        object.__init__(self)

        self.clear(all=True)

    ### Public Methods ###

    def add(self, widget, group='default'):
        if group not in self.groups:
            self.groups[group] = []
        widgets = self.groups[group]
        if widget not in widgets:
            widgets.append(widget)

    def remove(self, widget, group='default'):
        if group not in self.groups:
            return
        widgets = self.groups[group]
        if widget in widgets:
            widgets.remove(widget)

    def clear(self, group='default', all=True):
        if all:
            self.groups = {}
        else:
            del self.groups[group]

    def set_prop(self, prop, value, group='default', cond=None):
        if group not in self.groups:
            return
        widgets = self.groups[group]
        if callable(cond):
            widgets = [w for w in widgets if cond(w)]
        for widget in widgets:
            getattr(widget, prop)(value)

    def set_visible(self, *args, **kargs):
        self.set_prop('setVisible', *args, **kargs)

    def set_enable(self, *args, **kargs):
        self.set_prop('setEnabled', *args, **kargs)

def fileEditor(filename, **opts):
    'Open a simple modal file editing dialog'
    dialog = QDialog()
    dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
    vbox = QVBoxLayout()
    dialog.setLayout(vbox)
    editor = QsciScintilla()
    editor.setBraceMatching(QsciScintilla.SloppyBraceMatch)
    editor.setMarginLineNumbers(1, True)
    editor.setMarginWidth(1, '000')
    if opts.get('foldable'):
        editor.setFolding(QsciScintilla.BoxedTreeFoldStyle)
    vbox.addWidget(editor)
    BB = QDialogButtonBox
    bb = QDialogButtonBox(BB.Save|BB.Cancel)
    bb.accepted.connect(dialog.accept)
    bb.rejected.connect(dialog.reject)
    vbox.addWidget(bb)
    lexer = QsciLexerProperties()
    editor.setLexer(lexer)
    s = QSettings()
    ret = QDialog.Rejected
    try:
        contents = open(filename, 'rb').read()
        dialog.setWindowTitle(filename)
        geomname = 'editor-geom'
        editor.setText(contents)
        editor.setUtf8(True)
        editor.setModified(False)
        dialog.restoreGeometry(s.value(geomname).toByteArray())
        ret = dialog.exec_()
        if ret == QDialog.Accepted:
            f = util.atomictempfile(filename, 'wb', createmode=None)
            f.write(hglib.fromunicode(editor.text()))
            f.rename()
        s.setValue(geomname, dialog.saveGeometry())
    except EnvironmentError, e:
        WarningMsgBox(_('Unable to read/write config file'),
                      hglib.tounicode(e), parent=dialog)
    return ret

class SharedWidget(QWidget):
    """Share a single widget by many parents

    It makes a widget sharable by many parent widgets. When the user shows
    the widget (showEvent occured), it reparents the stored widget to the
    latest active widget.

    NOTE: This doesn't reconnect signals when the parent changed.
    So it's up to you if you want to emit signals only to the active parent.
    """
    parentChanged = pyqtSignal()

    def __init__(self, widget, parent=None):
        super(SharedWidget, self).__init__(parent)
        self._widget = widget
        vbox = QVBoxLayout()
        vbox.setContentsMargins(*(0,)*4)
        self.setLayout(vbox)

    def showEvent(self, event):
        """Change the parent of the stored widget if necessary"""
        if self._widget.parent() != self:
            self.layout().addWidget(self._widget)
            self.parentChanged.emit()
        super(SharedWidget, self).showEvent(event)

    def get(self):
        """Returns the stored widget"""
        return self._widget

    def __getattr__(self, name):
        return getattr(self._widget, name)


class DemandWidget(QWidget):
    'Create a widget the first time it is shown'

    def __init__(self, createfunc, parent=None):
        super(DemandWidget, self).__init__(parent)
        self._createfunc = createfunc
        self._widget = None
        vbox = QVBoxLayout()
        vbox.setContentsMargins(*(0,)*4)
        self.setLayout(vbox)

    def showEvent(self, event):
        """create the widget if necessary"""
        self.get()
        super(DemandWidget, self).showEvent(event)

    def forward(self, funcname, *args, **opts):
        if self._widget:
            getattr(self._widget, funcname)(*args)
        return opts.get('default')

    def get(self):
        """Returns the stored widget"""
        if self._widget is None:
            self._widget = self._createfunc()
            self.layout().addWidget(self._widget)
        return self._widget

    def __getattr__(self, name):
        return getattr(self._widget, name)

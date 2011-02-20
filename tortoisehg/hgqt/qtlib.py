# qtlib.py - Qt utility code
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.

import os
import atexit
import shutil
import stat
import tempfile
import re

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from mercurial import extensions

from tortoisehg.util import hglib, paths
from hgext.color import _styles

tmproot = None
def gettempdir():
    global tmproot
    def cleanup():
        def writeable(arg, dirname, fnames):
            for fname in fnames:
                os.chmod(os.path.join(dirname, fname), stat.S_IWUSR)
        try:
            os.path.walk(tmproot, writeable, None)
            shutil.rmtree(tmproot)
        except:
            pass
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
   'log.bookmark': 'blue #ffffaa_background',
   'log.curbookmark': 'black #ffdd77_background',
   'log.modified': 'black #ffddaa_background',
   'log.added': 'black #aaffaa_background',
   'log.removed': 'black #ffcccc_background',
   'status.deleted': 'red bold',
   'ui.error': 'red bold #ffcccc_background',
   'control': 'black bold #dddddd_background',
}

thgstylesheet = '* { white-space: pre; font-family: monospace; font-size: 9pt; }'

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
    labels = str(labels) # Could be QString
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

def getbgcoloreffect(labels):
    """Map labels like "log.date" to background color if available

    Returns QColor object. You may need to check validity by isValid().
    """
    for l in str(labels).split():
        if not l:
            continue
        for e in _styles.get(l, '').split():
            if e.endswith('_background'):
                return QColor(e[:-11])
    return QColor()

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

def descriptionhtmlizer(ui):
    """Return a function to mark up ctx.description() as an HTML

    >>> from mercurial import ui
    >>> u = ui.ui()
    >>> htmlize = descriptionhtmlizer(u)
    >>> htmlize('foo <bar> \\n& <baz>')
    u'foo &lt;bar&gt; \\n&amp; &lt;baz&gt;'

    changeset hash link:
    >>> htmlize('foo af50a62e9c20 bar')
    u'foo <a href="cset:af50a62e9c20">af50a62e9c20</a> bar'
    >>> htmlize('af50a62e9c2040dcdaf61ba6a6400bb45ab56410') # doctest: +ELLIPSIS
    u'<a href="cset:af...10">af...10</a>'

    http/https links:
    >>> s = htmlize('foo http://example.com:8000/foo?bar=baz&bax#blah')
    >>> (s[:63], s[63:]) # doctest: +NORMALIZE_WHITESPACE
    (u'foo <a href="http://example.com:8000/foo?bar=baz&amp;bax#blah">',
     u'http://example.com:8000/foo?bar=baz&amp;bax#blah</a>')
    >>> htmlize('https://example/')
    u'<a href="https://example/">https://example/</a>'

    issue links:
    >>> u.setconfig('tortoisehg', 'issue.regex', r'#(\\d+)\\b')
    >>> u.setconfig('tortoisehg', 'issue.link', 'http://example/issue/{1}/')
    >>> htmlize = descriptionhtmlizer(u)
    >>> htmlize('foo #123')
    u'foo <a href="http://example/issue/123/">#123</a>'

    missing issue.link setting:
    >>> u.setconfig('tortoisehg', 'issue.link', '')
    >>> htmlize = descriptionhtmlizer(u)
    >>> htmlize('foo #123')
    u'foo #123'

    too many replacements in issue.link:
    >>> u.setconfig('tortoisehg', 'issue.link', 'http://example/issue/{1}/{2}')
    >>> htmlize = descriptionhtmlizer(u)
    >>> htmlize('foo #123')
    u'foo #123'

    invalid regexp in issue.regex:
    >>> u.setconfig('tortoisehg', 'issue.regex', '(')
    >>> htmlize = descriptionhtmlizer(u)
    >>> htmlize('foo #123')
    u'foo #123'
    >>> htmlize('http://example/')
    u'<a href="http://example/">http://example/</a>'
    """
    csmatch = r'(\b[0-9a-f]{12}(?:[0-9a-f]{28})?\b)'
    httpmatch = r'(\b(http|https)://([-A-Za-z0-9+&@#/%?=~_()|!:,.;]*[-A-Za-z0-9+&@#/%=~_()|]))'
    regexp = r'%s|%s' % (csmatch, httpmatch)
    bodyre = re.compile(regexp)

    issuematch = ui.config('tortoisehg', 'issue.regex')
    issuerepl = ui.config('tortoisehg', 'issue.link')
    if issuematch and issuerepl:
        regexp += '|(%s)' % issuematch
        try:
            bodyre = re.compile(regexp)
        except re.error:
            pass

    def htmlize(desc):
        """Mark up ctx.description() [localstr] as an HTML [unicode]"""
        desc = unicode(Qt.escape(hglib.tounicode(desc)))

        buf = ''
        pos = 0
        for m in bodyre.finditer(desc):
            a, b = m.span()
            if a >= pos:
                buf += desc[pos:a]
                pos = b
            groups = m.groups()
            if groups[0]:
                cslink = groups[0]
                buf += '<a href="cset:%s">%s</a>' % (cslink, cslink)
            if groups[1]:
                urllink = groups[1]
                buf += '<a href="%s">%s</a>' % (urllink, urllink)
            if len(groups) > 4 and groups[4]:
                issue = groups[4]
                issueparams = groups[4:]
                try:
                    link = re.sub(r'\{(\d+)\}',
                                  lambda m: issueparams[int(m.group(1))],
                                  issuerepl)
                    buf += '<a href="%s">%s</a>' % (link, issue)
                except IndexError:
                    buf += issue

        if pos < len(desc):
            buf += desc[pos:]

        return buf

    return htmlize

_iconcache = {}

def _findicon(name):
    # TODO: icons should be placed at single location before release
    for pfx in (':/icons', os.path.join(paths.get_icon_path(), 'svg'),
                paths.get_icon_path()):
        for ext in ('svg', 'png', 'ico'):
            path = '%s/%s.%s' % (pfx, name, ext)
            if QFile.exists(path):
                return QIcon(path)

    return None

# http://standards.freedesktop.org/icon-theme-spec/icon-theme-spec-latest.html
_SCALABLE_ICON_PATHS = [(QSize(), 'scalable/actions', '.svg'),
                        (QSize(), 'scalable/apps', '.svg'),
                        (QSize(22, 22), '22x22/actions', '.png'),
                        (QSize(24, 24), '24x24/actions', '.png')]

def _findscalableicon(name):
    """Find icon from qrc by using freedesktop-like icon lookup"""
    o = QIcon()
    for size, subdir, sfx in _SCALABLE_ICON_PATHS:
        path = ':/icons/%s/%s%s' % (subdir, name, sfx)
        if QFile.exists(path):
            for mode in (QIcon.Normal, QIcon.Active):
                o.addFile(path, size, mode)
    if not o.isNull():
        return o

def geticon(name):
    """
    Return a QIcon for the specified name. (the given 'name' parameter
    must *not* provide the extension).

    This searches for the icon from theme, Qt resource or icons directory,
    named as 'name.(svg|png|ico)'.
    """
    if QIcon.hasThemeIcon(name):
        return QIcon.fromTheme(name)

    try:
        return _iconcache[name]
    except KeyError:
        _iconcache[name] = (_findscalableicon(name) or _findicon(name)
                            or QIcon(':/icons/fallback.svg'))
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
    'fontlog': 'monospace,10',
    'fontoutputlog': 'sans,8'
}
_fontcache = {}

def initfontcache(ui):
    for name in _fontdefaults:
        fname = ui.config('tortoisehg', name, _fontdefaults[name])
        _fontcache[name] = ThgFont(fname)

def getfont(name):
    assert name in _fontdefaults
    return _fontcache[name]

def CommonMsgBox(icon, title, main, text='', buttons=QMessageBox.Ok,
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

def fix_application_font():
    if os.name != 'nt':
        return
    try:
        import win32gui, win32con
    except ImportError:
        return

    # On Windows, the font for main window seems to be determined by "icon"
    # font, but Qt chooses uncustomizable system font.
    lf = win32gui.SystemParametersInfo(win32con.SPI_GETICONTITLELOGFONT)
    f = QFont(hglib.tounicode(lf.lfFaceName))
    f.setItalic(lf.lfItalic)
    if lf.lfWeight != win32con.FW_DONTCARE:
        weights = [(0, QFont.Light), (400, QFont.Normal), (600, QFont.DemiBold),
                   (700, QFont.Bold), (800, QFont.Black)]
        n, w = filter(lambda e: e[0] <= lf.lfWeight, weights)[-1]
        f.setWeight(w)
    f.setPixelSize(abs(lf.lfHeight))
    QApplication.setFont(f, 'QMainWindow')

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

    def set_expanded(self, state=True):
        if not self.button.is_expanded() == state:
            self.button.set_expanded(state)
            self.expanded.emit(state)

    def is_expanded(self):
        return self.button.is_expanded()

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
                icon = geticon(icon and 'success' or 'error')
            elif isinstance(icon, basestring):
                icon = geticon(icon)
            elif not isinstance(icon, QIcon):
                raise TypeError, '%s: bool, str or QIcon' % type(icon)
            self.status_icon.setShown(True)
            self.status_icon.setPixmap(icon.pixmap(16, 16))

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

class SharedWidget(QWidget):
    """Share a single widget by many parents

    It makes a widget sharable by many parent widgets. When the user shows
    the widget (showEvent occured), it reparents the stored widget to the
    latest active widget.

    Any signals connected via SharedWidget are disconnected/connected
    automatically when owner changes.
    """

    def __init__(self, widget, parent=None):
        super(SharedWidget, self).__init__(parent)
        self._widget = widget
        self._fakesignals = {}
        vbox = QVBoxLayout()
        vbox.setContentsMargins(*(0,)*4)
        self.setLayout(vbox)

    def showEvent(self, event):
        """Change the parent of the stored widget if necessary"""
        if self._widget.parent() != self:
            self._reconnectfakesignals(self._widget.parent())
            self.layout().addWidget(self._widget)
        super(SharedWidget, self).showEvent(event)

    def get(self):
        """Returns the stored widget"""
        return self._widget

    def __getattr__(self, name):
        try:
            if isinstance(getattr(self._widget.__class__, name), pyqtSignal):
                return self._fakesignal(name)
        except AttributeError:
            pass
        return getattr(self._widget, name)

    class _FakeSignal(object):
        """Imitate pyqtSignal object to hook signal connection"""
        def __init__(self):
            self._connections = []

        def connect(self, slot):
            self._connections.append(slot)
            return True

        def disconnect(self, slot):
            try:
                self._connections.remove(slot)
                return True
            except ValueError:
                return False

    def _fakesignal(self, name):
        if name not in self._fakesignals:
            self._fakesignals[name] = self._FakeSignal()
        return self._fakesignals[name]

    def _iterfakeconnections(self):
        for name, fakesig in self._fakesignals.iteritems():
            for slot in fakesig._connections:
                yield name, slot

    def _connectfakesignals(self):
        for name, slot in self._iterfakeconnections():
            getattr(self._widget, name).connect(slot)

    def _disconnectfakesignals(self):
        for name, slot in self._iterfakeconnections():
            getattr(self._widget, name).disconnect(slot)

    def _reconnectfakesignals(self, curowner):
        if isinstance(curowner, self.__class__):
            curowner._disconnectfakesignals()
        self._connectfakesignals()

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
            return getattr(self._widget, funcname)(*args)
        return opts.get('default')

    def get(self):
        """Returns the stored widget"""
        if self._widget is None:
            self._widget = self._createfunc()
            self.layout().addWidget(self._widget)
        return self._widget

    def __getattr__(self, name):
        return getattr(self._widget, name)

# gtklib.py - miscellaneous PyGTK classes and functions for TortoiseHg
#
# Copyright 2008 TK Soh <teekaysoh@gmail.com>
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import sys
import gtk
import gobject
import pango

from tortoisehg.util.i18n import _
from tortoisehg.util import paths, hglib

from tortoisehg.hgtk import hgtk

if gtk.gtk_version < (2, 14, 0):
    # at least on 2.12.12, gtk widgets can be confused by control
    # char markups (like "&#x1;"), so use cgi.escape instead
    from cgi import escape as markup_escape_text
else:
    from gobject import markup_escape_text

def set_tortoise_icon(window, thgicon):
    ico = paths.get_tortoise_icon(thgicon)
    if ico: window.set_icon_from_file(ico)

def get_thg_modifier():
    if sys.platform == 'darwin':
        return '<Mod1>'
    else:
        return '<Control>'

def set_tortoise_keys(window):
    'Set default TortoiseHg keyboard accelerators'
    if sys.platform == 'darwin':
        mask = gtk.accelerator_get_default_mod_mask()
        mask |= gtk.gdk.MOD1_MASK;
        gtk.accelerator_set_default_mod_mask(mask)
    mod = get_thg_modifier()
    accelgroup = gtk.AccelGroup()
    window.add_accel_group(accelgroup)
    key, modifier = gtk.accelerator_parse(mod+'w')
    window.add_accelerator('thg-close', accelgroup, key, modifier,
            gtk.ACCEL_VISIBLE)
    key, modifier = gtk.accelerator_parse(mod+'q')
    window.add_accelerator('thg-exit', accelgroup, key, modifier,
            gtk.ACCEL_VISIBLE)
    key, modifier = gtk.accelerator_parse('F5')
    window.add_accelerator('thg-refresh', accelgroup, key, modifier,
            gtk.ACCEL_VISIBLE)
    key, modifier = gtk.accelerator_parse(mod+'Return')
    window.add_accelerator('thg-accept', accelgroup, key, modifier,
            gtk.ACCEL_VISIBLE)

    # connect ctrl-w and ctrl-q to every window
    window.connect('thg-close', thgclose)
    window.connect('thg-exit', thgexit)

def thgexit(window):
    if thgclose(window):
        gobject.idle_add(hgtk.thgexit, window)

def thgclose(window):
    if hasattr(window, 'should_live'):
        if window.should_live():
            return False
    window.destroy()
    return True

class StatusBar(gtk.HBox):
    def __init__(self, extra=None):
        gtk.HBox.__init__(self)
        self.pbar = gtk.ProgressBar()
        self.sttext = gtk.Label("")
        self.sttext.set_alignment(0, 0.5)

        self.pbox = gtk.HBox()
        self.pbox.pack_start(gtk.VSeparator(), False, False)
        self.pbox.pack_start(self.pbar, False, False)

        self.pack_start(self.sttext, padding=4)
        if extra:
            self.pack_end(extra, False, False)
        self.pack_end(self.pbox, False, False, padding=1)
        self.pbox.set_child_visible(False)
        self.show_all()

    def _pulse_timer(self, now=False):
        self.pbar.pulse()
        return True

    def begin(self, msg=_('Running'), timeout=100):
        self.pbox.set_child_visible(True)
        self.pbox.map()
        self.set_status_text(msg)
        self._timeout_event = gobject.timeout_add(timeout, self._pulse_timer)

    def end(self, msg='', unmap=True):
        gobject.source_remove(self._timeout_event)
        self.set_status_text(msg)
        if unmap:
            self.pbox.unmap()
        else:
            self.pbar.set_fraction(1.0)

    def set_status_text(self, msg):
        self.sttext.set_text(str(msg))

    def set_pulse_step(self, val):
        self.pbar.set_pulse_step(val)


class MessageDialog(gtk.Dialog):
    button_map = {
            gtk.BUTTONS_NONE: None,
            gtk.BUTTONS_OK: (gtk.STOCK_OK, gtk.RESPONSE_OK),
            gtk.BUTTONS_CLOSE : (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE),
            gtk.BUTTONS_CANCEL: (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL),
            gtk.BUTTONS_YES_NO : (gtk.STOCK_YES, gtk.RESPONSE_YES,
                    gtk.STOCK_NO, gtk.RESPONSE_NO),
            gtk.BUTTONS_OK_CANCEL: (gtk.STOCK_OK, gtk.RESPONSE_OK,
                    gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL),
    }
    image_map = {
            gtk.MESSAGE_INFO : gtk.STOCK_DIALOG_INFO,
            gtk.MESSAGE_WARNING : gtk.STOCK_DIALOG_WARNING,
            gtk.MESSAGE_QUESTION : gtk.STOCK_DIALOG_QUESTION,
            gtk.MESSAGE_ERROR : gtk.STOCK_DIALOG_ERROR,
    }

    def __init__(self, parent=None, flags=0, type=gtk.MESSAGE_INFO,
            buttons=gtk.BUTTONS_NONE, message_format=None):
        gtk.Dialog.__init__(self,
                parent=parent,
                flags=flags | gtk.DIALOG_NO_SEPARATOR,
                buttons=MessageDialog.button_map[buttons])
        self.set_resizable(False)

        hbox = gtk.HBox()
        self._image_frame = gtk.Frame()
        self._image_frame.set_shadow_type(gtk.SHADOW_NONE)
        self._image = gtk.Image()
        self._image.set_from_stock(MessageDialog.image_map[type],
                gtk.ICON_SIZE_DIALOG)
        self._image_frame.add(self._image)
        hbox.pack_start(self._image_frame, padding=5)

        lblbox = gtk.VBox(spacing=10)
        self._primary = gtk.Label("")
        self._primary.set_alignment(0.0, 0.5)
        self._primary.set_line_wrap(True)
        lblbox.pack_start(self._primary)

        self._secondary = gtk.Label()
        lblbox.pack_end(self._secondary)
        self._secondary.set_line_wrap(True)
        hbox.pack_start(lblbox, padding=5)

        self.vbox.pack_start(hbox, False, False, 10)
        self.show_all()

    def set_markup(self, s):
        self._primary.set_markup(s)

    def format_secondary_markup(self, message_format):
        self._secondary.set_markup(message_format)

    def format_secondary_text(self, message_format):
        self._secondary.set_text(message_format)

    def set_image(self, image):
        self._image_frame.remove(self._image)
        self._image = image
        self._image_frame.add(self._image)
        self._image.show()

class NativeSaveFileDialogWrapper:
    """Wrap the windows file dialog, or display default gtk dialog if
    that isn't available"""
    def __init__(self, InitialDir = None, Title = _('Save File'),
                 Filter = ((_('All files'), '*.*'),), FilterIndex = 1,
                 FileName = '', Open=False):
        if InitialDir == None:
            InitialDir = os.path.expanduser("~")
        self.InitialDir = InitialDir
        self.FileName = FileName
        self.Title = Title
        self.Filter = Filter
        self.FilterIndex = FilterIndex
        self.Open = Open

    def run(self):
        """run the file dialog, either return a file name, or False if
        the user aborted the dialog"""
        try:
            import win32gui, win32con, pywintypes
            return self.runWindows()
        except ImportError:
            return self.runCompatible()

    def runWindows(self):
        import win32gui, win32con, pywintypes
        cwd = os.getcwd()
        fname = None
        try:
            f = ''
            for name, mask in self.Filter:
                f += '\0'.join([name, mask,''])
            opts = dict(InitialDir=self.InitialDir,
                    Flags=win32con.OFN_EXPLORER,
                    File=self.FileName,
                    DefExt=None,
                    Title=hglib.fromutf(self.Title),
                    Filter= hglib.fromutf(f),
                    CustomFilter=None,
                    FilterIndex=self.FilterIndex)
            if self.Open:
                fname, _, _ = win32gui.GetOpenFileNameW(**opts)
            else:
                fname, _, _ = win32gui.GetSaveFileNameW(**opts)
            if fname:
                fname = os.path.abspath(fname)
        except pywintypes.error:
            pass
        os.chdir(cwd)
        return fname

    def runCompatible(self):
        if self.Open:
            action = gtk.FILE_CHOOSER_ACTION_OPEN
            buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                       gtk.STOCK_OPEN, gtk.RESPONSE_OK)
        else:
            action = gtk.FILE_CHOOSER_ACTION_SAVE
            buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                       gtk.STOCK_SAVE, gtk.RESPONSE_OK)
        dlg = gtk.FileChooserDialog(self.Title, None, action, buttons)
        dlg.set_do_overwrite_confirmation(True)
        dlg.set_default_response(gtk.RESPONSE_OK)
        dlg.set_current_folder(self.InitialDir)
        if not self.Open:
            dlg.set_current_name(self.FileName)
        for name, pattern in self.Filter:
            fi = gtk.FileFilter()
            fi.set_name(name)
            fi.add_pattern(pattern)
            dlg.add_filter(fi)
        if dlg.run() == gtk.RESPONSE_OK:
            result = dlg.get_filename();
        else:
            result = False
        dlg.destroy()
        return result

class NativeFolderSelectDialog:
    """Wrap the windows folder dialog, or display default gtk dialog if
    that isn't available"""
    def __init__(self, initial = None, title = _('Select Folder')):
        self.initial = initial or os.getcwd()
        self.title = title

    def run(self):
        """run the file dialog, either return a file name, or False if
        the user aborted the dialog"""
        try:
            import win32com, win32gui, pywintypes
            return self.runWindows()
        except ImportError, e:
            return self.runCompatible()

    def runWindows(self):
        from win32com.shell import shell, shellcon
        import win32gui, pywintypes

        def BrowseCallbackProc(hwnd, msg, lp, data):
            if msg== shellcon.BFFM_INITIALIZED:
                win32gui.SendMessage(hwnd, shellcon.BFFM_SETSELECTION, 1, data)
            elif msg == shellcon.BFFM_SELCHANGED:
                # Set the status text of the
                # For this message, 'lp' is the address of the PIDL.
                pidl = shell.AddressAsPIDL(lp)
                try:
                    path = shell.SHGetPathFromIDList(pidl)
                    win32gui.SendMessage(hwnd, shellcon.BFFM_SETSTATUSTEXT, 0, path)
                except shell.error:
                    # No path for this PIDL
                    pass

        fname = None
        try: 
            flags = shellcon.BIF_EDITBOX | 0x40  #shellcon.BIF_NEWDIALOGSTYLE
            pidl, _, _ = shell.SHBrowseForFolder(0,
                               None,
                               hglib.fromutf(self.title),
                               flags,
                               BrowseCallbackProc, # callback function
                               self.initial)       # 'data' param for the callback
            if pidl:
                fname = hglib.toutf(shell.SHGetPathFromIDList(pidl))
        except (pywintypes.error, pywintypes.com_error):
            pass
        return fname

    def runCompatible(self):
        dialog = gtk.FileChooserDialog(title=None,
                action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,
                         gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        dialog.set_default_response(gtk.RESPONSE_OK)
        response = dialog.run()
        fname = dialog.get_filename()
        dialog.destroy()
        if response == gtk.RESPONSE_OK:
            return fname
        return None

class LayoutTable(gtk.VBox):

    def __init__(self):
        gtk.VBox.__init__(self)

        self.table = gtk.Table(1, 2)
        self.pack_start(self.table)
        self.headers = []

        self.set_default_paddings()

    def set_default_paddings(self, xpad=-1, ypad=-1):
        self.xpad = xpad >= 0 and xpad or 4
        self.ypad = ypad >= 0 and ypad or 2

    def get_first_header(self):
        if len(self.headers) > 0:
            return self.headers[0]
        return None

    def add_row(self, *widgets, **kargs):
        if len(widgets) == 0:
            return
        t = self.table
        FLAG = gtk.FILL|gtk.EXPAND
        rows = t.get_property('n-rows')
        t.set_property('n-rows', rows + 1)
        expand = kargs.get('expand', False)
        xpad = kargs.get('xpad', self.xpad)
        ypad = kargs.get('ypad', self.ypad)
        def getwidget(obj):
            if obj == None:
                return gtk.Label('')
            elif isinstance(obj, (int, long)):
                lbl = gtk.Label('')
                lbl.set_size_request(obj, -1)
                lbl.size_request()
                return lbl
            elif isinstance(obj, basestring):
                lbl = gtk.Label(obj)
                return lbl
            return obj
        def pack(*widgets, **kargs):
            expand = kargs.get('expand', False)
            hbox = gtk.HBox()
            widgets = [ getwidget(w) for w in widgets ]
            if not expand:
                widgets.append(gtk.Label(''))
            rest, last = widgets[:-1], widgets[-1]
            for index, obj in enumerate(rest):
                widget = getwidget(obj)
                pad = index != 0 and 2 or 0
                hbox.pack_start(widget, False, False, pad)
            hbox.pack_start(last, 2)
            return hbox
        if len(widgets) == 1:
            cols = t.get_property('n-columns')
            widget = getwidget(widgets[0])
            widget = pack(widget, **kargs)
            t.attach(widget, 0, cols, rows, rows + 1, FLAG, 0, xpad, ypad)
        else:
            first = getwidget(widgets[0])
            if isinstance(first, gtk.Label):
                first.set_alignment(1, 0.5)
            t.attach(first, 0, 1, rows, rows + 1, gtk.FILL, 0, xpad, ypad)
            self.headers.append(first)
            rest = pack(*(widgets[1:]), **kargs)
            t.attach(rest, 1, 2, rows, rows + 1, FLAG, 0, xpad, ypad)

def addspellcheck(textview, ui=None):
    lang = None
    if ui:
        lang = ui.config('tortoisehg', 'spellcheck', None)
    try:
        import gtkspell
        gtkspell.Spell(textview, lang)
    except ImportError:
        pass
    except Exception, e:
        print e
    else:
        def selectlang(senderitem):
            from tortoisehg.hgtk import dialog
            spell = gtkspell.get_from_text_view(textview)
            lang = ''
            while True:
                msg = _('Select language for spell checking.\n\n'
                        'Empty is for the default language.\n'
                        'When all text is highlited, the dictionary\n'
                        'is probably not installed.\n\n'
                        'examples: en, en_GB, en_US')
                if lang:
                    msg = _('Lang "%s" can not be set.\n') % lang + msg
                lang = dialog.entry_dialog(None, msg)
                if lang is None: # cancel
                    return
                lang = lang.strip()
                if not lang:
                    lang = None # set default language from $LANG
                try:
                    spell.set_language(lang)
                    return
                except Exception, e:
                    pass
        def langmenu(textview, menu):
            item = gtk.MenuItem(_('Spell Check Language'))
            item.connect('activate', selectlang)
            menuitems = menu.get_children()[:2]
            x = menuitems[0].get_submenu()
            if len(menuitems) >= 2 and menuitems[1].get_child() is None and menuitems[0].get_submenu():
                # the spellcheck language menu seems to be at the top
                menu.insert(item, 1)
            else:
                sep = gtk.SeparatorMenuItem()
                sep.show()
                menu.append(sep)
                menu.append(item)
            item.show()
        textview.connect('populate-popup', langmenu)

def hasspellcheck():
    try:
        import gtkspell
        gtkspell.Spell
        return True
    except ImportError:
        return False

#
# miscellaneous PyGTK classes and functions for TortoiseHg
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import os
import sys
import gtk
import gobject
import pango

from thgutil.i18n import _
from thgutil import paths, hglib

from hggtk import hgtk

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
        self.sttext.set_ellipsize(pango.ELLIPSIZE_END)
        self.sttext.set_alignment(0, 0.5)

        self.pbox = gtk.HBox()
        self.pbox.pack_start(gtk.VSeparator(), False, False)
        self.pbox.pack_start(self.pbar, False, False)

        self.pack_start(self.sttext, padding=1)
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

    def end(self, msg=_('Done'), unmap=True):
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
                 Filter = {"All files": "*.*"}, FilterIndex = 1, FileName = ''):
        if InitialDir == None:
            InitialDir = os.path.expanduser("~")
        self.InitialDir = InitialDir
        self.FileName = FileName
        self.Title = Title
        self.Filter = Filter
        self.FilterIndex = FilterIndex

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
        try:
            fname, customfilter, flags=win32gui.GetSaveFileNameW(
                InitialDir=self.InitialDir,
                Flags=win32con.OFN_EXPLORER,
                File=self.FileName,
                DefExt=None,
                Title=hglib.fromutf(self.Title),
                Filter='',
                CustomFilter='',
                FilterIndex=1)
            if fname:
                return fname
        except pywintypes.error:
            pass
        return False

    def runCompatible(self):
        file_save = gtk.FileChooserDialog(self.Title, None,
                gtk.FILE_CHOOSER_ACTION_SAVE,
                (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                 gtk.STOCK_SAVE, gtk.RESPONSE_OK))
        file_save.set_do_overwrite_confirmation(True)
        file_save.set_default_response(gtk.RESPONSE_OK)
        file_save.set_current_folder(self.InitialDir)
        file_save.set_current_name(self.FileName)
        for name, pattern in self.Filter.iteritems():
            fi = gtk.FileFilter()
            fi.set_name(name)
            fi.add_pattern(pattern)
            file_save.add_filter(fi)
        if file_save.run() == gtk.RESPONSE_OK:
            result = file_save.get_filename();
        else:
            result = False
        file_save.destroy()
        return result

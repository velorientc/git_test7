# hgcmd.py - A simple dialog to execute random command for TortoiseHg
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import gobject
import pango
import os
import Queue

from thgutil.i18n import _
from thgutil import shlib, hglib

from hggtk import gtklib, hgthread

class CmdDialog(gtk.Dialog):
    def __init__(self, cmdline, progressbar=True, width=520, height=400):
        if progressbar:
            title = 'hg ' + ' '.join(cmdline[1:])
        else:
            # use short title if progressbar is not in use.  The
            # calling code may not want to show the complete command
            title = 'hg ' + ' '.join(cmdline[1:2])
        if len(title) > 80:
            title = title[:80] + '...'
        title = hglib.toutf(title.replace('\n', ' '))
        gtk.Dialog.__init__(self,
                            title=title,
                            flags=gtk.DIALOG_MODAL,
                            )

        gtklib.set_tortoise_icon(self, 'hg.ico')
        gtklib.set_tortoise_keys(self)
        self.cmdline = cmdline
        self.returncode = None
        self.hgthread = None

        self.set_default_size(width, height)

        self._button_stop = gtk.Button(_('Stop'))
        self._button_stop.connect('clicked', self._on_stop_clicked)
        self.action_area.pack_start(self._button_stop)

        self._button_ok = gtk.Button(_('Close'))
        self._button_ok.connect('clicked', self._on_ok_clicked)
        self.action_area.pack_start(self._button_ok)

        self.connect('thg-accept', self._on_ok_clicked)

        self.connect('delete-event', self._delete)
        self.connect('response', self._response)

        self.pbar = None
        if progressbar:
            self.last_pbar_update = 0

            hbox = gtk.HBox()

            self.status_text = gtk.Label()
            self.status_text.set_text(title)
            self.status_text.set_alignment(0, 0.5)
            self.status_text.set_ellipsize(pango.ELLIPSIZE_END)
            hbox.pack_start(self.status_text, True, True, 3)

            # Create a centering alignment object
            align = gtk.Alignment(0.0, 0.0, 1, 0)
            hbox.pack_end(align, False, False, 3)
            align.show()

            # create the progress bar
            self.pbar = gtk.ProgressBar()
            align.add(self.pbar)
            self.pbar.pulse()
            self.pbar.show()

            self.vbox.pack_start(hbox, False, False, 3)

        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.textview = gtk.TextView(buffer=None)
        self.textview.set_editable(False)
        self.textview.modify_font(pango.FontDescription('Monospace'))
        scrolledwindow.add(self.textview)
        self.textbuffer = self.textview.get_buffer()
        self.textbuffer.create_tag('error', weight=pango.WEIGHT_HEAVY,
                                   foreground='#900000')

        self.vbox.pack_start(scrolledwindow, True, True)
        self.connect('map_event', self._on_window_map_event)

        self.show_all()

    def _on_ok_clicked(self, button):
        """ Ok button clicked handler. """
        self.response(gtk.RESPONSE_ACCEPT)

    def _on_stop_clicked(self, button):
        if self.hgthread:
            self.hgthread.terminate()

    def _delete(self, widget, event):
        return True

    def _response(self, widget, response_id):
        if self.hgthread and self.hgthread.isAlive():
            widget.emit_stop_by_name('response')

    def _on_window_map_event(self, event, param):
        if self.hgthread is None:
            self.hgthread = hgthread.HgThread(self.cmdline[1:])
            self.hgthread.start()
            self._button_ok.set_sensitive(False)
            self._button_stop.set_sensitive(True)
            gobject.timeout_add(10, self.process_queue)

    def write(self, msg, append=True):
        msg = hglib.toutf(msg)
        if append:
            enditer = self.textbuffer.get_end_iter()
            self.textbuffer.insert(enditer, msg)
        else:
            self.textbuffer.set_text(msg)

    def process_queue(self):
        """
        Handle all the messages currently in the queue (if any).
        """
        self.hgthread.process_dialogs()
        enditer = self.textbuffer.get_end_iter()
        while self.hgthread.getqueue().qsize():
            try:
                msg = self.hgthread.getqueue().get(0)
                self.textbuffer.insert(enditer, hglib.toutf(msg))
                self.textview.scroll_to_mark(self.textbuffer.get_insert(), 0)
            except Queue.Empty:
                pass
        while self.hgthread.geterrqueue().qsize():
            try:
                msg = self.hgthread.geterrqueue().get(0)
                self.textbuffer.insert_with_tags_by_name(enditer, msg, 'error')
                self.textview.scroll_to_mark(self.textbuffer.get_insert(), 0)
            except Queue.Empty:
                pass
        self.update_progress()
        if not self.hgthread.isAlive():
            self._button_stop.set_sensitive(False)
            self._button_ok.set_sensitive(True)
            self._button_ok.grab_focus()
            self.returncode = self.hgthread.return_code()
            if self.returncode is None:
                self.write(_('\n[command interrupted]'))
            return False # Stop polling this function
        else:
            return True

    def update_progress(self):
        if not self.pbar:
            return          # progress bar not enabled

        if not self.hgthread.isAlive():
            self.pbar.unmap()
        else:
            # pulse the progress bar every ~100ms
            tm = shlib.get_system_times()[4]
            if tm - self.last_pbar_update < 0.100:
                return
            self.last_pbar_update = tm
            self.pbar.pulse()

    def return_code(self):
        if self.hgthread:
            return self.hgthread.return_code()
        else:
            return False

class CmdWidget(gtk.VBox):

    def __init__(self, textview=True, progressbar=True, buttons=False):
        gtk.VBox.__init__(self)

        self.hgthread = None

        # build UI
        if textview:
            cmdpane = gtk.ScrolledWindow()
            cmdpane.set_shadow_type(gtk.SHADOW_ETCHED_IN)
            cmdpane.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
            self.textview = gtk.TextView(buffer=None)
            self.textview.set_editable(False)
            self.textview.modify_font(pango.FontDescription('Monospace'))
            cmdpane.add(self.textview)
            self.textbuffer = self.textview.get_buffer()
            self.textbuffer.create_tag('error', weight=pango.WEIGHT_HEAVY,
                                       foreground='#900000')
            self.pack_start(cmdpane)

        if progressbar:
            self.last_pbar_update = 0

            self.progbox = progbox = gtk.HBox()
            self.pack_start(progbox)

            if buttons:
                img = gtk.Image()
                img.set_from_stock(gtk.STOCK_JUSTIFY_LEFT,
                                   gtk.ICON_SIZE_SMALL_TOOLBAR)
                self.popup_btn = gtk.Button()
                self.popup_btn.set_image(img)
                self.popup_btn.set_relief(gtk.RELIEF_NONE)
                self.popup_btn.set_focus_on_click(False)
                progbox.pack_start(self.popup_btn, False, False)

            self.pbar = gtk.ProgressBar()
            progbox.pack_start(self.pbar)

            if buttons:
                img = gtk.Image()
                img.set_from_stock(gtk.STOCK_STOP,
                                   gtk.ICON_SIZE_SMALL_TOOLBAR)
                self.stop_btn = gtk.Button()
                self.stop_btn.set_image(img)
                self.stop_btn.set_sensitive(False)
                self.stop_btn.set_relief(gtk.RELIEF_NONE)
                self.stop_btn.set_focus_on_click(False)
                self.stop_btn.connect('clicked', self.stop_clicked)
                progbox.pack_start(self.stop_btn, False, False)

            gobject.idle_add(lambda: self.enable_progressbar(False))

    ### public functions ###

    def execute(self, cmdline, callback, *args, **kargs):
        if self.hgthread and self.hgthread.isAlive():
            return
        if self.hgthread is None:
            self.hgthread = hgthread.HgThread(cmdline[1:])
            self.hgthread.start()
            self.stop_btn.set_sensitive(True)
            gobject.timeout_add(10, self.process_queue, callback, args, kargs)
            def is_done():
                # show progressbar if it's still working
                if self.hgthread and self.hgthread.isAlive():
                    self.enable_progressbar()
                return False
            gobject.timeout_add(500, is_done)

    def stop(self):
        if self.hgthread:
            self.hgthread.terminate()

    def enable_progressbar(self, visible=True):
        if hasattr(self, 'progbox'):
            self.progbox.set_property('visible', visible)

    def enable_buttons(self, popup=True, stop=True):
        if hasattr(self, 'popup_btn'):
            self.popup_btn.set_property('visible', popup)
        if hasattr(self, 'stop_btn'):
            self.stop_btn.set_property('visible', stop)

    ### internal use functions ###

    def update_progress(self):
        if not self.pbar:
            return
        if not self.hgthread.isAlive():
            self.pbar.set_fraction(0)
        else:
            # pulse the progress bar every ~100ms
            tm = shlib.get_system_times()[4]
            if tm - self.last_pbar_update < 0.100:
                return
            self.last_pbar_update = tm
            self.pbar.pulse()

    def process_queue(self, callback, args, kargs):
        """
        Handle all the messages currently in the queue (if any).
        """
        self.hgthread.process_dialogs()

        if hasattr(self, 'textbuffer'):
            enditer = self.textbuffer.get_end_iter()
            while self.hgthread.getqueue().qsize():
                try:
                    msg = self.hgthread.getqueue().get(0)
                    self.textbuffer.insert(enditer, hglib.toutf(msg))
                    self.textview.scroll_to_mark(self.textbuffer.get_insert(), 0)
                except Queue.Empty:
                    pass
            while self.hgthread.geterrqueue().qsize():
                try:
                    msg = self.hgthread.geterrqueue().get(0)
                    self.textbuffer.insert_with_tags_by_name(enditer, msg, 'error')
                    self.textview.scroll_to_mark(self.textbuffer.get_insert(), 0)
                except Queue.Empty:
                    pass
        self.update_progress()
        if not self.hgthread.isAlive():
            self.stop_btn.set_sensitive(False)
            self.enable_progressbar(False)
            returncode = self.hgthread.return_code()
            if returncode is None:
                self.write(_('\n[command interrupted]'))
            self.hgthread = None
            def call_callback():
                callback(returncode, *args, **kargs)
            gobject.idle_add(call_callback)
            return False # Stop polling this function
        else:
            return True # Continue polling

    def write(self, msg, append=True):
        if hasattr(self, 'textbuffer'):
            msg = hglib.toutf(msg)
            if append:
                enditer = self.textbuffer.get_end_iter()
                self.textbuffer.insert(enditer, msg)
            else:
                self.textbuffer.set_text(msg)

    ### signal handlers ###

    def stop_clicked(self, button):
        self.stop()

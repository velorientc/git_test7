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
    def __init__(self, cmdline, progressbar=True):
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

        self.set_default_size(520, 400)

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

# CmdWidget style constans
STYLE_NORMAL  = 'normal'    # pbar + popup log viewer
STYLE_COMPACT = 'compact'   # pbar + log viewer

class CmdWidget(gtk.VBox):

    def __init__(self, style=STYLE_NORMAL):
        gtk.VBox.__init__(self)

        self.hgthread = None
        self.last_pbar_update = 0

        # log viewer
        if style == STYLE_NORMAL:
            self.log = CmdLogWidget()
            self.pack_start(log)
        elif style == STYLE_COMPACT:
            self.dlg = CmdLogDialog()
            self.log = self.dlg.get_logwidget()
        else:
            pass #FIXME should raise exception?

        # progress bar box
        self.progbox = progbox = gtk.HBox()
        self.pack_start(progbox)

        ## log button
        if style == STYLE_COMPACT:
            img = gtk.Image()
            img.set_from_stock(gtk.STOCK_JUSTIFY_LEFT,
                               gtk.ICON_SIZE_SMALL_TOOLBAR)
            self.log_btn = gtk.Button()
            self.log_btn.set_image(img)
            self.log_btn.set_relief(gtk.RELIEF_NONE)
            self.log_btn.set_focus_on_click(False)
            self.log_btn.connect('clicked', self.log_clicked)
            progbox.pack_start(self.log_btn, False, False)

        ## progress bar
        self.pbar = gtk.ProgressBar()
        progbox.pack_start(self.pbar)

        ## stop & close buttons
        if style == STYLE_COMPACT:
            img = gtk.Image()
            img.set_from_stock(gtk.STOCK_STOP,
                               gtk.ICON_SIZE_SMALL_TOOLBAR)
            self.stop_btn = gtk.Button()
            self.stop_btn.set_image(img)
            self.stop_btn.set_relief(gtk.RELIEF_NONE)
            self.stop_btn.set_focus_on_click(False)
            self.stop_btn.connect('clicked', self.stop_clicked)
            progbox.pack_start(self.stop_btn, False, False)

            img = gtk.Image()
            img.set_from_stock(gtk.STOCK_CLOSE,
                               gtk.ICON_SIZE_SMALL_TOOLBAR)
            self.close_btn = gtk.Button()
            self.close_btn.set_image(img)
            self.close_btn.set_relief(gtk.RELIEF_NONE)
            self.close_btn.set_focus_on_click(False)
            self.close_btn.connect('clicked', self.close_clicked)
            progbox.pack_start(self.close_btn, False, False)

        def after_init():
            self.set_pbar(False)
            self.set_buttons(stop=False)
        gobject.idle_add(after_init)

    ### public functions ###

    def execute(self, cmdline, callback, *args, **kargs):
        """
        Execute passed command line using 'hgthread'.
        When the command terminated, callback function is called
        with return code. 

        cmdline: command line string.
        callback: function called after terminated the thread.

        def callback(returncode, ...)

        returncode: See the description of 'hgthread' about return code.
        """
        if self.hgthread and self.hgthread.isAlive():
            return
        if self.hgthread is None:
            # clear previous logs
            self.log.clear()

            # prepare UI
            self.set_buttons(stop=True, close=False)
            self.already_opened = self.get_pbar()
            if not self.already_opened:
                def is_done():
                    # show progress bar if it's still working
                    if self.hgthread and self.hgthread.isAlive():
                        self.set_pbar(True)
                    return False
                gobject.timeout_add(500, is_done)

            # thread start
            self.hgthread = hgthread.HgThread(cmdline[1:])
            self.hgthread.start()
            gobject.timeout_add(10, self.process_queue, callback, args, kargs)

    def stop(self):
        """
        Terminate the thread forcibly.
        """
        if self.hgthread:
            self.hgthread.terminate()
            self.set_pbar(True)
            self.set_buttons(stop=False, close=True)

    def set_pbar(self, visible):
        """
        Set visible property of the progress bar box.

        visible: if True, the progress bar box is shown.
        """
        if hasattr(self, 'progbox'):
            self.progbox.set_property('visible', visible)

    def get_pbar(self):
        """
        Return 'visible' property of the progress bar box.
        If not exists progress bar, it always returns False.
        """
        if hasattr(self, 'progbox'):
            return self.progbox.get_property('visible')
        return False

    def set_buttons(self, log=None, stop=None, close=None):
        """
        Set visible properties of buttons on the progress bar box.
        If omitted all argments, it does nothing.

        log: if True, log button is shown. (default: None)
        stop: if True, stop button is shown. (default: None)
        close: if True, close button is shown. (default: None)
        """
        if not log is None and hasattr(self, 'log_btn'):
            self.log_btn.set_property('visible', log)
        if not stop is None and hasattr(self, 'stop_btn'):
            self.stop_btn.set_property('visible', stop)
        if not close is None and hasattr(self, 'close_btn'):
            self.close_btn.set_property('visible', close)

    def show_log(self):
        """
        Show log viewer.
        """
        if hasattr(self, 'dlg'):
            if not self.dlg.get_property('visible'):
                self.dlg.show_all()
            else:
                self.dlg.present()

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
        # process queue
        self.hgthread.process_dialogs()

        # output to buffer
        while self.hgthread.getqueue().qsize():
            try:
                msg = self.hgthread.getqueue().get(0)
                self.log.append(hglib.toutf(msg))
            except Queue.Empty:
                pass
        while self.hgthread.geterrqueue().qsize():
            try:
                msg = self.hgthread.geterrqueue().get(0)
                self.log.append(hglib.toutf(msg), error=True)
            except Queue.Empty:
                pass

        # update progress bar
        self.update_progress()

        # check thread
        if not self.hgthread.isAlive():
            returncode = self.hgthread.return_code()
            if returncode == 0 and not self.already_opened:
                self.set_pbar(False)
            else:
                self.set_pbar(True)
                self.set_buttons(stop=False, close=True)
            if returncode is None:
                self.log.append(_('\n[command interrupted]'))
            self.hgthread = None
            def call_callback():
                callback(returncode, *args, **kargs)
            gobject.idle_add(call_callback)
            return False # Stop polling this function
        else:
            return True # Continue polling

    ### signal handlers ###

    def log_clicked(self, button):
        self.show_log()

    def stop_clicked(self, button):
        self.stop()

    def close_clicked(self, button):
        self.set_pbar(False)

class CmdLogWidget(gtk.VBox):

    def __init__(self):
        gtk.VBox.__init__(self)

        # scrolled pane
        pane = gtk.ScrolledWindow()
        pane.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        pane.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.add(pane)

        # log textview
        self.textview = gtk.TextView(buffer=None)
        self.textview.set_editable(False)
        self.textview.modify_font(pango.FontDescription('Monospace'))
        pane.add(self.textview)

        # text buffer
        self.buffer = self.textview.get_buffer()
        self.buffer.create_tag('error', weight=pango.WEIGHT_HEAVY,
                               foreground='#900000')

    ### public functions ###

    def append(self, text, error=False):
        """
        Insert the text to the end of TextView.

        text: string you want to append.
        error: if True, append text with 'error' tag. (default: False)
        """
        enditer = self.buffer.get_end_iter()
        if error:
            self.buffer.insert_with_tags_by_name(enditer, text, 'error')
        else:
            self.buffer.insert(enditer, text)
        self.textview.scroll_to_mark(self.buffer.get_insert(), 0)

    def clear(self):
        """
        Clear all text in TextView.
        """
        self.buffer.delete(self.buffer.get_start_iter(),
                           self.buffer.get_end_iter())

class CmdLogDialog(gtk.Window):

    def __init__(self, title=_('Command Log')):
        gtk.Window.__init__(self, type=gtk.WINDOW_TOPLEVEL)
        gtklib.set_tortoise_icon(self, 'hg.ico')
        self.set_title(title)
        self.set_default_size(320, 240)
        self.connect('delete-event', self.delete_event)

        # log viewer
        self.log = CmdLogWidget()
        self.add(self.log)

        # change window decorations
        self.realize()
        if self.window:
            self.window.set_decorations(gtk.gdk.DECOR_BORDER | \
                                        gtk.gdk.DECOR_RESIZEH | \
                                        gtk.gdk.DECOR_TITLE | \
                                        gtk.gdk.DECOR_MENU | \
                                        gtk.gdk.DECOR_MINIMIZE)

    ### public functions ###

    def get_logwidget(self):
        """
        Return CmdLogWidget instance.
        """
        return self.log

    ### signal handlers ###

    def delete_event(self, widget, event):
        self.hide()
        return True

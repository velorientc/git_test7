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
import sys
import threading
import Queue

from tortoisehg.util.i18n import _
from tortoisehg.util import shlib, hglib

from tortoisehg.hgtk import gtklib, hgthread

class CmdDialog(gtk.Dialog):
    def __init__(self, cmdline, progressbar=True, text=None):
        if type(cmdline) is tuple:
            self.cmdlist = list(cmdline)[1:]
            cmdline = cmdline[0]
        else:
            self.cmdlist = []
        title = text or ' '.join(cmdline)
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
        if self.hgthread:
            return

        # Replace stdout file descriptor with our own pipe
        def pollstdout(*args):
            while True:
                # blocking read of stdout pipe
                o = os.read(self.readfd, 1024)
                if o:
                    self.stdoutq.put(o)
                else:
                    break
        self.oldstdout = os.dup(sys.__stdout__.fileno())
        self.stdoutq = Queue.Queue()
        self.readfd, writefd = os.pipe()
        os.dup2(writefd, sys.__stdout__.fileno())
        thread = threading.Thread(target=pollstdout, args=[])
        thread.start()

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
        while self.stdoutq.qsize():
            try:
                msg = self.stdoutq.get(0)
                self.textbuffer.insert_with_tags_by_name(enditer, msg, 'error')
                self.textview.scroll_to_mark(self.textbuffer.get_insert(), 0)
            except Queue.Empty:
                pass

        self.update_progress()
        if not self.hgthread.isAlive():
            self.returncode = self.hgthread.return_code()
            if self.returncode is None:
                self.write(_('\n[command interrupted]'))
            elif self.returncode == 0 and self.cmdlist:
                cmdline = self.cmdlist.pop(0)
                text = '\n' + hglib.toutf(' '.join(cmdline)) + '\n'
                self.textbuffer.insert(enditer, text)
                self.textview.scroll_to_mark(self.textbuffer.get_insert(), 0)
                self.hgthread = hgthread.HgThread(cmdline[1:])
                self.hgthread.start()
                return True
            self._button_stop.set_sensitive(False)
            self._button_ok.set_sensitive(True)
            self._button_ok.grab_focus()
            os.dup2(self.oldstdout, sys.__stdout__.fileno())
            os.close(self.oldstdout)
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

# CmdWidget style constants
STYLE_NORMAL  = 'normal'    # pbar + embedded log viewer
STYLE_COMPACT = 'compact'   # pbar + popup log viewer

class CmdWidget(gtk.VBox):

    def __init__(self, style=STYLE_NORMAL):
        gtk.VBox.__init__(self)

        self.hgthread = None
        self.last_pbar_update = 0
        self.is_normal = style == STYLE_NORMAL
        self.is_compact = style == STYLE_COMPACT

        # log viewer
        if self.is_normal:
            self.log = CmdLogWidget()
            self.log.set_size_request(640, 320)
            self.log.size_request()
            self.pack_start(self.log)
        elif self.is_compact:
            self.dlg = CmdLogDialog()
            def close_hook(dialog):
                self.show_log(False)
                return False
            self.dlg.set_close_hook(close_hook)
            self.log = self.dlg.get_logwidget()
        else:
            raise _('unknown CmdWidget style: %s') % style

        # progress bar box
        self.progbox = progbox = gtk.HBox()
        self.pack_start(progbox)

        def add_button(stock, handler):
            img = gtk.Image()
            img.set_from_stock(stock, gtk.ICON_SIZE_SMALL_TOOLBAR)
            btn = gtk.ToggleButton()
            btn.set_image(img)
            btn.set_relief(gtk.RELIEF_NONE)
            btn.set_focus_on_click(False)
            btn.connect('clicked', handler)
            progbox.pack_start(btn, False, False)
            return btn

        ## log button
        self.log_btn = add_button(gtk.STOCK_JUSTIFY_LEFT, self.log_toggled)

        ## progress bar
        self.pbar = gtk.ProgressBar()
        progbox.pack_start(self.pbar)

        ## stop & close buttons
        if self.is_compact:
            self.stop_btn = add_button(gtk.STOCK_STOP, self.stop_clicked)
            self.close_btn = add_button(gtk.STOCK_CLOSE, self.close_clicked)

        def after_init():
            self.set_buttons(stop=False)
            if self.is_normal:
                self.show_log(False)
            if self.is_compact:
                self.set_pbar(False)
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
        if self.hgthread:
            return

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

    def is_alive(self):
        return self.hgthread and self.hgthread.isAlive()

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

    def show_log(self, visible=True):
        """
        Show/hide log viewer.
        """
        if self.is_normal:
            self.log.set_property('visible', visible)
        elif self.is_compact:
            if visible:
                if self.dlg.get_property('visible'):
                    self.dlg.present()
                else:
                    self.dlg.show_all()
            else:
                self.dlg.hide()
        else:
            raise _('invalid state')

        # change toggle button state
        if self.log_btn.get_active() != visible:
            self.log_btn.handler_block_by_func(self.log_toggled)
            self.log_btn.set_active(visible)
            self.log_btn.handler_unblock_by_func(self.log_toggled)

    def is_show_log(self):
        """
        Return visible state of log viewer.
        """
        if self.is_normal:
            return self.log.get_property('visible')
        elif self.is_compact:
            return self.dlg.get_property('visible')
        else:
            raise _('invalid state')

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
            if not returncode == 0:
                self.show_log()
            self.hgthread = None
            def call_callback():
                callback(returncode, *args, **kargs)
            gobject.idle_add(call_callback)
            return False # Stop polling this function
        else:
            return True # Continue polling

    ### signal handlers ###

    def log_toggled(self, button):
        self.show_log(button.get_active())

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

    def set_close_hook(self, hook):
        """
        Set hook function.

        hook: the function called on closing this dialog.

        def close_hook(dialog)

        where 'dialog' is the instance of CmdLogDialog class.
        The hook function should return True or False.
        By returning True, you can prevent closing/hiding the dialog.
        """
        self.close_hook = hook

    ### signal handlers ###

    def delete_event(self, widget, event):
        if hasattr(self, 'close_hook'):
            if self.close_hook(self):
                self.hide()
        return True

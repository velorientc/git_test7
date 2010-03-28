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
import Queue
import urllib
import threading

from mercurial import util

from tortoisehg.util.i18n import _
from tortoisehg.util import paths, hglib, thread2

from tortoisehg.hgtk import hgtk

if gtk.gtk_version < (2, 14, 0):
    # at least on 2.12.12, gtk widgets can be confused by control
    # char markups (like "&#x1;"), so use cgi.escape instead
    from cgi import escape as markup_escape_text
else:
    from gobject import markup_escape_text

if gobject.pygobject_version <= (2,12,1):
    # http://www.mail-archive.com/tortoisehg-develop@lists.sourceforge.net/msg06900.html
    raise Exception('incompatible version of gobject')

# common colors

DRED = '#900000'
DGREEN = '#006400'
DBLUE = '#000090'

PRED = '#ffcccc'
PGREEN = '#aaffaa'
PBLUE = '#aaddff'
PYELLOW = '#ffffaa'
PORANGE = '#ffddaa'

def set_tortoise_icon(window, thgicon):
    ico = paths.get_tortoise_icon(thgicon)
    if ico: window.set_icon_from_file(ico)

def get_thg_modifier():
    if sys.platform == 'darwin':
        return '<Mod1>'
    else:
        return '<Control>'

def add_accelerator(widget, signal, accelgroup, accelerator,
                    accel_flags=gtk.ACCEL_VISIBLE):
    """Add an accelerator for signal to widget.

    accelerator is the key string parsed by gtk.accelerator_parse; the
    other parameters are passed to gtk.Widget.add_accelerator"""
    key, modifier = gtk.accelerator_parse(accelerator)
    widget.add_accelerator(signal, accelgroup, key, modifier, accel_flags)

def set_tortoise_keys(window, connect=True):
    'Set default TortoiseHg keyboard accelerators'
    if sys.platform == 'darwin':
        mask = gtk.accelerator_get_default_mod_mask()
        mask |= gtk.gdk.MOD1_MASK;
        gtk.accelerator_set_default_mod_mask(mask)
    mod = get_thg_modifier()
    accelgroup = gtk.AccelGroup()
    window.add_accel_group(accelgroup)

    default_accelerators = [
        (mod+'w', 'thg-close'),
        (mod+'q', 'thg-exit'),
        ('F5', 'thg-refresh'),
        (mod+'r', 'thg-refresh'),
        (mod+'Return', 'thg-accept'),
    ]

    for accelerator, signal in default_accelerators:
        add_accelerator(window, signal, accelgroup, accelerator)

    # connect ctrl-w and ctrl-q to every window
    if connect:
        window.connect('thg-close', thgclose)
        window.connect('thg-exit', thgexit)

    return accelgroup, mod

def thgexit(window):
    if thgclose(window):
        gobject.idle_add(hgtk.thgexit, window)

def thgclose(window):
    if hasattr(window, 'should_live'):
        if window.should_live():
            return False
    window.destroy()
    return True

def move_treeview_selection(window, treeview, distance=1):
    """Accelerator handler to move a treeview's cursor and selection

    Moves the treeview's cursor by distance and selects the row on which
    the cursor lands.

    distance: an integer number of rows to move the cursor, positive to
              move the selection down, negative for up.  A distance of
              0 will reset the selection to the current row."""
    row = 0
    path = treeview.get_cursor()[0]
    if path:
        row = path[0]
    model = treeview.get_model()

    # make sure new row is within bounds
    new_row = min((row + distance), len(model) - 1)
    new_row = max(0, new_row)

    selected = model.get_iter_from_string(str(new_row))
    selection = treeview.get_selection()
    selection.unselect_all()
    selection.select_iter(selected)
    treeview.set_cursor(model.get_path(selected))

_renderer = gtk.HBox()
def get_icon_pixbuf(name, size=gtk.ICON_SIZE_MENU):
    if name.startswith('gtk'):
        return _renderer.render_icon(name, size)
    else:
        path = paths.get_tortoise_icon(name)
        if path:
            try:
                w, h = gtk.icon_size_lookup(size)
                return gtk.gdk.pixbuf_new_from_file_at_size(path, w, h)
            except:
                pass
    return None

def get_icon_image(name):
    if name.startswith('gtk'):
        img = gtk.image_new_from_stock(name, gtk.ICON_SIZE_MENU)
    else:
        img = gtk.Image()
        pixbuf = get_icon_pixbuf(name)
        if pixbuf:
            img.set_from_pixbuf(pixbuf)
    return img

def normalize_dnd_paths(rawstr):
    paths = []
    for line in rawstr.rstrip('\x00').splitlines():
        if line.startswith('file:'):
            path = os.path.normpath(urllib.url2pathname(line[5:]))
            paths.append(path)
    return paths

def open_with_editor(ui, file, parent=None):
    def doedit():
        util.system('%s "%s"' % (editor, file))
    editor = (ui.config('tortoisehg', 'editor') or
            ui.config('gtools', 'editor') or
            os.environ.get('HGEDITOR') or
            ui.config('ui', 'editor') or
            os.environ.get('EDITOR', 'vi'))
    if os.path.basename(editor) in ('vi', 'vim', 'hgeditor'):
        from tortoisehg.hgtk import gdialog
        gdialog.Prompt(_('No visual editor configured'),
               _('Please configure a visual editor.'), parent).run()
        return False
    thread = threading.Thread(target=doedit, name='edit')
    thread.setDaemon(True)
    thread.start()
    return True

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
    def __init__(self, initial = None, title = _('Save File'),
                 filter = ((_('All files'), '*.*'),), filterindex = 1,
                 filename = '', open=False, multi=False):
        if initial is None:
            initial = os.path.expanduser("~")
        self.initial = initial
        self.filename = filename
        self.title = title
        self.filter = filter
        self.filterindex = filterindex
        self.open = open
        self.multi = multi

    def run(self):
        """run the file dialog, either return a file name, or False if
        the user aborted the dialog"""
        try:
            import win32gui, win32con, pywintypes            
            filepath = self.runWindows()
        except ImportError:
            filepath = self.runCompatible()
        if self.open:
            return filepath
        elif filepath:
            return self.overwriteConfirmation(filepath)
        else:
            return False

    def runWindows(self):

        def rundlg(q):
            import win32gui, win32con, pywintypes
            cwd = os.getcwd()
            fname = None
            try:
                f = ''
                for name, mask in self.filter:
                    f += '\0'.join([name, mask,''])
                flags = win32con.OFN_EXPLORER
                if self.multi:
                    flags |= win32con.OFN_ALLOWMULTISELECT
                opts = dict(InitialDir=self.initial,
                        Flags=flags,
                        File=self.filename,
                        DefExt=None,
                        Title=hglib.fromutf(self.title),
                        Filter= hglib.fromutf(f),
                        CustomFilter=None,
                        FilterIndex=self.filterindex)
                if self.open:
                    ret = win32gui.GetOpenFileNameW(**opts)
                else:
                    ret = win32gui.GetSaveFileNameW(**opts)
                fname = ret[0]
            except pywintypes.error:
                pass
            os.chdir(cwd)
            q.put(fname)

        q = Queue.Queue()
        thread = thread2.Thread(target=rundlg, args=(q,))
        thread.start()
        while thread.isAlive():
            # let gtk process events while we wait for rundlg finishing
            gtk.main_iteration(block=True)
        fname = False 
        if q.qsize():
            fname = q.get(0)
        if fname and self.multi and fname.find('\x00') != -1:
            splitted = fname.split('\x00')
            dir, fnames = splitted[0], splitted[1:]
            fname = []
            for fn in fnames:
                path = os.path.abspath(os.path.join(dir, fn))
                if os.path.exists(path):
                    fname.append(hglib.toutf(path))
        return fname

    def runCompatible(self):
        if self.open:
            action = gtk.FILE_CHOOSER_ACTION_OPEN
            buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                       gtk.STOCK_OPEN, gtk.RESPONSE_OK)
        else:
            action = gtk.FILE_CHOOSER_ACTION_SAVE
            buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                       gtk.STOCK_SAVE, gtk.RESPONSE_OK)
        dlg = gtk.FileChooserDialog(self.title, None, action, buttons)
        dlg.set_default_response(gtk.RESPONSE_OK)
        dlg.set_current_folder(self.initial)
        if self.multi:
            dlg.set_select_multiple(True)
        if not self.open:
            dlg.set_current_name(self.filename)
        for name, pattern in self.filter:
            fi = gtk.FileFilter()
            fi.set_name(name)
            fi.add_pattern(pattern)
            dlg.add_filter(fi)
        if dlg.run() == gtk.RESPONSE_OK:
            if self.multi:
                result = dlg.get_filenames()
            else:
                result = dlg.get_filename()
        else:
            result = False
        dlg.destroy()
        return result
    
    def overwriteConfirmation(self, filepath):        
        result = filepath
        if os.path.exists(filepath):
            from tortoisehg.hgtk import gdialog
            res = gdialog.Confirm(_('Confirm Overwrite'), [], None,
                _('The file "%s" already exists!\n\n'
                'Do you want to overwrite it?') % filepath).run()
            if res == gtk.RESPONSE_YES:
                os.remove(filepath)
            else:                
                result = False
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
    
        def rundlg(q):
            from win32com.shell import shell, shellcon
            import win32gui, pywintypes

            def BrowseCallbackProc(hwnd, msg, lp, data):
                if msg == shellcon.BFFM_INITIALIZED:
                    win32gui.SendMessage(
                        hwnd, shellcon.BFFM_SETSELECTION, 1, data)
                elif msg == shellcon.BFFM_SELCHANGED:
                    # Set the status text of the
                    # For this message, 'lp' is the address of the PIDL.
                    pidl = shell.AddressAsPIDL(lp)
                    try:
                        path = shell.SHGetPathFromIDList(pidl)
                        win32gui.SendMessage(
                            hwnd, shellcon.BFFM_SETSTATUSTEXT, 0, path)
                    except shell.error:
                        # No path for this PIDL
                        pass

            fname = None
            try: 
                flags = shellcon.BIF_EDITBOX | 0x40 #shellcon.BIF_NEWDIALOGSTYLE
                pidl, _, _ = shell.SHBrowseForFolder(
                   0,
                   None,
                   hglib.fromutf(self.title),
                   flags,
                   BrowseCallbackProc, # callback function
                   self.initial)       # 'data' param for the callback
                if pidl:
                    fname = hglib.toutf(shell.SHGetPathFromIDList(pidl))
            except (pywintypes.error, pywintypes.com_error):
                pass
            q.put(fname)

        q = Queue.Queue()
        thread = thread2.Thread(target=rundlg, args=(q,))
        thread.start()
        while thread.isAlive():
            # let gtk process events while we wait for rundlg finishing
            gtk.main_iteration(block=True)
        fname = None
        if q.qsize():
            fname = q.get(0)
        return fname

    def runCompatible(self):
        dialog = gtk.FileChooserDialog(title=self.title,
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

class NativeFileManager:
    """
    Wrapper for opening the specific file manager; Explorer on Windows,
    Nautilus File Manager on Linux.
    """
    def __init__(self, path):
        self.path = path

    def run(self):
        try:
            import pywintypes
            self.runExplorer()
        except ImportError:
            self.runNautilus()

    def runExplorer(self):
        import subprocess
        subprocess.Popen('explorer "%s"' % self.path)

    def runNautilus(self):
        import subprocess
        subprocess.Popen('nautilus --browser "%s"' % self.path)

def markup(text, **kargs):
    """
    A wrapper function for Pango Markup Language.

    All options must be passed as keywork arguments.
    """
    if len(kargs) == 0:
        return markup_escape_text(str(text))
    attr = ''
    for name, value in kargs.items():
        attr += ' %s="%s"' % (name, value)
    text = markup_escape_text(text)
    return '<span%s>%s</span>' % (attr, text)

class LayoutGroup(object):

    def __init__(self, width=0):
        self.width = width
        self.tables = []

    def add(self, *tables, **kargs):
        self.tables.extend(tables)
        if kargs.get('adjust', True):
            self.adjust(**kargs)

    def adjust(self, force=False):
        def realized():
            '''check all tables realized or not'''
            for table in self.tables:
                if tuple(table.allocation) == (-1, -1, 1, 1):
                    return False
            return True
        def trylater():
            '''retry when occurred "size-allocate" signal'''
            adjusted = [False]
            def allocated(table, rect, hid):
                table.disconnect(hid[0])
                if not adjusted[0] and realized():
                    adjusted[0] = True
                    self.adjust()
            for table in self.tables:
                hid = [None]
                hid[0] = table.connect('size-allocate', allocated, hid)
        # check all realized
        if not force and not realized():
            trylater()
            return
        # find out max width
        max = self.width
        for table in self.tables:
            first = table.get_first_header()
            w = first.allocation.width
            max = w > max and w or max
        # apply width
        for table in self.tables:
            first = table.get_first_header()
            first.set_size_request(max, -1)
            first.size_request()

class LayoutTable(gtk.VBox):
    """
    Provide 2 columns layout table.

    This table has 2 columns; first column is used for header, second
    is used for body. In default, the header will be aligned right and
    the body will be aligned left with expanded padding.
    """

    def __init__(self, **kargs):
        gtk.VBox.__init__(self)

        self.table = gtk.Table(1, 2)
        self.pack_start(self.table)
        self.headers = []

        self.set_default_paddings(kargs.get('xpad', -1),
                                  kargs.get('ypad', -1))
        self.set_default_options(kargs.get('headopts', None),
                                 kargs.get('bodyopts', None))

    def set_default_paddings(self, xpad=None, ypad=None):
        """
        Set default paddings between cells.

        LayoutTable has xpad=4, ypad=2 as preset padding values.

        xpad: Number. Pixcel value of padding for x-axis.
              Use -1 to reset padding to preset value.
              Default: None (no change).
        ypad: Number. Pixcel value of padding for y-axis.
              Use -1 to reset padding to preset value.
              Default: None (no change).
        """
        if xpad is not None:
            self.xpad = xpad >= 0 and xpad or 4
        if ypad is not None:
            self.ypad = ypad >= 0 and ypad or 2

    def set_default_options(self, headopts=None, bodyopts=None):
        """
        Set default options for markups of label.

        In default, LayoutTable doesn't use any markups and set the test
        as plane text.  See markup()'s description for more details of
        option parameters.  Note that if called add_row() with just one
        widget, it will be tried to apply 'bodyopts', not 'headopts'.

        headopts: Dictionary. Options used for markups of gtk.Label.
                  This option is only availabled for the label.
                  The text will be escaped automatically.  Default: None.
        bodyopts: [same as 'headopts']
        """
        self.headopts = headopts
        self.bodyopts = bodyopts

    def get_first_header(self):
        """
        Return the cell at top-left corner if exists.
        """
        if len(self.headers) > 0:
            return self.headers[0]
        return None

    def clear_rows(self):
        for child in self.table.get_children():
            self.table.remove(child)

    def add_row(self, *widgets, **kargs):
        """
        Append a new row to the table.

        widgets: mixed list of widget, string, number or None;
                 i.e. ['host:', gtk.Entry(), 20, 'port:', gtk.Entry()]
                 First item will be header, and the rest will be body
                 after packed into a gtk.HBox.

            widget: Standard GTK+ widget.
            string: Label text, will be converted gtk.Label.
            number: Fixed width padding.
            None: Flexible padding.

        kargs: 'padding', 'expand', 'xpad' and 'ypad' are availabled.

            padding: Boolean. If False, the padding won't append the end
                     of body.  Default: True.
            expand: Number. Position of body element to expand.  If you
                    specify this option, 'padding' option will be changed
                    to False automatically.  Default: -1 (last element).
            xpad: Number. Override default 'xpad' value.
            ypad: Same as 'xpad'.
            xhopt: Number. Combination of gtk.EXPAND, gtk.SHRINK or gtk.FILL.
                   Note that this option is applied with only head element.
                   Default: gtk.FILL.
            yhopt: Same as 'xhopt' except default value. Default: 0.
            xopt: Number. Combination of gtk.EXPAND, gtk.SHRINK or gtk.FILL.
                  Note that this option is applied with only body elements.
                  Default: gtk.FILL|gtk.EXPAND.
            yopt: Same as 'xopt' except default value. Default: 0.
            headopts: Dictionary. Override default 'headopts' value.
            bodyopts: Same as 'headopts'.
        """
        if len(widgets) == 0:
            return
        t = self.table
        rows = t.get_property('n-rows')
        t.set_property('n-rows', rows + 1)
        xpad = kargs.get('xpad', self.xpad)
        ypad = kargs.get('ypad', self.ypad)
        xhopt = kargs.get('xhopt', gtk.FILL)
        yhopt = kargs.get('yhopt', 0)
        xopt = kargs.get('xopt', gtk.FILL|gtk.EXPAND)
        yopt = kargs.get('yopt', 0)
        hopts = kargs.get('headopts', self.headopts)
        bopts = kargs.get('bodyopts', self.bodyopts)
        def getwidget(obj, opts=None):
            '''element converter'''
            if obj == None:
                return gtk.Label('')
            elif isinstance(obj, (int, long)):
                lbl = gtk.Label('')
                lbl.set_size_request(obj, -1)
                lbl.size_request()
                return lbl
            elif isinstance(obj, basestring):
                if opts is None:
                    lbl = gtk.Label(obj)
                else:
                    obj = markup(obj, **opts)
                    lbl = gtk.Label()
                    lbl.set_markup(obj)
                return lbl
            return obj
        def pack(*widgets, **kargs):
            '''pack some of widgets and return HBox'''
            expand = kargs.get('expand', -1)
            if len(widgets) <= expand:
                expand = -1
            padding = kargs.get('padding', expand == -1)
            if padding is True:
                widgets += (None,)
            expmap = [ w is None for w in widgets ]
            expmap[expand] = True
            widgets = [ getwidget(w, bopts) for w in widgets ]
            hbox = gtk.HBox()
            for i, obj in enumerate(widgets):
                widget = getwidget(obj, bopts)
                pad = i != 0 and 2 or 0
                hbox.pack_start(widget, expmap[i], expmap[i], pad)
            return hbox
        if len(widgets) == 1:
            cols = t.get_property('n-columns')
            widget = pack(*widgets, **kargs)
            t.attach(widget, 0, cols, rows, rows + 1, xopt, yopt, xpad, ypad)
        else:
            first = getwidget(widgets[0], hopts)
            if isinstance(first, gtk.Label):
                first.set_alignment(1, 0.5)
            t.attach(first, 0, 1, rows, rows + 1, xhopt, yhopt, xpad, ypad)
            self.headers.append(first)
            rest = pack(*(widgets[1:]), **kargs)
            t.attach(rest, 1, 2, rows, rows + 1, xopt, yopt, xpad, ypad)

class SlimToolbar(gtk.HBox):
    """
    Slim Toolbar, allows to add the buttons with small icon.
    """
    def __init__(self, tooltips=None):
        gtk.HBox.__init__(self)
        self.tooltips = tooltips
        self.groups = {}

    ### public methods ###

    def append_button(self, icon, tooltip=None, toggle=False, group=None):
        """
        icon: stock id or file name bundled in TortoiseHg.
        """
        if toggle:
            button = gtk.ToggleButton()
        else:
            button = gtk.Button()
        button.set_image(get_icon_image(icon))
        button.set_relief(gtk.RELIEF_NONE)
        button.set_focus_on_click(False)
        if self.tooltips and tooltip:
            self.tooltips.set_tip(button, tooltip)
        self.append_widget(button, padding=0, group=group)
        return button

    def append_widget(self, widget, expand=False, padding=2, group=None):
        self.pack_start(widget, expand, expand, padding)
        self.add_group(group, widget)

    def append_space(self):
        self.append_widget(gtk.Label(), expand=True, padding=0)

    def append_separator(self, group=None):
        self.append_widget(gtk.VSeparator(), group=group)

    def set_enable(self, group, enable=True):
        if not group or not self.groups.has_key(group):
            return
        for widget in self.groups[group]:
            widget.set_sensitive(enable)

    def set_visible(self, group, visible=True):
        if not group or not self.groups.has_key(group):
            return
        for widget in self.groups[group]:
            if visible is True:
                widget.set_no_show_all(False)
            widget.set_property('visible', visible)
            if visible is False:
                widget.set_no_show_all(True)

    ### internal method ###

    def add_group(self, group, widget):
        if not group or not widget:
            return
        if not self.groups.has_key(group):
            self.groups[group] = []
        self.groups[group].append(widget)

def create_menuitem(label, handler=None, icon=None, *args, **kargs):
    """
    Create a new menu item and append it the end of menu.

    label: a string to be shown as menu label.
    handler: a function to be connected with 'activate' signal.
             Default: None.
    icon: GKT+ stock item name or TortoiseHg's bundle icon name.
          Default: None.
    ascheck: whether enable toggle feature. Default: False.
    asradio: whether use radio menu item. Default: False.
    group: menu item instance to be used for group of radio menu item.
           Default: None.
    check: toggle or selection state for check/radio menu item.
           Default: False.
    sensitive: sensitive state on init. Default: True.
    use_underline: handle underline as accelerator key prefix.
                   Default: True.
    args: an argument list for 'handler' parameter.
          Default: [] (an empty list).
    """
    use_underline = kargs.get('use_underline', True)
    if gtk.gtk_version < (2, 14, 0) and not use_underline:
       # workaround (set_use_underline not available on gtk < 2.14)
       label = label.replace('_', '__')
    if kargs.get('asradio') or kargs.get('ascheck'):
        if kargs.get('asradio'):
            menu = gtk.RadioMenuItem(kargs.get('group'), label, use_underline=use_underline)
        else:
            menu = gtk.CheckMenuItem(label, use_underline=use_underline)
        menu.set_active(kargs.get('check', False))
    elif icon:
        menu = gtk.ImageMenuItem(label)
        menu.set_image(get_icon_image(icon))
    else:
        menu = gtk.MenuItem(label, use_underline=use_underline)
    if handler:
        args = kargs.get('args', [])
        menu.connect('activate', handler, *args)
    menu.set_sensitive(kargs.get('sensitive', True))
    menu.set_border_width(1)
    return menu

class MenuBuilder(object):
    '''controls creation of menus by ignoring separators at odd places'''
    def __init__(self):
        self.reset()

    ### public methods ###

    def reset(self):
        self.childs = []
        self.sep = None

    def append(self, *a, **k):
        menu = create_menuitem(*a, **k)
        self.append_child(menu)
        return menu

    def append_sep(self):
        self.append_child(gtk.SeparatorMenuItem())

    def append_submenu(self, label, submenu, icon=None, *a, **k):
        menu = create_menuitem(label, None, icon, *a, **k)
        menu.set_submenu(submenu)
        self.append_child(menu)

    def build(self):
        menu = gtk.Menu()
        for c in self.childs:
            menu.append(c)
        self.reset()
        return menu

    def get_menus(self):
        return self.childs[:]

    ### internal method ###

    def append_child(self, child):
        '''appends the child menu item, but ignores odd separators'''
        if isinstance(child, gtk.SeparatorMenuItem):
            if len(self.childs) > 0:
                self.sep = child
        else:
            if self.sep:
                self.childs.append(self.sep)
                self.sep = None
            self.childs.append(child)

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

def idle_add_single_call(f, *args):
    '''wrap function f for gobject.idle_add, so that f is guaranteed to be
    called only once, independent of its return value'''

    class single_call(object):
        def __init__(self, f, args):
           self.f = f
           self.args = args
        def __call__(self):
           self.f(*args)  # ignore return value of f
           return False   # return False to signal: don't call me again

    # functions passed to gobject.idle_add must return False, or they
    # will be called repeatedly. The single_call object wraps f and always
    # returns False when called. So the return value of f doesn't matter,
    # it can even return True (which would lead to gobject.idle_add
    # calling the function again, if used without single_call).
    gobject.idle_add(single_call(f, args))

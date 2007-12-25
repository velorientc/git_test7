# gtools.py - Graphical diff and status extension for Mercurial
#
# Copyright 2007 Brad Schick, brad at gmail . com
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.
# 
"""gtools extension provides graphical status and commit dialogs

The gtools extension provides gtk+ based graphical status, log,
and commit dialogs. Each dialogs provides a convenient way to see what 
has changed in a repository. Data is displayed in a list that can be
sorted, selected, and double-clicked to launch diff and editor tools.
Right-click context menus and toolbars provide operations like commit, 
add, view, delete, ignore, remove, revert, and refresh.

Files are diff'ed and edited in place whenever possible, so you can
make changes within external tools and save them directly back to the
working copy. To enable gtools:

   [extensions]
   hgext.gtools =

   [gtools]
   # external diff tool and options
   diffcmd = gdiff
   diffopts = -Nprc5
 
   # editor, if not specified [ui] editor is used
   editor = scite
 
   # set the fonts for the comments, diffs, and lists
   fontcomment = courier 10
   fontdiff = courier 10
   fontlist = courier 9

   # make the integrated diff window appear at the bottom or side
   diffbottom = False
 
The external diff tool is run as shown below. Unless specified otherwise,
file_rev1 and file_rev2 are the parent revision and the working copy 
respectively:

diffcmd diffopts file_rev1 file_rev2
"""

import mercurial.demandimport; mercurial.demandimport.disable()

import os
import threading
import StringIO
import sys
import shutil
import tempfile
import datetime
import cPickle

import pygtk
pygtk.require('2.0')
import gtk
import gobject
import pango

from mercurial.i18n import _
from mercurial.node import *
from mercurial import cmdutil, util, ui, hg, commands, patch
from hgext import extdiff
from shlib import shell_notify

class SimpleMessage(gtk.MessageDialog):
    def run(self):
        response = gtk.MessageDialog.run(self)
        self.destroy()
        return response


class Prompt(SimpleMessage):
    def __init__(self, title, message, parent):
        gtk.MessageDialog.__init__(self, parent, gtk.DIALOG_MODAL, gtk.MESSAGE_INFO,
                                    gtk.BUTTONS_CLOSE)
        self.set_title(title)
        self.set_markup('<b>' + message + '</b>')


class Confirm(SimpleMessage):
    """Dialog returns gtk.RESPONSE_YES or gtk.RESPONSE_NO 
    """
    def __init__(self, title, files, parent, primary=None):
        gtk.MessageDialog.__init__(self, parent, gtk.DIALOG_MODAL, gtk.MESSAGE_QUESTION,
                                    gtk.BUTTONS_YES_NO)
        self.set_title('Confirm ' + title)
        if primary is None:
            primary = title + ' file' + ((len(files) > 1 and 's') or '') + '?'
        primary = '<b>' + primary + '</b>'
        self.set_markup(primary)
        message = ''
        for i, file in enumerate(files):
            message += '   ' + file + '\n'
            if i == 9: 
                message += '   ...\n'
                break
        self.format_secondary_text(message)


class GDialog(gtk.Window):
    """GTK+ based dialog for displaying mercurial information

    The following methods are meant to be overridden by subclasses. At this
    point GCommit is really the only intended subclass.

        parse_opts(self)
        get_title(self)
        get_minsize(self)
        get_defsize(self)
        get_tbbuttons(self)
        get_body(self)
        get_extras(self)
        prepare_display(self)
        should_live(self, widget, event)
        save_settings(self)
        load_settings(self, settings)
    """

    # "Constants"
    settings_version = 1

    def __init__(self, ui, repo, pats, opts, main):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        self._cwd = repo.root
        self.ui = ui
        self.ui.interactive=False
        self.repo = repo
        self.pats = pats
        self.opts = opts
        self.main = main

    ### Following methods are meant to be overridden by subclasses ###

    def parse_opts(self):
        pass


    def get_title(self):
        return ''


    def get_minsize(self):
        return (395, 200)


    def get_defsize(self):
        return self._setting_defsize 


    def get_tbbuttons(self):
        return []


    def get_body(self):
        return None


    def get_extras(self):
        return None


    def prepare_display(self):
        pass


    def should_live(self, widget=None, event=None):
        return False


    def save_settings(self):
        rect = self.get_allocation()
        return {'gdialog': (rect.width, rect.height)}


    def load_settings(self, settings):
        if settings:
            self._setting_defsize = settings['gdialog']
        else:
            self._setting_defsize = (678, 585)

    ### End of overridable methods ###

    def display(self):
        self._parse_config()
        self._load_settings()
        self._setup_gtk()
        self._parse_opts()
        self.prepare_display()
        self.show_all()


    def test_opt(self, opt):
        return opt in self.opts and self.opts[opt]


    def _parse_config(self):
        # defaults    
        self.fontcomment = 'courier 10'
        self.fontdiff = 'courier 10'
        self.fontlist = 'courier 9'
        self.diffopts = ''
        self.diffcmd = ''
        self.diffbottom = ''

        for attr, setting in self.ui.configitems('gtools'):
            if setting : setattr(self, attr, setting)

        if not self.diffcmd :
            if not self.diffopts : self.diffopts = '-Npru'
            self.diffcmd = 'diff'

        if not self.diffbottom or self.diffbottom.lower() == 'false' or self.diffbottom == '0':
            self.diffbottom = False
        else:
            self.diffbottom = True


    def _parse_opts(self):
        # Remove dry_run since Hg only honors it for certain commands
        self.opts['dry_run'] = False
        self.opts['force_editor'] = False
        self.parse_opts()


    def merge_opts(self, defaults, mergelist=()):
        """Merge default options with the specified local options and globals.
        Results is defaults + merglist + globals
        """
        newopts = {}
        for hgopt in defaults:
            newopts[hgopt[1].replace('-', '_')] = hgopt[2]
        for mergeopt in mergelist:
            newopts[mergeopt] = self.opts[mergeopt]
        newopts.update(self.global_opts())
        return newopts


    def global_opts(self):
        globals = {}
        hgglobals = [opt[1].replace('-', '_') for opt in commands.globalopts if opt[1] != 'help']
        for key in self.opts:
            if key in  hgglobals :
                globals[key] = self.opts[key]
        return globals


    def count_revs(self):
        cnt = 0
        if self.test_opt('rev'):
            for rev in self.opts['rev']:
                cnt += len(rev.split(cmdutil.revrangesep, 1))
        return cnt


    def make_toolbutton(self, stock, label, handler, userdata=None):
        tbutton = gtk.ToolButton(stock)
        tbutton.set_use_underline(True)
        tbutton.set_label(label)
        tbutton.connect('clicked', handler, userdata)
        return tbutton


    def _setup_gtk(self):
        self.set_title(self.get_title())
        
        # Minimum size
        minx, miny = self.get_minsize()
        self.set_size_request(minx, miny)
        # Initial size
        defx, defy = self.get_defsize()
        self.set_default_size(defx, defy)
        
        vbox = gtk.VBox(False, 0)
        self.add(vbox)
        
        toolbar = gtk.Toolbar()
        tbuttons =  self.get_tbbuttons()
        for tbutton in tbuttons:
            toolbar.insert(tbutton, -1)

        vbox.pack_start(toolbar, False, False, 0)

        # Subclass returns the main body
        body = self.get_body()
        vbox.pack_start(body, True, True, 0)
        
        hbox = gtk.HBox(False, 0)
        hbox.set_border_width(6)
        vbox.pack_end(hbox, False, False, 0)
        
        bbox = gtk.HButtonBox()
        bbox.set_layout(gtk.BUTTONBOX_EDGE)
        hbox.pack_end(bbox, False, False)

        if self.main:
            button = gtk.Button(stock=gtk.STOCK_QUIT)
        else:
            button = gtk.Button(stock=gtk.STOCK_CLOSE)

        button.connect('clicked', self._quit_clicked)
        bbox.pack_end(button, False, False)
        self.connect('destroy', self._destroying)
        self.connect('delete_event', self.should_live)

        # Subclass provides extra stuff to left of Quit button
        extras = self.get_extras()
        if extras:
            hbox.pack_start(extras, False, False)


    def _quit_clicked(self, button):
        if not self.should_live():
            self.destroy()


    def _destroying(self, gtkobj):
        try:
            file = None
            settings = self.save_settings()
            versioned = (GDialog.settings_version, settings)
            dirname = os.path.join(os.path.expanduser('~'), '.hgext/gtools')
            filename = os.path.join(dirname, self.__class__.__name__)
            try:
                if not os.path.exists(dirname):
                    os.makedirs(dirname)
                file = open(filename, 'wb')
                cPickle.dump(versioned, file, cPickle.HIGHEST_PROTOCOL)
            except (IOError, cPickle.PickleError):
                pass
        finally:
            if file:
                file.close()
            if self.main:
                gtk.main_quit()


    def _load_settings(self):
        try:
            file = None
            settings = None
            dirname = os.path.join(os.path.expanduser('~'), '.hgext/gtools')
            filename = os.path.join(dirname, self.__class__.__name__)
            try:
                file = open(filename, 'rb')
                versioned = cPickle.load(file)
                if versioned[0] == GDialog.settings_version:
                    settings = versioned[1]
            except (IOError, cPickle.PickleError), inst:
                pass
        finally:
            if file:
                file.close()
            self.load_settings(settings)


    def restore_cwd(self):
        # extdiff works on relative directories to avoid showing temp paths. Since another thread
        # could be running that changed cwd, we always need to set it back. This is a race condition
        # but not likely to be a problem.
        os.chdir(self._cwd)


    def _hg_call_wrapper(self, title, command, showoutput=True):
        """Run the specified command and display any resulting aborts, messages, 
        and errors 
        """
        self.restore_cwd()
        textout = ''
        saved = sys.stderr
        errors = StringIO.StringIO()
        try:
            sys.stderr = errors
            self.ui.pushbuffer()
            try:
                command()
            except util.Abort, inst:
                Prompt(title + ' Aborted', str(inst), self).run()
                return False, ''
        finally:
            sys.stderr = saved
            textout = self.ui.popbuffer() 
            prompttext = ''
            if showoutput:
                prompttext = textout + '\n'
            prompttext += errors.getvalue()
            errors.close()
            if len(prompttext) > 1:
                Prompt(title + ' Messages and Errors', prompttext, self).run()

        return True, textout

class NativeSaveFileDialogWrapper:
    """Wrap the windows file dialog, or display default gtk dialog if that isn't available"""
    def __init__(self, InitialDir = None, Title = "Save File", Filter = {"All files": "*.*"}, FilterIndex = 1):
        import os.path
        if InitialDir == None:
            InitialDir = os.path.expanduser("~")
        self.InitialDir = InitialDir
        self.Title = Title
        self.Filter = Filter
        self.FilterIndex = FilterIndex

    def run(self):
        """run the file dialog, either return a file name, or False if the user aborted the dialog"""
        try:
            import win32gui
            if self.tortoiseHgIsInstalled(): #as of 20071021, the file dialog will hang if the tortoiseHg shell extension is installed. I have no clue why, yet - Tyberius Prime
                   return self.runCompatible()
            else:
                    return self.runWindows()
        except ImportError:
            return self.runCompatible()

    def tortoiseHgIsInstalled(self):
        import _winreg
        try:
            hkey = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,r"Software\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\Changed")
            if hkey:
                cls = _winreg.QueryValue(hkey,"")
                return cls == "{102C6A24-5F38-4186-B64A-237011809FAB}"
        except WindowsError: #reg key not found
            pass
        return False

    def runWindows(self):
        import win32gui, win32con, os
        filter = ""
        for name, pattern in self.Filter.items():
            filter += name + "\0" + pattern + "\0"
        customfilter = "\0"

        fname, customfilter, flags=win32gui.GetSaveFileNameW(
            InitialDir=self.InitialDir,
            Flags=win32con.OFN_EXPLORER,
            File='', DefExt='py',
            Title=self.Title,
            Filter="",
            CustomFilter="",
            FilterIndex=1)
        if fname:
            return fname
        else:
           return False

    def runCompatible(self):
        file_save =gtk.FileChooserDialog(self.Title,None,
                gtk.FILE_CHOOSER_ACTION_SAVE
                , (gtk.STOCK_CANCEL
                    , gtk.RESPONSE_CANCEL
                    , gtk.STOCK_SAVE
                    , gtk.RESPONSE_OK))
        file_save.set_default_response(gtk.RESPONSE_OK)
        file_save.set_current_folder(self.InitialDir)
        for name, pattern in self.Filter.items():
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

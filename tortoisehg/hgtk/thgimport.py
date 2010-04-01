# thgimport.py - TortoiseHg's dialog for (q)importing patches
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject
import tempfile

from tortoisehg.util.i18n import _

from tortoisehg.hgtk import gtklib, gdialog, cslist

COL_NAME  = 0
COL_LABEL = 1

DEST_REPO = 'repo'
DEST_MQ   = 'mq'

class ImportDialog(gdialog.GDialog):
    """ Dialog to import patches """

    def __init__(self, repo=None, dest=DEST_REPO, sources=None):
        gdialog.GDialog.__init__(self, resizable=True)

        self.done = False
        self.mqloaded = hasattr(self.repo, 'mq')
        self.clipboard = gtk.Clipboard()
        self.tempfiles = []
        self.initdest = dest
        if not self.mqloaded and dest == DEST_MQ:
            self.initdest = DEST_REPO
        self.initsrc = sources

        # persistent settings
        self.recent = self.settings.mrul('src_paths')

    ### Start of Overriding Section ###

    def get_title(self, reponame):
        return _('Import - %s') % reponame

    def get_icon(self):
        return 'menuimport.ico'

    def get_defsize(self):
        return (500, 390)

    def get_setting_name(self):
        return 'import'

    def get_body(self, vbox):
        # layout table
        self.table = table = gtklib.LayoutTable()
        vbox.pack_start(table, True, True, 2)

        ## source path combo & browse buttons
        self.src_list = gtk.ListStore(str)
        self.src_combo = gtk.ComboBoxEntry(self.src_list, 0)
        self.files_btn = gtk.Button(_('Browse...'))

        ## set given sources (but preview later)
        if self.initsrc:
            src = os.pathsep.join(self.initsrc)
            self.src_combo.child.set_text(src)

        ## other sources
        menubtn = gtk.ToggleButton()
        menubtn.set_focus_on_click(False)
        menubtn.add(gtk.Arrow(gtk.ARROW_DOWN, gtk.SHADOW_NONE))

        m = gtklib.MenuBuilder()
        m.append(_('Browse Directory...'), self.dir_clicked,
                 gtk.STOCK_DIRECTORY)
        m.append(_('Import from Clipboard'), self.clip_clicked,
                 gtk.STOCK_PASTE)
        self.menu = m.build()

        table.add_row(_('Source:'), self.src_combo, 1,
                      self.files_btn, menubtn, expand=0)

        ## add MRU paths to source combo
        for path in self.recent:
            self.src_list.append([path])

        # copy form thgstrip.py
        def createlabel():
            label = gtk.Label()
            label.set_alignment(0, 0.5)
            label.set_size_request(-1, 25)
            label.size_request()
            return label

        ## info label
        self.infolbl = createlabel()
        self.infobox = gtk.HBox()
        self.infobox.pack_start(self.infolbl, False, False)
        table.add_row(_('Preview:'), self.infobox, padding=False)

        ## dest combo
        self.dest_model = gtk.ListStore(gobject.TYPE_STRING, # dest name
                                        gobject.TYPE_STRING) # dest label
        for row in {DEST_REPO: _('Repository'),
                    DEST_MQ: _('Patch Queue')}.items():
            self.dest_model.append(row)
        self.dest_combo = gtk.ComboBox(self.dest_model)
        cell = gtk.CellRendererText()
        self.dest_combo.pack_start(cell, True)
        self.dest_combo.add_attribute(cell, 'text', COL_LABEL)

        for row in self.dest_model:
            name, label = self.dest_model[row.path]
            if name == self.initdest:
                self.dest_combo.set_active_iter(row.iter)
                break

        ## patch preview
        self.cslist = cslist.ChangesetList()
        table.add_row(None, self.cslist, padding=False,
                      yopt=gtk.FILL|gtk.EXPAND)
        self.cslist.set_dnd_enable(True)
        self.cslist.set_checkbox_enable(True)

        # signal handlers
        self.files_btn.connect('clicked', self.files_clicked)
        self.cslist.connect('list-updated', self.list_updated)
        self.cslist.connect('files-dropped', self.files_dropped)
        self.src_combo.connect('changed', lambda e: self.preview(queue=True))

        menubtn.connect('button-press-event', self.extra_pressed)
        popdown = lambda m: menubtn.set_active(False)
        self.menu.connect('selection-done', popdown)
        self.menu.connect('cancel', popdown)

        # hook thg-close/thg-exit
        def hook(dialog, orig):
            self.unlink_all_tempfiles()
            return orig(dialog)
        self.connect('thg-close', hook, gtklib.thgclose)
        self.connect('thg-exit', hook, gtklib.thgexit)

        # prepare to show
        self.cslist.clear()

    def get_extras(self, vbox):
        # dest combo
        if self.mqloaded:
            self.dest_combo.show_all()
            self.dest_combo.hide()
            self.infobox.pack_start(self.dest_combo, False, False, 6)

        # start preview
        if self.initsrc:
            self.preview()

    def get_buttons(self):
        return [('import', _('Import'), gtk.RESPONSE_OK),
                ('close', gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)]

    def get_default_button(self):
        return 'import'

    def get_action_map(self):
        return {gtk.RESPONSE_OK: self.doimport}

    def switch_to(self, normal, working, cmd):
        self.table.set_sensitive(normal)
        self.buttons['import'].set_property('visible', normal)
        self.buttons['close'].set_property('visible', normal)
        if normal:
            self.buttons['close'].grab_focus()

    def command_done(self, returncode, useraborted, *args):
        self.done = True
        self.add_to_mru()
        if returncode == 0:
            self.cmd.set_result(_('Imported successfully'), style='ok')
        elif useraborted:
            self.cmd.set_result(_('Canceled importing'), style='error')
        else:
            self.cmd.set_result(_('Failed to import'), style='error')

    def before_close(self):
        if len(self.cslist.get_items()) != 0 and not self.done:
            ret = gdialog.Confirm(_('Confirm Close'), [], self,
                                  _('Do you want to close?')).run()
            if ret != gtk.RESPONSE_YES:
                return False # don't close
            self.unlink_all_tempfiles()
        return True

    ### End of Overriding Section ###

    def files_clicked(self, button):
        initdir = self.get_initial_dir()
        result = gtklib.NativeSaveFileDialogWrapper(title=_('Select Patches'),
                        initial=initdir, open=True, multi=True).run()
        if result and result != initdir:
            if not isinstance(result, basestring):
                result = os.pathsep.join(result)
            self.src_combo.child.set_text(result)
            self.preview()

    def dir_clicked(self, menuitem):
        initdir = self.get_initial_dir()
        result = gtklib.NativeFolderSelectDialog(
                        title=_('Select Directory contains patches:'),
                        initial=initdir).run()
        if result and result != initdir:
            self.src_combo.child.set_text(result)
            self.preview()

    def clip_clicked(self, menuitem):
        text = self.clipboard.wait_for_text()
        if not text:
            return
        filepath = self.save_as_tempfile(text)
        cur_text = self.src_combo.child.get_text()
        self.src_combo.child.set_text(cur_text + os.pathsep + filepath)
        self.preview()

    def extra_pressed(self, button, event):
        if not button.get_active():
            button.set_active(True)
            self.menu.show_all()
            def pos(*args):
                x, y = button.window.get_origin()
                r = button.allocation
                return (x + r.x, y + r.y + r.height, True)
            self.menu.popup(None, None, pos, event.button, event.time)

    def list_updated(self, cslist, total, sel, *args):
        self.update_status(sel)

    def files_dropped(self, cslist, files, *args):
        src = self.src_combo.child.get_text()
        if src:
            files = [src] + files
        self.src_combo.child.set_text(os.pathsep.join(files))
        self.preview()

    def get_initial_dir(self):
        src = self.src_combo.child.get_text()
        if src and os.path.exists(src):
            if os.path.isdir(src):
                return src
            parent = os.path.dirname(src)
            if parent and os.path.exists(parent):
                return parent
        return None

    def add_to_mru(self):
        dirs = self.get_dirpaths()
        for dir in dirs:
            if dir.find(tempfile.gettempdir()) != -1:
                continue
            self.recent.add(dir)
            self.src_list.append([dir])
        self.settings.write()

    def save_as_tempfile(self, text):
        fd, filepath = tempfile.mkstemp(prefix='thg-patch-')
        os.write(fd, text)
        os.close(fd)
        self.tempfiles.append(filepath)
        return filepath

    def unlink_all_tempfiles(self):
        for path in self.tempfiles:
            os.unlink(path)

    def update_status(self, count):
        if count:
            inner = gtklib.markup(_('%s patches') % count, weight='bold')
            if self.mqloaded:
                info = _('%s will be imported to the') % inner
            else:
                info = _('%s will be imported to the repository') % inner
        else:
            info = gtklib.markup(_('Nothing to import'),
                                 weight='bold', color=gtklib.DRED)
        self.infolbl.set_markup(info)
        if self.mqloaded:
            self.dest_combo.set_property('visible', bool(count))
        self.buttons['import'].set_sensitive(bool(count))

    def get_filepaths(self):
        src = self.src_combo.child.get_text()
        if not src:
            return []
        files = []
        for path in src.split(os.pathsep):
            path = path.strip('\r\n\t ')
            if not os.path.exists(path) or path in files:
                continue
            if os.path.isdir(path):
                entries = os.listdir(path)
                for entry in entries:
                    file = os.path.join(path, entry)
                    if os.path.isfile(file):
                        files.append(file)
            elif os.path.isfile(path):
                files.append(path)
        return files

    def get_dirpaths(self):
        dirs = []
        files = self.get_filepaths()
        for file in files:
            dir = os.path.dirname(file)
            if os.path.isdir(dir) and dir not in dirs:
                dirs.append(dir)
        return dirs

    def get_dest(self):
        iter = self.dest_combo.get_active_iter()
        return self.dest_model.get(iter, COL_NAME)[0]

    def preview(self, queue=False):
        files = self.get_filepaths()
        if files:
            self.cslist.update(files, self.repo, queue=queue)
        else:
            self.cslist.clear()

    def doimport(self):
        items = self.cslist.get_items(sel=True)
        files = [file for file, sel in items if sel]
        if not files:
            return

        dest = self.get_dest()
        if DEST_REPO == dest:
            cmd = 'import'
        elif DEST_MQ == dest:
            cmd = 'qimport'
        else:
            raise _('unexpected destination name: %s') % dest

        # prepare command line
        cmdline = ['hg', cmd, '--verbose', '--']
        cmdline.extend(files)

        # start importing
        self.execute_command(cmdline)

def run(ui, *pats, **opts):
    dest = opts.get('mq', False) and DEST_MQ or DEST_REPO
    sources = []
    for item in pats:
        if os.path.exists(item):
            sources.append(os.path.abspath(item))
    return ImportDialog(dest=dest, sources=sources)

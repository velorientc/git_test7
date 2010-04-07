# quickop.py - TortoiseHg's dialog for quick dirstate operations
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import pango

from mercurial import cmdutil, util

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, shlib

from tortoisehg.hgtk import gtklib, gdialog

LABELS = { 'add': (_('Select files to add'), _('Add')),
           'forget': (_('Select files to forget'), _('Forget')),
           'revert': (_('Select files to revert'), _('Revert')),
           'remove': (_('Select files to remove'), _('Remove')),}

DEFAULT_SIZE = (450, 300)
DEFAULT_POS = (0, 0)

class QuickOpDialog(gdialog.GDialog):
    """ Dialog for performing quick dirstate operations """
    def __init__(self, command, pats):
        gdialog.GDialog.__init__(self, resizable=True)
        self.pats = pats

        # Handle rm alias
        if command == 'rm':
            command = 'remove'
        self.command = command

        # show minimize/maximize buttons
        self.realize()
        if self.window:
            self.window.set_decorations(gtk.gdk.DECOR_ALL)

    ### Start of Overriding Section ###

    def get_title(self, reponame):
        return reponame + ' - hg ' + self.command

    def get_icon(self):
        return 'hg.ico'

    def get_defsize(self):
        return self.defsize

    def get_setting_name(self):
        return 'quickop'

    def get_body(self, vbox):
        os.chdir(self.repo.root)

        # wrap box
        wrapbox = gtk.VBox()
        wrapbox.set_border_width(5)
        vbox.pack_start(wrapbox, True, True)
        self.wrapbox = wrapbox

        lbl = gtk.Label(LABELS[self.command][0])
        lbl.set_alignment(0, 0)
        wrapbox.pack_start(lbl, False, False)

        def keypressed(tree, event):
            'Make spacebar toggle selected rows'
            if event.keyval != 32:
                return False
            def toggler(model, path, bufiter):
                model[path][0] = not model[path][0]
            selection = tree.get_selection()
            selection.selected_foreach(toggler)
            return True

        # add file list treeview
        fm = gtk.ListStore(bool, # Checked
                           str,  # Path
                           str,  # Path-UTF8
                           str)  # Status
        self.filetree = gtk.TreeView(fm)
        self.filetree.connect('key-press-event', keypressed)
        self.filetree.set_headers_clickable(True)
        self.filetree.set_reorderable(False)
        if hasattr(self.filetree, 'set_rubber_banding'):
            self.filetree.set_rubber_banding(True)
        fontlist = hglib.getfontconfig()['fontlist']
        self.filetree.modify_font(pango.FontDescription(fontlist))

        def select_toggle(cell, path):
            fm[path][0] = not fm[path][0]

        # file selection checkboxes
        toggle_cell = gtk.CellRendererToggle()
        toggle_cell.connect('toggled', select_toggle)
        toggle_cell.set_property('activatable', True)

        col = gtk.TreeViewColumn('', toggle_cell, active=0)
        col.set_resizable(False)
        self.filetree.append_column(col)

        col = gtk.TreeViewColumn(_('status'), gtk.CellRendererText(), text=3)
        self.filetree.append_column(col)

        col = gtk.TreeViewColumn(_('path'), gtk.CellRendererText(), text=2)
        self.filetree.append_column(col)

        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller.add(self.filetree)
        wrapbox.pack_start(scroller, True, True, 6)

        def toggleall(button):
            for row in self.filetree.get_model():
                row[0] = not row[0]

        # extra box
        self.extrabox = hbox = gtk.HBox()
        wrapbox.pack_start(hbox, False, False)

        ## toggle button
        tb = gtk.Button(_('Toggle all selections'))
        tb.connect('pressed', toggleall)
        hbox.pack_start(tb, False, False)

        if self.command == 'revert':
            ## no backup checkbox
            chk = gtk.CheckButton(_('Do not save backup files (*.orig)'))
            hbox.pack_start(chk, False, False, 6)
            self.nobackup = chk

            ## padding
            hbox.pack_start(gtk.Label())

        types = { 'add' : 'I?',
                  'forget' : 'MAR!C',
                  'revert' : 'MAR!',
                  'remove' : 'MAR!CI?',
                }
        filetypes = types[self.command]

        try:
            matcher = cmdutil.match(self.repo, self.pats)
            status = self.repo.status(match=matcher,
                                 clean='C' in filetypes,
                                 ignored='I' in filetypes,
                                 unknown='?' in filetypes)
        except (IOError, util.Abort), e:
            gdialog.Prompt(_('Unable to determine repository status'),
                           str(e), self).run()
            self.earlyout=True
            self.hide()
            return

        (modified, added, removed, deleted, unknown, ignored, clean) = status
        if 'M' in filetypes:
            for f in modified:
                fm.append([True, f, hglib.toutf(f), _('modified')])
        if 'A' in filetypes:
            for f in added:
                fm.append([True, f, hglib.toutf(f), _('added')])
        if 'R' in filetypes:
            for f in removed:
                fm.append([True, f, hglib.toutf(f), _('removed')])
        if '!' in filetypes:
            for f in deleted:
                fm.append([True, f, hglib.toutf(f), _('missing')])
        if '?' in filetypes:
            for f in unknown:
                fm.append([True, f, hglib.toutf(f), _('unknown')])
        if 'I' in filetypes:
            for f in ignored:
                if self.command == 'remove' or f in self.pats:
                    fm.append([True, f, hglib.toutf(f), _('ignored')])
        if 'C' in filetypes:
            for f in clean:
                if self.command == 'remove' or f in self.pats:
                    fm.append([True, f, hglib.toutf(f), _('clean')])

        if not len(fm):
            gdialog.Prompt(_('No appropriate files'),
                           _('No files found for this operation'), self).run()
            self.earlyout=True
            self.hide()

    def get_buttons(self):
        return [('go', LABELS[self.command][1], gtk.RESPONSE_OK),
                ('cancel', gtk.STOCK_CANCEL, gtk.RESPONSE_CLOSE)]

    def get_default_button(self):
        return 'go'

    def get_action_map(self):
        return {gtk.RESPONSE_OK: self.operation}

    def switch_to(self, normal, working, cmd):
        self.wrapbox.set_sensitive(normal)
        self.buttons['go'].set_property('visible', normal)
        self.buttons['cancel'].set_property('visible', normal)
        if normal:
            self.buttons['cancel'].grab_focus()

    def command_done(self, returncode, useraborted, list):
        if returncode == 0:
            shlib.shell_notify(list)
            self.cmd.set_result(_('Successfully'), style='ok')
        elif useraborted:
            self.cmd.set_result(_('Canceled'), style='error')
        else:
            self.cmd.set_result(_('Failed'), style='error')

    def before_show(self):
        # restore dialog state
        if self.defmax:
            self.maximize()

        # restore dialog position
        screen = self.get_screen()
        w, h = screen.get_width(), screen.get_height()
        x, y = self.defpos
        if x >= 0 and x < w and y >= 0 and y < h:
            self.move(x, y)

    def load_settings(self):
        self.defsize = self.settings.get_value('size', DEFAULT_SIZE)
        self.defpos = self.settings.get_value('pos', DEFAULT_POS)
        self.defmax = self.settings.get_value('maximize', False)

    def store_settings(self):
        state = self.window.get_state()
        ismaximized = bool(state & gtk.gdk.WINDOW_STATE_MAXIMIZED)
        if ismaximized or state & gtk.gdk.WINDOW_STATE_ICONIFIED:
            self.settings.set_value('size', DEFAULT_SIZE)
            self.settings.set_value('pos', DEFAULT_POS)
        else:
            rect = self.get_allocation()
            self.settings.set_value('size', (rect.width, rect.height))
            self.settings.set_value('pos', self.get_position())
        self.settings.set_value('maximize', ismaximized)
        self.settings.write()

    ### End of Overriding Section ###

    def operation(self):
        fm = self.filetree.get_model()
        deleting = self.command == 'remove'
        list, dellist = [], []
        for row in fm:
            if not row[0]: continue
            if deleting and row[3] in (_('unknown'), _('ignored')):
                dellist.append(row[1])
            else:
                list.append(row[1])

        if not (list or dellist):
            gdialog.Prompt(_('No files selected'),
                           _('No operation to perform'), self).run()
            return

        for file in dellist:
            try:
                os.unlink(file)
            except IOError:
                pass

        if not list:
            gtklib.idle_add_single_call(self.response, gtk.RESPONSE_CLOSE)
            return

        # prepare command line
        cmdline = ['hg', self.command, '--verbose']
        if hasattr(self, 'nobackup') and self.nobackup.get_active():
            cmdline.append('--no-backup')
        cmdline.append('--')
        cmdline += list

        # execute command
        self.execute_command(cmdline, list)

def run(ui, *pats, **opts):
    pats = hglib.canonpaths(pats)
    if opts.get('canonpats'):
        pats = list(pats) + opts['canonpats']
    return QuickOpDialog(opts.get('alias'), pats)
